"""Host-only test environment, application-URL reference of the guard, and the test-role prefix.

Change `database-least-privilege`, tasks 3.1 and 3.4. No test here opens a connection: the sweep
runs against a fake connection that records the statements.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.core.db_safety import UnsafeTestDatabaseError
from tests.db_support import (
    MissingTestDatabaseError,
    load_test_environment,
    require_test_admin_database_url,
    require_test_database_url,
)
from tests.role_support import (
    REAL_ROLE_NAMES,
    TEST_ROLE_PREFIX,
    assert_test_role_name,
    make_test_role_name,
    sweep_test_roles,
)

APP_URL = "postgresql+psycopg://asistente_app:Pw1-long-enough-aaaa@127.0.0.1:5442/asistenteia"
TEST_URL = "postgresql+psycopg://asistente:Pw2-long-enough-bbbb@127.0.0.1:5442/asistenteia_test"
ADMIN_URL = "postgresql+psycopg://asistente:Pw2-long-enough-bbbb@127.0.0.1:5442/postgres"

VARIABLES = ("DATABASE_URL", "TEST_DATABASE_URL", "TEST_ADMIN_DATABASE_URL", "APP_ENV")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)


# --- host-only environment files -------------------------------------------------------------


def test_the_test_file_supplies_the_test_variables_and_the_api_file_the_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env.test").write_text(
        f"TEST_DATABASE_URL={TEST_URL}\nTEST_ADMIN_DATABASE_URL={ADMIN_URL}\n", encoding="utf-8"
    )
    (tmp_path / ".env").write_text(f"DATABASE_URL={APP_URL}\n", encoding="utf-8")

    load_test_environment(tmp_path)

    assert require_test_database_url() == TEST_URL
    assert require_test_admin_database_url() == ADMIN_URL
    monkeypatch.delenv("TEST_ADMIN_DATABASE_URL")
    monkeypatch.delenv("TEST_DATABASE_URL")


def test_the_real_environment_wins_over_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env.test").write_text(f"TEST_DATABASE_URL={TEST_URL}\n", encoding="utf-8")
    other = TEST_URL.replace("asistenteia_test", "other_test")
    monkeypatch.setenv("TEST_DATABASE_URL", other)
    monkeypatch.setenv("DATABASE_URL", APP_URL)

    load_test_environment(tmp_path)

    assert require_test_database_url() == other


def test_a_legacy_test_variable_in_the_api_file_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Existing checkouts keep TEST_DATABASE_URL in backend/.env until they migrate (compatible).
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={APP_URL}\nTEST_DATABASE_URL={TEST_URL}\n", encoding="utf-8"
    )

    load_test_environment(tmp_path)

    assert require_test_database_url() == TEST_URL
    monkeypatch.delenv("TEST_DATABASE_URL")


def test_missing_files_are_not_an_error(tmp_path: Path) -> None:
    load_test_environment(tmp_path)  # nothing to read; the requirement functions then fail

    with pytest.raises(MissingTestDatabaseError, match="TEST_DATABASE_URL"):
        require_test_database_url()


# --- the guard keeps its reference -------------------------------------------------------------


def test_the_guard_does_not_silently_skip_the_comparison_without_the_application_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)

    with pytest.raises(MissingTestDatabaseError) as caught:
        require_test_database_url()

    message = str(caught.value)
    assert "DATABASE_URL" in message and "Pw2-long" not in message


def test_the_guard_still_rejects_the_same_database_name_on_another_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/asistenteia_test")
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)

    with pytest.raises(UnsafeTestDatabaseError):
        require_test_database_url()


def test_the_administrator_url_fails_when_missing_and_names_the_variable() -> None:
    with pytest.raises(MissingTestDatabaseError, match="TEST_ADMIN_DATABASE_URL"):
        require_test_admin_database_url()


def test_the_administrator_url_must_be_on_the_same_server_as_the_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("TEST_ADMIN_DATABASE_URL", ADMIN_URL.replace("5442", "5999"))

    with pytest.raises(UnsafeTestDatabaseError) as caught:
        require_test_admin_database_url()

    assert "Pw2-long" not in str(caught.value)


def test_the_administrator_url_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", APP_URL)
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("TEST_ADMIN_DATABASE_URL", ADMIN_URL)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(UnsafeTestDatabaseError):
        require_test_admin_database_url()


# --- reserved role prefix and sweep ------------------------------------------------------------


def test_the_prefix_cannot_match_any_real_role() -> None:
    assert TEST_ROLE_PREFIX.endswith("_")
    for real in REAL_ROLE_NAMES:
        assert not real.startswith(TEST_ROLE_PREFIX), real
        assert not TEST_ROLE_PREFIX.startswith(real), real


def test_test_role_names_carry_the_prefix_and_are_valid_identifiers() -> None:
    name = make_test_role_name("app")

    assert name.startswith(TEST_ROLE_PREFIX)
    assert_test_role_name(name)


@pytest.mark.parametrize(
    "name",
    [*REAL_ROLE_NAMES, "postgres", "tstrole", "TSTROLE_x", f"{TEST_ROLE_PREFIX}", "x" * 80, ""],
)
def test_names_without_the_prefix_are_refused(name: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_test_role_name(name)


@pytest.mark.parametrize(
    "suffix", ['a"; DROP ROLE asistente; --', "a b", "a-b", "A", "ñ", "a;b", "a\nb", "a'b"]
)
def test_names_with_unsafe_characters_are_refused(suffix: str) -> None:
    with pytest.raises(UnsafeTestDatabaseError):
        assert_test_role_name(TEST_ROLE_PREFIX + suffix)


class FakeResult:
    def __init__(self, rows: Sequence[str]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[str]]:
        return [(row,) for row in self._rows]


class FakeConnection:
    def __init__(self, existing: Sequence[str]) -> None:
        self.existing = existing
        self.statements: list[str] = []

    def execute(self, statement: Any, parameters: Any = None) -> FakeResult:
        assert isinstance(statement, str)  # the real connection is psycopg: plain SQL text only
        self.statements.append(statement)
        if "pg_roles" in statement:
            assert parameters is not None
            assert parameters[0].replace("\\", "").startswith(TEST_ROLE_PREFIX)
            return FakeResult(self.existing)
        return FakeResult([])


def test_the_sweep_drops_only_prefixed_roles_and_what_they_own() -> None:
    names = [make_test_role_name("old_app"), make_test_role_name("old_worker")]
    connection = FakeConnection(names)

    swept = sweep_test_roles(connection)

    assert swept == names
    drops = [s for s in connection.statements if s.startswith(("DROP OWNED", "DROP ROLE"))]
    assert drops == [
        f'DROP OWNED BY "{names[0]}"',
        f'DROP ROLE "{names[0]}"',
        f'DROP OWNED BY "{names[1]}"',
        f'DROP ROLE "{names[1]}"',
    ]


def test_the_sweep_refuses_a_name_that_slipped_through_the_pattern() -> None:
    connection = FakeConnection([make_test_role_name("ok"), "asistente_app"])

    with pytest.raises(UnsafeTestDatabaseError):
        sweep_test_roles(connection)

    assert not [s for s in connection.statements if "asistente_app" in s]


def test_the_sweep_with_nothing_left_changes_nothing() -> None:
    connection = FakeConnection([])

    assert sweep_test_roles(connection) == []
    assert len(connection.statements) == 1  # only the lookup
