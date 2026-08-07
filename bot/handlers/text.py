import httpx
from aiogram import F, Router
from aiogram.types import Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.keyboards.feedback import feedback_kb
from bot.services.backend_client import BackendClient
from bot.web import stream_to_chat


router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        chat_id = await get_user_chat_id(
            message=message,
            backend=backend,
        )

        tokens = backend.send_message(
            chat_id=chat_id,
            content=message.text or "",
        )

        result = await stream_to_chat(
            message=message,
            tokens=tokens,
        )

        if result.backend_message_id:
            await message.answer(
                "Оцените ответ:",
                reply_markup=feedback_kb(result.backend_message_id),
            )

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))
