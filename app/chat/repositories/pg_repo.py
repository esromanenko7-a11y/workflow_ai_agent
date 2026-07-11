from datetime import UTC, timedelta, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.domain import Chat, ChatMessage
from app.chat.repositories.pg_models import BroadcastQueueRow, ChatMessageRow, ChatRow, MessageFeedbackRow


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
            media_refs=message.media_refs,
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

    async def get_admin_stats(self) -> dict:
        since = datetime.now(UTC) - timedelta(hours=24)

        total_messages = await self.session.scalar(
            select(func.count())
            .select_from(ChatMessageRow)
            .where(ChatMessageRow.created_at >= since)
            .where(ChatMessageRow.deleted_at.is_(None))
        )

        active_users = await self.session.scalar(
            select(func.count(func.distinct(ChatRow.owner_external_id)))
            .select_from(ChatMessageRow)
            .join(ChatRow, ChatMessageRow.chat_id == ChatRow.id)
            .where(ChatMessageRow.created_at >= since)
            .where(ChatMessageRow.deleted_at.is_(None))
        )

        feedback_total = await self.session.scalar(
            select(func.count())
            .select_from(MessageFeedbackRow)
            .where(MessageFeedbackRow.created_at >= since)
        )

        feedback_up = await self.session.scalar(
            select(func.count())
            .select_from(MessageFeedbackRow)
            .where(MessageFeedbackRow.created_at >= since)
            .where(MessageFeedbackRow.value == "up")
        )

        feedback_up_ratio = 0.0

        if feedback_total:
            feedback_up_ratio = float(feedback_up or 0) / float(feedback_total)

        return {
            "total_messages": int(total_messages or 0),
            "active_users": int(active_users or 0),
            "avg_latency_ms": None,
            "moderation_block_rate": 0.0,
            "feedback_up_ratio": feedback_up_ratio,
            "top_questions": [],
        }

    async def list_admin_users(
        self,
        limit: int = 50,
    ) -> list[dict]:
        statement = (
            select(
                ChatRow.owner_external_id,
                ChatRow.interface,
                func.count(func.distinct(ChatRow.id)).label("chats_count"),
                func.coalesce(
                    func.max(ChatMessageRow.created_at),
                    func.max(ChatRow.created_at),
                ).label("last_seen_at"),
            )
            .select_from(ChatRow)
            .outerjoin(ChatMessageRow, ChatMessageRow.chat_id == ChatRow.id)
            .group_by(ChatRow.owner_external_id, ChatRow.interface)
            .order_by(func.coalesce(
                func.max(ChatMessageRow.created_at),
                func.max(ChatRow.created_at),
            ).desc())
            .limit(limit)
        )

        rows = (await self.session.execute(statement)).all()

        return [
            {
                "owner_external_id": row.owner_external_id,
                "interface": row.interface,
                "chats_count": int(row.chats_count or 0),
                "last_seen_at": row.last_seen_at,
            }
            for row in rows
        ]

    async def enqueue_broadcast(
        self,
        message: str,
        interface_filter: str,
    ) -> UUID:
        row = BroadcastQueueRow(
            message=message,
            interface=interface_filter,
            status="pending",
        )

        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)

        return row.id

    async def list_pending_broadcasts(
        self,
        interface_filter: str = "telegram",
        limit: int = 10,
    ) -> list[dict]:
        statement = (
            select(BroadcastQueueRow)
            .where(BroadcastQueueRow.interface == interface_filter)
            .where(BroadcastQueueRow.status == "pending")
            .order_by(BroadcastQueueRow.created_at.asc())
            .limit(limit)
        )

        rows = (await self.session.execute(statement)).scalars().all()

        return [
            {
                "id": row.id,
                "message": row.message,
                "interface": row.interface,
                "status": row.status,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    async def mark_broadcast_sent(
        self,
        broadcast_id: UUID,
    ) -> None:
        statement = (
            update(BroadcastQueueRow)
            .where(BroadcastQueueRow.id == broadcast_id)
            .values(
                status="sent",
                sent_at=func.now(),
            )
        )

        await self.session.execute(statement)
        await self.session.commit()

    async def save_feedback(
        self,
        message_id: UUID,
        owner_external_id: str,
        value: str,
    ) -> None:
        statement = (
            insert(MessageFeedbackRow)
            .values(
                message_id=message_id,
                owner_external_id=owner_external_id,
                value=value,
            )
            .on_conflict_do_update(
                constraint="uq_message_feedback_owner_message",
                set_={
                    "value": value,
                    "created_at": func.now(),
                },
            )
        )

        await self.session.execute(statement)
        await self.session.commit()

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        statement = (
            update(ChatMessageRow)
            .where(ChatMessageRow.chat_id == chat_id)
            .where(ChatMessageRow.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

        await self.session.execute(statement)
        await self.session.commit()
