# ИИ-ассистент для проверки пакетов с данными

Учебный проект по разработке ИИ-агента для анализа результатов автоматических проверок пакетов данных.

Ассистент помогает:

- понять, какие проверки прошёл пакет;
- выделить критичные ошибки и предупреждения;
- определить, можно ли передавать пакет дальше;
- получить рекомендации по исправлению проблем.

Проект развивается поэтапно:

1. реализован Function Calling для проверки пакета по `package_id`;
2. описан архитектурный паспорт проекта;
3. добавлен FastAPI-сервис для работы с LLM.

---

## Основные возможности

### Function Calling

В проекте реализован инструмент:

```text
get_validation_report(package_id)
```

Он получает результаты автоматических проверок пакета данных по идентификатору.

Пример идентификатора пакета:

```text
PKG-001
```

Пример пользовательского запроса:

```text
Проверь пакет PKG-001. Можно ли его передавать дальше?
```

Если пользователь спрашивает про конкретный пакет и указывает `package_id`, модель может вызвать tool `get_validation_report`.

Если пользователь задаёт общий вопрос или не указывает `package_id`, tool не вызывается.

---

### FastAPI-сервис

В проект добавлен FastAPI-слой, который превращает приложение в HTTP-сервис.

Сервис запускается командой:

```powershell
python -m uvicorn app.main:app --reload
```

После запуска доступны endpoints:

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/health` | Проверка, что сервис запущен |
| `GET` | `/models` | Получить список доступных моделей |
| `POST` | `/chat` | Получить обычный LLM-ответ |
| `POST` | `/chat/stream` | Получить streaming-ответ через SSE |

Swagger доступен по адресу:

```text
http://localhost:8000/docs
```

---

## Важное уточнение по текущей версии

Сейчас в проекте есть два рабочих сценария:

### 1. Function Calling сценарий проверки пакетов

Запускается через файлы в `examples/`.

Он использует:

```text
app/llm/client.py
app/tools/
app/prompts/
app/data/validation_reports.json
```

И умеет проверять пакеты по `package_id`.

### 2. FastAPI LLM-сервис

Запускается через:

```powershell
python -m uvicorn app.main:app --reload
```

Он использует:

```text
app/main.py
app/routers/
app/services/llm.py
app/schemas/
app/deps/
app/core/
```

И предоставляет HTTP API для обычного LLM-чата, streaming, кеширования и обработки ошибок.

В следующих этапах FastAPI-слой можно будет связать с агентом проверки пакетов, чтобы проверка `PKG-001` была доступна не только через `examples`, но и через HTTP API.

---

## Структура проекта

```text
ai-agents-cource/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── deps/
│   │   └── providers.py
│   ├── routers/
│   │   ├── chat.py
│   │   ├── health.py
│   │   └── models.py
│   ├── services/
│   │   └── llm.py
│   ├── schemas/
│   │   ├── chat.py
│   │   └── models.py
│   ├── tools/
│   │   ├── handlers.py
│   │   └── schemas.py
│   ├── prompts/
│   │   ├── system_v1.j2
│   │   ├── final_report_v1.j2
│   │   └── tools/
│   │       └── get_validation_report.md
│   ├── data/
│   │   └── validation_reports.json
│   └── llm/
│       └── client.py
├── docs/
│   ├── architecture.md
│   └── litellm/
│       └── config.yaml
├── examples/
│   ├── check_handler_locally.py
│   ├── check_tool_locally.py
│   ├── check_tool_schema_locally.py
│   ├── check_ollama_connection.py
│   ├── run_one_tool_call.py
│   └── run_three_cases.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Где находится реализация Function Calling

- `app/tools/schemas.py` — JSON Schema для инструмента `get_validation_report`;
- `app/tools/handlers.py` — Python-обработчик инструмента;
- `app/data/validation_reports.json` — локальный источник данных с результатами проверок;
- `app/prompts/system_v1.j2` — основной системный prompt ассистента;
- `app/prompts/final_report_v1.j2` — prompt для финального отчёта после получения результата tool;
- `app/prompts/tools/get_validation_report.md` — description для tool;
- `app/llm/client.py` — полный цикл Function Calling;
- `examples/run_three_cases.py` — запуск трёх тестовых сценариев.

---

## Логика анализа пакета

Бизнес-логика выполняется в Python, а не придумывается моделью.

Правила анализа:

- если есть хотя бы одна проверка со статусом `error`, итоговый статус пакета — `BLOCKED`;
- если ошибок нет, но есть `warning`, итоговый статус — `NEEDS_REVIEW`;
- если все проверки `ok`, итоговый статус — `APPROVED`.

Модель использует готовое поле `analysis` из результата tool и формирует понятное объяснение для пользователя.

---

## Function Calling цикл

В проекте реализован полный цикл Function Calling:

1. Пользователь задаёт вопрос.
2. Ассистент получает `messages` и описание доступных `tools`.
3. Если в вопросе есть `package_id` формата `PKG-001`, модель может вызвать `get_validation_report`.
4. Python-код выполняет функцию-обработчик.
5. Результат функции возвращается модели.
6. Модель формирует финальный ответ пользователю.

Если пользователь задаёт общий вопрос или не указывает `package_id`, tool не вызывается.

---

## Тест-кейсы Function Calling

### Случай A: запрос точно требует tool

Запрос пользователя:

```text
Проверь пакет PKG-001. Можно ли его передавать дальше?
```

Наблюдение:

Модель вызвала tool `get_validation_report` с аргументом:

```json
{"package_id": "PKG-001"}
```

Tool вернул результаты проверок пакета. В финальном ответе ассистент указал:

- итоговый статус `BLOCKED`;
- критичную ошибку: отсутствует файл `metadata.json`;
- предупреждение: даты в файле `data.csv` указаны в формате `DD.MM.YYYY`;
- рекомендации: добавить `metadata.json` и привести даты к формату `YYYY-MM-DD`.

### Случай B: запрос точно не требует tool

Запрос пользователя:

```text
Что означает статус BLOCKED при проверке пакета данных?
```

Наблюдение:

Tool не вызывался. Ассистент ответил обычным текстом и объяснил, что статус `BLOCKED` означает невозможность передать пакет дальше до исправления критичных ошибок.

### Случай C: пограничный запрос

Запрос пользователя:

```text
Кажется, с пакетом есть проблемы. Можно ли его передавать дальше?
```

Наблюдение:

Пользователь просит оценить пакет, но не указывает `package_id`. Tool не вызывается. Ассистент просит указать идентификатор пакета в формате `PKG-001`.

---

## Архитектурный паспорт

В проекте добавлен архитектурный документ:

```text
docs/architecture.md
```

В нём описаны:

- четыре слоя архитектуры: `Gateway → Service → LLM → Data`;
- поток одного запроса;
- Cache-Aside;
- Circuit Breaker;
- Fallback chain;
- Bulkhead;
- latency-critical и cost-critical вызовы;
- ADR по выбору паттерна взаимодействия;
- ADR по стратегии fault tolerance;
- потенциальные точки отказа;
- graceful degradation;
- роль LiteLLM Gateway.

Также добавлен пример конфигурации LiteLLM:

```text
docs/litellm/config.yaml
```

На текущем этапе LiteLLM изучается и документируется, но в runtime проекта пока не подключён.

---

## Архитектура FastAPI-слоя

FastAPI-часть проекта разделена на несколько слоёв.

### `app/main.py`

Создаёт FastAPI-приложение.

В этом файле реализованы:

- `lifespan`;
- создание `AsyncOpenAI`;
- создание Redis-клиента;
- CORS middleware;
- HTTP middleware для логирования запросов;
- обработчики ошибок;
- подключение routers.

### `app/core/config.py`

Описывает настройки через `pydantic-settings`.

Используемые настройки:

- `OPENAI_API_KEY`;
- `OPENAI_BASE_URL`;
- `DEFAULT_MODEL`;
- `REQUEST_TIMEOUT`;
- `REDIS_URL`;
- `CACHE_TTL_SECONDS`;
- `CORS_ORIGINS`.

### `app/core/exceptions.py`

Содержит доменные ошибки LLM-слоя:

- `LLMError`;
- `LLMRateLimitError`;
- `LLMTimeoutError`;
- `LLMAuthError`.

Эти ошибки преобразуются в HTTP-ответы.

### `app/deps/providers.py`

Содержит Dependency Injection:

- `get_settings`;
- `get_openai`;
- `get_cache`;
- `get_llm_service`.

Routers не создают клиентов напрямую, а получают готовый `LLMService` через зависимости FastAPI.

### `app/services/llm.py`

Сервисный слой для работы с LLM.

Реализовано:

- обычное completion-взаимодействие;
- streaming;
- Redis cache-aside;
- адаптация ответа SDK к `ChatResponse`;
- обработка ошибок провайдера.

### `app/routers/chat.py`

Содержит endpoints:

- `POST /chat`;
- `POST /chat/stream`.

### `app/routers/health.py`

Содержит endpoint:

- `GET /health`.

Он возвращает `{"status": "ok"}` и не зависит от Redis или LLM.

### `app/routers/models.py`

Содержит endpoint:

- `GET /models`.

Возвращает статический список доступных моделей.

---

## Конфигурация

Настройки берутся из `.env`.

Пример безопасной конфигурации находится в файле:

```text
.env.example
```

Для локальной работы через Ollama можно использовать:

```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
DEFAULT_MODEL=llama3.2
REQUEST_TIMEOUT=30
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=3600
CORS_ORIGINS=["http://localhost:3000"]
```

Реальный `.env` не должен попадать в Git.

---

## Работа с Ollama

Проект использует OpenAI-compatible API.

Для локальной Ollama настройки выглядят так:

```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
DEFAULT_MODEL=llama3.2
```

Для работы должна быть установлена и запущена Ollama.

Проверить список моделей:

```powershell
ollama list
```

Если модель `llama3.2` не установлена, её можно скачать:

```powershell
ollama pull llama3.2
```

---

## Cache-Aside

Для endpoint `POST /chat` реализован Redis cache-aside.

Логика:

1. Сервис строит cache key на основе параметров запроса.
2. Если ответ есть в Redis, возвращается ответ с `cached: true`.
3. Если ответа нет, сервис вызывает LLM.
4. Ответ сохраняется в Redis с TTL из настроек.
5. Первый запрос возвращает `cached: false`, повторный одинаковый запрос — `cached: true`.

Если Redis недоступен, сервис продолжает работать без кеша.

Это сделано специально: кеш — это оптимизация, он не должен ломать основной сценарий.

---

## Streaming

Endpoint:

```text
POST /chat/stream
```

возвращает ответ потоком в формате Server-Sent Events.

Пример формата:

```text
data: 1

data: ,

data: 2

data: {"usage":{"prompt_tokens":30,"completion_tokens":15,"total_tokens":45}}

data: [DONE]
```

Streaming реализован через:

```text
StreamingResponse(media_type="text/event-stream")
```

В конце потока отправляется:

```text
data: [DONE]
```

---

## Middleware и обработка ошибок

В проекте добавлен HTTP middleware.

Он:

- генерирует `request_id`;
- берёт `X-Request-ID` из запроса, если он передан;
- замеряет `duration_ms`;
- пишет лог по каждому HTTP-запросу;
- добавляет заголовок `X-Request-ID` в ответ.

Обработчики ошибок:

| Ошибка | HTTP-статус | Формат |
|---|---:|---|
| Ошибка валидации | `422` | `validation_error` |
| Rate limit LLM-провайдера | `429` | `llm_rate_limit` |
| Timeout LLM-провайдера | `504` | `llm_timeout` |
| Остальная ошибка LLM-провайдера | `502` | `llm_error` |

Пример ошибки:

```json
{
  "error": {
    "code": "llm_error",
    "message": "Ошибка при обращении к LLM-провайдеру"
  }
}
```

---

## Логирование Function Calling

Function Calling сценарий пишет события в файл:

```text
logs/tool_calls.jsonl
```

Логируются:

- пользовательский ввод;
- имя выбранного tool;
- аргументы tool;
- результат функции;
- финальный ответ модели;
- количество токенов, если модель вернула `usage.total_tokens`.

Примеры типов событий:

- `user_input`;
- `tool_call`;
- `tool_result`;
- `final_answer`;
- `final_answer_without_tool`.

---

## Как запустить проект

### 1. Установить зависимости

```powershell
python -m pip install -r requirements.txt
```

### 2. Подготовить `.env`

Создать файл `.env` на основе `.env.example`.

Для локальной Ollama:

```env
OPENAI_API_KEY=ollama
OPENAI_BASE_URL=http://localhost:11434/v1
DEFAULT_MODEL=llama3.2
REQUEST_TIMEOUT=30
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=3600
CORS_ORIGINS=["http://localhost:3000"]
```

### 3. Запустить Ollama

Проверить, что Ollama доступна:

```powershell
ollama list
```

Проверить OpenAI-compatible endpoint Ollama:

```powershell
curl.exe http://localhost:11434/api/tags
```

### 4. Запустить FastAPI-сервис

```powershell
python -m uvicorn app.main:app --reload
```

После запуска Swagger доступен здесь:

```text
http://localhost:8000/docs
```

### 5. Проверить health endpoint

```powershell
curl.exe http://localhost:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

### 6. Проверить список моделей

```powershell
curl.exe http://localhost:8000/models
```

### 7. Проверить обычный chat-запрос

Создать временный JSON-файл:

```powershell
@'
{"messages":[{"role":"user","content":"Say hello in one short sentence"}],"temperature":0,"max_tokens":50}
'@ | Set-Content -NoNewline -Encoding UTF8 .\tmp_chat.json
```

Отправить запрос:

```powershell
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  --data-binary "@tmp_chat.json"
```

При первом запросе ожидается:

```json
"cached": false
```

При повторном таком же запросе:

```json
"cached": true
```

### 8. Проверить streaming

Создать временный JSON-файл:

```powershell
@'
{"messages":[{"role":"user","content":"Count from one to five"}],"temperature":0,"max_tokens":100}
'@ | Set-Content -NoNewline -Encoding UTF8 .\tmp_stream_chat.json
```

Отправить streaming-запрос:

```powershell
curl.exe -N -X POST http://localhost:8000/chat/stream `
  -H "Content-Type: application/json" `
  --data-binary "@tmp_stream_chat.json"
```

Ожидаемый формат ответа:

```text
data: 1

data: 2

data: 3

data: [DONE]
```

### 9. Проверить ошибку валидации

Создать невалидный запрос:

```powershell
'{"messages":[]}' | Set-Content -Encoding UTF8 .\tmp_invalid_chat.json
```

Отправить запрос:

```powershell
curl.exe -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  --data-binary "@tmp_invalid_chat.json"
```

Ожидается ответ с кодом:

```text
validation_error
```

### 10. Проверить ошибку LLM-провайдера

Создать запрос с несуществующей моделью:

```powershell
@'
{"model":"model-that-does-not-exist","messages":[{"role":"user","content":"Hello"}],"temperature":0,"max_tokens":20}
'@ | Set-Content -NoNewline -Encoding UTF8 .\tmp_bad_model.json
```

Отправить запрос:

```powershell
curl.exe -i -X POST http://localhost:8000/chat `
  -H "Content-Type: application/json" `
  --data-binary "@tmp_bad_model.json"
```

Ожидается HTTP-статус:

```text
502 Bad Gateway
```

### 11. Проверить старый Function Calling сценарий

Проверить локальный обработчик tool:

```powershell
python -m examples.check_tool_locally
```

Запустить три тест-кейса:

```powershell
python -m examples.run_three_cases
```

Посмотреть лог в PowerShell:

```powershell
Get-Content .\logs\tool_calls.jsonl -Encoding UTF8
```

---

## Проверенные сценарии

Проверено вручную:

- `GET /health` возвращает `{"status":"ok"}`;
- `GET /models` возвращает список моделей Ollama;
- `POST /chat` возвращает ответ модели;
- повторный одинаковый `POST /chat` возвращает `cached: true`;
- `POST /chat/stream` отдаёт SSE-события `data: ...` и завершает поток событием `data: [DONE]`;
- запрос с несуществующей моделью возвращает HTTP `502`, а не traceback;
- невалидный запрос возвращает единый JSON-формат ошибки валидации;
- Function Calling сценарий корректно обрабатывает запросы с `package_id`.

---



