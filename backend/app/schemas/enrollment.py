import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.validators import Email


class EnrollmentRequest(BaseModel):
    student_email: Email


class EnrollmentResponse(BaseModel):
    """Enrollment as seen by the owning teacher: ids and the student email, nothing else."""

    id: uuid.UUID
    subject_id: uuid.UUID
    student_id: uuid.UUID
    student_email: str
    created_at: datetime
