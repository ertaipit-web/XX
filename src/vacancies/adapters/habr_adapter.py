from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..core.models import SearchQuery, Vacancy
from .base import SourceAdapter

logger = logging.getLogger(__name__)


class HabrAdapter(SourceAdapter):
    """Adapter for Habr Career (mock implementation for testing).

    In production, this would use the Habr Career API.
    """

    @property
    def source_name(self) -> str:
        return "habr.com"

    def __init__(self) -> None:
        pass

    def search(self, query: SearchQuery) -> List[Vacancy]:
        logger.info("Habr adapter: mock search for %s", query.text)
        # Return empty list for now - real implementation would use Habr API
        return []

    def fetch_details(self, vacancy: Vacancy) -> Vacancy:
        return vacancy

    def get_source_status(self) -> Dict[str, Any]:
        return {
            "source": self.source_name,
            "available": False,
            "limitations": ["Requires Habr Career API access - mock implementation"],
        }