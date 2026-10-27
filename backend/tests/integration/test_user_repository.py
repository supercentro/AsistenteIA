import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


def make_user(email: str = "ana@example.com", role: UserRole = UserRole.STUDENT) -> User:
    return User(name="Ana", email=email, password_hash="$argon2id$fake", role=role)


def test_add_assigns_id_and_created_at(db_session: Session) -> None:
    user = UserRepository(db_session).add(make_user())

    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
    assert user.consent_version is None
    assert user.consent_accepted_at is None


def test_get_by_id_returns_the_user_or_none(db_session: Session) -> None:
    repo = UserRepository(db_session)
    user = repo.add(make_user())

    assert repo.get_by_id(user.id) is user
    assert repo.get_by_id(uuid.uuid4()) is None


def test_get_by_email_matches_lowercase_email(db_session: Session) -> None:
    repo = UserRepository(db_session)
    user = repo.add(make_user("ana@example.com"))

    assert repo.get_by_email("ana@example.com") is user
    assert repo.get_by_email("other@example.com") is None


def test_role_round_trips_as_enum_values(db_session: Session) -> None:
    repo = UserRepository(db_session)
    teacher = repo.add(make_user("t@example.com", UserRole.TEACHER))
    db_session.expire_all()

    assert repo.get_by_id(teacher.id) is not None
    assert teacher.role is UserRole.TEACHER
    stored = db_session.execute(
        text("SELECT role::text FROM users WHERE id = :id"), {"id": teacher.id}
    ).scalar_one()
    assert stored == "teacher"


def test_duplicate_email_raises_conflict_and_session_stays_usable(db_session: Session) -> None:
    repo = UserRepository(db_session)
    repo.add(make_user("dup@example.com"))

    with pytest.raises(ConflictError):
        repo.add(make_user("dup@example.com"))

    assert repo.add(make_user("fresh@example.com")).id is not None
    count = db_session.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert count == 2


def test_database_rejects_uppercase_email(db_session: Session) -> None:
    repo = UserRepository(db_session)

    with pytest.raises(IntegrityError):
        repo.add(make_user("Upper@Example.com"))


def test_database_rejects_invalid_role_value(db_session: Session) -> None:
    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                "INSERT INTO users (name, email, password_hash, role) "
                "VALUES ('x', 'x@example.com', 'h', 'admin')"
            )
        )
