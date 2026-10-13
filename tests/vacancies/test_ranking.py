from __future__ import annotations

from src.vacancies.core.enums import DmsStatus, WorkFormat
from src.vacancies.core.models import BenefitsInfo, SalaryInfo, Vacancy, VacancyScore
from src.vacancies.core.scoring import ScoringCalculator


def test_dms_not_confirmed_marked():
    v = Vacancy(
        id='1',
        title='Go-разработчик',
        source_url='https://example.com/1',
        work_format=WorkFormat.REMOTE,
        salary=SalaryInfo(from_amount=120000),
        benefits=BenefitsInfo(dms_status=DmsStatus.NOT_MENTIONED),
        score=VacancyScore(salary_fit=100, format_fit=100, dms_fit=0, technical_interest=60, career_potential=50),
    )
    ScoringCalculator.calculate_score(v)
    assert v.score.total > 0
    assert v.benefits.dms_status == DmsStatus.NOT_MENTIONED
