# HH.ru Learning Analyst

Workspace custom agent and a dependency-free Python CLI for collecting vacancy data through the official hh.ru API.

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
