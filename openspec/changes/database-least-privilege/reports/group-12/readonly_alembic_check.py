"""Read-only `alembic current` and `alembic check` against the development database.

Run INSIDE the existing worker container (nothing is recreated or stopped):
    docker exec -i asistenteia-worker-1 python - < readonly_alembic_check.py

The container holds the code of `main` (revisions up to 0005) and the credential of its own
DATABASE_URL, which is never printed. The session is read-only (`default_transaction_read_only`),
so even a defect of this script could not change the database. Change `database-least-privilege`,
task 12.1 and 12.3.
"""

import os
import sys

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

url = os.environ["DATABASE_URL"]
read_only = "options=-c%20default_transaction_read_only%3Don"
url = url + ("&" if "?" in url else "?") + read_only

config = Config("/app/alembic.ini")
config.set_main_option("script_location", "/app/alembic")
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

head = ScriptDirectory.from_config(config).get_current_head()
engine = create_engine(url)
try:
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        read_only_session = connection.exec_driver_sql("SHOW default_transaction_read_only").scalar()
finally:
    engine.dispose()
print(f"alembic current (database): {current}")
print(f"alembic head (code in the worker image): {head}")
print(f"session read-only: {read_only_session}")
try:
    command.check(config)
except Exception as exc:  # noqa: BLE001 - report the drift, never raise past the report
    print(f"alembic check: DRIFT or error: {type(exc).__name__}")
    sys.exit(1)
print("alembic check: no new upgrade operations detected (no drift)")
