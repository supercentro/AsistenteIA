"""Skeletons of the database administration commands (change `database-least-privilege`, 3.2).

The commands exist in the parser so that their names and options are fixed, but they do nothing yet
(group 4 implements them). They must fail clearly, must not need the API settings and must never
touch a database.
"""

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


@pytest.mark.parametrize("command", DATABASE_COMMANDS)
def test_each_command_fails_clearly_without_needing_the_api_settings(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([command])

    captured = capsys.readouterr()
    assert code == 1
    assert command in captured.err and "not implemented" in captured.err
    assert captured.out == ""
    assert "JWT_SECRET" not in captured.err and "DATABASE_URL" not in captured.err


def test_the_existing_commands_are_unchanged() -> None:
    parser = build_parser()

    assert parser.parse_args(["create-teacher", "--email", "a@b.co"]).command == "create-teacher"
    assert parser.parse_args(["seed"]).command == "seed"
