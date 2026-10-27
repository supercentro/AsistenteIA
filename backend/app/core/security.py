"""Password hashing (Argon2id) and access-token (HS256 JWT) primitives.

Nothing here logs: callers must never log passwords, hashes, tokens or the secret.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings
from app.core.errors import UnauthorizedError

JWT_ALGORITHM = "HS256"
REQUIRED_CLAIMS = ["sub", "iat", "exp", "iss", "aud"]
TOKEN_ERROR_MESSAGE = "Invalid or expired token"  # noqa: S105 - error text, not a secret


class PasswordService:
    """Argon2id hashing. Defaults are the argon2-cffi (RFC 9106 low-memory) parameters.

    Tests pass small explicit costs to stay fast; production uses the defaults.
    """

    def __init__(
        self,
        time_cost: int | None = None,
        memory_cost: int | None = None,
        parallelism: int | None = None,
    ) -> None:
        params: dict[str, Any] = {
            name: value
            for name, value in (
                ("time_cost", time_cost),
                ("memory_cost", memory_cost),
                ("parallelism", parallelism),
            )
            if value is not None
        }
        self._hasher = PasswordHasher(**params)
        # Hash of a random value nobody knows: used to spend equal work for unknown accounts.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def verify_dummy(self, password: str) -> bool:
        """Perform a verification that always fails, with the same cost as a real one."""
        self.verify(password, self._dummy_hash)
        return False


def encode_access_token(user_id: uuid.UUID, settings: Settings, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings, now: datetime | None = None) -> uuid.UUID:
    """Return the user id of a valid token; raise one generic `UnauthorizedError` otherwise.

    Signature, algorithm (HS256 only), issuer, audience and the presence of every required
    claim are checked by PyJWT. Expiry and issue time are checked here against `now` (no leeway)
    so tests can control the clock.
    """
    current = (now or datetime.now(UTC)).timestamp()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={
                "require": REQUIRED_CLAIMS,
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        exp, iat, subject = claims["exp"], claims["iat"], claims["sub"]
        for value in (exp, iat):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError("non-numeric time claim")
        if current >= exp or iat > current:
            raise ValueError("token not currently valid")
        # Strict: the audience must be exactly ours (not a list) and the subject canonical.
        if claims["aud"] != settings.jwt_audience:
            raise ValueError("unexpected audience")
        user_id = uuid.UUID(str(subject))
        if not isinstance(subject, str) or str(user_id) != subject:
            raise ValueError("non-canonical subject")
        return user_id
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise UnauthorizedError(
            TOKEN_ERROR_MESSAGE, headers={"WWW-Authenticate": "Bearer"}
        ) from None
