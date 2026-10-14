from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from ..core.enums import Currency, DmsStatus, WorkFormat
from ..core.models import BenefitsInfo, SalaryInfo, Vacancy
from .base import SourceAdapter

logger = logging.getLogger(__name__)

# Mock/public API for a second source (e.g., Habr Career, SuperJob, or generic JSON feed)
# This can be replaced with a real API integration

PUBLIC_SOURCES = {
    "habr": {
        "base_url": "https://career.habr.com/vacancies",
        "search_params": {"q": "", "type": "all"},
    },
    "superjob": {
        "base_url": "https://api.superjob.ru/2.0/vacancies",
        "search_params": {"keyword": "", "town": 4},  # 4 = SPb
    },
}


class GenericJSONFeedAdapter(SourceAdapter):
    """Adapter for generic JSON vacancy feeds (RSS, custom APIs, etc.)."""

    @property
    def source_name(self) -> str:
        return "generic-json-feed"

    def __init__(self, feed_url: str, mapping: Dict[str, str] | None = None) -> None:
        self.feed_url = feed_url
        self.mapping = mapping or {
            "id": "id",
            "title": "title",
            "employer": "company.name",
            "url": "url",
            "location": "location",
            "description": "description",
            "salary_from": "salary.from",
            "salary_to": "salary.to",
            "currency": "salary.currency",
            "work_format": "employment_type",
        }

    def search(self, query: "SearchQuery") -> List[Vacancy]:
        """Fetch and filter vacancies from JSON feed."""
        import urllib.request
        try:
            req = urllib.request.Request(self.feed_url, headers={"User-Agent": "vacancy-agent/1.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logger.error("Failed to fetch feed %s: %s", self.feed_url, e)
            return []

        items = data if isinstance(data, list) else data.get("items", [])
        vacancies: List[Vacancy] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            # Filter by query text
            text = query.text.lower() if query.text else ""
            title = str(item.get(self.mapping.get("title", "title"), ""))
            if text and text not in title.lower():
                continue

            v = self._normalize_item(item)
            vacancies.append(v)

        return vacancies

    def fetch_details(self, vacancy: Vacancy) -> Vacancy:
        return vacancy  # Already have full data from feed

    def _normalize_item(self, item: Dict[str, Any]) -> Vacancy:
        def get_nested(obj: Dict, path: str) -> Any:
            keys = path.split(".")
            for k in keys:
                if isinstance(obj, dict):
                    obj = obj.get(k)
                else:
                    return None
            return obj

        title = str(get_nested(item, self.mapping.get("title", "title")) or "")
        employer = get_nested(item, self.mapping.get("employer", "employer"))
        url = str(get_nested(item, self.mapping.get("url", "url")) or "")
        location = str(get_nested(item, self.mapping.get("location", "location")) or "")

        v = Vacancy(
            id=str(get_nested(item, self.mapping.get("id", "id")) or url or ""),
            title=title,
            employer=str(employer) if employer else None,
            source_url=url,
            source_name=self.source_name,
            location=location,
            description=str(get_nested(item, self.mapping.get("description", "description")) or ""),
        )

        # Salary
        from_amt = get_nested(item, self.mapping.get("salary_from", "salary_from"))
        to_amt = get_nested(item, self.mapping.get("salary_to", "salary_to"))
        currency = str(get_nested(item, self.mapping.get("currency", "currency")) or "RUB")

        if from_amt is not None or to_amt is not None:
            v.salary = SalaryInfo(
                from_amount=float(from_amt) if from_amt is not None else None,
                to_amount=float(to_amt) if to_amt is not None else None,
                currency=self._map_currency(currency),
            )

        # Work format
        fmt = str(get_nested(item, self.mapping.get("work_format", "work_format")) or "")
        v.work_format = self._parse_work_format(fmt)

        return v

    @staticmethod
    def _map_currency(cur: str | None) -> Currency:
        if not cur:
            return Currency.UNKNOWN
        mapping = {"RUB": Currency.RUB, "RUR": Currency.RUB, "USD": Currency.USD, "EUR": Currency.EUR}
        return mapping.get(cur.upper(), Currency.UNKNOWN)

    def _parse_work_format(self, fmt: str) -> WorkFormat:
        if not fmt:
            return WorkFormat.UNKNOWN
        f = fmt.lower()
        if "remote" in f or "удал" in f:
            return WorkFormat.REMOTE
        if "hybrid" in f or "гибр" in f:
            return WorkFormat.HYBRID
        if "office" in f or "офис" in f:
            return WorkFormat.OFFICE
        return WorkFormat.UNKNOWN


class HabrAdapter(SourceAdapter):
    """Adapter for Habr Career (mock implementation for testing)."""

    @property
    def source_name(self) -> str:
        return "habr.com"

    def __init__(self) -> None:
        pass

    def search(self, query: "SearchQuery") -> List[Vacancy]:
        # Mock implementation - in production, use Habr API
        logger.info("Habr adapter: mock search for %s", query.text)
        return []

    def fetch_details(self, vacancy: Vacancy) -> Vacancy:
        return vacancy

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source": self.source_name,
            "available": False,
            "limitations": ["Requires Habr Career API access - mock implementation"],
        }


class MultiSourceAdapter:
    """Orchestrates multiple source adapters."""

    def __init__(self, adapters: List[SourceAdapter]) -> None:
        self.adapters = {a.source_name: a for a in adapters}

    def search_all(self, query: "SearchQuery") -> Dict[str, List[Vacancy]]:
        results: Dict[str, List[Vacancy]] = {}
        for name, adapter in self.adapters.items():
            try:
                results[name] = adapter.search(query)
                logger.info("Source %s returned %d vacancies", name, len(results[name]))
            except Exception as e:
                logger.error("Source %s failed: %s", name, e)
                results[name] = []
        return results

    def get_all_statuses(self) -> Dict[str, Dict[str, Any]]:
        return {name: adapter.get_source_status() for name, adapter in self.adapters.items()}