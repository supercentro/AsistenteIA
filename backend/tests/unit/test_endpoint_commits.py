"""Endpoints that promise persistence commit before they answer (TD-039, change
`database-least-privilege`, 8A.5 to 8A.7).

The handlers are called directly with a recording session and a fake service that writes to the
same list: nothing connects. The commit must come after the service call and before the response,
and a refused commit must roll back and propagate (never a response without stored data).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.v1.endpoints import auth, documents, enrollments, subjects
from app.core.errors import ConflictError
from app.models.subject import Enrollment, Subject
from app.models.user import User, UserRole
from app.repositories.enrollment_repository import EnrollmentRow
from app.schemas.auth import RegisterRequest
from app.schemas.enrollment import EnrollmentRequest
from app.schemas.subject import SubjectCreate

NOW = datetime.now(UTC)
TEACHER = User(
    id=uuid.uuid4(), name="T", email="t@example.com", password_hash="h", role=UserRole.TEACHER
)


class Recorder:
    """Session and service in one: the order of the calls is what the tests assert."""

    def __init__(
        self, commit_error: Exception | None = None, service_error: Exception | None = None
    ):
        self.calls: list[str] = []
        self.commit_error = commit_error
        self.service_error = service_error

    # --- session
    def commit(self) -> None:
        self.calls.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.calls.append("rollback")

    # --- services
    def _run(self, name: str) -> None:
        self.calls.append(name)
        if self.service_error is not None:
            raise self.service_error

    def register_student(self, name: str, email: str, password: str) -> User:
        self._run("service")
        return User(
            id=uuid.uuid4(),
            name=name,
            email=email,
            password_hash="h",
            role=UserRole.STUDENT,
            created_at=NOW,
        )

    def create(self, teacher: User, data: SubjectCreate) -> Subject:
        self._run("service")
        return Subject(
            id=uuid.uuid4(),
            name=data.name,
            description=data.description,
            teacher_id=teacher.id,
            created_at=NOW,
        )

    def delete(self, *args: object) -> None:  # a subject, or a document (teacher id first)
        self._run("service")

    def enroll(self, teacher: User, subject_id: uuid.UUID, student_email: str) -> EnrollmentRow:
        self._run("service")
        enrollment = Enrollment(
            id=uuid.uuid4(), subject_id=subject_id, student_id=uuid.uuid4(), created_at=NOW
        )
        return EnrollmentRow(enrollment=enrollment, student_email=student_email)

    def remove(self, teacher: User, subject_id: uuid.UUID, student_id: uuid.UUID) -> None:
        self._run("service")


def session_of(recorder: Recorder) -> Session:
    return cast(Session, recorder)


def register(r: Recorder) -> Any:
    body = RegisterRequest(name="Ana", email="ana@example.com", password="a-very-long-password")
    return auth.register(body, cast(Any, r), session_of(r))


def create_subject(r: Recorder) -> Any:
    return subjects.create_subject(
        SubjectCreate(name="Algebra"), TEACHER, cast(Any, r), session_of(r)
    )


def delete_subject(r: Recorder) -> Any:
    return subjects.delete_subject(uuid.uuid4(), TEACHER, cast(Any, r), session_of(r))


def delete_document(r: Recorder) -> Any:
    return documents.delete_document(
        TEACHER, uuid.uuid4(), uuid.uuid4(), cast(Any, r), session_of(r)
    )


def enroll(r: Recorder) -> Any:
    body = EnrollmentRequest(student_email="s@example.com")
    return enrollments.enroll_student(uuid.uuid4(), body, TEACHER, cast(Any, r), session_of(r))


def remove(r: Recorder) -> Any:
    return enrollments.remove_enrollment(
        uuid.uuid4(), uuid.uuid4(), TEACHER, cast(Any, r), session_of(r)
    )


OPERATIONS: dict[str, Callable[[Recorder], Any]] = {
    "register": register,
    "create-subject": create_subject,
    "delete-subject": delete_subject,
    "delete-document": delete_document,
    "enroll": enroll,
    "remove-enrollment": remove,
}
REFUSAL = OperationalError("COMMIT", {}, Exception("commit refused by the database"))


@pytest.mark.parametrize("name", OPERATIONS)
def test_the_commit_follows_the_service_and_precedes_the_response(name: str) -> None:
    recorder = Recorder()

    response = OPERATIONS[name](recorder)

    assert recorder.calls == ["service", "commit"]  # exactly one commit, after the write
    assert response is not None


@pytest.mark.parametrize("name", OPERATIONS)
def test_a_refused_commit_rolls_back_and_never_returns_a_response(name: str) -> None:
    recorder = Recorder(commit_error=REFUSAL)

    with pytest.raises(OperationalError):
        OPERATIONS[name](recorder)

    assert recorder.calls == ["service", "commit", "rollback"]


@pytest.mark.parametrize("name", OPERATIONS)
def test_an_error_of_the_service_commits_nothing(name: str) -> None:
    recorder = Recorder(service_error=ConflictError("duplicate"))

    with pytest.raises(ConflictError):
        OPERATIONS[name](recorder)

    assert recorder.calls == ["service"]  # no commit and no explicit rollback: get_db rolls back


def test_a_failure_after_the_commit_is_an_error_but_the_data_stays_committed() -> None:
    """Inherent to commit-then-respond (review L2): the 500 does not undo a committed write."""

    class BrokenResponse(Recorder):
        def register_student(self, name: str, email: str, password: str) -> User:
            self._run("service")
            return User(name=name, email=email, password_hash="h")  # no id: the schema rejects it

    recorder = BrokenResponse()

    with pytest.raises(ValidationError):
        register(recorder)

    assert recorder.calls == ["service", "commit"]  # committed; no rollback after the commit
