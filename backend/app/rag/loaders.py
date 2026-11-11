"""Document loaders (change 6, tasks 6.1 and 6.2): strict UTF-8 text and the isolated PDF child.

Both loaders turn the uploaded bytes into normalised `Page` objects or raise
`DocumentLoadError` with one code of the failure catalogue. The error carries the fixed message of
its code and never any content, library text or exception chain; nothing is logged here.

- `load_text` / `load_markdown`: strict UTF-8 (a leading BOM is accepted and removed, NUL is
  rejected), Markdown is data and is never interpreted. One page without a number.
- `load_pdf`: runs `pdf_child.py` in a separate, short-lived process (design D9) with a minimal
  environment, the bytes on a pipe, a wall-clock deadline, a cap on the bytes read and the limits
  applied by the child itself. The child is killed on any breach. PDFs are parsed on Linux only
  (the limits rely on `rlimit`); there is no in-process fallback.
"""

import json
import os
import select
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.rag.chunker import Page
from app.rag.normalizer import normalize_text

if TYPE_CHECKING:
    from app.core.config import WorkerSettings

DEFAULT_MAX_EXTRACTED_CHARS = 2_000_000
_BYTES_PER_MB = 1024 * 1024
_READ_SIZE = 65_536
_POLL_SECONDS = 0.25
_CHILD_SCRIPT = Path(__file__).with_name("pdf_child.py")
# Codes the child may report; anything else it says is treated as a processing failure.
_CHILD_CODES = frozenset(
    {
        DocumentErrorCode.ENCRYPTED_PDF,
        DocumentErrorCode.CORRUPT_FILE,
        DocumentErrorCode.TOO_MANY_PAGES,
        DocumentErrorCode.TEXT_TOO_LARGE,
        DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED,
    }
)


class DocumentLoadError(Exception):
    """The document cannot be loaded. Carries a catalogue code and its fixed message only."""

    def __init__(self, code: DocumentErrorCode) -> None:
        super().__init__(DOCUMENT_ERROR_MESSAGES[code])
        self.code = code


class UnsupportedPlatformError(RuntimeError):
    """PDFs are parsed only where the child's resource limits exist (Linux)."""


@dataclass(frozen=True)
class PdfLimits:
    """Every limit of one PDF parse (design D9)."""

    max_pages: int
    max_chars: int
    memory_mb: int
    cpu_seconds: int
    timeout_seconds: int
    max_output_bytes: int

    @classmethod
    def from_settings(cls, settings: "WorkerSettings") -> "PdfLimits":
        return cls(
            max_pages=settings.max_pdf_pages,
            max_chars=settings.max_extracted_chars,
            memory_mb=settings.pdf_child_max_memory_mb,
            cpu_seconds=settings.pdf_child_cpu_seconds,
            timeout_seconds=settings.pdf_child_timeout_seconds,
            max_output_bytes=settings.pdf_child_max_output_mb * _BYTES_PER_MB,
        )


def _decode(payload: bytes, max_chars: int) -> str:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentLoadError(DocumentErrorCode.CORRUPT_FILE) from None
    if "\x00" in text:
        raise DocumentLoadError(DocumentErrorCode.CORRUPT_FILE)
    if len(text) > max_chars:
        raise DocumentLoadError(DocumentErrorCode.TEXT_TOO_LARGE)
    return text


def load_text(payload: bytes, *, max_chars: int = DEFAULT_MAX_EXTRACTED_CHARS) -> list[Page]:
    """Decode a `.txt` file as strict UTF-8 and normalise it (one page without a number)."""
    cleaned = normalize_text(_decode(payload, max_chars))
    if not cleaned:
        raise DocumentLoadError(DocumentErrorCode.NO_EXTRACTABLE_TEXT)
    return [Page(number=None, text=cleaned)]


def load_markdown(payload: bytes, *, max_chars: int = DEFAULT_MAX_EXTRACTED_CHARS) -> list[Page]:
    """Load a `.md` file: the same as text, because Markdown is stored as inert data."""
    return load_text(payload, max_chars=max_chars)


def pdf_child_environment() -> dict[str, str]:
    """The only environment the child gets: nothing from the parent, no secret, no setting."""
    return {"LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin"}


def _feed(stdin: IO[bytes], payload: bytes) -> None:
    with suppress(OSError, ValueError):
        stdin.write(payload)
    with suppress(OSError, ValueError):
        stdin.close()


def _collect(process: "subprocess.Popen[bytes]", deadline: float, max_bytes: int) -> bytes:
    """Read the child's standard output within the deadline and the byte cap."""
    assert process.stdout is not None  # noqa: S101 - created with stdout=PIPE
    descriptor = process.stdout.fileno()
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DocumentLoadError(DocumentErrorCode.PROCESSING_TIMEOUT)
        ready, _, _ = select.select([descriptor], [], [], min(remaining, _POLL_SECONDS))
        if not ready:
            continue
        data = os.read(descriptor, _READ_SIZE)
        if not data:
            break
        total += len(data)
        if total > max_bytes:
            raise DocumentLoadError(DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED)
        chunks.append(data)
    try:
        process.wait(timeout=max(deadline - time.monotonic(), 0.05))
    except subprocess.TimeoutExpired:
        raise DocumentLoadError(DocumentErrorCode.PROCESSING_TIMEOUT) from None
    return b"".join(chunks)


def _stop(process: "subprocess.Popen[bytes]", feeder: threading.Thread) -> None:
    """Kill the child and its process group if still running, then reap it and close the pipes."""
    if process.poll() is None:
        with suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
        with suppress(ProcessLookupError):
            process.kill()
    process.wait()
    if process.stdout is not None:
        process.stdout.close()
    feeder.join(timeout=5)
    if process.stdin is not None:
        with suppress(OSError, ValueError):
            process.stdin.close()


def _child_code(reported: object) -> DocumentErrorCode:
    """The code the child reported, or a processing failure if it is not one it may use."""
    if not isinstance(reported, str):
        return DocumentErrorCode.PROCESSING_FAILED
    try:
        code = DocumentErrorCode(reported)
    except ValueError:
        return DocumentErrorCode.PROCESSING_FAILED
    return code if code in _CHILD_CODES else DocumentErrorCode.PROCESSING_FAILED


def _fail(code: DocumentErrorCode) -> DocumentLoadError:
    return DocumentLoadError(code)


def _exit_error(returncode: int) -> DocumentLoadError | None:
    if returncode < 0:
        if -returncode == signal.SIGXCPU:
            return _fail(DocumentErrorCode.PROCESSING_TIMEOUT)
        if -returncode == signal.SIGKILL:
            return _fail(DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED)
    return None


def _parse(output: bytes, returncode: int, max_pages: int) -> list[Page]:
    """Validate the child's protocol strictly and return the normalised pages."""
    failed = DocumentErrorCode.PROCESSING_FAILED
    pages: list[Page] = []
    last_number = 0
    ended = False
    for raw in output.split(b"\n"):
        if not raw:
            continue
        try:
            record: Any = json.loads(raw)
        except (ValueError, RecursionError):
            raise _fail(failed) from None
        if ended or not isinstance(record, dict):
            raise _fail(failed)
        if "error" in record:
            code = record["error"]
            raise _fail(_child_code(code))
        keys = set(record)
        if keys == {"end"}:
            if record["end"] is not True:
                raise _fail(failed)
            ended = True
            continue
        number, text = record.get("page"), record.get("text")
        if keys != {"page", "text"} or not isinstance(text, str):
            raise _fail(failed)
        if type(number) is not int or number <= last_number:
            raise _fail(failed)
        last_number = number
        cleaned = normalize_text(text)
        if cleaned:
            pages.append(Page(number=number, text=cleaned))
        if number > max_pages:
            raise _fail(DocumentErrorCode.TOO_MANY_PAGES)
    if returncode != 0 or not ended:
        raise _fail(failed)
    return pages


def load_pdf(payload: bytes, limits: PdfLimits) -> list[Page]:
    """Extract the text of a PDF in the isolated child; one `Page` per page with visible text.

    Raises `UnsupportedPlatformError` outside Linux and `DocumentLoadError` for every rejection
    (`ENCRYPTED_PDF`, `CORRUPT_FILE`, `TOO_MANY_PAGES`, `TEXT_TOO_LARGE`, `NO_EXTRACTABLE_TEXT`,
    `PROCESSING_TIMEOUT`, `RESOURCE_LIMIT_EXCEEDED`, `PROCESSING_FAILED`).
    """
    if sys.platform != "linux":
        raise UnsupportedPlatformError("PDF files are parsed only on Linux")
    deadline = time.monotonic() + limits.timeout_seconds
    command = [
        sys.executable,
        "-I",
        str(_CHILD_SCRIPT),
        str(limits.memory_mb),
        str(limits.cpu_seconds),
        str(limits.max_pages),
        str(limits.max_chars),
    ]
    process = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell, no user input
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=pdf_child_environment(),
        cwd="/",
        close_fds=True,
        start_new_session=True,
    )
    assert process.stdin is not None  # noqa: S101 - created with stdin=PIPE
    feeder = threading.Thread(
        target=_feed, args=(process.stdin, payload), name="pdf-input-feeder", daemon=True
    )
    feeder.start()
    try:
        output = _collect(process, deadline, limits.max_output_bytes)
        killed = _exit_error(process.returncode)
        if killed is not None:
            raise killed
        pages = _parse(output, process.returncode, limits.max_pages)
    finally:
        _stop(process, feeder)
    if not pages:
        raise DocumentLoadError(DocumentErrorCode.NO_EXTRACTABLE_TEXT)
    return pages
