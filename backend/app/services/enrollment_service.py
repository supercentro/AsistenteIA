import logging
import uuid

from app.core.errors import NotFoundError
from app.models.user import User, UserRole
from app.repositories.enrollment_repository import EnrollmentRepository, EnrollmentRow
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from app.services.subject_service import SUBJECT_NOT_FOUND_MESSAGE

logger = logging.getLogger(__name__)

# Same answer for an unknown email and for the email of a non-student account.
STUDENT_NOT_FOUND_MESSAGE = "Student not found"
ENROLLMENT_NOT_FOUND_MESSAGE = "Enrollment not found"


class EnrollmentService:
    """Enrollment use cases for the owning teacher. Never logs or echoes student emails."""

    def __init__(
        self,
        subjects: SubjectRepository,
        enrollments: EnrollmentRepository,
        users: UserRepository,
    ) -> None:
        self._subjects = subjects
        self._enrollments = enrollments
        self._users = users

    def _require_owned_subject(self, teacher: User, subject_id: uuid.UUID) -> uuid.UUID:
        subject = self._subjects.get_for_teacher(subject_id, teacher.id)
        if subject is None:
            raise NotFoundError(SUBJECT_NOT_FOUND_MESSAGE)
        return subject.id

    def enroll(self, teacher: User, subject_id: uuid.UUID, student_email: str) -> EnrollmentRow:
        owned_id = self._require_owned_subject(teacher, subject_id)
        student = self._users.get_by_email(student_email)
        if student is None or student.role is not UserRole.STUDENT:
            raise NotFoundError(STUDENT_NOT_FOUND_MESSAGE)
        try:
            enrollment = self._enrollments.add(owned_id, student.id)
        except NotFoundError:
            # Deleted after the lookups: answer like an unknown email.
            raise NotFoundError(STUDENT_NOT_FOUND_MESSAGE) from None
        logger.info("student enrolled subject=%s student=%s", owned_id, student.id)
        return EnrollmentRow(enrollment, student.email)

    def list_for_subject(self, teacher: User, subject_id: uuid.UUID) -> list[EnrollmentRow]:
        owned_id = self._require_owned_subject(teacher, subject_id)
        return self._enrollments.list_for_teacher_subject(owned_id, teacher.id)

    def remove(self, teacher: User, subject_id: uuid.UUID, student_id: uuid.UUID) -> None:
        owned_id = self._require_owned_subject(teacher, subject_id)
        if not self._enrollments.delete_for_teacher_subject(owned_id, teacher.id, student_id):
            raise NotFoundError(ENROLLMENT_NOT_FOUND_MESSAGE)
        logger.info("student unenrolled subject=%s student=%s", owned_id, student_id)
