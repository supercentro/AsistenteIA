"""The parent side of the PDF child: protocol, process handling and minimal environment (6.2)."""

import dataclasses
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from app.core.config import load_settings
from app.models.ingestion import DocumentErrorCode
from app.rag import loaders
from app.rag.chunker import Page
from app.rag.loaders import DocumentLoadError, PdfLimits, UnsupportedPlatformError, load_pdf
from tests.child_support import END, PAGE_ONE, emit, install
from tests.constants import TEST_JWT_SECRET

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


def failure(limit: PdfLimits = LIMITS) -> DocumentLoadError:
    with pytest.raises(DocumentLoadError) as caught:
        load_pdf(b"%PDF-1.4 anything", limit)
    return caught.value


def test_pdfs_are_not_parsed_outside_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[object] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))

    with pytest.raises(UnsupportedPlatformError):
        load_pdf(b"%PDF-1.4", LIMITS)

    assert started == []  # no process, and no in-process fallback


@linux_only
class TestProtocol:
    def test_pages_are_returned_in_order_with_their_numbers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(
            monkeypatch,
            tmp_path,
            emit('{"page": 1, "text": "uno"}', '{"page": 3, "text": "tres"}', END),
        )

        assert load_pdf(b"x", LIMITS) == [Page(1, "uno"), Page(3, "tres")]

    def test_text_is_normalised_in_the_parent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        line = '{"page": 1, "text": "a\\u0000b\\u202ec\\u00a0d\\u2028e"}'
        install(monkeypatch, tmp_path, emit(line, END))

        assert load_pdf(b"x", LIMITS) == [Page(1, "abc d\ne")]

    def test_blank_looking_pages_produce_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        blank = '{"page": 1, "text": "\\u00a0\\u0085\\u00a0"}'
        install(monkeypatch, tmp_path, emit(blank, '{"page": 2, "text": "real"}', END))

        assert load_pdf(b"x", LIMITS) == [Page(2, "real")]

    def test_a_document_that_is_blank_after_normalisation_has_no_extractable_text(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        blank = '{"page": 1, "text": "\\u00a0\\u0085"}'
        install(monkeypatch, tmp_path, emit(blank, END))

        assert failure().code is DocumentErrorCode.NO_EXTRACTABLE_TEXT

    def test_no_pages_at_all_have_no_extractable_text(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, emit(END))

        assert failure().code is DocumentErrorCode.NO_EXTRACTABLE_TEXT

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("ENCRYPTED_PDF", DocumentErrorCode.ENCRYPTED_PDF),
            ("CORRUPT_FILE", DocumentErrorCode.CORRUPT_FILE),
            ("TOO_MANY_PAGES", DocumentErrorCode.TOO_MANY_PAGES),
            ("TEXT_TOO_LARGE", DocumentErrorCode.TEXT_TOO_LARGE),
            ("RESOURCE_LIMIT_EXCEEDED", DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED),
        ],
    )
    def test_the_codes_the_child_may_report_are_mapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        code: str,
        expected: DocumentErrorCode,
    ) -> None:
        install(monkeypatch, tmp_path, emit(f'{{"error": "{code}"}}') + "sys.exit(1)\n")

        assert failure().code is expected

    @pytest.mark.parametrize(
        "code",
        ["EMBEDDING_FAILED", "JOB_EXPIRED", "NOT_A_CODE", "", "corrupt_file"],
    )
    def test_any_other_code_reported_by_the_child_is_a_processing_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: str
    ) -> None:
        install(monkeypatch, tmp_path, emit(f'{{"error": "{code}"}}') + "sys.exit(1)\n")

        assert failure().code is DocumentErrorCode.PROCESSING_FAILED

    @pytest.mark.parametrize(
        "lines",
        [
            pytest.param([PAGE_ONE], id="no-end-marker"),
            pytest.param(["not json", END], id="not-json"),
            pytest.param(["[1, 2]", END], id="not-an-object"),
            pytest.param(['{"page": "1", "text": "a"}', END], id="page-is-a-string"),
            pytest.param(['{"page": 0, "text": "a"}', END], id="page-zero"),
            pytest.param(['{"page": true, "text": "a"}', END], id="page-is-a-boolean"),
            pytest.param(['{"page": 1, "text": 5}', END], id="text-is-a-number"),
            pytest.param(['{"page": 1}', END], id="text-missing"),
            pytest.param(['{"text": "a"}', END], id="page-missing"),
            pytest.param([PAGE_ONE, PAGE_ONE, END], id="page-repeated"),
            pytest.param(['{"page": 2, "text": "a"}', PAGE_ONE, END], id="pages-out-of-order"),
            pytest.param([PAGE_ONE, END, PAGE_ONE], id="data-after-the-end"),
            pytest.param([PAGE_ONE, '{"end": false}'], id="end-is-false"),
            pytest.param([PAGE_ONE, '{"end": true, "extra": 1}'], id="end-with-extra-keys"),
            pytest.param(['{"page": 1, "text": "a", "extra": 1}', END], id="page-with-extra-keys"),
        ],
    )
    def test_a_malformed_stream_is_a_processing_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lines: list[str]
    ) -> None:
        install(monkeypatch, tmp_path, emit(*lines))

        assert failure().code is DocumentErrorCode.PROCESSING_FAILED

    def test_a_child_that_exits_with_an_error_status_after_a_valid_stream_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END) + "sys.exit(3)\n")

        assert failure().code is DocumentErrorCode.PROCESSING_FAILED

    def test_more_pages_than_allowed_from_a_misbehaving_child_are_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        lines = [f'{{"page": {n}, "text": "t"}}' for n in (1, 2, 3)]
        install(monkeypatch, tmp_path, emit(*lines, END))

        error = failure(dataclasses.replace(LIMITS, max_pages=2))

        assert error.code is DocumentErrorCode.TOO_MANY_PAGES

    def test_an_error_line_wins_over_pages_already_sent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(
            monkeypatch, tmp_path, emit(PAGE_ONE, '{"error": "CORRUPT_FILE"}') + "sys.exit(1)\n"
        )

        assert failure().code is DocumentErrorCode.CORRUPT_FILE

    def test_extra_data_in_an_error_line_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        line = '{"error": "CORRUPT_FILE", "detail": "SECRET-DETAIL", "trace": "boom"}'
        install(monkeypatch, tmp_path, emit(line) + "sys.exit(1)\n")

        error = failure()

        assert error.code is DocumentErrorCode.CORRUPT_FILE
        assert "SECRET-DETAIL" not in repr(error) + str(error)


@linux_only
class TestExitStatus:
    @pytest.mark.parametrize(
        ("kill_with", "expected"),
        [
            ("SIGXCPU", DocumentErrorCode.PROCESSING_TIMEOUT),
            ("SIGKILL", DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED),
            ("SIGSEGV", DocumentErrorCode.PROCESSING_FAILED),
            ("SIGABRT", DocumentErrorCode.PROCESSING_FAILED),
        ],
    )
    def test_a_child_ended_by_a_signal_is_mapped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        kill_with: str,
        expected: DocumentErrorCode,
    ) -> None:
        number = int(signal.Signals[kill_with])
        install(
            monkeypatch,
            tmp_path,
            f"try:\n    signal.signal({number}, signal.SIG_DFL)\nexcept OSError:\n    pass\n"
            f"os.kill(os.getpid(), {number})\ntime.sleep(5)\n",
        )

        assert failure().code is expected

    def test_a_child_that_prints_nothing_and_exits_cleanly_fails(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, "pass\n")

        assert failure().code is DocumentErrorCode.PROCESSING_FAILED


@linux_only
class TestWallClockAndOutputCap:
    def test_a_child_that_hangs_is_killed_at_the_deadline(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, "time.sleep(60)\n")
        started = time.monotonic()

        error = failure(dataclasses.replace(LIMITS, timeout_seconds=1))

        assert error.code is DocumentErrorCode.PROCESSING_TIMEOUT
        assert 0.9 < time.monotonic() - started < 8

    def test_a_child_that_dribbles_output_is_still_stopped_by_the_deadline(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body = (
            "while True:\n    sys.stdout.write(' ')\n    sys.stdout.flush()\n    time.sleep(0.05)\n"
        )
        install(monkeypatch, tmp_path, body)

        error = failure(dataclasses.replace(LIMITS, timeout_seconds=1))

        assert error.code is DocumentErrorCode.PROCESSING_TIMEOUT

    def test_a_child_that_floods_stdout_is_killed_at_the_cap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body = "chunk = b'x' * 65536\nwhile True:\n    sys.stdout.buffer.write(chunk)\n"
        install(monkeypatch, tmp_path, body)
        started = time.monotonic()

        error = failure(dataclasses.replace(LIMITS, max_output_bytes=1_000_000))

        assert error.code is DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED
        assert time.monotonic() - started < 10

    def test_a_single_line_without_a_newline_cannot_exceed_the_cap(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body = "sys.stdout.write('y' * 5_000_000)\nsys.stdout.flush()\ntime.sleep(5)\n"
        install(monkeypatch, tmp_path, body)

        error = failure(dataclasses.replace(LIMITS, max_output_bytes=100_000))

        assert error.code is DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED

    def test_output_exactly_at_the_cap_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stream = f"{PAGE_ONE}\n{END}\n"
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END))

        pages = load_pdf(b"x", dataclasses.replace(LIMITS, max_output_bytes=len(stream)))

        assert pages == [Page(1, "hello")]

    def test_one_byte_over_the_cap_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        stream = f"{PAGE_ONE}\n{END}\n"
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END))

        error = failure(dataclasses.replace(LIMITS, max_output_bytes=len(stream) - 1))

        assert error.code is DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED

    def test_a_child_that_never_reads_a_large_input_does_not_block_the_parent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, "sys.exit(0)\n")
        started = time.monotonic()

        with pytest.raises(DocumentLoadError):
            load_pdf(b"x" * 20_000_000, LIMITS)

        assert time.monotonic() - started < 10

    def test_a_child_that_reads_a_large_input_receives_all_of_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        body = (
            "size = len(sys.stdin.buffer.read())\n"
            "print(json.dumps({'page': 1, 'text': str(size)}))\n"
            "print(json.dumps({'end': True}))\n"
        )
        install(monkeypatch, tmp_path, body)

        assert load_pdf(b"x" * 5_000_000, LIMITS) == [Page(1, "5000000")]


@linux_only
class TestProcessHandling:
    def _spy(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        real = subprocess.Popen

        def spy(*args: Any, **kwargs: Any) -> Any:
            seen["args"] = args[0] if args else kwargs["args"]
            seen["kwargs"] = kwargs
            seen["process"] = real(*args, **kwargs)
            return seen["process"]

        monkeypatch.setattr(subprocess, "Popen", spy)
        return seen

    def test_the_child_is_started_isolated_with_discarded_stderr(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END))
        seen = self._spy(monkeypatch)

        load_pdf(b"x", LIMITS)

        command = seen["args"]
        kwargs = seen["kwargs"]
        assert command[0] == sys.executable
        assert command[1] == "-I"
        assert kwargs["stdin"] == subprocess.PIPE
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["close_fds"] is True
        assert kwargs["start_new_session"] is True
        assert kwargs.get("shell", False) is False

    def test_the_limits_are_passed_to_the_child_to_apply_by_itself(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END))
        seen = self._spy(monkeypatch)
        custom = PdfLimits(
            max_pages=7,
            max_chars=1234,
            memory_mb=321,
            cpu_seconds=9,
            timeout_seconds=11,
            max_output_bytes=4096,
        )

        load_pdf(b"x", custom)

        arguments = " ".join(seen["args"][3:])
        for expected in ("7", "1234", "321", "9"):
            assert expected in arguments.split()

    def test_the_environment_is_minimal_and_holds_no_secret(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("JWT_SECRET_KEY", "SECRET-IN-THE-PARENT")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:SECRET@host/db")
        body = (
            "print(json.dumps({'page': 1, 'text': json.dumps(sorted(os.environ))}))\n"
            "print(json.dumps({'end': True}))\n"
        )
        install(monkeypatch, tmp_path, body)

        pages = load_pdf(b"x", LIMITS)

        names = json.loads(pages[0].text)
        assert set(names) <= {"LC_ALL", "LANG", "PATH"}
        assert "SECRET" not in pages[0].text

    def test_the_environment_function_ignores_the_parent_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SOME_SECRET", "x")

        assert "SOME_SECRET" not in loaders.pdf_child_environment()

    @pytest.mark.parametrize(
        "body",
        ["time.sleep(60)\n", "while True:\n    sys.stdout.buffer.write(b'x' * 65536)\n"],
        ids=["timeout", "flood"],
    )
    def test_a_breach_leaves_no_running_process(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str
    ) -> None:
        install(monkeypatch, tmp_path, body)
        seen = self._spy(monkeypatch)

        with pytest.raises(DocumentLoadError):
            load_pdf(
                b"x",
                dataclasses.replace(LIMITS, timeout_seconds=1, max_output_bytes=500_000),
            )

        process = seen["process"]
        assert process.poll() is not None  # already reaped: not running, not a zombie
        with pytest.raises(ProcessLookupError):
            os.kill(process.pid, 0)

    def test_pipes_are_closed_after_each_call(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END))
        seen = self._spy(monkeypatch)

        load_pdf(b"x", LIMITS)

        process = seen["process"]
        assert process.stdout.closed
        assert process.stdin.closed

    def test_many_calls_do_not_leak_descriptors(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        install(monkeypatch, tmp_path, emit(PAGE_ONE, END))
        before = len(os.listdir("/proc/self/fd"))

        for _ in range(15):
            load_pdf(b"x", LIMITS)

        assert len(os.listdir("/proc/self/fd")) <= before + 1


class TestPdfLimits:
    @pytest.fixture(autouse=True)
    def base_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in (
            "MAX_PDF_PAGES",
            "MAX_EXTRACTED_CHARS",
            "PDF_CHILD_MAX_MEMORY_MB",
            "PDF_CHILD_CPU_SECONDS",
            "PDF_CHILD_TIMEOUT_SECONDS",
            "PDF_CHILD_MAX_OUTPUT_MB",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("JWT_SECRET", TEST_JWT_SECRET)
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")

    def test_the_limits_come_from_the_settings(self) -> None:
        derived = PdfLimits.from_settings(load_settings(env_file=None))

        assert derived == PdfLimits(
            max_pages=300,
            max_chars=2_000_000,
            memory_mb=768,
            cpu_seconds=20,
            timeout_seconds=30,
            max_output_bytes=8 * 1024 * 1024,
        )

    def test_custom_settings_are_converted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAX_PDF_PAGES", "12")
        monkeypatch.setenv("MAX_EXTRACTED_CHARS", "3456")
        monkeypatch.setenv("PDF_CHILD_MAX_MEMORY_MB", "200")
        monkeypatch.setenv("PDF_CHILD_CPU_SECONDS", "5")
        monkeypatch.setenv("PDF_CHILD_TIMEOUT_SECONDS", "8")
        monkeypatch.setenv("PDF_CHILD_MAX_OUTPUT_MB", "2")

        derived = PdfLimits.from_settings(load_settings(env_file=None))

        assert (derived.max_pages, derived.max_chars, derived.memory_mb) == (12, 3456, 200)
        assert (derived.cpu_seconds, derived.timeout_seconds) == (5, 8)
        assert derived.max_output_bytes == 2 * 1024 * 1024
