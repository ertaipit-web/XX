from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .enums import (
    Currency,
    DataCompleteness,
    DmsStatus,
    TaxType,
    VacancyStatus,
    WorkFormat,
)


@dataclass
class SourceEvidence:
    source_url: str
    snippet: Optional[str] = None
    field_name: Optional[str] = None
    extracted_at: Optional[datetime] = None


@dataclass
class SalaryInfo:
    from_amount: Optional[float] = None
    to_amount: Optional[float] = None
    currency: Currency = Currency.UNKNOWN
    tax_type: TaxType = TaxType.UNKNOWN
    period: str = "month"
    raw_text: Optional[str] = None
    evidence: List[SourceEvidence] = field(default_factory=list)


@dataclass
class BenefitsInfo:
    dms_status: DmsStatus = DmsStatus.UNKNOWN
    dms_notes: Optional[str] = None
    other_benefits: List[str] = field(default_factory=list)
    evidence: List[SourceEvidence] = field(default_factory=list)


@dataclass
class CandidateProfile:
    profession: str = "Go-разработчик"
    locations: List[str] = field(default_factory=lambda: ["Санкт-Петербург", "Удалённая работа"])
    work_formats: List[WorkFormat] = field(default_factory=lambda: [WorkFormat.REMOTE, WorkFormat.HYBRID])
    min_salary_rub_month: float = 119000.0
    require_dms: bool = True
    language: str = "ru"
    main_currency: Currency = Currency.RUB
    search_frequency: Optional[str] = None
    additional_notes: Optional[str] = None
    contradictions: List[str] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)


@dataclass
class SearchQuery:
    text: str
    areas: List[str] = field(default_factory=list)
    work_formats: List[WorkFormat] = field(default_factory=list)
    min_salary: Optional[float] = None
    currency: Currency = Currency.RUB
    period: str = "month"
    limit: Optional[int] = None
    page_size: int = 20
    max_pages: int = 1


@dataclass
class TechnicalAnalysis:
    technologies: List[str] = field(default_factory=list)
    go_relevance_score: int = 0
    task_interest_score: int = 0
    concurrency_signals: List[str] = field(default_factory=list)
    backend_signals: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    positives: List[str] = field(default_factory=list)
    has_confirmed_tech: bool = False


@dataclass
class CareerFitAnalysis:
    fit_score: int = 0
    career_growth_score: int = 0
    motivation_score: int = 0
    strong_points: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    questions_for_interview: List[str] = field(default_factory=list)
    recommendation: Optional[str] = None


@dataclass
class VacancyScore:
    salary_fit: int = 0
    format_fit: int = 0
    dms_fit: int = 0
    technical_interest: int = 0
    career_potential: int = 0
    total: int = 0
    weights: Dict[str, float] = field(default_factory=lambda: {
        "salary_fit": 0.25,
        "format_fit": 0.25,
        "dms_fit": 0.15,
        "technical_interest": 0.25,
        "career_potential": 0.10,
    })
    explanation: List[str] = field(default_factory=list)


@dataclass
class Vacancy:
    id: str
    title: str
    employer: Optional[str] = None
    source_url: str = ""
    alternate_urls: List[str] = field(default_factory=list)
    source_name: str = "unknown"
    published_at: Optional[datetime] = None
    checked_at: Optional[datetime] = None
    location: Optional[str] = None
    work_format: WorkFormat = WorkFormat.UNKNOWN
    salary: SalaryInfo = field(default_factory=SalaryInfo)
    benefits: BenefitsInfo = field(default_factory=BenefitsInfo)
    technology_stack: List[str] = field(default_factory=list)
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    confirmed_facts: List[str] = field(default_factory=list)
    evidence: List[SourceEvidence] = field(default_factory=list)
    technical_analysis: TechnicalAnalysis = field(default_factory=TechnicalAnalysis)
    career_fit: CareerFitAnalysis = field(default_factory=CareerFitAnalysis)
    score: VacancyScore = field(default_factory=VacancyScore)
    status: VacancyStatus = VacancyStatus.NEEDS_CLARIFICATION
    non_compliance_reasons: List[str] = field(default_factory=list)
    data_completeness: DataCompleteness = DataCompleteness.UNKNOWN
    llm_summary: Optional[str] = None
    llm_why_fits: Optional[str] = None
    llm_unknowns: List[str] = field(default_factory=list)
    llm_what_to_ask: List[str] = field(default_factory=list)
