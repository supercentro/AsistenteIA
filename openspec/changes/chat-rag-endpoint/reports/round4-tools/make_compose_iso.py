"""Builds a throwaway copy of the repository with throwaway env files for an isolated Compose project.

Nothing here reads or copies a real env file: the copy comes from `git ls-files` (which ignores them)
and every value below is generated now.
"""

import re
import secrets
import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])  # clean copy of the repository (no env files)
target = Path(sys.argv[2])
assert "scratchpad" in str(target), "refusing to write outside the scratch directory"

if target.exists():
    shutil.rmtree(target)
target.mkdir(parents=True)
for name in ('backend', 'frontend', 'docker'):
    shutil.copytree(source / name, target / name)
shutil.copy(source / 'docker-compose.yml', target / 'docker-compose.yml')

pw = {name: secrets.token_urlsafe(24) for name in ("admin", "migrator", "app", "worker", "cli")}
backend = target / "backend"

(backend / ".env.db").write_text(
    f"POSTGRES_USER=asistente\nPOSTGRES_PASSWORD={pw['admin']}\nPOSTGRES_DB=asistenteia\n"
)
(backend / ".env.roles").write_text(
    f"ADMIN_DATABASE_URL=postgresql+psycopg://asistente:{pw['admin']}@db:5432/postgres\n"
    f"DB_MIGRATOR_PASSWORD={pw['migrator']}\nDB_APP_PASSWORD={pw['app']}\n"
    f"DB_WORKER_PASSWORD={pw['worker']}\nDB_CLI_PASSWORD={pw['cli']}\n"
)
(backend / ".env.migrate").write_text(
    f"MIGRATION_DATABASE_URL=postgresql+psycopg://asistente_migrator:{pw['migrator']}@db:5432/asistenteia\n"
)
(backend / ".env.cli").write_text(
    f"CLI_DATABASE_URL=postgresql+psycopg://asistente_cli:{pw['cli']}@db:5432/asistenteia\n"
)
(backend / ".env").write_text(
    "APP_ENV=development\n"
    f"DATABASE_URL=postgresql+psycopg://asistente_app:{pw['app']}@db:5432/asistenteia\n"
    f"JWT_SECRET={secrets.token_urlsafe(48)}\n"
    "CORS_ORIGINS=http://localhost:5173\n"
    "LLM_BACKEND=fake\nALLOW_FAKE_LLM=true\n"
)
worker = (backend / ".env.worker.example").read_text()
worker = re.sub(
    r"^DATABASE_URL=.*$",
    f"DATABASE_URL=postgresql+psycopg://asistente_worker:{pw['worker']}@db:5432/asistenteia",
    worker,
    flags=re.MULTILINE,
)
assert not any("CHANGE_ME" in l for l in worker.splitlines() if not l.lstrip().startswith("#")), "unreplaced placeholder"
(backend / ".env.worker").write_text(worker)
(target / "frontend" / ".env").write_text("VITE_API_URL=http://localhost:8000/api/v1\n")

(target / "docker-compose.verify.yml").write_text(
    "services:\n"
    "  db:\n    ports: !reset []\n"
    "  backend:\n    ports: !reset []\n"
    "  frontend:\n    ports: !reset []\n"
)
print("prepared", target)
