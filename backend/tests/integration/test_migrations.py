from alembic import command
from sqlalchemy import text

from tests.db_support import alembic_config, drop_everything, guarded_engine


def vector_installed(url: str) -> bool:
    with guarded_engine(url) as engine, engine.connect() as conn:
        found = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
    return found is not None


def users_table_and_type(url: str) -> tuple[bool, bool]:
    with guarded_engine(url) as engine, engine.connect() as conn:
        table = conn.execute(text("SELECT to_regclass('public.users') IS NOT NULL")).scalar_one()
        enum = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role')")
        ).scalar_one()
    return bool(table), bool(enum)


def constraint_names(url: str) -> set[str]:
    with guarded_engine(url) as engine, engine.connect() as conn:
        rows = conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conrelid = 'public.users'::regclass")
        )
        return {row[0] for row in rows}


def test_upgrade_head_enables_vector_and_downgrade_base_removes_it(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)

    command.upgrade(config, "head")
    assert vector_installed(test_db_url)

    command.downgrade(config, "base")
    assert not vector_installed(test_db_url)

    command.upgrade(config, "head")
    assert vector_installed(test_db_url)


def test_users_table_and_role_type_exist_after_upgrade_and_vanish_after_downgrade(
    test_db_url: str,
) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)

    command.upgrade(config, "head")
    assert users_table_and_type(test_db_url) == (True, True)
    assert {
        "pk_users",
        "uq_users_email",
        "ck_users_email_lowercase",
    } <= constraint_names(test_db_url)

    command.downgrade(config, "base")
    assert users_table_and_type(test_db_url) == (False, False)

    command.upgrade(config, "head")  # leaves the database migrated for the other tests
    assert users_table_and_type(test_db_url) == (True, True)


def test_users_migration_downgrades_one_step_to_the_vector_revision(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "head")

    command.downgrade(config, "-1")

    assert users_table_and_type(test_db_url) == (False, False)
    assert vector_installed(test_db_url)
    command.upgrade(config, "head")
