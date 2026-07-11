from collections.abc import AsyncIterator
from uuid import UUID

from fastapi.testclient import TestClient

from app.chat.deps import get_chat_service
from app.chat.domain import Chat, ChatMessage
from app.main import app


class FakeChatService:
    def __init__(self) -> None:
        self.chat = Chat(
            owner_external_id="test-user",
            interface="test",
            system_prompt="System prompt",
        )
        self.clear_called = False
        self.last_user_content: str | None = None
        self.last_media_refs: dict | None = None

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

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        if chat_id == self.chat.id:
            return self.chat

        return None

    async def list_messages(
        self,
        chat_id: UUID,
        limit: int = 50,
    ) -> list[ChatMessage]:
        return [
            ChatMessage(
                chat_id=chat_id,
                role="user",
                content="hello",
            )
        ]

    async def send_message(
        self,
        chat_id: UUID,
        user_content: str,
        media_refs: dict | None = None,
    ) -> AsyncIterator[str]:
        self.last_user_content = user_content
        self.last_media_refs = media_refs

        yield "one"
        yield "two"

    async def clear_history(self, chat_id: UUID) -> None:
        self.clear_called = True


def test_create_chat_endpoint() -> None:
    fake_service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)

        response = client.post(
            "/chats",
            json={
                "owner_external_id": "user-1",
                "interface": "telegram",
                "system_prompt": "You are helpful",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "chat_id": str(fake_service.chat.id),
        }
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
        assert response.json()["owner_external_id"] == "test-user"
    finally:
        app.dependency_overrides.clear()


def test_list_messages_endpoint() -> None:
    fake_service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)

        response = client.get(
            f"/chats/{fake_service.chat.id}/messages",
        )

        assert response.status_code == 200
        assert response.json()[0]["role"] == "user"
        assert response.json()[0]["content"] == "hello"
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
            data={
                "content": "Hi",
            },
        ) as response:
            body = response.read().decode("utf-8")

        assert response.status_code == 200
        assert fake_service.last_user_content == "Hi"
        assert fake_service.last_media_refs is None
        assert body == (
            'data: {"type": "token", "delta": "one"}\n\n'
            'data: {"type": "token", "delta": "two"}\n\n'
            'data: {"type": "done"}\n\n'
        )
    finally:
        app.dependency_overrides.clear()


def test_clear_messages_endpoint() -> None:
    fake_service = FakeChatService()
    app.dependency_overrides[get_chat_service] = lambda: fake_service

    try:
        client = TestClient(app)

        response = client.delete(
            f"/chats/{fake_service.chat.id}/messages",
        )

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
        }
        assert fake_service.clear_called is True
    finally:
        app.dependency_overrides.clear()
