"""Settings of the migration service and of the role bootstrap (change `database-least-privilege`).

Task 3.1 and 3.2. Migrations and the bootstrap must not need the API secrets, must not fall back to
another database URL, and must never print a credential.
"""

import argparse
import io
from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr

from app.core.config import (
    ConfigurationError,
    MigrationSettings,
    RolesSettings,
    load_cli_settings,
    load_migration_settings,
    load_roles_settings,
    load_verify_settings,
)
from app.db_admin.commands import run_database_command
from tests.db_support import BACKEND_DIR

MIGRATOR_URL = (
    "postgresql+psycopg://asistente_migrator:Mg7-correct-horse-battery@db:5432/asistenteia"
)
ADMIN_URL = "postgresql+psycopg://asistente:Ad9-staple-horse-battery-x@db:5432/postgres"
PASSWORDS = {
    "DB_MIGRATOR_PASSWORD": "Mig-0123456789-abcdefgh",
    "DB_APP_PASSWORD": "App-0123456789-abcdefgh",
    "DB_WORKER_PASSWORD": "Wrk-0123456789-abcdefgh",
    "DB_CLI_PASSWORD": "Cli-0123456789-abcdefgh",
}
OTHER_VARIABLES = (
    "DATABASE_URL",
    "JWT_SECRET",
    "CORS_ORIGINS",
    "TEST_DATABASE_URL",
    "TEST_ADMIN_DATABASE_URL",
    "POSTGRES_PASSWORD",
    "MIGRATION_DATABASE_URL",
    "ADMIN_DATABASE_URL",
    *PASSWORDS,
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OTHER_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def set_roles(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {"ADMIN_DATABASE_URL": ADMIN_URL, **PASSWORDS, **overrides}
    for name, value in values.items():
        monkeypatch.setenv(name, value)


# --- MigrationSettings -------------------------------------------------------------------------


def test_migration_settings_need_only_the_migrator_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATOR_URL)

    settings = load_migration_settings(env_file=None)

    assert isinstance(settings, MigrationSettings)
    assert settings.migration_database_url.get_secret_value() == MIGRATOR_URL


def test_migration_settings_never_fall_back_to_the_application_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", MIGRATOR_URL
    )  # present, but not the variable of this service
    monkeypatch.setenv("POSTGRES_PASSWORD", "x" * 24)

    with pytest.raises(ConfigurationError, match="MIGRATION_DATABASE_URL"):
        load_migration_settings(env_file=None)


def test_migration_settings_ignore_every_other_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATOR_URL)
    monkeypatch.setenv("JWT_SECRET", "t3sT-s3cr3t-only-for-automated-tests-9Zq")
    monkeypatch.setenv("TEST_DATABASE_URL", "not-even-a-url")

    settings = load_migration_settings(env_file=None)

    assert set(MigrationSettings.model_fields) == {"migration_database_url"}
    assert "t3sT" not in repr(settings) and "not-even" not in repr(settings)


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-url",
        "mysql://u:Pw-long-enough-123@db/asistenteia",
        "postgresql+psycopg://asistente_migrator:Pw-long-enough-123@db:5432/",
        "postgresql+psycopg://:Pw-long-enough-123@db:5432/asistenteia",
        "postgresql+psycopg://asistente_migrator:CHANGE_ME@db:5432/asistenteia",
        "postgresql+psycopg://asistente_migrator@db:5432/asistenteia",
    ],
    ids=["unparsable", "wrong-driver", "no-database", "no-user", "placeholder", "no-password"],
)
def test_migration_settings_reject_a_bad_url_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", bad)

    with pytest.raises(ConfigurationError) as caught:
        load_migration_settings(env_file=None)

    message = str(caught.value)
    assert "MIGRATION_DATABASE_URL" in message
    assert "Pw-long-enough-123" not in message and bad not in message


def test_migration_settings_are_never_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATOR_URL)

    settings = load_migration_settings(env_file=None)

    assert "Mg7-correct" not in repr(settings) and "Mg7-correct" not in str(settings)
    assert isinstance(settings.migration_database_url, SecretStr)


def test_migration_settings_read_the_migrate_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.migrate"
    env_file.write_text(f"MIGRATION_DATABASE_URL={MIGRATOR_URL}\n", encoding="utf-8")

    settings = load_migration_settings(env_file=str(env_file))

    assert settings.migration_database_url.get_secret_value() == MIGRATOR_URL


# --- Alembic uses MigrationSettings ------------------------------------------------------------


def offline_upgrade() -> str:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.output_buffer = io.StringIO()
    command.upgrade(config, "head", sql=True)
    return config.output_buffer.getvalue()


def test_alembic_starts_with_only_the_migrator_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIGRATION_DATABASE_URL", MIGRATOR_URL)  # no JWT_SECRET, no CORS_ORIGINS

    script = offline_upgrade()

    assert "CREATE TABLE users" in script and "ingestion_jobs" in script


def test_alembic_refuses_to_use_the_application_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", MIGRATOR_URL)
    monkeypatch.setenv("JWT_SECRET", "t3sT-s3cr3t-only-for-automated-tests-9Zq")

    with pytest.raises(ConfigurationError) as caught:
        offline_upgrade()

    assert "MIGRATION_DATABASE_URL" in str(caught.value)
    assert "Mg7-correct" not in str(caught.value)


def test_alembic_env_no_longer_imports_the_api_settings() -> None:
    source = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")

    assert "load_settings" not in source
    assert "load_migration_settings" in source


# --- RolesSettings (bootstrap) -----------------------------------------------------------------


def test_roles_settings_hold_the_administrator_and_the_four_role_passwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_roles(monkeypatch)

    settings = load_roles_settings(env_file=None)

    assert isinstance(settings, RolesSettings)
    assert settings.admin_database_url.get_secret_value() == ADMIN_URL
    assert settings.db_cli_password.get_secret_value() == PASSWORDS["DB_CLI_PASSWORD"]
    assert "Mig-0123456789" not in repr(settings) and "Ad9-staple" not in repr(settings)


@pytest.mark.parametrize("missing", ["ADMIN_DATABASE_URL", *PASSWORDS])
def test_roles_settings_name_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    set_roles(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(ConfigurationError, match=missing):
        load_roles_settings(env_file=None)


@pytest.mark.parametrize(
    "weak",
    ["CHANGE_ME", "changeme-changeme-123", "short-pw-1", ""],
    ids=["placeholder", "placeholder-long", "too-short", "empty"],
)
def test_roles_settings_reject_weak_passwords_without_echoing_them(
    monkeypatch: pytest.MonkeyPatch, weak: str
) -> None:
    set_roles(monkeypatch, DB_APP_PASSWORD=weak)

    with pytest.raises(ConfigurationError) as caught:
        load_roles_settings(env_file=None)

    message = str(caught.value)
    assert "DB_APP_PASSWORD" in message
    assert (not weak) or weak not in message


def test_roles_settings_reject_two_roles_sharing_a_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_roles(monkeypatch, DB_WORKER_PASSWORD=PASSWORDS["DB_APP_PASSWORD"])

    with pytest.raises(ConfigurationError, match="distinct") as caught:
        load_roles_settings(env_file=None)

    assert PASSWORDS["DB_APP_PASSWORD"] not in str(caught.value)


def test_roles_settings_reject_a_bad_administrator_url_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_roles(
        monkeypatch, ADMIN_DATABASE_URL="postgresql+psycopg://asistente:CHANGE_ME@db/postgres"
    )

    with pytest.raises(ConfigurationError) as caught:
        load_roles_settings(env_file=None)

    assert "ADMIN_DATABASE_URL" in str(caught.value) and "asistente:" not in str(caught.value)


def test_roles_settings_do_not_need_the_api_or_migration_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_roles(monkeypatch)

    load_roles_settings(env_file=None)  # DATABASE_URL, JWT_SECRET and MIGRATION_DATABASE_URL unset


# --- Finding P2 of the Codex review of 6e85470 (task 19.3.4): malformed URLs ---
# SQLAlchemy raises ArgumentError for an unparsable URL, but a ValueError (for example an invalid
# port taken from the part of a password that follows an unescaped "@") for others. Both must be
# rejected with a message that names the variable and holds nothing from the value. Synthetic only.

FRAGMENT = "Zq9-frag-secret"
MALFORMED = {
    "unescaped-at-in-password": f"postgresql+psycopg://app_user:pre@part:{FRAGMENT}@db/app",
    "malformed-port": "postgresql+psycopg://app_user:Pw-long-enough-123@db:notaport/app",
}
UNPARSABLE = {"not-a-url": "this is not a url"}
LOADERS = {
    "migration": "MIGRATION_DATABASE_URL",
    "admin": "ADMIN_DATABASE_URL",
    "cli": "CLI_DATABASE_URL",
    "verify": "MIGRATION_DATABASE_URL",
}


def prepare_loader(monkeypatch: pytest.MonkeyPatch, loader: str, url: str) -> Callable[[], object]:
    for name in ("CLI_DATABASE_URL", "APP_ENV", "DB_CONNECT_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)  # nothing of the real environment may interfere
    if loader == "migration":
        monkeypatch.setenv("MIGRATION_DATABASE_URL", url)
        return lambda: load_migration_settings(env_file=None)
    if loader == "admin":
        set_roles(monkeypatch, ADMIN_DATABASE_URL=url)
        return lambda: load_roles_settings(env_file=None)
    if loader == "cli":
        monkeypatch.setenv("CLI_DATABASE_URL", url)
        return lambda: load_cli_settings(env_file=None)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", url)
    for name, value in PASSWORDS.items():
        monkeypatch.setenv(name, value)
    return lambda: load_verify_settings(env_files=None)


def assert_value_free(message: str, variable: str, url: str) -> None:
    assert variable in message, message
    for forbidden in (
        url,
        FRAGMENT,
        "Pw-long-enough-123",
        "notaport",
        "invalid literal",
        "int()",
        "app_user",
    ):
        assert forbidden not in message, "the message holds part of the value or an internal text"


@pytest.mark.parametrize("loader", list(LOADERS))
@pytest.mark.parametrize("case", list(MALFORMED))
def test_a_malformed_database_url_is_rejected_without_leaking_any_part_of_it(
    monkeypatch: pytest.MonkeyPatch, loader: str, case: str
) -> None:
    load = prepare_loader(monkeypatch, loader, MALFORMED[case])

    with pytest.raises(ConfigurationError) as caught:
        load()

    assert_value_free(str(caught.value), LOADERS[loader], MALFORMED[case])
    assert caught.value.__cause__ is None and caught.value.__suppress_context__ is True


@pytest.mark.parametrize("loader", list(LOADERS))
def test_an_unparsable_database_url_keeps_its_safe_rejection(
    monkeypatch: pytest.MonkeyPatch, loader: str
) -> None:
    load = prepare_loader(monkeypatch, loader, UNPARSABLE["not-a-url"])

    with pytest.raises(ConfigurationError) as caught:
        load()

    assert_value_free(str(caught.value), LOADERS[loader], UNPARSABLE["not-a-url"])
    assert caught.value.__cause__ is None and caught.value.__suppress_context__ is True


@pytest.mark.parametrize("case", list(MALFORMED))
@pytest.mark.parametrize(
    ("command", "loader"),
    [("db-migrate", "migration"), ("db-bootstrap", "admin"), ("db-verify", "verify")],
)
def test_the_database_commands_print_nothing_from_a_malformed_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, command: str, loader: str, case: str
) -> None:
    monkeypatch.chdir(tmp_path)  # no environment file is read from the project
    prepare_loader(monkeypatch, loader, MALFORMED[case])
    printed: list[str] = []
    errors: list[str] = []
    args = argparse.Namespace(command=command, database="postgres", downgrade=None)

    code = run_database_command(args, printed.append, errors.append)

    assert code == 1 and printed == []
    assert_value_free("\n".join(errors), LOADERS[loader], MALFORMED[case])
