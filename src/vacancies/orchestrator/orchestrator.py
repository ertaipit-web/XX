from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
from ..reporting.writers import ReportWriterAgent, VacancyReportWriter
from ..llm.client import BaseLLMClient, build_llm_client
from ..utils.config import ConfigLoader
from ..utils.sanitize import sanitize_untrusted_text
from ..adapters.multi_source import MultiSourceAdapter
from ..adapters.hh_adapter import HHAdapter
from ..adapters.habr_adapter import HabrAdapter
from ..adapters.base import SourceAdapter
from ..storage.history import RunHistory, NewVacancyDetector

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorLimits:
    """Safety limits for a single research run."""

    max_vacancies: int = 200
    max_retries: int = 2
    retry_delay_seconds: float = 1.0
    agent_timeout_seconds: float = 60.0
    max_qa_iterations: int = 2
    enable_parallel_analysis: bool = True


class VacancyResearchOrchestrator:
    """Coordinates the full multi-agent vacancy research pipeline.

    Stages:
        1. Intake      — parse query into CandidateProfile
        2. Discovery   — collect vacancies from sources
        3. Sanitize    — neutralize untrusted external text
        4. Verify      — check sources, extract facts
        5. Analysis    — technical + compensation + career fit (parallel)
        6. Dedup/Rank  — deduplicate and score
        7. Report      — write Markdown + JSON
        8. QA          — validate report, limited fix loop
    """

    def __init__(
        self,
        limits: OrchestratorLimits | None = None,
        config_loader: ConfigLoader | None = None,
        llm: BaseLLMClient | None = None,
        disable_llm: bool = False,
        sources: List[SourceAdapter] | None = None,
    ) -> None:
        self.limits = limits or OrchestratorLimits()
        self.config = config_loader or ConfigLoader()

        # Build the LLM client from config unless one was injected or disabled.
        if disable_llm:
            self.llm: BaseLLMClient | None = None
        elif llm is not None:
            self.llm = llm
        else:
            llm_config = self.config.load_llm_config()
            self.llm = build_llm_client(llm_config) if llm_config.enabled else None

        # Initialize source adapters
        self.sources = sources or []
        if not self.sources:
            # Default: hh.ru adapter (requires HH_ACCESS_TOKEN)
            self.sources.append(HHAdapter())
            # Habr mock adapter (always available for testing)
            self.sources.append(HabrAdapter())

        self.multi_adapter = MultiSourceAdapter(self.sources)

        self.intake = CareerIntakeAgent(llm=self.llm)
        self.discovery = VacancyDiscoveryAgent()
        self.verifier = VacancyVerificationAgent()
        self.tech = GoTechnicalAnalyst(llm=self.llm)
        self.comp = CompensationBenefitsAgent()
        self.fit = CareerFitAnalyst(llm=self.llm)
        self.dedup = DeduplicationRankingAgent()
        self.qa = QualityAssuranceAgent()
        self.report_writer = ReportWriterAgent(llm=self.llm)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_with_retry(
        self,
        name: str,
        fn: Callable[[], Any],
        run: ResearchRun,
        critical: bool = False,
    ) -> Any:
        """Run an agent callable with a bounded retry loop."""
        attempts = self.limits.max_retries + 1
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                result = fn()
                run.agent_results.append(
                    AgentResult(agent_name=name, success=True, messages=[f"attempt {attempt}"])
                )
                return result
            except Exception as e:  # noqa: BLE001 — record and retry any agent error
                last_error = e
                logger.warning("Agent %s failed (attempt %d/%d): %s", name, attempt, attempts, e)
                if attempt < attempts:
                    time.sleep(self.limits.retry_delay_seconds)

        run.agent_results.append(
            AgentResult(agent_name=name, success=False, errors=[str(last_error)])
        )
        run.errors.append(f"{name}: {last_error}")
        if critical:
            raise last_error  # type: ignore[misc]
        return None

    def _sanitize_vacancies(self, vacancies: List[Vacancy]) -> int:
        """Sanitize untrusted free-text fields. Returns count of flagged vacancies."""
        flagged = 0
        for v in vacancies:
            if v.description:
                report = sanitize_untrusted_text(v.description)
                if report.detected:
                    flagged += 1
                    v.confirmed_facts.append(
                        "⚠️ Обнаружены признаки prompt injection в описании (текст помечен как недоверенный)"
                    )
                v.description = report.sanitized
            if v.requirements:
                v.requirements = sanitize_untrusted_text(v.requirements).sanitized
            if v.responsibilities:
                v.responsibilities = sanitize_untrusted_text(v.responsibilities).sanitized
        return flagged

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        raw_query: str | None = None,
        profile: CandidateProfile | None = None,
        fixtures: List[Vacancy] | None = None,
        source: str = "multi",
        fixture_path: str | Path | None = None,
        output_dir: Path = Path("reports"),
        write_reports: bool = True,
    ) -> VacancyReport:
        """Execute the full research pipeline."""
        run_id = str(uuid.uuid4())[:8]
        run = ResearchRun(run_id=run_id, started_at=datetime.now(timezone.utc))

        # --- 1. Intake -------------------------------------------------
        base_profile: CandidateProfile = profile or self.config.load_candidate_profile()

        intake_res = self._run_with_retry(
            self.intake.name,
            lambda: self.intake.run(raw_query=raw_query, profile=base_profile),
            run,
            critical=True,
        )
        active_profile: CandidateProfile = intake_res.get("profile") or base_profile
        run.profile = active_profile

        # --- 2. Discovery ---------------------------------------------
        vacancies: List[Vacancy] = []
        if fixtures is not None:
            vacancies = list(fixtures)
            run.metadata["source"] = "fixtures"
        else:
            query = SearchQuery(text=raw_query or "go разработчик", max_pages=1, page_size=20)
            disc = self._run_with_retry(
                self.discovery.name,
                lambda: self.discovery.run(
                    query=query,
                    source=source,
                    hh_adapter=HHAdapter() if source == "hh" else None,
                    multi_adapter=self.multi_adapter,
                    fixture_path=fixture_path,
                ),
                run,
            )
            if disc:
                vacancies = disc.get("vacancies", [])
                run.metadata["limitations"] = disc.get("limitations", [])
                run.metadata["source_results"] = disc.get("source_results", {})

        # Enforce max vacancy limit
        if len(vacancies) > self.limits.max_vacancies:
            logger.warning(
                "Truncating %d vacancies to limit %d", len(vacancies), self.limits.max_vacancies
            )
            vacancies = vacancies[: self.limits.max_vacancies]

        run.vacancies_found = len(vacancies)

        # --- 3. Sanitize ----------------------------------------------
        flagged = self._sanitize_vacancies(vacancies)
        if flagged:
            run.metadata["injection_flagged"] = flagged

        # --- 4. Verify -------------------------------------------------
        self._run_with_retry(self.verifier.name, lambda: self.verifier.run(vacancies), run)
        run.vacancies_checked = len(vacancies)

        # --- 5. Analysis (parallel where independent) -----------------
        weights = self.config.load_scoring_weights()
        min_salary = active_profile.min_salary_rub_month

        if self.limits.enable_parallel_analysis and len(vacancies) > 1:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [
                    pool.submit(self._safe_agent, self.tech.name, self.tech.run, vacancies),
                    pool.submit(self._safe_agent, self.comp.name, self.comp.run, vacancies, min_salary),
                    pool.submit(self._safe_agent, self.fit.name, self.fit.run, vacancies),
                ]
                for f in futures:
                    try:
                        res = f.result(timeout=self.limits.agent_timeout_seconds * max(1, len(vacancies)))
                    except Exception as e:  # noqa: BLE001 — includes TimeoutError
                        logger.warning("Parallel analysis timed out/failed: %s", e)
                        run.errors.append(f"parallel analysis: {e}")
                        continue
                    if res and not res.get("success", True):
                        run.errors.append(f"{res.get('agent', 'agent')} reported failure")
        else:
            self._run_with_retry(self.tech.name, lambda: self.tech.run(vacancies), run)
            self._run_with_retry(self.comp.name, lambda: self.comp.run(vacancies, min_salary), run)
            self._run_with_retry(self.fit.name, lambda: self.fit.run(vacancies), run)

        # --- 6. Dedup & Rank ------------------------------------------
        dedup_res = self._run_with_retry(
            self.dedup.name,
            lambda: self.dedup.run(vacancies, weights=weights, min_salary=min_salary),
            run,
            critical=True,
        )
        vacancies = dedup_res.get("vacancies", vacancies)
        run.vacancies_unique = len(vacancies)

        # --- 7. Report -------------------------------------------------
        run.finished_at = datetime.now(timezone.utc)
        report = VacancyReport(run=run, vacancies=vacancies)
        self._populate_report(report, vacancies, active_profile)

        # --- 7b. LLM report enrichment --------------------------------
        if self.llm is not None:
            enr = self._run_with_retry(
                self.report_writer.name,
                lambda: self.report_writer.enrich(report.best_vacancies),
                run,
            )
            if enr:
                run.metadata["report_llm_enriched"] = enr.get("enriched", 0)

        # --- 8. QA with limited fix loop ------------------------------
        for iteration in range(self.limits.max_qa_iterations):
            qa_res = self._run_with_retry(
                f"{self.qa.name} (iter {iteration + 1})",
                lambda: self.qa.run(vacancies, report),
                run,
            )
            if qa_res is None or qa_res.get("success", True):
                break
            issues = qa_res.get("issues", [])
            logger.warning("QA found %d issues (iter %d): %s", len(issues), iteration + 1, issues)
            run.metadata.setdefault("qa_issues", []).extend(issues)
            self.dedup.run(vacancies, weights=weights, min_salary=min_salary)

        if write_reports:
            VacancyReportWriter.write_json(report, output_dir / "latest.json")
            VacancyReportWriter.write_markdown(report, output_dir / "latest.md")
            run_dir = output_dir / "runs"
            run_dir.mkdir(parents=True, exist_ok=True)
            VacancyReportWriter.write_json(report, run_dir / f"{run_id}.json")
            VacancyReportWriter.write_markdown(report, run_dir / f"{run_id}.md")

            # --- 9. Save to history and detect new/changed vacancies ---
            history = RunHistory()
            history.save_run(report)

            detector = NewVacancyDetector(history)
            changes = detector.detect(vacancies)
            run.metadata["vacancy_changes"] = detector.format_for_report(changes)
            report.summary["new_vacancies"] = len(changes["new"])
            report.summary["changed_vacancies"] = len(changes["changed"])
            report.summary["removed_vacancies"] = len(changes["removed"])

        # Add source status to metadata
        run.metadata["source_status"] = self.multi_adapter.get_all_statuses()

        return report

    def _safe_agent(self, name: str, fn: Callable[..., Any], *args: Any) -> Dict[str, Any]:
        """Run an agent catching errors, for use inside ThreadPoolExecutor."""
        try:
            res = fn(*args)
            if isinstance(res, dict):
                res.setdefault("agent", name)
            return res
        except Exception as e:  # noqa: BLE001
            logger.warning("Parallel agent %s failed: %s", name, e)
            return {"agent": name, "success": False, "errors": [str(e)]}

    def _populate_report(
        self, report: VacancyReport, vacancies: List[Vacancy], profile: CandidateProfile
    ) -> None:
        """Fill report summary and grouped categories."""
        def _status(v: Vacancy) -> str:
            return v.status.value if hasattr(v.status, "value") else str(v.status)

        report.best_vacancies = sorted(
            [v for v in vacancies if _status(v) == "suitable"],
            key=lambda x: x.score.total,
            reverse=True,
        )
        report.needs_clarification = [v for v in vacancies if _status(v) == "needs_clarification"]
        report.not_suitable = [v for v in vacancies if _status(v) == "not_suitable"]

        run = report.run
        run.vacancies_suitable = len(report.best_vacancies)
        run.vacancies_needs_clarification = len(report.needs_clarification)

        report.summary = {
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "vacancies_found": run.vacancies_found,
            "vacancies_checked": run.vacancies_checked,
            "vacancies_unique": run.vacancies_unique,
            "suitable": run.vacancies_suitable,
            "needs_clarification": run.vacancies_needs_clarification,
            "not_suitable": len(report.not_suitable),
            "errors": run.errors,
        }

        report.next_steps = [
            "Откликнуться на вакансии из категории «Подходят» в первую очередь",
            "Уточнить по вакансиям из категории «Требует уточнения» детали зарплаты и ДМС",
            "Проверить статус вакансий при следующем запуске",
        ]
        report.candidate_improvements = [
            "Указать грейд и опыт (лет) для более точного скоринга",
            "Уточнить приоритет: зарплата vs интересные задачи",
            "Добавить предпочтения по стеку (GRPC, Kubernetes, Kafka и т.д.)",
        ]
        report.to_recheck = [v.source_url for v in report.needs_clarification if v.source_url]