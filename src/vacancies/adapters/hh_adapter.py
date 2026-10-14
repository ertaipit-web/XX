from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..core.enums import Currency, DmsStatus, TaxType, WorkFormat
from ..core.models import BenefitsInfo, SalaryInfo, Vacancy
from .base import SourceAdapter

logger = logging.getLogger(__name__)

API_BASE = "https://api.hh.ru"
DEFAULT_USER_AGENT = "vacancy-research-agent/1.0"


class HHAdapter(SourceAdapter):
    """Adapter for hh.ru official API and public sources."""

    @property
    def source_name(self) -> str:
        return "hh.ru"

    def __init__(self, access_token: Optional[str] = None) -> None:
        self.access_token = access_token or os.environ.get("HH_ACCESS_TOKEN")

    def _make_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _request(self, url: str) -> Any:
        request = Request(url, headers=self._make_headers(), method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            if error.code == 429:
                raise RuntimeError("hh.ru rate limit reached (HTTP 429); retry later") from error
            if error.code in {401, 403}:
                raise RuntimeError(f"hh.ru authorization denied (HTTP {error.code})") from error
            raise RuntimeError(f"hh.ru request failed (HTTP {error.code})") from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(f"hh.ru network request failed: {error}") from error

    def search(self, query: "SearchQuery") -> List[Vacancy]:
        """Search vacancies via official hh.ru API."""
        if not self.access_token:
            logger.warning("HH_ACCESS_TOKEN not set, falling back to public search")
            return self._public_search(query)

        from ..core.models import SearchQuery
        text = query.text or "go разработчик"
        area_id = query.areas[0] if query.areas else "2"
        max_pages = query.max_pages or 1
        per_page = min(query.page_size or 20, 100)

        vacancies: List[Vacancy] = []
        for page in range(max_pages):
            params = {
                "text": text,
                "area": area_id,
                "page": str(page),
                "per_page": str(per_page),
            }
            url = f"{API_BASE}/vacancies?{urlencode(params)}"
            try:
                payload = self._request(url)
            except RuntimeError as e:
                logger.error("API search failed: %s", e)
                break

            for item in payload.get("items", []):
                v = self._normalize_item(item)
                vacancies.append(v)

            if page + 1 >= int(payload.get("pages", max_pages)):
                break
            time.sleep(0.2)

        return vacancies

    def _public_search(self, query: "SearchQuery") -> List[Vacancy]:
        """Fallback: generate public search URLs for manual research."""
        logger.info("Using public search mode (no API token)")
        # This is a fallback - in real usage, you'd use the scraper
        return []

    def fetch_details(self, vacancy: Vacancy) -> Vacancy:
        """Fetch full vacancy details from hh.ru API."""
        if not vacancy.id or not self.access_token:
            return vacancy

        try:
            url = f"{API_BASE}/vacancies/{vacancy.id}"
            data = self._request(url)
            self._normalize_item(data, target=vacancy)
        except RuntimeError as e:
            logger.warning("Failed to fetch details for %s: %s", vacancy.id, e)
        return vacancy

    def _normalize_item(self, item: Dict[str, Any], target: Optional[Vacancy] = None) -> Vacancy:
        employer = item.get("employer") or {}
        salary = item.get("salary") or {}
        experience = item.get("experience") or {}
        employment = item.get("employment") or {}
        schedule = item.get("schedule") or {}
        area = item.get("area") or {}

        vac = target or Vacancy(
            id=str(item.get("id")),
            title=item.get("name") or "",
            employer=employer.get("name"),
            source_url=item.get("alternate_url") or item.get("url") or "",
            source_name=self.source_name,
            location=area.get("name"),
            published_at=item.get("published_at"),
        )

        # Salary
        if salary:
            vac.salary = SalaryInfo(
                from_amount=salary.get("from"),
                to_amount=salary.get("to"),
                currency=self._map_currency(salary.get("currency")),
                tax_type=TaxType.UNKNOWN,  # API doesn't specify
                period="month",
                raw_text=f"{salary.get('from')}-{salary.get('to')} {salary.get('currency')}",
            )

        # Work format
        schedule_name = (schedule.get("name") or "").lower()
        if "удал" in schedule_name or "remote" in schedule_name:
            vac.work_format = WorkFormat.REMOTE
        elif "гибр" in schedule_name or "hybrid" in schedule_name:
            vac.work_format = WorkFormat.HYBRID
        elif "офис" in schedule_name or "office" in schedule_name:
            vac.work_format = WorkFormat.OFFICE
        else:
            vac.work_format = WorkFormat.UNKNOWN

        vac.description = item.get("description")
        vac.requirements = item.get("experience", {}).get("name")
        vac.technology_stack = [s.get("name") for s in item.get("key_skills", []) if s.get("name")]

        return vac

    @staticmethod
    def _map_currency(cur: str | None) -> Currency:
        if not cur:
            return Currency.UNKNOWN
        mapping = {"RUB": Currency.RUB, "RUR": Currency.RUB, "USD": Currency.USD, "EUR": Currency.EUR}
        return mapping.get(cur.upper(), Currency.UNKNOWN)

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source": self.source_name,
            "available": self.access_token is not None,
            "limitations": ["Requires HH_ACCESS_TOKEN for full API access"] if not self.access_token else [],
        }