"""Pydantic schemas for the /chat endpoint (api-spec.yml ChatResponse, Source)."""

import unicodedata
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    subject_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message", mode="before")
    @classmethod
    def clean_message(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.replace(chr(0), "").strip()
        visible = "".join(
            ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf", "Zs", "Zl", "Zp")
        )
        if not visible:
            raise ValueError("message must contain visible text")
        return text


class SourceSchema(BaseModel):
    """Canonical `Source` of docs/api-spec.yml; shared by the chat answer and the history."""

    chunk_id: uuid.UUID | None
    document_id: uuid.UUID | None
    filename: str
    page_number: int | None
    rank: int
    snippet: str = Field(max_length=300)


Attribution = Literal["cited", "retrieved"]


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    no_material: bool
    sources: list[SourceSchema]
    # Whether the sources were cited by the answer or only retrieved; null without sources.
    attribution: Attribution | None = None
