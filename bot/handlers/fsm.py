from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.keyboards.inline import get_topic_title, topics_kb
from bot.services.backend_client import BackendClient
from bot.states import AskFlow


router = Router()


@router.message(Command("ask"))
async def ask_start_handler(
    message: Message,
    state: FSMContext,
) -> None:
    await state.set_state(AskFlow.waiting_for_topic)

    await message.answer(
        "Выберите тему вопроса по проверке пакета данных:",
        reply_markup=topics_kb(),
    )


@router.callback_query(
    StateFilter(AskFlow.waiting_for_topic),
    F.data.startswith("topic:"),
)
async def topic_selected_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    data = callback.data or ""
    topic_slug = data.removeprefix("topic:")

    if topic_slug == "cancel":
        await state.clear()

        if callback.message is not None:
            await callback.message.edit_text("Сценарий отменён.")

        await callback.answer()
        return

    topic_title = get_topic_title(topic_slug)

    await state.update_data(topic=topic_title)
    await state.set_state(AskFlow.waiting_for_question)

    if callback.message is not None:
        await callback.message.edit_text(
            f"Тема: {topic_title}\n\nТеперь напишите вопрос."
        )

    await callback.answer()


@router.message(
    StateFilter(AskFlow.waiting_for_question),
    F.text,
)
async def question_handler(
    message: Message,
    state: FSMContext,
    backend: BackendClient,
) -> None:
    if message.text is None:
        return

    data = await state.get_data()
    topic = data.get("topic", "Общий вопрос")

    prompt = f"Тема: {topic}. Вопрос: {message.text}"

    try:
        chat_id = await get_user_chat_id(message, backend)

        answer_message = await message.answer("Думаю...")
        buffer = ""

        async for chunk in backend.send_message(
            chat_id=chat_id,
            content=prompt,
        ):
            buffer += chunk
            await answer_message.edit_text(buffer)

        if not buffer:
            await answer_message.edit_text("Backend вернул пустой ответ.")

    except Exception as error:
        await message.answer(backend_error_text(error))
    finally:
        await state.clear()
