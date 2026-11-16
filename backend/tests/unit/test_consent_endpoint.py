"""POST /users/me/consent commits before it answers (change `database-least-privilege`, group 7).

The handler is called directly with a recording session: nothing connects. Until now the commit
happened when the request-scoped session was closed, after the 200 had been built, so a refused
`UPDATE` was answered with success and nothing stored.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.users import record_consent
from app.core.config import Settings
from app.core.errors import InvalidConsentVersionError
from app.models.user import User, UserRole
from app.schemas.consent import ConsentRequest
from app.services.consent_service import ConsentService
from tests.constants import TEST_JWT_SECRET

CURRENT = "2026-10-v1"


class RecordingSession:
    """Remembers the calls in order and can refuse the commit like PostgreSQL would."""

    def __init__(self, commit_error: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.commit_error = commit_error

    def commit(self) -> None:
        self.calls.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self) -> None:
        self.calls.append("rollback")


def make_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/x_test", jwt_secret=TEST_JWT_SECRET
    )


def make_user() -> User:
    return User(
        id=uuid.uuid4(),
        name="N",
        email="n@example.com",
        password_hash="h",
        role=UserRole.STUDENT,
        created_at=datetime.now(UTC),
    )


def call(session: RecordingSession, user: User, version: str = CURRENT) -> Any:
    return record_consent(
        ConsentRequest(consent_version=version),
        user,
        ConsentService(make_settings()),
        cast(Session, session),
    )


def test_the_commit_happens_inside_the_handler_after_the_user_is_updated() -> None:
    session, user = RecordingSession(), make_user()

    response = call(session, user)

    assert session.calls == ["commit"]  # exactly once, before the response is returned
    assert response.consent_version == CURRENT and response.consent_accepted_at is not None
    assert user.consent_version == CURRENT


def test_a_refused_commit_is_an_error_and_rolls_the_session_back() -> None:
    refusal = ProgrammingError(
        "UPDATE users ...", {}, Exception("permission denied for table users")
    )
    session, user = RecordingSession(refusal), make_user()

    with pytest.raises(ProgrammingError):
        call(session, user)

    assert session.calls == ["commit", "rollback"]  # never a response without stored evidence


def test_any_commit_failure_is_rolled_back_and_propagated_even_if_the_rollback_fails() -> None:
    class FailingRollback(RecordingSession):
        def rollback(self) -> None:
            super().rollback()
            raise RuntimeError("rollback failed")

    session, user = FailingRollback(ValueError("not a SQLAlchemy error")), make_user()

    with pytest.raises(RuntimeError):  # still an error for the caller, never a response
        call(session, user)

    assert session.calls == ["commit", "rollback"]


def test_a_non_database_commit_failure_is_also_rolled_back() -> None:
    session, user = RecordingSession(ValueError("unexpected")), make_user()

    with pytest.raises(ValueError, match="unexpected"):
        call(session, user)

    assert session.calls == ["commit", "rollback"]


def test_a_wrong_version_commits_nothing() -> None:
    session, user = RecordingSession(), make_user()

    with pytest.raises(InvalidConsentVersionError):
        call(session, user, "1999-01-v0")

    assert session.calls == []
    assert user.consent_version is None and user.consent_accepted_at is None


def test_a_second_acceptance_commits_again_and_keeps_the_version() -> None:
    session, user = RecordingSession(), make_user()

    first = call(session, user).consent_accepted_at
    second = call(session, user).consent_accepted_at

    assert session.calls == ["commit", "commit"]
    assert user.consent_version == CURRENT and second >= first
