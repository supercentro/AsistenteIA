"""Connection hardening and error hygiene of the administration commands (task 4.1, 4.6).

The driver is replaced by a fake, so nothing connects. These tests are what notices a removed
`search_path = pg_catalog` (the planting defence) or a leaked statement in an error message.
"""

from typing import Any

import psycopg
import pytest

from app.db_admin import connection
from app.db_admin.errors import DbAdminError
from app.db_admin.sql import Step

URL = "postgresql+psycopg://admin:S3cret-Password-123@db.internal:5432/postgres"


class FakeConnection:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.executed: list[str] = []

    def execute(self, query: str) -> None:
        if self.error is not None:
            raise self.error
        self.executed.append(query)


def capture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_connect(**kwargs: Any) -> str:
        seen.update(kwargs)
        return "connection"

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    return seen


def test_every_session_runs_with_the_catalog_search_path_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = capture(monkeypatch)

    connection.connect(URL)

    assert "-c search_path=pg_catalog" in seen["options"]
    assert "public" not in seen["options"]


def test_read_only_and_lock_timeout_are_session_options(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = capture(monkeypatch)

    connection.connect(URL, read_only=True, lock_timeout_ms=300)

    assert "-c default_transaction_read_only=on" in seen["options"]
    assert "-c lock_timeout=300" in seen["options"]
    plain = capture(monkeypatch)
    connection.connect(URL)
    assert "read_only" not in plain["options"] and "lock_timeout" not in plain["options"]


def test_only_the_tls_parameters_of_the_url_are_passed_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = capture(monkeypatch)

    connection.connect(URL + "?sslmode=verify-full&sslrootcert=/ca.pem&options=-c%20x&host=evil")

    assert seen["sslmode"] == "verify-full" and seen["sslrootcert"] == "/ca.pem"
    assert "host" in seen and seen["host"] == "db.internal"  # not replaced by the query
    assert "-c x" not in seen["options"]


def test_the_login_probe_keeps_the_tls_requirement_of_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db_admin.names import DEFAULT_NAMES, RolePasswords
    from app.db_admin.verify import _login_probe

    calls: list[dict[str, Any]] = []

    def refuse(**kwargs: Any) -> None:
        calls.append(kwargs)
        raise psycopg.OperationalError("no")

    monkeypatch.setattr(psycopg, "connect", refuse)
    passwords = RolePasswords(migrator="a" * 20, app="b" * 20, worker="c" * 20, cli="d" * 20)

    _login_probe(URL + "?sslmode=require", passwords, DEFAULT_NAMES)

    assert len(calls) == 4 and all(c["sslmode"] == "require" for c in calls)


def test_the_bootstrap_connection_silences_statement_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = capture(monkeypatch)

    connection.connect(URL, quiet_logs=True)

    for option in (
        "log_statement=none",
        "log_min_error_statement=panic",
        "log_min_duration_statement=-1",
    ):
        assert f"-c {option}" in seen["options"]
    quiet = capture(monkeypatch)
    connection.connect(URL)
    assert "log_statement" not in quiet["options"]


def test_the_password_travels_as_a_parameter_and_the_database_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = capture(monkeypatch)

    connection.connect(URL, database="other", autocommit=False)

    assert seen["password"] == "S3cret-Password-123"  # noqa: S105
    assert seen["dbname"] == "other" and seen["autocommit"] is False
    assert seen["connect_timeout"] <= 10 and seen["application_name"]
    assert "S3cret" not in seen["options"]


def test_a_failed_connection_names_the_server_and_the_sqlstate_but_no_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(**kwargs: Any) -> None:
        raise psycopg.OperationalError(f'FATAL: password "{kwargs["password"]}" rejected')

    monkeypatch.setattr(psycopg, "connect", refuse)

    with pytest.raises(DbAdminError) as caught:
        connection.connect(URL)

    message = str(caught.value)
    assert "db.internal:5432" in message and "admin" in message
    assert "S3cret" not in message and "rejected" not in message


def test_an_invalid_url_is_reported_without_echoing_it() -> None:
    with pytest.raises(DbAdminError) as caught:
        connection.connect("not a url S3cret-Password-123")

    assert "S3cret" not in str(caught.value)


def test_a_failing_step_names_the_step_and_the_sqlstate_not_the_statement() -> None:
    error = psycopg.errors.UndefinedObject(
        "role \"x\" does not exist: PASSWORD 'SCRAM-SHA-256$...'"
    )
    fake = FakeConnection(error)
    step = Step("alter role x", "ALTER ROLE \"x\" PASSWORD 'SCRAM-SHA-256$4096:aaa$bbb:ccc'", True)

    with pytest.raises(DbAdminError) as caught:
        connection.run_steps(fake, [step])  # type: ignore[arg-type]

    message = str(caught.value)
    assert "alter role x" in message and "42704" in message
    assert "SCRAM" not in message and "does not exist" not in message


def test_the_steps_run_in_order_and_are_counted() -> None:
    fake = FakeConnection()
    steps = [Step("a", "SELECT 1"), Step("b", "SELECT 2")]

    assert connection.run_steps(fake, steps) == 2  # type: ignore[arg-type]
    assert fake.executed == ["SELECT 1", "SELECT 2"]
