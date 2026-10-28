import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.validators import Description, SubjectName


class SubjectCreate(BaseModel):
    name: SubjectName
    description: Description | None = None


class SubjectResponse(BaseModel):
    """Subject as returned to its owner teacher and to enrolled students."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    teacher_id: uuid.UUID
    created_at: datetime
