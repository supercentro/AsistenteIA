"""Check that the migrated database is at the head revision and that models and migrations agree.

Run from `backend/` with `MIGRATION_DATABASE_URL` (the migrator role) in the environment, after
`python -m app.cli db-migrate`. `alembic check` needs an explicit URL (a direct online run is
refused by `alembic/env.py`), so the command is called through the API with the URL in the
config, exactly like the migration tests. Prints revisions only, never the URL.
Change `database-least-privilege`, task 10.1.
"""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

MINIMUM_HEAD = 6  # the gate proves at least migration 0006 (the teacher separation)


def acceptable(head: str | None, current: str | None) -> bool:
    """The database is at the head of the migrations and the head is at least `MINIMUM_HEAD`."""
    if head is None or current != head or not head.isdigit():
        return False
    return int(head) >= MINIMUM_HEAD


def main() -> int:
    url = os.environ.get("MIGRATION_DATABASE_URL", "")
    if not url:
        print("::error::missing prerequisite MIGRATION_DATABASE_URL")
        return 1
    backend = Path.cwd()
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    head = ScriptDirectory.from_config(config).get_current_head()
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    print(f"revision in the database: {current}; head of the migrations: {head}")
    if not acceptable(head, current):
        print(f"::error::expected the database at the head (at least 000{MINIMUM_HEAD}): found {current}, head {head}")
        return 1
    command.check(config)  # raises when the models and the migrations differ
    print("alembic check: no drift between the models and the migrations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
