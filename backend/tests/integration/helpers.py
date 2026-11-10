"""Shared helpers for HTTP-level integration tests."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import create_db_engine, create_session_factory
from app.core.security import PasswordService
from app.main import create_app
from app.models.subject import Subject
from app.models.user import User, UserRole
from app.repositories.enrollment_repository import EnrollmentRepository
from app.repositories.subject_repository import SubjectRepository
from app.repositories.user_repository import UserRepository
from tests.constants import TEST_JWT_SECRET

# Low Argon2 cost keeps the suite fast; production uses the library defaults.
FAST_PASSWORDS = PasswordService(time_cost=1, memory_cost=8, parallelism=1)

DEFAULT_PASSWORD = "a-very-long-password"


@dataclass
class TestUser:
    __test__ = False  # not a pytest test class

    id: str
    email: str
    password: str
    role: UserRole


def build_settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": database_url,
        "jwt_secret": TEST_JWT_SECRET,
        "cors_origins": ["http://localhost:5173"],
        # High by default so ordinary tests never hit the limiter; rate-limit tests lower it.
        "login_rate_limit": "1000/minute",
        "register_rate_limit": "1000/minute",
        "upload_rate_limit": "1000/minute",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def build_app(database_url: str, **overrides: object) -> FastAPI:
    return create_app(build_settings(database_url, **overrides), password_service=FAST_PASSWORDS)


MakeUser = Callable[..., TestUser]


def insert_user(
    database_url: str,
    email: str,
    role: UserRole = UserRole.STUDENT,
    password: str = DEFAULT_PASSWORD,
    name: str = "Test User",
) -> TestUser:
    """Insert an account directly in the database (bypasses the API), committed."""
    engine = create_db_engine(database_url)
    session: Session = create_session_factory(engine)()
    try:
        user = UserRepository(session).add(
            User(
                name=name,
                email=email,
                password_hash=FAST_PASSWORDS.hash(password),
                role=role,
            )
        )
        session.commit()
        return TestUser(id=str(user.id), email=email, password=password, role=role)
    finally:
        session.close()
        engine.dispose()


def login_token(client: TestClient, email: str, password: str = DEFAULT_PASSWORD) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def insert_subject(
    database_url: str, teacher_id: str, name: str = "Algebra", description: str | None = None
) -> str:
    """Insert a subject directly in the database (bypasses the API); returns its id."""
    engine = create_db_engine(database_url)
    session: Session = create_session_factory(engine)()
    try:
        subject = SubjectRepository(session).add(
            Subject(name=name, description=description, teacher_id=uuid.UUID(teacher_id))
        )
        session.commit()
        return str(subject.id)
    finally:
        session.close()
        engine.dispose()


def insert_enrollment(database_url: str, subject_id: str, student_id: str) -> None:
    """Enrol a student directly in the database (bypasses the API)."""
    engine = create_db_engine(database_url)
    session: Session = create_session_factory(engine)()
    try:
        teacher_id = session.execute(
            select(Subject.teacher_id).where(Subject.id == uuid.UUID(subject_id))
        ).scalar_one()
        EnrollmentRepository(session).add(uuid.UUID(subject_id), teacher_id, uuid.UUID(student_id))
        session.commit()
    finally:
        session.close()
        engine.dispose()
