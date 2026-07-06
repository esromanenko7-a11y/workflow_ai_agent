from collections.abc import AsyncIterator
from uuid import uuid4

from fastapi.testclient import TestClient

from app.chat.deps import get_chat_service
from app.chat.domain import Chat, ChatMessage
from app.main import app


class FakeChatService:
    def __init__(self) -> None:
        self.chat = Chat(
            id=uuid4(),
            owner_external_id="test-owner",
            interface="cli",
            system_prompt="Test system prompt",
        )
        self.messages: list[ChatMessage] = []
        self.clear_called = False

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        self.chat = Chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )
        return self.chat

    async def get_chat(self, chat_id):
        if chat_id == self.chat.id:
            return self.chat

        return None

    async def list_messages(self, chat_id, limit: int = 50):
        return self.messages[-limit:]

    async def clear_history(self, chat_id) -> None:
        self.clear_called = True
        self.messages = []

    async def send_message(
        self,
        chat_id,
        user_content: str,
    ) -> AsyncIterator[str]:
        self.messages.append(
            ChatMessage(
                chat_id=chat_id,
                role="user",
                content=user_content,
            )
        )

        for chunk in ["Hello", ", ", "world"]:
            yield chunk

        self.messages.append(
            ChatMessage(
                chat_id=chat_id,
                role="assistant",
                content="Hello, world",
            )
        )


def test_create_chat_endpoint() -> None:
    fake_service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)
        response = client.post(
            "/chats",
            json={
                "owner_external_id": "user-1",
                "interface": "cli",
                "system_prompt": "You are helpful.",
            },
        )

        assert response.status_code == 200
        assert response.json()["chat_id"] == str(fake_service.chat.id)
    finally:
        app.dependency_overrides.clear()


def test_get_chat_endpoint() -> None:
    fake_service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)
        response = client.get(f"/chats/{fake_service.chat.id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(fake_service.chat.id)
        assert response.json()["owner_external_id"] == "test-owner"
    finally:
        app.dependency_overrides.clear()


def test_list_messages_endpoint() -> None:
    fake_service = FakeChatService()
    fake_service.messages = [
        ChatMessage(
            chat_id=fake_service.chat.id,
            role="user",
            content="Hello",
        ),
        ChatMessage(
            chat_id=fake_service.chat.id,
            role="assistant",
            content="Hi",
        ),
    ]
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)
        response = client.get(f"/chats/{fake_service.chat.id}/messages")

        assert response.status_code == 200
        assert [item["role"] for item in response.json()] == [
            "user",
            "assistant",
        ]
    finally:
        app.dependency_overrides.clear()


def test_send_message_endpoint_streams_sse() -> None:
    fake_service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)
        with client.stream(
            "POST",
            f"/chats/{fake_service.chat.id}/messages",
            json={"content": "Hi"},
        ) as response:
            body = response.read().decode("utf-8")

        assert response.status_code == 200
        assert "data: Hello" in body
        assert "data: , " in body
        assert "data: world" in body
        assert "data: [DONE]" in body
    finally:
        app.dependency_overrides.clear()


def test_clear_messages_endpoint() -> None:
    fake_service = FakeChatService()
    fake_service.messages = [
        ChatMessage(
            chat_id=fake_service.chat.id,
            role="user",
            content="Hello",
        )
    ]
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)
        response = client.delete(f"/chats/{fake_service.chat.id}/messages")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert fake_service.clear_called is True
    finally:
        app.dependency_overrides.clear()
