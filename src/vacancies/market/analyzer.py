"""Market skill intelligence module with two datasets."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ..core.enums import Currency, DmsStatus, TaxType, WorkFormat
from ..core.models import Vacancy, SalaryInfo
from ..role_pack.registry import RolePackRegistry

logger = logging.getLogger(__name__)


@dataclass
class SkillOccurrence:
    """Single occurrence of a skill in a vacancy."""
    skill_id: str
    skill_name: str
    category: str
    vacancy_id: str
    vacancy_title: str
    employer: str
    source_name: str
    source_url: str
    requirement_strength: str  # explicit_required, explicit_preferred, mentioned, inferred, unknown
    extracted_phrase: str
    extracted_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SkillStatistics:
    """Aggregated statistics for a skill."""
    skill_id: str
    skill_name: str
    category: str
    total_vacancies: int  # unique vacancies mentioning this skill
    total_employers: int  # unique employers mentioning this skill
    explicit_required: int = 0
    explicit_preferred: int = 0
    mentioned: int = 0
    inferred: int = 0
    unknown: int = 0
    evidence: List[str] = field(default_factory=list)  # sample vacancy URLs
    percentage_of_vacancies: float = 0.0
    percentage_of_employers: float = 0.0

    @property
    def total_mentions(self) -> int:
        return self.explicit_required + self.explicit_preferred + self.mentioned + self.inferred + self.unknown


@dataclass
class MarketAnalysisResult:
    """Complete market analysis result."""
    total_unique_vacancies: int
    total_unique_employers: int
    total_sources: int
    skill_stats: List["SkillStatistics"]
    eligible_vacancy_count: int
    market_sample_vacancy_count: int
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    limitations: List[str] = field(default_factory=list)

    def get_top_skills(self, n: int = 20, min_vacancies: int = 1) -> List["SkillStatistics"]:
        """Get top N skills by vacancy count."""
        filtered = [s for s in self.skill_stats if s.total_vacancies >= min_vacancies]
        return sorted(filtered, key=lambda s: -s.total_vacancies)[:n]

    def get_skills_by_category(self, category: str) -> List["SkillStatistics"]:
        return [s for s in self.skill_stats if s.category == category]


class SkillExtractor:
    """Extract skills from vacancy descriptions."""

    def __init__(self, role_pack_id: str = "go_junior") -> None:
        self.role_pack_id = role_pack_id
        self.registry = RolePackRegistry()
        self.role_pack = self.registry.load(role_pack_id) or self.registry._builtin_packs.get(role_pack_id)

    def extract_skills(self, vacancy: "Vacancy") -> List[SkillOccurrence]:
        """Extract skills from a single vacancy."""
        if not self.role_pack:
            return []

        occurrences = []
        text = self._get_vacancy_text(vacancy)

        for skill_def in self.role_pack.skills:
            # Check for skill mentions
            matches = self._find_skill_mentions(text, skill_def)
            for match in matches:
                req_strength = self._determine_requirement_strength(vacancy, skill_def, match)
                occ = SkillOccurrence(
                    skill_id=skill_def.skill_id,
                    skill_name=skill_def.name,
                    category=skill_def.category,
                    vacancy_id=vacancy.id,
                    vacancy_title=vacancy.title,
                    employer=vacancy.employer or "Unknown",
                    source_name=vacancy.source_name,
                    source_url=vacancy.source_url,
                    requirement_strength=req_strength,
                    extracted_phrase=match[:200],
                )
                yield occ

    def _get_vacancy_text(self, vacancy: "Vacancy") -> str:
        """Combine all text fields for skill extraction."""
        parts = []
        if vacancy.title:
            parts.append(vacancy.title)
        if vacancy.description:
            parts.append(vacancy.description)
        if vacancy.requirements:
            parts.append(vacancy.requirements)
        if vacancy.responsibilities:
            parts.append(vacancy.responsibilities)
        if vacancy.technology_stack:
            parts.append(" ".join(vacancy.technology_stack))
        return " ".join(parts).lower()

    def _find_skill_mentions(self, text: str, skill_def: Any) -> List[str]:
        """Find mentions of a skill in text."""
        matches = []
        # Check primary name
        name = skill_def.name.lower()
        if name in text:
            matches.append(skill_def.name)
        # Check aliases
        for alias in skill_def.aliases:
            alias_lower = alias.lower()
            if alias_lower in text:
                matches.append(alias)
        return matches

    def _determine_requirement_strength(self, vacancy: "Vacancy", skill_def: Any, match: str) -> str:
        """Determine requirement strength based on context."""
        text = self._get_vacancy_text(vacancy)
        match_pos = text.find(match.lower())

        # Check surrounding context for requirement keywords
        context_window = 100
        start = max(0, match_pos - context_window)
        end = min(len(text), match_pos + len(match) + context_window)
        context = text[start:end]

        # Requirement keywords
        required_keywords = {"требуется", "обязательно", "must", "required", "necessary", "essential", "нужен", "нужны"}
        preferred_keywords = {"плюс", "желательно", "предпочтительно", "plus", "preferred", "nice to have", "welcome"}

        context_lower = context.lower()
        if any(kw in context_lower for kw in required_keywords):
            return "explicit_required"
        if any(kw in context_lower for kw in preferred_keywords):
            return "explicit_preferred"

        # Check skill definition
        if hasattr(skill_def, 'requirement_strength'):
            return skill_def.requirement_strength

        return "mentioned"


class MarketAnalyzer:
    """Analyze market skill intelligence from vacancy corpus."""

    def __init__(self, role_pack_id: str = "go_junior") -> None:
        self.role_pack_id = role_pack_id
        self.registry = RolePackRegistry()
        self.role_pack = self.registry.load(role_pack_id) or self.registry._builtin_packs.get(role_pack_id)
        self.extractor = SkillExtractor(role_pack_id)

    def analyze(
        self,
        vacancies: List["Vacancy"],
        eligible_vacancies: Optional[List["Vacancy"]] = None,
    ) -> "MarketAnalysisResult":
        """Analyze market skill intelligence from vacancy corpus."""
        if not self.role_pack:
            logger.warning("No role pack loaded")
            return MarketAnalysisResult(
                total_unique_vacancies=0,
                total_unique_employers=0,
                total_sources=0,
                skill_stats=[],
                eligible_vacancy_count=0,
                market_sample_vacancy_count=len(vacancies),
                limitations=["No role pack loaded"],
            )

        # Separate into two datasets
        eligible = eligible_vacancies or []
        ineligible_ids = set(id(v) for v in eligible)
        market_sample = [v for v in vacancies if id(v) not in ineligible_ids]

        logger.info(f"Analyzing {len(eligible)} eligible + {len(market_sample)} market sample vacancies")

        # Extract skills from both datasets
        eligible_occurrences = list(self._extract_all_skills(eligible))
        market_occurrences = list(self._extract_all_skills(market_sample))

        # Compute statistics
        skill_stats = self._compute_skill_statistics(eligible_occurrences, market_occurrences)

        # Compute unique counts
        all_vacancies = vacancies
        unique_employers = set(v.employer for v in all_vacancies if v.employer)
        sources = set(v.source_name for v in all_vacancies)

        return MarketAnalysisResult(
            total_unique_vacancies=len(vacancies),
            total_unique_employers=len(unique_employers),
            total_sources=len(set(v.source_name for v in all_vacancies)),
            skill_stats=skill_stats,
            eligible_vacancy_count=len(eligible),
            market_sample_vacancy_count=len(market_sample),
            limitations=self._generate_limitations(vacancies),
        )

    def _extract_all_skills(self, vacancies: List["Vacancy"]) -> List[Any]:
        """Extract all skill occurrences from vacancies."""
        occurrences = []
        for v in vacancies:
            for occ in self.extractor.extract_skills(v):
                occurrences.append(occ)
        return occurrences

    def _compute_skill_statistics(
        self,
        eligible_occurrences: List[Any],
        market_occurrences: List[Any],
    ) -> List[Any]:
        """Compute skill statistics from occurrences."""
        from ..role_pack.go_junior import GO_JUNIOR_ROLE_PACK

        # Combine occurrences from both cohorts. Counts below are computed over
        # UNIQUE canonical vacancies (a vacancy mentioning a skill via several
        # aliases is counted once), never raw duplicate listings.
        all_occurrences = eligible_occurrences + market_occurrences

        # Strength priority: required > preferred > mentioned > inferred > unknown
        strength_priority = {
            "explicit_required": 4,
            "explicit_preferred": 3,
            "mentioned": 2,
            "inferred": 1,
            "unknown": 0,
        }

        # skill -> {vacancy_id -> [strengths]}  (deduplicates alias mentions)
        vac_by_skill: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
        employer_by_skill: Dict[str, Set[str]] = defaultdict(set)
        urls_by_skill: Dict[str, Set[str]] = defaultdict(set)

        for occ in all_occurrences:
            vac_by_skill[occ.skill_id][occ.vacancy_id].append(occ.requirement_strength)
            if occ.employer:
                employer_by_skill[occ.skill_id].add(occ.employer)
            if occ.source_url:
                urls_by_skill[occ.skill_id].add(occ.source_url)

        total_vacancies = len(set(occ.vacancy_id for occ in all_occurrences))
        total_employers = len(set(occ.employer for occ in all_occurrences if occ.employer))

        # Enumerate EVERY role-pack skill so absent skills become explicit zeros
        # (each stat has evidence links OR an explicit zero, never phantom counts).
        stats: List[Any] = []
        for skill_def in GO_JUNIOR_ROLE_PACK.skills:
            skill_id = skill_def.skill_id
            vac_map = vac_by_skill.get(skill_id, {})
            vac_count = len(vac_map)

            label_counts = {
                "explicit_required": 0,
                "explicit_preferred": 0,
                "mentioned": 0,
                "inferred": 0,
                "unknown": 0,
            }
            # One vacancy contributes to exactly one label bucket (its strongest).
            for strengths in vac_map.values():
                best = max(strengths, key=lambda s: strength_priority.get(s, 0))
                label_counts[best] += 1

            employer_set = employer_by_skill.get(skill_id, set())
            url_set = urls_by_skill.get(skill_id, set())

            stats.append({
                "skill_id": skill_id,
                "skill_name": skill_def.name,
                "category": skill_def.category,
                "total_vacancies": vac_count,
                "total_employers": len(employer_set),
                "explicit_required": label_counts["explicit_required"],
                "explicit_preferred": label_counts["explicit_preferred"],
                "mentioned": label_counts["mentioned"],
                "inferred": label_counts["inferred"],
                "unknown": label_counts["unknown"],
                "percentage_of_vacancies": round(vac_count / total_vacancies * 100, 1) if total_vacancies else 0.0,
                "percentage_of_employers": round(len(employer_set) / total_employers * 100, 1) if total_employers else 0.0,
                "evidence": sorted(url_set),
            })

        # Sort by total_vacancies descending (stable: ties keep role-pack order)
        stats.sort(key=lambda x: -x["total_vacancies"])
        return stats

    def _generate_limitations(self, vacancies: List["Vacancy"]) -> List[str]:
        """Generate list of analysis limitations."""
        limitations = []

        # Check for missing data
        no_salary = sum(1 for v in vacancies if v.salary.from_amount is None and v.salary.to_amount is None)
        if no_salary > 0:
            limitations.append(f"{no_salary} vacancies have no salary information")

        no_format = sum(1 for v in vacancies if v.work_format.value == "unknown")
        if no_format > 0:
            limitations.append(f"{no_format} vacancies have unknown work format")

        no_location = sum(1 for v in vacancies if not v.location)
        if no_location > 0:
            limitations.append(f"{no_location} vacancies have no location")

        failed_sources = set()
        for v in vacancies:
            if v.status.value in ("check_failed", "not_suitable"):
                failed_sources.add(v.source_name)
        if failed_sources:
            limitations.append(f"Sources with issues: {', '.join(failed_sources)}")

        return limitations