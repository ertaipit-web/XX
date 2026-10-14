# Go Vacancy Research Agent

**Agent ID:** `go-vacancy-research`

## Description
Мультиагентная система поиска, анализа, оценки и подготовки отчётов о вакансиях для Go-разработчика. Система работает как команда специализированных агентов во главе с оркестратором.

## Входы (Inputs)
- `raw_query` (str, optional) — свободный текстовый запрос кандидата
- `profile` (CandidateProfile, optional) — заранее загруженный профиль
- `fixtures` (List[Vacancy], optional) — тестовые данные для оффлайн-режима
- `source` (str) — режим источника: `"multi"` (все источники), `"hh"` (только hh.ru), `"fixture"` (только фикстуры)
- `disable_llm` (bool) — отключить LLM-анализ, использовать только эвристики
- `output_dir` (Path) — директория для отчётов
- `write_reports` (bool) — сохранять ли отчёты на диск

## Выходы (Outputs)
- `VacancyReport` — структурированный отчёт с полем `summary` (метрики), `best_vacancies` (подходящие), `needs_clarification` (требуют уточнения), `not_suitable` (не подходят)
- Файлы: `reports/latest.md`, `reports/latest.json`, `reports/runs/<run_id>.*`

## Источники данных
1. **hh.ru** — официальный API (требует `HH_ACCESS_TOKEN` в env) или public scraping (fallback)
2. **habr.com** — mock-адаптер (готов к подключению Habr Career API)

## Конфигурация
- `config/candidate.yaml` — профиль кандидата (уровень, зарплата, формат, ДМС, LLM настройки)
- `config/scoring.yaml` — веса скоринга (salary_fit, format_fit, dms_fit, technical_interest, career_potential)
- `config/llm.yaml` — LLM провайдер (по умолчанию Ollama), модель, таймауты

## Агенты
1. **Career Intake Agent** — парсинг запроса в CandidateProfile (LLM + эвристики)
2. **Vacancy Discovery Agent** — поиск вакансий через MultiSourceAdapter
3. **Vacancy Verification Agent** — проверка источников, извлечение фактов, evidence
4. **Go Technical Analyst** — технический анализ задач (LLM + эвристики по Go/backend сигналам)
5. **Compensation & Benefits Agent** — нормализация зарплаты (net/gross, валют, периодов), детекция ДМС
6. **Career Fit Analyst** — карьерное соответствие (LLM + эвристики по грейду)
7. **Deduplication & Ranking Agent** — дедупликация (URL, cross-source fuzzy), скоринг, статусы
8. **Quality Assurance Agent** — проверка целостности, ограниченный fix-loop
9. **Report Writer Agent** — LLM-обогащение карточек лучших вакансий

## Ограничения и безопасность
- Зарплатный порог: **119 000 RUB/мес net** (gross и unknown tax basis не проходят автоматически)
- Обязательный формат: remote или hybrid в СПб
- ДМС: режим `prefer` (повышает рейтинг, но не фильтр) или `required`
- LLM: Ollama по умолчанию; cloud API только при явном `cloud_fallback_enabled: true`
- Prompt injection защита: текст вакансии санитизируется, не попадает в системные промпты
- Не сохраняет секреты в отчёты/логи
- Не отправляет отклики автоматически

## Запуск
```bash
# Ручной запуск (offline с фикстурами)
python -c "
from src.vacancies.orchestrator.orchestrator import VacancyResearchOrchestrator
orch = VacancyResearchOrchestrator(disable_llm=True)
# ... add fixtures
rep = orch.run(fixtures=[...])
"

# Ежедневный запуск через cron/Task Scheduler
python -m src.vacancies.cli daily
```

## История и детекция изменений
- История запусков сохраняется в `history/runs/`
- `index.json` — индекс запусков
- При каждом запуске: сравнение с предыдущим успешным запуском (до 30 дней)
- В отчёте: `new_vacancies`, `changed_vacancies`, `removed_vacancies`

## Тестирование
```bash
python -m pytest tests/vacancies/ tests/test_hh_vacancies.py -v
```
Все тесты работают без сети и платных API (используют моки и фикстуры).