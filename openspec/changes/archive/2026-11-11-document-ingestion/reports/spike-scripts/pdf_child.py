"""Prototype of the isolated PDF child (design D9). Reads the PDF from stdin, writes JSON lines to stdout.

Only fixed codes leave the child: never parser text, never exception messages. Limits are applied by the
child itself before it touches the input (Linux only).
"""
import io
import json
import os
import resource
import sys

MAX_INPUT = int(os.environ.get("CHILD_MAX_INPUT", 10 * 1024 * 1024 + 4096))
MAX_PAGES = int(os.environ.get("CHILD_MAX_PAGES", 300))
MAX_CHARS = int(os.environ.get("CHILD_MAX_CHARS", 2_000_000))
AS_MB = int(os.environ.get("CHILD_AS_MB", 768))
CPU_S = int(os.environ.get("CHILD_CPU_S", 20))


def limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (AS_MB * 1024 * 1024, AS_MB * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_S, CPU_S + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    limits()
    data = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        emit({"error": "RESOURCE_LIMIT_EXCEEDED"})
        return 3
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            emit({"error": "ENCRYPTED_PDF"})
            return 3
        pages = len(reader.pages)
        if pages > MAX_PAGES:
            emit({"error": "TOO_MANY_PAGES"})
            return 3
        total = 0
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            total += len(text)
            if total > MAX_CHARS:
                emit({"error": "TEXT_TOO_LARGE"})
                return 3
            emit({"page": number, "text": text})
        emit({"done": True, "pages": pages, "chars": total})
        return 0
    except MemoryError:
        emit({"error": "RESOURCE_LIMIT_EXCEEDED"})
        return 3
    except Exception:  # noqa: BLE001 - the type and text are deliberately not reported
        emit({"error": "CORRUPT_FILE"})
        return 3


if __name__ == "__main__":
    sys.exit(main())
