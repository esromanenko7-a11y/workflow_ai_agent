import asyncio
import time
import uuid
from collections.abc import AsyncIterator

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


MAX_TELEGRAM_TEXT_LENGTH = 4096
DRAFT_SAFE_LIMIT = 3900
DRAFT_UPDATE_INTERVAL_SECONDS = 2.0


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


def _draft_text(text: str) -> str:
    if len(text) <= DRAFT_SAFE_LIMIT:
        return text

    return text[-DRAFT_SAFE_LIMIT:]


async def _safe_send_message_draft(
    message: Message,
    draft_id: int,
    text: str,
) -> float:
    """
    Аккуратно обновляет Telegram draft.

    Если Telegram просит подождать из-за flood control,
    не падаем с исключением, а ставим паузу перед следующим draft-update.
    """
    try:
        await message.bot.send_message_draft(
            chat_id=message.chat.id,
            text=_draft_text(text),
            draft_id=draft_id,
        )
        return time.monotonic() + DRAFT_UPDATE_INTERVAL_SECONDS

    except TelegramRetryAfter as error:
        retry_after = float(getattr(error, "retry_after", 3))
        return time.monotonic() + retry_after + 0.5


async def stream_to_chat(
    message: Message,
    tokens: AsyncIterator[str],
) -> str:
    """
    Показывает streaming-ответ через Telegram sendMessageDraft.

    Draft обновляем не на каждый token, а с задержкой.
    Это защищает от Telegram flood control.
    Финальный send_message нужен, чтобы ответ остался в истории чата.
    """
    draft_id = uuid.uuid4().int & 0xFFFFFFFF
    buffer = ""
    next_draft_at = 0.0

    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action=ChatAction.TYPING,
    )

    async for delta in tokens:
        buffer += delta

        if not buffer.strip():
            continue

        now = time.monotonic()

        if now >= next_draft_at:
            next_draft_at = await _safe_send_message_draft(
                message=message,
                draft_id=draft_id,
                text=buffer,
            )

    if not buffer.strip():
        await message.bot.send_message(
            chat_id=message.chat.id,
            text="Backend вернул пустой ответ.",
        )
        return buffer

    # Один финальный draft-update перед обычным сообщением.
    # Если Telegram не даст обновить draft — не страшно,
    # главное ниже отправить финальный send_message.
    await _safe_send_message_draft(
        message=message,
        draft_id=draft_id,
        text=buffer,
    )

    if len(buffer) <= MAX_TELEGRAM_TEXT_LENGTH:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=buffer,
        )
        return buffer

    await message.bot.send_message(
        chat_id=message.chat.id,
        text=buffer[:MAX_TELEGRAM_TEXT_LENGTH],
    )

    return buffer
