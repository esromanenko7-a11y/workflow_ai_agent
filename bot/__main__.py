import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_bot_settings
from bot.handlers import router
from bot.services.backend_client import BackendClient


def build_telegram_session(
    proxy: str | None,
    verify_ssl: bool,
) -> AiohttpSession | None:
    if not proxy:
        return None

    session = AiohttpSession(proxy=proxy)

    if not verify_ssl:
        # Локальный dev-режим для proxy, который подменяет сертификаты.
        # В production лучше использовать корректный доверенный CA-сертификат.
        session._connector_init["ssl"] = False

    return session


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    settings = get_bot_settings()

    telegram_session = build_telegram_session(
        proxy=settings.bot_proxy,
        verify_ssl=settings.bot_verify_ssl,
    )

    bot = Bot(
        token=settings.bot_token,
        session=telegram_session,
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    backend = BackendClient(
        backend_url=settings.backend_url,
    )

    dispatcher["backend"] = backend
    dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(bot)
    finally:
        await backend.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
