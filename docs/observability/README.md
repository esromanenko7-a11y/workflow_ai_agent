# Observability

В этом каталоге хранится результат observability-проверки FastAPI LLM-сервиса.

## Phoenix trace

Файл со скриншотом:

```text
phoenix_trace.png
```

На скриншоте показан trace, который был автоматически создан после запроса к endpoint:

```text
POST /chat
```

## Что видно на скриншоте

На скриншоте видно:

- Phoenix UI открыт на `http://localhost:6006`;
- выбран проект `diploma-fastapi`;
- в проекте появился LLM span с именем `ChatCompletion`;
- span имеет тип `LLM`;
- запрос завершился успешно;
- отображается latency LLM-вызова;
- отображается количество использованных токенов;
- стоимость равна `$0`, потому что используется локальная модель Ollama;
- trace был создан автоматически через OpenInference-инструментацию OpenAI SDK.

## Что проверяет этот скриншот

Скриншот подтверждает, что observability-слой работает:

1. FastAPI-приложение отправляет traces в Phoenix.
2. Phoenix принимает traces от контейнера `app`.
3. LLM-вызовы автоматически инструментируются.
4. В UI Phoenix видны параметры LLM-запроса, latency и tokens.

## Связанные компоненты

Observability-слой реализован в файлах:

```text
app/observability/tracing.py
app/observability/logging.py
app/observability/pii.py
```

Docker Compose поднимает Phoenix как отдельный сервис:

```text
phoenix
```

Адрес Phoenix UI:

```text
http://localhost:6006
```

Переменная окружения для отправки traces из контейнера `app`:

```text
PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006
```

В коде этот адрес нормализуется до HTTP endpoint для отправки traces:

```text
http://phoenix:6006/v1/traces
```

## JSON-логи

Кроме Phoenix traces, сервис пишет структурные JSON-логи через `structlog`.

Для запроса к `/chat` в логах появляются события:

```text
http_request_started
llm_request_completed
http_request_completed
```

Событие `llm_request_completed` содержит:

- `request_id`;
- `model`;
- `input_tokens`;
- `output_tokens`;
- `total_tokens`;
- `latency_ms`;
- `finish_reason`;
- `prompt_hash`;
- `prompt_preview`.

Сырой prompt в лог не записывается.

## PII-маскирование

Перед записью `prompt_preview` в лог выполняется маскирование чувствительных данных.

Маскируются:

- email;
- российский телефон;
- номер банковской карты;
- ИНН;
- паспорт.

Пример:

```text
Мой email ivan@mail.ru, тел +7 (999) 123-45-67, карта 4111 1111 1111 1111
```

В лог попадёт в безопасном виде:

```text
Мой email [EMAIL], тел [PHONE_RU], карта [CARD]
```

Unit-тесты для PII-маскирования находятся в файле:

```text
tests/test_pii.py
```

Запуск тестов:

```powershell
python -m pytest tests/test_pii.py
```