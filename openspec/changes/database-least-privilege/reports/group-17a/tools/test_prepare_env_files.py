"""Self-test of prepare_env_files.py on synthetic folders (group 17A). Run: python test_prepare_env_files.py

No real file is read: every folder is created in a temporary directory with made-up values.
"""

import contextlib
import io
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_env_files as tool  # noqa: E402

ADMIN = "p@ss:w/ord#1é"  # awkward on purpose: ':' '/' '@' '#' and a non-ASCII letter (a ' #' would be an inline comment for Compose)
FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        FAILURES.append(label)


def make(folder: Path, newline: str = "\n", bom: bool = False, extra_api: str = "", admin: str = ADMIN) -> None:
    encoded = quote(admin, safe="")
    prefix = "﻿" if bom else ""
    (folder / ".env.db").write_bytes((prefix + newline.join(["POSTGRES_USER=asistente", f"POSTGRES_PASSWORD={admin}", "POSTGRES_DB=asistenteia", ""])).encode("utf-8"))
    api = ["APP_ENV=development", "# a comment", f"DATABASE_URL=postgresql+psycopg://asistente:{encoded}@db:5432/asistenteia?sslmode=disable  # trailing", "JWT_SECRET=not-a-real-secret-0123456789abcdef", extra_api, ""]
    worker = ["LOG_LEVEL=INFO", f"DATABASE_URL=postgresql+psycopg://asistente:{encoded}@db:5432/asistenteia", ""]
    (folder / ".env").write_bytes((prefix + newline.join(api)).encode("utf-8"))
    (folder / ".env.worker").write_bytes((prefix + newline.join(worker)).encode("utf-8"))


def run(folder: Path, *args: str) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = tool.main([str(folder), *args])
    return code, buffer.getvalue()


def snapshot(folder: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}


def case_normal(newline: str, bom: bool) -> None:
    label = f"newline={'CRLF' if newline == chr(13) + chr(10) else 'LF'} bom={bom}"
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder, newline, bom)
        before = snapshot(folder)
        code, output = run(folder, "--dry-run")
        check(f"{label}: dry run succeeds and writes nothing", code == 0 and snapshot(folder) == before)
        code, output = run(folder)
        check(f"{label}: forward run succeeds", code == 0)
        check(f"{label}: nothing secret is printed", ADMIN not in output and "postgresql" not in output and "@" not in output)
        api = (folder / ".env").read_bytes().decode("utf-8")
        check(f"{label}: .env names the application role and keeps host, database, query, comment and other lines", "asistente_app:" in api and "@db:5432/asistenteia?sslmode=disable  # trailing" in api and "JWT_SECRET=not-a-real-secret-0123456789abcdef" in api and "# a comment" in api)
        original = before[".env"].decode("utf-8-sig")
        keep = lambda text: [line for line in text.splitlines(keepends=True) if not line.startswith("DATABASE_URL=")]  # noqa: E731
        check(f"{label}: every other line is byte for byte (line endings included)", keep(original) == keep(api))
        check(f"{label}: the worker file names the worker role", "asistente_worker:" in (folder / ".env.worker").read_text(encoding="utf-8"))
        roles = (folder / ".env.roles").read_text(encoding="utf-8")
        check(f"{label}: .env.roles holds the administrator URL and four passwords", roles.count("DB_") == 4 and "ADMIN_DATABASE_URL=" in roles)
        check(f"{label}: the backups are the originals", all((folder / (name + ".pre-17b")).read_bytes() == before[name] for name in (".env", ".env.worker", ".env.db")))
        code, _ = run(folder)
        check(f"{label}: a second run refuses and does not change anything", code == 1)
        # rotate the administrator password, then roll back: the restored files use the CURRENT one
        rotated = "N3w-adm1n-Passw0rd"
        db = (folder / ".env.db").read_bytes().decode("utf-8").replace(ADMIN, rotated)
        (folder / ".env.db").write_bytes(db.encode("utf-8"))
        code, output = run(folder, "--rollback")
        check(f"{label}: rollback succeeds and prints no value", code == 0 and rotated not in output and ADMIN not in output)
        restored = (folder / ".env").read_bytes().decode("utf-8")
        check(f"{label}: rollback restores the administrator with the CURRENT password, not the exposed one", "asistente:" + quote(rotated, safe="") + "@db:5432/asistenteia?sslmode=disable  # trailing" in restored and quote(ADMIN, safe="") not in restored)
        check(f"{label}: rollback renames the three new files", all((folder / (name + ".rolled-back")).exists() and not (folder / name).exists() for name in tool.NEW_FILES))
        code, _ = run(folder, "--rollback")
        check(f"{label}: a second rollback refuses (nothing replaced silently)", code == 1)
        code, output = run(folder)
        check(f"{label}: a new forward run is refused while the .pre-17b copies exist and says to destroy them", code == 1 and "destroy" in output)


def case_refusals() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder)
        (folder / ".env.worker").write_text("DATABASE_URL=postgresql+psycopg://other:pw@db:5432/asistenteia\n", encoding="utf-8")
        before = snapshot(folder)
        code, output = run(folder)
        check("a worker file that is not the administrator is refused and nothing is written", code == 1 and snapshot(folder) == before)
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder, extra_api="DATABASE_URL=postgresql+psycopg://asistente:x@db:5432/asistenteia")
        before = snapshot(folder)
        code, _ = run(folder)
        check("two DATABASE_URL lines are refused", code == 1 and snapshot(folder) == before)
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder)
        (folder / ".env.cli").write_text("x=1\n", encoding="utf-8")
        before = snapshot(folder)
        code, _ = run(folder)
        check("an existing target file is refused", code == 1 and snapshot(folder) == before)
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder, admin="CHANGE_ME")
        code, _ = run(folder)
        check("a placeholder administrator password is refused", code == 1)


def case_quoted_and_partial_copy() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder)
        text = (folder / ".env").read_text(encoding="utf-8")
        quoted = text.replace("DATABASE_URL=", 'DATABASE_URL="', 1).replace("  # trailing", '"  # trailing', 1)
        (folder / ".env").write_text(quoted, encoding="utf-8")
        before = snapshot(folder)
        code, output = run(folder)
        check("a quoted DATABASE_URL is refused before anything is written", code == 1 and snapshot(folder) == before and "quoted" in output)
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder)
        before = snapshot(folder)
        original = tool.private_copy
        calls = {"n": 0}

        def truncating(source: Path, target: Path) -> None:
            calls["n"] += 1
            if calls["n"] == 2:
                target.write_bytes(b"trunc")  # a partial copy, then the failure
                raise OSError("disk full")
            original(source, target)

        tool.private_copy = truncating  # type: ignore[assignment]
        try:
            code, output = run(folder)
        finally:
            tool.private_copy = original  # type: ignore[assignment]
        check("a failure in the middle of a copy leaves no truncated backup and no changed original", code == 1 and snapshot(folder) == before)


def case_failure_midway() -> None:
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        make(folder)
        before = snapshot(folder)
        original = tool.rewrite_database_url

        def broken(path: Path, user: str, password: str) -> bool:
            if path.name == ".env.worker":
                raise OSError("disk full with a secret inside")
            return original(path, user, password)

        tool.rewrite_database_url = broken  # type: ignore[assignment]
        try:
            code, output = run(folder)
        finally:
            tool.rewrite_database_url = original  # type: ignore[assignment]
        check("a failure after the first write is undone completely", code == 1 and snapshot(folder) == before)
        check("the message names the error type only", "OSError" in output and "secret" not in output)


for newline in ("\n", "\r\n"):
    for bom in (False, True):
        case_normal(newline, bom)
case_refusals()
case_failure_midway()
case_quoted_and_partial_copy()
print(f"{len(FAILURES)} failure(s)")
sys.exit(1 if FAILURES else 0)
