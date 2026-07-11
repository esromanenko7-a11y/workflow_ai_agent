from uuid import UUID

import httpx
from aiogram.types import Message

from bot.services.backend_client import BackendClient


def get_owner_external_id(message: Message) -> str:
    if message.from_user is not None:
        return f"telegram:{message.from_user.id}"

    return f"telegram-chat:{message.chat.id}"


async def get_user_chat_id(
    message: Message,
    backend: BackendClient,
) -> UUID:
    return await backend.get_or_create_chat(
        owner_external_id=get_owner_external_id(message),
        interface="telegram",
    )


def backend_error_text(error: Exception) -> str:
    if isinstance(error, httpx.ConnectError):
        return "Не удалось подключиться к backend-сервису. Проверьте, что FastAPI запущен."

    if isinstance(error, httpx.ReadTimeout):
        return "Backend слишком долго отвечает. Попробуйте ещё раз чуть позже."

    if isinstance(error, httpx.HTTPStatusError):
        return f"Backend вернул ошибку HTTP {error.response.status_code}."

    return "Произошла ошибка при обращении к backend-сервису."
