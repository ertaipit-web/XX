from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

from ..core.enums import Currency, DmsStatus, TaxType, VacancyStatus, WorkFormat
from ..core.models import Vacancy, VacancyScore
from ..core.contracts import ResearchRun, VacancyReport


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
    def calculate_score(vacancy: Vacancy, weights: Dict[str, float] | None = None) -> VacancyScore:
        w = weights or {
            "salary_fit": 0.25,
            "format_fit": 0.25,
            "dms_fit": 0.15,
            "technical_interest": 0.25,
            "career_potential": 0.10,
        }
        total = (
            vacancy.score.salary_fit * w["salary_fit"]
            + vacancy.score.format_fit * w["format_fit"]
            + vacancy.score.dms_fit * w["dms_fit"]
            + vacancy.score.technical_interest * w["technical_interest"]
            + vacancy.score.career_potential * w["career_potential"]
        )
        vacancy.score.total = int(round(total))
        vacancy.score.weights = w
        return vacancy.score
