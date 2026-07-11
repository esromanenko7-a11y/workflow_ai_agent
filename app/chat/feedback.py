from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


FeedbackValue = Literal["up", "down"]


class MessageFeedback(BaseModel):
    message_id: UUID
    owner_external_id: str
    value: FeedbackValue
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )


class FeedbackIn(BaseModel):
    value: FeedbackValue


class FeedbackOut(BaseModel):
    status: str = "ok"
