from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

from ..core.enums import WorkFormat
from ..core.models import CandidateProfile, SearchQuery, Vacancy


@dataclass
class AgentBase:
    name: str

    def run(self, **kwargs: Any) -> Any:
        raise NotImplementedError


@dataclass
class CareerIntakeAgent(AgentBase):
    name: str = "Career Intake Agent"

    def run(self, raw_query: str | None = None, profile: CandidateProfile | None = None) -> Dict[str, Any]:
        if profile is None:
            profile = CandidateProfile()
        return {"profile": profile, "messages": ["Профиль нормализован"]}


@dataclass
class VacancyDiscoveryAgent(AgentBase):
    name: str = "Vacancy Discovery Agent"

    def run(self, query: SearchQuery, source: str = "test") -> Dict[str, Any]:
        vacancies: List[Vacancy] = []
        return {"vacancies": vacancies, "source": source}
