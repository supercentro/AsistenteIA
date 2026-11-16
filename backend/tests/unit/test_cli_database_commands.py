"""Wiring of the database administration commands (change `database-least-privilege`, 3.2 and 4).

The commands read only their own settings: no JWT secret, no API `DATABASE_URL`. Their behaviour
against PostgreSQL is tested in `tests/integration/test_db_admin_*.py`.
"""

from pathlib import Path

import pytest

from app.cli import DATABASE_COMMANDS, build_parser, main

API_VARIABLES = ("DATABASE_URL", "JWT_SECRET", "CORS_ORIGINS")


@pytest.fixture(autouse=True)
def no_api_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in API_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_the_database_commands_are_declared() -> None:
    assert DATABASE_COMMANDS == ("db-bootstrap", "db-adopt", "db-migrate", "db-grants", "db-verify")


@pytest.mark.parametrize("command", DATABASE_COMMANDS)
def test_each_command_parses(command: str) -> None:
    assert build_parser().parse_args([command]).command == command


NEEDS = {
    "db-bootstrap": "ADMIN_DATABASE_URL",
    "db-adopt": "ADMIN_DATABASE_URL",
    "db-migrate": "MIGRATION_DATABASE_URL",
    "db-grants": "MIGRATION_DATABASE_URL",
    "db-verify": "MIGRATION_DATABASE_URL",
}


@pytest.mark.parametrize("command", DATABASE_COMMANDS)
def test_each_command_names_its_own_missing_variable_and_never_the_api_ones(
    command: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name in set(NEEDS.values()):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env.* files here

    code = main([command])

    captured = capsys.readouterr()
    assert code == 1
    assert NEEDS[command] in captured.err
    assert captured.out == ""
    assert "JWT_SECRET" not in captured.err and "DATABASE_URL:" not in captured.err.replace(
        "MIGRATION_DATABASE_URL", ""
    ).replace("ADMIN_DATABASE_URL", "")


def test_adopt_is_a_dry_run_unless_told_otherwise() -> None:
    parser = build_parser()

    assert parser.parse_args(["db-adopt"]).apply is False
    assert parser.parse_args(["db-adopt", "--apply"]).apply is True
    assert parser.parse_args(["db-adopt", "--rollback"]).rollback is True
    assert parser.parse_args(["db-adopt", "--rollback", "--remove-roles"]).remove_roles is True


def test_the_existing_commands_are_unchanged() -> None:
    parser = build_parser()

    assert parser.parse_args(["create-teacher", "--email", "a@b.co"]).command == "create-teacher"
    assert parser.parse_args(["seed"]).command == "seed"
