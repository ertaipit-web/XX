from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from ..core.contracts import AgentResult, ResearchRun, VacancyReport
from ..core.models import CandidateProfile, SearchQuery, Vacancy
from ..go_agents.agents import (
    AgentBase,
    CareerIntakeAgent,
    VacancyDiscoveryAgent,
)


class VacancyResearchOrchestrator:
    def __init__(self) -> None:
        self.intake = CareerIntakeAgent()
        self.discovery = VacancyDiscoveryAgent()

    def run(
        self,
        raw_query: str | None = None,
        profile: CandidateProfile | None = None,
        fixtures: List[Vacancy] | None = None,
        output_dir: Path = Path("reports"),
    ) -> VacancyReport:
        run_id = str(uuid.uuid4())[:8]
        run = ResearchRun(run_id=run_id, started_at=datetime.now(), profile=profile)

        intake_res = self.intake.run(raw_query=raw_query, profile=profile)
        profile = intake_res.get("profile") or CandidateProfile()

        if fixtures is not None:
            vacancies = list(fixtures)
            run.vacancies_found = len(vacancies)
            run.vacancies_checked = len(vacancies)
            run.vacancies_unique = len(vacancies)
            run.vacancies_suitable = sum(1 for v in vacancies if getattr(v, "status").value == "suitable")
            run.vacancies_needs_clarification = len(vacancies) - run.vacancies_suitable
        else:
            disc = self.discovery.run(query=SearchQuery(text=raw_query or "go"))
            vacancies = disc.get("vacancies", [])

        run.finished_at = datetime.now()
        report = VacancyReport(run=run, vacancies=vacancies)
        report.summary = {
            "run_id": run.run_id,
            "vacancies": len(vacancies),
        }
        return report
