import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import aiofiles

from app.chat.domain import Chat, ChatMessage


class JsonChatRepository:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.chats_dir = self.base_dir / "chats"

    def _chat_dir(self, chat_id: UUID) -> Path:
        return self.chats_dir / str(chat_id)

    def _chat_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "chat.json"

    def _messages_path(self, chat_id: UUID) -> Path:
        return self._chat_dir(chat_id) / "messages.jsonl"

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: str | None = None,
    ) -> Chat:
        chat = Chat(
            owner_external_id=owner_external_id,
            interface=interface,
            system_prompt=system_prompt,
        )

        chat_dir = self._chat_dir(chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(
            self._chat_path(chat.id),
            mode="w",
            encoding="utf-8",
        ) as file:
            await file.write(chat.model_dump_json())

        messages_path = self._messages_path(chat.id)
        messages_path.touch(exist_ok=True)

        return chat

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        chat_path = self._chat_path(chat_id)

        if not chat_path.exists():
            return None

        async with aiofiles.open(
            chat_path,
            mode="r",
            encoding="utf-8",
        ) as file:
            raw_chat = await file.read()

        return Chat.model_validate_json(raw_chat)

    async def append_message(
        self,
        chat_id: UUID,
        message: ChatMessage,
    ) -> ChatMessage:
        if message.chat_id != chat_id:
            raise ValueError("message.chat_id must match chat_id")

        chat_dir = self._chat_dir(chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(
            self._messages_path(chat_id),
            mode="a",
            encoding="utf-8",
        ) as file:
            await file.write(message.model_dump_json())
            await file.write("\n")

        return message

    async def list_messages(
        self,
        chat_id: UUID,
        limit: int = 50,
    ) -> list[ChatMessage]:
        messages_path = self._messages_path(chat_id)

        if not messages_path.exists():
            return []

        async with aiofiles.open(
            messages_path,
            mode="r",
            encoding="utf-8",
        ) as file:
            lines = await file.readlines()

        last_soft_delete_index = -1

        for index, line in enumerate(lines):
            if not line.strip():
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "soft_delete":
                last_soft_delete_index = index

        visible_lines = lines[last_soft_delete_index + 1 :]
        messages: list[ChatMessage] = []

        for line in visible_lines:
            if not line.strip():
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            if payload.get("type") == "soft_delete":
                continue

            messages.append(ChatMessage.model_validate(payload))

        return messages[-limit:]

    async def get_admin_stats(self) -> dict:
        return {
            "total_messages": 0,
            "active_users": 0,
            "avg_latency_ms": None,
            "moderation_block_rate": 0.0,
            "feedback_up_ratio": 0.0,
            "top_questions": [],
        }

    async def list_admin_users(
        self,
        limit: int = 50,
    ) -> list[dict]:
        return []

    async def enqueue_broadcast(
        self,
        message: str,
        interface_filter: str,
    ) -> UUID:
        broadcast_id = uuid4()
        broadcast_path = self.storage_dir / "broadcast_queue.jsonl"

        record = {
            "id": str(broadcast_id),
            "message": message,
            "interface": interface_filter,
            "status": "pending",
        }

        with broadcast_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

        return broadcast_id

    async def list_pending_broadcasts(
        self,
        interface_filter: str = "telegram",
        limit: int = 10,
    ) -> list[dict]:
        broadcast_path = self.storage_dir / "broadcast_queue.jsonl"

        if not broadcast_path.exists():
            return []

        result: list[dict] = []

        for line in broadcast_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            item = json.loads(line)

            if (
                item.get("interface") == interface_filter
                and item.get("status") == "pending"
            ):
                result.append(item)

            if len(result) >= limit:
                break

        return result

    async def mark_broadcast_sent(
        self,
        broadcast_id: UUID,
    ) -> None:
        broadcast_path = self.storage_dir / "broadcast_queue.jsonl"

        if not broadcast_path.exists():
            return

        lines = []

        for line in broadcast_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            item = json.loads(line)

            if item.get("id") == str(broadcast_id):
                item["status"] = "sent"

            lines.append(json.dumps(item, ensure_ascii=False))

        broadcast_path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    async def save_feedback(
        self,
        message_id: UUID,
        owner_external_id: str,
        value: str,
    ) -> None:
        feedback_path = self.storage_dir / "message_feedback.jsonl"

        record = {
            "message_id": str(message_id),
            "owner_external_id": owner_external_id,
            "value": value,
        }

        lines: list[str] = []

        if feedback_path.exists():
            lines = feedback_path.read_text(
                encoding="utf-8",
            ).splitlines()

        filtered_lines = []

        for line in lines:
            if not line.strip():
                continue

            item = json.loads(line)

            if (
                item.get("message_id") == str(message_id)
                and item.get("owner_external_id") == owner_external_id
            ):
                continue

            filtered_lines.append(line)

        filtered_lines.append(
            json.dumps(record, ensure_ascii=False)
        )

        feedback_path.write_text(
            "\n".join(filtered_lines) + "\n",
            encoding="utf-8",
        )

    async def soft_delete_messages(self, chat_id: UUID) -> None:
        chat_dir = self._chat_dir(chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)

        marker = {
            "type": "soft_delete",
            "at": datetime.now(UTC).isoformat(),
        }

        async with aiofiles.open(
            self._messages_path(chat_id),
            mode="a",
            encoding="utf-8",
        ) as file:
            await file.write(json.dumps(marker, ensure_ascii=False))
            await file.write("\n")