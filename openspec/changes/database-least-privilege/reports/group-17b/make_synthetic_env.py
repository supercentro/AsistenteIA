"""Write a SYNTHETIC backend env folder (legacy administrator variables included) for the 17B.1 tests. No real value."""

from __future__ import annotations

import sys
from pathlib import Path

ADMIN = "Syn-Admin-pw-0123456789"


def make(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    url = f"postgresql+psycopg://asistente:{ADMIN}@db:5432/asistenteia"
    (folder / ".env.db").write_text(f"POSTGRES_USER=asistente\nPOSTGRES_PASSWORD={ADMIN}\nPOSTGRES_DB=asistenteia\n", encoding="utf-8")
    (folder / ".env").write_text(
        f"APP_ENV=development\nDATABASE_URL={url}\nPOSTGRES_USER=asistente\nPOSTGRES_PASSWORD={ADMIN}\nPOSTGRES_DB=asistenteia\n"
        f"TEST_DATABASE_URL=postgresql+psycopg://asistente:{ADMIN}@127.0.0.1:5442/asistenteia_test\nJWT_SECRET=not-a-real-secret-0123456789abcdef\n",
        encoding="utf-8",
    )
    (folder / ".env.worker").write_text(f"LOG_LEVEL=INFO\nDATABASE_URL={url}\n", encoding="utf-8")


if __name__ == "__main__":
    make(Path(sys.argv[1]))
