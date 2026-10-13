from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import Vacancy, VacancyScore


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    messages: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    processed_count: int = 0


@dataclass
class ResearchRun:
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    profile: Optional[Any] = None
    vacancies_found: int = 0
    vacancies_checked: int = 0
    vacancies_unique: int = 0
    vacancies_suitable: int = 0
    vacancies_needs_clarification: int = 0
    errors: List[str] = field(default_factory=list)
    agent_results: List[AgentResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VacancyReport:
    run: ResearchRun
    vacancies: List[Vacancy] = field(default_factory=list)
    best_vacancies: List[Vacancy] = field(default_factory=list)
    needs_clarification: List[Vacancy] = field(default_factory=list)
    not_suitable: List[Vacancy] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    candidate_improvements: List[str] = field(default_factory=list)
    to_recheck: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
