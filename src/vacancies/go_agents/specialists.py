from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..core.enums import Currency, DmsStatus, VacancyStatus, WorkFormat, DataCompleteness
from ..core.models import (
    BenefitsInfo,
    CareerFitAnalysis,
    SalaryInfo,
    SourceEvidence,
    TechnicalAnalysis,
    Vacancy,
    VacancyScore,
)
from ..core.scoring import ScoringCalculator, VacancyNormalizer
from ..llm.client import BaseLLMClient
from ..llm.prompts import (
    CAREER_FIT_SYSTEM,
    TECHNICAL_SYSTEM,
    build_career_fit_prompt,
    build_technical_prompt,
)

logger = logging.getLogger(__name__)


class VacancyVerificationAgent:
    name = "VacancyVerificationAgent"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        """Verify vacancies: check URLs, extract facts, mark data completeness."""
        for v in vacancies:
            v.checked_at = v.checked_at or datetime.now(timezone.utc)

            if not v.source_url:
                v.status = VacancyStatus.CHECK_FAILED
                v.non_compliance_reasons.append("Отсутствует проверяемый источник")
            else:
                v.confirmed_facts.append("Есть ссылка на первоисточник")
                v.evidence.append(SourceEvidence(
                    source_url=v.source_url,
                    field_name="source_url",
                    extracted_at=datetime.now(timezone.utc),
                ))

            # Determine data completeness
            has_salary = v.salary.from_amount is not None or v.salary.to_amount is not None
            has_desc = bool(v.description)
            has_location = bool(v.location)
            has_format = v.work_format != WorkFormat.UNKNOWN

            if has_salary and has_desc and has_location and has_format:
                v.data_completeness = DataCompleteness.FULL
            elif has_salary and has_desc:
                v.data_completeness = DataCompleteness.PARTIAL
            elif has_salary or has_desc:
                v.data_completeness = DataCompleteness.MINIMAL
            else:
                v.data_completeness = DataCompleteness.MINIMAL

        return {"vacancies": vacancies, "success": True}


class GoTechnicalAnalyst:
    name = "GoTechnicalAnalyst"
    def __init__(self, llm=None) -> None:
        self.llm = llm
    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        if self.llm is not None:
            llm_ok = 0
            for v in vacancies:
                if self._analyze_with_llm(v):
                    llm_ok += 1
            if llm_ok:
                return {"vacancies": vacancies, "success": True, "llm_analyzed": llm_ok}
            logger.warning("LLM technical analysis produced no results; using heuristics")
        return self._run_heuristics(vacancies)
    def _analyze_with_llm(self, v: Vacancy) -> bool:
        client = self.llm
        if client is None:
            return False
        try:
            parsed = client.generate_json(
                build_technical_prompt(v.title, v.description or "", v.requirements),
                system=TECHNICAL_SYSTEM,
            )
        except Exception as e:
            logger.warning("LLM technical analysis failed for %s: %s", v.id, e)
            return False
        if not parsed:
            return False
        def _clamp(val, default):
            try:
                return max(0, min(100, int(val)))
            except (TypeError, ValueError):
                return default
        v.technical_analysis = TechnicalAnalysis(
            technologies=[str(x) for x in parsed.get("technologies", []) if x],
            go_relevance_score=_clamp(parsed.get("go_relevance_score"), 50),
            task_interest_score=_clamp(parsed.get("task_interest_score"), 50),
            backend_signals=[str(x) for x in parsed.get("positives", []) if x],
            concerns=[str(x) for x in parsed.get("concerns", []) if x],
            positives=[str(x) for x in parsed.get("positives", []) if x],
            has_confirmed_tech=bool(parsed.get("technologies")),
        )
        return True
    def _run_heuristics(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        go_signals = ["golang", "go", "goroutine", "gopher", "std", "stdlib", "gofmt", "golangci"]
        backend_signals = ["api", "rest", "grpc", "microservice", "kubernetes", "k8s", "docker", "kafka", "rabbitmq", "redis", "postgresql", "mysql", "cassandra", "distributed", "concurrent", "performance", "scalab", "load", "backend", "сервис", "микросервис", "конкурент"]
        routine_signals = ["html", "frontend", "css", "javascript", "react", "vue", "wordpress"]
        for v in vacancies:
            desc = (v.description or "").lower()
            title = (v.title or "").lower()
            combined = desc + " " + title
            go_count = sum(1 for s in go_signals if s in combined)
            go_relevance = min(100, go_count * 20 + 20)
            backend_count = sum(1 for s in backend_signals if s in combined)
            backend_signals_list = [s for s in backend_signals if s in combined]
            routine_count = sum(1 for s in routine_signals if s in combined)
            interest = min(100, 30 + backend_count * 8 - routine_count * 10)
            concerns = []
            if routine_count > 2:
                concerns.append("Много фронтенд/рутинных задач (HTML, CSS, JS)")
            if go_count == 0:
                concerns.append("Go не упоминается в описании")
            positives = []
            if backend_count >= 3:
                positives.append("Сильный backend-стек: " + ", ".join(backend_signals_list[:5]))
            if go_count >= 2:
                positives.append("Go активно используется в задачах")
            v.technical_analysis = TechnicalAnalysis(
                technologies=["Go"] if go_count > 0 else [],
                go_relevance_score=go_relevance,
                task_interest_score=interest,
                concurrency_signals=[s for s in backend_signals_list if any(c in s for c in ["concurrent", "load", "scalab"])],
                backend_signals=backend_signals_list,
                concerns=concerns,
                positives=positives,
                has_confirmed_tech=go_count > 0,
            )
        return {"vacancies": vacancies, "success": True}


class CompensationBenefitsAgent:
    name = "Compensation & Benefits Agent"

    def run(self, vacancies: List[Vacancy], min_salary: float = 119000) -> Dict[str, Any]:
        """Normalize and validate salary + benefits."""
        dms_patterns = [
            r"\bдмс\b",
            r"добровольн\w+\s+медицинск\w+\s+страхован",
            r"корпоративн\w+\s+медицинск",
            r"medical\s+insurance",
            r"voluntary\s+medical",
        ]

        for v in vacancies:
            # DMS detection from description
            desc = (v.description or "").lower()
            if v.benefits.dms_status == DmsStatus.UNKNOWN:
                for pattern in dms_patterns:
                    if re.search(pattern, desc):
                        v.benefits.dms_status = DmsStatus.CONFIRMED
                        v.benefits.dms_notes = "Упоминание ДМС найдено в тексте вакансии"
                        v.evidence.append(SourceEvidence(
                            source_url=v.source_url,
                            field_name="dms",
                            snippet=pattern,
                            extracted_at=datetime.now(timezone.utc),
                        ))
                        break
                else:
                    v.benefits.dms_status = DmsStatus.NOT_MENTIONED

            # Salary check - use proper conversion
            net_monthly = VacancyNormalizer.convert_to_monthly_net(
                v.salary.from_amount if v.salary.from_amount is not None else 0,
                v.salary.currency,
                v.salary.tax_type,
                v.salary.period,
            )
            if net_monthly is not None and net_monthly < min_salary:
                v.non_compliance_reasons.append(
                    f"Зарплата ({v.salary.from_amount:.0f} {v.salary.currency.value}) ниже порога {min_salary:.0f} руб/мес"
                )

        return {"vacancies": vacancies, "success": True}


class CareerFitAnalyst:
    name = "CareerFitAnalyst"
    def __init__(self, llm=None) -> None:
        self.llm = llm
    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        if self.llm is not None:
            llm_ok = 0
            for v in vacancies:
                if self._analyze_with_llm(v):
                    llm_ok += 1
            if llm_ok:
                return {"vacancies": vacancies, "success": True, "llm_analyzed": llm_ok}
            logger.warning("LLM career fit produced no results; using heuristics")
        return self._run_heuristics(vacancies)
    def _analyze_with_llm(self, v: Vacancy) -> bool:
        client = self.llm
        if client is None:
            return False
        salary = f'{v.salary.from_amount:.0f}-{v.salary.to_amount:.0f} {v.salary.currency.value}' if v.salary.from_amount is not None and v.salary.to_amount is not None else (f'от {v.salary.from_amount:.0f} {v.salary.currency.value}' if v.salary.from_amount is not None else 'не указана')
        try:
            parsed = client.generate_json(
                build_career_fit_prompt(v.title, v.description or "", v.work_format.value, salary),
                system=CAREER_FIT_SYSTEM,
            )
        except Exception as e:
            logger.warning("LLM career fit failed for %s: %s", v.id, e)
            return False
        if not parsed:
            return False
        try:
            fit_score = max(0, min(100, int(parsed.get("fit_score", 50))))
        except (TypeError, ValueError):
            fit_score = 50
        v.career_fit = CareerFitAnalysis(
            fit_score=fit_score,
            career_growth_score=fit_score,
            motivation_score=fit_score,
            strong_points=[str(x) for x in parsed.get("strong_points", []) if x],
            risks=[str(x) for x in parsed.get("risks", []) if x],
            questions_for_interview=[str(x) for x in parsed.get("questions_for_interview", []) if x],
            recommendation=str(parsed.get("recommendation") or ""),
        )
        return True
    def _run_heuristics(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        seniority_indicators = {
            "lead": 90, "руковод": 90, "staff": 85, "principal": 85,
            "senior": 80, "старший": 80, "lead": 80,
            "middle": 60, "мидл": 60, "разработчик": 55,
            "junior": 40, "стаж": 35, "trainee": 35,
            "intern": 30, "младший": 40,
        }
        for v in vacancies:
            title = (v.title or "").lower()
            desc = (v.description or "").lower()
            combined = title + " " + desc
            seniority_score = 50
            for indicator, score in seniority_indicators.items():
                if indicator in combined:
                    seniority_score = max(seniority_score, score)
            strong_points = []
            risks = []
            questions = []
            if v.work_format in (WorkFormat.REMOTE, WorkFormat.HYBRID):
                strong_points.append(f"Формат работы подходит: {v.work_format.value}")
            else:
                risks.append("Офисный формат может не соответствовать ожиданиям")
            if v.salary.from_amount is not None:
                strong_points.append(f"Зарплата указана: {v.salary.from_amount:.0f} {v.salary.currency.value}")
            else:
                risks.append("Зарплата не указана — требуется уточнение")
                questions.append("Каков диапазон зарплат для этой позиции?")
            if v.benefits.dms_status == DmsStatus.CONFIRMED:
                strong_points.append("Подтверждено ДМС")
            elif v.benefits.dms_status == DmsStatus.NOT_MENTIONED:
                questions.append("Есть ли ДМС и другие соц benefits?")
            if v.technical_analysis and v.technical_analysis.positives:
                strong_points.extend(v.technical_analysis.positives[:2])
            if v.technical_analysis and v.technical_analysis.concerns:
                risks.extend(v.technical_analysis.concerns[:2])
            questions.append("Каков стек технологий и процессы разработки?")
            v.career_fit = CareerFitAnalysis(
                fit_score=seniority_score,
                career_growth_score=min(100, seniority_score + 10),
                motivation_score=seniority_score,
                strong_points=strong_points,
                risks=risks,
                questions_for_interview=questions,
                recommendation="Рекомендуется к рассмотрению" if seniority_score >= 60 else "Требует уточнения",
            )
        return {"vacancies": vacancies, "success": True}


class DeduplicationRankingAgent:
    name = "Deduplication & Ranking Agent"
    def run(self, vacancies: List[Vacancy], weights=None, min_salary: float = 119000) -> Dict[str, Any]:
        for v in vacancies:
            v.score = ScoringCalculator.calculate_score(v, weights, min_salary)
            # If salary is in RUB and below threshold, treat as not suitable
            if v.salary.from_amount is not None and v.salary.from_amount < min_salary:
                v.status = VacancyStatus.NOT_SUITABLE
                if not any("ниже порога" in r for r in v.non_compliance_reasons):
                    v.non_compliance_reasons.append(f'Зарплата ({v.salary.from_amount:.0f} руб) ниже порога {min_salary:.0f} руб/мес')
            elif any("ниже порога" in r for r in v.non_compliance_reasons):
                v.status = VacancyStatus.NOT_SUITABLE
            elif v.score.total >= 60:
                v.status = VacancyStatus.SUITABLE
            else:
                v.status = VacancyStatus.NEEDS_CLARIFICATION
        return {"vacancies": vacancies, "success": True}


class QualityAssuranceAgent:
    name = "Quality Assurance Agent"
    def run(self, vacancies: List[Vacancy], report: Any = None) -> Dict[str, Any]:
        """QA check: verify data integrity and report consistency."""
        issues: List[str] = []

        for v in vacancies:
            if not v.source_url:
                issues.append(f"Вакансия '{v.title}' не имеет source_url")
                v.status = VacancyStatus.CHECK_FAILED

            if v.salary.from_amount is not None and v.salary.currency == Currency.UNKNOWN:
                issues.append(f"Вакансия '{v.title}' имеет зарплату с неизвестной валютой")

            if v.work_format == WorkFormat.UNKNOWN and v.location:
                issues.append(f"Вакансия '{v.title}' имеет локацию, но неизвестный формат работы")

        # Check report structure if provided
        if report is not None:
            if not report.vacancies:
                issues.append("Отчёт содержит 0 вакансий")

        return {
            "vacancies": vacancies,
            "success": len(issues) == 0,
            "issues": issues,
        }