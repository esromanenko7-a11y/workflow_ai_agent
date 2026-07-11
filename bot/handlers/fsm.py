import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.keyboards.inline import get_topic_title, topics_kb
from bot.services.backend_client import BackendClient
from bot.states import AskFlow
from bot.web import stream_to_chat


router = Router()


@router.message(Command("ask"))
async def start_ask_flow(
    message: Message,
    state: FSMContext,
) -> None:
    await state.set_state(AskFlow.waiting_for_topic)

    await message.answer(
        "Выберите тему вопроса:",
        reply_markup=topics_kb(),
    )


@router.callback_query(
    AskFlow.waiting_for_topic,
    F.data.startswith("topic:"),
)
async def handle_topic_choice(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()

    topic_slug = (callback.data or "").removeprefix("topic:")

    if topic_slug == "cancel":
        await state.clear()

        if callback.message is not None:
            await callback.message.edit_text("Сценарий отменён.")

        return

    topic_title = get_topic_title(topic_slug)

    await state.update_data(topic=topic_title)
    await state.set_state(AskFlow.waiting_for_question)

    if callback.message is not None:
        await callback.message.edit_text(
            f"Тема: {topic_title}\nТеперь напишите вопрос.",
        )


@router.message(
    AskFlow.waiting_for_question,
    F.text,
)
async def handle_topic_question(
    message: Message,
    state: FSMContext,
    backend: BackendClient,
) -> None:
    data = await state.get_data()
    topic = data.get("topic", "проверка пакета данных")

    prompt = f"Тема: {topic}. Вопрос: {message.text}"

    try:
        chat_id = await get_user_chat_id(
            message=message,
            backend=backend,
        )

        tokens = backend.send_message(
            chat_id=chat_id,
            content=prompt,
        )

        await stream_to_chat(
            message=message,
            tokens=tokens,
        )

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))

    finally:
        await state.clear()
