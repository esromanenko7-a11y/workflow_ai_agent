import json
from collections.abc import AsyncIterator
from uuid import UUID

import httpx


class BackendClient:
    def __init__(
        self,
        backend_url: str,
        client: httpx.AsyncClient | None = None,
        admin_token: str | None = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.admin_token = admin_token

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
    ) -> AsyncIterator[dict]:
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
                yield payload

                if payload.get("type") == "done":
                    return

    async def save_feedback(
        self,
        chat_id: UUID | str,
        message_id: UUID | str,
        owner_external_id: str,
        value: str,
    ) -> None:
        response = await self.http.post(
            f"/chats/{chat_id}/messages/{message_id}/feedback",
            params={
                "owner_external_id": owner_external_id,
            },
            json={
                "value": value,
            },
        )
        response.raise_for_status()

    def _admin_headers(self) -> dict[str, str]:
        if not self.admin_token:
            raise RuntimeError("ADMIN_TOKEN is not configured for bot")

        return {
            "X-Admin-Token": self.admin_token,
        }

    async def get_admin_stats(self) -> dict:
        response = await self.http.get(
            "/chats/admin/stats",
            headers=self._admin_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def get_admin_users(
        self,
        limit: int = 50,
    ) -> dict:
        response = await self.http.get(
            "/chats/admin/users",
            params={
                "limit": limit,
            },
            headers=self._admin_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def enqueue_broadcast(
        self,
        message: str,
        interface_filter: str = "telegram",
    ) -> dict:
        response = await self.http.post(
            "/chats/admin/broadcast",
            headers=self._admin_headers(),
            json={
                "message": message,
                "interface_filter": interface_filter,
            },
        )
        response.raise_for_status()
        return response.json()

    async def list_pending_broadcasts(
        self,
        interface_filter: str = "telegram",
        limit: int = 10,
    ) -> dict:
        response = await self.http.get(
            "/chats/admin/broadcasts/pending",
            params={
                "interface_filter": interface_filter,
                "limit": limit,
            },
            headers=self._admin_headers(),
        )
        response.raise_for_status()
        return response.json()

    async def mark_broadcast_sent(
        self,
        broadcast_id: str,
    ) -> None:
        response = await self.http.post(
            f"/chats/admin/broadcasts/{broadcast_id}/sent",
            headers=self._admin_headers(),
        )
        response.raise_for_status()

    async def clear_messages(
        self,
        chat_id: UUID | str,
    ) -> None:
        response = await self.http.delete(
            f"/chats/{chat_id}/messages",
        )
        response.raise_for_status()
