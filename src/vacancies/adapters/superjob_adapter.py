"""SuperJob API adapter for vacancy search."""

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

# SuperJob API documentation: https://api.superjob.ru/
API_BASE = "https://api.superjob.ru/2.0"
DEFAULT_USER_AGENT = "vacancy-research-agent/1.0"


class SuperJobAdapter(SourceAdapter):
    """Adapter for SuperJob.ru official API."""

    @property
    def source_name(self) -> str:
        return "superjob.ru"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, access_token: Optional[str] = None) -> None:
        self.client_id = client_id or os.environ.get("SUPERJOB_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("SUPERJOB_CLIENT_SECRET")
        self.access_token = access_token or os.environ.get("SUPERJOB_ACCESS_TOKEN")
        self._token_expires_at: Optional[float] = None

    def _make_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _ensure_token(self) -> bool:
        """Ensure we have a valid access token."""
        if self.access_token and self._token_expires_at and time.time() < self._token_expires_at - 60:
            return True

        if not self.client_id or not self.client_secret:
            logger.warning("SuperJob: No client credentials for OAuth")
            return False

        # Client credentials flow
        import requests
        try:
            response = requests.post(
                f"{API_BASE}/oauth2/password/",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
                headers={"User-Agent": DEFAULT_USER_AGENT},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in
                return True
            else:
                logger.error(f"SuperJob OAuth failed: {response.status_code} {response.text}")
                return False
        except Exception as e:
            logger.error(f"SuperJob OAuth error: {e}")
            return False

    def search(self, query: "SearchQuery") -> List["Vacancy"]:
        """Search vacancies via SuperJob API."""
        if not self._ensure_token():
            logger.warning("SuperJob: No valid access token, skipping search")
            return []

        import requests
        text = query.text or "go разработчик"
        area = query.areas[0] if query.areas else "2"  # Default to SPb
        max_pages = query.max_pages or 1
        per_page = min(query.page_size or 20, 100)

        vacancies: List["Vacancy"] = []
        for page in range(max_pages):
            params = {
                "keyword": text,
                "t": area,
                "page": page,
                "count": per_page,
            }
            url = f"{API_BASE}/vacancies/?{urlencode(params)}"
            try:
                headers = self._make_headers()
                import requests
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code == 401:
                    # Token expired, try refresh once
                    if self._ensure_token():
                        headers = self._make_headers()
                        response = requests.get(url, headers=headers, timeout=20)
                    else:
                        break
                if response.status_code != 200:
                    logger.error(f"SuperJob search failed: {response.status_code} {response.text}")
                    break

                payload = response.json()
                for item in payload.get("objects", []):
                    v = self._normalize_item(item)
                    if v:
                        vacancies.append(v)

                if not payload.get("more", False):
                    break
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"SuperJob search error: {e}")
                break

        return vacancies

    def fetch_details(self, vacancy: "Vacancy") -> "Vacancy":
        """Fetch full vacancy details."""
        if not vacancy.id or not self._ensure_token():
            return vacancy

        import requests
        try:
            url = f"{API_BASE}/vacancies/{vacancy.id}/"
            headers = self._make_headers()
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                data = response.json()
                self._normalize_item(data, target=vacancy)
        except Exception as e:
            logger.warning(f"Failed to fetch SuperJob details for {vacancy.id}: {e}")
        return vacancy

    def _normalize_item(self, item: Dict[str, Any], target: Optional["Vacancy"] = None) -> Optional["Vacancy"]:
        from ..core.enums import Currency, DmsStatus, TaxType, WorkFormat
        from ..core.models import BenefitsInfo, SalaryInfo, Vacancy

        payment = item.get("payment_from") or item.get("payment_to")
        if payment is None:
            return None

        salary_from = item.get("payment_from")
        salary_to = item.get("payment_to")
        currency = item.get("currency", "rub")

        work_format_str = (item.get("type_of_work", {}).get("title") or "").lower()
        if "удален" in work_format_str or "remote" in work_format_str:
            work_format = WorkFormat.REMOTE
        elif "частичн" in work_format_str or "гибрид" in work_format_str or "hybrid" in work_format_str:
            work_format = WorkFormat.HYBRID
        else:
            work_format = WorkFormat.OFFICE

        town = item.get("town", {}).get("title") or item.get("town", "")

        vac = target or Vacancy(
            id=str(item.get("id")),
            title=item.get("profession") or "",
            employer=item.get("firm_name"),
            source_url=item.get("link") or "",
            source_name=self.source_name,
            location=town,
            published_at=item.get("date_published"),
        )

        if salary_from is not None or salary_to is not None:
            vac.salary = SalaryInfo(
                from_amount=float(salary_from) if salary_from else None,
                to_amount=float(salary_to) if salary_to else None,
                currency=self._map_currency(currency),
                tax_type=TaxType.NET,  # SuperJob usually shows net
                period="month",
            )

        vac.work_format = work_format
        vac.description = item.get("vacancyRichText") or item.get("candidat")
        vac.requirements = item.get("education", {}).get("title")
        vac.technology_stack = [s.get("title") for s in item.get("catalogues", []) if s.get("title")]

        return vac

    def _map_currency(self, cur: str) -> "Currency":
        from ..core.enums import Currency
        if not cur:
            return Currency.UNKNOWN
        mapping = {"rub": Currency.RUB, "uah": Currency.UNKNOWN, "uzs": Currency.UNKNOWN, "kzt": Currency.UNKNOWN}
        return mapping.get(cur.lower(), Currency.UNKNOWN)

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source": self.source_name,
            "available": bool(self.client_id and self.client_secret),
            "limitations": ["Requires SuperJob API credentials (client_id, client_secret)"] if not (self.client_id and self.client_secret) else [],
        }