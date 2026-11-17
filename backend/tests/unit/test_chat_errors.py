"""Unit tests for domain errors introduced by chat-rag-endpoint (task 2.3)."""

from app.core.errors import (
    ConsentRequiredError,
    ForbiddenError,
    LLMBlockedError,
    LLMUnavailableError,
    SearchUnavailableError,
)


def test_consent_required_error() -> None:
    err = ConsentRequiredError()
    assert err.status_code == 403
    assert err.code == "CONSENT_REQUIRED"
    assert isinstance(err, ForbiddenError)
    assert "consent" in err.message.lower()


def test_llm_unavailable_error() -> None:
    err = LLMUnavailableError()
    assert err.status_code == 502
    assert err.code == "LLM_UNAVAILABLE"
    assert "unavailable" in err.message.lower()


def test_llm_blocked_error() -> None:
    err = LLMBlockedError()
    assert err.status_code == 502
    assert err.code == "LLM_BLOCKED"
    assert "safety" in err.message.lower()


def test_search_unavailable_error() -> None:
    err = SearchUnavailableError()
    assert err.status_code == 503
    assert err.code == "SEARCH_UNAVAILABLE"
    assert "unavailable" in err.message.lower()


def test_error_messages_are_fixed_english_text() -> None:
    for cls in (ConsentRequiredError, LLMUnavailableError, LLMBlockedError, SearchUnavailableError):
        err = cls()
        assert isinstance(err.message, str)
        assert len(err.message) > 10
