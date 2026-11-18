"""Settings introduced by the chat-rag-endpoint change (group 1, task 1.1).

Tests for: GOOGLE_API_KEY, LLM_BACKEND, CHAT_LLM_MODEL, CHAT_LLM_TIMEOUT_SECONDS,
CHAT_TOP_K, CHAT_RELEVANCE_THRESHOLD, CHAT_HISTORY_MESSAGES, CHAT_RATE_LIMIT.
"""

import pytest

from app.core.config import ConfigurationError, load_settings
from tests.constants import TEST_JWT_SECRET

DB_URL = "postgresql+psycopg://user:pw@localhost:5432/asistenteia"

CHAT_VARIABLES = (
    "GOOGLE_API_KEY",
    "LLM_BACKEND",
    "ALLOW_FAKE_LLM",
    "CHAT_LLM_MODEL",
    "CHAT_LLM_TIMEOUT_SECONDS",
    "CHAT_TOP_K",
    "CHAT_RELEVANCE_THRESHOLD",
    "CHAT_HISTORY_MESSAGES",
    "CHAT_RATE_LIMIT",
    "APP_ENV",
    "CORS_ORIGINS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CHAT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("APP_ENV", "test")


# --- defaults ---


def test_chat_defaults() -> None:
    settings = load_settings(env_file=None)

    assert settings.llm_backend == "fake"
    assert settings.chat_llm_model == "gemini-3.1-flash-lite"
    assert settings.chat_llm_timeout_seconds == 30
    assert settings.chat_top_k == 5
    assert settings.chat_relevance_threshold == pytest.approx(0.3)
    assert settings.chat_history_messages == 10
    assert settings.chat_rate_limit == "20/minute"


# --- GOOGLE_API_KEY ---


def test_google_api_key_is_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-key-1234567890")

    settings = load_settings(env_file=None)

    assert settings.google_api_key is not None
    assert settings.google_api_key.get_secret_value() == "AIza-test-key-1234567890"
    assert "AIza" not in repr(settings.google_api_key)


def test_google_api_key_is_required_when_llm_backend_is_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "GOOGLE_API_KEY" in str(exc.value)


def test_google_api_key_is_optional_when_llm_backend_is_fake() -> None:
    settings = load_settings(env_file=None)

    assert settings.google_api_key is None


# --- LLM_BACKEND fake gate (same pattern as EMBEDDER_BACKEND) ---


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_fake_llm_is_rejected_outside_the_test_environment(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")
    monkeypatch.setenv("LLM_BACKEND", "fake")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "LLM_BACKEND" in str(exc.value)


def test_fake_llm_is_accepted_in_the_test_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LLM_BACKEND", "fake")

    assert load_settings(env_file=None).llm_backend == "fake"


def test_fake_llm_needs_an_explicit_flag_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("ALLOW_FAKE_LLM", "true")

    assert load_settings(env_file=None).llm_backend == "fake"


def test_fake_llm_is_never_accepted_in_production_even_with_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example")
    monkeypatch.setenv("LLM_BACKEND", "fake")
    monkeypatch.setenv("ALLOW_FAKE_LLM", "true")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "LLM_BACKEND" in str(exc.value)


def test_allow_fake_llm_flag_alone_does_not_select_the_fake_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ALLOW_FAKE_LLM", "true")
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test-key-1234567890")

    assert load_settings(env_file=None).llm_backend == "gemini"


def test_invalid_llm_backend_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "openai")

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert "LLM_BACKEND" in str(exc.value)


# --- environment overrides ---


@pytest.mark.parametrize(
    ("variable", "value", "attribute", "expected"),
    [
        ("CHAT_LLM_MODEL", "gemini-2.0-flash", "chat_llm_model", "gemini-2.0-flash"),
        ("CHAT_LLM_TIMEOUT_SECONDS", "60", "chat_llm_timeout_seconds", 60),
        ("CHAT_TOP_K", "10", "chat_top_k", 10),
        ("CHAT_RELEVANCE_THRESHOLD", "0.5", "chat_relevance_threshold", 0.5),
        ("CHAT_HISTORY_MESSAGES", "20", "chat_history_messages", 20),
        ("CHAT_RATE_LIMIT", "30/minute", "chat_rate_limit", "30/minute"),
    ],
)
def test_chat_values_can_be_set_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
    attribute: str,
    expected: object,
) -> None:
    monkeypatch.setenv(variable, value)

    settings = load_settings(env_file=None)

    assert getattr(settings, attribute) == expected


# --- range validation ---


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("CHAT_LLM_TIMEOUT_SECONDS", "4"),
        ("CHAT_LLM_TIMEOUT_SECONDS", "121"),
        ("CHAT_LLM_TIMEOUT_SECONDS", "0"),
        ("CHAT_LLM_TIMEOUT_SECONDS", "abc"),
        ("CHAT_TOP_K", "0"),
        ("CHAT_TOP_K", "51"),
        ("CHAT_TOP_K", "-1"),
        ("CHAT_RELEVANCE_THRESHOLD", "-0.1"),
        ("CHAT_RELEVANCE_THRESHOLD", "1.1"),
        ("CHAT_RELEVANCE_THRESHOLD", "abc"),
        ("CHAT_HISTORY_MESSAGES", "-1"),
        ("CHAT_HISTORY_MESSAGES", "51"),
        ("CHAT_RATE_LIMIT", "often"),
        ("CHAT_RATE_LIMIT", "0/minute"),
    ],
)
def test_invalid_chat_values_are_rejected_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ConfigurationError) as exc:
        load_settings(env_file=None)

    assert variable in str(exc.value)


# --- boundary values ---


def test_chat_relevance_threshold_accepts_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_RELEVANCE_THRESHOLD", "0.0")
    assert load_settings(env_file=None).chat_relevance_threshold == pytest.approx(0.0)

    monkeypatch.setenv("CHAT_RELEVANCE_THRESHOLD", "1.0")
    assert load_settings(env_file=None).chat_relevance_threshold == pytest.approx(1.0)


def test_chat_history_messages_accepts_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_HISTORY_MESSAGES", "0")
    assert load_settings(env_file=None).chat_history_messages == 0


def test_chat_llm_timeout_accepts_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_LLM_TIMEOUT_SECONDS", "5")
    assert load_settings(env_file=None).chat_llm_timeout_seconds == 5

    monkeypatch.setenv("CHAT_LLM_TIMEOUT_SECONDS", "120")
    assert load_settings(env_file=None).chat_llm_timeout_seconds == 120
