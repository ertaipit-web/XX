from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .enums import Currency, DmsStatus, TaxType, VacancyStatus, WorkFormat
from .models import Vacancy, VacancyScore


class VacancyNormalizer:
    @staticmethod
    def normalize_work_format(schedule: str | None, remote_flag: bool | None = None) -> WorkFormat:
        if not schedule:
            return WorkFormat.UNKNOWN
        s = str(schedule).lower()
        if "удал" in s or "remote" in s:
            return WorkFormat.REMOTE
        if "гибр" in s or "hybrid" in s:
            return WorkFormat.HYBRID
        if "офис" in s or "office" in s:
            return WorkFormat.OFFICE
        return WorkFormat.UNKNOWN

    @staticmethod
    def normalize_currency(cur: str | None) -> Currency:
        if not cur:
            return Currency.UNKNOWN
        c = str(cur).upper()
        if c in ("RUB", "RUR"):
            return Currency.RUB
        if c == "USD":
            return Currency.USD
        if c == "EUR":
            return Currency.EUR
        return Currency.UNKNOWN

    @staticmethod
    def normalize_tax(tax: str | None) -> TaxType:
        if not tax:
            return TaxType.UNKNOWN
        t = str(tax).lower()
        if "net" in t:
            return TaxType.NET
        if "gross" in t:
            return TaxType.GROSS
        return TaxType.UNKNOWN


class ScoringCalculator:
    @staticmethod
    def calculate_score(
        vacancy: Vacancy,
        weights: Dict[str, float] | None = None,
        min_salary_rub: float = 119000,
    ) -> VacancyScore:
        """Calculate vacancy score from weighted criteria.

        Args:
            vacancy: The vacancy to score.
            weights: Optional weight overrides (keys: salary_fit, format_fit, etc.)
            min_salary_rub: Minimum salary threshold in RUB/month.

        Returns:
            VacancyScore with individual component scores and total.
        """
        w = weights or {
            "salary_fit": 0.25,
            "format_fit": 0.25,
            "dms_fit": 0.15,
            "technical_interest": 0.25,
            "career_potential": 0.10,
        }

        salary_score = ScoringCalculator._score_salary(vacancy, min_salary_rub)
        format_score = ScoringCalculator._score_format(vacancy)
        dms_score = ScoringCalculator._score_dms(vacancy)
        technical_score = ScoringCalculator._score_technical(vacancy)
        career_score = ScoringCalculator._score_career(vacancy)

        total = int(
            salary_score * w.get("salary_fit", 0.25)
            + format_score * w.get("format_fit", 0.25)
            + dms_score * w.get("dms_fit", 0.15)
            + technical_score * w.get("technical_interest", 0.25)
            + career_score * w.get("career_potential", 0.10)
        )

        explanation: List[str] = []
        if salary_score < 50:
            explanation.append("Низкое соответствие зарплатному ожиданию")
        if format_score < 50:
            explanation.append("Формат работы не соответствует предпочтениям")
        if dms_score < 50:
            explanation.append("ДМС не подтверждён или не указан")
        if technical_score < 50:
            explanation.append("Технические задачи могут быть рутинными")

        return VacancyScore(
            salary_fit=salary_score,
            format_fit=format_score,
            dms_fit=dms_score,
            technical_interest=technical_score,
            career_potential=career_score,
            total=total,
            weights=w,
            explanation=explanation,
        )

    @staticmethod
    def _score_salary(vacancy: Vacancy, min_salary: float) -> int:
        """Score salary match (0-100)."""
        salary = vacancy.salary
        if salary.from_amount is None and salary.to_amount is None:
            return 30  # Unknown — medium score, don't penalize too much

        from_amount = salary.from_amount or 0
        # Convert to RUB if needed (simple approximation)
        if salary.currency == Currency.USD:
            from_amount *= 90  # Rough exchange rate
        elif salary.currency == Currency.EUR:
            from_amount *= 100

        if from_amount >= min_salary * 1.5:
            return 100
        elif from_amount >= min_salary:
            return 75
        elif from_amount >= min_salary * 0.8:
            return 50
        else:
            return 20

    @staticmethod
    def _score_format(vacancy: Vacancy) -> int:
        """Score work format match (0-100)."""
        fmt = vacancy.work_format
        if fmt == WorkFormat.REMOTE:
            return 100
        elif fmt == WorkFormat.HYBRID:
            return 80
        elif fmt == WorkFormat.OFFICE:
            return 30
        else:
            return 50  # Unknown

    @staticmethod
    def _score_dms(vacancy: Vacancy) -> int:
        """Score DMS status (0-100)."""
        dms = vacancy.benefits.dms_status
        if dms == DmsStatus.CONFIRMED:
            return 100
        elif dms == DmsStatus.NOT_MENTIONED:
            return 40
        else:
            return 50  # Unknown — don't penalize

    @staticmethod
    def _score_technical(vacancy: Vacancy) -> int:
        """Score technical interest (0-100)."""
        if vacancy.technical_analysis:
            return vacancy.technical_analysis.task_interest_score or 50
        # Fallback: check description for tech signals
        desc = (vacancy.description or "").lower()
        signals = [
            "golang", "go", "concurrency", "goroutine", "grpc", "microservice",
            "kubernetes", "docker", "kafka", "redis", "postgresql",
            "distributed", "api", "rest", "gRPC",
        ]
        matches = sum(1 for s in signals if s in desc)
        return min(100, 30 + matches * 10)

    @staticmethod
    def _score_career(vacancy: Vacancy) -> int:
        """Score career potential (0-100)."""
        if vacancy.career_fit:
            return vacancy.career_fit.fit_score or 50
        # Fallback: seniority hints in title
        title = (vacancy.title or "").lower()
        if any(s in title for s in ["lead", "senior", "lead", "руковод", "staff"]):
            return 80
        elif any(s in title for s in ["middle", "мидл", "разработчик"]):
            return 60
        elif any(s in title for s in ["junior", "стаж", "trainee"]):
            return 40
        return 50
