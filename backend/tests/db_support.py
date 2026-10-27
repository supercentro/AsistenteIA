"""Helpers shared by integration tests. All destructive database helpers live under tests/."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.db_safety import assert_safe_test_database


class MissingTestDatabaseError(RuntimeError):
    """Raised when integration tests run without TEST_DATABASE_URL."""


def require_test_database_url() -> str:
    """Return TEST_DATABASE_URL after the isolation guard passed; never connects."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise MissingTestDatabaseError(
            "TEST_DATABASE_URL is required to run integration tests (see backend/.env.example)"
        )
    assert_safe_test_database(url, os.environ.get("DATABASE_URL"), os.environ.get("APP_ENV", ""))
    return url


@contextmanager
def guarded_engine(url: str) -> Iterator[Engine]:
    """Engine for a URL that already passed the guard (re-checked here before connecting)."""
    assert_safe_test_database(url, os.environ.get("DATABASE_URL"), os.environ.get("APP_ENV", ""))
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        yield engine
    finally:
        engine.dispose()


def drop_everything(url: str) -> None:
    """Destructive cleanup: drop the public schema contents and extensions of a test database."""
    with guarded_engine(url) as engine, engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("DROP EXTENSION IF EXISTS vector CASCADE"))
