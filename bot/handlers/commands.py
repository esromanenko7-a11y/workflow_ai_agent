from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.services.backend_client import BackendClient


router = Router()


@router.message(CommandStart())
async def start_handler(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        await get_user_chat_id(message, backend)
    except Exception as error:
        await message.answer(backend_error_text(error))
        return

    await message.answer(
        "Привет! Я Telegram-клиент для ассистента проверки пакетов данных.\n\n"
        "Я не храню историю сам: вся история и LLM-логика находятся в backend.\n\n"
        "Доступные команды:\n"
        "/help — список команд\n"
        "/clear — очистить историю\n"
        "/ask — задать вопрос через сценарий с выбором темы\n"
        "/cancel — отменить активный сценарий"
    )


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Доступные команды:\n\n"
        "/start — создать чат и показать инструкцию\n"
        "/help — показать это сообщение\n"
        "/clear — очистить историю сообщений в backend\n"
        "/ask — выбрать тему и задать вопрос\n"
        "/cancel — отменить активный сценарий\n\n"
        "Также можно просто отправить текстовое сообщение — я передам его в backend."
    )


@router.message(Command("clear"))
async def clear_handler(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        chat_id = await get_user_chat_id(message, backend)
        await backend.clear_messages(chat_id)
    except Exception as error:
        await message.answer(backend_error_text(error))
        return

    await message.answer("История очищена.")


@router.message(Command("cancel"))
async def cancel_handler(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer("Сценарий отменён.")
