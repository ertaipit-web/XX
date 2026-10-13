from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from ..core.contracts import VacancyReport
from ..core.enums import Currency, DmsStatus, TaxType, VacancyStatus, WorkFormat


class VacancyReportWriter:
    @staticmethod
    def _serialize(obj: Any) -> Any:
        if is_dataclass(obj):
            return {k: VacancyReportWriter._serialize(v) for k, v in asdict(obj).items()}
        if isinstance(obj, dict):
            return {k: VacancyReportWriter._serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [VacancyReportWriter._serialize(v) for v in obj]
        if isinstance(obj, Enum if False else (Currency, DmsStatus, TaxType, VacancyStatus, WorkFormat)):
            try:
                return obj.value
            except Exception:
                return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    @staticmethod
    def write_json(report: VacancyReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = VacancyReportWriter._serialize(report)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    @staticmethod
    def write_markdown(report: VacancyReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        run = report.run
        lines: List[str] = []
        lines.append("# Отчёт по вакансиям Go-разработчика")
        lines.append("")
        lines.append(f"- Дата и время запуска: {run.started_at.isoformat()}")
        lines.append(f"- Период поиска: {run.metadata.get('search_period', 'не указан')}")
        lines.append(f"- Найдено вакансий: {run.vacancies_found}")
        lines.append(f"- Проверено вакансий: {run.vacancies_checked}")
        lines.append(f"- Уникальных после дедупликации: {run.vacancies_unique}")
        lines.append(f"- Подходящих: {run.vacancies_suitable}")
        lines.append(f"- Требуют уточнения: {run.vacancies_needs_clarification}")
        lines.append(f"- Ограничения: {run.metadata.get('limitations', 'не указаны')}")
        lines.append("")

        if report.vacancies:
            lines.append("## Таблица вакансий")
            lines.append("| Рейтинг | Название | Компания | Зарплата | Формат | ДМС | Соответствие | Интересность | Риски | Дата проверки | Ссылка |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
            for v in sorted(report.vacancies, key=lambda x: x.score.total, reverse=True):
                salary = "-"
                if v.salary.from_amount is not None or v.salary.to_amount is not None:
                    f = v.salary.from_amount if v.salary.from_amount is not None else ""
                    t = v.salary.to_amount if v.salary.to_amount is not None else ""
                    cur = v.salary.currency.value if hasattr(v.salary.currency, "value") else v.salary.currency
                    salary = f"{f}–{t} {cur}".replace("– ", "–").replace(" –", "–")
                dms = v.benefits.dms_status.value if hasattr(v.benefits.dms_status, "value") else v.benefits.dms_status
                status = v.status.value if hasattr(v.status, "value") else v.status
                risks = "; ".join(v.career_fit.risks[:2]) or "-"
                checked = v.checked_at.isoformat() if v.checked_at else "-"
                lines.append(f"| {v.score.total} | {v.title} | {v.employer or '-'} | {salary} | {v.work_format.value} | {dms} | {status} | {v.technical_analysis.task_interest_score} | {risks} | {checked} | [{v.source_url}]({v.source_url}) |")
            lines.append("")

        if report.best_vacancies:
            lines.append("## Лучшие вакансии")
            for v in report.best_vacancies:
                lines.append(f"### {v.title} — {v.employer or ''}")
                lines.append(f"- Рейтинг: {v.score.total}")
                lines.append(f"- Ссылка: {v.source_url}")
                lines.append("- Почему подходит: " + ("; ".join(v.career_fit.strong_points) or "-"))
                lines.append("")

        if report.needs_clarification:
            lines.append("## Требуют уточнения")
            for v in report.needs_clarification:
                lines.append(f"- {v.title} ({v.employer or '-'}) — {v.source_url}")

        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
