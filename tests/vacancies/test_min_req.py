from __future__ import annotations

from src.vacancies.core.enums import Currency, DmsStatus, TaxType, WorkFormat, VacancyStatus
from src.vacancies.core.models import BenefitsInfo, SalaryInfo, Vacancy
from src.vacancies.go_agents.specialists import CompensationBenefitsAgent, DeduplicationRankingAgent


def test_min_salary_check():
    v = Vacancy(
        id='m1',
        title='Go-разработчик',
        source_url='https://example.com/m1',
        work_format=WorkFormat.REMOTE,
        salary=SalaryInfo(from_amount=100000, currency=Currency.RUB, tax_type=TaxType.UNKNOWN),
        benefits=BenefitsInfo(dms_status=DmsStatus.UNKNOWN),
    )
    comp = CompensationBenefitsAgent()
    comp.run([v])
    dedup = DeduplicationRankingAgent()
    dedup.run([v])
    assert v.status == VacancyStatus.NOT_SUITABLE
