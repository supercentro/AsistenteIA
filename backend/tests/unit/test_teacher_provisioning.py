"""Teacher provisioning is separated from public registration (`database-least-privilege`).

Unit level: the registration path does not name the role, the model carries the server default, and
the administrative command reads its own settings (no JWT secret, no API database URL).
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

import app.cli as cli_module
from app.core.config import ConfigurationError, load_cli_settings
from app.core.security import PasswordService
from app.models.user import User, UserRole
from app.services.auth_service import AuthService

CLI_URL = "postgresql+psycopg://asistente_cli:Cli-0123456789-abcdef@db:5432/asistenteia"


def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CLI_DATABASE_URL", "DATABASE_URL", "JWT_SECRET", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)


class RecordingUsers:
    def __init__(self) -> None:
        self.named_the_role: list[bool] = []

    def add(self, user: User) -> User:
        self.named_the_role.append("role" in sa.inspect(user).dict)
        user.role = UserRole.STUDENT  # what the server default returns after the INSERT
        return user


def test_the_model_declares_the_student_default_on_the_server() -> None:
    default = User.__table__.c.role.server_default

    assert default is not None
    assert str(default.arg) == "'student'"


def test_registration_builds_a_user_without_naming_the_role() -> None:
    users = RecordingUsers()
    service = AuthService(users, PasswordService(time_cost=1, memory_cost=8, parallelism=1), None)  # type: ignore[arg-type]

    service.register_student("Ana", "ana@example.com", "a-very-long-password")

    assert users.named_the_role == [False]  # not set, so the INSERT leaves the column out


def test_the_insert_of_a_registered_user_omits_role_and_a_teacher_insert_names_it() -> None:
    student = sa.insert(User).values(name="A", email="a@example.com", password_hash="h")
    teacher = sa.insert(User).values(
        name="A", email="a@example.com", password_hash="h", role=UserRole.TEACHER
    )

    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    assert "role" not in student.compile(dialect=dialect).params
    assert "role" in teacher.compile(dialect=dialect).params


def test_cli_settings_need_only_the_cli_url(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_environment(monkeypatch)
    monkeypatch.setenv("CLI_DATABASE_URL", CLI_URL)
    settings = load_cli_settings(None)

    assert settings.cli_database_url.get_secret_value() == CLI_URL
    assert "Cli-0123456789" not in repr(settings)


def test_the_seed_gate_fails_closed_when_app_env_is_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_environment(monkeypatch)
    monkeypatch.setenv("CLI_DATABASE_URL", CLI_URL)

    assert load_cli_settings(None).app_env == "production"


def test_cli_settings_do_not_fall_back_to_the_api_url_and_do_not_leak_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean_environment(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://asistente_app:App-0123456789-abcdef@db:5432/x"
    )
    monkeypatch.setenv("JWT_SECRET", "j" * 40)
    try:
        load_cli_settings(None)
    except ConfigurationError as exc:
        assert "CLI_DATABASE_URL" in str(exc)
        assert "App-0123456789" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("the CLI must not use the API credential")


def test_cli_settings_reject_a_placeholder_password(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_environment(monkeypatch)
    monkeypatch.setenv(
        "CLI_DATABASE_URL", "postgresql+psycopg://asistente_cli:CHANGE_ME@db:5432/asistenteia"
    )
    try:
        load_cli_settings(None)
    except ConfigurationError as exc:
        assert "CHANGE_ME" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("placeholder accepted")


def test_the_cli_module_does_not_import_the_api_settings() -> None:
    assert not hasattr(cli_module, "load_settings")
    assert not hasattr(cli_module, "Settings")
