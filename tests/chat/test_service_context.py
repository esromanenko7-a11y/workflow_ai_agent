from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.chat.domain import ChatMessage
from app.chat.repository import ChatRepository
from app.chat.service import ChatService, count_tokens, fit_to_budget


pytestmark = pytest.mark.anyio


class FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks

    def __aiter__(self):
        self._iterator = iter(self.chunks)
        return self

    async def __anext__(self):
        try:
            content = next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=content),
                )
            ]
        )


class FakeCompletions:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.chunks)


class FakeChat:
    def __init__(self, chunks: list[str]) -> None:
        self.completions = FakeCompletions(chunks)


class FakeLLMClient:
    def __init__(self, chunks: list[str]) -> None:
        self.chat = FakeChat(chunks)


async def test_send_message_streams_and_persists_assistant_response(
    repository: ChatRepository,
) -> None:
    llm_client = FakeLLMClient(chunks=["Hello", ", user"])
    service = ChatService(
        repository=repository,
        llm_client=llm_client,
        default_model="test-model",
        context_window=10,
    )

    chat = await service.create_chat(
        owner_external_id="test-user",
        interface="cli",
        system_prompt="You are a helpful assistant.",
    )

    chunks = [
        chunk async for chunk in service.send_message(chat.id, "Hi")
    ]

    assert chunks == ["Hello", ", user"]

    messages = await repository.list_messages(chat.id)

    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "Hi"
    assert messages[1].content == "Hello, user"

    call = llm_client.chat.completions.calls[0]

    assert call["model"] == "test-model"
    assert call["stream"] is True
    assert call["messages"][0] == {
        "role": "system",
        "content": "You are a helpful assistant.",
    }


async def test_send_message_uses_sliding_window_context(
    repository: ChatRepository,
) -> None:
    llm_client = FakeLLMClient(chunks=["ok"])
    service = ChatService(
        repository=repository,
        llm_client=llm_client,
        context_window=2,
    )

    chat = await service.create_chat(
        owner_external_id="test-user",
        interface="cli",
        system_prompt="System prompt",
    )

    await repository.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="user", content="old-1"),
    )
    await repository.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="assistant", content="old-2"),
    )
    await repository.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="user", content="old-3"),
    )

    _ = [
        chunk async for chunk in service.send_message(chat.id, "current")
    ]

    call_messages = llm_client.chat.completions.calls[0]["messages"]

    assert [message["content"] for message in call_messages] == [
        "System prompt",
        "old-3",
        "current",
    ]


async def test_clear_history_delegates_to_repository(
    repository: ChatRepository,
) -> None:
    llm_client = FakeLLMClient(chunks=["ok"])
    service = ChatService(repository=repository, llm_client=llm_client)

    chat = await service.create_chat(
        owner_external_id="test-user",
        interface="cli",
    )

    await repository.append_message(
        chat.id,
        ChatMessage(chat_id=chat.id, role="user", content="old"),
    )

    await service.clear_history(chat.id)

    assert await repository.list_messages(chat.id) == []


async def test_send_message_unknown_chat_raises_value_error(
    repository: ChatRepository,
) -> None:
    llm_client = FakeLLMClient(chunks=["ok"])
    service = ChatService(repository=repository, llm_client=llm_client)

    with pytest.raises(ValueError, match="Chat not found"):
        _ = [
            chunk async for chunk in service.send_message(uuid4(), "hello")
        ]


def test_count_tokens_returns_positive_number() -> None:
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]

    assert count_tokens(messages) > 0


def test_fit_to_budget_preserves_system_message() -> None:
    messages = [
        {"role": "system", "content": "Important system prompt"},
        {"role": "user", "content": "old message " * 100},
        {"role": "assistant", "content": "old answer " * 100},
        {"role": "user", "content": "new message"},
    ]

    fitted = fit_to_budget(messages, budget=30)

    assert fitted[0]["role"] == "system"
    assert fitted[0]["content"] == "Important system prompt"
    assert len(fitted) < len(messages)
