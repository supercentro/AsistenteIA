"""Write a SYNTHETIC backend env folder, an old-password file and a new-password file for the rotation tests. No real value."""

from __future__ import annotations

import secrets
import sys
from pathlib import Path


def main(root: Path, host: str) -> None:
    old = "Old" + secrets.token_urlsafe(30)
    new = "New" + secrets.token_urlsafe(30)
    folder = root / "backend"
    outside = root / "outside"
    folder.mkdir(parents=True)
    outside.mkdir()
    nl = chr(10)
    (folder / ".env.db").write_text(f"POSTGRES_USER=asistente{nl}POSTGRES_PASSWORD={old}{nl}POSTGRES_DB=asistenteia{nl}", encoding="utf-8")
    (folder / ".env.roles").write_text(
        f"ADMIN_DATABASE_URL=postgresql+psycopg://asistente:{old}@{host}:5432/postgres{nl}DB_APP_PASSWORD=AppPw_{secrets.token_urlsafe(24)}{nl}", encoding="utf-8"
    )
    (folder / ".env.test").write_text(
        f"TEST_DATABASE_URL=postgresql+psycopg://asistente:{old}@{host}:5432/asistenteia_test{nl}"
        f"TEST_ADMIN_DATABASE_URL=postgresql+psycopg://asistente:{old}@{host}:5432/postgres{nl}",
        encoding="utf-8",
    )
    (folder / ".env.db.pre-17b").write_text(f"POSTGRES_USER=asistente{nl}POSTGRES_PASSWORD={old}{nl}", encoding="utf-8")
    (folder / ".env.pre-17b").write_text(f"DATABASE_URL=postgresql+psycopg://asistente:{old}@{host}:5432/asistenteia{nl}", encoding="utf-8")
    (outside / "old.txt").write_text(old + nl, encoding="utf-8")
    (outside / "new.txt").write_text(new + nl, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
