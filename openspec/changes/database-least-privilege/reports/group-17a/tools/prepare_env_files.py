"""Prepare the environment files of the roles flow WITHOUT printing or logging any value (group 17A).

usage: python prepare_env_files.py <directory> [--dry-run | --rollback]

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

With `--rollback` it undoes the switch: `.env` and `.env.worker` are restored from their `.pre-17b` copies
but their DATABASE_URL gets the administrator of the CURRENT `.env.db` (so a rotated password is used, not
the exposed one), and `.env.roles`, `.env.migrate` and `.env.cli` are renamed `*.rolled-back` (refused if a
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
    already = [name for name in NEW_FILES if (folder / (name + ".rolled-back")).exists()]
    if already:
        print(f"refused: {already} already exist; move them away first")
        return 1
    admin = read_assignments(folder / ADMIN_FILE)
    user, password = admin.get("POSTGRES_USER", ""), admin.get("POSTGRES_PASSWORD", "")
    if not user or not password:
        print("refused: .env.db is incomplete")
        return 1
    for name in (API_FILE, WORKER_FILE):
        shutil.copy2(folder / (name + ".pre-17b"), folder / name)
        if not rewrite_database_url(folder / name, user, password):
            print(f"error: DATABASE_URL not found in {name}")
            return 1
    for name in NEW_FILES:
        source = folder / name
        if source.exists():
            source.replace(folder / (name + ".rolled-back"))
    print("restored (administrator of the current .env.db):", API_FILE, WORKER_FILE)
    print("renamed to *.rolled-back:", ", ".join(NEW_FILES))
    print("destroy the .pre-17b copies after the acceptance: they hold the previous administrator password")
    return 0


def forward(folder: Path, dry_run: bool) -> int:
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
    if dry_run:
        print("dry run: nothing written; would create", ", ".join(NEW_FILES), "and rewrite DATABASE_URL in", API_FILE, "and", WORKER_FILE)
        return 0

    passwords = {logical: secrets.token_urlsafe(24) for logical in ROLES}
    created: list[Path] = []
    completed: list[str] = []  # backups copied completely: only these may restore an original
    try:
        for name in BACKED_UP:
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
            private_write(folder / name, content)
            created.append(folder / name)
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
    except Exception as error:  # noqa: BLE001 - undo, then report the TYPE only (a message could hold a value)
        problems: list[str] = []
        for name in (API_FILE, WORKER_FILE):
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
    print("backups:", ", ".join(name + ".pre-17b" for name in BACKED_UP))
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    folder = Path(argv[0])
    if "--rollback" in argv:
        return rollback(folder)
    return forward(folder, "--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
