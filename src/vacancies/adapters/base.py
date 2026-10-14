from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.models import Vacancy, SearchQuery


class SourceAdapter(ABC):
    """Base interface for vacancy source adapters."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this source (e.g., 'hh.ru', 'habr')."""
        pass

    @abstractmethod
    def search(self, query: SearchQuery) -> List[Vacancy]:
        """Search for vacancies using the given query."""
        pass

    @abstractmethod
    def fetch_details(self, vacancy: Vacancy) -> Vacancy:
        """Fetch and enrich full vacancy details."""
        pass

    def load_fixture(self, path: Path) -> List[Vacancy]:
        """Load vacancies from a JSON fixture file (for testing)."""
        import json
        data = json.loads(path.read_text(encoding='utf-8'))
        items = data.get('items', []) if isinstance(data, dict) else data
        vacancies: List[Vacancy] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            v = Vacancy(
                id=str(it.get('id') or it.get('url') or ''),
                title=it.get('name') or it.get('title') or '',
                employer=it.get('employer'),
                source_url=it.get('url') or it.get('alternate_url') or '',
                source_name=it.get('source_name') or self.source_name,
                location=it.get('area') or it.get('location'),
                description=it.get('description'),
            )
            if it.get('salary'):
                sal = it.get('salary')
                v.salary = self._parse_salary(sal)
            if it.get('work_format'):
                v.work_format = self._parse_work_format(it.get('work_format'))
            if it.get('dms'):
                v.benefits.dms_status = self._parse_dms(it.get('dms'))
            vacancies.append(v)
        return vacancies

    def _parse_salary(self, sal: Dict[str, Any]) -> Any:
        from ..core.enums import Currency, TaxType
        from ..core.models import SalaryInfo
        return SalaryInfo(
            from_amount=sal.get('from'),
            to_amount=sal.get('to'),
            currency=self._map_currency(sal.get('currency')),
            tax_type=self._map_tax(sal.get('tax_type')),
            period=sal.get('period', 'month'),
        )

    def _map_currency(self, cur: str | None) -> Any:
        from ..core.enums import Currency
        if not cur:
            return Currency.UNKNOWN
        mapping = {"RUB": Currency.RUB, "RUR": Currency.RUB, "USD": Currency.USD, "EUR": Currency.EUR}
        return mapping.get(cur.upper(), Currency.UNKNOWN)

    def _map_tax(self, tax: str | None) -> Any:
        from ..core.enums import TaxType
        if not tax:
            return TaxType.UNKNOWN
        t = tax.lower()
        if "net" in t or "на руки" in t:
            return TaxType.NET
        if "gross" in t or "до вычета" in t:
            return TaxType.GROSS
        return TaxType.UNKNOWN

    def _parse_work_format(self, fmt: str) -> Any:
        from ..core.enums import WorkFormat
        mapping = {"remote": WorkFormat.REMOTE, "hybrid": WorkFormat.HYBRID, "office": WorkFormat.OFFICE}
        return mapping.get((fmt or "").lower(), WorkFormat.UNKNOWN)

    def _parse_dms(self, dms: str) -> Any:
        from ..core.enums import DmsStatus
        mapping = {"confirmed": DmsStatus.CONFIRMED, "not_mentioned": DmsStatus.NOT_MENTIONED}
        return mapping.get((dms or "").lower(), DmsStatus.UNKNOWN)

    def get_source_status(self) -> Dict[str, Any]:
        """Return source health/status information."""
        return {
            "source": self.source_name,
            "available": True,
            "limitations": [],
        }