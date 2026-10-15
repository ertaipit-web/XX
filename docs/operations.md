# Инструкции по запуску и диагностике

## Установка зависимостей
```bash
# Основные зависимости (std + pyyaml)
pip install pyyaml requests

# Для LLM (Ollama)
pip install requests  # уже есть

# Для hh.ru public scraping (опционально)
pip install curl_cffi beautifulsoup4

# Для тестов
pip install pytest pytest-mock
```

## Конфигурация

### 1. Профиль кандидата (`config/candidate.yaml`)
```yaml
profession: "Go Developer"
candidate_level: "junior"
experience_years: null
location:
  city: "Санкт-Петербург"
  country: "Россия"
work_preferences:
  - "remote"
  - "hybrid_spb"
salary:
  minimum: 119000
  currency: "RUB"
  period: "month"
  tax_basis: "net"
  is_mandatory: true
benefits:
  dms:
    mode: "prefer"      # prefer | required
    required: false
preferences:
  interesting_technical_work: true
llm:
  provider: "ollama"
  cloud_fallback_enabled: false
search:
  frequency: "daily"
report:
  language: "ru"
```

### 2. Веса скоринга (`config/scoring.yaml`)
```yaml
salary_fit: 0.25
format_fit: 0.25
dms_fit: 0.15
technical_interest: 0.25
career_potential: 0.10
```

### 3. LLM (`config/llm.yaml`)
```yaml
provider: "ollama"
model: "qwen2.5-coder:3b"
base_url: "http://localhost:11434"
temperature: 0.2
timeout: 120.0
max_retries: 2
retry_delay: 1.0
max_output_tokens: 512
enabled: true
```

### 4. Переменные окружения (`.env`)
```bash
# hh.ru API токен (для официального API)
HH_ACCESS_TOKEN=your_token_here

# SuperJob API ключ (опционально, для официального API)
SUPERJOB_API_KEY=your_key_here

# Переопределение LLM провайдера (для тестов/CI)
VACANCIES_LLM_PROVIDER=mock

# Отключить LLM полностью (детерминированный путь)
VACANCIES_DISABLE_LLM=1
```

## Режимы работы

### Ручной запуск (Python)
```python
from src.vacancies.orchestrator.orchestrator import VacancyResearchOrchestrator
from src.vacancies.core.enums import WorkFormat, DmsStatus, TaxType, Currency
from src.vacancies.core.models import Vacancy, SalaryInfo, BenefitsInfo

orch = VacancyResearchOrchestrator(disable_llm=True)  # или без disable_llm для LLM

# С фикстурами (оффлайн)
v = Vacancy(
    id="1", title="Go-разработчик", employer="TestCo",
    source_url="https://hh.ru/vacancy/1",
    work_format=WorkFormat.REMOTE,
    salary=SalaryInfo(from_amount=140000, currency=Currency.RUB, tax_type=TaxType.NET),
    benefits=BenefitsInfo(dms_status=DmsStatus.NOT_MENTIONED),
)
rep = orch.run(fixtures=[v])
```

### Ежедневный запуск (cron / Windows Task Scheduler)

**Linux/macOS (cron):**
```bash
# Каждый день в 09:00 (детерминированно, без LLM)
0 9 * * * cd /path/to/XX && VACANCIES_DISABLE_LLM=1 python -m src.vacancies.cli daily >> logs/daily.log 2>&1
```

**Windows (Task Scheduler):**
1. Создать задачу: "Ежедневно в 09:00"
2. Действие: `python.exe -m src.vacancies.cli daily`
3. Рабочая папка: `C:\Git\XX`

### CLI (в разработке)
```bash
# Ежедневный запуск
python -m src.vacancies.cli daily

# Ручной поиск с запросом
python -m src.vacancies.cli search "Go разработчик remote" --source multi

# Только фикстуры (тест)
python -m src.vacancies.cli test
```

## Получение hh.ru API токена
1. Зарегистрируйте приложение на https://dev.hh.ru/
2. Получите `client_id` и `client_secret`
3. Оформите OAuth2 авторизацию (Authorization Code flow)
4. Сохраните `access_token` в `HH_ACCESS_TOKEN` env variable

**Без токена:** работает public fallback (генерация ссылок на поиск), но данные ограничены.

## Запуск тестов
```bash
# Все тесты (кроме требующих curl_cffi)
python -m pytest tests/vacancies/ tests/test_hh_vacancies.py -v -k "not OrchestratorDisableLLM"

# Только unit-тесты
python -m pytest tests/vacancies/test_min_req.py tests/vacancies/test_core.py tests/vacancies/test_scenarios.py tests/vacancies/test_ranking.py -v

# LLM тесты (с MockLLMClient)
python -m pytest tests/vacancies/test_llm.py -v
```

## Структура отчётов
```
reports/
├── latest.md           # Последний Markdown отчёт
├── latest.json         # Последний JSON отчёт
├── career_report.md    # Task 04: рыночная статистика, матрица пробелов, план обучения (без PII)
├── runs/
│   ├── <run_id>.md     # История запусков
│   └── <run_id>.json
history/
├── index.json          # Индекс запусков
└── runs/
    └── <run_id>.json   # Полные данные запуска
data/candidates/
└── <profile_id>.json    # Локальный профиль кандидата (никогда не коммитится)
```

## Диагностика

### Типичные проблемы

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError: curl_cffi` | `pip install curl_cffi` или используйте `source="fixture"` |
| `HH_ACCESS_TOKEN not set` | Добавьте токен в `.env` или используйте public mode |
| `Ollama connection refused` | Запустите `ollama serve` или добавьте `VACANCIES_DISABLE_LLM=1` |
| `Rate limit (HTTP 429)` | Увеличьте задержки, уменьшите `per_page`/`max_pages` |
| `LLM timeout` | Увеличьте `timeout` в `config/llm.yaml` |

### Логирование
```python
import logging
logging.basicConfig(level=logging.DEBUG)
# Или через env:
# PYTHONPATH=. python -m src.vacancies.cli daily 2>&1 | tee log.txt
```

### Проверка конфигурации
```python
from src.vacancies.utils.config import ConfigLoader
cfg = ConfigLoader()
profile = cfg.load_candidate_profile()
weights = cfg.load_scoring_weights()
llm_cfg = cfg.load_llm_config()
print(profile, weights, llm_cfg)
```

## Оффлайн / тестовый режим
- Все тесты работают без сети (`MockLLMClient`, фикстуры в `tests/fixtures/`)
- Фикстуры помечены как `synthetic/fixture data` в метаданных
- Не выдавайте фикстуры за реальные вакансии

## Безопасность
- Не коммитьте `.env`, токены, API ключи
- Используйте `.env.example` как шаблон
- Отчёты не содержат секретов (проверяется в QA)
- Текст вакансий санитизируется перед LLM (prompt injection защита)