"""Configuration loader for candidate profile and scoring weights."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..core.enums import Currency, WorkFormat
from ..core.models import CandidateProfile

logger = logging.getLogger(__name__)

# Project root is 3 levels up from this file: src/vacancies/utils/config.py -> project root
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"
DEFAULT_CANDIDATE_YAML = DEFAULT_CONFIG_DIR / "candidate.yaml"
DEFAULT_SCORING_YAML = DEFAULT_CONFIG_DIR / "scoring.yaml"


def _clean_bom(text: str) -> str:
    """Remove BOM if present."""
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _parse_work_formats(raw: List[str]) -> List[WorkFormat]:
    """Parse work format strings to WorkFormat enum."""
    result = []
    for fmt in raw:
        s = str(fmt).strip().lower()
        if s in ("remote", "удалённо", "удаленно"):
            result.append(WorkFormat.REMOTE)
        elif s in ("hybrid", "гибрид"):
            result.append(WorkFormat.HYBRID)
        elif s in ("office", "офис"):
            result.append(WorkFormat.OFFICE)
        else:
            logger.warning("Unknown work format: %s", fmt)
    return result


def _parse_currency(raw: str) -> Currency:
    """Parse currency string to Currency enum."""
    s = str(raw).strip().upper()
    mapping = {
        "RUB": Currency.RUB,
        "RUR": Currency.RUB,
        "USD": Currency.USD,
        "EUR": Currency.EUR,
    }
    return mapping.get(s, Currency.UNKNOWN)


class ConfigLoader:
    """Loads and validates YAML configuration files."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR

    def load_candidate_profile(self, path: Path | None = None) -> CandidateProfile:
        """Load candidate profile from YAML file."""
        path = path or DEFAULT_CANDIDATE_YAML
        if not path.exists():
            logger.warning("Candidate config not found: %s, using defaults", path)
            return CandidateProfile()

        text = _clean_bom(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(text) or {}

        return CandidateProfile(
            profession=str(data.get("profession", "Go-разработчик")),
            locations=data.get("locations", ["Санкт-Петербург", "Удалённая работа"]),
            work_formats=_parse_work_formats(data.get("work_formats", ["remote", "hybrid"])),
            min_salary_rub_month=float(data.get("min_salary_rub_month", 119000)),
            require_dms=bool(data.get("require_dms", True)),
            language=str(data.get("language", "ru")),
            main_currency=_parse_currency(data.get("main_currency", "RUB")),
        )

    def load_scoring_weights(self, path: Path | None = None) -> Dict[str, float]:
        """Load scoring weights from YAML file."""
        path = path or DEFAULT_SCORING_YAML
        if not path.exists():
            logger.warning("Scoring config not found: %s, using defaults", path)
            return {
                "salary_fit": 0.25,
                "format_fit": 0.25,
                "dms_fit": 0.15,
                "technical_interest": 0.25,
                "career_potential": 0.10,
            }

        text = _clean_bom(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(text) or {}

        # Validate weights sum to ~1.0
        total = sum(data.values())
        if abs(total - 1.0) > 0.01:
            logger.warning("Scoring weights sum to %.2f (expected 1.0), normalizing", total)
            if total > 0:
                data = {k: v / total for k, v in data.items()}

        return {str(k): float(v) for k, v in data.items()}

    def save_candidate_profile(self, profile: CandidateProfile, path: Path | None = None) -> None:
        """Save candidate profile to YAML file."""
        path = path or DEFAULT_CANDIDATE_YAML
        path.parent.mkdir(parents=True, exist_ok=True)

        data = asdict(profile)
        # Convert enums to strings
        for key, val in data.items():
            if isinstance(val, list) and val and isinstance(val[0], WorkFormat):
                data[key] = [v.value for v in val]
            elif isinstance(val, Currency):
                data[key] = val.value

        text = yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
        path.write_text(text, encoding="utf-8")
