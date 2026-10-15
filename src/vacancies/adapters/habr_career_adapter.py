"""Habr Career adapter for vacancy search."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from ..core.enums import Currency, DmsStatus, TaxType, WorkFormat
from ..core.models import BenefitsInfo, SalaryInfo, Vacancy
from .base import SourceAdapter

logger = logging.getLogger(__name__)

# Habr Career API (if available)
API_BASE = "https://career.habr.com/api/v2"
DEFAULT_USER_AGENT = "vacancy-research-agent/1.0"


class HabrCareerAdapter(SourceAdapter):
    """Adapter for Habr Career official API."""

    @property
    def source_name(self) -> str:
        return "career.habr.com"

    def __init__(self, access_token: Optional[str] = None) -> None:
        self.access_token = access_token or os.environ.get("HABR_CAREER_TOKEN")

    def _make_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _request(self, url: str) -> Optional[Dict[str, Any]]:
        import requests
        try:
            response = requests.get(url, headers=self._make_headers(), timeout=20)
            if response.status_code == 401:
                logger.warning("Habr Career: Unauthorized (invalid/expired token)")
                return None
            if response.status_code == 429:
                logger.warning("Habr Career: Rate limited")
                return None
            if response.status_code != 200:
                logger.error(f"Habr Career request failed: {response.status_code} {response.text}")
                return None
            return response.json()
        except Exception as e:
            logger.error(f"Habr Career network error: {e}")
            return None

    def search(self, query: "SearchQuery") -> List["Vacancy"]:
        if not self.access_token:
            logger.info("Habr Career: No token, returning mock data for testing")
            return self._mock_search(query)

        text = query.text or "go разработчик"
        max_pages = query.max_pages or 1
        per_page = min(query.page_size or 20, 50)

        vacancies: List["Vacancy"] = []
        for page in range(query.max_pages or 1):
            params = {
                "q": text,
                "page": page + 1,
                "per_page": per_page,
            }
            url = f"{API_BASE}/vacancies?{urlencode(params)}"
            try:
                payload = self._request(url)
                if not payload:
                    break

                for item in payload.get("vacancies", []):
                    v = self._normalize_item(item)
                    if v:
                        vacancies.append(v)

                if page + 1 >= payload.get("pages", 1):
                    break
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"Habr Career search error: {e}")
                break

        return vacancies

    def fetch_details(self, vacancy: "Vacancy") -> "Vacancy":
        if not vacancy.id or not self.access_token:
            return vacancy

        import requests
        try:
            url = f"{API_BASE}/vacancies/{vacancy.id}"
            response = requests.get(url, headers=self._make_headers(), timeout=20)
            if response.status_code == 200:
                data = response.json()
                self._normalize_item(data, target=vacancy)
        except Exception as e:
            logger.warning(f"Failed to fetch Habr Career details for {vacancy.id}: {e}")
        return vacancy

    def _normalize_item(self, item: Dict[str, Any], target: Optional["Vacancy"] = None) -> Optional["Vacancy"]:
        from ..core.enums import Currency, DmsStatus, TaxType, WorkFormat
        from ..core.models import BenefitsInfo, SalaryInfo, Vacancy

        salary = item.get("salary") or {}
        salary_from = salary.get("from")
        salary_to = salary.get("to")
        currency = salary.get("currency", "RUB")

        if salary_from is None and salary_to is None:
            return None

        work_format_str = (item.get("employment_type") or {}).get("title", "").lower()
        if "удален" in work_format_str or "remote" in work_format_str:
            work_format = WorkFormat.REMOTE
        elif "частичн" in work_format_str or "гибр" in work_format_str or "hybrid" in work_format_str:
            work_format = WorkFormat.HYBRID
        else:
            work_format = WorkFormat.OFFICE

        area = item.get("area", {}).get("name", "")

        vac = target or Vacancy(
            id=str(item.get("id")),
            title=item.get("title") or "",
            employer=item.get("company", {}).get("name"),
            source_url=item.get("url") or "",
            source_name=self.source_name,
            location=area,
            published_at=item.get("published_at"),
        )

        if salary_from is not None or salary_to is not None:
            vac.salary = SalaryInfo(
                from_amount=float(salary_from) if salary_from else None,
                to_amount=float(salary_to) if salary_to else None,
                currency=self._map_currency(currency),
                tax_type=TaxType.UNKNOWN,
                period="month",
            )

        vac.work_format = work_format
        vac.description = item.get("description")
        vac.requirements = item.get("skills")
        vac.technology_stack = item.get("skills", [])

        return vac

    def _map_currency(self, cur: str) -> "Currency":
        from ..core.enums import Currency
        if not cur:
            return Currency.UNKNOWN
        mapping = {"RUB": Currency.RUB, "RUR": Currency.RUB, "USD": Currency.USD, "EUR": Currency.EUR}
        return mapping.get(cur.upper(), Currency.UNKNOWN)

    def _mock_search(self, query: "SearchQuery") -> List["Vacancy"]:
        """Return mock data for testing when no token."""
        logger.info("Habr Career: Using mock data (no token)")
        return []

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source": self.source_name,
            "available": bool(self.access_token),
            "limitations": ["Requires Habr Career API token"] if not self.access_token else [],
        }