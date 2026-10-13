from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ..core.enums import Currency, DmsStatus, WorkFormat
from ..core.models import BenefitsInfo, SalaryInfo, Vacancy
from .hh_scraper import HHWebScraper


class HHAdapter:
    """Adapter for hh.ru data sources (fixtures, public URLs, live scraping)."""

    def __init__(self, scraper: HHWebScraper | None = None) -> None:
        self.scraper = scraper or HHWebScraper()

    def from_public_urls(self, urls: List[str]) -> List[Vacancy]:
        return []

    def from_fixture(self, path: Path) -> List[Vacancy]:
        """Load vacancies from a JSON fixture file (full field support)."""
        data = json.loads(path.read_text(encoding='utf-8'))
        items = data.get('items', []) if isinstance(data, dict) else data
        vacancies: List[Vacancy] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            sal = it.get('salary') or {}
            vacancies.append(
                Vacancy(
                    id=str(it.get('id') or it.get('url') or ''),
                    title=it.get('name') or it.get('title') or '',
                    employer=it.get('employer'),
                    source_url=it.get('url') or it.get('alternate_url') or '',
                    source_name=it.get('source_name') or 'fixture',
                    location=it.get('area') or it.get('location'),
                    work_format=self._map_format(it.get('work_format')),
                    salary=SalaryInfo(
                        from_amount=sal.get('from'),
                        to_amount=sal.get('to'),
                        currency=self._map_currency(sal.get('currency')),
                    ),
                    benefits=BenefitsInfo(dms_status=self._map_dms(it.get('dms'))),
                    description=it.get('description'),
                    technology_stack=it.get('technology_stack') or [],
                )
            )
        return vacancies

    @staticmethod
    def _map_format(value: str | None) -> WorkFormat:
        mapping = {
            "remote": WorkFormat.REMOTE,
            "hybrid": WorkFormat.HYBRID,
            "office": WorkFormat.OFFICE,
        }
        return mapping.get((value or "").lower(), WorkFormat.UNKNOWN)

    @staticmethod
    def _map_currency(value: str | None) -> Currency:
        mapping = {"RUB": Currency.RUB, "USD": Currency.USD, "EUR": Currency.EUR}
        return mapping.get((value or "").upper(), Currency.UNKNOWN)

    @staticmethod
    def _map_dms(value: str | None) -> DmsStatus:
        mapping = {
            "confirmed": DmsStatus.CONFIRMED,
            "not_mentioned": DmsStatus.NOT_MENTIONED,
        }
        return mapping.get((value or "").lower(), DmsStatus.UNKNOWN)

    def scrape(
        self,
        text: str,
        area_id: str = "2",
        max_pages: int = 1,
        per_page: int = 20,
        extra_params: dict | None = None,
        enrich: bool = True,
        enrich_limit: int = 30,
    ) -> List[Vacancy]:
        """Scrape vacancies from public hh.ru pages.

        Args:
            text: Search query (e.g. "Go разработчик").
            area_id: hh.ru area ID (2 = Saint Petersburg, 113 = Russia).
            max_pages: Number of pages to scrape.
            per_page: Results per page (max 50).
            extra_params: Additional filters (schedule=remote, etc.).
            enrich: If True, fetch detail pages for each vacancy.
            enrich_limit: Max vacancies to enrich (rate limit safety).

        Returns:
            List of Vacancy objects.
        """
        if enrich:
            return self.scraper.search_and_enrich(
                text=text,
                area_id=area_id,
                max_pages=max_pages,
                per_page=per_page,
                extra_params=extra_params,
                enrich_limit=enrich_limit,
            )
        return self.scraper.search(
            text=text,
            area_id=area_id,
            max_pages=max_pages,
            per_page=per_page,
            extra_params=extra_params,
        )
