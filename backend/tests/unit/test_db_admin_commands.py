"""Exit codes and safety switches of the db-* commands (review S-03, S-08, S-11).

The functions that talk to PostgreSQL are replaced by fakes: nothing connects.
"""

from typing import Any

import psycopg
import pytest

from app.cli import main
from app.core.config import RolesSettings
from app.db_admin import commands
from app.db_admin.bootstrap import BootstrapReport

PASSWORDS = {
    "db_migrator_password": "Mig-0123456789-abcdefgh",
    "db_app_password": "App-0123456789-abcdefgh",
    "db_worker_password": "Wrk-0123456789-abcdefgh",
    "db_cli_password": "Cli-0123456789-abcdefgh",
}


@pytest.fixture(autouse=True)
def fake_roles_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = RolesSettings(
        _env_file=None,
        admin_database_url="postgresql+psycopg://admin:Ad9-staple-horse-battery-x@db:5432/postgres",
        **PASSWORDS,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(commands, "load_roles_settings", lambda: settings)


def report(drift: tuple[str, ...]) -> BootstrapReport:
    return BootstrapReport(created=("r",), updated=(), closed_databases=3, ownership_drift=drift)


def test_bootstrap_succeeds_when_there_is_no_ownership_drift(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "bootstrap", lambda *a, **k: report(()))

    assert main(["db-bootstrap"]) == 0
    assert "no drift" in capsys.readouterr().out


def test_bootstrap_exits_non_zero_when_it_finds_ownership_drift(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "bootstrap", lambda *a, **k: report(("table users owned by x",)))

    assert main(["db-bootstrap"]) == 1
    assert "db-adopt" in capsys.readouterr().out  # the way out is named


def test_a_rollback_is_a_dry_run_without_apply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    called: list[str] = []
    monkeypatch.setattr(commands, "rollback_adoption", lambda *a, **k: called.append("x"))

    assert main(["db-adopt", "--rollback", "--remove-roles"]) == 0

    out = capsys.readouterr().out
    assert called == [] and "dry run" in out and "--apply" in out and "drop the four roles" in out


def test_a_rollback_runs_with_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class Done:
        def summary(self) -> list[str]:
            return ["done"]

    def fake(*args: Any, **kwargs: Any) -> Done:
        seen.update(kwargs)
        return Done()

    monkeypatch.setattr(commands, "rollback_adoption", fake)

    assert main(["db-adopt", "--rollback", "--remove-roles", "--apply"]) == 0
    assert seen["remove_roles"] is True


def test_remove_roles_without_rollback_is_an_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(commands, "adopt", lambda *a, **k: pytest.fail("must not run"))

    assert main(["db-adopt", "--remove-roles", "--apply"]) == 1
    assert "--rollback" in capsys.readouterr().err


def test_a_driver_error_is_reported_by_type_and_sqlstate_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise psycopg.errors.UndefinedTable('relation "users" does not exist; PASSWORD x')

    monkeypatch.setattr(commands, "bootstrap", boom)

    assert main(["db-bootstrap"]) == 1

    err = capsys.readouterr().err
    assert "UndefinedTable" in err and "42P01" in err
    assert "users" not in err and "PASSWORD" not in err
