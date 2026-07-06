from typing import Protocol
from uuid import UUID

from app.chat.domain import Chat, ChatMessage


class ChatRepository(Protocol):
    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        """Создать новый чат."""
        ...

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        """Получить метаданные чата или None, если чат не найден."""
        ...

    async def append_message(
        self,
        chat_id: UUID,
        message: ChatMessage,
    ) -> ChatMessage:
        """Добавить сообщение в историю чата."""
        ...

    async def list_messages(
        self,
        chat_id: UUID,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """Вернуть последние limit сообщений в хронологическом порядке."""
        ...

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        """Мягко очистить историю сообщений чата."""
        ...