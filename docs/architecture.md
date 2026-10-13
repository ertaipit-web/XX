# Архитектура мультиагентной системы поиска вакансий для Go-разработчика

Система реализует команду специализированных агентов во главе с оркестратором.
Каждому агенту назначена чёткая ответственность, типизированные контракты и
ограниченные инструменты. Все изменения выполняются в ветке `dev`.

## Принципы

1. **Сначала детерминированный код.** Рейтинг, дедупликация, нормализация и
   проверка обязательных критериев реализованы детерминированно. LLM не
   используется для расчёта баллов — только для интерпретации текста (опционально).
2. **Типизированные контракты.** Все сущности описаны `@dataclass` в
   `src/vacancies/core/models.py` и `core/contracts.py`.
3. **Неизвестность ≠ отрицание.** Отсутствие данных (зарплата, ДМС, формат)
   помечается явными статусами (`unknown`, `not_mentioned`), а не нулями.
4. **Недоверенный внешний ввод.** Текст вакансий санитизируется на предмет
   prompt injection (`utils/sanitize.py`).
5. **Ограниченные ресурсы.** Оркестратор использует лимиты: max_vacancies,
   max_retries, max_qa_iterations, timeout.

## Структура модулей

```
src/vacancies/
├── core/
│   ├── models.py        # CandidateProfile, Vacancy, SalaryInfo, BenefitsInfo, ...
│   ├── contracts.py     # AgentResult, ResearchRun, VacancyReport
│   ├── enums.py         # Currency, DmsStatus, TaxType, WorkFormat, VacancyStatus, ...
│   └── scoring.py       # VacancyNormalizer, ScoringCalculator (детерминированный)
├── go_agents/
│   ├── agents.py        # CareerIntakeAgent, VacancyDiscoveryAgent
│   └── specialists.py   # Verification, Technical, Compensation, CareerFit, Dedup, QA
├── llm/
│   ├── client.py        # LLMConfig, OllamaClient, MockLLMClient, build_llm_client
│   └── prompts.py       # системные промпты + security preamble
├── adapters/
│   ├── hh_adapter.py    # HHAdapter: fixture + live scraping
│   └── hh_scraper.py    # HHWebScraper: curl_cffi TLS fingerprint
├── orchestrator/
│   └── orchestrator.py  # VacancyResearchOrchestrator + OrchestratorLimits
├── reporting/
│   └── writers.py       # VacancyReportWriter + ReportWriterAgent (LLM)
├── utils/
│   ├── config.py        # ConfigLoader (candidate.yaml, scoring.yaml, llm.yaml)
│   └── sanitize.py      # prompt-injection detection & neutralization
└── storage/             # зарезервировано под историю запусков
```

## LLM-слой

Локальная модель подключается через Ollama (`config/llm.yaml`). Абстракция
`BaseLLMClient` даёт две реализации:

- **`OllamaClient`** — реальный вызов локального сервера (`/api/generate`),
  с retry, таймаутом и ограничением длины вывода.
- **`MockLLMClient`** — детерминированный ответ для тестов и offline-режима.

Ключевые принципы:

1. **LLM ≠ источник истины.** Рейтинг, дедупликация и обязательные критерии
   считает детерминированный код; LLM только интерпретирует текст.
2. **Graceful degradation.** При недоступности LLM каждый агент переходит на
   эвристики — пайплайн не падает.
3. **Строгая схема вывода.** Агенты ожидают JSON-объект; клиент извлекает его
   даже из markdown-обёртки, при неудаче — fallback.
4. **Безопасность.** Текст вакансии нейтрализуется (prompt injection), системные
   промпты содержат явный запрет следовать инструкциям из данных.

## Поток данных (пайплайн)

```
Запрос пользователя
        │
        ▼
[1] Career Intake Agent ──► CandidateProfile (валидированный)
        │
        ▼
[2] Vacancy Discovery Agent ──► List[Vacancy]  (hh.ru / fixture)
        │
        ▼
[3] Sanitize (prompt injection guard)
        │
        ▼
[4] Vacancy Verification Agent ──► подтверждённые факты + data_completeness
        │
        ▼
[5] Анализ (параллельно, ThreadPoolExecutor):
        ├── Go Technical Analyst      ──► TechnicalAnalysis
        ├── Compensation & Benefits   ──► SalaryInfo/BenefitsInfo
        └── Career Fit Analyst        ──► CareerFitAnalysis
        │
        ▼
[6] Deduplication & Ranking Agent ──► дедуп + VacancyScore + статус
        │
        ▼
[7] Report Writer ──► reports/latest.md + reports/latest.json
        │
        ▼
[8] Quality Assurance Agent ──► ограниченный цикл исправления (max_qa_iterations)
```

## Модель рейтинга (детерминированная)

| Критерий             | Вес  |
|----------------------|------|
| Соответствие зарплате| 0.25 |
| Формат и география   | 0.25 |
| Подтверждённость ДМС | 0.15 |
| Интересность задач   | 0.25 |
| Карьерный потенциал  | 0.10 |

Веса загружаются из `config/scoring.yaml` (не зашиты в код). Каждая
составляющая оценивается 0–100, итог — взвешенная сумма.

## Обязательные критерии vs рейтинг

Обязательное несоответствие (например, зарплата ниже порога 119 000 руб/мес)
присваивает статус `not_suitable` независимо от рейтинга. Недостаток данных
приводит к `needs_clarification`, а не к исключению вакансии.

## Источники данных

- **hh.ru public scraping** — через `HHWebScraper` (curl_cffi, Chrome TLS
  fingerprint). Без API-токена. Соблюдаются задержки между запросами.
- **Fixture-файлы** — статические JSON для тестов и работы без сети.
- API-интеграции — зарезервированы за интерфейсом адаптера.

## Хранение истории

- `reports/latest.md` / `reports/latest.json` — последний отчёт.
- `reports/runs/<run_id>.md` / `.json` — история запусков.

## Конфигурация

- `config/candidate.yaml` — профиль кандидата (профессия, география, порог
  зарплаты, ДМС, язык).
- `config/scoring.yaml` — веса рейтинга.
- `.env` — секреты (не коммитится); `.env.example` — шаблон.
