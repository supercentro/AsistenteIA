import hashlib
import uuid
from typing import NamedTuple

from psycopg import errors as pg_errors
from sqlalchemy import delete, insert, literal, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.subject import Enrollment, Subject
from app.models.user import User


class EnrollmentRow(NamedTuple):
    """An enrollment with the student email (the only student data a teacher sees)."""

    enrollment: Enrollment
    student_email: str


# First integer of the advisory lock "student and subject" (the bytes spell "ENRL"). The two-integer
# form of `pg_advisory_xact_lock` is a different key space from the one-bigint admission lock of the
# documents, so the two can never collide.
ENROLLMENT_LOCK_SPACE = 0x454E524C


def enrollment_lock_key(student_id: uuid.UUID, subject_id: uuid.UUID) -> int:
    """Stable signed 32-bit key of one student in one subject.

    Two different pairs may share a key (it only serialises two unrelated pairs); the same pair
    always gets the same key, which is what the lock needs.
    """
    digest = hashlib.sha256(f"{student_id}:{subject_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big", signed=True)


class EnrollmentRepository:
    """All data access for enrollments. Every operation is scoped by subject owner."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_student_subject(self, student_id: uuid.UUID, subject_id: uuid.UUID) -> None:
        """Take, until this transaction ends, the lock that orders a chat turn and an unenrolment.

        Rules (design D3): a transaction takes at most this one advisory lock and takes it first;
        nobody holds it during embedding or generation; it needs no table privilege.
        """
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(:space, :key)"),
            {"space": ENROLLMENT_LOCK_SPACE, "key": enrollment_lock_key(student_id, subject_id)},
        )

    def add(
        self, subject_id: uuid.UUID, teacher_id: uuid.UUID, student_id: uuid.UUID
    ) -> Enrollment:
        """Enrol a student in a subject owned by `teacher_id`.

        Ownership is part of the INSERT ... SELECT, so a stranger can never create a row. A
        subject that is not owned by the teacher (or that vanished) and a student deleted after
        the lookup raise `NotFoundError`; a duplicate raises `ConflictError`.
        """
        owned_subject = select(Subject.id, literal(student_id, Enrollment.student_id.type)).where(
            Subject.id == subject_id, Subject.teacher_id == teacher_id
        )
        statement = (
            insert(Enrollment)
            .from_select(["subject_id", "student_id"], owned_subject)
            .returning(Enrollment)
        )
        try:
            with self._session.begin_nested():
                enrollment = self._session.execute(statement).scalars().first()
        except IntegrityError as exc:
            if isinstance(exc.orig, pg_errors.UniqueViolation):
                raise ConflictError("Student is already enrolled in this subject") from None
            if isinstance(exc.orig, pg_errors.ForeignKeyViolation):
                # The student was deleted between the lookup and the insert.
                raise NotFoundError("Resource not found") from None
            raise
        if enrollment is None:
            raise NotFoundError("Resource not found")
        return enrollment

    def list_for_teacher_subject(
        self, subject_id: uuid.UUID, teacher_id: uuid.UUID
    ) -> list[EnrollmentRow]:
        statement = (
            select(Enrollment, User.email)
            .join(Subject, Subject.id == Enrollment.subject_id)
            .join(User, User.id == Enrollment.student_id)
            .where(Enrollment.subject_id == subject_id, Subject.teacher_id == teacher_id)
            .order_by(Enrollment.created_at, Enrollment.id)
        )
        return [EnrollmentRow(row[0], row[1]) for row in self._session.execute(statement)]

    def is_enrolled(self, *, student_id: uuid.UUID, subject_id: uuid.UUID) -> bool:
        statement = select(
            select(Enrollment.id)
            .where(
                Enrollment.student_id == student_id,
                Enrollment.subject_id == subject_id,
            )
            .exists()
        )
        result: bool = self._session.execute(statement).scalar_one()
        return result

    def delete_for_teacher_subject(
        self, subject_id: uuid.UUID, teacher_id: uuid.UUID, student_id: uuid.UUID
    ) -> bool:
        self.lock_student_subject(student_id, subject_id)  # before the delete: M2
        owned_subject = select(Subject.id).where(
            Subject.id == subject_id, Subject.teacher_id == teacher_id
        )
        statement = (
            delete(Enrollment)
            .where(
                Enrollment.subject_id == subject_id,
                Enrollment.student_id == student_id,
                Enrollment.subject_id.in_(owned_subject),
            )
            .returning(Enrollment.id)
        )
        return self._session.execute(statement).first() is not None
