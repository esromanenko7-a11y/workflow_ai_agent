import httpx
from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.handlers.common import backend_error_text, get_owner_external_id
from bot.services.backend_client import BackendClient


router = Router()


@router.callback_query(F.data.startswith("fb:"))
async def handle_feedback(
    callback: CallbackQuery,
    backend: BackendClient,
) -> None:
    parts = (callback.data or "").split(":", maxsplit=2)

    if len(parts) != 3:
        await callback.answer(
            "Не удалось разобрать оценку.",
            show_alert=True,
        )
        return

    _, value, message_id = parts

    if value not in {"up", "down"}:
        await callback.answer(
            "Неизвестная оценка.",
            show_alert=True,
        )
        return

    if callback.message is None:
        await callback.answer(
            "Сообщение не найдено.",
            show_alert=True,
        )
        return

    try:
        chat_id = await backend.get_or_create_chat(
            owner_external_id=get_owner_external_id(callback.message),
            interface="telegram",
        )

        await backend.save_feedback(
            chat_id=chat_id,
            message_id=message_id,
            owner_external_id=get_owner_external_id(callback.message),
            value=value,
        )

        await callback.message.edit_reply_markup(
            reply_markup=None,
        )

        await callback.answer("Спасибо за оценку!")

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await callback.answer(
            backend_error_text(error),
            show_alert=True,
        )
