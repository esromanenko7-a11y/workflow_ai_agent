# Chat backend: архитектура чата и хранение истории

## Что добавлено

В проект добавлен модуль `app/chat/`, который отвечает за stateful-чат.

Главное отличие от старого endpoint `/chat`: теперь клиент не обязан каждый раз передавать всю историю сообщений. История хранится на стороне backend-сервиса, а клиент работает через стабильный контракт:

```text
/chats/{chat_id}/messages
```

Этот контракт дальше можно использовать для Telegram-бота, web-интерфейса, RAG и agent tools.

## Архитектура

```mermaid
flowchart LR
    Client[Client: CLI / Web / Telegram] --> Routes[app/chat/routes.py]

    Routes --> Service[ChatService]

    Service --> Repository[ChatRepository Protocol]
    Service --> LLM[AsyncOpenAI-compatible client]

    Repository --> JsonRepo[JsonChatRepository]
    Repository --> PgRepo[PostgresChatRepository]

    JsonRepo --> JsonFiles[(JSONL files)]
    PgRepo --> Postgres[(Postgres)]

    LLM --> Ollama[Ollama / OpenAI-compatible API]
```

## Основные компоненты

### `app/chat/domain.py`

Содержит доменные модели:

- `Chat` — метаданные диалога;
- `ChatMessage` — одно сообщение в истории.

Доменные модели не зависят от FastAPI, SQLAlchemy или файловой системы.

### `app/chat/repository.py`

Содержит контракт `ChatRepository` через `typing.Protocol`.

Минимальные методы:

```python
create_chat(...)
get_chat(...)
append_message(...)
list_messages(...)
soft_delete_messages(...)
```

Это позволяет использовать разные хранилища с одинаковым интерфейсом.

### `app/chat/repositories/json_repo.py`

JSONL-реализация репозитория.

Структура хранения:

```text
var/chats/
  chats/
    <chat_id>/
      chat.json
      messages.jsonl
```

`messages.jsonl` хранит одно сообщение на строку.

Очистка истории работает через soft delete: старые сообщения физически остаются в файле, но в конец добавляется marker:

```json
{"type": "soft_delete", "at": "..."}
```

После такого marker метод `list_messages()` возвращает только новые сообщения.

### `app/chat/service.py`

`ChatService` отвечает за бизнес-логику чата:

1. сохранить user-сообщение;
2. загрузить историю;
3. построить context для LLM;
4. вызвать LLM в streaming-режиме;
5. отдавать chunks наружу;
6. после завершения сохранить полный assistant-ответ.

## Выбранная стратегия контекста

Выбрана стратегия `sliding window`.

Она берёт последние `N` сообщений из истории:

```python
history = await repo.list_messages(chat_id, limit=N)
```

`N` задаётся настройкой:

```env
CHAT_CONTEXT_WINDOW=10
```

Почему выбрана эта стратегия:

- она простая и надёжная для первого backend-чата;
- её легко тестировать;
- она хорошо подходит для коротких диалогов поддержки и проверки пакетов данных;
- она не требует отдельного LLM-вызова для summary;
- она помогает быстро проверить главный принцип: история живёт на сервере.

Для будущего дипломного проекта можно будет перейти к `hybrid`-стратегии: summary + последние сообщения. Это будет полезно, если диалоги станут длинными и нужно будет помнить старые решения, ошибки пакетов и выводы анализа.

## Token budget

В `app/chat/service.py` добавлены функции:

```python
count_tokens(messages)
fit_to_budget(messages, budget)
```

Основной способ подсчёта токенов использует:

```python
tiktoken.get_encoding("o200k_base")
```

Если локальная среда не может загрузить encoding из-за proxy или отсутствия сети, используется fallback-оценка. Это нужно, чтобы unit-тесты и локальная разработка не падали из-за инфраструктуры.

## Endpoints

### Создать чат

```http
POST /chats
```

Body:

```json
{
  "owner_external_id": "test-1",
  "interface": "cli",
  "system_prompt": "Ты помощник проверки пакетов данных."
}
```

Ответ:

```json
{
  "chat_id": "..."
}
```

### Получить метаданные чата

```http
GET /chats/{chat_id}
```

### Отправить сообщение в чат

```http
POST /chats/{chat_id}/messages
```

Body:

```json
{
  "content": "Привет, меня зовут Аня"
}
```

Ответ приходит через SSE:

```text
data: ...
data: ...
data: [DONE]
```

### Получить историю сообщений

```http
GET /chats/{chat_id}/messages?limit=50
```

Ответ — массив сообщений в хронологическом порядке:

```json
[
  {
    "role": "user",
    "content": "Привет, меня зовут Аня"
  },
  {
    "role": "assistant",
    "content": "..."
  }
]
```

### Очистить историю сообщений

```http
DELETE /chats/{chat_id}/messages
```

Ответ:

```json
{
  "status": "ok"
}
```

## Настройки

Добавлены настройки:

```env
CHAT_REPOSITORY=json
CHAT_STORAGE_DIR=./var/chats
CHAT_CONTEXT_STRATEGY=sliding
CHAT_CONTEXT_WINDOW=10
```

### JSON-хранилище

```env
CHAT_REPOSITORY=json
CHAT_STORAGE_DIR=./var/chats
```

Используется `JsonChatRepository`.

### Postgres-хранилище

```env
CHAT_REPOSITORY=postgres
```

Postgres-реализация будет подключена отдельным шагом через `PostgresChatRepository`, async SQLAlchemy и Alembic migration.

## Как запустить локально

```powershell
$env:CHAT_REPOSITORY = "json"
$env:CHAT_STORAGE_DIR = "./var/chats"

uvicorn app.main:app --reload
```

Если порт `8000` занят старым процессом, можно запустить на другом порту:

```powershell
uvicorn app.main:app --reload --port 8001
```

## Ручная проверка

1. `POST /chats` возвращает `chat_id`.
2. `GET /chats/{chat_id}` возвращает метаданные чата.
3. `POST /chats/{chat_id}/messages` отдаёт SSE chunks и завершает поток строкой `data: [DONE]`.
4. Второй `POST /messages` использует историю предыдущих сообщений.
5. `GET /messages` возвращает историю в хронологическом порядке.
6. `DELETE /messages` возвращает `{"status":"ok"}`.
7. После `DELETE` следующий `GET /messages` возвращает пустой список.
8. В JSONL-файле появляется soft-delete marker.

## Тесты

Запуск chat-тестов:

```powershell
python -m pytest tests/chat -m "not llm"
```

Запуск всех быстрых тестов:

```powershell
python -m pytest tests/unit tests/chat -m "not llm"
```

Текущий результат:

```text
52 passed
```