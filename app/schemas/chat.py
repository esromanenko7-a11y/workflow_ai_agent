from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"] = Field(
        description="Роль сообщения в диалоге"
    )
    content: str = Field(
        min_length=1,
        description="Текст сообщения",
    )


class ChatRequest(BaseModel):
    messages: list[Message] = Field(
        min_length=1,
        description="История сообщений для LLM",
    )
    model: str | None = Field(
        default=None,
        description="Модель. Если не указана, используется модель из настроек",
    )
    temperature: float = Field(
        default=0.0,
        ge=0,
        le=2,
        description="Температура генерации. 0 — максимально детерминированный ответ",
    )
    max_tokens: int = Field(
        default=1000,
        ge=1,
        le=16000,
        description="Максимальное количество токенов в ответе",
    )
    user_id: str | None = Field(
        default=None,
        description="Идентификатор пользователя для логирования и аналитики",
    )
    session_id: str | None = Field(
        default=None,
        description="Идентификатор сессии для будущей истории диалога",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Что означает статус BLOCKED при проверке пакета данных?",
                        }
                    ],
                    "temperature": 0,
                    "max_tokens": 500,
                    "user_id": "demo-user",
                    "session_id": "demo-session",
                },
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Отвечай кратко и понятно.",
                        },
                        {
                            "role": "user",
                            "content": "Проверь пакет PKG-001. Можно ли его передавать дальше?",
                        },
                    ],
                    "model": "llama3.2",
                    "temperature": 0,
                    "max_tokens": 700,
                },
            ]
        }
    )


class Usage(BaseModel):
    prompt_tokens: int = Field(default=0, description="Количество входных токенов")
    completion_tokens: int = Field(default=0, description="Количество выходных токенов")
    total_tokens: int = Field(default=0, description="Общее количество токенов")


class ChatResponse(BaseModel):
    content: str = Field(description="Финальный текст ответа модели")
    model: str = Field(description="Модель, которая сформировала ответ")
    usage: Usage = Field(description="Информация о токенах")
    finish_reason: str | None = Field(
        default=None,
        description="Причина завершения генерации",
    )
    cached: bool = Field(
        default=False,
        description="Признак, что ответ был получен из кеша",
    )

    @classmethod
    def from_openai(cls, response: Any, cached: bool = False) -> "ChatResponse":
        choice = response.choices[0]
        message = choice.message

        usage = Usage(
            prompt_tokens=getattr(response.usage, "prompt_tokens", 0) if response.usage else 0,
            completion_tokens=getattr(response.usage, "completion_tokens", 0) if response.usage else 0,
            total_tokens=getattr(response.usage, "total_tokens", 0) if response.usage else 0,
        )

        return cls(
            content=message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            cached=cached,
        )


class ChatDelta(BaseModel):
    content: str | None = Field(
        default=None,
        description="Очередной кусок streaming-ответа",
    )
    usage: Usage | None = Field(
        default=None,
        description="Usage, который приходит отдельным финальным событием",
    )