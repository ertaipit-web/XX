# Инструкции по запуску и диагностике

## Установка зависимостей

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\pip install -r requirements.txt
# Linux/macOS:
.venv/bin/pip install -r requirements.txt
```

Зависимости: `requests`, `curl_cffi`, `beautifulsoup4`, `lxml`, `pyyaml`,
`pytest`, `pytest-mock`.

## Запуск тестов

```bash
python -m pytest tests/ -v
```

Все тесты используют фикстуры и моки — внешние сервисы не нужны.

## Запуск полного пайплайна

На тестовых фикстурах (без сети):

```bash
python tools/hh_vacancies.py --report --report-source fixture \
    --fixture tests/fixtures/hh_sample.json \
    --text "Go-разработчик, удалёнка, от 150000"
```

С реальным scraping hh.ru (без API-токена):

```bash
python tools/hh_vacancies.py --report --report-source hh \
    --text "Go разработчик" --scrape-delay 8
```

Результаты: `reports/latest.md`, `reports/latest.json`,
`reports/runs/<run_id>.{md,json}`.

## Только scraping (без анализа)

```bash
python tools/hh_vacancies.py --text "Go разработчик" --area-id 2 \
    --max-pages 1 --per-page 20 --scrape --scrape-delay 8 \
    --output data/hh/scrape.json
```

## Режим без API-ключей

Система работает без ключей в двух режимах:
- `--report-source fixture` — статические данные;
- `--report-source hh` — публичный scraping hh.ru.

API-токен `HH_ACCESS_TOKEN` требуется только для официального API hh.ru
(режим без `--scrape`/`--report`).

## Конфигурация

- `config/candidate.yaml` — профиль кандидата.
- `config/scoring.yaml` — веса рейтинга (должны суммироваться к 1.0).
- Секреты — в `.env` (не коммитится). Шаблон: `.env.example`.

## Диагностика

- **403 / 429 / captcha от hh.ru** — снизьте частоту (`--scrape-delay`),
  смените IP. При обнаружении анти-бота диагностический HTML сохраняется в
  `data/hh/scrape-diag.html`.
- **0 вакансий** — проверьте доступность источника; оркестратор запишет
  ограничения в `run.metadata["limitations"]`.
- **QA находит проблемы** — см. `run.metadata["qa_issues"]`; цикл исправления
  ограничен `max_qa_iterations`.
- **Prompt injection** — количество помеченных вакансий в
  `run.metadata["injection_flagged"]`.

## Ограничения scraping

- hh.ru может блокировать частые запросы (403/429/captcha).
- Парсинг зависит от структуры сайта и может сломаться при редизайне.
- Использовать для личных исследований; соблюдать условия hh.ru.
