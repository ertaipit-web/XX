"""Rabota.ru API adapter for vacancy search."""

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

# Rabota.ru API documentation
API_BASE = "https://api.rabota.ru/v3"
DEFAULT_USER_AGENT = "vacancy-research-agent/1.0"


class RabotaRuAdapter(SourceAdapter):
    """Adapter for Rabota.ru official API."""

    @property
    def source_name(self) -> str:
        return "rabota.ru"

    def __init__(self, access_token: Optional[str] = None) -> None:
        self.access_token = access_token or os.environ.get("RABOTA_RU_TOKEN")

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
                logger.error("Rabota.ru: Unauthorized (invalid/expired token)")
                return None
            if response.status_code == 429:
                logger.warning("Rabota.ru: Rate limited")
                return None
            if response.status_code != 200:
                logger.error(f"Rabota.ru request failed: {response.status_code} {response.text}")
                return None
            return response.json()
        except Exception as e:
            logger.error(f"Rabota.ru network error: {e}")
            return None

    def search(self, query: "SearchQuery") -> List["Vacancy"]:
        if not self.access_token:
            logger.warning("Rabota.ru: No access token, skipping search")
            return []

        text = query.text or "go разработчик"
        area = query.areas[0] if query.areas else "2"  # SPb region
        max_pages = query.max_pages or 1
        per_page = min(query.page_size or 20, 100)

        vacancies: List["Vacancy"] = []
        for page in range(max_pages):
            params = {
                "text": text,
                "area": area,
                "page": page,
                "per_page": per_page,
            }
            url = f"{API_BASE}/vacancies?{urlencode(params)}"
            try:
                payload = self._request(url)
                if not payload:
                    break

                for item in payload.get("items", []):
                    v = self._normalize_item(item)
                    if v:
                        vacancies.append(v)

                if page + 1 >= payload.get("pages", 0):
                    break
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"Rabota.ru search error: {e}")
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
            logger.warning(f"Failed to fetch Rabota.ru details for {vacancy.id}: {e}")
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

        work_format_str = (item.get("schedule") or {}).get("title", "").lower()
        if "удален" in work_format_str or "remote" in work_format_str:
            work_format = WorkFormat.REMOTE
        elif "гибр" in work_format_str or "hybrid" in work_format_str:
            work_format = WorkFormat.HYBRID
        else:
            work_format = WorkFormat.OFFICE

        area = item.get("area", {}).get("name", "")

        vac = target or Vacancy(
            id=str(item.get("id")),
            title=item.get("name") or "",
            employer=item.get("employer", {}).get("name"),
            source_url=item.get("alternate_url") or "",
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
        vac.requirements = item.get("experience", {}).get("name")
        vac.technology_stack = [s.get("name") for s in item.get("key_skills", []) if s.get("name")]

        return vac

    def _map_currency(self, cur: str) -> "Currency":
        from ..core.enums import Currency
        if not cur:
            return Currency.UNKNOWN
        mapping = {"RUB": Currency.RUB, "RUR": Currency.RUB, "USD": Currency.USD, "EUR": Currency.EUR}
        return mapping.get(cur.upper(), Currency.UNKNOWN)

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source": self.source_name,
            "available": bool(self.access_token),
            "limitations": ["Requires Rabota.ru API token"] if not self.access_token else [],
        }