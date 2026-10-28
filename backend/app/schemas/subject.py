import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.validators import Description, SubjectName


class SubjectCreate(BaseModel):
    name: SubjectName
    description: Description | None = None

    @field_validator("description")
    @classmethod
    def blank_description_is_none(cls, value: str | None) -> str | None:
        """A description that is empty after trimming is stored as null."""
        return value or None


class SubjectResponse(BaseModel):
    """Subject as returned to its owner teacher and to enrolled students."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    teacher_id: uuid.UUID
    created_at: datetime
