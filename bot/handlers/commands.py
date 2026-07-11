import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.services.backend_client import BackendClient


router = Router()


@router.message(Command("start"))
async def handle_start(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        await get_user_chat_id(
            message=message,
            backend=backend,
        )

        await message.answer(
            "Привет! Я Telegram-клиент для ассистента проверки "
            "пакетов данных.\n\n"
            "Я не храню историю сам: все сообщения отправляются "
            "в backend chat-service.\n\n"
            "Команды:\n"
            "/help — помощь\n"
            "/clear — очистить историю\n"
            "/ask — вопрос по теме\n"
            "/cancel — отменить сценарий\n"
            "/chatid — показать chat_id для проверки /notify",
        )
    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    await message.answer(
        "Я помогаю анализировать результаты проверки пакетов данных.\n\n"
        "Можно отправить обычный текст, фото, голосовое сообщение, "
        "PDF или DOCX.\n\n"
        "Команды:\n"
        "/start — начать работу\n"
        "/clear — очистить историю backend-чата\n"
        "/ask — задать вопрос через сценарий с выбором темы\n"
        "/cancel — отменить текущий сценарий\n"
        "/chatid — показать chat_id для проверки /notify",
    )


@router.message(Command("chatid"))
async def handle_chat_id(message: Message) -> None:
    await message.answer(
        f"chat_id для /notify: {message.chat.id}",
    )


@router.message(Command("clear"))
async def handle_clear(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        chat_id = await get_user_chat_id(
            message=message,
            backend=backend,
        )

        await backend.clear_messages(chat_id)

        await message.answer("История очищена.")
    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))


@router.message(Command("cancel"))
async def handle_cancel(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer("Сценарий отменён.")
