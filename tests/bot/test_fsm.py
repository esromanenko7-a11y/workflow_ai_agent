from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.fsm import ask_start_handler, topic_selected_handler
from bot.states import AskFlow


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeState:
    def __init__(self) -> None:
        self.state = None
        self.data: dict[str, str] = {}

    async def set_state(self, state) -> None:
        self.state = state

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict[str, str]:
        return self.data

    async def clear(self) -> None:
        self.state = None
        self.data.clear()


async def test_ask_flow_select_topic_updates_state_and_data() -> None:
    state = FakeState()

    message = SimpleNamespace(
        answer=AsyncMock(),
    )

    await ask_start_handler(
        message=message,
        state=state,
    )

    assert state.state == AskFlow.waiting_for_topic
    message.answer.assert_awaited_once()

    callback_message = SimpleNamespace(
        edit_text=AsyncMock(),
    )
    callback = SimpleNamespace(
        data="topic:package_errors",
        message=callback_message,
        answer=AsyncMock(),
    )

    await topic_selected_handler(
        callback=callback,
        state=state,
    )

    assert state.state == AskFlow.waiting_for_question
    assert state.data["topic"] == "Ошибки пакета"

    callback_message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once()
