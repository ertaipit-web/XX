from __future__ import annotations

from pathlib import Path
from typing import List

from ..core.models import Vacancy


class HHAdapter:
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
