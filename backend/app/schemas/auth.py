import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints, field_validator

MAX_EMAIL_LENGTH = 255
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


# Bidirectional marks, embeddings, overrides and isolates: they allow visual spoofing of names.
BIDI_CONTROLS = frozenset(
    chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F)
)


def ensure_no_control_characters(value: str) -> str:
    """Names are single-line plain text.

    Rejects control characters (PostgreSQL cannot store NUL), Unicode line and paragraph
    separators and bidirectional controls. Joiners used by real scripts (ZWNJ, ZWJ) stay allowed.
    """
    for char in value:
        if unicodedata.category(char) in {"Cc", "Zl", "Zp"} or char in BIDI_CONTROLS:
            raise ValueError("contains control or direction characters")
    return value


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(ensure_no_control_characters),
]


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValueError("email is too long")
    return email


class RegisterRequest(BaseModel):
    """Public registration. Any `role` sent by the client is ignored (extra fields are dropped)."""

    name: Name
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: EmailStr
    # No minimum here: the length policy applies when a password is chosen, not when it is checked.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return normalize_email(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
