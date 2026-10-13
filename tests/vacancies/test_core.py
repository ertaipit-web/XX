from __future__ import annotations

from datetime import datetime
from src.vacancies.core.contracts import ResearchRun, VacancyReport
from src.vacancies.core.enums import DmsStatus, VacancyStatus, WorkFormat
from src.vacancies.core.models import BenefitsInfo, SalaryInfo, Vacancy, VacancyScore
from src.vacancies.reporting.writers import VacancyReportWriter
from pathlib import Path


def test_minimal_scenario(tmp_path) -> None:
    run = ResearchRun(run_id="t1", started_at=datetime.now())
    v = Vacancy(
        id="123",
        title="Go-разработчик",
        employer="Test",
        source_url="https://example.com/v/123",
        work_format=WorkFormat.REMOTE,
        salary=SalaryInfo(from_amount=120000, to_amount=150000),
        benefits=BenefitsInfo(dms_status=DmsStatus.UNKNOWN),
        score=VacancyScore(total=70),
        status=VacancyStatus.NEEDS_CLARIFICATION,
    )
    report = VacancyReport(run=run, vacancies=[v], needs_clarification=[v])
    md = VacancyReportWriter.write_markdown(report, tmp_path / "test_min.md")
    js = VacancyReportWriter.write_json(report, tmp_path / "test_min.json")
    assert md.exists()
    assert js.exists()
