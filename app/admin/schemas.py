from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TopQuestionOut(BaseModel):
    question: str
    count: int


class StatsOut(BaseModel):
    total_messages: int
    active_users: int
    avg_latency_ms: float | None = None
    moderation_block_rate: float = 0.0
    feedback_up_ratio: float = 0.0
    top_questions: list[TopQuestionOut] = Field(default_factory=list)


class AdminUserOut(BaseModel):
    owner_external_id: str
    interface: str
    chats_count: int
    last_seen_at: datetime | None = None


class AdminUsersOut(BaseModel):
    users: list[AdminUserOut]


class BroadcastIn(BaseModel):
    message: str = Field(min_length=1)
    interface_filter: Literal["telegram"] = "telegram"


class BroadcastOut(BaseModel):
    status: str = "queued"
    broadcast_id: UUID | None = None
