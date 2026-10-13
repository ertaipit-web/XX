"""Web scraper for public hh.ru pages (no API token required).

This module parses the public HTML pages of hh.ru to extract vacancy data.
It is intended for personal research use only. Respect hh.ru terms of service
and apply reasonable delays between requests.

Uses curl_cffi to emulate real Chrome browser TLS/JA3 fingerprint,
which bypasses most anti-bot protections (Cloudflare, Akamai, etc.).
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from ..core.enums import Currency, DmsStatus, TaxType, WorkFormat
from ..core.models import BenefitsInfo, SalaryInfo, Vacancy

logger = logging.getLogger(__name__)

# Realistic browser headers matching Chrome 126 on Windows 10
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Connection": "keep-alive",
}

# Browser impersonation target for curl_cffi (emulates Chrome TLS fingerprint)
IMPERSONATE = "chrome124"

SEARCH_BASE = "https://hh.ru/search/vacancy"
VACANCY_BASE = "https://hh.ru/vacancy"


class HHScraperError(RuntimeError):
    """Raised when scraping fails or hh.ru blocks the request."""


class HHWebScraper:
    """Scrapes vacancy data from public hh.ru HTML pages.

    Uses curl_cffi to emulate a real Chrome browser's TLS fingerprint (JA3/JA4),
    which bypasses Cloudflare, Akamai, and similar anti-bot systems.
    """

    def __init__(self, delay: float = 8.0, timeout: float = 30.0) -> None:
        self.delay = delay
        self.timeout = timeout
        self._session = None
        self._session_initialized = False

    def _get_curl_session(self) -> Any:
        """Get or create a curl_cffi session with Chrome TLS fingerprint."""
        if self._session is None:
            self._session = curl_requests.Session(impersonate=IMPERSONATE)
        return self._session

    def _init_session(self) -> None:
        """Warm up session by fetching hh.ru landing page to get cookies."""
        if self._session_initialized:
            return
        try:
            session = self._get_curl_session()
            resp = session.get("https://hh.ru", timeout=15)
            if resp.status_code == 200:
                logger.info("Session warmed up with hh.ru cookies")
        except Exception as e:
            logger.warning("Failed to warm up session: %s", e)
        self._session_initialized = True

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(
        self,
        text: str,
        area_id: str = "2",
        max_pages: int = 1,
        per_page: int = 20,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> List[Vacancy]:
        """Search vacancies on hh.ru public search page.

        Args:
            text: Search query (e.g. "Go разработчик").
            area_id: Area ID (2 = Saint Petersburg, 113 = Russia).
            max_pages: Maximum pages to scrape.
            per_page: Results per page (max 50 on hh.ru).
            extra_params: Additional query params (schedule, experience, etc.)

        Returns:
            List of Vacancy objects with basic fields populated.
        """
        self._init_session()
        vacancies: List[Vacancy] = []
        seen_urls: set = set()

        for page in range(max_pages):
            params: Dict[str, str] = {
                "area": area_id,
                "text": text,
                "page": str(page),
                "per_page": str(min(per_page, 50)),
            }
            if extra_params:
                params.update(extra_params)

            url = f"{SEARCH_BASE}?{urlencode(params)}"
            logger.info("Scraping page %d: %s", page + 1, url)

            html = self._fetch(url)
            items = self._parse_search_page(html)

            for item in items:
                if item.source_url and item.source_url not in seen_urls:
                    seen_urls.add(item.source_url)
                    vacancies.append(item)

            # Check if there are more pages
            total_pages = self._extract_total_pages(html)
            if page + 1 >= total_pages:
                break

            if page + 1 < max_pages:
                time.sleep(self.delay)

        return vacancies

    def fetch_detail(self, vacancy: Vacancy) -> Vacancy:
        """Fetch and parse a vacancy detail page to enrich fields.

        Adds: description, requirements, skills, work_format, DMS info,
        precise salary, publication date.
        """
        url = vacancy.source_url
        if not url:
            return vacancy

        logger.info("Fetching detail: %s", url)
        html = self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        # Extract embedded JSON (hh.ru stores vacancy data in a script tag)
        embedded = self._extract_embedded_json(soup)
        if embedded:
            self._fill_from_embedded(vacancy, embedded)

        # Always also parse DOM (embedded JSON-LD may miss salary, skills, etc.)
        self._fill_from_dom(vacancy, soup)

        # DMS detection from full text
        self._detect_dms(vacancy, html)

        vacancy.checked_at = datetime.now(timezone.utc)
        return vacancy

    def search_and_enrich(
        self,
        text: str,
        area_id: str = "2",
        max_pages: int = 1,
        per_page: int = 20,
        extra_params: Optional[Dict[str, str]] = None,
        enrich_limit: int = 30,
    ) -> List[Vacancy]:
        """Search and then enrich each vacancy with detail page data.

        Args:
            enrich_limit: Max vacancies to enrich (to avoid too many requests).

        Returns:
            Enriched list of Vacancy objects.
        """
        vacancies = self.search(text, area_id, max_pages, per_page, extra_params)

        for i, v in enumerate(vacancies[:enrich_limit]):
            try:
                self.fetch_detail(v)
            except HHScraperError as e:
                logger.warning("Failed to enrich vacancy %s: %s", v.id, e)
            if i < min(enrich_limit, len(vacancies)) - 1:
                time.sleep(self.delay)

        return vacancies

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> str:
        """Fetch a URL with realistic browser emulation."""
        # Random delay to mimic human behavior (between 2s and delay)
        human_delay = random.uniform(2.0, self.delay)
        time.sleep(human_delay)

        session = self._get_curl_session()

        try:
            resp = session.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except Exception as e:
            raise HHScraperError(f"Network error fetching {url}: {e}") from e

        if resp.status_code == 403:
            snippet = resp.text[:500] if resp.text else "(empty)"
            raise HHScraperError(
                f"hh.ru returned 403 (blocked). "
                f"IP may be blocked. Response snippet: {snippet!r}"
            )
        if resp.status_code == 429:
            raise HHScraperError(f"hh.ru rate limit hit (429). URL: {url}")
        if resp.status_code != 200:
            raise HHScraperError(f"hh.ru returned HTTP {resp.status_code}. URL: {url}")

        html = resp.text

        # Detect anti-bot pages by checking title and first 2000 chars only
        # (not the full HTML — hh.ru includes "captcha" string in Sentry config)
        head = html[:2000].lower()
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).lower() if title_match else ""

        bot_title_indicators = [
            "captcha", "robot check", "access denied",
            "are you a human", "checking your browser",
            "just a moment", "attention required",
        ]
        for indicator in bot_title_indicators:
            if indicator in title or indicator in head[:500]:
                diag_path = Path("data/hh/scrape-diag.html")
                diag_path.parent.mkdir(parents=True, exist_ok=True)
                diag_path.write_text(html, encoding="utf-8")
                logger.error("Anti-bot detected (%s). Diagnostics saved to %s", indicator, diag_path)
                raise HHScraperError(
                    f"hh.ru anti-bot detected ({indicator}). "
                    f"Diagnostics saved to data/hh/scrape-diag.html "
                    f"Try from a different IP or increase delay."
                )

        return html

    def _parse_search_page(self, html: str) -> List[Vacancy]:
        """Parse vacancy cards from a search results page."""
        soup = BeautifulSoup(html, 'lxml')
        vacancies: List[Vacancy] = []

        # Modern hh.ru layout: vacancy cards have class "vacancy-card--*"
        cards = soup.select('div[class*="vacancy-card--"]')

        for card in cards:
            v = self._parse_search_item(card)
            if v and v.title:
                vacancies.append(v)

        return vacancies

        for item in items:
            v = self._parse_search_item(item)
            if v:
                vacancies.append(v)

        return vacancies

    def _parse_search_item(self, card) -> Optional[Vacancy]:
        """Parse a single search result card (modern hh.ru layout)."""
        # Title link
        title_el = card.select_one('[data-qa="serp-item__title"], [data-qa="vacancy-serp__vacancy"]')
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get('href', '')
        if href and not href.startswith('http'):
            href = f"https://hh.ru{href}"

        # Vacancy ID from URL
        vac_id = ''
        id_match = re.search(r'/vacancy/(\d+)', href)
        if id_match:
            vac_id = id_match.group(1)

        # Employer
        emp_el = card.select_one('[data-qa="vacancy-serp__vacancy-employer"]')
        employer = emp_el.get_text(strip=True) if emp_el else None

        # Location
        loc_el = card.select_one('[data-qa="vacancy-serp__vacancy-address"]')
        location = loc_el.get_text(strip=True) if loc_el else None

        # Work format from labels
        work_format = WorkFormat.UNKNOWN
        if card.select_one('[data-qa="vacancy-label-work-schedule-remote"]'):
            work_format = WorkFormat.REMOTE
        elif card.select_one('[data-qa="vacancy-label-work-schedule-remotePossible"]'):
            work_format = WorkFormat.HYBRID

        # Salary — hh.ru may not show it in search list for anonymous users
        salary = SalaryInfo()
        sal_el = card.select_one('[data-qa="vacancy-serp__vacancy_compensation"]')
        if sal_el:
            salary = self._parse_salary(sal_el.get_text(strip=True))

        return Vacancy(
            id=vac_id,
            title=title,
            employer=employer,
            source_url=href,
            source_name='hh.ru (scraped)',
            location=location,
            work_format=work_format,
            salary=salary,
        )

    def _parse_link_item(self, link) -> Optional[Vacancy]:
        """Parse a bare link to a vacancy (fallback mode)."""
        href = link.get("href", "")
        if "/vacancy/" not in href:
            return None
        if not href.startswith("http"):
            href = f"https://hh.ru{href}"

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        vac_id = ""
        id_match = re.search(r"/vacancy/(\d+)", href)
        if id_match:
            vac_id = id_match.group(1)

        return Vacancy(
            id=vac_id,
            title=title,
            source_url=href,
            source_name="hh.ru (scraped)",
        )

    def _extract_salary_text(self, item) -> Optional[str]:
        """Extract salary text from a search card."""
        for selector in [
            "[data-qa='vacancy-serp__vacancy_compensation']",
            ".vacancy-serp-item__compensation",
            ".g-page-snippet-description__salary",
            ".vacancy-serp-item__salary",
        ]:
            el = item.select_one(selector)
            if el:
                return el.get_text(strip=True)
        # Fallback: look for text matching salary pattern
        text = item.get_text()
        match = re.search(r"[\d\s]+[–\-—][\s\d]+.*?(?:₽|руб|USD|EUR|\$|€)", text, re.IGNORECASE)
        if match:
            return match.group(0)
        return None

    def _extract_employer(self, item) -> Optional[str]:
        """Extract employer name from a search card."""
        for selector in [
            "[data-qa='vacancy-serp__vacancy_employer']",
            ".vacancy-serp-item__organization-name",
            ".g-page-snippet-description__org",
            ".vacancy-serp-item__employer",
        ]:
            el = item.select_one(selector)
            if el:
                return el.get_text(strip=True)
        return None

    def _extract_location(self, item) -> Optional[str]:
        """Extract location from a search card."""
        for selector in [
            "[data-qa='vacancy-serp__vacancy_address']",
            ".vacancy-serp-item__area",
            ".g-page-snippet-description__area",
            ".vacancy-serp-item__address",
        ]:
            el = item.select_one(selector)
            if el:
                return el.get_text(strip=True)
        return None

    def _extract_total_pages(self, html: str) -> int:
        """Extract total number of pages from search results."""
        soup = BeautifulSoup(html, "lxml")
        # Look for pagination info
        el = soup.select_one("[data-qa='pager'] [data-qa='pager-item']:last-child")
        if el:
            try:
                return int(el.get_text(strip=True))
            except ValueError:
                pass
        # Fallback: look for "found N vacancies" text
        text = soup.get_text()
        match = re.search(r"(\d+)\s+ваканси", text, re.IGNORECASE)
        if match:
            total = int(match.group(1))
            return max(1, (total + 19) // 20)  # Assume 20 per page
        return 1

    def _extract_embedded_json(self, soup) -> Optional[Dict[str, Any]]:
        """Try to extract vacancy data from embedded JSON in script tags."""
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") == "JobPosting":
                    return data
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _fill_from_embedded(self, vacancy: Vacancy, data: Dict[str, Any]) -> None:
        """Fill vacancy fields from JSON-LD JobPosting schema."""
        vacancy.description = data.get("description")
        vacancy.title = data.get("title") or vacancy.title

        org = data.get("hiringOrganization") or {}
        vacancy.employer = org.get("name") or vacancy.employer

        # Salary
        base_salary = data.get("baseSalary") or {}
        if isinstance(base_salary, dict):
            value = base_salary.get("value") or {}
            if isinstance(value, dict):
                vacancy.salary = SalaryInfo(
                    from_amount=value.get("minValue"),
                    to_amount=value.get("maxValue"),
                    currency=self._map_currency(value.get("currency", "")),
                    raw_text=str(base_salary),
                )

        # Employment type
        emp_type = data.get("employmentType", "")
        vacancy.work_format = self._parse_work_format(emp_type)

    def _fill_from_dom(self, vacancy: Vacancy, soup) -> None:
        """Fill vacancy fields from DOM elements (fallback)."""
        # Description
        desc_el = (
            soup.select_one("[data-qa='vacancy-description']")
            or soup.select_one(".vacancy-raw")
            or soup.select_one(".vacancy-description")
        )
        if desc_el:
            vacancy.description = desc_el.get_text(separator="\n", strip=True)

        # Skills
        skills = soup.select("[data-qa='skill'], .vacancy-skill, .g-card-marker")
        if skills:
            vacancy.technology_stack = [s.get_text(strip=True) for s in skills if s.get_text(strip=True)]

        # Employer
        emp_el = (
            soup.select_one("[data-qa='vacancy-company-name']")
            or soup.select_one(".vacancy-company-name")
        )
        if emp_el and not vacancy.employer:
            vacancy.employer = emp_el.get_text(strip=True)

        # Work format / schedule
        for el in soup.select("[data-qa='vacancy-employment'], .vacancy-block__line"):
            text = el.get_text(strip=True).lower()
            fmt = self._parse_work_format(text)
            if fmt != WorkFormat.UNKNOWN:
                vacancy.work_format = fmt
                break

        # Salary on detail page
        sal_el = (
            soup.select_one("[data-qa='vacancy-salary']")
            or soup.select_one(".vacancy-salary")
        )
        if sal_el and not vacancy.salary.from_amount:
            salary_text = sal_el.get_text(strip=True)
            vacancy.salary = self._parse_salary(salary_text)

    def _detect_dms(self, vacancy: Vacancy, full_html: str) -> None:
        """Detect DMS (voluntary medical insurance) mention in vacancy text."""
        text = (vacancy.description or "").lower() + " " + full_html.lower()

        dms_patterns = [
            r"\bдмс\b",
            r"добровольн\w+\s+медицинск\w+\s+страхован",
            r"корпоративн\w+\s+медицинск",
            r"medical\s+insurance",
            r"voluntary\s+medical",
        ]
        for pattern in dms_patterns:
            if re.search(pattern, text):
                vacancy.benefits.dms_status = DmsStatus.CONFIRMED
                vacancy.benefits.dms_notes = "Упоминание ДМС найдено в тексте вакансии"
                return

        # If no mention found, mark as not_mentioned (not "unknown")
        if vacancy.benefits.dms_status == DmsStatus.UNKNOWN:
            vacancy.benefits.dms_status = DmsStatus.NOT_MENTIONED

    # ------------------------------------------------------------------
    # Utility parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_salary(text: Optional[str]) -> SalaryInfo:
        """Parse salary from Russian text like 'от 150 000 до 200 000 ₽'."""
        if not text:
            return SalaryInfo()

        # Normalize spaces
        normalized = re.sub(r"[\s\u00a0]+", " ", text).strip()

        # Extract numbers (hh.ru may not have spaces between "от" and number)
        # Use [р₽] to match both Cyrillic 'р' and Latin '₽' symbols
        from_match = re.search(r"от\s*([\d\s]+?)(?:до|–|—|[р₽]|$)", normalized, re.IGNORECASE)
        to_match = re.search(r"до\s*([\d\s]+?)(?:[р₽]|$)", normalized, re.IGNORECASE)
        range_match = re.search(r"([\d\s]+?)\s*[–\-—]\s*([\d\s]+?)(?:[р₽]|$)", normalized)

        from_amount = None
        to_amount = None

        if from_match:
            from_amount = float(from_match.group(1).replace(" ", ""))
        if to_match:
            to_amount = float(to_match.group(1).replace(" ", ""))
        if range_match and from_amount is None:
            from_amount = float(range_match.group(1).replace(" ", ""))
            to_amount = float(range_match.group(2).replace(" ", ""))

        # Currency detection
        lower = normalized.lower()
        currency = Currency.UNKNOWN
        if any(k in lower for k in ("₽", "руб")):
            currency = Currency.RUB
        elif any(k in lower for k in ("$", "usd", "доллар")):
            currency = Currency.USD
        elif any(k in lower for k in ("€", "eur", "евро")):
            currency = Currency.EUR

        # Tax type
        tax_type = TaxType.UNKNOWN
        if "net" in lower or "на руки" in lower:
            tax_type = TaxType.NET
        elif "gross" in lower or "до вычета" in lower:
            tax_type = TaxType.GROSS

        return SalaryInfo(
            from_amount=from_amount,
            to_amount=to_amount,
            currency=currency,
            tax_type=tax_type,
            raw_text=normalized,
        )

    @staticmethod
    def _parse_work_format(text: str) -> WorkFormat:
        """Determine work format from text."""
        lower = text.lower()
        if any(k in lower for k in ("удалён", "удаленн", "remote", "дистанцион")):
            return WorkFormat.REMOTE
        if any(k in lower for k in ("гибр", "hybrid", "гибридн")):
            return WorkFormat.HYBRID
        if any(k in lower for k in ("офис", "office", "полный день")):
            return WorkFormat.OFFICE
        return WorkFormat.UNKNOWN

    @staticmethod
    def _map_currency(raw: str) -> Currency:
        """Map currency string to enum."""
        upper = raw.upper()
        if upper in ("RUB", "RUR"):
            return Currency.RUB
        if upper == "USD":
            return Currency.USD
        if upper == "EUR":
            return Currency.EUR
        return Currency.UNKNOWN
