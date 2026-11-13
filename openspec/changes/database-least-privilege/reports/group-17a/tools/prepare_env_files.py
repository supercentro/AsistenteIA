"""Prepare the environment files of the roles flow WITHOUT printing or logging any value (group 17A).

usage: python prepare_env_files.py <directory> [--dry-run | --rollback]

The directory holds the existing files `.env.db`, `.env` (API) and `.env.worker`. The tool

- backs up `.env`, `.env.worker` and `.env.db` as `<name>.pre-17b` (mode 0600 where the system has modes),
- creates `.env.roles` (administrator URL taken from `.env.db`, four NEW random passwords),
  `.env.migrate` and `.env.cli`,
- rewrites only the user and the password of `DATABASE_URL` in `.env` (role `asistente_app`) and in
  `.env.worker` (role `asistente_worker`), leaving every other line byte for byte,
- prints variable NAMES and file names only, never a value, and refuses to run when a target file
  already exists (so it can not overwrite a previous run), when a file is missing, or when the
  existing `DATABASE_URL` does not look like the administrator of `.env.db`.

With `--rollback` it undoes the switch: `.env` and `.env.worker` are restored from their `.pre-17b` copies
but their DATABASE_URL gets the administrator of the CURRENT `.env.db` (so a rotated password is used,
not the exposed one), and `.env.roles`, `.env.migrate` and `.env.cli` are renamed `*.rolled-back`.
The `.pre-17b` copies are kept and MUST be destroyed after the acceptance because they hold the old
administrator password.

It is the executable form of step 17B.3; in 17A it was only run on synthetic files.
"""

import os
import re
import secrets
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ADMIN_FILE = ".env.db"
API_FILE = ".env"
WORKER_FILE = ".env.worker"
NEW_FILES = (".env.roles", ".env.migrate", ".env.cli")
HOST = "db"  # the Compose service name
DATABASE = "asistenteia"
ROLES = {
    "migrator": "asistente_migrator",
    "app": "asistente_app",
    "worker": "asistente_worker",
    "cli": "asistente_cli",
}


def read_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).split(" #")[0].strip()
    return values


def url(user: str, password: str, database: str) -> str:
    return f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}@{HOST}:5432/{database}"


def private_copy(source: Path, target: Path) -> None:
    shutil.copy2(source, target)
    try:
        os.chmod(target, 0o600)
    except OSError:  # a file system without modes (Windows): the folder permissions apply
        pass


def rewrite_database_url(path: Path, user: str, password: str) -> bool:
    """Replace user and password of DATABASE_URL, keeping host, port, database and every other line."""
    changed = False
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = re.match(r"^(DATABASE_URL=)(\S+)(.*)$", line.rstrip("\r\n"))
        if not match:
            continue
        parts = urlsplit(match.group(2))
        host = parts.hostname or ""
        netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}" + (f":{parts.port}" if parts.port else "")
        ending = line[len(line.rstrip("\r\n")):]
        lines[index] = match.group(1) + urlunsplit((parts.scheme, netloc, parts.path, parts.query, "")) + match.group(3) + ending
        changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8", newline="")
    return changed


def rollback(folder: Path) -> int:
    pre = [folder / (name + ".pre-17b") for name in (API_FILE, WORKER_FILE)]
    if not all(path.is_file() for path in pre) or not (folder / ADMIN_FILE).is_file():
        print("refused: the .pre-17b copies of .env and .env.worker or .env.db are missing")
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


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    folder = Path(argv[0])
    if "--rollback" in argv:
        return rollback(folder)
    dry_run = "--dry-run" in argv
    missing = [name for name in (ADMIN_FILE, API_FILE, WORKER_FILE) if not (folder / name).is_file()]
    present = [name for name in NEW_FILES if (folder / name).exists()]
    backups = [name + ".pre-17b" for name in (ADMIN_FILE, API_FILE, WORKER_FILE) if (folder / (name + ".pre-17b")).exists()]
    if missing or present or backups:
        print(f"refused: missing={missing} already-present={present + backups}")
        return 1

    admin = read_assignments(folder / ADMIN_FILE)
    admin_user, admin_password = admin.get("POSTGRES_USER", ""), admin.get("POSTGRES_PASSWORD", "")
    if not admin_user or not admin_password or "CHANGE_ME" in admin_password or admin.get("POSTGRES_DB") != DATABASE:
        print("refused: .env.db is incomplete (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB=asistenteia)")
        return 1
    for name in (API_FILE, WORKER_FILE):
        current = urlsplit(read_assignments(folder / name).get("DATABASE_URL", ""))
        if current.username != admin_user or current.password != admin_password or current.hostname != HOST:
            print(f"refused: DATABASE_URL of {name} is not the administrator of .env.db at host {HOST}")
            return 1

    passwords = {logical: secrets.token_urlsafe(24) for logical in ROLES}
    if dry_run:
        print("dry run: nothing written; would create", ", ".join(NEW_FILES), "and rewrite DATABASE_URL in", API_FILE, "and", WORKER_FILE)
        return 0

    for name in (ADMIN_FILE, API_FILE, WORKER_FILE):
        private_copy(folder / name, folder / (name + ".pre-17b"))
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
        target = folder / name
        target.write_text(content, encoding="utf-8", newline="")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    rewrote_api = rewrite_database_url(folder / API_FILE, ROLES["app"], passwords["app"])
    rewrote_worker = rewrite_database_url(folder / WORKER_FILE, ROLES["worker"], passwords["worker"])
    if not (rewrote_api and rewrote_worker):
        print("error: DATABASE_URL not found in .env or .env.worker; restore the .pre-17b copies")
        return 1
    print("created:", ", ".join(files), "| variables written: ADMIN_DATABASE_URL DB_MIGRATOR_PASSWORD DB_APP_PASSWORD DB_WORKER_PASSWORD DB_CLI_PASSWORD MIGRATION_DATABASE_URL CLI_DATABASE_URL")
    print("rewritten (user and password only): DATABASE_URL in", API_FILE, "and", WORKER_FILE)
    print("backups:", ", ".join(name + ".pre-17b" for name in (ADMIN_FILE, API_FILE, WORKER_FILE)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
