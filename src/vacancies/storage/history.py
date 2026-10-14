from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.contracts import ResearchRun, VacancyReport
from ..core.models import Vacancy

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DIR = Path(__file__).resolve().parent.parent.parent.parent / "history"
DEFAULT_RUNS_DIR = DEFAULT_HISTORY_DIR / "runs"
DEFAULT_INDEX_FILE = DEFAULT_HISTORY_DIR / "index.json"


class RunHistory:
    """Manages run history and vacancy tracking across runs."""

    def __init__(self, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
        self.history_dir = history_dir
        self.runs_dir = history_dir / "runs"
        self.index_file = history_dir / "index.json"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, report: VacancyReport) -> None:
        """Save a completed research run to history."""
        run = report.run
        run_file = self.runs_dir / f"{run.run_id}.json"

        # Prepare run data for storage
        run_data = {
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "vacancies_found": run.vacancies_found,
            "vacancies_checked": run.vacancies_checked,
            "vacancies_unique": run.vacancies_unique,
            "vacancies_suitable": run.vacancies_suitable,
            "vacancies_needs_clarification": run.vacancies_needs_clarification,
            "errors": run.errors,
            "agent_results": [
                {
                    "agent_name": ar.agent_name,
                    "success": ar.success,
                    "messages": ar.messages,
                    "errors": ar.errors,
                    "data": ar.data,
                    "processed_count": ar.processed_count,
                }
                for ar in run.agent_results
            ],
            "metadata": run.metadata,
            "vacancies": [self._vacancy_to_dict(v) for v in report.vacancies],
        }

        run_file.write_text(json.dumps(run_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Update index
        self._update_index(run.run_id, run_data)

        logger.info("Saved run %s to history", run.run_id)

    def _vacancy_to_dict(self, v: Vacancy) -> Dict[str, Any]:
        """Convert Vacancy to dict for storage."""
        return {
            "id": v.id,
            "title": v.title,
            "employer": v.employer,
            "source_url": v.source_url,
            "alternate_urls": v.alternate_urls,
            "canonical_url": v.canonical_url,
            "source_name": v.source_name,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "checked_at": v.checked_at.isoformat() if v.checked_at else None,
            "location": v.location,
            "work_format": v.work_format.value if hasattr(v.work_format, "value") else str(v.work_format),
            "salary": {
                "from_amount": v.salary.from_amount,
                "to_amount": v.salary.to_amount,
                "currency": v.salary.currency.value if hasattr(v.salary.currency, "value") else str(v.salary.currency),
                "tax_type": v.salary.tax_type.value if hasattr(v.salary.tax_type, "value") else str(v.salary.tax_type),
                "period": v.salary.period,
            },
            "benefits": {
                "dms_status": v.benefits.dms_status.value if hasattr(v.benefits.dms_status, "value") else str(v.benefits.dms_status),
            },
            "status": v.status.value if hasattr(v.status, "value") else str(v.status),
            "score": v.score.total,
        }

    def _update_index(self, run_id: str, run_data: Dict[str, Any]) -> None:
        """Update the run index."""
        index: Dict[str, Any] = {"runs": []}
        if self.index_file.exists():
            try:
                index = json.loads(self.index_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Add new run
        index["runs"].append({
            "run_id": run_id,
            "started_at": run_data["started_at"],
            "vacancies_found": run_data["vacancies_found"],
            "vacancies_unique": run_data["vacancies_unique"],
            "suitable": run_data["vacancies_suitable"],
        })

        # Keep only last 100 runs
        index["runs"] = index["runs"][-100:]
        self.index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_previous_run(self, max_age_days: int = 30) -> Optional[Dict[str, Any]]:
        """Get the most recent successful run within max_age_days."""
        if not self.index_file.exists():
            return None

        try:
            index = json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return None

        runs = index.get("runs", [])
        if not runs:
            return None

        # Find most recent run within age limit
        now = datetime.now()
        for run_info in reversed(runs):
            started_str = run_info.get("started_at")
            if not started_str:
                continue
            try:
                started = datetime.fromisoformat(started_str)
                if (now - started).days <= max_age_days:
                    run_file = self.runs_dir / f"{run_info['run_id']}.json"
                    if run_file.exists():
                        return json.loads(run_file.read_text(encoding="utf-8"))
            except Exception:
                continue
        return None

    def detect_new_and_changed(self, current_vacancies: List[Vacancy], max_age_days: int = 30) -> Dict[str, List[Vacancy]]:
        """Compare current vacancies with previous run to detect new and changed."""
        prev_run = self.get_previous_run(max_age_days)
        if not prev_run:
            return {"new": current_vacancies, "changed": [], "removed": [], "unchanged": []}

        prev_vacancies = {v["id"]: v for v in prev_run.get("vacancies", [])}
        curr_by_id = {v.id: v for v in current_vacancies}

        new = []
        changed = []
        unchanged = []

        for v in current_vacancies:
            if v.id not in prev_vacancies:
                new.append(v)
            else:
                # Check for changes in key fields
                prev = prev_vacancies[v.id]
                if self._vacancy_changed(v, prev):
                    changed.append(v)
                else:
                    unchanged.append(v)

        removed_ids = set(prev_vacancies.keys()) - set(curr_by_id.keys())
        removed = [prev_vacancies[rid] for rid in removed_ids if prev_vacancies[rid].get("status") != "not_suitable"]

        return {"new": new, "changed": changed, "removed": removed, "unchanged": unchanged}

    def _vacancy_changed(self, current: Vacancy, previous: Dict[str, Any]) -> bool:
        """Check if a vacancy has significant changes since last run."""
        # Compare salary
        if current.salary.from_amount != previous.get("salary", {}).get("from_amount"):
            return True
        if current.salary.to_amount != previous.get("salary", {}).get("to_amount"):
            return True
        if current.work_format.value != previous.get("work_format"):
            return True
        if current.status.value != previous.get("status"):
            return True
        if current.benefits.dms_status.value != previous.get("benefits", {}).get("dms_status"):
            return True
        if current.location != previous.get("location"):
            return True
        return False


class NewVacancyDetector:
    """Detects and tracks new vacancies across runs."""

    def __init__(self, history: RunHistory) -> None:
        self.history = history

    def detect(self, current_vacancies: List[Vacancy]) -> Dict[str, Any]:
        """Detect new/changed/removed vacancies."""
        return self.history.detect_new_and_changed(current_vacancies)

    def format_for_report(self, detection: Dict[str, List[Vacancy]]) -> Dict[str, List[Dict[str, Any]]]:
        """Format detection results for report inclusion."""
        return {
            "new": [self._vacancy_summary(v) for v in detection["new"]],
            "changed": [self._vacancy_summary(v) for v in detection["changed"]],
            "removed": [self._vacancy_summary(v) for v in detection["removed"]],
        }

    def _vacancy_summary(self, v: Vacancy) -> Dict[str, Any]:
        return {
            "id": v.id,
            "title": v.title,
            "employer": v.employer,
            "source_url": v.source_url,
            "source_name": v.source_name,
            "status": v.status.value if hasattr(v.status, "value") else str(v.status),
            "salary": f"{v.salary.from_amount}-{v.salary.to_amount} {v.salary.currency.value}" if v.salary.from_amount else "не указана",
        }