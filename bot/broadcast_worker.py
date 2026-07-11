import asyncio
import logging

import httpx
from aiogram import Bot

from bot.services.backend_client import BackendClient


logger = logging.getLogger(__name__)


def _telegram_chat_id(owner_external_id: str) -> int | None:
    prefix = "telegram:"

    if not owner_external_id.startswith(prefix):
        return None

    raw_id = owner_external_id.removeprefix(prefix)

    try:
        return int(raw_id)
    except ValueError:
        return None


async def broadcast_worker(
    bot: Bot,
    backend: BackendClient,
    interval_seconds: float = 10.0,
) -> None:
    while True:
        try:
            pending_payload = await backend.list_pending_broadcasts(
                interface_filter="telegram",
                limit=10,
            )
            users_payload = await backend.get_admin_users(
                limit=100,
            )

            users = users_payload.get("users", [])

            for broadcast in pending_payload.get("broadcasts", []):
                message = str(broadcast.get("message", ""))
                broadcast_id = str(broadcast.get("id", ""))

                if not message or not broadcast_id:
                    continue

                for user in users:
                    chat_id = _telegram_chat_id(
                        str(user.get("owner_external_id", ""))
                    )

                    if chat_id is None:
                        continue

                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                    )

                await backend.mark_broadcast_sent(
                    broadcast_id=broadcast_id,
                )

        except (
            RuntimeError,
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.HTTPStatusError,
        ) as error:
            logger.warning(
                "broadcast_worker_error: %s",
                error,
            )
        except Exception:
            logger.exception("unexpected_broadcast_worker_error")

        await asyncio.sleep(interval_seconds)
