"""Unit tests for LLMService protocol, FakeLLMService and GeminiLLMService (task 2.1)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import LLMBlockedError, LLMUnavailableError
from app.services.llm_service import (
    FakeLLMService,
    GeminiLLMService,
    LLMService,
    build_llm_service,
)

# --- protocol conformance ---


def test_fake_llm_service_satisfies_the_protocol() -> None:
    assert isinstance(FakeLLMService(), LLMService)


# --- FakeLLMService ---


@pytest.mark.asyncio
async def test_fake_llm_returns_deterministic_string_with_chunk_references() -> None:
    service = FakeLLMService()
    result = await service.generate(
        system_prompt="You are a helpful assistant.",
        user_messages=[{"role": "user", "content": "What is the capital of France?"}],
    )

    assert isinstance(result, str)
    assert len(result) > 0
    assert "FakeLLM" in result


@pytest.mark.asyncio
async def test_fake_llm_response_is_deterministic() -> None:
    service = FakeLLMService()
    messages = [{"role": "user", "content": "Tell me about biology"}]

    r1 = await service.generate("system", messages)
    r2 = await service.generate("system", messages)

    assert r1 == r2


@pytest.mark.asyncio
async def test_fake_llm_includes_message_content_reference() -> None:
    service = FakeLLMService()
    result = await service.generate(
        system_prompt="system",
        user_messages=[{"role": "user", "content": "about photosynthesis"}],
    )

    assert "photosynthesis" in result.lower() or "FakeLLM" in result


# --- GeminiLLMService (mocked) ---


@pytest.mark.asyncio
async def test_gemini_service_success() -> None:
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Paris is the capital of France."
    mock_model.ainvoke = AsyncMock(return_value=mock_response)

    service = GeminiLLMService(model=mock_model, timeout_seconds=30)
    result = await service.generate(
        system_prompt="Answer from context only.",
        user_messages=[{"role": "user", "content": "What is the capital of France?"}],
    )

    assert result == "Paris is the capital of France."
    mock_model.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_service_timeout_raises_llm_unavailable() -> None:
    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=TimeoutError("request timed out"))

    service = GeminiLLMService(model=mock_model, timeout_seconds=30)

    with pytest.raises(LLMUnavailableError):
        await service.generate("system", [{"role": "user", "content": "test"}])


@pytest.mark.asyncio
async def test_gemini_service_server_error_raises_llm_unavailable() -> None:
    from google.genai.errors import ServerError

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(side_effect=ServerError(500, {"error": {"message": "internal"}}))

    service = GeminiLLMService(model=mock_model, timeout_seconds=30)

    with pytest.raises(LLMUnavailableError):
        await service.generate("system", [{"role": "user", "content": "test"}])


@pytest.mark.asyncio
async def test_gemini_service_client_error_raises_llm_unavailable() -> None:
    from google.genai.errors import ClientError

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(
        side_effect=ClientError(429, {"error": {"message": "rate limit"}})
    )

    service = GeminiLLMService(model=mock_model, timeout_seconds=30)

    with pytest.raises(LLMUnavailableError):
        await service.generate("system", [{"role": "user", "content": "test"}])


@pytest.mark.asyncio
async def test_gemini_service_safety_block_raises_llm_blocked() -> None:
    from google.genai.errors import ClientError

    mock_model = MagicMock()
    mock_model.ainvoke = AsyncMock(
        side_effect=ClientError(
            400, {"error": {"message": "Content was blocked by safety filters"}}
        )
    )

    service = GeminiLLMService(model=mock_model, timeout_seconds=30)

    with pytest.raises(LLMBlockedError):
        await service.generate("system", [{"role": "user", "content": "test"}])


# --- build_llm_service factory ---


def test_build_llm_service_returns_fake_when_configured() -> None:
    settings = MagicMock()
    settings.llm_backend = "fake"

    service = build_llm_service(settings)

    assert isinstance(service, FakeLLMService)


def test_build_llm_service_returns_gemini_when_configured() -> None:
    settings = MagicMock()
    settings.llm_backend = "gemini"
    settings.google_api_key = MagicMock()
    settings.google_api_key.get_secret_value.return_value = "AIza-test-key"
    settings.chat_llm_model = "gemini-2.5-flash"
    settings.chat_llm_timeout_seconds = 30

    with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        service = build_llm_service(settings)

    assert isinstance(service, GeminiLLMService)


# --- error classes ---


def test_llm_unavailable_error_has_fixed_message() -> None:
    err = LLMUnavailableError()
    assert err.status_code == 502
    assert err.code == "LLM_UNAVAILABLE"


def test_llm_blocked_error_has_fixed_message() -> None:
    err = LLMBlockedError()
    assert err.status_code == 502
    assert err.code == "LLM_BLOCKED"
