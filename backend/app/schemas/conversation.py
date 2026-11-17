"""Pydantic schemas for conversation endpoints (api-spec.yml Conversation, Message)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.chat import SourceSchema


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_id: uuid.UUID
    created_at: datetime
    last_message_preview: str | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    sources: list[SourceSchema] = []
