import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Message
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


MAX_TELEGRAM_TEXT_LENGTH = 4096
EDIT_SAFE_LIMIT = 3900
EDIT_UPDATE_INTERVAL_SECONDS = 0.8


@dataclass
class StreamResult:
    text: str
    backend_message_id: str | None = None
    sources: list[dict[str, Any]] | None = None


class NotifyRequest(BaseModel):
    chat_id: int
    text: str


def build_api(
    bot: Bot,
    internal_token: str,
) -> FastAPI:
    api = FastAPI(
        title="Telegram Bot Internal API",
    )

    @api.post("/notify")
    async def notify(
        request: NotifyRequest,
        x_internal_token: str = Header(...),
    ) -> dict[str, bool]:
        if x_internal_token != internal_token:
            raise HTTPException(
                status_code=401,
                detail="Invalid internal token",
            )

        await bot.send_message(
            chat_id=request.chat_id,
            text=request.text,
        )

        return {
            "ok": True,
        }

    return api


def _telegram_safe_text(text: str) -> str:
    if len(text) <= EDIT_SAFE_LIMIT:
        return text

    return (
        text[:EDIT_SAFE_LIMIT]
        + "\n\n…ответ длинный, продолжение будет отправлено следующим сообщением."
    )


def _format_sources(
    sources: list[dict[str, Any]],
) -> str:
    if not sources:
        return ""

    lines = [
        "",
        "Источники:",
    ]

    for index, source in enumerate(sources[:5], start=1):
        source_id = source.get("id") or str(index)
        file_name = source.get("file_name") or "источник без имени"
        page = source.get("page")
        score = source.get("score")

        parts = [
            f"[{source_id}] {file_name}",
        ]

        if page is not None:
            parts.append(f"page={page}")

        if isinstance(score, int | float):
            parts.append(f"score={score:.3f}")

        lines.append(", ".join(parts))

    return "\n".join(lines)


async def _safe_edit_message(
    message: Message,
    text: str,
) -> float:
    try:
        await message.edit_text(
            text=_telegram_safe_text(text),
        )
        return time.monotonic() + EDIT_UPDATE_INTERVAL_SECONDS

    except TelegramRetryAfter as error:
        retry_after = float(getattr(error, "retry_after", 3))
        return time.monotonic() + retry_after + 0.5

    except TelegramBadRequest as error:
        error_text = str(error).lower()

        if "message is not modified" in error_text:
            return time.monotonic() + EDIT_UPDATE_INTERVAL_SECONDS

        return time.monotonic() + EDIT_UPDATE_INTERVAL_SECONDS


async def _send_final_text(
    draft_message: Message,
    original_message: Message,
    text: str,
) -> None:
    if len(text) <= MAX_TELEGRAM_TEXT_LENGTH:
        await _safe_edit_message(
            message=draft_message,
            text=text,
        )
        return

    first_part = text[:MAX_TELEGRAM_TEXT_LENGTH]

    await _safe_edit_message(
        message=draft_message,
        text=first_part,
    )

    remaining_text = text[MAX_TELEGRAM_TEXT_LENGTH:]

    while remaining_text.strip():
        chunk = remaining_text[:MAX_TELEGRAM_TEXT_LENGTH]
        remaining_text = remaining_text[MAX_TELEGRAM_TEXT_LENGTH:]

        await original_message.answer(
            text=chunk,
        )


async def stream_to_chat(
    message: Message,
    tokens: AsyncIterator[dict],
) -> StreamResult:
    draft_message = await message.answer("Готовлю ответ...")

    buffer = ""
    next_edit_at = 0.0
    backend_message_id = None
    sources: list[dict[str, Any]] = []

    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action=ChatAction.TYPING,
    )

    async for event in tokens:
        event_type = event.get("type")

        if event_type == "done":
            backend_message_id = event.get("message_id") or backend_message_id
            continue

        if event_type == "sources":
            backend_message_id = event.get("message_id") or backend_message_id

            raw_sources = event.get("sources", [])
            if isinstance(raw_sources, list):
                sources = raw_sources

            continue

        if event_type != "token":
            continue

        delta = event.get("delta", "")
        buffer += delta

        if not buffer.strip():
            continue

        now = time.monotonic()

        if now >= next_edit_at:
            next_edit_at = await _safe_edit_message(
                message=draft_message,
                text=buffer,
            )

    if not buffer.strip():
        empty_text = "Backend вернул пустой ответ."

        await _safe_edit_message(
            message=draft_message,
            text=empty_text,
        )

        return StreamResult(
            text=empty_text,
            backend_message_id=backend_message_id,
            sources=sources,
        )

    final_text = buffer + _format_sources(sources)

    await _send_final_text(
        draft_message=draft_message,
        original_message=message,
        text=final_text,
    )

    return StreamResult(
        text=final_text,
        backend_message_id=backend_message_id,
        sources=sources,
    )