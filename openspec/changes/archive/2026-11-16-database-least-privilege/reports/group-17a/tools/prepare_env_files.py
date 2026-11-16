"""Prepare the environment files of the roles flow WITHOUT printing or logging any value (group 17A).

usage: python prepare_env_files.py <directory> [--dry-run] [--strip-legacy] | --rollback

The directory holds the existing files `.env.db`, `.env` (API) and `.env.worker`. The tool

- validates everything first (nothing is written when a check fails),
- backs up `.env`, `.env.worker` and `.env.db` as `<name>.pre-17b` (mode 0600 where the system has modes),
- creates `.env.roles` (administrator URL taken from `.env.db`, four NEW random passwords),
  `.env.migrate` and `.env.cli`,
- rewrites only the user and the password of `DATABASE_URL` in `.env` (role `asistente_app`) and in
  `.env.worker` (role `asistente_worker`); every other line is kept byte for byte, line endings included
  (a UTF-8 byte order mark is dropped, because Compose would read it as part of the first name),
- prints variable NAMES and file names only, never a value,
- refuses to run when a target file already exists (so it can not overwrite a previous run), when a file
  is missing, when `DATABASE_URL` does not appear exactly once per file, or when it is not the
  administrator of `.env.db`,
- undoes what it did when it fails after the first write (the new files are removed, the originals restored
  from the backups, the backups removed), so a failure never leaves a half-prepared folder.

Legacy variables: the API file of a checkout from before the split of the env files may still carry
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (the database administrator, already in `.env.db`) and
`TEST_*` (host-only test settings, whose URLs hold the administrator password). The API container would
keep receiving them, so the run is REFUSED while `.env` or `.env.worker` carry them, naming them. With
`--strip-legacy` the `POSTGRES_*` lines are removed and the `TEST_*` lines are MOVED to `.env.test` (created
with mode 0600, or appended to when it exists and does not already hold those names; a pre-existing file is
backed up as `.env.test.pre-17b`; a created one leaves the marker `.env.test.absent-before-17b`). Host tests
keep working because they read `.env.test` first.

With `--rollback` it undoes the switch: `.env` and `.env.worker` are restored from their `.pre-17b` copies
but their DATABASE_URL gets the administrator of the CURRENT `.env.db` (so a rotated password is used, not
the exposed one), the `TEST_*` lines of the restored `.env` take the CURRENT values of `.env.test` when it holds
them (a created `.env.test` is renamed `.env.test.rolled-back`), and `.env.roles`, `.env.migrate` and `.env.cli` are renamed `*.rolled-back` (refused if a
`*.rolled-back` already exists). The `.pre-17b` copies are kept and MUST be destroyed after the acceptance
because they hold the old administrator password; a new forward run is refused while they exist.

It is the executable form of step 17B.2; in 17A it was run only on synthetic files (`test_prepare_env_files.py`
and the replica).
"""

import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ADMIN_FILE = ".env.db"
API_FILE = ".env"
WORKER_FILE = ".env.worker"
NEW_FILES = (".env.roles", ".env.migrate", ".env.cli")
TEST_FILE = ".env.test"
MARKER = ".env.test.absent-before-17b"
LEGACY = re.compile(r"^(POSTGRES_(USER|PASSWORD|DB)|TEST_[A-Z0-9_]+)=")
BACKED_UP = (ADMIN_FILE, API_FILE, WORKER_FILE)
HOST = "db"  # the Compose service name
DATABASE = "asistenteia"
ROLES = {
    "migrator": "asistente_migrator",
    "app": "asistente_app",
    "worker": "asistente_worker",
    "cli": "asistente_cli",
}


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8-sig", newline="") as handle:  # keeps CRLF, drops a BOM
        return handle.read()


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def clean_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value.split(" #")[0].strip()


def read_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if match:
            values[match.group(1)] = clean_value(match.group(2))
    return values


def database_url_lines(path: Path) -> int:
    return sum(1 for line in read_text(path).splitlines() if line.startswith("DATABASE_URL="))


def legacy_names(path: Path) -> list[str]:
    return sorted({line.split("=", 1)[0] for line in read_text(path).splitlines() if LEGACY.match(line)})


def split_legacy(path: Path) -> tuple[list[str], list[str]]:
    """The TEST_* lines (kept with their endings) and the file text without any legacy line."""
    moved, kept = [], []
    for line in read_text(path).splitlines(keepends=True):
        if LEGACY.match(line):
            if line.startswith("TEST_"):
                moved.append(line if line.endswith("\n") else line + "\n")
        else:
            kept.append(line)
    return moved, kept


def database_url_is_quoted(path: Path) -> bool:
    for line in read_text(path).splitlines():
        if line.startswith("DATABASE_URL="):
            return line[len("DATABASE_URL=") :].lstrip()[:1] in {"'", '"'}
    return False


def rewritten_correctly(path: Path, user: str, password: str) -> bool:
    """Re-read the file and check scheme, user, password and host of DATABASE_URL (never printed)."""
    try:
        parts = urlsplit(read_assignments(path).get("DATABASE_URL", ""))
        return (
            parts.scheme == "postgresql+psycopg"
            and unquote(parts.username or "") == user
            and unquote(parts.password or "") == password
            and parts.hostname == HOST
        )
    except ValueError:
        return False


def url(user: str, password: str, database: str) -> str:
    return f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}@{HOST}:5432/{database}"


def private_copy(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    try:
        os.chmod(target, 0o600)
    except OSError:  # a file system without modes (Windows): the folder permissions apply
        pass


def private_write(path: Path, text: str) -> None:
    write_text(path, text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def rewrite_database_url(path: Path, user: str, password: str) -> bool:
    """Replace user and password of DATABASE_URL, keeping host, port, database, query and every other line."""
    changed = False
    lines = read_text(path).splitlines(keepends=True)
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = re.match(r"^(DATABASE_URL=)(\S+)(.*)$", body)
        if not match:
            continue
        parts = urlsplit(match.group(2))
        netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{parts.hostname or ''}" + (
            f":{parts.port}" if parts.port else ""
        )
        replaced = urlunsplit((parts.scheme, netloc, parts.path, parts.query, ""))
        lines[index] = match.group(1) + replaced + match.group(3) + ending
        changed = True
    if changed:
        write_text(path, "".join(lines))
    return changed


def is_administrator_url(raw: str, user: str, password: str) -> bool:
    try:
        parts = urlsplit(raw)
        return (
            unquote(parts.username or "") == user
            and unquote(parts.password or "") == password
            and parts.hostname == HOST
        )
    except ValueError:
        return False


def rollback(folder: Path) -> int:
    pre = [folder / (name + ".pre-17b") for name in (API_FILE, WORKER_FILE)]
    if not all(path.is_file() for path in pre) or not (folder / ADMIN_FILE).is_file():
        print("refused: the .pre-17b copies of .env and .env.worker or .env.db are missing")
        return 1
    already = [name for name in (*NEW_FILES, TEST_FILE, API_FILE, WORKER_FILE) if (folder / (name + ".rolled-back")).exists()]
    if already:
        print(f"refused: {already} already exist; move them away first")
        return 1
    admin = read_assignments(folder / ADMIN_FILE)
    user, password = admin.get("POSTGRES_USER", ""), admin.get("POSTGRES_PASSWORD", "")
    if not user or not password:
        print("refused: .env.db is incomplete")
        return 1
    for name in (API_FILE, WORKER_FILE):
        shutil.copy2(folder / name, folder / (name + ".rolled-back"))  # keep what is being replaced: nothing edited after 17B is lost
        shutil.copy2(folder / (name + ".pre-17b"), folder / name)
        if not rewrite_database_url(folder / name, user, password):
            print(f"error: DATABASE_URL not found in {name}")
            return 1
    test_file = folder / TEST_FILE
    if test_file.is_file():
        current = {line.split("=", 1)[0]: line for line in read_text(test_file).splitlines(keepends=True) if line.startswith("TEST_") and "=" in line}
        restored = read_text(folder / API_FILE).splitlines(keepends=True)
        for index, line in enumerate(restored):
            key = line.split("=", 1)[0]
            if line.startswith("TEST_") and key in current:
                restored[index] = current[key] if current[key].endswith("\n") else current[key] + "\n"
        write_text(folder / API_FILE, "".join(restored))
        if (folder / MARKER).exists():  # .env.test did not exist before 17B: it was created by the tool
            test_file.replace(folder / (TEST_FILE + ".rolled-back"))
            (folder / MARKER).unlink()
    for name in NEW_FILES:
        source = folder / name
        if source.exists():
            source.replace(folder / (name + ".rolled-back"))
    print("restored (administrator of the current .env.db):", API_FILE, WORKER_FILE)
    print("renamed to *.rolled-back:", ", ".join(NEW_FILES))
    print("destroy the .pre-17b copies after the acceptance: they hold the previous administrator password")
    return 0


def forward(folder: Path, dry_run: bool, strip_legacy: bool) -> int:
    missing = [name for name in BACKED_UP if not (folder / name).is_file()]
    present = [name for name in NEW_FILES if (folder / name).exists()]
    backups = [name + ".pre-17b" for name in BACKED_UP if (folder / (name + ".pre-17b")).exists()]
    rolled = [name + ".rolled-back" for name in NEW_FILES if (folder / (name + ".rolled-back")).exists()]
    if missing or present or backups or rolled:
        print(f"refused: missing={missing} already-present={present + backups + rolled}")
        if backups:
            print("destroy the .pre-17b copies (they hold the previous administrator password) before a new run")
        return 1
    admin = read_assignments(folder / ADMIN_FILE)
    admin_user, admin_password = admin.get("POSTGRES_USER", ""), admin.get("POSTGRES_PASSWORD", "")
    if not admin_user or not admin_password or "CHANGE_ME" in admin_password or admin.get("POSTGRES_DB") != DATABASE:
        print("refused: .env.db is incomplete (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB=asistenteia)")
        return 1
    for name in (API_FILE, WORKER_FILE):
        if database_url_lines(folder / name) != 1:
            print(f"refused: DATABASE_URL must appear exactly once in {name}")
            return 1
        if database_url_is_quoted(folder / name):
            print(f"refused: DATABASE_URL of {name} is quoted; remove the quotes by hand first")
            return 1
        if not is_administrator_url(read_assignments(folder / name).get("DATABASE_URL", ""), admin_user, admin_password):
            print(f"refused: DATABASE_URL of {name} is not the administrator of .env.db at host {HOST}")
            return 1
    legacy = {name: legacy_names(folder / name) for name in (API_FILE, WORKER_FILE)}
    if any(legacy.values()) and not strip_legacy:
        print(f"refused: legacy names that would keep the administrator credentials in the service environment: {legacy}; run again with --strip-legacy (POSTGRES_* removed, TEST_* moved to {TEST_FILE})")
        return 1
    moved_names = sorted({n for name in (API_FILE, WORKER_FILE) for n in legacy[name] if n.startswith("TEST_")})
    if moved_names and (folder / TEST_FILE).exists():
        already = sorted(set(moved_names) & set(read_assignments(folder / TEST_FILE)))
        if already:
            print(f"refused: {TEST_FILE} already holds {already}; reconcile by hand")
            return 1
    if dry_run:
        if any(legacy.values()):
            print(f"dry run: would strip {legacy} (TEST_* to {TEST_FILE}, {'appended' if (folder / TEST_FILE).exists() else 'created'})")
        print("dry run: nothing written; would create", ", ".join(NEW_FILES), "and rewrite DATABASE_URL in", API_FILE, "and", WORKER_FILE)
        return 0

    passwords = {logical: secrets.token_urlsafe(24) for logical in ROLES}
    created: list[Path] = []
    completed: list[str] = []  # backups copied completely: only these may restore an original
    try:
        test_existed = (folder / TEST_FILE).exists()
        to_back_up = list(BACKED_UP) + ([TEST_FILE] if (moved_names and test_existed) else [])
        for name in to_back_up:
            created.append(folder / (name + ".pre-17b"))  # registered BEFORE the copy: a truncated copy is removed
            private_copy(folder / name, folder / (name + ".pre-17b"))
            completed.append(name)
        roles = (
            f"ADMIN_DATABASE_URL={url(admin_user, admin_password, 'postgres')}\n"
            f"DB_MIGRATOR_PASSWORD={passwords['migrator']}\nDB_APP_PASSWORD={passwords['app']}\n"
            f"DB_WORKER_PASSWORD={passwords['worker']}\nDB_CLI_PASSWORD={passwords['cli']}\n"
        )
        files = {
            ".env.roles": roles,
            ".env.migrate": f"MIGRATION_DATABASE_URL={url(ROLES['migrator'], passwords['migrator'], DATABASE)}\n",
            ".env.cli": f"CLI_DATABASE_URL={url(ROLES['cli'], passwords['cli'], DATABASE)}\n",
        }
        for name, content in files.items():
            created.append(folder / name)  # registered BEFORE the write: a partial file is removed by the undo
            private_write(folder / name, content)
        if any(legacy.values()):
            moved, kept = split_legacy(folder / API_FILE)
            worker_moved, worker_kept = split_legacy(folder / WORKER_FILE)
            seen = {line.split("=", 1)[0] for line in moved}
            moved = moved + [line for line in worker_moved if line.split("=", 1)[0] not in seen]  # TEST_* of .env.worker are kept too
            if moved:
                if test_existed:
                    existing = read_text(folder / TEST_FILE)
                    private_write(folder / TEST_FILE, existing + ("" if existing.endswith("\n") or not existing else "\n") + "".join(moved))
                else:
                    created.append(folder / TEST_FILE)
                    created.append(folder / MARKER)
                    private_write(folder / TEST_FILE, "".join(moved))
                    private_write(folder / MARKER, "")
            write_text(folder / API_FILE, "".join(kept))
            write_text(folder / WORKER_FILE, "".join(worker_kept))
        if not (
            rewrite_database_url(folder / API_FILE, ROLES["app"], passwords["app"])
            and rewrite_database_url(folder / WORKER_FILE, ROLES["worker"], passwords["worker"])
        ):
            raise RuntimeError("DATABASE_URL not rewritten")
        if not (
            rewritten_correctly(folder / API_FILE, ROLES["app"], passwords["app"])
            and rewritten_correctly(folder / WORKER_FILE, ROLES["worker"], passwords["worker"])
        ):
            raise RuntimeError("DATABASE_URL rewritten wrongly")
        if legacy_names(folder / API_FILE) or legacy_names(folder / WORKER_FILE):
            raise RuntimeError("legacy names remain")
    except BaseException as error:  # noqa: BLE001 - also Ctrl+C: the undo must run - undo, then report the TYPE only (a message could hold a value)
        problems: list[str] = []
        for name in (API_FILE, WORKER_FILE, TEST_FILE):
            if name in completed:
                try:
                    shutil.copy2(folder / (name + ".pre-17b"), folder / name)
                except OSError as undo_error:
                    problems.append(f"{name}: {type(undo_error).__name__}")
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError as undo_error:
                problems.append(f"{path.name}: {type(undo_error).__name__}")
        if problems:
            print(f"error: {type(error).__name__}; the undo itself failed for: {', '.join(problems)}; the originals are the files named *.pre-17b, copy them back by hand")
        else:
            print(f"error: {type(error).__name__}; everything was undone, the folder is as it was")
        return 1
    print("created:", ", ".join(files), "| variables written: ADMIN_DATABASE_URL DB_MIGRATOR_PASSWORD DB_APP_PASSWORD DB_WORKER_PASSWORD DB_CLI_PASSWORD MIGRATION_DATABASE_URL CLI_DATABASE_URL")
    print("rewritten (user and password only): DATABASE_URL in", API_FILE, "and", WORKER_FILE)
    print("backups:", ", ".join(name + ".pre-17b" for name in to_back_up))
    if any(legacy.values()):
        print("legacy names stripped:", legacy)
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    folder = Path(argv[0])
    if "--rollback" in argv:
        return rollback(folder)
    return forward(folder, "--dry-run" in argv, "--strip-legacy" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
