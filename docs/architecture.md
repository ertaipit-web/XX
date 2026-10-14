# Архитектура мультиагентной системы поиска Go-вакансий

## Обзор
Система реализует оркестратор (`VacancyResearchOrchestrator`), координирующий 9 специализированных агентов. Каждый агент имеет чёткую ответственность, типизированные контракты и ограниченные инструменты.

## Компоненты

### Orchestrator (`src/vacancies/orchestrator/orchestrator.py`)
- **VacancyResearchOrchestrator** — главный класс, управляющий pipeline
- **OrchestratorLimits** — лимиты безопасности (макс. вакансии, ретраи, таймауты, QA-итерации)
- Этапы:
  1. **Intake** — парсинг запроса в CandidateProfile
  2. **Discovery** — сбор вакансий из источников
  3. **Sanitize** — санитизация недоверенного текста (prompt injection защита)
  4. **Verify** — проверка источников, evidence extraction
  5. **Analysis** — параллельный запуск Tech/Comp/Fit агентов
  5. **Dedup/Rank** — дедупликация, скоринг, статусы
  6. **Report** — формирование Markdown + JSON
  7. **LLM Enrichment** — опциональное обогащение карточек
  8. **QA** — проверка + ограниченный fix-loop (max 2 итерации)
  9. **History** — сохранение, детекция новых/изменённых вакансий

### Agents (`src/vacancies/go_agents/`)
| Агент | Ответственность | LLM |
|-------|----------------|-----|
| CareerIntakeAgent | Парсинг запроса → CandidateProfile | Да (опционально) |
| VacancyDiscoveryAgent | Поиск через MultiSourceAdapter | Нет |
| VacancyVerificationAgent | Проверка URL, evidence, completeness | Нет |
| GoTechnicalAnalyst | Технический анализ Go/Backend задач | Да (опционально) |
| CompensationBenefitsAgent | Зарплата (net/gross/period), ДМС детекция | Нет |
| CareerFitAnalyst | Карьерное соответствие, риски, вопросы | Да (опционально) |
| DeduplicationRankingAgent | Дедуп (URL canonicalization, cross-source), скоринг | Нет |
| QualityAssuranceAgent | Валидация отчёта, fix-loop | Нет |
| ReportWriterAgent | LLM-обогащение карточек | Да (опционально) |

### Adapters (`src/vacancies/adapters/`)
| Адаптер | Источник | Статус |
|---------|----------|--------|
| `HHAdapter` | hh.ru API (OAuth) / public fallback | Рабочий |
| `HabrAdapter` | habr.com Career API | Mock (готов к интеграции) |
| `GenericJSONFeedAdapter` | Любой JSON-фид | Рабочий |
| `MultiSourceAdapter` | Координация нескольких источников | Рабочий |

**Интерфейс `SourceAdapter` (base.py):**
- `search(query: SearchQuery) -> List[Vacancy]`
- `fetch_details(vacancy: Vacancy) -> Vacancy`
- `load_fixture(path: Path) -> List[Vacancy]`
- `get_source_status() -> Dict`

### Core Models (`src/vacancies/core/models.py`)
- `CandidateProfile` — профиль кандидата (junior, 119k net, remote/hybrid SPb, dms_mode)
- `Vacancy` — полная модель вакансии с evidence, анализами, скором, статусом
- `SalaryInfo` — from/to, currency, tax_type (NET/GROSS/UNKNOWN), period
- `BenefitsInfo` — dms_status (CONFIRMED/NOT_MENTIONED/UNKNOWN)
- `TechnicalAnalysis` / `CareerFitAnalysis` — результаты LLM/эвристик
- `VacancyScore` — 5 компонентов + total + weights + explanation

### Scoring (`src/vacancies/core/scoring.py`)
- **Взвешенная сумма** 5 компонентов (настраивается в `config/scoring.yaml`)
- **Зарплата**: конвертация в месячный net RUB (нет hardcoded курсов), gross/unknown не проходят net-порог автоматически
- **Формат**: remote=100, hybrid=80, office=30, unknown=50
- **ДМС**: confirmed=100, not_mentioned=40, unknown=50
- **Технический**: от LLM или эвристик (Go signals, backend signals)
- **Карьерный**: от LLM или эвристик (seniority indicators)

### Storage (`src/vacancies/storage/`)
- `RunHistory` — сохранение запусков в `history/runs/`, индекс в `index.json`
- `NewVacancyDetector` — сравнение с предыдущим запуском (до 30 дней), детекция new/changed/removed

### Config (`src/vacancies/utils/config.py`)
- `ConfigLoader` — загрузка YAML с поддержкой legacy flat и нового nested формата
- ENV overrides: `VACANCIES_LLM_PROVIDER`, `VACANCIES_DISABLE_LLM`

### LLM (`src/vacancies/llm/`)
- `BaseLLMClient` — интерфейс + `generate_json()` с извлечением JSON
- `OllamaClient` — локальный Ollama (retries, timeout)
- `MockLLMClient` — детерминированный для тестов
- `build_llm_client()` — фабрика

### Prompts (`src/vacancies/llm/prompts.py`)
- `SECURITY_PREAMBLE` — защита от prompt injection
- Системные промпты: INTAKE, TECHNICAL, CAREER_FIT, REPORT
- Builders: `build_technical_prompt`, `build_career_fit_prompt`, etc.

## Поток данных
```
raw_query → CareerIntakeAgent → CandidateProfile
    ↓
VacancyDiscoveryAgent (MultiSourceAdapter) → List[Vacancy]
    ↓
Sanitize (prompt injection defense)
    ↓
VacancyVerificationAgent → checked_at, evidence, completeness
    ↓
Parallel: GoTechnicalAnalyst, CompensationBenefitsAgent, CareerFitAnalyst
    ↓
DeduplicationRankingAgent → canonical_url, cross-source fuzzy, score, status
    ↓
VacancyReport (summary, best/needs/not groups)
    ↓
LLM ReportWriter (опционально)
    ↓
QA (loop max 2 iter) → fix if needed
    ↓
RunHistory.save_run() + NewVacancyDetector.detect()
    ↓
Reports: latest.md/.json + runs/<run_id>.* + history/runs/
```

## Безопасность
- Секреты только в env (`.env.example` шаблон)
- Текст вакансий = untrusted input → санитизация перед LLM
- Системные промпты содержат `SECURITY_PREAMBLE`
- Нет авто-откликов, нет публикации личных данных
- Rate limits, timeouts, retry bounds на каждом сетевом этапе