from pydantic import BaseModel, Field

from app.schemas.validators import (
    MAX_EMAIL_LENGTH,
    Email,
    Name,
    ensure_no_control_characters,
    normalize_email,
)

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128

# Re-exported for the CLI and existing callers; the rules live in `schemas/validators.py`.
__all__ = [
    "MAX_EMAIL_LENGTH",
    "MAX_PASSWORD_LENGTH",
    "MIN_PASSWORD_LENGTH",
    "Email",
    "LoginRequest",
    "Name",
    "RegisterRequest",
    "TokenResponse",
    "ensure_no_control_characters",
    "normalize_email",
]


class RegisterRequest(BaseModel):
    """Public registration. Any `role` sent by the client is ignored (extra fields are dropped)."""

    name: Name
    email: Email
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    email: Email
    # No minimum here: the length policy applies when a password is chosen, not when it is checked.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
