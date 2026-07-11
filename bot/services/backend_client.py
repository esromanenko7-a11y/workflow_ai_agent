from collections.abc import AsyncIterator
from uuid import UUID

import httpx


class BackendClient:
    """
    Тонкий клиент к backend chat-service.

    Бот не знает про LLM, историю и хранилище.
    Он только вызывает HTTP endpoints backend-а.
    """

    def __init__(
        self,
        backend_url: str,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self._chat_cache: dict[tuple[str, str], UUID] = {}

        if client is None:
            self._client = httpx.AsyncClient(
                base_url=self.backend_url,
                timeout=timeout,
            )
            self._owns_client = True
        else:
            self._client = client
            self._owns_client = False

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def get_or_create_chat(
        self,
        owner_external_id: str,
        interface: str,
    ) -> UUID:
        """
        Создаёт чат в backend или возвращает уже известный chat_id.

        Идемпотентность здесь реализована на стороне клиента:
        если в рамках жизни процесса бота уже создавали чат для пары
        owner_external_id + interface, повторно POST /chats не вызываем.
        """
        cache_key = (owner_external_id, interface)

        if cache_key in self._chat_cache:
            return self._chat_cache[cache_key]

        response = await self._client.post(
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
        chat_id: UUID,
        content: str,
        media: bytes | None = None,
        mime: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Отправляет сообщение в backend и возвращает SSE chunks.

        media и mime пока не используются.
        Они добавлены заранее, потому что в Б4.3 этот же метод расширится
        для мультимодальности без создания отдельного media-метода.
        """
        if media is not None or mime is not None:
            raise NotImplementedError(
                "Media support will be added in module 4.3"
            )

        async with self._client.stream(
            "POST",
            f"/chats/{chat_id}/messages",
            json={
                "content": content,
            },
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                if not line.startswith("data: "):
                    continue

                chunk = line.removeprefix("data: ")

                if chunk == "[DONE]":
                    break

                yield chunk

    async def clear_messages(self, chat_id: UUID) -> None:
        response = await self._client.delete(
            f"/chats/{chat_id}/messages",
        )
        response.raise_for_status()
