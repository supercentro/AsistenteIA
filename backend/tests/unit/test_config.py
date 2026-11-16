import pytest

from app.core.config import ConfigurationError, load_settings
from tests.constants import TEST_JWT_SECRET

DB_URL = "postgresql+psycopg://user:pw@localhost:5432/asistenteia"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_ENV", "LOG_LEVEL", "DATABASE_URL", "CORS_ORIGINS", "TEST_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)


def test_load_settings_missing_database_url_names_the_variable() -> None:
    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "DATABASE_URL" in str(exc.value)


def test_load_settings_development_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)

    settings = load_settings(env_file=None)

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.cors_origins == ["http://localhost:5173"]


def test_load_settings_parses_comma_separated_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, https://b.example")

    settings = load_settings(env_file=None)

    assert settings.cors_origins == ["http://a.example", "https://b.example"]


@pytest.mark.parametrize("app_env", ["development", "test", "production"])
def test_load_settings_wildcard_origin_is_rejected_in_every_environment(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "CORS_ORIGINS" in str(exc.value)


def test_load_settings_production_requires_explicit_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "CORS_ORIGINS" in str(exc.value)


def test_load_settings_production_with_explicit_origins_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")

    assert load_settings(env_file=None).cors_origins == ["https://app.example"]


def test_load_settings_starts_without_test_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)

    load_settings(env_file=None)  # must not raise although TEST_DATABASE_URL is unset


def test_load_settings_ignores_invalid_test_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("TEST_DATABASE_URL", "not-a-url")

    load_settings(env_file=None)  # TEST_DATABASE_URL is never read or validated by the application


def test_the_uvicorn_entry_point_builds_the_application_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.main as main_module

    checked: list[object] = []
    # The entry point now asks the server for its identity (PG-01); no database exists here.
    monkeypatch.setattr(main_module, "assert_restricted_database_role", checked.append)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/factory_test")
    monkeypatch.setenv("JWT_SECRET", "t3sT-s3cr3t-only-for-automated-tests-9Zq")

    app = main_module.app_factory()

    assert app.title == "AsistenteIA API"
    assert len(checked) == 1
