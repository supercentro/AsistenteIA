"""The isolation guard must reject unsafe configurations before opening any connection."""

from collections.abc import Callable
from typing import Any, NoReturn

import psycopg
import pytest
import sqlalchemy

from app.core.db_safety import UnsafeTestDatabaseError
from tests import db_support
from tests.db_support import (
    MissingTestDatabaseError,
    drop_everything,
    guarded_engine,
    require_test_database_url,
)

APP_URL = "postgresql+psycopg://u:p@db:5432/asistenteia"


@pytest.fixture
def no_connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail loudly (and record) if anything tries to create an engine or open a connection."""
    attempts: list[str] = []

    def forbidden(name: str) -> Callable[..., NoReturn]:
        def _raise(*args: Any, **kwargs: Any) -> NoReturn:
            attempts.append(name)
            raise AssertionError(f"{name} called before the guard rejected the configuration")

        return _raise

    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden("create_engine"))
    monkeypatch.setattr(db_support, "create_engine", forbidden("db_support.create_engine"))
    monkeypatch.setattr(psycopg, "connect", forbidden("psycopg.connect"))
    monkeypatch.setattr(psycopg.Connection, "connect", forbidden("Connection.connect"))
    return attempts


UNSAFE_URLS = [
    pytest.param(APP_URL, id="same-database-as-application"),
    pytest.param("postgresql+psycopg://u:p@127.0.0.1:5442/asistenteia", id="no-test-suffix"),
    pytest.param("postgresql+psycopg://u:p@127.0.0.1:5442/asistenteia_test2", id="wrong-suffix"),
    pytest.param("postgresql+psycopg://u:p@127.0.0.1:5442/asistenteia_test_", id="trailing-char"),
    pytest.param("not-a-url", id="unparsable"),
]


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_require_test_database_url_rejects_unsafe_url_without_connecting(
    monkeypatch: pytest.MonkeyPatch, no_connections: list[str], url: str
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database_url()

    assert no_connections == []


def test_require_test_database_url_rejects_production_without_connecting(
    monkeypatch: pytest.MonkeyPatch, no_connections: list[str]
) -> None:
    monkeypatch.setenv(
        "TEST_DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:5442/asistenteia_test"
    )
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database_url()

    assert no_connections == []


def test_require_test_database_url_missing_variable_does_not_connect(
    monkeypatch: pytest.MonkeyPatch, no_connections: list[str]
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(MissingTestDatabaseError):
        require_test_database_url()

    assert no_connections == []


@pytest.mark.parametrize("url", [APP_URL, "postgresql+psycopg://u:p@127.0.0.1:5442/prod"])
def test_destructive_helpers_recheck_the_guard_before_connecting(
    monkeypatch: pytest.MonkeyPatch, no_connections: list[str], url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", APP_URL)

    with pytest.raises(UnsafeTestDatabaseError), guarded_engine(url):
        pass
    with pytest.raises(UnsafeTestDatabaseError):
        drop_everything(url)

    assert no_connections == []
