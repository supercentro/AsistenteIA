"""Cleaning of the client file name and the decision of the file type (change 6, task 9.1).

The type is decided from the extension and the content; the client `Content-Type` plays no part
(there is no parameter for it). Every rejection carries a fixed reason and never the input.
"""

import pytest

from app.core.errors import UnsupportedMediaTypeError, UploadValidationError
from app.services.upload_inspection import (
    MAX_FILENAME_LENGTH,
    UploadRejection,
    clean_filename,
    inspect_upload,
)

PDF = b"%PDF-1.7\n1 0 obj\n"
TEXT = "Derivadas e integrales: ñandú, áéíóú.".encode()


def reason(error: pytest.ExceptionInfo[UploadValidationError]) -> object:
    assert error.value.details is not None
    return error.value.details["reason"]


# --- the file name ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("unit1.pdf", "unit1.pdf"),
        (r"..\..\notes/unit1.pdf", "unit1.pdf"),
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\teacher\\unit1.md", "unit1.md"),
        ("/absolute/path/unit1.txt", "unit1.txt"),
        ("  spaced name .txt  ", "spaced name .txt"),
        ("ünïcode-ñame.txt", "ünïcode-ñame.txt"),
        ("tab\tinside.txt", "tabinside.txt"),
        ("new\nline\r.txt", "newline.txt"),
        ("nul\x00byte.txt", "nulbyte.txt"),
        ("rtl\u202eexe.txt", "rtlexe.txt"),
        ("isolate\u2066x\u2069.txt", "isolatex.txt"),
        ("sep\u2028arator\u2029.txt", "separator.txt"),
        ("marks\u200e\u200f.txt", "marks.txt"),
    ],
)
def test_the_name_is_the_last_component_without_hostile_characters(raw: str, expected: str) -> None:
    assert clean_filename(raw) == expected


def test_a_name_at_the_length_limit_is_kept() -> None:
    name = "a" * (MAX_FILENAME_LENGTH - 4) + ".txt"

    assert clean_filename(name) == name


def test_a_name_over_the_length_limit_is_rejected_after_cleaning() -> None:
    with pytest.raises(UploadValidationError) as error:
        clean_filename("a" * MAX_FILENAME_LENGTH + ".txt")

    assert reason(error) == UploadRejection.INVALID_FILENAME


def test_controls_do_not_count_towards_the_length() -> None:
    name = ("a\u202e" * (MAX_FILENAME_LENGTH - 4)) + ".txt"  # long only before cleaning

    assert len(clean_filename(name)) == MAX_FILENAME_LENGTH


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "\u202e\u202e", "\x00\x01", "dir/", "..\\..\\", "/", ".", "..", "a/.."],
)
def test_a_name_that_is_empty_after_cleaning_is_rejected(raw: str | None) -> None:
    with pytest.raises(UploadValidationError) as error:
        clean_filename(raw)

    assert reason(error) == UploadRejection.INVALID_FILENAME


def test_the_rejection_never_contains_the_name() -> None:
    marker = "MARKER-NAME-" + "x" * MAX_FILENAME_LENGTH
    with pytest.raises(UploadValidationError) as error:
        clean_filename(marker)

    assert marker not in str(error.value)
    assert marker not in repr(error.value.details)


# --- empty files --------------------------------------------------------------------------------


def test_an_empty_file_is_rejected_before_its_type_is_decided() -> None:
    with pytest.raises(UploadValidationError) as error:
        inspect_upload("notes.exe", b"")

    assert reason(error) == UploadRejection.EMPTY_FILE


def test_the_name_is_validated_before_the_content() -> None:
    with pytest.raises(UploadValidationError) as error:
        inspect_upload("..", b"")

    assert reason(error) == UploadRejection.INVALID_FILENAME


# --- the type -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("unit1.pdf", PDF, "application/pdf"),
        ("UNIT1.PDF", PDF, "application/pdf"),
        ("notes.txt", TEXT, "text/plain"),
        ("notes.TXT", TEXT, "text/plain"),
        ("notes.md", b"# Title\n\n- item\n", "text/markdown"),
        ("notes.txt", b"\xef\xbb\xbfwith bom", "text/plain"),
        ("notes.txt", b"x", "text/plain"),
    ],
)
def test_the_type_follows_the_extension_when_the_content_agrees(
    name: str, content: bytes, expected: str
) -> None:
    inspected = inspect_upload(name, content)

    assert inspected.content_type == expected
    assert inspected.filename == name


def test_the_stored_name_is_the_cleaned_one() -> None:
    assert inspect_upload(r"..\..\notes/unit1.pdf", PDF).filename == "unit1.pdf"


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("unit1.pdf", b"MZ\x90\x00 executable"),
        ("notes.txt", b"MZ\x90\x00 executable"),
        ("unit1.pdf", b"plain text, not a pdf"),
        ("unit1.pdf", b" %PDF-1.7 leading space"),
        ("unit1.pdf", b"%PDX-1.7"),
        ("unit1.pdf", b"%PDF"),
        ("notes.txt", b"\xff\xfe invalid utf-8"),
        ("notes.md", b"caf\xe9 latin-1"),
        ("notes.txt", b"with\x00nul"),
        ("notes.md", b"\x00"),
        ("notes.txt", "surrogate \ud800".encode("utf-8", "surrogatepass")),
        ("notes.exe", PDF),
        ("notes.docx", PDF),
        ("notes", TEXT),
        (".txt", TEXT),
        ("archive.tar.gz", TEXT),
        ("notes.txt.exe", TEXT),
        ("notes.pdf ", PDF[:4]),
    ],
)
def test_a_type_that_is_not_allowed_or_does_not_match_is_unsupported(
    name: str, content: bytes
) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        inspect_upload(name, content)


def test_the_extension_is_the_text_after_the_last_dot_of_the_cleaned_name() -> None:
    assert inspect_upload("report.v2.final.txt", TEXT).content_type == "text/plain"
    with pytest.raises(UnsupportedMediaTypeError):
        inspect_upload("notes.txt/.exe", TEXT)  # the last path component is ".exe"


def test_a_pdf_signature_does_not_make_a_text_file_a_pdf() -> None:
    assert inspect_upload("notes.txt", PDF).content_type == "text/plain"  # valid UTF-8 text


def test_the_unsupported_answer_never_contains_the_name_or_the_content() -> None:
    marker = "MARKER-CONTENT-4411"
    with pytest.raises(UnsupportedMediaTypeError) as error:
        inspect_upload("MARKER-NAME-9921.exe", marker.encode())

    text = str(error.value) + repr(error.value.details)
    assert marker not in text
    assert "MARKER-NAME-9921" not in text
