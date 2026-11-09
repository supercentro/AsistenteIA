"""The closed catalogue of failure codes and their fixed messages (group 3, task 3.2)."""

import re

from app.models.ingestion import (
    DOCUMENT_ERROR_CODE_MAX_LENGTH,
    DOCUMENT_ERROR_MESSAGES,
    DocumentErrorCode,
)

# The `document-ingestion` spec lists exactly these twelve codes.
EXPECTED_CODES = {
    "NO_EXTRACTABLE_TEXT",
    "ENCRYPTED_PDF",
    "CORRUPT_FILE",
    "TOO_MANY_PAGES",
    "TEXT_TOO_LARGE",
    "TOO_MANY_CHUNKS",
    "PROCESSING_TIMEOUT",
    "RESOURCE_LIMIT_EXCEEDED",
    "EMBEDDING_FAILED",
    "PROCESSING_INTERRUPTED",
    "JOB_EXPIRED",
    "PROCESSING_FAILED",
}


def test_the_catalogue_is_exactly_the_twelve_codes_of_the_spec() -> None:
    assert {code.value for code in DocumentErrorCode} == EXPECTED_CODES
    assert len(DocumentErrorCode) == 12


def test_each_member_name_equals_its_value() -> None:
    assert all(code.name == code.value for code in DocumentErrorCode)


def test_codes_fit_the_database_column() -> None:
    assert DOCUMENT_ERROR_CODE_MAX_LENGTH == 40
    assert all(len(code.value) <= DOCUMENT_ERROR_CODE_MAX_LENGTH for code in DocumentErrorCode)
    assert all(re.fullmatch(r"[A-Z][A-Z_]+", code.value) for code in DocumentErrorCode)


def test_every_code_has_exactly_one_fixed_message() -> None:
    assert set(DOCUMENT_ERROR_MESSAGES) == set(DocumentErrorCode)
    assert len(set(DOCUMENT_ERROR_MESSAGES.values())) == len(DocumentErrorCode)


def test_messages_are_short_plain_english_sentences() -> None:
    for code, message in DOCUMENT_ERROR_MESSAGES.items():
        assert message.isascii(), code
        assert message == message.strip(), code
        assert message.endswith("."), code
        assert 10 <= len(message) <= 200, code


def test_messages_cannot_carry_parser_database_or_system_text() -> None:
    """Fixed sentences: no placeholders, paths, quotes or traces that could be filled in later."""
    for code, message in DOCUMENT_ERROR_MESSAGES.items():
        assert not re.search(r"[{}%\\/<>\"'`]", message), code
        assert "Traceback" not in message and "Error:" not in message, code
