"""Guards of the harness: real model permission, call cap, isolated database, secret scrubbing."""

import re
from collections.abc import Iterable

from app.core.db_safety import UnsafeTestDatabaseError, assert_safe_test_database


class HarnessRefusedError(RuntimeError):
    """The harness refuses to run; the message never carries a secret."""


class CallCapExceededError(HarnessRefusedError):
    """More model calls are needed than the cap allows; raised before the first call."""


# The owner authorised at most 50 real free-tier requests for the evaluation (2026-11-20).
MAX_REAL_REQUESTS = 50


def require_cap_within_ceiling(cap: int) -> None:
    if not 0 <= cap <= MAX_REAL_REQUESTS:
        raise HarnessRefusedError(
            f"--max-calls must be between 0 and {MAX_REAL_REQUESTS} (the authorised ceiling)"
        )


def require_real_model_permission(*, llm: str, allow_real_llm: bool) -> None:
    if llm == "gemini" and not allow_real_llm:
        raise HarnessRefusedError(
            "the real model is only used with --allow-real-llm (free tier, fictitious data)"
        )


def plan_model_calls(*, needed: int, cap: int) -> int:
    """Return the number of calls to make, or stop before the first one when it exceeds the cap."""
    if needed > cap:
        raise CallCapExceededError(
            f"{needed} model calls are needed but the cap is {cap}; "
            "raise --max-calls or mark fewer cases for the model"
        )
    return needed


def assert_isolated_database(test_url: str, app_url: str | None, app_env: str) -> None:
    """Use the guard of the test suite and add the harness's own refusal."""
    try:
        assert_safe_test_database(test_url, app_url, app_env)
    except UnsafeTestDatabaseError as error:
        raise HarnessRefusedError(f"refusing to run: {error}") from None


_URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+(@)")


def scrub(text: str, secrets: Iterable[str]) -> str:
    """Remove the given secrets and the password of any database URL from `text`."""
    cleaned = text
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        cleaned = cleaned.replace(secret, "***")
    return _URL_PASSWORD.sub(r"\1***\2", cleaned)
