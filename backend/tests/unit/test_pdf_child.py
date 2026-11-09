"""The isolated PDF child with generated fixtures (change 6, task 6.2).

The real child process runs on Linux only (it relies on `rlimit`). On other systems these tests are
skipped with an explicit reason and the CI job (Linux) and the worker image run them.
"""

import dataclasses
import importlib.util
import json
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from app.models.ingestion import DocumentErrorCode
from app.rag import loaders
from app.rag.chunker import Page
from app.rag.loaders import DocumentLoadError, PdfLimits, load_pdf
from tests import pdf_support

pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="the PDF child applies Linux resource limits; run in the Linux container or CI",
)

LIMITS = PdfLimits(
    max_pages=300,
    max_chars=2_000_000,
    memory_mb=768,
    cpu_seconds=20,
    timeout_seconds=30,
    max_output_bytes=8 * 1024 * 1024,
)


def limits(**changes: int) -> PdfLimits:
    return dataclasses.replace(LIMITS, **changes)


def failure(payload: bytes, limit: PdfLimits = LIMITS) -> DocumentLoadError:
    with pytest.raises(DocumentLoadError) as caught:
        load_pdf(payload, limit)
    return caught.value


@pytest.fixture(scope="module")
def heavy_page() -> bytes:
    """A 5 MB file with one page of 600,000 text lines: minutes of work for the extractor."""
    return pdf_support.pdf_many_text_lines(600_000)


class TestTextExtraction:
    def test_each_page_keeps_its_number(self) -> None:
        pdf = pdf_support.pdf_with_pages(["Primera pagina", "Segunda pagina", "Tercera pagina"])

        assert load_pdf(pdf, LIMITS) == [
            Page(number=1, text="Primera pagina"),
            Page(number=2, text="Segunda pagina"),
            Page(number=3, text="Tercera pagina"),
        ]

    def test_pages_without_text_are_skipped_and_numbers_are_kept(self) -> None:
        pdf = pdf_support.pdf_with_pages(["uno", "", "tres"])

        assert load_pdf(pdf, LIMITS) == [Page(1, "uno"), Page(3, "tres")]

    def test_a_scan_without_text_has_no_extractable_text(self) -> None:
        assert failure(pdf_support.pdf_without_text(3)).code is DocumentErrorCode.NO_EXTRACTABLE_TEXT

    def test_a_pdf_without_pages_has_no_extractable_text(self) -> None:
        assert failure(pdf_support.pdf_from_streams([])).code is DocumentErrorCode.NO_EXTRACTABLE_TEXT

    def test_each_call_uses_a_fresh_process(self) -> None:
        pdf = pdf_support.pdf_with_pages(["hola"])

        assert load_pdf(pdf, LIMITS) == load_pdf(pdf, LIMITS)


class TestInvalidFiles:
    def test_a_truncated_pdf_is_corrupt(self) -> None:
        pdf = pdf_support.truncated(pdf_support.pdf_with_pages(["a"] * 5))

        assert failure(pdf).code is DocumentErrorCode.CORRUPT_FILE

    @pytest.mark.parametrize("payload", [b"", b"not a pdf at all", b"%PDF-1.4\n", b"\x00" * 100])
    def test_bytes_that_are_not_a_pdf_are_corrupt(self, payload: bytes) -> None:
        assert failure(payload).code is DocumentErrorCode.CORRUPT_FILE

    def test_an_encrypted_pdf_that_opens_without_a_password_still_fails(self) -> None:
        pdf = pdf_support.encrypted_pdf(["secreto"], user_password="")

        assert failure(pdf).code is DocumentErrorCode.ENCRYPTED_PDF

    def test_an_encrypted_pdf_with_a_password_fails(self) -> None:
        pdf = pdf_support.encrypted_pdf(["secreto"], user_password="clave")

        assert failure(pdf).code is DocumentErrorCode.ENCRYPTED_PDF

    def test_an_aes_encrypted_pdf_fails(self) -> None:
        pytest.importorskip("cryptography", reason="AES encryption needs the cryptography package")
        pdf = pdf_support.encrypted_pdf(["secreto"], algorithm="AES-256")

        assert failure(pdf).code is DocumentErrorCode.ENCRYPTED_PDF


class TestPageAndCharacterCaps:
    def test_more_pages_than_the_cap_fail(self) -> None:
        error = failure(pdf_support.pdf_many_pages(5), limits(max_pages=4))

        assert error.code is DocumentErrorCode.TOO_MANY_PAGES

    def test_exactly_the_cap_is_accepted(self) -> None:
        pages = load_pdf(pdf_support.pdf_many_pages(4), limits(max_pages=4))

        assert [page.number for page in pages] == [1, 2, 3, 4]

    def test_the_page_count_is_checked_before_any_text_is_extracted(self) -> None:
        # Two pages: the first one would burn the whole CPU budget if it were extracted.
        pdf = pdf_support.pdf_from_streams([_heavy_stream(), b"BT ET"])
        started = time.monotonic()

        error = failure(pdf, limits(max_pages=1, cpu_seconds=30))

        assert error.code is DocumentErrorCode.TOO_MANY_PAGES
        assert time.monotonic() - started < 10

    def test_text_above_the_character_cap_fails(self) -> None:
        pdf = pdf_support.pdf_with_pages(["a" * 10, "b" * 10])

        assert failure(pdf, limits(max_chars=19)).code is DocumentErrorCode.TEXT_TOO_LARGE

    def test_text_exactly_at_the_character_cap_is_accepted(self) -> None:
        pdf = pdf_support.pdf_with_pages(["a" * 10, "b" * 10])

        assert len(load_pdf(pdf, limits(max_chars=20))) == 2

    def test_the_character_cap_stops_a_page_that_is_huge_on_its_own(self) -> None:
        pdf = pdf_support.pdf_with_pages(["x" * 5000])

        assert failure(pdf, limits(max_chars=1000)).code is DocumentErrorCode.TEXT_TOO_LARGE


class TestResourceLimits:
    def test_output_above_the_cap_is_a_resource_limit(self) -> None:
        pdf = pdf_support.pdf_with_pages(["y" * 3000, "z" * 3000])

        error = failure(pdf, limits(max_output_bytes=2000))

        assert error.code is DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED

    def test_output_within_the_cap_is_accepted(self) -> None:
        pdf = pdf_support.pdf_with_pages(["y" * 300])

        assert load_pdf(pdf, limits(max_output_bytes=4000))[0].text == "y" * 300

    def test_the_cpu_limit_stops_a_small_file_with_a_huge_page(self, heavy_page: bytes) -> None:
        started = time.monotonic()

        error = failure(heavy_page, limits(cpu_seconds=1, timeout_seconds=60))

        assert error.code is DocumentErrorCode.PROCESSING_TIMEOUT
        assert time.monotonic() - started < 20  # far below the wall clock: the CPU limit acted

    def test_the_wall_clock_limit_stops_a_slow_parse(self, heavy_page: bytes) -> None:
        started = time.monotonic()

        error = failure(heavy_page, limits(cpu_seconds=300, timeout_seconds=1))

        assert error.code is DocumentErrorCode.PROCESSING_TIMEOUT
        assert time.monotonic() - started < 10

    def test_the_memory_limit_stops_a_large_allocation(self) -> None:
        pdf = pdf_support.pdf_with_flate_stream(60 << 20)

        error = failure(pdf, limits(memory_mb=100))

        assert error.code is DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED

    def test_the_same_file_is_accepted_when_the_memory_limit_allows_it(self) -> None:
        pdf = pdf_support.pdf_with_flate_stream(1 << 20)

        with pytest.raises(DocumentLoadError) as caught:
            load_pdf(pdf, limits(memory_mb=768))

        # A stream of spaces has no text; what matters is that it is not a resource failure.
        assert caught.value.code is DocumentErrorCode.NO_EXTRACTABLE_TEXT

    def test_an_oversized_decompression_is_a_controlled_failure(self) -> None:
        pdf = pdf_support.pdf_with_flate_stream(300 << 20)
        started = time.monotonic()

        error = failure(pdf)

        assert error.code in {
            DocumentErrorCode.CORRUPT_FILE,
            DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED,
        }
        assert time.monotonic() - started < 25

    def test_the_worker_keeps_working_after_each_breach(self, heavy_page: bytes) -> None:
        failure(heavy_page, limits(cpu_seconds=1))

        assert load_pdf(pdf_support.pdf_with_pages(["sigue"]), LIMITS) == [Page(1, "sigue")]


class TestAdvisoryShapes:
    """Purpose-made files for the advisories of the selected `pypdf` (design D9)."""

    def test_a_pdf_with_an_xfa_form_is_read_as_plain_text(self) -> None:
        assert load_pdf(pdf_support.pdf_with_xfa(), LIMITS) == [Page(1, "form with xfa")]

    def test_malformed_jpeg_data_is_never_decoded(self) -> None:
        assert load_pdf(pdf_support.pdf_with_bad_jpeg(), LIMITS) == [Page(1, "image page")]

    def test_a_cross_reference_stream_with_equal_offsets_ends_in_a_controlled_way(self) -> None:
        started = time.monotonic()

        error = failure(pdf_support.pdf_xref_stream_with_equal_offsets())

        assert error.code in {
            DocumentErrorCode.CORRUPT_FILE,
            DocumentErrorCode.NO_EXTRACTABLE_TEXT,
        }
        assert time.monotonic() - started < 10


def _heavy_stream() -> bytes:
    parts = [b"BT /F1 6 Tf 7 TL 10 780 Td"]
    parts.extend(b"(line) '" for _ in range(600_000))
    parts.append(b"ET")
    return b"\n".join(parts)


APPLY_LIMITS_CODE = textwrap.dedent(
    """
    import importlib.util, json, resource, sys
    spec = importlib.util.spec_from_file_location("pdf_child_under_test", sys.argv[1])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply_limits(int(sys.argv[2]), int(sys.argv[3]))
    out = {}
    for name in ("RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_FSIZE", "RLIMIT_NOFILE", "RLIMIT_CORE"):
        out[name] = list(resource.getrlimit(getattr(resource, name)))
    try:
        with open(sys.argv[4], "wb") as handle:
            handle.write(b"x")
            handle.flush()
        out["write"] = "allowed"
    except OSError:
        out["write"] = "blocked"
    print(json.dumps(out))
    """
)


def _applied_limits(tmp_path: Path, memory_mb: int, cpu_seconds: int) -> dict[str, object]:
    spec = importlib.util.find_spec("app.rag.pdf_child")
    assert spec is not None and spec.origin is not None
    completed = subprocess.run(  # noqa: S603 - fixed arguments, the interpreter of this process
        [
            sys.executable,
            "-I",
            "-c",
            APPLY_LIMITS_CODE,
            spec.origin,
            str(memory_mb),
            str(cpu_seconds),
            str(tmp_path / "must-not-exist"),
        ],
        capture_output=True,
        timeout=30,
        check=True,
    )
    result: dict[str, object] = json.loads(completed.stdout)
    return result


class TestSelfAppliedLimits:
    """The child applies every limit by itself, before it reads or parses anything."""

    def test_address_space_equals_the_memory_limit(self, tmp_path: Path) -> None:
        applied = _applied_limits(tmp_path, 300, 7)

        assert applied["RLIMIT_AS"] == [300 << 20, 300 << 20]

    def test_cpu_time_has_a_soft_limit_that_ends_the_process(self, tmp_path: Path) -> None:
        applied = _applied_limits(tmp_path, 300, 7)
        soft, hard = applied["RLIMIT_CPU"]  # type: ignore[misc]

        assert soft == 7
        assert hard > soft  # the soft limit sends SIGXCPU before the hard limit sends SIGKILL

    def test_the_child_cannot_write_files(self, tmp_path: Path) -> None:
        applied = _applied_limits(tmp_path, 300, 7)

        assert applied["RLIMIT_FSIZE"] == [0, 0]
        assert applied["write"] == "blocked"

    def test_the_number_of_open_files_is_small(self, tmp_path: Path) -> None:
        applied = _applied_limits(tmp_path, 300, 7)

        assert applied["RLIMIT_NOFILE"] == [32, 32]

    def test_core_dumps_are_disabled(self, tmp_path: Path) -> None:
        applied = _applied_limits(tmp_path, 300, 7)

        assert applied["RLIMIT_CORE"] == [0, 0]

    def test_limits_are_applied_before_the_input_is_read(self) -> None:
        # The parent module sets the same order the child follows: limits first, then stdin.
        source = Path(loaders.__file__).with_name("pdf_child.py").read_text(encoding="utf-8")

        assert source.rindex("apply_limits(") < source.index("stdin.buffer.read")
