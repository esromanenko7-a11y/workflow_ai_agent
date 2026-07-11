import httpx
import pytest
from pydantic import SecretStr

from app.services.notifier import NotifierSettings, notify_user


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_notify_user_posts_to_bot_notify_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.method == "POST"
        assert request.url.path == "/notify"
        assert request.headers["X-Internal-Token"] == "secret-token"
        assert request.url.host == "bot"

        body = request.read()

        assert b'"chat_id":123' in body
        assert b'"text":"Task completed"' in body

        return httpx.Response(
            status_code=200,
            json={
                "ok": True,
            },
        )

    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://bot",
    ) as client:
        await notify_user(
            chat_id_tg=123,
            text="Task completed",
            settings=NotifierSettings(
                BOT_URL="http://bot",
                INTERNAL_TOKEN=SecretStr("secret-token"),
            ),
            client=client,
        )

    assert len(requests) == 1
