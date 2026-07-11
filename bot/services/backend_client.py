import json
from collections.abc import AsyncIterator
from uuid import UUID

import httpx


class BackendClient:
    def __init__(
        self,
        backend_url: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")

        self.default_timeout = httpx.Timeout(
            connect=3.0,
            read=60.0,
            write=10.0,
            pool=5.0,
        )
        self.streaming_timeout = httpx.Timeout(
            connect=3.0,
            read=120.0,
            write=10.0,
            pool=5.0,
        )

        self._own_client = client is None
        self.http = client or httpx.AsyncClient(
            base_url=self.backend_url,
            timeout=self.default_timeout,
            trust_env=False,
        )

        self._chat_cache: dict[tuple[str, str], UUID] = {}

    async def close(self) -> None:
        if self._own_client:
            await self.http.aclose()

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
    ) -> UUID:
        cache_key = (owner_external_id, interface)

        if cache_key in self._chat_cache:
            return self._chat_cache[cache_key]

        response = await self.http.post(
            "/chats",
            json={
                "owner_external_id": owner_external_id,
                "interface": interface,
            },
        )
        response.raise_for_status()

        chat_id = UUID(response.json()["chat_id"])
        self._chat_cache[cache_key] = chat_id

        return chat_id

    async def send_message(
        self,
        chat_id: UUID | str,
        content: str,
        media: bytes | None = None,
        mime: str | None = None,
    ) -> AsyncIterator[str]:
        data = {
            "content": content,
        }

        files = None

        if media is not None:
            files = {
                "media": (
                    "file.bin",
                    media,
                    mime or "application/octet-stream",
                )
            }

        async with self.http.stream(
            "POST",
            f"/chats/{chat_id}/messages",
            data=data,
            files=files,
            timeout=self.streaming_timeout,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                raw_payload = line.removeprefix("data: ").strip()

                if not raw_payload:
                    continue

                payload = json.loads(raw_payload)

                if payload["type"] == "token":
                    yield payload["delta"]
                    continue

                if payload["type"] == "done":
                    return

    async def clear_messages(
        self,
        chat_id: UUID | str,
    ) -> None:
        response = await self.http.delete(
            f"/chats/{chat_id}/messages",
        )
        response.raise_for_status()
