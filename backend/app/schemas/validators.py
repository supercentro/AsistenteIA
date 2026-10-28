"""Reusable field validators shared by the request schemas (names, descriptions, emails)."""

import unicodedata
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, Field, StringConstraints

MAX_EMAIL_LENGTH = 255
MAX_USER_NAME_LENGTH = 100
MAX_SUBJECT_NAME_LENGTH = 150
MAX_DESCRIPTION_LENGTH = 2000

# Bidirectional marks, embeddings, overrides and isolates: they allow visual spoofing of names.
BIDI_CONTROLS = frozenset(
    chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F)
)

# Line breaks and tabs are legitimate in free text such as descriptions.
_TEXT_WHITESPACE = frozenset("\n\r\t")


def ensure_no_control_characters(value: str) -> str:
    """Names are single-line plain text.

    Rejects control characters (PostgreSQL cannot store NUL), Unicode line and paragraph
    separators and bidirectional controls. Joiners used by real scripts (ZWNJ, ZWJ) stay allowed.
    """
    for char in value:
        if unicodedata.category(char) in {"Cc", "Zl", "Zp"} or char in BIDI_CONTROLS:
            raise ValueError("contains control or direction characters")
    return value


def ensure_plain_text(value: str) -> str:
    """Free text: like a name, but line breaks and tabs are allowed."""
    for char in value:
        if char in _TEXT_WHITESPACE:
            continue
        if unicodedata.category(char) in {"Cc", "Zl", "Zp"} or char in BIDI_CONTROLS:
            raise ValueError("contains control or direction characters")
    return value


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_USER_NAME_LENGTH),
    AfterValidator(ensure_no_control_characters),
]

SubjectName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_SUBJECT_NAME_LENGTH),
    AfterValidator(ensure_no_control_characters),
]

Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=MAX_DESCRIPTION_LENGTH),
    AfterValidator(ensure_plain_text),
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


# The limit is enforced by `normalize_email`; `maxLength` only documents it in the OpenAPI schema.
Email = Annotated[
    str,
    AfterValidator(ascii_email),
    Field(json_schema_extra={"format": "email", "maxLength": MAX_EMAIL_LENGTH}),
]
