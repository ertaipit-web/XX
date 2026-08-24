import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))

from hh_vacancies import (
    DEFAULT_PROMPT_TERMS,
    build_query,
    build_public_search_url,
    collect_pages,
    find_area_id,
    is_prompt_engineering_role,
    normalize_vacancy,
)


class HhVacanciesTests(unittest.TestCase):
    def test_build_query_encodes_text_and_filters(self):
        url = build_query("Python developer", "2", 0, 10, {"experience": "between1And3"})
        self.assertIn("text=Python+developer", url)
        self.assertIn("area=2", url)
        self.assertIn("experience=between1And3", url)

    def test_build_public_search_url_supports_no_token_mode(self):
        url = build_public_search_url("vibe coder", "113", {"schedule": "remote"})
        self.assertIn("https://hh.ru/search/vacancy?", url)
        self.assertIn("area=113", url)
        self.assertIn("text=vibe+coder", url)
        self.assertIn("schedule=remote", url)

    def test_find_area_id_recurses(self):
        areas = [{"id": "1", "name": "Россия", "areas": [{"id": "2", "name": "Санкт-Петербург", "areas": []}]}]
        self.assertEqual(find_area_id(areas), "2")

    def test_normalize_vacancy_keeps_analysis_fields(self):
        item = {
            "id": "42",
            "name": "Python developer",
            "alternate_url": "https://hh.ru/vacancy/42",
            "employer": {"name": "Example"},
            "area": {"name": "Санкт-Петербург"},
            "salary": {"from": 100000, "to": None, "currency": "RUR"},
            "experience": {"name": "1-3 года"},
            "key_skills": [{"name": "Python"}, {"name": "SQL"}],
        }
        normalized = normalize_vacancy(item)
        self.assertEqual(normalized["employer"], "Example")
        self.assertEqual(normalized["salary"]["from"], 100000)
        self.assertEqual(normalized["key_skills"], ["Python", "SQL"])

    def test_collect_pages_deduplicates_items(self):
        responses = iter([
            {"found": 3, "pages": 2, "items": [{"id": "1", "name": "One"}, {"id": "2", "name": "Two"}]},
            {"found": 3, "pages": 2, "items": [{"id": "2", "name": "Two"}, {"id": "3", "name": "Three"}]},
        ])

        def transport(url, headers, timeout):
            return next(responses)

        items, total, pages = collect_pages("Python", "2", 2, 2, {}, transport=transport, delay=0)
        self.assertEqual([item["id"] for item in items], ["1", "2", "3"])
        self.assertEqual((total, pages), (3, 2))

    def test_prompt_role_filter_accepts_russian_prompt_role(self):
        accepted, reason = is_prompt_engineering_role({"name": "Инженер по промптам", "description": "Работа с LLM"})
        self.assertTrue(accepted)
        self.assertIsNone(reason)

    def test_prompt_role_filter_accepts_vibe_role(self):
        accepted, reason = is_prompt_engineering_role({"name": "AI Builder / Vibe Coder", "description": "Создание AI-продуктов"})
        self.assertTrue(accepted)
        self.assertIsNone(reason)

    def test_prompt_role_filter_excludes_traditional_ml_developer(self):
        accepted, reason = is_prompt_engineering_role({"name": "Machine Learning developer", "description": "Prompt engineering"})
        self.assertFalse(accepted)
        self.assertIn("традиционную", reason)

    def test_default_terms_include_prompt_and_vibe_variants(self):
        for term in ("prompt engineer", "vibecoder", "vibe coder", "вайбкодер", "вайб-кодер"):
            self.assertIn(term, DEFAULT_PROMPT_TERMS)


if __name__ == "__main__":
    unittest.main()
