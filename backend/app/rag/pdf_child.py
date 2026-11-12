"""Isolated PDF text extraction (change 6, task 6.2), design D9.

This file is run as its own interpreter, `python -I pdf_child.py MEMORY_MB CPU_SECONDS MAX_PAGES
MAX_CHARS`, by `app.rag.loaders` with a minimal environment, the PDF bytes on standard input,
standard output read through a size cap and standard error discarded. It is self-contained on
purpose (standard library and `pypdf` only): it never imports the application, its settings or
the database layer, so a hostile file reaches as little code as possible.

Before it reads a single byte the child applies its own limits (Linux `rlimit`): address space, CPU
time (a soft limit that ends the process with `SIGXCPU`), no file writes, few open files and no core
dumps. The parent adds the wall-clock timeout and the output cap and kills the child on a breach.

Output protocol, one JSON object per line on standard output:
- `{"page": N, "text": "..."}` for every page, in order, `N` starting at 1;
- `{"end": true}` after the last page (a stream without it is incomplete);
- `{"error": "CODE"}` followed by exit status 1 when the file is rejected.

Nothing else is ever written: no library message, path, metadata or exception text.
"""

import io
import json
import sys
from typing import Any

# Open files the child may hold (standard streams plus the interpreter's own needs).
NOFILE_LIMIT = 32
# Seconds between the soft CPU limit (SIGXCPU ends the process) and the hard one (SIGKILL).
_CPU_GRACE_SECONDS = 2

ENCRYPTED_PDF = "ENCRYPTED_PDF"
CORRUPT_FILE = "CORRUPT_FILE"
TOO_MANY_PAGES = "TOO_MANY_PAGES"
TEXT_TOO_LARGE = "TEXT_TOO_LARGE"
RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"

_SURROGATES = {code: None for code in range(0xD800, 0xE000)}


class _Rejected(Exception):  # noqa: N818 - internal control flow, not an error type
    """The file is refused with one of the codes above."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    """Apply every resource limit to this process (Linux only; imported lazily)."""
    import resource

    memory = memory_mb << 20
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + _CPU_GRACE_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (NOFILE_LIMIT, NOFILE_LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _write(record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    sys.stdout.buffer.write(line.encode("utf-8"))


def _extract(data: bytes, max_pages: int, max_chars: int) -> None:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        raise _Rejected(ENCRYPTED_PDF)
    pages = reader.pages
    if len(pages) > max_pages:
        raise _Rejected(TOO_MANY_PAGES)
    total = 0
    for number, page in enumerate(pages, start=1):
        text = (page.extract_text() or "").translate(_SURROGATES)
        total += len(text)
        if total > max_chars:
            raise _Rejected(TEXT_TOO_LARGE)
        _write({"page": number, "text": text})
    _write({"end": True})


def _report(code: str) -> int:
    try:
        _write({"error": code})
        sys.stdout.buffer.flush()
    except Exception:  # noqa: BLE001, S110 - the parent maps a missing report to a failure
        pass
    return 1


def main(argv: list[str]) -> int:
    memory_mb, cpu_seconds, max_pages, max_chars = (int(value) for value in argv[1:5])
    apply_limits(memory_mb, cpu_seconds)
    data = sys.stdin.buffer.read()
    try:
        _extract(data, max_pages, max_chars)
        sys.stdout.buffer.flush()
    except _Rejected as rejected:
        return _report(rejected.code)
    except MemoryError:
        del data
        return _report(RESOURCE_LIMIT_EXCEEDED)
    except Exception:  # noqa: BLE001 - any parser failure means the file is not readable
        return _report(CORRUPT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
