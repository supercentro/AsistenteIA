"""Helpers shared by integration tests. All destructive database helpers live under tests/."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError

from app.core.db_safety import UnsafeTestDatabaseError, assert_safe_test_database


class MissingTestDatabaseError(RuntimeError):
    """Raised when integration tests run without TEST_DATABASE_URL."""


def load_test_environment(directory: Path | None = None) -> None:
    """Read the host-only `.env.test`, then `.env`, without overriding the real environment.

    `.env` still supplies the application `DATABASE_URL` (the guard compares with it) and, for
    checkouts that have not moved yet, a legacy `TEST_DATABASE_URL`. Order of precedence: the real
    environment, `.env.test`, `.env`.
    """
    base = directory or Path(__file__).resolve().parents[1]
    load_dotenv(base / ".env.test", override=False)
    load_dotenv(base / ".env", override=False)


def _application_url() -> str:
    """The URL the guard compares with; a missing one never silently disables the comparison."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise MissingTestDatabaseError(
            "DATABASE_URL (the application database the guard compares with) is required to "
            "run integration tests"
        )
    return url


def require_test_database_url() -> str:
    """Return TEST_DATABASE_URL after the isolation guard passed; never connects."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise MissingTestDatabaseError(
            "TEST_DATABASE_URL is required to run integration tests (see backend/.env.test.example)"
        )
    assert_safe_test_database(url, _application_url(), os.environ.get("APP_ENV", ""))
    return url


def require_test_admin_database_url() -> str:
    """Return TEST_ADMIN_DATABASE_URL for the role-bound tests; never connects.

    It must name the same server as the guarded test database (roles are cluster objects, so the
    database name is not `_test`) and is refused in production.
    """
    url = os.environ.get("TEST_ADMIN_DATABASE_URL")
    if not url:
        raise MissingTestDatabaseError(
            "TEST_ADMIN_DATABASE_URL is required to run the role-bound tests "
            "(see backend/.env.test.example)"
        )
    test_url = require_test_database_url()
    try:
        admin, test = make_url(url), make_url(test_url)
    except ArgumentError:
        raise UnsafeTestDatabaseError(
            "TEST_ADMIN_DATABASE_URL is not a valid database URL"
        ) from None
    if (admin.host, admin.port) != (test.host, test.port):
        raise UnsafeTestDatabaseError(
            "TEST_ADMIN_DATABASE_URL must name the same server as TEST_DATABASE_URL"
        )
    return url


@contextmanager
def guarded_engine(url: str) -> Iterator[Engine]:
    """Engine for a URL that already passed the guard (re-checked here before connecting)."""
    assert_safe_test_database(url, _application_url(), os.environ.get("APP_ENV", ""))
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


BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    """Alembic config bound to a URL that already passed the isolation guard."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def truncate_all(url: str) -> None:
    """Destructive cleanup between tests: empty every table except alembic_version."""
    with guarded_engine(url) as engine, engine.connect() as conn:
        names = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
        ]
        if names:
            quoted = ", ".join(f'"{name}"' for name in names)
            conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
