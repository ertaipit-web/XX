"""Configuration loader for candidate profile and scoring weights."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..core.enums import Currency, DmsMode, WorkFormat
from ..core.models import CandidateProfile
from ..llm.client import LLMConfig

logger = logging.getLogger(__name__)

# Project root is 3 levels up from this file: src/vacancies/utils/config.py -> project root
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"
DEFAULT_CANDIDATE_YAML = DEFAULT_CONFIG_DIR / "candidate.yaml"
DEFAULT_SCORING_YAML = DEFAULT_CONFIG_DIR / "scoring.yaml"
DEFAULT_LLM_YAML = DEFAULT_CONFIG_DIR / "llm.yaml"


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
        if s in ("remote", "удалённо", "удаленно", "remote_any"):
            result.append(WorkFormat.REMOTE)
        elif s in ("hybrid", "гибрид", "hybrid_spb"):
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


def _parse_dms_mode(raw: str) -> str:
    """Parse DMS mode string."""
    s = str(raw).strip().lower()
    if s in ("prefer", "preferred"):
        return "prefer"
    if s in ("required", "mandatory"):
        return "required"
    logger.warning("Unknown DMS mode: %s, defaulting to 'prefer'", raw)
    return "prefer"


class ConfigLoader:
    """Loads and validates YAML configuration files."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or DEFAULT_CONFIG_DIR

    def load_candidate_profile(self, path: Path | None = None) -> CandidateProfile:
        """Load candidate profile from YAML file.

        Supports both legacy flat format and new nested format from problem-definition.
        """
        path = path or DEFAULT_CANDIDATE_YAML
        if not path.exists():
            logger.warning("Candidate config not found: %s, using defaults", path)
            return CandidateProfile()

        text = _clean_bom(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(text) or {}

        # --- Extract values with support for both formats ---
        # Profession / candidate level
        profession = str(data.get("profession", "Go-разработчик"))
        candidate_level = str(data.get("candidate_level", "junior"))
        experience_years = data.get("experience_years")

        # Location - support both flat and nested
        locations = data.get("locations")
        if locations is None:
            loc = data.get("location", {})
            if isinstance(loc, dict):
                city = loc.get("city", "Санкт-Петербург")
                country = loc.get("country", "Россия")
                locations = [city, f"Удалённая работа ({country})"]
            else:
                locations = ["Санкт-Петербург", "Удалённая работа"]

        # Work formats - support both flat and nested
        work_formats_raw = data.get("work_formats")
        if work_formats_raw is None:
            wp = data.get("work_preferences", [])
            work_formats_raw = wp if wp else ["remote", "hybrid"]
        work_formats = _parse_work_formats(work_formats_raw)

        # Salary - support both flat and nested
        min_salary = data.get("min_salary_rub_month")
        if min_salary is None:
            sal = data.get("salary", {})
            min_salary = sal.get("minimum", 119000) if isinstance(sal, dict) else 119000

        min_salary_tax_basis = data.get("min_salary_tax_basis")
        if min_salary_tax_basis is None:
            sal = data.get("salary", {})
            min_salary_tax_basis = sal.get("tax_basis", "net") if isinstance(sal, dict) else "net"

        min_salary_period = data.get("min_salary_period")
        if min_salary_period is None:
            sal = data.get("salary", {})
            min_salary_period = sal.get("period", "month") if isinstance(sal, dict) else "month"

        min_salary_is_mandatory = data.get("min_salary_is_mandatory")
        if min_salary_is_mandatory is None:
            sal = data.get("salary", {})
            min_salary_is_mandatory = sal.get("is_mandatory", True) if isinstance(sal, dict) else True

        # DMS - support both formats
        dms_mode = data.get("dms_mode")
        if dms_mode is None:
            dms_cfg = data.get("benefits", {}).get("dms", {}) if isinstance(data.get("benefits"), dict) else {}
            dms_mode = dms_cfg.get("mode", "prefer")
        dms_mode = _parse_dms_mode(dms_mode)

        # Language
        language = str(data.get("language", "ru"))
        if language == "ru" and "report" in data:
            language = str(data.get("report", {}).get("language", "ru"))

        # Main currency
        main_currency_raw = data.get("main_currency")
        if main_currency_raw is None:
            sal = data.get("salary", {})
            main_currency_raw = sal.get("currency", "RUB") if isinstance(sal, dict) else "RUB"
        main_currency = _parse_currency(main_currency_raw)

        # Search frequency
        search_frequency = data.get("search_frequency")
        if search_frequency is None:
            search_cfg = data.get("search", {})
            search_frequency = search_cfg.get("frequency", "daily") if isinstance(search_cfg, dict) else "daily"

        # LLM settings
        llm_provider = data.get("llm_provider")
        if llm_provider is None:
            llm_cfg = data.get("llm", {})
            llm_provider = llm_cfg.get("provider", "ollama") if isinstance(llm_cfg, dict) else "ollama"

        cloud_fallback_enabled = data.get("cloud_fallback_enabled")
        if cloud_fallback_enabled is None:
            llm_cfg = data.get("llm", {})
            cloud_fallback_enabled = llm_cfg.get("cloud_fallback_enabled", False) if isinstance(llm_cfg, dict) else False

        # Additional notes
        additional_notes = data.get("additional_notes")

        # Contradictions and missing data
        contradictions = data.get("contradictions", [])
        missing_data = data.get("missing_data", [])

        return CandidateProfile(
            profession=profession,
            candidate_level=candidate_level,
            experience_years=experience_years,
            locations=locations,
            work_formats=work_formats,
            min_salary_rub_month=float(min_salary),
            min_salary_tax_basis=min_salary_tax_basis,
            min_salary_period=min_salary_period,
            min_salary_is_mandatory=bool(min_salary_is_mandatory),
            dms_mode=dms_mode,
            language=language,
            main_currency=main_currency,
            search_frequency=search_frequency,
            llm_provider=llm_provider,
            cloud_fallback_enabled=cloud_fallback_enabled,
            additional_notes=additional_notes,
            contradictions=contradictions,
            missing_data=missing_data,
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

    def load_llm_config(self, path: Path | None = None) -> LLMConfig:
        """Load LLM provider configuration from YAML file.

        Environment overrides (useful for tests/CI):
            VACANCIES_LLM_PROVIDER  — force provider (e.g. "mock")
            VACANCIES_DISABLE_LLM   — "1"/"true" disables LLM entirely
        """
        path = path or DEFAULT_LLM_YAML
        if not path.exists():
            logger.warning("LLM config not found: %s, using defaults", path)
            config = LLMConfig()
        else:
            text = _clean_bom(path.read_text(encoding="utf-8"))
            data = yaml.safe_load(text) or {}
            config = LLMConfig(
                provider=str(data.get("provider", "ollama")),
                model=str(data.get("model", "qwen2.5-coder:3b")),
                base_url=str(data.get("base_url", "http://localhost:11434")),
                temperature=float(data.get("temperature", 0.2)),
                timeout=float(data.get("timeout", 120.0)),
                max_retries=int(data.get("max_retries", 2)),
                retry_delay=float(data.get("retry_delay", 1.0)),
                max_output_tokens=int(data.get("max_output_tokens", 512)),
                enabled=bool(data.get("enabled", True)),
            )

        env_provider = os.environ.get("VACANCIES_LLM_PROVIDER")
        if env_provider:
            config.provider = env_provider
        if os.environ.get("VACANCIES_DISABLE_LLM", "").lower() in ("1", "true", "yes"):
            config.enabled = False

        return config

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