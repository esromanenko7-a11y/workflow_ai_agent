from aiogram import F, Router
from aiogram.types import Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.services.backend_client import BackendClient


router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def text_handler(
    message: Message,
    backend: BackendClient,
) -> None:
    if message.text is None:
        return

    try:
        chat_id = await get_user_chat_id(message, backend)

        answer_message = await message.answer("Думаю...")
        buffer = ""

        async for chunk in backend.send_message(
            chat_id=chat_id,
            content=message.text,
        ):
            buffer += chunk
            await answer_message.edit_text(buffer)

        if not buffer:
            await answer_message.edit_text("Backend вернул пустой ответ.")

    except Exception as error:
        await message.answer(backend_error_text(error))
