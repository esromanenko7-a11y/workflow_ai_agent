import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_bot_settings
from bot.handlers import router
from bot.services.backend_client import BackendClient


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    settings = get_bot_settings()

    bot = Bot(token=settings.bot_token)
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
