from collections.abc import AsyncIterator
from uuid import UUID

import structlog
import tiktoken

from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository


logger = structlog.get_logger("chat-service")


CONTEXT_WINDOW_TOKENS = 128_000
RESPONSE_TOKENS = 1_000
SAFETY_MARGIN = 500


ChatCompletionMessage = dict[str, str]


def _count_text_tokens(text: str) -> int:
    """
    Считает токены для одного текста.

    Основной путь — tiktoken o200k_base, как требуется в задании.
    Fallback нужен для локальной разработки: tiktoken при первом запуске может
    пытаться скачать BPE-файл, а на машине может быть настроен SOCKS proxy
    без установленной requests[socks].
    """
    try:
        encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(text))
    except Exception:
        # Грубая оценка: в среднем 1 токен ≈ 4 символа.
        # Это не замена tiktoken для production-метрик, но позволяет
        # сервису и unit-тестам работать офлайн.
        return max(1, len(text) // 4)


def count_tokens(messages: list[ChatCompletionMessage]) -> int:
    """
    Примерная оценка количества токенов в ChatML-формате.

    +4 на каждое сообщение и +2 итогово — простая поправка на служебные
    токены формата чата.
    """
    total = 2

    for message in messages:
        total += 4
        total += _count_text_tokens(message["role"])
        total += _count_text_tokens(message["content"])

    return total


def fit_to_budget(
    messages: list[ChatCompletionMessage],
    budget: int,
) -> list[ChatCompletionMessage]:
    """
    Обрезает историю с начала, сохраняя system-сообщение, если оно есть.
    """
    if count_tokens(messages) <= budget:
        return messages

    if messages and messages[0]["role"] == "system":
        system_message = messages[0]
        history = messages[1:]
    else:
        system_message = None
        history = messages

    while history:
        candidate = [*history]

        if system_message is not None:
            candidate = [system_message, *candidate]

        if count_tokens(candidate) <= budget:
            return candidate

        history = history[1:]

    return [system_message] if system_message is not None else []


def _extract_delta_content(chunk: object) -> str:
    """
    Достаёт текстовый delta-content из chunk OpenAI-compatible stream.
    """
    if isinstance(chunk, dict):
        choices = chunk.get("choices") or []

        if not choices:
            return ""

        delta = choices[0].get("delta") or {}

        return delta.get("content") or ""

    choices = getattr(chunk, "choices", None)

    if not choices:
        return ""

    delta = getattr(choices[0], "delta", None)

    if delta is None:
        return ""

    content = getattr(delta, "content", None)

    return content or ""


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        llm_client,
        default_model: str = "llama3.2",
        context_window: int = 10,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.default_model = default_model
        self.context_window = context_window

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        return await self.repository.create_chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        return await self.repository.get_chat(chat_id)

    async def list_messages(
        self,
        chat_id: UUID,
        limit: int = 50,
    ) -> list[ChatMessage]:
        return await self.repository.list_messages(chat_id, limit=limit)

    async def clear_history(self, chat_id: UUID) -> None:
        await self.repository.soft_delete_messages(chat_id)

    async def _build_messages(self, chat: Chat) -> list[ChatCompletionMessage]:
        history = await self.repository.list_messages(
            chat.id,
            limit=self.context_window,
        )

        messages: list[ChatCompletionMessage] = []

        if chat.system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": chat.system_prompt,
                }
            )

        for message in history:
            messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        budget = CONTEXT_WINDOW_TOKENS - RESPONSE_TOKENS - SAFETY_MARGIN

        return fit_to_budget(messages, budget)

    async def send_message(
        self,
        chat_id: UUID,
        user_content: str,
    ) -> AsyncIterator[str]:
        chat = await self.repository.get_chat(chat_id)

        if chat is None:
            raise ValueError(f"Chat not found: {chat_id}")

        user_message = ChatMessage(
            chat_id=chat_id,
            role="user",
            content=user_content,
        )

        await self.repository.append_message(chat_id, user_message)

        messages = await self._build_messages(chat)

        stream = await self.llm_client.chat.completions.create(
            model=self.default_model,
            messages=messages,
            stream=True,
        )

        assistant_parts: list[str] = []

        try:
            async for chunk in stream:
                content = _extract_delta_content(chunk)

                if not content:
                    continue

                assistant_parts.append(content)
                yield content
        finally:
            assistant_content = "".join(assistant_parts)

            if assistant_content:
                await self.repository.append_message(
                    chat_id,
                    ChatMessage(
                        chat_id=chat_id,
                        role="assistant",
                        content=assistant_content,
                    ),
                )

                logger.info(
                    "chat_assistant_message_saved",
                    chat_id=str(chat_id),
                    content_length=len(assistant_content),
                )
