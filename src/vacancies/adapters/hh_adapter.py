from __future__ import annotations

from pathlib import Path
from typing import List

from ..core.models import Vacancy
from .hh_scraper import HHWebScraper


class HHAdapter:
    """Adapter for hh.ru data sources (fixtures, public URLs, live scraping)."""

    def __init__(self, scraper: HHWebScraper | None = None) -> None:
        self.scraper = scraper or HHWebScraper()

    def from_public_urls(self, urls: List[str]) -> List[Vacancy]:
        return []

    def from_fixture(self, path: Path) -> List[Vacancy]:
        import json

        data = json.loads(path.read_text(encoding='utf-8'))
        items = data.get('items', []) if isinstance(data, dict) else data
        vacancies: List[Vacancy] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            vacancies.append(
                Vacancy(
                    id=str(it.get('id') or it.get('url') or ''),
                    title=it.get('name') or it.get('title') or '',
                    employer=it.get('employer'),
                    source_url=it.get('url') or it.get('alternate_url') or '',
                )
            )
        return vacancies

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
