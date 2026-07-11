import pytest

from app.chat.domain import ChatMessage
from app.chat.service import ChatService


pytestmark = pytest.mark.anyio


class FakeDelta:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.delta = FakeDelta(content)


class FakeChunk:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeStream:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield FakeChunk(chunk)


class FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(["ok"])


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeLLMClient:
    def __init__(self) -> None:
        self.chat = FakeChat()


async def test_service_saves_media_refs_and_builds_content_parts(repository):
    llm_client = FakeLLMClient()

    service = ChatService(
        repository=repository,
        llm_client=llm_client,
        default_model="test-model",
        context_window=10,
    )

    chat = await service.create_chat(
        owner_external_id="media-service-user",
        interface="test",
        system_prompt="System prompt",
    )

    media_refs = {
        "mime": "application/pdf",
        "size": 123,
        "filename": "package-report.pdf",
        "part": {
            "type": "text",
            "text": "[документ PDF]:\nОшибка обязательного поля",
        },
    }

    chunks = [
        chunk
        async for chunk in service.send_message(
            chat_id=chat.id,
            user_content="Проверь документ",
            media_refs=media_refs,
        )
    ]

    assert chunks[0] == {
        "type": "token",
        "delta": "ok",
    }
    assert chunks[1]["type"] == "done"
    assert "message_id" in chunks[1]

    saved_messages = await repository.list_messages(chat.id)
    assert saved_messages[0].role == "user"
    assert saved_messages[0].media_refs == media_refs
    assert saved_messages[1].role == "assistant"
    assert saved_messages[1].content == "ok"

    call = llm_client.chat.completions.calls[0]

    assert call["model"] == "test-model"
    assert call["stream"] is True

    sent_messages = call["messages"]
    assert sent_messages[0] == {
        "role": "system",
        "content": "System prompt",
    }

    user_message = sent_messages[1]
    assert user_message["role"] == "user"
    assert user_message["content"] == [
        {
            "type": "text",
            "text": "Проверь документ",
        },
        media_refs["part"],
    ]
