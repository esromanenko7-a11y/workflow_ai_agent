from uuid import UUID

import httpx
import pytest

from bot.services.backend_client import BackendClient


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_get_or_create_chat_returns_uuid_and_uses_cache() -> None:
    chat_id = UUID("11111111-1111-1111-1111-111111111111")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "POST"
        assert request.url.path == "/chats"

        return httpx.Response(
            status_code=200,
            json={
                "chat_id": str(chat_id),
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        backend = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        first = await backend.get_or_create_chat(
            owner_external_id="telegram:1",
            interface="telegram",
        )
        second = await backend.get_or_create_chat(
            owner_external_id="telegram:1",
            interface="telegram",
        )

    assert first == chat_id
    assert second == chat_id
    assert len(requests) == 1


async def test_send_message_parses_json_sse_tokens() -> None:
    chat_id = UUID("22222222-2222-2222-2222-222222222222")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/chats/{chat_id}/messages"
        assert request.headers["content-type"].startswith(
            "application/x-www-form-urlencoded"
        )

        body = await request.aread()
        assert b"content=hello" in body

        return httpx.Response(
            status_code=200,
            content=(
                b'data: {"type":"token","delta":"Pri"}\n\n'
                b'data: {"type":"token","delta":"vet"}\n\n'
                b'data: {"type":"token","delta":"!"}\n\n'
                b'data: {"type":"done"}\n\n'
            ),
            headers={
                "content-type": "text/event-stream",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        backend = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        chunks = [
            chunk
            async for chunk in backend.send_message(
                chat_id=chat_id,
                content="hello",
            )
        ]

    assert chunks == [
        {"type": "token", "delta": "Pri"},
        {"type": "token", "delta": "vet"},
        {"type": "token", "delta": "!"},
        {"type": "done"},
    ]


async def test_send_message_with_media_sends_multipart_request() -> None:
    chat_id = UUID("33333333-3333-3333-3333-333333333333")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/chats/{chat_id}/messages"
        assert request.headers["content-type"].startswith(
            "multipart/form-data"
        )

        body = await request.aread()

        assert b'name="content"' in body
        assert b"check this file" in body
        assert b'name="media"' in body
        assert b'filename="file.bin"' in body
        assert b"fake-media-bytes" in body

        return httpx.Response(
            status_code=200,
            content=(
                b'data: {"type":"token","delta":"ok"}\n\n'
                b'data: {"type":"done"}\n\n'
            ),
            headers={
                "content-type": "text/event-stream",
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        backend = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        chunks = [
            chunk
            async for chunk in backend.send_message(
                chat_id=chat_id,
                content="check this file",
                media=b"fake-media-bytes",
                mime="image/png",
            )
        ]

    assert chunks == [
        {"type": "token", "delta": "ok"},
        {"type": "done"},
    ]


async def test_clear_messages_sends_delete_request() -> None:
    chat_id = UUID("44444444-4444-4444-4444-444444444444")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "DELETE"
        assert request.url.path == f"/chats/{chat_id}/messages"

        return httpx.Response(status_code=200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        backend = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        await backend.clear_messages(chat_id)

    assert len(requests) == 1

async def test_save_feedback_sends_post_request() -> None:
    chat_id = UUID("55555555-5555-5555-5555-555555555555")
    message_id = UUID("66666666-6666-6666-6666-666666666666")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            f"/chats/{chat_id}/messages/{message_id}/feedback"
        )
        assert request.url.params["owner_external_id"] == "telegram:123"

        body = await request.aread()
        assert b'"value":"up"' in body

        return httpx.Response(status_code=200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://backend",
    ) as http_client:
        backend = BackendClient(
            backend_url="http://backend",
            client=http_client,
        )

        await backend.save_feedback(
            chat_id=chat_id,
            message_id=message_id,
            owner_external_id="telegram:123",
            value="up",
        )
