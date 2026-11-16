"""`db-migrate`: Alembic as the migrator, then the grants (task 4.4).

The only supported way to migrate: grants vanish with a recreated table (A-07), so a migration
without the grants step would leave the new table owner-only. `alembic/env.py` refuses an online
run that is not given an explicit URL, which is what this module passes.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.db_admin.connection import require_identity
from app.db_admin.grants import apply_grants
from app.db_admin.names import DEFAULT_NAMES, RoleNames

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(migrator_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", migrator_url.replace("%", "%%"))
    return config


def migrate(migrator_url: str, *, names: RoleNames = DEFAULT_NAMES, revision: str = "head") -> None:
    """Upgrade to `revision` and apply the privilege matrix.

    The identity is checked first: Alembic runs no statement as anyone but the migrator (PG-02).
    """
    require_identity(migrator_url, names.migrator, "db-migrate")
    command.upgrade(alembic_config(migrator_url), revision)
    apply_grants(migrator_url, names=names)


def downgrade(migrator_url: str, revision: str, *, names: RoleNames = DEFAULT_NAMES) -> None:
    """Downgrade as the migrator. No grants are applied: the tables that remain keep theirs."""
    require_identity(migrator_url, names.migrator, "db-migrate --downgrade")
    command.downgrade(alembic_config(migrator_url), revision)
