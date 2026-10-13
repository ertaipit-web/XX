from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.enums import WorkFormat
from ..core.models import CandidateProfile, SearchQuery, Vacancy


@dataclass
class AgentBase:
    name: str

    def run(self, **kwargs: Any) -> Any:
        raise NotImplementedError


@dataclass
class CareerIntakeAgent(AgentBase):
    """Parses a raw text query and extracts candidate profile criteria.

    Extracts: profession, location hints, salary expectations, work format preferences.
    Returns validated profile with any contradictions or missing data flagged.
    """

    name: str = "Career Intake Agent"

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
