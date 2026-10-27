"""Helpers to forge tokens by hand so tests can break individual claims."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import Settings
from tests.constants import TEST_JWT_SECRET


def forge_token(
    settings: Settings,
    user_id: uuid.UUID | str,
    *,
    secret: str = TEST_JWT_SECRET,
    algorithm: str = "HS256",
    minutes_valid: int = 60,
    issued_minutes_ago: int = 0,
    drop: tuple[str, ...] = (),
    **overrides: Any,
) -> str:
    now = datetime.now(UTC) - timedelta(minutes=issued_minutes_ago)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes_valid)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    claims.update(overrides)
    for name in drop:
        claims.pop(name, None)
    return jwt.encode(claims, secret, algorithm=algorithm)
