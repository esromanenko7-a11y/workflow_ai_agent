from unittest.mock import AsyncMock

import httpx
import pytest

from bot.web import build_api


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_notify_sends_message_when_internal_token_is_valid() -> None:
    bot = AsyncMock()
    api = build_api(
        bot=bot,
        internal_token="secret-token",
    )

    transport = httpx.ASGITransport(app=api)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://bot",
    ) as client:
        response = await client.post(
            "/notify",
            json={
                "chat_id": 123,
                "text": "Background task completed",
            },
            headers={
                "X-Internal-Token": "secret-token",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
    }

    bot.send_message.assert_awaited_once_with(
        chat_id=123,
        text="Background task completed",
    )


async def test_notify_returns_401_when_internal_token_is_invalid() -> None:
    bot = AsyncMock()
    api = build_api(
        bot=bot,
        internal_token="secret-token",
    )

    transport = httpx.ASGITransport(app=api)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://bot",
    ) as client:
        response = await client.post(
            "/notify",
            json={
                "chat_id": 123,
                "text": "Should not be sent",
            },
            headers={
                "X-Internal-Token": "wrong-token",
            },
        )

    assert response.status_code == 401
    bot.send_message.assert_not_awaited()
