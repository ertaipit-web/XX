# Роли и контракты агентов

## Общие принципы
- Каждый агент наследуется от `AgentBase` (name, run())
- Возвращает `Dict[str, Any]` с ключами: `success`, `data`/`vacancies`, `errors`/`messages`
- Ошибки не маскируются — пробрасываются в `ResearchRun.agent_results` + `errors`
- LLM-агенты имеют fallback на эвристики при недоступности/ошибке LLM

---

## 1. Career Intake Agent
**Класс:** `CareerIntakeAgent` (`go_agents/agents.py`)
**LLM:** Опционально
**Вход:** `raw_query` (str), `profile` (CandidateProfile, optional)
**Выход:**
```python
{
    "profile": CandidateProfile,
    "messages": List[str],
    "contradictions": List[str],
    "missing_data": List[str],
}
```
**Поведение:**
- LLM парсит свободный текст → структурированный профиль
- Fallback: эвристики (regex для зарплаты, ключевые слова для локации/формата)
- Не выдумывает неизвестные поля → оставляет `null` / `missing_data`

---

## 2. Vacancy Discovery Agent
**Класс:** `VacancyDiscoveryAgent` (`go_agents/agents.py`)
**LLM:** Нет
**Вход:** `query` (SearchQuery), `source` (str), `multi_adapter`, `fixture_path`
**Выход:**
```python
{
    "vacancies": List[Vacancy],
    "source": str,
    "limitations": List[str],
    "source_results": Dict[str, List[Vacancy]],
}
```
**Источники:** `multi` (все), `hh` (hh.ru), `fixture` (тестовые данные)
**Поведение:** Делегирует поиск `MultiSourceAdapter`; агрегирует результаты и limitations

---

## 3. Vacancy Verification Agent
**Класс:** `VacancyVerificationAgent` (`go_agents/specialists.py`)
**LLM:** Нет
**Вход:** `vacancies` (List[Vacancy])
**Выход:** `{"vacancies": List[Vacancy], "success": bool}`
**Действия:**
- `checked_at = now`
- Проверка `source_url` → `CHECK_FAILED` если нет
- `evidence` + `confirmed_facts` для каждого поля
- `data_completeness`: FULL/PARTIAL/MINIMAL/UNKNOWN

---

## 4. Go Technical Analyst
**Класс:** `GoTechnicalAnalyst` (`go_agents/specialists.py`)
**LLM:** Опционально
**Вход:** `vacancies` (List[Vacancy])
**Выход:** `{"vacancies": List[Vacancy], "success": bool, "llm_analyzed": int}`
**LLM JSON схема:**
```json
{
  "task_interest_score": 0-100,
  "go_relevance_score": 0-100,
  "technologies": ["Go", "gRPC"],
  "positives": ["strong backend"],
  "concerns": ["no Go mentioned"]
}
```
**Эвристики:** Go signals, backend signals, routine signals → `task_interest_score`

---

## 5. Compensation & Benefits Agent
**Класс:** `CompensationBenefitsAgent` (`go_agents/specialists.py`)
**LLM:** Нет
**Вход:** `vacancies`, `min_salary` (float)
**Выход:** `{"vacancies": List[Vacancy], "success": bool}`
**Действия:**
- ДМС: regex поиск в description → `dms_status = CONFIRMED` + evidence
- Зарплата: `VacancyNormalizer.convert_to_monthly_net()` → сравнение с порогом
- `non_compliance_reasons` если ниже порога

---

## 6. Career Fit Analyst
**Класс:** `CareerFitAnalyst` (`go_agents/specialists.py`)
**LLM:** Опционально
**Вход:** `vacancies` (List[Vacancy])
**Выход:** `{"vacancies": List[Vacancy], "success": bool, "llm_analyzed": int}`
**LLM JSON схема:**
```json
{
  "fit_score": 0-100,
  "strong_points": ["remote", "modern stack"],
  "risks": ["no team info"],
  "questions_for_interview": ["team size?"],
  "recommendation": "подходит"
}
```
**Эвристики:** seniority indicators (lead/senior/middle/junior) → `fit_score`

---

## 7. Deduplication & Ranking Agent
**Класс:** `DeduplicationRankingAgent` (`go_agents/specialists.py`)
**LLM:** Нет
**Вход:** `vacancies`, `weights` (dict), `min_salary` (float)
**Выход:** `{"vacancies": List[Vacancy], "success": bool}`
**Дедупликация (3 этапа):**
1. **URL canonicalization** — убираем tracking params (utm_, gclid, fbclid, ref, source)
2. **Source ID match** — exact match по canonical URL
3. **Cross-source fuzzy** — employer+title+location similarity (>0.85/0.8)
**Скоринг:** `ScoringCalculator.calculate_score()` → `VacancyScore`
**Статусы:**
- `NOT_SUITABLE` — зарплата < порога (RUB)
- `SUITABLE` — score >= 60
- `NEEDS_CLARIFICATION` — остальное

---

## 8. Quality Assurance Agent
**Класс:** `QualityAssuranceAgent` (`go_agents/specialists.py`)
**LLM:** Нет
**Вход:** `vacancies`, `report` (optional)
**Выход:** `{"vacancies", "success": bool, "issues": List[str]}`
**Проверки:**
- `source_url` present
- currency != UNKNOWN при наличии зарплаты
- work_format известен при наличии location
- report.vacancies не пуст
**Fix-loop:** Orchestrator вызывает до 2 итераций, пересчитывает dedup/score

---

## 9. Report Writer Agent
**Класс:** `ReportWriterAgent` (`reporting/writers.py`)
**LLM:** Опционально
**Вход:** `best_vacancies` (List[Vacancy]), `limit` (int)
**Выход:** `{"enriched": int, "skipped": int}`
**LLM JSON схема:**
```json
{
  "summary": "Хорошая вакансия",
  "why_fits": "Соответствует стеку",
  "unknowns": ["размер команды"],
  "what_to_ask": ["какой процесс релизов?"]
}
```
Пишет: `latest.md`, `latest.json`, `runs/<run_id>.*`

---

## 10. Career Intelligence (Task 04)

Не LLM-агент, а детерминированный этап оркестратора (`orchestrator.py` §8b), использующий:

| Компонент | Файл | Ответственность |
|----------|------|-----------------|
| `MarketAnalyzer` | `market/analyzer.py` | Статистика навыков по двум датасетам |
| `GapAnalyzer` | `candidate/gap_analysis.py` | Матрица пробелов + план обучения + интервью |
| `ResumeParser` | `candidate/resume_parser.py` | Парсинг резюме (TXT/MD/PDF/DOCX) |
| `CandidateProfileManager` | `candidate/profile.py` | Локальное хранилище профиля |
| `InterviewQuestionBank` | `candidate/interview.py` | Целевые вопросы для intake |
| `Deduplicator` | `deduplication/deduplicator.py` | URL canonicalization → exact → fuzzy |
| `RolePackRegistry` | `role_pack/registry.py` | Загрузка role pack |
| `GO_JUNIOR_ROLE_PACK` | `role_pack/go_junior.py` | 22 навыка для Junior Go Developer |

**Поведение:**
- После дедупликации вакансии разбиваются на `candidate_eligible_vacancies` (status `suitable` или `needs_clarification`) и `role_market_sample` (остальные, для оценки спроса на навыки).
- `MarketAnalyzer` извлекает навыки по `GO_JUNIOR_ROLE_PACK`, считает: количество и % уникальных вакансий, количество уникальных работодателей, breakdown по required/preferred/mentioned/inferred, evidence-ссылки. Denominator — уникальные канонические вакансии.
- `GapAnalyzer` сравнивает профиль кандидата с рыночными статами → `skill_gaps` (gap_type: `confirmed_gap`/`needs_assessment`/`matches_target`/`not_relevant`/`unknown`), `learning_plan`, `interview_prep`. Отсутствие доказательств навыка → `needs_assessment` (не invented), а не `confirmed_gap`.
- `career_report.md` пишется в `reports/` с секциями: статус источников, новые/изменённые вакансии, лучшие вакансии, рыночная статистика навыков, целевой профиль, база кандидата (без PII), матрица пробелов, план обучения, интервью, ограничения.

**LLM:** используется только если `llm_provider != mock` и Ollama доступен. Без LLM весь pipeline работает детерминированно.

---

## Контракты данных
Все модели в `src/vacancies/core/models.py`:
- `CandidateProfile` — профиль (junior, 119k net, remote/hybrid, dms_mode)
- `Vacancy` — полная модель с evidence, анализами, скором, статусом
- `SalaryInfo` — from/to, currency, tax_type, period
- `VacancyScore` — 5 компонентов + total + weights + explanation
- `ResearchRun` / `VacancyReport` — метаданные запуска и итоговый отчёт