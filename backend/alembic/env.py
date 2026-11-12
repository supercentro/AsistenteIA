"""Alembic environment.

Offline runs (`--sql`) use MIGRATION_DATABASE_URL (the migrator role, `.env.migrate`) from
`MigrationSettings`: the API settings are never loaded, so no JWT secret is needed and DATABASE_URL
is never a fallback. Online runs must go through `python -m app.cli db-migrate`, which passes the
URL explicitly and applies the privilege grants afterwards (a recreated table loses its grants).
Tests pass an explicit `sqlalchemy.url` (already validated by the test-database guard) through the
Alembic config.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (register models on the metadata)
from app.core.config import load_migration_settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit
    if not context.is_offline_mode():
        raise RuntimeError(
            "Run migrations with `python -m app.cli db-migrate`: it applies the privilege grants "
            "after Alembic. A direct online alembic run without an explicit URL is refused."
        )
    return load_migration_settings().migration_database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
