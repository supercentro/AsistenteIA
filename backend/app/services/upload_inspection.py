"""What an upload is: a cleaned file name and a type decided from the content (change 6, task 9.1).

The client `Content-Type` is not an input of this module: the type follows the extension of the
cleaned name and must agree with the first bytes (a PDF signature) or with the whole content
(strict UTF-8 without NUL for text and Markdown). Every rejection is a controlled error with a
fixed message and, for `422`, a fixed `details.reason`; the name and the content are never
placed in an error.
"""

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import UnsupportedMediaTypeError, UploadValidationError
from app.schemas.validators import BIDI_CONTROLS

MAX_FILENAME_LENGTH = 255
_PDF_SIGNATURE = b"%PDF-"
_UTF8_BOM = b"\xef\xbb\xbf"
_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}
_REMOVED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})


class UploadRejection(StrEnum):
    """The fixed `details.reason` values of a `422` on the upload (see the API contract)."""

    MALFORMED_MULTIPART = "MALFORMED_MULTIPART"
    FILE_PART_MISSING = "FILE_PART_MISSING"
    UNEXPECTED_FIELDS = "UNEXPECTED_FIELDS"
    EMPTY_FILE = "EMPTY_FILE"
    INVALID_FILENAME = "INVALID_FILENAME"


_MESSAGES = {
    UploadRejection.MALFORMED_MULTIPART: "The upload is not a valid multipart request",
    UploadRejection.FILE_PART_MISSING: "The request has no file part named 'file'",
    UploadRejection.UNEXPECTED_FIELDS: "Send exactly one file and no other fields",
    UploadRejection.EMPTY_FILE: "The file is empty",
    UploadRejection.INVALID_FILENAME: "The file name is not valid",
}


def rejection(reason: UploadRejection) -> UploadValidationError:
    """The `422` for `reason`, with its fixed message."""
    return UploadValidationError(reason.value, _MESSAGES[reason])


@dataclass(frozen=True)
class InspectedUpload:
    filename: str
    content_type: str


def clean_filename(raw: str | None) -> str:
    """The last path component of the client name without control or direction characters.

    Raises the `INVALID_FILENAME` rejection when nothing usable is left, when the name is `.` or
    `..`, or when it exceeds `MAX_FILENAME_LENGTH` characters after cleaning.
    """
    if raw is None:
        raise rejection(UploadRejection.INVALID_FILENAME)
    last = raw.replace("\\", "/").rsplit("/", 1)[-1]
    kept = "".join(
        char
        for char in last
        if unicodedata.category(char) not in _REMOVED_CATEGORIES and char not in BIDI_CONTROLS
    ).strip()
    if not kept or kept in {".", ".."} or len(kept) > MAX_FILENAME_LENGTH:
        raise rejection(UploadRejection.INVALID_FILENAME)
    return kept


def inspect_upload(raw_filename: str | None, content: bytes) -> InspectedUpload:
    """Validate the name and the content; return the stored name and the decided content type.

    Order: name (`422`), empty file (`422`), type (`415`).
    """
    filename = clean_filename(raw_filename)
    if not content:
        raise rejection(UploadRejection.EMPTY_FILE)
    stem, dot, extension = filename.rpartition(".")
    content_type = _TYPES.get("." + extension.lower()) if dot and stem else None
    if content_type is None:
        raise UnsupportedMediaTypeError
    if content_type == "application/pdf":
        if not content.startswith(_PDF_SIGNATURE):
            raise UnsupportedMediaTypeError
    elif not _is_plain_utf8(content):
        raise UnsupportedMediaTypeError
    return InspectedUpload(filename, content_type)


def _is_plain_utf8(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return True
