from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.enums import Currency, WorkFormat
from ..core.models import CandidateProfile, SearchQuery, Vacancy
from ..llm.client import BaseLLMClient
from ..llm.prompts import INTAKE_SYSTEM, build_intake_prompt

logger = logging.getLogger(__name__)


@dataclass
class AgentBase:
    name: str

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError


@dataclass
class CareerIntakeAgent(AgentBase):
    """Parses a raw text query and extracts candidate profile criteria.

    Uses an optional LLM client for free-text parsing; falls back to
    deterministic heuristics when the LLM is unavailable or returns garbage.
    """

    name: str = "Career Intake Agent"
    llm: Optional[BaseLLMClient] = None

    def run(self, raw_query: str | None = None, profile: CandidateProfile | None = None) -> Dict[str, Any]:
        """Parse raw query string and merge with existing profile.

        Returns:
            Dict with 'profile' (CandidateProfile), 'messages' (list[str]),
            'contradictions' (list[str]), 'missing_data' (list[str]).
        """
        if profile is None:
            profile = CandidateProfile()

        messages: List[str] = []
        contradictions: List[str] = []
        missing_data: List[str] = []

        if not raw_query:
            messages.append("No query provided, using default profile")
            return {
                "profile": profile,
                "messages": messages,
                "contradictions": contradictions,
                "missing_data": missing_data,
            }

        # --- LLM path -------------------------------------------------
        if self.llm is not None:
            parsed = self._parse_with_llm(raw_query)
            if parsed:
                self._apply_llm_result(profile, parsed, messages, contradictions, missing_data)
                return {
                    "profile": profile,
                    "messages": messages,
                    "contradictions": contradictions,
                    "missing_data": missing_data,
                }
            messages.append("LLM parsing unavailable, using heuristic fallback")

        # --- Heuristic fallback ---------------------------------------
        return self._parse_with_heuristics(raw_query, profile, messages, contradictions, missing_data)

    def _parse_with_llm(self, raw_query: str) -> Optional[Dict[str, Any]]:
        client = self.llm
        if client is None:
            return None
        try:
            return client.generate_json(
                build_intake_prompt(raw_query), system=INTAKE_SYSTEM
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM intake failed: %s", e)
            return None

    def _apply_llm_result(
        self,
        profile: CandidateProfile,
        parsed: Dict[str, Any],
        messages: List[str],
        contradictions: List[str],
        missing_data: List[str],
    ) -> None:
        if parsed.get("profession"):
            profile.profession = str(parsed["profession"])
        if isinstance(parsed.get("locations"), list) and parsed["locations"]:
            profile.locations = [str(x) for x in parsed["locations"]]
        if isinstance(parsed.get("work_formats"), list) and parsed["work_formats"]:
            fmts = []
            for f in parsed["work_formats"]:
                s = str(f).lower()
                if s in ("remote", "удалённо", "удаленно"):
                    fmts.append(WorkFormat.REMOTE)
                elif s in ("hybrid", "гибрид"):
                    fmts.append(WorkFormat.HYBRID)
                elif s in ("office", "офис"):
                    fmts.append(WorkFormat.OFFICE)
            if fmts:
                profile.work_formats = fmts
        if parsed.get("min_salary_rub_month") is not None:
            try:
                profile.min_salary_rub_month = float(parsed["min_salary_rub_month"])
            except (TypeError, ValueError):
                pass
        if parsed.get("require_dms") is not None:
            profile.require_dms = bool(parsed["require_dms"])
        if isinstance(parsed.get("contradictions"), list):
            contradictions.extend(str(x) for x in parsed["contradictions"])
        if isinstance(parsed.get("missing_data"), list):
            missing_data.extend(str(x) for x in parsed["missing_data"])

        profile.contradictions = contradictions
        profile.missing_data = missing_data
        messages.append(
            f"Профиль разобран LLM: {profile.profession}, {', '.join(profile.locations)}"
        )

    def _parse_with_heuristics(
        self,
        raw_query: str,
        profile: CandidateProfile,
        messages: List[str],
        contradictions: List[str],
        missing_data: List[str],
    ) -> Dict[str, Any]:
        query_lower = raw_query.lower()

        # Extract profession (default: Go-разработчик)
        profession = profile.profession
        if "go" in query_lower or "golang" in query_lower:
            profession = "Go-разработчик"
        elif "python" in query_lower and "go" not in query_lower:
            profession = "Python-разработчик"

        # Extract location hints
        locations = list(profile.locations)
        if "москв" in query_lower:
            if "Санкт-Петербург" in locations and "Москва" not in locations:
                contradictions.append(
                    "Запрос содержит 'Москва', но профиль кандидата указывает 'Санкт-Петербург'"
                )
            locations.append("Москва")
        if "удаленно" in query_lower or "remote" in query_lower:
            if "Удалённая работа" not in locations:
                locations.append("Удалённая работа")

        # Extract salary hints
        min_salary = profile.min_salary_rub_month
        salary_match = __import__("re").search(r"(\d+)\s*(тыс\.?)?\s*(руб\.?)?", raw_query)
        if salary_match:
            suggested = float(salary_match.group(1))
            if salary_match.group(2) == "тыс.":
                suggested *= 1000
            if suggested > min_salary:
                min_salary = suggested
                messages.append(f"Из запроса извлечена зарплата: {int(suggested)} руб/мес")

        # Build updated profile
        profile.profession = profession
        profile.locations = locations
        profile.min_salary_rub_month = min_salary
        profile.contradictions = contradictions
        profile.missing_data = missing_data

        messages.append(f"Профиль нормализован: {profession}, {', '.join(locations)}")
        return {
            "profile": profile,
            "messages": messages,
            "contradictions": contradictions,
            "missing_data": missing_data,
        }


@dataclass
class VacancyDiscoveryAgent(AgentBase):
    """Discovers vacancies from configured sources.

    Supports:
    - hh.ru public scraping (curl_cffi TLS fingerprint)
    - Fixture files for testing
    - Placeholder for future API integrations
    """

    name: str = "Vacancy Discovery Agent"

    def run(
        self,
        query: SearchQuery,
        source: str = "test",
        hh_adapter: Any = None,
        fixture_path: str | Path | None = None,
    ) -> Dict[str, Any]:
        """Discover vacancies from the specified source.

        Args:
            query: SearchQuery with text, areas, formats, etc.
            source: Source name ('hh', 'fixture', 'test').
            hh_adapter: Optional HHAdapter instance for hh.ru scraping.
            fixture_path: Optional path to fixture JSON file.

        Returns:
            Dict with 'vacancies' (list[Vacancy]), 'source' (str),
            'limitations' (list[str]).
        """
        vacancies: List[Vacancy] = []
        limitations: List[str] = []

        if source == "hh" and hh_adapter is not None:
            # Scrape from hh.ru
            try:
                vacancies = hh_adapter.scrape(
                    text=query.text,
                    area_id="2",  # Default: Saint Petersburg
                    max_pages=query.max_pages,
                    per_page=query.page_size,
                    enrich=True,
                    enrich_limit=30,
                )
                limitations.append("hh.ru public scraping may miss some vacancies behind login")
                limitations.append("Rate limits apply: ~8-10 seconds between requests")
            except Exception as e:
                limitations.append(f"hh.ru scraping failed: {e}")
                limitations.append("Switching to fixture-based mode")

        elif source == "fixture" and fixture_path is not None:
            # Load from fixture file
            if hh_adapter is not None:
                vacancies = hh_adapter.from_fixture(Path(fixture_path))
            limitations.append("Fixture-based mode: results are static test data")

        else:
            # Test mode: return empty list (integrator should provide fixtures)
            limitations.append("No real data source configured; returning empty list")
            limitations.append("Use source='hh' with hh_adapter for live scraping")
            limitations.append("Use source='fixture' with fixture_path for test data")

        return {
            "vacancies": vacancies,
            "source": source,
            "limitations": limitations,
        }
