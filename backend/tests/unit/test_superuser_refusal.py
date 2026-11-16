"""The API and the worker refuse to start as a PostgreSQL superuser (finding PG-01, task 15.2).

The decision is the server's answer about the effective identity, not the user name in the URL.
Nothing connects here: the engine is a stand-in that returns what PostgreSQL would answer. The
real server behind real roles is exercised by `tests/integration/test_db_roles_startup.py`.
"""

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app import main as main_module
from app import worker as worker_module
from app.core.config import Settings, WorkerSettings
from app.core.database import SuperuserConnectionError, assert_restricted_database_role

URL = "postgresql+psycopg://asistente_app:never-printed-secret@db:5432/asistenteia"
JWT = "Zq8!vN3#rT6&wK1@mX9$pL4^bC7*dF2_hG5+yJ0"


class FakeEngine:
    """Answers the identity query like PostgreSQL would: (is_superuser setting, role flag)."""

    def __init__(self, row: tuple[bool, bool | None] | None, error: Exception | None = None):
        self.row, self.error = row, error
        self.statements: list[str] = []

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.error is not None:
            raise self.error
        engine = self

        class Connection:
            def execute(self, statement: Any) -> Any:
                engine.statements.append(str(statement))
                result = MagicMock()
                result.one.return_value = engine.row
                return result

        yield Connection()


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ((False, False), True),
        ((True, False), False),  # the setting says superuser
        ((False, True), False),  # the roles of the session say superuser
        ((True, True), False),
        ((False, None), False),  # the roles could not be read: not proved restricted
    ],
)
def test_the_decision_follows_what_the_server_reports(
    row: tuple[bool, bool | None], expected: bool
) -> None:
    engine = FakeEngine(row)

    if expected:
        assert_restricted_database_role(engine)  # type: ignore[arg-type]
    else:
        with pytest.raises(SuperuserConnectionError):
            assert_restricted_database_role(engine)  # type: ignore[arg-type]


def test_the_check_asks_the_server_and_never_reads_a_name() -> None:
    engine = FakeEngine((False, False))

    assert_restricted_database_role(engine)  # type: ignore[arg-type]

    sql = " ".join(engine.statements).lower()
    assert "is_superuser" in sql
    assert "rolsuper" in sql
    assert "current_user" in sql
    assert "session_user" in sql
    assert "pg_catalog.pg_roles" in sql  # qualified: nothing planted in public can answer


def test_an_unreachable_database_fails_closed_without_leaking_the_error() -> None:
    engine = FakeEngine(None, OperationalError("SELECT 1", {}, Exception(f"connect to {URL}")))

    with pytest.raises(SuperuserConnectionError) as refused:
        assert_restricted_database_role(engine)  # type: ignore[arg-type]

    assert "never-printed-secret" not in str(refused.value)
    assert "asistente_app" not in str(refused.value)
    assert "@db" not in str(refused.value)


def test_the_refusal_names_neither_a_password_nor_a_url() -> None:
    with pytest.raises(SuperuserConnectionError) as refused:
        assert_restricted_database_role(FakeEngine((True, True)))  # type: ignore[arg-type]

    assert "superuser" in str(refused.value).lower()
    assert "postgresql+psycopg" not in str(refused.value)
    assert "@" not in str(refused.value)


# --- the settings ---------------------------------------------------------------------------


def api_settings(**extra: object) -> Settings:
    return Settings(database_url=URL, jwt_secret=JWT, cors_origins=["http://x"], **extra)  # type: ignore[arg-type]


def worker_settings(**extra: object) -> WorkerSettings:
    return WorkerSettings(database_url=URL, **extra)  # type: ignore[arg-type]


@pytest.mark.parametrize("environment", ["development", "production"])
def test_the_exception_is_rejected_outside_the_test_environment(environment: str) -> None:
    with pytest.raises(ValidationError):
        api_settings(app_env=environment, allow_superuser_database_role=True)
    with pytest.raises(ValidationError):
        worker_settings(app_env=environment, allow_superuser_database_role=True)


def test_the_exception_is_accepted_only_with_the_test_environment() -> None:
    assert api_settings(app_env="test", allow_superuser_database_role=True)
    assert worker_settings(app_env="test", allow_superuser_database_role=True)


def test_the_exception_is_off_by_default() -> None:
    assert api_settings().allow_superuser_database_role is False
    assert worker_settings().allow_superuser_database_role is False


# --- the production entry points ------------------------------------------------------------


@pytest.fixture
def checks(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Replaces the check in both entry points with a recorder; returns the engines it saw."""
    seen: list[object] = []

    def record(engine: object) -> None:
        seen.append(engine)

    monkeypatch.setattr(main_module, "assert_restricted_database_role", record)
    monkeypatch.setattr(worker_module, "assert_restricted_database_role", record)
    return seen


def test_the_api_entry_point_checks_the_identity(
    monkeypatch: pytest.MonkeyPatch, checks: list[object]
) -> None:
    monkeypatch.setattr(main_module, "load_settings", lambda: api_settings())

    main_module.app_factory()

    assert len(checks) == 1


def test_the_api_entry_point_refuses_a_superuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "load_settings", lambda: api_settings())

    def refuse(engine: object) -> None:
        raise SuperuserConnectionError

    monkeypatch.setattr(main_module, "assert_restricted_database_role", refuse)

    with pytest.raises(SuperuserConnectionError):
        main_module.app_factory()


def test_the_api_entry_point_skips_the_check_only_with_the_test_exception(
    monkeypatch: pytest.MonkeyPatch, checks: list[object]
) -> None:
    monkeypatch.setattr(
        main_module,
        "load_settings",
        lambda: api_settings(app_env="test", allow_superuser_database_role=True),
    )

    main_module.app_factory()

    assert checks == []


def test_create_app_in_process_does_not_check(checks: list[object]) -> None:
    """Unit tests build the application in process; only the production entry point enforces."""
    main_module.create_app(api_settings())

    assert checks == []


class _Stop(threading.Event):
    pass


def _prepare_worker(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(worker_module, "build_embedder", lambda settings: object())
    monkeypatch.setattr(worker_module, "startup_check", lambda embedder: None)
    monkeypatch.setattr(worker_module, "create_db_engine", lambda *a, **k: MagicMock())
    monkeypatch.setattr(worker_module, "IngestionService", lambda *a, **k: object())
    monkeypatch.setattr(worker_module, "create_session_factory", lambda engine: object())

    class Loop:
        def __init__(self, *a: object, **k: object) -> None:
            calls.append("loop-built")

        def run(self) -> None:
            calls.append("loop-ran")

    monkeypatch.setattr(worker_module, "WorkerLoop", Loop)
    monkeypatch.setattr(worker_module, "Beacon", lambda *a, **k: MagicMock())
    return calls


def test_the_worker_refuses_a_superuser_before_it_serves(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, tmp_path: Any
) -> None:
    calls = _prepare_worker(monkeypatch)

    def refuse(engine: object) -> None:
        raise SuperuserConnectionError

    monkeypatch.setattr(worker_module, "assert_restricted_database_role", refuse)
    stop = threading.Event()
    stop.set()

    with caplog.at_level(logging.ERROR):
        code = worker_module.run_worker(
            worker_settings(),
            platform="linux",
            stop=stop,
            health_file=tmp_path / "health",
            enforce_database_identity=True,
        )

    assert code == worker_module.EXIT_REFUSED
    assert calls == []  # the loop was never built
    assert "superuser" in caplog.text.lower()
    assert "never-printed-secret" not in caplog.text


def test_the_worker_serves_when_the_role_is_restricted(
    monkeypatch: pytest.MonkeyPatch, checks: list[object], tmp_path: Any
) -> None:
    calls = _prepare_worker(monkeypatch)
    stop = threading.Event()
    stop.set()

    code = worker_module.run_worker(
        worker_settings(),
        platform="linux",
        stop=stop,
        health_file=tmp_path / "health",
        enforce_database_identity=True,
    )

    assert code == worker_module.EXIT_OK
    assert len(checks) == 1
    assert calls == ["loop-built", "loop-ran"]


def test_the_worker_skips_the_check_only_with_the_test_exception(
    monkeypatch: pytest.MonkeyPatch, checks: list[object], tmp_path: Any
) -> None:
    _prepare_worker(monkeypatch)
    stop = threading.Event()
    stop.set()

    worker_module.run_worker(
        worker_settings(app_env="test", allow_superuser_database_role=True),
        platform="linux",
        stop=stop,
        health_file=tmp_path / "health",
        enforce_database_identity=True,
    )

    assert checks == []


def test_the_worker_main_enforces_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    received: dict[str, object] = {}

    def fake_run(settings: object, **kwargs: object) -> int:
        received.update(kwargs)
        return 0

    monkeypatch.setattr(worker_module, "load_worker_settings", lambda: worker_settings())
    monkeypatch.setattr(worker_module, "run_worker", fake_run)

    assert worker_module.main() == 0
    assert received.get("enforce_database_identity") is True


def test_run_worker_in_process_does_not_enforce_by_default() -> None:
    import inspect

    default = inspect.signature(worker_module.run_worker).parameters["enforce_database_identity"]
    assert default.default is False


def test_the_worker_refuses_a_superuser_before_it_loads_the_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """A restart loop under a restart policy must not load the embedding model each time (R1)."""
    built: list[str] = []
    _prepare_worker(monkeypatch)
    monkeypatch.setattr(worker_module, "build_embedder", lambda settings: built.append("model"))

    def refuse(engine: object) -> None:
        raise SuperuserConnectionError

    monkeypatch.setattr(worker_module, "assert_restricted_database_role", refuse)
    stop = threading.Event()
    stop.set()

    code = worker_module.run_worker(
        worker_settings(),
        platform="linux",
        stop=stop,
        health_file=tmp_path / "health",
        enforce_database_identity=True,
    )

    assert code == worker_module.EXIT_REFUSED
    assert built == []
