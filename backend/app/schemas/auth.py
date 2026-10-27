import unicodedata
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, Field, StringConstraints

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
    """Trim and lowercase; emails are ASCII only (internationalised domains as punycode)."""
    email = value.strip().lower()
    if not email.isascii():
        raise ValueError("email must contain only ASCII characters")
    if len(email) > MAX_EMAIL_LENGTH:
        raise ValueError("email is too long")
    return email


def ascii_email(value: str) -> str:
    """Validate the syntax and return the lowercase ASCII form.

    Non-ASCII input is rejected before validation: `email-validator` would otherwise convert a
    punycode domain to Unicode, and look-alike addresses must never become separate accounts.
    The messages are fixed so the submitted value is never echoed.
    """
    raw = normalize_email(value)
    try:
        checked = validate_email(raw, check_deliverability=False, allow_smtputf8=False)
    except EmailNotValidError:
        raise ValueError("value is not a valid email address") from None
    return normalize_email(checked.ascii_email or checked.normalized)


Email = Annotated[str, AfterValidator(ascii_email), Field(json_schema_extra={"format": "email"})]


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
