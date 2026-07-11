from html import escape

import httpx
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.filters.admin import IsAdmin
from bot.handlers.common import backend_error_text
from bot.services.backend_client import BackendClient


router = Router()
router.message.filter(IsAdmin())


def _format_stats(stats: dict) -> str:
    return (
        "<b>Статистика за 24 часа</b>\n\n"
        f"Сообщений: <b>{stats.get('total_messages', 0)}</b>\n"
        f"Активных пользователей: <b>{stats.get('active_users', 0)}</b>\n"
        f"Средняя latency, мс: <b>{stats.get('avg_latency_ms')}</b>\n"
        f"Доля блокировок moderation: <b>{stats.get('moderation_block_rate', 0)}</b>\n"
        f"Доля 👍 feedback: <b>{stats.get('feedback_up_ratio', 0)}</b>"
    )


def _format_users(payload: dict) -> str:
    users = payload.get("users", [])

    if not users:
        return "Пользователей пока нет."

    lines = [
        "<b>Последние пользователи</b>",
        "",
        "<pre>owner              chats interface</pre>",
    ]

    for user in users[:10]:
        owner = escape(str(user.get("owner_external_id", "")))[:18]
        chats_count = str(user.get("chats_count", 0))
        interface = escape(str(user.get("interface", "")))

        lines.append(
            f"<pre>{owner:<18} {chats_count:<5} {interface}</pre>"
        )

    return "\n".join(lines)


@router.message(Command("stats"))
async def handle_admin_stats(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        stats = await backend.get_admin_stats()

        await message.answer(
            _format_stats(stats),
            parse_mode="HTML",
        )

    except (
        RuntimeError,
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(
            backend_error_text(error),
        )


@router.message(Command("users"))
async def handle_admin_users(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        users = await backend.get_admin_users(limit=10)

        await message.answer(
            _format_users(users),
            parse_mode="HTML",
        )

    except (
        RuntimeError,
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(
            backend_error_text(error),
        )


@router.message(Command("broadcast"))
async def handle_admin_broadcast(
    message: Message,
    command: CommandObject,
    backend: BackendClient,
) -> None:
    text = (command.args or "").strip()

    if not text:
        await message.answer(
            "Использование: /broadcast текст сообщения",
        )
        return

    try:
        result = await backend.enqueue_broadcast(
            message=text,
            interface_filter="telegram",
        )

        await message.answer(
            "Broadcast поставлен в очередь.\n"
            f"id: <code>{escape(str(result.get('broadcast_id')))}</code>",
            parse_mode="HTML",
        )

    except (
        RuntimeError,
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(
            backend_error_text(error),
        )
