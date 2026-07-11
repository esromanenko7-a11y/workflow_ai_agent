from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.domain import Chat, ChatMessage
from app.chat.repositories.pg_models import ChatMessageRow, ChatRow


class PostgresChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        row = ChatRow(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )

        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)

        return Chat.model_validate(row, from_attributes=True)

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        row = await self.session.get(ChatRow, chat_id)

        if row is None:
            return None

        return Chat.model_validate(row, from_attributes=True)

    async def append_message(
        self,
        chat_id: UUID,
        message: ChatMessage,
    ) -> ChatMessage:
        if message.chat_id != chat_id:
            raise ValueError("message.chat_id must match chat_id")

        row = ChatMessageRow(
            id=message.id,
            chat_id=chat_id,
            role=message.role,
            content=message.content,
            tokens=message.tokens,
            created_at=message.created_at,
        )

        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)

        return ChatMessage.model_validate(row, from_attributes=True)

    async def list_messages(
        self,
        chat_id: UUID,
        limit: int = 50,
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []

        statement = (
            select(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id)
            .where(ChatMessageRow.deleted_at.is_(None))
            .order_by(ChatMessageRow.created_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(statement)
        rows = list(result.scalars().all())
        rows.reverse()

        return [
            ChatMessage.model_validate(row, from_attributes=True)
            for row in rows
        ]

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        statement = (
            update(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id)
            .where(ChatMessageRow.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

        await self.session.execute(statement)
        await self.session.commit()
