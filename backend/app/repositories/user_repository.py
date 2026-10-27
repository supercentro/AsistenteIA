import uuid

from psycopg import errors as pg_errors
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.user import User


class UserRepository:
    """All data access for users. Emails are expected in lowercase."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, user: User) -> User:
        """Insert a user; a duplicate email raises `ConflictError` and keeps the session usable."""
        try:
            with self._session.begin_nested():
                self._session.add(user)
                self._session.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, pg_errors.UniqueViolation):
                raise ConflictError("Email already registered") from None
            raise
        return user

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._session.execute(select(User).where(User.email == email)).scalar_one_or_none()
