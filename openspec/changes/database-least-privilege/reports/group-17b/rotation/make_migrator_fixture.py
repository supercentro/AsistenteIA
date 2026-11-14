"""Write a SYNTHETIC backend env folder for the migrator rotation tests (SEC-17B-01). No real value: every secret is random."""

from __future__ import annotations

import secrets
import sys
from pathlib import Path


def main(root: Path, host: str) -> None:
    old = "Old" + secrets.token_urlsafe(30)
    new = "New" + secrets.token_urlsafe(30)
    admin = "Adm" + secrets.token_urlsafe(30)
    folder, outside = root / "backend", root / "outside"
    folder.mkdir(parents=True)
    outside.mkdir()
    nl = chr(10)
    pw = lambda: secrets.token_urlsafe(24)  # noqa: E731
    (folder / ".env.db").write_text(f"POSTGRES_USER=asistente{nl}POSTGRES_PASSWORD={admin}{nl}POSTGRES_DB=asistenteia{nl}", encoding="utf-8")
    (folder / ".env.roles").write_text(
        f"ADMIN_DATABASE_URL=postgresql+psycopg://asistente:{admin}@{host}:5432/postgres{nl}"
        f"DB_MIGRATOR_PASSWORD={old}  # synthetic{nl}DB_APP_PASSWORD=App{pw()}{nl}DB_WORKER_PASSWORD=Wrk{pw()}{nl}DB_CLI_PASSWORD=Cli{pw()}{nl}",
        encoding="utf-8",
    )
    (folder / ".env.migrate").write_text(f"MIGRATION_DATABASE_URL=postgresql+psycopg://asistente_migrator:{old}@{host}:5432/asistenteia{nl}", encoding="utf-8")
    (folder / ".env").write_text(f"DATABASE_URL=postgresql+psycopg://asistente_app:App{pw()}@{host}:5432/asistenteia{nl}JWT_SECRET=Jwt{pw()}{nl}", encoding="utf-8")
    (folder / ".env.worker").write_text(f"DATABASE_URL=postgresql+psycopg://asistente_worker:Wrk{pw()}@{host}:5432/asistenteia{nl}", encoding="utf-8")
    (folder / ".env.pre-17b").write_text(f"DATABASE_URL=postgresql+psycopg://asistente:{admin}@{host}:5432/asistenteia{nl}", encoding="utf-8")
    (outside / "old.txt").write_text(old + nl, encoding="utf-8")
    (outside / "new.txt").write_text(new + nl, encoding="utf-8")
    (outside / "admin.txt").write_text(admin + nl, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
