"""The model used by the harness makes exactly one request per call and records error kinds."""

import asyncio
from typing import Any

import pytest

from app.core.config import Settings
from tests.constants import TEST_JWT_SECRET
from tests.evaluation.llm import RecordingModel, build_gemini_service


class _ProviderError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = status_code  # the attribute google.genai errors carry


class _FailingModel:
    async def ainvoke(self, messages: Any) -> Any:
        raise _ProviderError(429, "quota exceeded for key AIzaSySECRET")


def test_the_gemini_service_of_the_harness_makes_one_attempt_per_call() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@db:5432/x_test",
        jwt_secret=TEST_JWT_SECRET,
        google_api_key="AIza-not-a-real-key",
        app_env="test",
        cors_origins=["http://localhost:5173"],
    )

    service = build_gemini_service(settings)

    # 1 means one attempt (the library passes it as HttpRetryOptions(attempts=1))
    assert service._model._inner.max_retries == 1  # noqa: SLF001 - the point of the test


def test_the_recording_model_counts_error_kinds_and_keeps_no_message() -> None:
    model = RecordingModel(_FailingModel())

    with pytest.raises(_ProviderError):
        asyncio.run(model.ainvoke([]))
    with pytest.raises(_ProviderError):
        asyncio.run(model.ainvoke([]))

    assert model.error_kinds == {"_ProviderError:429": 2}
    assert "AIzaSySECRET" not in repr(model.error_kinds)
    assert model.requests == 2
