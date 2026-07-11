from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.fsm import handle_topic_choice, start_ask_flow
from bot.states import AskFlow


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeState:
    def __init__(self) -> None:
        self.state = None
        self.data: dict = {}

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict:
        return dict(self.data)

    async def clear(self) -> None:
        self.state = None
        self.data.clear()


async def test_start_ask_flow_sets_waiting_for_topic_state() -> None:
    state = FakeState()
    message = SimpleNamespace(
        answer=AsyncMock(),
    )

    await start_ask_flow(
        message=message,
        state=state,
    )

    assert state.state == AskFlow.waiting_for_topic

    message.answer.assert_awaited_once()

    args, kwargs = message.answer.call_args

    assert "Выберите тему" in args[0]
    assert kwargs["reply_markup"] is not None


async def test_topic_choice_sets_waiting_for_question_state() -> None:
    state = FakeState()

    callback_message = SimpleNamespace(
        edit_text=AsyncMock(),
    )
    callback = SimpleNamespace(
        data="topic:errors",
        answer=AsyncMock(),
        message=callback_message,
    )

    await handle_topic_choice(
        callback=callback,
        state=state,
    )

    callback.answer.assert_awaited_once()
    callback_message.edit_text.assert_awaited_once()

    assert state.state == AskFlow.waiting_for_question
    assert "topic" in state.data

    args, _ = callback_message.edit_text.call_args

    assert "Тема:" in args[0]
    assert "Теперь напишите вопрос" in args[0]


async def test_topic_cancel_clears_state() -> None:
    state = FakeState()
    state.data["topic"] = "Ошибки пакета"
    state.state = AskFlow.waiting_for_topic

    callback_message = SimpleNamespace(
        edit_text=AsyncMock(),
    )
    callback = SimpleNamespace(
        data="topic:cancel",
        answer=AsyncMock(),
        message=callback_message,
    )

    await handle_topic_choice(
        callback=callback,
        state=state,
    )

    callback.answer.assert_awaited_once()
    callback_message.edit_text.assert_awaited_once_with(
        "Сценарий отменён.",
    )

    assert state.state is None
    assert state.data == {}
