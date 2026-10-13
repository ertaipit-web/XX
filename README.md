# HH.ru Learning Analyst

Workspace custom agent and a dependency-free Python CLI for collecting vacancy data through the official hh.ru API.

## Мультиагентная система анализа вакансий для Go-разработчика

Проект включает мультиагентную систему поиска, анализа, оценки и подготовки
отчётов о вакансиях Go-разработчика (СПб / удалёнка, от 119 000 руб/мес, ДМС).

Возможности:

- поиск вакансий через публичный scraping hh.ru (без API-токена, curl_cffi TLS fingerprint);
- профиль кандидата и веса рейтинга в YAML (`config/`);
- детерминированный рейтинг по критериям ТЗ;
- разделение «подходят» / «требуют уточнения» / «не подходят»;
- защита от prompt injection в описаниях вакансий;
- отчёты в Markdown и JSON с историей запусков;
- работа без API-ключей на фикстурах.

### Быстрый старт

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Полный пайплайн на тестовых данных (без сети)
python tools/hh_vacancies.py --report --report-source fixture --fixture tests/fixtures/hh_sample.json --text "Go-разработчик, удалёнка"

# Полный пайплайн с реальным scraping hh.ru
python tools/hh_vacancies.py --report --report-source hh --text "Go разработчик" --scrape-delay 8
```

Результаты: `reports/latest.md`, `reports/latest.json`, `reports/runs/<run_id>.*`.

Документация: [docs/architecture.md](docs/architecture.md),
[docs/agents.md](docs/agents.md), [docs/operations.md](docs/operations.md).

## Dry-run

```powershell
py -3 tools/hh_vacancies.py --text "Python developer" --area-id 2 --dry-run
```

Для целевого сбора prompt engineering- и vibe coding-вакансий используй встроенный набор английских и русских синонимов (`prompt engineer`, `vibecoder`, `vibe coder`, `вайбкодер`, `вайб-кодер` и другие). CLI загрузит полные карточки найденных вакансий, объединит дубли и исключит традиционные developer/ML-роли в поле `excluded`.

```powershell
py -3 tools/hh_vacancies.py --prompt-terms --area-id 2 --max-pages 1 --per-page 20 --output data/hh/prompt-engineering-spb.json
```

Для поиска по всей России используй `--all-russia`. Для полного сбора задай явный лимит страниц; при большом объеме начинай с одной страницы и проверяй результат.

Правило формата работы: вакансии в Санкт-Петербурге можно брать в офисе, гибриде или удаленно. Вакансии из других регионов России включай только при явной удаленке.

```powershell
py -3 tools/hh_vacancies.py --prompt-terms --all-russia --max-pages 1 --per-page 20 --output data/hh/prompt-engineering-russia.json
```

Без `HH_ACCESS_TOKEN` можно вывести публичные страницы поиска. Этот режим не является полным API-экспортом: результаты и описания нужно проверять в открытых карточках hh.ru.

```powershell
py -3 tools/hh_vacancies.py --prompt-terms --all-russia --public --output data/hh/public-search-russia.json
```

Without `--area-id`, the CLI resolves Санкт-Петербург through `/areas`. Collection requires an OAuth access token in `HH_ACCESS_TOKEN`; use `.env.example` as a variable checklist and keep real credentials outside the repository.

```powershell
$env:HH_ACCESS_TOKEN = "<local-token>"
py -3 tools/hh_vacancies.py --text "Python developer" --max-pages 1 --per-page 10
```

The agent is [`.github/agents/hh-learning-analyst.agent.md`](.github/agents/hh-learning-analyst.agent.md). It requires confirmation before network collection and does not automate login, CAPTCHA, 2FA, or private endpoints.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
```
