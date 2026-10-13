from __future__ import annotations

from typing import Any, Dict, List

from ..core.enums import DmsStatus, VacancyStatus, WorkFormat, DataCompleteness
from ..core.models import (
    BenefitsInfo,
    CareerFitAnalysis,
    SalaryInfo,
    SourceEvidence,
    TechnicalAnalysis,
    Vacancy,
    VacancyScore,
)
from ..core.scoring import ScoringCalculator


class VacancyVerificationAgent:
    name: str = "Vacancy Verification Agent"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        for v in vacancies:
            if v.checked_at is None:
                from datetime import datetime

                v.checked_at = datetime.now()
            if not v.source_url:
                v.status = VacancyStatus.CHECK_FAILED
                v.non_compliance_reasons.append("Отсутствует проверяемый источник")
            else:
                v.confirmed_facts.append("Есть ссылка на первоисточник")
            v.data_completeness = DataCompleteness.PARTIAL
        return {"vacancies": vacancies, "success": True}


class GoTechnicalAnalyst:
    name: str = "Go Technical Analyst"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        for v in vacancies:
            v.technical_analysis = TechnicalAnalysis(
                technologies=["Go"] if "go" in (v.title or "").lower() or "go" in (v.description or "") else [],
                task_interest_score=60,
                has_confirmed_tech=True,
            )
        return {"vacancies": vacancies, "success": True}


class CompensationBenefitsAgent:
    name: str = "Compensation & Benefits Agent"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        for v in vacancies:
            if v.benefits.dms_status == DmsStatus.UNKNOWN:
                v.benefits.dms_status = DmsStatus.NOT_MENTIONED
            if v.salary.from_amount and v.salary.from_amount < 119000:
                v.non_compliance_reasons.append("Зарплата ниже минимального порога 119000 руб/мес")
        return {"vacancies": vacancies, "success": True}


class CareerFitAnalyst:
    name: str = "Career Fit Analyst"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        for v in vacancies:
            v.career_fit = CareerFitAnalysis(
                fit_score=70,
                strong_points=["Соответствует базовым критериям"],
                questions_for_interview=["Есть ли подтверждение ДМС?", "Удалёнка/гибрид подтверждены ли?"],
            )
        return {"vacancies": vacancies, "success": True}


class DeduplicationRankingAgent:
    name: str = "Deduplication & Ranking Agent"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        seen = set()
        unique = []
        for v in vacancies:
            key = v.source_url or v.id
            if key not in seen:
                seen.add(key)
                unique.append(v)
        for v in unique:
            v.score = ScoringCalculator.calculate_score(v)
            if any("ниже минимального" in r for r in v.non_compliance_reasons):
                v.status = VacancyStatus.NOT_SUITABLE
            elif v.benefits.dms_status == DmsStatus.CONFIRMED:
                v.status = VacancyStatus.SUITABLE
            else:
                v.status = VacancyStatus.NEEDS_CLARIFICATION
        return {"vacancies": unique, "success": True}


class QualityAssuranceAgent:
    name: str = "Quality Assurance Agent"

    def run(self, vacancies: List[Vacancy], report: Any = None) -> Dict[str, Any]:
        for v in vacancies:
            if not v.source_url:
                v.status = VacancyStatus.CHECK_FAILED
        return {"vacancies": vacancies, "success": True}
