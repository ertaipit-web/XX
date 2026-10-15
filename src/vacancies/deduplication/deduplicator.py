"""Cross-source deduplication with staged algorithm."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from ..core.enums import WorkFormat
from ..core.models import Vacancy
from ..role_pack.registry import RolePackRegistry

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of deduplication."""
    unique_vacancies: List["Vacancy"]
    duplicate_groups: List[List["Vacancy"]]
    merged_count: int
    uncertain_matches: List[Tuple["Vacancy", "Vacancy", float]]  # (vac1, vac2, similarity)


class URLCanonicalizer:
    """Canonicalize URLs for deduplication."""

    # Tracking parameters to remove
    TRACKING_PARAMS = frozenset({
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "yclid", "gclid", "fbclid", "msclkid", "dclid",
        "ref", "source", "from", "via", "share",
        "_ga", "_gl", "_hsenc", "_hsmi",
        "mc_cid", "mc_eid",
        "utm_id", "utm_source_platform", "utm_creative_format", "utm_marketing_tactic",
    })

    @classmethod
    def canonicalize(cls, url: str) -> str:
        """Remove tracking parameters and normalize URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            # Normalize scheme and host
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            # Remove www prefix
            if netloc.startswith("www."):
                netloc = netloc[4:]
            # Remove trailing slash from path
            path = parsed.path.rstrip("/")
            # Filter query parameters
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in query_params.items() if k.lower() not in cls.TRACKING_PARAMS}
            new_query = urlencode(filtered, doseq=True)
            return urlunparse((scheme, netloc, path, "", new_query, ""))
        except Exception:
            return url


class EmployerNormalizer:
    """Normalize employer names for comparison."""

    # Common suffixes to remove
    SUFFIXES = frozenset({
        "ooo", "зАО", "АО", "LLC", "Inc", "Ltd", "Group", "Corporation",
        "Corp", "Company", "Co", "Holding", "Group", "Solutions", "Systems",
        "Technologies", "Tech", "Labs", "Lab", "Studio", "Agency", "Digital",
        "Service", "Services", "Platform", "Platforma",
    })

    @classmethod
    def normalize(cls, name: str) -> str:
        """Normalize employer name for comparison."""
        if not name:
            return ""
        # Lowercase, remove punctuation
        name = name.lower()
        name = re.sub(r"[^\w\s]", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        # Remove common suffixes
        words = name.split()
        filtered = [w for w in words if w not in cls.SUFFIXES]
        return " ".join(filtered)


class TitleNormalizer:
    """Normalize vacancy titles for comparison."""

    # Prefixes/suffixes to remove
    PREFIXES = frozenset({
        "вакансия", "vacancy", "position", "job", "job opening",
        "junior", "middle", "senior", "lead", "staff", "principal",
        "junior ", "middle ", "senior ", "lead ", "staff ",
    })

    @classmethod
    def normalize(cls, title: str) -> str:
        """Normalize title for comparison."""
        if not title:
            return ""
        title = title.lower()
        title = re.sub(r"[^\w\s]", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        # Remove common prefixes
        words = title.split()
        filtered = []
        skip_prefix = True
        for word in words:
            if skip_prefix and word in cls.PREFIXES:
                continue
            filtered.append(word)
            skip_prefix = False
        return " ".join(filtered)


class Deduplicator:
    """Staged cross-source deduplication."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        title_threshold: float = 0.85,
        employer_threshold: float = 0.8,
        location_threshold: float = 0.8,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.title_threshold = title_threshold
        self.employer_threshold = employer_threshold
        self.location_threshold = location_threshold

    def deduplicate(self, vacancies: List["Vacancy"]) -> DeduplicationResult:
        """Run staged deduplication."""
        if not vacancies:
            return DeduplicationResult(
                unique_vacancies=[],
                duplicate_groups=[],
                merged_count=0,
                uncertain_matches=[],
            )

        # Stage 1: Canonicalize URLs
        for v in vacancies:
            v.canonical_url = URLCanonicalizer.canonicalize(v.source_url)

        # Stage 2: Exact URL / source ID match
        unique_by_url: Dict[str, "Vacancy"] = {}
        for v in vacancies:
            key = v.canonical_url or v.id
            if key in unique_by_url:
                # Merge alternate URLs
                existing = unique_by_url[key]
                if v.source_url not in existing.alternate_urls:
                    existing.alternate_urls.append(v.source_url)
                if v.source_name not in existing.source_name:
                    existing.source_name += f" | {v.source_name}"
            else:
                unique_by_url[key] = v

        # Stage 3: Cross-source fuzzy matching
        candidates = list(unique_by_url.values())
        merged = set()
        final: List["Vacancy"] = []
        duplicate_groups: List[List["Vacancy"]] = []
        uncertain_matches: List[Tuple["Vacancy", "Vacancy", float]] = []

        for i, v1 in enumerate(candidates):
            if i in merged:
                continue

            duplicates = [v1]
            for j, v2 in enumerate(candidates[i+1:], i+1):
                if j in merged:
                    continue
                similarity = self._compute_similarity(v1, v2)
                if similarity >= self.similarity_threshold:
                    duplicates.append(v2)
                    merged.add(j)
                elif similarity >= 0.7:
                    uncertain_matches.append((v1, v2, similarity))

            if len(duplicates) > 1:
                primary = duplicates[0]
                for dup in duplicates[1:]:
                    primary.alternate_urls.append(dup.source_url)
                    if dup.source_name not in primary.source_name:
                        primary.source_name += f" | {dup.source_name}"
                final.append(primary)
                duplicate_groups.append(duplicates)
            else:
                final.append(v1)

        return DeduplicationResult(
            unique_vacancies=final,
            duplicate_groups=duplicate_groups,
            merged_count=len(vacancies) - len(final),
            uncertain_matches=uncertain_matches,
        )

    def _compute_similarity(self, v1: "Vacancy", v2: "Vacancy") -> float:
        """Compute similarity between two vacancies (0-1)."""
        # Must be from different sources
        if v1.source_name == v2.source_name:
            return 0.0

        # Title similarity
        title1 = TitleNormalizer.normalize(v1.title)
        title2 = TitleNormalizer.normalize(v2.title)
        title_sim = SequenceMatcher(None, title1, title2).ratio()

        # Employer similarity
        emp1 = EmployerNormalizer.normalize(v1.employer or "")
        emp2 = EmployerNormalizer.normalize(v2.employer or "")
        emp_sim = SequenceMatcher(None, emp1, emp2).ratio() if emp1 and emp2 else 0.0

        # Location similarity
        loc1 = (v1.location or "").lower().strip()
        loc2 = (v2.location or "").lower().strip()
        loc_sim = SequenceMatcher(None, loc1, loc2).ratio() if loc1 and loc2 else 0.0

        # Work format match
        fmt_match = 1.0 if v1.work_format == v2.work_format else 0.0

        # Weighted similarity
        # Title and employer are most important
        similarity = (
            title_sim * 0.4 +
            emp_sim * 0.35 +
            loc_sim * 0.15 +
            fmt_match * 0.1
        )

        return similarity