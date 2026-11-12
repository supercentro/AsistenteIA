"""Leak tests for the loaders and the PDF child (change 6, task 6.3).

Markers placed in the file content, in the PDF metadata, in the child's error detail and in its
standard error must never reach an exception, its representation, a traceback or a log record.
Only the extracted text may carry content, and only through the returned pages.
"""

import logging
import sys
import traceback
from pathlib import Path

import pytest

from app.models.ingestion import DocumentErrorCode
from app.rag.loaders import DocumentLoadError, PdfLimits, load_markdown, load_pdf, load_text
from tests import pdf_support
from tests.child_support import END, install

MARKER = "LEAKMARKER-5521-document-secret"
LIMITS = PdfLimits(
    max_pages=300,
    max_chars=2_000_000,
    memory_mb=768,
    cpu_seconds=20,
    timeout_seconds=30,
    max_output_bytes=8 * 1024 * 1024,
)
linux_only = pytest.mark.skipif(
    sys.platform != "linux", reason="the PDF child runs on Linux only (resource limits)"
)


@pytest.fixture(autouse=True)
def all_logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


def surfaces(error: BaseException) -> str:
    """Everything an error can show: str, repr, arguments, and the formatted traceback."""
    formatted = "".join(traceback.format_exception(error))
    return f"{error!s}|{error!r}|{error.args!r}|{formatted}"


def assert_clean(
    error: BaseException, caplog: pytest.LogCaptureFixture, *, marker: str = MARKER
) -> None:
    assert marker not in surfaces(error)
    assert marker not in caplog.text
    assert [record for record in caplog.records if marker in record.getMessage()] == []


class TestTextLoaders:
    @pytest.mark.parametrize("loader", [load_text, load_markdown])
    def test_an_invalid_file_does_not_echo_its_content(
        self, loader: object, all_logs: pytest.LogCaptureFixture
    ) -> None:
        payload = MARKER.encode() + b"\xff" + MARKER.encode()

        with pytest.raises(DocumentLoadError) as caught:
            loader(payload)  # type: ignore[operator]

        assert_clean(caught.value, all_logs)
        assert caught.value.code is DocumentErrorCode.CORRUPT_FILE

    @pytest.mark.parametrize("loader", [load_text, load_markdown])
    def test_a_file_with_nul_does_not_echo_its_content(
        self, loader: object, all_logs: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(DocumentLoadError) as caught:
            loader(f"{MARKER}\x00{MARKER}".encode())  # type: ignore[operator]

        assert_clean(caught.value, all_logs)

    def test_a_file_over_the_cap_does_not_echo_its_content(
        self, all_logs: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(DocumentLoadError) as caught:
            load_text(MARKER.encode() * 5, max_chars=10)

        assert_clean(caught.value, all_logs)
        assert caught.value.code is DocumentErrorCode.TEXT_TOO_LARGE

    @pytest.mark.parametrize("loader", [load_text, load_markdown])
    def test_a_valid_file_returns_its_text_and_logs_nothing(
        self, loader: object, all_logs: pytest.LogCaptureFixture
    ) -> None:
        pages = loader(f"hola {MARKER}".encode())  # type: ignore[operator]

        assert pages[0].text == f"hola {MARKER}"
        assert all_logs.records == []

    def test_a_blank_file_logs_nothing(self, all_logs: pytest.LogCaptureFixture) -> None:
        with pytest.raises(DocumentLoadError):
            load_text(b"   ")

        assert all_logs.records == []


@linux_only
class TestPdfLoader:
    def test_metadata_never_reaches_the_returned_pages(
        self, all_logs: pytest.LogCaptureFixture
    ) -> None:
        pdf = pdf_support.pdf_with_metadata(MARKER, "visible body text")

        pages = load_pdf(pdf, LIMITS)

        assert [page.text for page in pages] == ["visible body text"]
        assert MARKER not in repr(pages)
        assert all_logs.records == []

    def test_body_text_is_returned_only_through_the_pages(
        self, all_logs: pytest.LogCaptureFixture
    ) -> None:
        pages = load_pdf(pdf_support.pdf_with_pages([MARKER]), LIMITS)

        assert pages[0].text == MARKER
        assert all_logs.records == []

    def test_a_corrupt_pdf_does_not_echo_its_content(
        self, all_logs: pytest.LogCaptureFixture
    ) -> None:
        pdf = pdf_support.truncated(pdf_support.pdf_with_metadata(MARKER, MARKER), 0.6)

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(pdf, LIMITS)

        assert_clean(caught.value, all_logs)

    def test_an_encrypted_pdf_does_not_echo_its_content(
        self, all_logs: pytest.LogCaptureFixture
    ) -> None:
        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(pdf_support.encrypted_pdf([MARKER], user_password=MARKER), LIMITS)

        assert_clean(caught.value, all_logs)
        assert caught.value.code is DocumentErrorCode.ENCRYPTED_PDF

    def test_the_child_writes_nothing_to_the_standard_streams_of_the_parent(
        self, capfd: pytest.CaptureFixture[str]
    ) -> None:
        pdf = pdf_support.truncated(pdf_support.pdf_with_pages([MARKER] * 5))

        with pytest.raises(DocumentLoadError):
            load_pdf(pdf, LIMITS)
        load_pdf(pdf_support.pdf_with_pages([MARKER]), LIMITS)

        captured = capfd.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_the_failure_after_a_limit_does_not_echo_the_content(
        self, all_logs: pytest.LogCaptureFixture
    ) -> None:
        pdf = pdf_support.pdf_with_pages([MARKER * 100])

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(pdf, PdfLimits(300, 50, 768, 20, 30, 8 * 1024 * 1024))

        assert_clean(caught.value, all_logs)
        assert caught.value.code is DocumentErrorCode.TEXT_TOO_LARGE


@linux_only
class TestFakeChild:
    def test_the_standard_error_of_the_child_is_discarded(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        all_logs: pytest.LogCaptureFixture,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        body = (
            f"sys.stderr.write({MARKER!r} * 50)\nsys.stderr.flush()\n"
            "print(json.dumps({'error': 'CORRUPT_FILE'}))\nsys.exit(1)\n"
        )
        install(monkeypatch, tmp_path, body)

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(b"x", LIMITS)

        assert_clean(caught.value, all_logs)
        assert MARKER not in capfd.readouterr().err

    def test_a_marker_in_a_malformed_line_is_not_echoed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        all_logs: pytest.LogCaptureFixture,
    ) -> None:
        install(monkeypatch, tmp_path, f"print({MARKER!r} + ' {{broken json')\n")

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(b"x", LIMITS)

        assert_clean(caught.value, all_logs)
        assert caught.value.code is DocumentErrorCode.PROCESSING_FAILED
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None or caught.value.__suppress_context__

    def test_a_marker_in_a_wrongly_typed_field_is_not_echoed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        all_logs: pytest.LogCaptureFixture,
    ) -> None:
        line = f'{{"page": "{MARKER}", "text": "{MARKER}"}}'
        install(monkeypatch, tmp_path, f"print({line!r})\nprint({END!r})\n")

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(b"x", LIMITS)

        assert_clean(caught.value, all_logs)

    def test_a_marker_in_the_unknown_error_code_is_not_echoed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        all_logs: pytest.LogCaptureFixture,
    ) -> None:
        install(
            monkeypatch,
            tmp_path,
            f"print(json.dumps({{'error': {MARKER!r}}}))\nsys.exit(1)\n",
        )

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(b"x", LIMITS)

        assert_clean(caught.value, all_logs)
        assert caught.value.code is DocumentErrorCode.PROCESSING_FAILED

    def test_the_payload_is_not_kept_in_the_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, all_logs: pytest.LogCaptureFixture
    ) -> None:
        install(monkeypatch, tmp_path, "sys.exit(2)\n")

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(MARKER.encode(), LIMITS)

        assert_clean(caught.value, all_logs)

    def test_every_error_message_is_the_fixed_text_of_its_code(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from app.models.ingestion import DOCUMENT_ERROR_MESSAGES

        install(monkeypatch, tmp_path, "sys.exit(2)\n")

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(b"x", LIMITS)

        assert str(caught.value) == DOCUMENT_ERROR_MESSAGES[caught.value.code]
