"""The real model as the harness uses it: one request per call, no hidden retries.

The application builds `ChatGoogleGenerativeAI` with the library's retry policy, so one logical
call can become several real requests. The harness counts the free-tier requests it
makes (the cap counts calls, one attempt each), so it builds the same wrapper with a single
attempt and records the kind of every failure (the class and the HTTP status, never the message).
"""

from collections import Counter
from typing import Any

from app.core.config import Settings
from app.services.llm_service import GeminiLLMService, _status_code


class RecordingModel:
    """Delegates `ainvoke`, counts the requests and the kinds of the errors."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.requests = 0
        self.error_kinds: Counter[str] = Counter()

    async def ainvoke(self, messages: Any) -> Any:
        self.requests += 1
        try:
            return await self._inner.ainvoke(messages)
        except Exception as error:
            self.error_kinds[f"{type(error).__name__}:{_status_code(error)}"] += 1
            raise


class HarnessGeminiService(GeminiLLMService):
    """The application's Gemini wrapper plus access to what the recording model saw."""

    def __init__(self, model: RecordingModel, timeout_seconds: int) -> None:
        super().__init__(model=model, timeout_seconds=timeout_seconds)
        self.recorder = model


def build_gemini_service(settings: Settings) -> HarnessGeminiService:
    """Gemini behind the application's wrapper, with retries disabled and requests recorded."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    if settings.google_api_key is None:
        raise ValueError("GOOGLE_API_KEY is required")
    model = ChatGoogleGenerativeAI(
        model=settings.chat_llm_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        timeout=settings.chat_llm_timeout_seconds,
        max_retries=1,  # HttpRetryOptions(attempts=1): a single attempt, no hidden retries
    )
    return HarnessGeminiService(RecordingModel(model), settings.chat_llm_timeout_seconds)
