import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog
import tiktoken
from fastapi import HTTPException

from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository
from app.moderation.schemas import ModerationResult
from app.moderation.service import ModerationService


logger = structlog.get_logger(__name__)

CONTEXT_WINDOW_TOKENS = 128_000
RESPONSE_TOKENS = 1_000
SAFETY_MARGIN = 500

SAFE_MODERATION_OUTPUT = (
    "Не могу показать ответ — он мог нарушить правила."
)

ChatCompletionMessage = dict[str, Any]
ChatStreamEvent = dict[str, Any]
FOLLOW_UP_WORDS = {
    "них",
    "него",
    "нее",
    "ним",
    "ними",
    "их",
    "им",
    "они",
    "это",
    "этого",
    "этому",
    "эти",
    "этих",
    "такие",
    "таких",
    "там",
}

FOLLOW_UP_PREFIXES = (
    "а ",
    "и ",
    "тогда ",
    "а для ",
    "а если ",
    "а какая ",
    "а какой ",
    "а какие ",
    "а что ",
)


def _is_follow_up_question(text: str) -> bool:
    normalized = text.strip().lower().replace("ё", "е")

    if not normalized:
        return False

    if len(normalized) > 120:
        return False

    punctuation = ".,!?;:()[]{}\"'«»"
    token_text = normalized

    for char in punctuation:
        token_text = token_text.replace(char, " ")

    tokens = set(token_text.split())

    return normalized.startswith(FOLLOW_UP_PREFIXES) or bool(
        tokens & FOLLOW_UP_WORDS
    )

def _content_to_text_for_token_count(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks: list[str] = []

        for part in content:
            if not isinstance(part, dict):
                chunks.append(str(part))
                continue

            if part.get("type") == "text":
                chunks.append(str(part.get("text", "")))
            else:
                chunks.append(json.dumps(part, ensure_ascii=False))

        return "\n".join(chunks)

    return str(content)


def _count_text_tokens(text: str) -> int:
    try:
        encoding = tiktoken.get_encoding("o200k_base")
        return len(encoding.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def count_tokens(messages: list[ChatCompletionMessage]) -> int:
    total = 2

    for message in messages:
        total += 4
        total += _count_text_tokens(str(message.get("role", "")))
        total += _count_text_tokens(
            _content_to_text_for_token_count(message.get("content", ""))
        )

    return total


def fit_to_budget(
    messages: list[ChatCompletionMessage],
    budget: int,
) -> list[ChatCompletionMessage]:
    if count_tokens(messages) <= budget:
        return messages

    system_message: ChatCompletionMessage | None = None
    history = messages

    if messages and messages[0].get("role") == "system":
        system_message = messages[0]
        history = messages[1:]

    while history and count_tokens(
        ([system_message] if system_message else []) + history
    ) > budget:
        history = history[1:]

    if system_message is not None:
        return [system_message] + history

    return history


def _extract_delta_content(chunk: Any) -> str:
    if isinstance(chunk, dict):
        choices = chunk.get("choices") or []
        if not choices:
            return ""

        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""

    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""

    delta = getattr(choices[0], "delta", None)
    return getattr(delta, "content", None) or ""

def _extract_completion_content(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if not choices:
            return ""

        message = choices[0].get("message") or {}
        return message.get("content") or ""

    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    message = getattr(choices[0], "message", None)
    return getattr(message, "content", None) or ""

def _message_to_completion_message(
    message: ChatMessage,
) -> ChatCompletionMessage:
    content: Any = message.content

    media_part = None

    if message.media_refs:
        candidate = message.media_refs.get("part")
        if isinstance(candidate, dict):
            media_part = candidate

    if media_part is not None and message.role == "user":
        content = [
            {
                "type": "text",
                "text": message.content or "[медиа]",
            },
            media_part,
        ]

    return {
        "role": message.role,
        "content": content,
    }


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        llm_client: Any,
        default_model: str = "llama3.2",
        context_window: int = 10,
        moderation_service: ModerationService | None = None,
    ) -> None:
        self.repository = repository
        self.llm_client = llm_client
        self.default_model = default_model
        self.context_window = context_window
        self.moderation_service = moderation_service or ModerationService()

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
        return await self.repository.list_messages(
            chat_id=chat_id,
            limit=limit,
        )

    async def save_feedback(
        self,
        chat_id: UUID,
        message_id: UUID,
        owner_external_id: str,
        value: str,
    ) -> None:
        chat = await self.repository.get_chat(chat_id)

        if chat is None:
            raise ValueError(f"Chat not found: {chat_id}")

        await self.repository.save_feedback(
            message_id=message_id,
            owner_external_id=owner_external_id,
            value=value,
        )

    async def clear_history(self, chat_id: UUID) -> None:
        await self.repository.soft_delete_messages(chat_id)

    def check_input_moderation(
        self,
        content: str,
    ) -> ModerationResult:
        result = self.moderation_service.check_input(content)

        if result.allowed:
            return result

        raise HTTPException(
            status_code=403,
            detail={
                "code": "moderation_blocked",
                "categories": result.categories,
                "reasons": result.reasons,
                "blocked_by": result.blocked_by,
            },
        )

    async def _build_messages(
        self,
        chat: Chat,
    ) -> list[ChatCompletionMessage]:
        history = await self.repository.list_messages(
            chat_id=chat.id,
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

        messages.extend(
            _message_to_completion_message(message)
            for message in history
        )

        budget = CONTEXT_WINDOW_TOKENS - RESPONSE_TOKENS - SAFETY_MARGIN

        return fit_to_budget(
            messages=messages,
            budget=budget,
        )
    def _split_stream_chunks(
        self,
        text: str,
        chunk_size: int = 120,
    ) -> list[str]:
        chunks = []
        current = ""

        for word in text.split(" "):
            candidate = f"{current} {word}".strip()

            if len(candidate) <= chunk_size:
                current = candidate
                continue

            if current:
                chunks.append(current + " ")

            current = word

        if current:
            chunks.append(current)

        return chunks
    def _find_previous_user_question(
        self,
        history: list[ChatMessage],
        current_question: str,
    ) -> str | None:
        current_normalized = current_question.strip().lower()

        for message in reversed(history):
            if message.role != "user":
                continue

            content = message.content.strip()

            if not content:
                continue

            if content.lower() == current_normalized:
                continue

            if _is_follow_up_question(current_question) and _is_follow_up_question(content):
                continue

            return content

        return None

    async def _build_rag_search_question(
        self,
        current_question: str,
        history: list[ChatMessage],
    ) -> str:
        previous_user_question = self._find_previous_user_question(
            history=history,
            current_question=current_question,
        )

        if _is_follow_up_question(current_question) and previous_user_question:
            search_question = (
                f"{previous_user_question}. "
                f"Уточнение пользователя: {current_question}"
            )

            logger.info(
                "rag_follow_up_rewritten",
                original_question=current_question,
                search_question=search_question,
            )

            return search_question

        previous_messages = [
            message
            for message in history
            if message.content and message.content != current_question
        ]

        if not previous_messages:
            return current_question

        compact_history = previous_messages[-6:]

        messages: list[ChatCompletionMessage] = [
            {
                "role": "system",
                "content": (
                    "Ты переписываешь follow-up вопрос пользователя "
                    "в самостоятельный поисковый запрос для RAG. "
                    "Не отвечай на вопрос. Верни только один уточнённый вопрос. "
                    "Если вопрос уже самостоятельный, верни его без изменений."
                ),
            }
        ]

        for message in compact_history:
            messages.append(
                {
                    "role": message.role,
                    "content": message.content,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": (
                    "Текущий вопрос пользователя:\n"
                    f"{current_question}\n\n"
                    "Самостоятельный вопрос для поиска:"
                ),
            }
        )

        try:
            response = await self.llm_client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                stream=False,
            )
        except Exception:
            logger.exception("rag_condense_failed")
            return current_question

        search_question = _extract_completion_content(response).strip()

        return search_question or current_question
    async def _send_rag_message(
        self,
        chat_id: UUID,
        user_content: str,
        rag_service: Any,
    ) -> AsyncIterator[ChatStreamEvent]:
        history = await self.repository.list_messages(
            chat_id=chat_id,
            limit=self.context_window,
        )

        search_question = await self._build_rag_search_question(
            current_question=user_content,
            history=history,
        )

        rag_result = await asyncio.to_thread(
            rag_service.answer,
            search_question,
        )

        assistant_content = str(rag_result.get("answer", "")).strip()

        if not assistant_content:
            return

        output_result = self.moderation_service.check_output(
            assistant_content,
        )

        if not output_result.allowed:
            logger.warning(
                "rag_output_replaced_by_moderation",
                chat_id=str(chat_id),
                categories=output_result.categories,
                blocked_by=output_result.blocked_by,
            )
            assistant_content = SAFE_MODERATION_OUTPUT

        assistant_message = await self.repository.append_message(
            chat_id,
            ChatMessage(
                chat_id=chat_id,
                role="assistant",
                content=assistant_content,
                media_refs={
                    "rag": {
                        "search_question": search_question,
                        "top_score": rag_result.get("top_score"),
                        "confident": rag_result.get("confident"),
                        "sources": rag_result.get("sources", []),
                    }
                },
            ),
        )

        for chunk in self._split_stream_chunks(assistant_content):
            yield {
                "type": "token",
                "delta": chunk,
            }
            await asyncio.sleep(0)

        yield {
            "type": "sources",
            "message_id": str(assistant_message.id),
            "top_score": rag_result.get("top_score"),
            "confident": rag_result.get("confident"),
            "sources": rag_result.get("sources", []),
        }

        yield {
            "type": "done",
            "message_id": str(assistant_message.id),
        }

    async def send_message(
            self,
            chat_id: UUID,
            user_content: str,
            media_refs: dict[str, Any] | None = None,
            rag_service: Any | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        self.check_input_moderation(user_content)

        chat = await self.repository.get_chat(chat_id)

        if chat is None:
            raise ValueError(f"Chat not found: {chat_id}")

        visible_content = user_content.strip() or "[медиа]"

        await self.repository.append_message(
            chat_id,
            ChatMessage(
                chat_id=chat_id,
                role="user",
                content=visible_content,
                media_refs=media_refs,
            ),
        )

        if rag_service is not None and media_refs is None:
            async for event in self._send_rag_message(
                    chat_id=chat_id,
                    user_content=visible_content,
                    rag_service=rag_service,
            ):
                yield event

            return

        messages = await self._build_messages(chat)

        stream = await self.llm_client.chat.completions.create(
            model=self.default_model,
            messages=messages,
            stream=True,
        )

        assistant_chunks: list[str] = []

        async for chunk in stream:
            content = _extract_delta_content(chunk)

            if not content:
                continue

            assistant_chunks.append(content)

        assistant_content = "".join(assistant_chunks)

        if not assistant_content:
            return

        output_result = self.moderation_service.check_output(
            assistant_content,
        )

        if not output_result.allowed:
            logger.warning(
                "chat_output_replaced_by_moderation",
                chat_id=str(chat_id),
                categories=output_result.categories,
                blocked_by=output_result.blocked_by,
            )
            assistant_content = SAFE_MODERATION_OUTPUT

        assistant_message = await self.repository.append_message(
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
            message_id=str(assistant_message.id),
            chars=len(assistant_content),
        )

        yield {
            "type": "token",
            "delta": assistant_content,
        }
        yield {
            "type": "done",
            "message_id": str(assistant_message.id),
        }
