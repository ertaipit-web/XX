"""Unit tests for HHWebScraper (no real network calls)."""
from __future__ import annotations

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from src.vacancies.adapters.hh_scraper import HHWebScraper, HHScraperError
from src.vacancies.adapters.hh_adapter import HHAdapter
from src.vacancies.core.enums import Currency, DmsStatus, TaxType, WorkFormat


class TestParseSalary:
    """Test salary parsing from Russian text."""

    def test_parse_range_rub(self):
        result = HHWebScraper._parse_salary("от 150 000 до 200 000 ₽")
        assert result.from_amount == 150000.0
        assert result.to_amount == 200000.0
        assert result.currency == Currency.RUB

    def test_parse_from_only(self):
        result = HHWebScraper._parse_salary("от 120 000 руб.")
        assert result.from_amount == 120000.0
        assert result.to_amount is None
        assert result.currency == Currency.RUB

    def test_parse_from_only_no_space(self):
        """Test salary without space after 'от' (hh.ru format)."""
        result = HHWebScraper._parse_salary("от120 000руб.")
        assert result.from_amount == 120000.0
        assert result.to_amount is None
        assert result.currency == Currency.RUB

    def test_parse_net(self):
        result = HHWebScraper._parse_salary("от 100 000 до 150 000 ₽ на руки")
        assert result.tax_type == TaxType.NET

    def test_parse_usd(self):
        result = HHWebScraper._parse_salary("от 2 000 до 3 000 USD")
        assert result.currency == Currency.USD

    def test_parse_empty(self):
        result = HHWebScraper._parse_salary(None)
        assert result.from_amount is None
        assert result.currency == Currency.UNKNOWN


class TestParseWorkFormat:
    """Test work format detection."""

    def test_remote_russian(self):
        assert HHWebScraper._parse_work_format("Удалённая работа") == WorkFormat.REMOTE

    def test_remote_english(self):
        assert HHWebScraper._parse_work_format("Remote") == WorkFormat.REMOTE

    def test_hybrid(self):
        assert HHWebScraper._parse_work_format("Гибридный формат") == WorkFormat.HYBRID

    def test_office(self):
        assert HHWebScraper._parse_work_format("Офис") == WorkFormat.OFFICE

    def test_unknown(self):
        assert HHWebScraper._parse_work_format("что-то") == WorkFormat.UNKNOWN


class TestDmsDetection:
    """Test DMS detection from vacancy text."""

    def test_dms_confirmed(self):
        scraper = HHWebScraper()
        from src.vacancies.core.models import Vacancy
        v = Vacancy(id="1", title="Go dev", description="Мы предлагаем ДМС после испытательного срока")
        scraper._detect_dms(v, "")
        assert v.benefits.dms_status == DmsStatus.CONFIRMED

    def test_dms_not_mentioned(self):
        scraper = HHWebScraper()
        from src.vacancies.core.models import Vacancy
        v = Vacancy(id="1", title="Go dev", description="Офис в центре города")
        scraper._detect_dms(v, "")
        assert v.benefits.dms_status == DmsStatus.NOT_MENTIONED


class TestHHAdapter:
    """Test HHAdapter with mocked scraper."""

    def test_adapter_creates_scraper_by_default(self):
        adapter = HHAdapter()
        assert adapter.scraper is not None

    def test_adapter_accepts_custom_scraper(self):
        mock_scraper = Mock(spec=HHWebScraper)
        adapter = HHAdapter(scraper=mock_scraper)
        assert adapter.scraper is mock_scraper

    def test_adapter_from_fixture(self, tmp_path):
        fixture = tmp_path / "test.json"
        fixture.write_text(json.dumps([
            {"id": "123", "name": "Go dev", "employer": "Corp", "url": "https://hh.ru/vacancy/123"}
        ]), encoding="utf-8")
        adapter = HHAdapter()
        vacancies = adapter.from_fixture(fixture)
        assert len(vacancies) == 1
        assert vacancies[0].title == "Go dev"
        assert vacancies[0].employer == "Corp"


class TestFetchErrorHandling:
    """Test error handling for network failures."""

    def test_403_raises_scraper_error(self, mocker):
        """Test that 403 raises HHScraperError with diagnostic info."""
        scraper = HHWebScraper()
        mock_resp = Mock()
        mock_resp.status_code = 403
        mock_resp.text = "<html><body>Access Denied</body></html>"
        scraper._session = Mock()
        scraper._session.get = Mock(return_value=mock_resp)

        with pytest.raises(HHScraperError, match="403"):
            scraper._fetch("https://hh.ru/vacancy/123")

    def test_429_raises_scraper_error(self, mocker):
        """Test that 429 raises HHScraperError."""
        scraper = HHWebScraper()
        mock_resp = Mock()
        mock_resp.status_code = 429
        mock_resp.text = ""
        scraper._session = Mock()
        scraper._session.get = Mock(return_value=mock_resp)

        with pytest.raises(HHScraperError, match="429"):
            scraper._fetch("https://hh.ru/vacancy/123")

    def test_captcha_detected(self, mocker):
        """Test that captcha/anti-bot pages raise error."""
        scraper = HHWebScraper()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = "Captcha required - please enter characters"
        scraper._session = Mock()
        scraper._session.get = Mock(return_value=mock_resp)

        with pytest.raises(HHScraperError, match="anti-bot"):
            scraper._fetch("https://hh.ru/vacancy/123")

    def test_cloudflare_detected(self, mocker):
        """Test that Cloudflare pages raise error."""
        scraper = HHWebScraper()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><head><title>Just a moment - Cloudflare</title></head><body></body></html>"
        scraper._session = Mock()
        scraper._session.get = Mock(return_value=mock_resp)

        with pytest.raises(HHScraperError, match="anti-bot"):
            scraper._fetch("https://hh.ru/vacancy/123")
