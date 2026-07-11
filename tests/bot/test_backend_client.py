from uuid import UUID

import httpx
import pytest

from bot.services.backend_client import BackendClient


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_get_or_create_chat_returns_uuid_and_is_idempotent() -> None:
    chat_id = UUID("11111111-1111-1111-1111-111111111111")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "POST"
        assert request.url.path == "/chats"

        return httpx.Response(
            200,
            json={
                "chat_id": str(chat_id),
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        client = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        first_result = await client.get_or_create_chat(
            owner_external_id="123",
            interface="telegram",
        )
        second_result = await client.get_or_create_chat(
            owner_external_id="123",
            interface="telegram",
        )

    assert first_result == chat_id
    assert second_result == chat_id
    assert len(requests) == 1


async def test_send_message_parses_sse_stream() -> None:
    chat_id = UUID("22222222-2222-2222-2222-222222222222")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/chats/{chat_id}/messages"

        return httpx.Response(
            200,
            content=(
                "data: При\n\n"
                "data: вет\n\n"
                "data: !\n\n"
                "data: [DONE]\n\n"
            ).encode("utf-8"),
            headers={
                "content-type": "text/event-stream",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        client = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        chunks = [
            chunk
            async for chunk in client.send_message(
                chat_id=chat_id,
                content="Привет",
            )
        ]

    assert chunks == ["При", "вет", "!"]


async def test_clear_messages_sends_delete_to_backend() -> None:
    chat_id = UUID("33333333-3333-3333-3333-333333333333")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "DELETE"
        assert request.url.path == f"/chats/{chat_id}/messages"

        return httpx.Response(
            200,
            json={
                "status": "ok",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        client = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        await client.clear_messages(chat_id)

    assert len(requests) == 1
