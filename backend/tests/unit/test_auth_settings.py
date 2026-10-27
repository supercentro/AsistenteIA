import pytest

from app.core.config import ConfigurationError, load_settings
from tests.constants import TEST_JWT_SECRET

DB_URL = "postgresql+psycopg://user:pw@localhost:5432/asistenteia"


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "APP_ENV",
        "JWT_SECRET",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "JWT_EXPIRE_MINUTES",
        "PRIVACY_POLICY_VERSION",
        "LOGIN_RATE_LIMIT",
        "REGISTER_RATE_LIMIT",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)


def test_defaults_are_applied() -> None:
    settings = load_settings(env_file=None)

    assert settings.jwt_issuer == "asistenteia"
    assert settings.jwt_audience == "asistenteia-api"
    assert settings.jwt_expire_minutes == 60
    assert settings.privacy_policy_version == "2026-10-v1"
    assert settings.login_rate_limit == "10/minute"
    assert settings.register_rate_limit == "5/minute"
    assert settings.jwt_secret.get_secret_value() == TEST_JWT_SECRET


def test_missing_secret_fails_naming_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "JWT_SECRET" in str(exc.value)


@pytest.mark.parametrize("app_env", ["development", "test", "production"])
@pytest.mark.parametrize(
    "secret",
    [
        "short-secret",
        "x" * 31,
        "CHANGE_ME" + "a1b2c3d4" * 4,
        "changeme-" + "zq9x" * 10,
        "a" * 40,
        "ab" * 20,
    ],
)
def test_weak_secret_is_rejected_in_every_environment_without_printing_it(
    monkeypatch: pytest.MonkeyPatch, secret: str, app_env: str
) -> None:
    monkeypatch.setenv("JWT_SECRET", secret)
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "JWT_SECRET" in str(exc.value)
    assert secret not in str(exc.value)


def test_secret_of_exactly_32_bytes_with_variety_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", "k3Jx9Qm2Lp7Rv5Tn8Wz1Yb4Hd6Gs0FcA")  # 33 chars

    load_settings(env_file=None)


def test_secret_length_is_measured_in_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "é" * 16)  # 16 chars, 32 bytes, only one distinct char

    with pytest.raises(ConfigurationError):
        load_settings(env_file=None)


def test_secret_is_not_exposed_in_settings_repr() -> None:
    settings = load_settings(env_file=None)

    assert TEST_JWT_SECRET not in repr(settings)
    assert TEST_JWT_SECRET not in str(settings)


@pytest.mark.parametrize("value", ["0", "-5", "1441", "abc"])
def test_invalid_expiry_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "JWT_EXPIRE_MINUTES" in str(exc.value)


@pytest.mark.parametrize("value", ["", "x" * 21])
def test_invalid_policy_version_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("PRIVACY_POLICY_VERSION", value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "PRIVACY_POLICY_VERSION" in str(exc.value)


def test_policy_version_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIVACY_POLICY_VERSION", "2027-01-v2")

    assert load_settings(env_file=None).privacy_policy_version == "2027-01-v2"


@pytest.mark.parametrize("value", ["lots", "10/fortnight", "0/minute", ""])
def test_unparsable_rate_limit_is_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("LOGIN_RATE_LIMIT", value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "LOGIN_RATE_LIMIT" in str(exc.value)


def test_rate_limit_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "2/minute")

    assert load_settings(env_file=None).login_rate_limit == "2/minute"


@pytest.mark.parametrize("value", ["lots", "10/fortnight", "0/minute", ""])
def test_unparsable_register_rate_limit_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("REGISTER_RATE_LIMIT", value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "REGISTER_RATE_LIMIT" in str(exc.value)


def test_register_rate_limit_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "2/minute")

    assert load_settings(env_file=None).register_rate_limit == "2/minute"
