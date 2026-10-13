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
- `config/llm.yaml` — локальная LLM (Ollama).
- Секреты — в `.env` (не коммитится). Шаблон: `.env.example`.

## Локальная LLM (Ollama)

Система использует локальную модель через [Ollama](https://ollama.com) —
без облачных ключей и без отправки данных наружу.

### Установка и запуск

```powershell
# 1. Установить Ollama (если ещё нет): https://ollama.com/download
# 2. Запустить сервер (обычно стартует автоматически)
ollama serve
# 3. Скачать модель
ollama pull qwen2.5-coder:3b
# 4. Проверить
ollama list
```

### Настройка

`config/llm.yaml`:

```yaml
provider: ollama
model: qwen2.5-coder:3b
base_url: http://localhost:11434
temperature: 0.2
timeout: 120.0
max_retries: 2
max_output_tokens: 512
enabled: true
```

### Выбор модели

| Модель | Размер | Скорость (1 вызов) | Качество | Рекомендация |
|--------|--------|--------------------|----------|--------------|
| qwen2.5-coder:1.5b | 986 MB | ~5 с | базовое | очень слабое железо |
| qwen2.5-coder:3b | 1.9 GB | ~12 с | хорошее | **по умолчанию** |
| qwen2.5-coder:7b | 4.7 GB | ~73 с | хорошее | если есть время |
| qwen3:8b | 5.2 GB | медленно | хорошее (thinking) | сложный анализ |

3b даёт качество, сопоставимое с 7b, при ~6x меньшем времени. Для прогона на
5 вакансиях полный пайплайн занимает ~3.5 минуты на 3b.

### Управление через CLI

```powershell
# Полный пайплайн с LLM (по умолчанию)
python tools/hh_vacancies.py --report --report-source fixture --fixture tests/fixtures/hh_sample.json --text "Go-разработчик"

# Другая модель
python tools/hh_vacancies.py --report --report-source fixture --fixture tests/fixtures/hh_sample.json --text "Go" --llm-model qwen2.5-coder:7b

# Без LLM — только детерминированные эвристики (быстро)
python tools/hh_vacancies.py --report --report-source fixture --fixture tests/fixtures/hh_sample.json --text "Go" --no-llm
```

### Что делает LLM, а что — код

| Этап | Кто выполняет |
|------|---------------|
| Расчёт рейтинга, дедупликация | **детерминированный код** |
| Проверка обязательных критериев | **детерминированный код** |
| Нормализация зарплаты | **детерминированный код** |
| Разбор свободного запроса | LLM (fallback: эвристики) |
| Оценка технической интересности | LLM (fallback: эвристики) |
| Карьерный анализ, риски, вопросы | LLM (fallback: эвристики) |
| Карточки в отчёте | LLM (fallback: шаблон) |

При недоступности Ollama или ошибке LLM система автоматически переключается
на эвристики — пайплайн не падает.

### Переменные окружения

- `VACANCIES_DISABLE_LLM=1` — полностью отключить LLM.
- `VACANCIES_LLM_PROVIDER=mock` — подменить провайдер (тесты/CI).

### Безопасность

Текст вакансий — недоверенный. Перед подачей в LLM он проходит через
`sanitize_untrusted_text`, который детектирует и **нейтрализует** попытки
prompt injection (заменяет инструкции-подобные фрагменты плейсхолдером и
оборачивает текст в guard-маркеры). Системные промпты содержат явный запрет
следовать инструкциям из текста вакансии.

### Диагностика

- **`Connection refused` / LLM недоступна** — проверьте `ollama serve` и
  `base_url` в `config/llm.yaml`. Система продолжит работу на эвристиках.
- **Очень медленно** — смените модель на меньшую (`--llm-model qwen2.5-coder:1.5b`)
  или запустите с `--no-llm`.
- **Модель вернула не-JSON** — клиент извлекает JSON из markdown-обёрток;
  если не удалось, агент переходит на эвристики.

## Диагностика (общая)

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
