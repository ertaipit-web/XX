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
        if "net" in t or "на руки" in t:
            return TaxType.NET
        if "gross" in t or "до вычета" in t:
            return TaxType.GROSS
        return TaxType.UNKNOWN

    @staticmethod
    def normalize_period(period: str | None) -> str:
        """Normalize salary period to standard format."""
        if not period:
            return "month"
        p = str(period).lower()
        if any(k in p for k in ("month", "месяц", "мес")):
            return "month"
        if any(k in p for k in ("year", "год", "годов")):
            return "year"
        if any(k in p for k in ("hour", "час", "час.")):
            return "hour"
        return "month"

    @staticmethod
    def convert_to_monthly_net(
        amount: float,
        currency: Currency,
        tax_type: TaxType,
        period: str,
    ) -> Optional[float]:
        """Convert salary to monthly net RUB equivalent.

        Returns None if conversion is not possible (unknown currency/tax/period).
        """
        # Period conversion
        monthly = amount
        if period == "year":
            monthly = amount / 12
        elif period == "hour":
            # Assume 160 hours/month
            monthly = amount * 160
        elif period != "month":
            return None

        # Currency conversion - NO hardcoded rates, require explicit rate
        if currency == Currency.RUB:
            rub = monthly
        elif currency in (Currency.USD, Currency.EUR):
            # No hardcoded rates - cannot convert without explicit rate
            return None
        else:
            return None

        # Tax type conversion - NO gross->net without explicit model
        if tax_type == TaxType.NET:
            return rub
        elif tax_type == TaxType.GROSS:
            # Cannot convert gross to net without documented tax model
            return None
        else:
            # Unknown tax basis - cannot determine net
            return None


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
            min_salary_rub: Minimum salary threshold in RUB/month net.

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
        """Score salary match (0-100).

        Logic per problem-definition:
        - Threshold is 119000 RUB/month NET
        - If confirmed max < threshold -> NOT_SUITABLE (score 0)
        - If confirmed min >= threshold -> PASS (score 100)
        - If range crosses threshold or only max known -> NEEDS_CLARIFICATION (score 50)
        - Unknown salary -> NEEDS_CLARIFICATION (score 30)
        - Gross/unknown tax basis cannot auto-pass net threshold
        """
        salary = vacancy.salary
        if salary.from_amount is None and salary.to_amount is None:
            return 30  # Unknown — medium score, don't penalize too much

        # Convert both bounds to monthly net RUB if possible
        min_net = None
        max_net = None

        if salary.from_amount is not None:
            min_net = VacancyNormalizer.convert_to_monthly_net(
                salary.from_amount, salary.currency, salary.tax_type, salary.period
            )
        if salary.to_amount is not None:
            max_net = VacancyNormalizer.convert_to_monthly_net(
                salary.to_amount, salary.currency, salary.tax_type, salary.period
            )

        # If we couldn't convert to net RUB (unknown currency/tax/period)
        if min_net is None and max_net is None:
            return 50  # Needs clarification - can't determine

        # Use available bounds
        lower = min_net if min_net is not None else max_net
        upper = max_net if max_net is not None else min_net

        # If confirmed maximum is below threshold -> NOT_SUITABLE
        if upper is not None and upper < min_salary:
            return 0

        # If confirmed minimum meets threshold -> PASS
        if lower is not None and lower >= min_salary:
            return 100

        # Range crosses threshold or only upper bound known above threshold
        return 50  # Needs clarification

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

    @staticmethod
    def _check_mandatory_salary(vacancy: Vacancy, min_salary: float) -> Optional[bool]:
        """Check if vacancy meets mandatory salary requirement.
        
        Returns:
            True  - confirmed salary >= min_salary net RUB/month
            False - confirmed salary < min_salary (proven violation)
            None  - unknown/unconfirmable (lack of data)
        """
        salary = vacancy.salary
        if salary.from_amount is None and salary.to_amount is None:
            return None  # Unknown - lack of data
        
        # For RUB currency, if amount is below threshold, we can prove violation
        # regardless of tax_type (gross > net, so gross < threshold implies net < threshold)
        if salary.currency == Currency.RUB:
            lower_bound = salary.from_amount if salary.from_amount is not None else salary.to_amount
            if lower_bound is not None and lower_bound < min_salary:
                return False  # Proven violation: even gross is below threshold
        
        min_net = None
        max_net = None
        
        if salary.from_amount is not None:
            min_net = VacancyNormalizer.convert_to_monthly_net(
                salary.from_amount, salary.currency, salary.tax_type, salary.period
            )
        if salary.to_amount is not None:
            max_net = VacancyNormalizer.convert_to_monthly_net(
                salary.to_amount, salary.currency, salary.tax_type, salary.period
            )
        
        # If we couldn't convert to net RUB
        if min_net is None and max_net is None:
            return None  # Cannot confirm - lack of data
        
        upper = max_net if max_net is not None else min_net
        
        # If confirmed maximum is below threshold -> PROVEN VIOLATION
        if upper is not None and upper < min_salary:
            return False
        
        # If confirmed minimum meets threshold -> CONFIRMED PASS
        lower = min_net if min_net is not None else max_net
        if lower is not None and lower >= min_salary:
            return True
        
        # Range crosses threshold or only upper bound known above threshold
        return None  # Cannot confirm pass or fail - lack of data

    @staticmethod
    def _check_mandatory_format(vacancy: Vacancy) -> Optional[bool]:
        """Check if vacancy meets mandatory format requirement.
        
        Returns:
            True  - confirmed remote or hybrid in SPb
            False - confirmed office or hybrid outside SPb (proven violation)
            None  - unknown format or location (lack of data)
        """
        fmt = vacancy.work_format
        if fmt == WorkFormat.REMOTE:
            return True
        if fmt == WorkFormat.HYBRID:
            # For hybrid, need to check location is SPb
            if vacancy.location:
                loc = vacancy.location.lower()
                if "санкт" in loc or "spb" in loc or "питер" in loc:
                    return True
                # Hybrid but location not SPb - proven violation
                return False
            # Hybrid but no location - lack of data
            return None
        if fmt == WorkFormat.OFFICE:
            return False  # Proven violation
        return None  # UNKNOWN - lack of data