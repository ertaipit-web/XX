#!/usr/bin/env python3
"""Collect and normalize vacancies from the official HeadHunter API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.hh.ru"
DEFAULT_USER_AGENT = "hh-learning-analyst/1.0"
DEFAULT_PROMPT_TERMS = (
    "prompt engineer",
    "prompt-инженер",
    "промпт-инженер",
    "промт-инженер",
    "prompt инженер",
    "промпт инженер",
    "промт инженер",
    "инженер по промптам",
    "специалист по промптам",
    "prompt engineering",
    "prompt designer",
    "vibecoder",
    "vibe coder",
    "vibe-coder",
    "vibe coding",
    "вайбкодер",
    "вайб кодер",
    "вайб-кодер",
    "вайбкодинг",
    "вайб-кодинг",
    "AI-assisted developer",
)
TRADITIONAL_TITLE_RE = re.compile(
    r"(?:^|[\s/()\-])(?:machine learning|ml|backend|frontend|fullstack|full stack|software|data scientist|devops|qa|\.?net|python|java|php|go|c\+\+|1с|разработчик|программист|программист-исследователь|тестировщик)(?:$|[\s/()\-])",
    re.IGNORECASE,
)
PROMPT_RE = re.compile(
    r"(?:prompt|промпт|промт)[\s-]*(?:engineer|engineering|инженер|инжиниринг|дизайнер|designer|специалист)"
    r"|(?:инженер|специалист)\s+по\s+(?:промптам|промтам)",
    re.IGNORECASE,
)
VIBE_RE = re.compile(r"(?:vibe[\s-]*coder|vibe[\s-]*coding|вайб[\s-]*(?:кодер|кодинг))", re.IGNORECASE)
Transport = Callable[[str, dict[str, str], float], Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_query(text: str, area_id: str, page: int, per_page: int, extra: dict[str, str]) -> str:
    params = {"text": text, "area": area_id, "page": str(page), "per_page": str(per_page)}
    params.update({key: value for key, value in extra.items() if value})
    return f"{API_BASE}/vacancies?{urlencode(params)}"


def build_public_search_url(text: str, area_id: str, extra: dict[str, str]) -> str:
    params = {"area": area_id, "text": text}
    params.update({key: value for key, value in extra.items() if value})
    return f"https://hh.ru/search/vacancy?{urlencode(params)}"


def request_json(url: str, headers: dict[str, str], timeout: float = 20.0) -> Any:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 429:
            raise RuntimeError("hh.ru rate limit reached (HTTP 429); retry later") from error
        if error.code in {401, 403}:
            raise RuntimeError(f"hh.ru authorization denied (HTTP {error.code})") from error
        raise RuntimeError(f"hh.ru request failed (HTTP {error.code})") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"hh.ru network request failed: {error}") from error
    return payload


def make_headers(token: str | None, user_agent: str = DEFAULT_USER_AGENT) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": user_agent}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def find_area_id(areas: list[dict[str, Any]], target: str = "Санкт-Петербург") -> str | None:
    for area in areas:
        if area.get("name") == target:
            return str(area["id"])
        nested = find_area_id(area.get("areas", []), target)
        if nested:
            return nested
    return None


def normalize_vacancy(item: dict[str, Any]) -> dict[str, Any]:
    employer = item.get("employer") or {}
    salary = item.get("salary") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "url": item.get("alternate_url") or item.get("url"),
        "employer": employer.get("name"),
        "area": (item.get("area") or {}).get("name"),
        "salary": {
            "from": salary.get("from"),
            "to": salary.get("to"),
            "currency": salary.get("currency"),
        } if salary else None,
        "experience": (item.get("experience") or {}).get("name"),
        "employment": (item.get("employment") or {}).get("name"),
        "schedule": (item.get("schedule") or {}).get("name"),
        "published_at": item.get("published_at"),
        "description": item.get("description"),
        "key_skills": [skill.get("name") for skill in item.get("key_skills", []) if skill.get("name")],
    }


def is_prompt_engineering_role(vacancy: dict[str, Any]) -> tuple[bool, str | None]:
    title = str(vacancy.get("name") or "")
    description = str(vacancy.get("description") or "")
    if not (PROMPT_RE.search(title + " " + description) or VIBE_RE.search(title + " " + description)):
        return False, "не найден prompt/vibe engineering термин"
    if TRADITIONAL_TITLE_RE.search(title):
        return False, "название указывает на традиционную IT/ML-разработку"
    return True, None


def fetch_vacancy_details(
    items: list[dict[str, Any]],
    headers: dict[str, str],
    transport: Transport = request_json,
    delay: float = 0.2,
) -> list[dict[str, Any]]:
    detailed: list[dict[str, Any]] = []
    for item in items:
        vacancy_id = item.get("id")
        if not vacancy_id:
            continue
        detail = transport(f"{API_BASE}/vacancies/{vacancy_id}", headers, 20.0)
        if not isinstance(detail, dict):
            continue
        detailed.append(normalize_vacancy(detail))
        if delay:
            time.sleep(delay)
    return detailed


def collect_pages(
    text: str,
    area_id: str,
    max_pages: int,
    per_page: int,
    headers: dict[str, str],
    transport: Transport = request_json,
    delay: float = 0.2,
    extra: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], int, int]:
    vacancies: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_found = 0
    pages_read = 0
    for page in range(max_pages):
        url = build_query(text, area_id, page, per_page, extra or {})
        payload = transport(url, headers, 20.0)
        total_found = int(payload.get("found", total_found))
        pages_read += 1
        for item in payload.get("items", []):
            vacancy_id = str(item.get("id", ""))
            if vacancy_id and vacancy_id not in seen_ids:
                seen_ids.add(vacancy_id)
                vacancies.append(normalize_vacancy(item))
        if page + 1 >= int(payload.get("pages", max_pages)):
            break
        if delay:
            time.sleep(delay)
    return vacancies, total_found, pages_read


def collect_terms(
    terms: tuple[str, ...],
    area_id: str,
    max_pages: int,
    per_page: int,
    headers: dict[str, str],
    transport: Transport = request_json,
    delay: float = 0.2,
    extra: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    all_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    found_by_term: dict[str, int] = {}
    pages_read = 0
    for term in terms:
        items, total_found, term_pages = collect_pages(
            term, area_id, max_pages, per_page, headers,
            transport=transport, delay=delay, extra=extra,
        )
        found_by_term[term] = total_found
        pages_read += term_pages
        for item in items:
            vacancy_id = str(item.get("id") or "")
            if vacancy_id and vacancy_id not in seen_ids:
                seen_ids.add(vacancy_id)
                all_items.append(item)
    return all_items, found_by_term, pages_read


def parse_extra(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Extra filter must use key=value: {value}")
        key, filter_value = value.split("=", 1)
        if not key or not filter_value:
            raise ValueError(f"Extra filter must use non-empty key and value: {value}")
        result[key] = filter_value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", action="append", help="Search phrase; repeat to combine terms")
    parser.add_argument("--prompt-terms", action="store_true", help="Use built-in prompt engineering synonyms")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--per-page", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("data/hh/vacancies.json"))
    parser.add_argument("--area-id", help="Use only for an already verified area ID")
    parser.add_argument("--all-russia", action="store_true", help="Search across Russia instead of Санкт-Петербург")
    parser.add_argument("--extra", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--public", action="store_true", help="Output public hh.ru search links without API token")
    args = parser.parse_args()
    terms = tuple(args.text or ())
    if args.prompt_terms:
        terms = tuple(dict.fromkeys((*terms, *DEFAULT_PROMPT_TERMS)))
    if not terms:
        parser.error("provide --text or --prompt-terms")
    if args.max_pages < 1 or args.per_page < 1 or args.per_page > 100:
        parser.error("max-pages must be positive and per-page must be between 1 and 100")
    try:
        extra = parse_extra(args.extra)
    except ValueError as error:
        parser.error(str(error))

    token = os.environ.get("HH_ACCESS_TOKEN")
    headers = make_headers(token)
    if args.all_russia and args.area_id:
        parser.error("use either --all-russia or --area-id, not both")
    area_name = "Россия" if args.all_russia else "Санкт-Петербург"
    area_id = args.area_id
    if args.public and not area_id:
        area_id = "113" if args.all_russia else "2"
    if args.public:
        public_urls = [build_public_search_url(term, area_id, extra) for term in terms]
        result = {
            "mode": "public-web-research",
            "area": area_name,
            "area_id": area_id,
            "queries": list(terms),
            "search_urls": public_urls,
            "limitations": [
                "hh.ru public pages are not a complete API export",
                "vacancy descriptions must be read from public vacancy cards",
                "results and counts can change between requests",
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.output != Path("data/hh/vacancies.json"):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0
    if not area_id:
        areas = request_json(f"{API_BASE}/areas", headers)
        if not isinstance(areas, list):
            raise RuntimeError("hh.ru /areas returned an unexpected JSON shape")
        area_id = find_area_id(areas, area_name)
    if not area_id:
        raise RuntimeError(f"Could not find {area_name} in /areas response")

    first_urls = [build_query(term, area_id, 0, args.per_page, extra) for term in terms]
    print(json.dumps({"area_id": area_id, "requests": first_urls, "max_pages": args.max_pages}, ensure_ascii=False))
    if args.dry_run:
        return 0
    if not token:
        raise RuntimeError("HH_ACCESS_TOKEN is required for collection; use --dry-run to inspect the request")

    items, found_by_term, pages_read = collect_terms(
        terms, area_id, args.max_pages, args.per_page, headers, extra=extra,
    )
    items = fetch_vacancy_details(items, headers)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in items:
        accepted, reason = is_prompt_engineering_role(item)
        if accepted:
            included.append(item)
        else:
            excluded.append({"id": item.get("id"), "name": item.get("name"), "url": item.get("url"), "reason": reason})
    result = {
        "query": list(terms),
        "filters": {"area": area_name, "area_id": area_id, **extra},
        "retrieved_at": utc_now(),
        "source": "https://api.hh.ru/vacancies",
        "pages": pages_read,
        "found_by_term": found_by_term,
        "total_found": sum(found_by_term.values()),
        "items": included,
        "excluded": excluded,
        "warnings": ["Фильтр исключает традиционные IT/ML-роли; проверьте excluded перед анализом"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {len(items)} vacancies to {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
