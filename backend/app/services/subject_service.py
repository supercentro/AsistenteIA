import logging
import uuid

from app.core.errors import NotFoundError
from app.models.subject import Subject
from app.models.user import User, UserRole
from app.repositories.subject_repository import SubjectRepository
from app.schemas.subject import SubjectCreate

logger = logging.getLogger(__name__)

# One message for "missing" and "not accessible": the response never reveals which one it was.
SUBJECT_NOT_FOUND_MESSAGE = "Subject not found"


class SubjectService:
    """Subject use cases. Role checks happen in the API dependencies; visibility is scoped here."""

    def __init__(self, subjects: SubjectRepository) -> None:
        self._subjects = subjects

    def create(self, teacher: User, data: SubjectCreate) -> Subject:
        subject = self._subjects.add(
            Subject(name=data.name, description=data.description, teacher_id=teacher.id)
        )
        logger.info("subject created id=%s teacher=%s", subject.id, teacher.id)
        return subject

    def list_visible(self, user: User) -> list[Subject]:
        if user.role is UserRole.TEACHER:
            return self._subjects.list_for_teacher(user.id)
        return self._subjects.list_for_student(user.id)

    def get_visible(self, user: User, subject_id: uuid.UUID) -> Subject:
        if user.role is UserRole.TEACHER:
            subject = self._subjects.get_for_teacher(subject_id, user.id)
        else:
            subject = self._subjects.get_for_student(subject_id, user.id)
        if subject is None:
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)
        return subject

    def delete(self, teacher: User, subject_id: uuid.UUID) -> None:
        if not self._subjects.delete_for_teacher(subject_id, teacher.id):
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)
        logger.info("subject deleted id=%s teacher=%s", subject_id, teacher.id)
