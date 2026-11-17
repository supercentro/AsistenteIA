"""LLM service: protocol, Gemini wrapper and fake for tests (design D1).

The ``LLMService`` protocol isolates the rest of the codebase from the LangChain API surface.
Only this module imports ``langchain-google-genai``.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.core.errors import LLMBlockedError, LLMUnavailableError

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)


# --- protocol ----------------------------------------------------------------------------------


@runtime_checkable
class LLMService(Protocol):
    async def generate(
        self,
        system_prompt: str,
        user_messages: list[dict[str, str]],
    ) -> str: ...


# --- fake ---------------------------------------------------------------------------------------


class FakeLLMService:
    """Deterministic LLM for tests: the answer includes a hash of the last user message."""

    async def generate(
        self,
        system_prompt: str,
        user_messages: list[dict[str, str]],
    ) -> str:
        last = user_messages[-1]["content"] if user_messages else ""
        digest = hashlib.md5(last.encode()).hexdigest()[:8]  # noqa: S324
        return f"[FakeLLM:{digest}] Based on the provided context, here is the answer to: {last}"


def _answer_text(content: object) -> str:
    """Return the text of a provider message: a string, or the text of its content blocks.

    Blocks that carry no text (images, tool calls) are ignored. An answer with no text at all
    comes back as an empty string, which the caller treats as a blocked answer.
    """
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts).strip()


# --- Gemini (langchain-google-genai) -----------------------------------------------------------


class GeminiLLMService:
    """Wraps ``ChatGoogleGenerativeAI`` behind the ``LLMService`` protocol."""

    def __init__(self, model: Any, timeout_seconds: int) -> None:
        self._model = model
        self._timeout = timeout_seconds

    async def generate(
        self,
        system_prompt: str,
        user_messages: list[dict[str, str]],
    ) -> str:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages: list[SystemMessage | HumanMessage | AIMessage] = [
            SystemMessage(content=system_prompt),
        ]
        for msg in user_messages:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        try:
            response = await self._model.ainvoke(messages)
        except TimeoutError:
            logger.warning("llm timeout")
            raise LLMUnavailableError() from None
        except Exception as exc:
            if _is_safety_block(exc):
                logger.warning("llm safety block")
                raise LLMBlockedError() from None
            if _is_rate_limit_or_server_error(exc):
                logger.warning("llm provider error")
                raise LLMUnavailableError() from None
            logger.warning("llm unexpected error")
            raise LLMUnavailableError() from None

        if _is_blocked_response(response):
            logger.warning("llm safety block")
            raise LLMBlockedError()
        text = _answer_text(response.content)
        if not text:
            logger.warning("llm empty answer")
            raise LLMBlockedError()
        return text


def _is_rate_limit_or_server_error(exc: BaseException) -> bool:
    try:
        from google.genai.errors import ClientError, ServerError

        if isinstance(exc, (ClientError, ServerError)):
            return True
    except ImportError:
        pass
    cls_name = type(exc).__name__
    return "ServerError" in cls_name or "ClientError" in cls_name


_REFUSAL_FINISH_REASONS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"})
_NO_BLOCK_REASONS = frozenset({"", "0", "BLOCK_REASON_UNSPECIFIED"})


def _is_blocked_response(response: object) -> bool:
    """A refusal reported by the provider in the response metadata (structured signals only)."""
    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, dict):
        return False
    if str(metadata.get("finish_reason", "")).upper() in _REFUSAL_FINISH_REASONS:
        return True
    feedback = metadata.get("prompt_feedback")
    if not isinstance(feedback, dict):
        return False
    reason = feedback.get("block_reason")
    reason = getattr(reason, "name", reason)
    if isinstance(reason, bool):
        return False
    if isinstance(reason, int):
        return reason != 0
    return isinstance(reason, str) and reason.strip().upper() not in _NO_BLOCK_REASONS


def _is_safety_block(exc: BaseException) -> bool:
    """A provider error that names a safety block.

    The status code decides first: 429 and 5xx are never a block, whatever their text says. The
    text counts only for an exception of the Google client libraries, with no status code or 400.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code != 400:
        return False
    if not type(exc).__module__.startswith(("google.", "langchain_google_genai")):
        return False
    msg = str(exc).lower()
    return "safety" in msg or "blocked" in msg


# --- factory ------------------------------------------------------------------------------------


def build_llm_service(settings: Settings) -> LLMService:
    """Build the configured LLM service (same pattern as ``build_embedder``)."""
    if settings.llm_backend == "fake":
        return FakeLLMService()

    from langchain_google_genai import ChatGoogleGenerativeAI

    if settings.google_api_key is None:  # pragma: no cover – guarded by the validator
        msg = "GOOGLE_API_KEY is required"
        raise ValueError(msg)
    model = ChatGoogleGenerativeAI(
        model=settings.chat_llm_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        timeout=settings.chat_llm_timeout_seconds,
    )
    return GeminiLLMService(model=model, timeout_seconds=settings.chat_llm_timeout_seconds)
