# Роли и контракты агентов

Все агенты следуют общему контракту: `run(...) -> Dict[str, Any]`, где результат
содержит минимум ключ `success`. Идентификация агента — поле `name`.

## 1. Career Intake Agent (`go_agents/agents.py`)
- **Ответственность:** разбор запроса → валидированный `CandidateProfile`.
- **Вход:** `raw_query: str | None`, `profile: CandidateProfile | None`.
- **Выход:** `{profile, messages, contradictions, missing_data}`.
- **Ограничение:** не придумывает характеристики кандидата; фиксирует противоречия.

## 2. Vacancy Discovery Agent (`go_agents/agents.py`)
- **Ответственность:** сбор вакансий из источников.
- **Вход:** `SearchQuery`, `source` (`hh` | `fixture` | `test`), адаптер/фикстура.
- **Выход:** `{vacancies, source, limitations}`.
- **Ограничение:** каждая вакансия имеет проверяемый `source_url`; при отказе
  источника возвращает пустой список и фиксирует ограничение.

## 3. Vacancy Verification Agent (`go_agents/specialists.py`)
- **Ответственность:** проверка источника, извлечение фактов, оценка полноты.
- **Выход:** вакансии с `confirmed_facts`, `evidence`, `data_completeness`.
- **Ограничение:** отсутствие данных не становится отрицательным фактом.

## 4. Go Technical Analyst (`go_agents/specialists.py`)
- **Ответственность:** технический анализ (Go, backend, конкурентность, рутина).
- **Выход:** `TechnicalAnalysis` (go_relevance_score, task_interest_score, concerns).
- **Ограничение:** не приписывает технологии, не подтверждённые описанием.

## 5. Compensation & Benefits Agent (`go_agents/specialists.py`)
- **Ответственность:** нормализация зарплаты и льгот, проверка порога.
- **Выход:** обновлённые `SalaryInfo`/`BenefitsInfo`, `non_compliance_reasons`.
- **Ограничение:** не вычисляет net из gross без обоснованных допущений.

## 6. Career Fit Analyst (`go_agents/specialists.py`)
- **Ответственность:** карьерное соответствие, риски, вопросы для интервью.
- **Выход:** `CareerFitAnalysis` (fit_score, strong_points, risks, questions).
- **Ограничение:** не проводит психологическую диагностику; выводы — из описания.

## 7. Deduplication & Ranking Agent (`go_agents/specialists.py`)
- **Ответственность:** дедупликация по URL + детерминированный рейтинг.
- **Выход:** уникальные вакансии с `VacancyScore` и статусом.
- **Ограничение:** баллы считает `ScoringCalculator`, а не LLM; обязательные
  нарушения → `not_suitable`.

## 8. Report Writer Agent (`reporting/writers.py`)
- **Ответственность:** генерация Markdown и JSON.
- **Ограничение:** не добавляет факты, отсутствующие в результатах агентов.

## 9. Quality Assurance Agent (`go_agents/specialists.py`)
- **Ответственность:** проверка целостности и непротиворечивости.
- **Выход:** `{success, issues}`.
- **Ограничение:** не исправляет факты без источника; возвращает на исправление.

## Оркестратор — Vacancy Research Orchestrator (`orchestrator/orchestrator.py`)
- **Ответственность:** координация всех этапов, retry, лимиты, запись отчётов.
- **Лимиты (`OrchestratorLimits`):** `max_vacancies`, `max_retries`,
  `retry_delay_seconds`, `max_qa_iterations`, `enable_parallel_analysis`.
- **Ограничение:** конечное число итераций; без бесконечного самоулучшения.
