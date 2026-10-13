from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.vacancies.core.contracts import ResearchRun, VacancyReport
from src.vacancies.core.enums import DmsStatus, TaxType, VacancyStatus, WorkFormat
from src.vacancies.core.models import BenefitsInfo, SalaryInfo, Vacancy, VacancyScore
from src.vacancies.reporting.writers import VacancyReportWriter


def test_markdown_and_json_generation(tmp_path):
    run = ResearchRun(run_id='s1', started_at=datetime.now())
    v = Vacancy(
        id='1',
        title='Go-разработчик',
        employer='TestCo',
        source_url='https://example.com/1',
        work_format=WorkFormat.REMOTE,
        salary=SalaryInfo(from_amount=119000, to_amount=160000, tax_type=TaxType.UNKNOWN),
        benefits=BenefitsInfo(dms_status=DmsStatus.NOT_MENTIONED),
        score=VacancyScore(total=85),
        status=VacancyStatus.NEEDS_CLARIFICATION,
    )
    report = VacancyReport(
        run=run,
        vacancies=[v],
        best_vacancies=[v],
        needs_clarification=[v],
    )
    md = VacancyReportWriter.write_markdown(report, tmp_path / 'latest.md')
    js = VacancyReportWriter.write_json(report, tmp_path / 'latest.json')
    assert md.exists() and js.exists()
    assert 'Go-разработчик' in md.read_text(encoding='utf-8')
    assert 'vacancies' in js.read_text(encoding='utf-8')
