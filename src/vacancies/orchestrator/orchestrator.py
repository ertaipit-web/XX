from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from ..core.contracts import AgentResult, ResearchRun, VacancyReport
from ..core.models import CandidateProfile, SearchQuery, Vacancy
from ..go_agents.agents import CareerIntakeAgent, VacancyDiscoveryAgent
from ..go_agents.specialists import (
    CareerFitAnalyst,
    CompensationBenefitsAgent,
    DeduplicationRankingAgent,
    GoTechnicalAnalyst,
    QualityAssuranceAgent,
    VacancyVerificationAgent,
)


class VacancyResearchOrchestrator:
    def __init__(self) -> None:
        self.intake = CareerIntakeAgent()
        self.discovery = VacancyDiscoveryAgent()
        self.verifier = VacancyVerificationAgent()
        self.tech = GoTechnicalAnalyst()
        self.comp = CompensationBenefitsAgent()
        self.fit = CareerFitAnalyst()
        self.dedup = DeduplicationRankingAgent()
        self.qa = QualityAssuranceAgent()

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

        vacancies: List[Vacancy] = []
        if fixtures is not None:
            vacancies = list(fixtures)
        else:
            disc = self.discovery.run(query=SearchQuery(text=raw_query or "go"))
            vacancies = disc.get("vacancies", [])

        run.vacancies_found = len(vacancies)
        self.verifier.run(vacancies)
        run.vacancies_checked = len(vacancies)
        self.tech.run(vacancies)
        self.comp.run(vacancies)
        self.fit.run(vacancies)
        self.dedup.run(vacancies)
        run.vacancies_unique = len(vacancies)
        report = VacancyReport(run=run, vacancies=vacancies)
        self.qa.run(vacancies, report)
        run.vacancies_suitable = sum(1 for v in vacancies if getattr(v.status.value, "value", v.status) == "suitable")
        run.vacancies_needs_clarification = sum(1 for v in vacancies if getattr(v.status.value, "value", v.status) == "needs_clarification")
        run.finished_at = datetime.now()
        report.summary = {
            "run_id": run.run_id,
            "vacancies": len(vacancies),
            "suitable": run.vacancies_suitable,
            "needs_clarification": run.vacancies_needs_clarification,
        }
        report.best_vacancies = [v for v in vacancies if getattr(v.status.value, "value", v.status) == "suitable"]
        report.needs_clarification = [v for v in vacancies if getattr(v.status.value, "value", v.status) == "needs_clarification"]
        report.not_suitable = [v for v in vacancies if getattr(v.status.value, "value", v.status) == "not_suitable"]
        return report
