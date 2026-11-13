"""Migration 0006: server default `'student'` on `users.role` (change `database-least-privilege`).

The default lets the application role register students without holding `INSERT` on `users.role`
(decision DD-9, option A). Existing rows and roles must be untouched in both directions.
"""

from alembic import command
from alembic.script import ScriptDirectory

from tests.db_support import alembic_config, drop_everything
from tests.integration.test_migrations_documents import columns, fetch_all
from tests.sql_support import insert_user, run


def role_default(url: str) -> str | None:
    return columns(url, "users")["role"][2]


def test_0006_is_the_head_and_follows_0005() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://x/y_test"))

    assert script.get_heads() == ["0006"]
    revision = script.get_revision("0006")
    assert revision is not None
    assert revision.down_revision == "0005"


def test_upgrade_sets_the_default_and_keeps_every_existing_user(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0005")
    assert role_default(test_db_url) is None
    insert_user(test_db_url, "teacher@example.com", "teacher")
    insert_user(test_db_url, "student@example.com", "student")
    before = fetch_all(test_db_url, "SELECT id, email, role::text FROM users ORDER BY email")

    command.upgrade(config, "0006")

    assert role_default(test_db_url) == "'student'::user_role"
    assert (
        fetch_all(test_db_url, "SELECT id, email, role::text FROM users ORDER BY email") == before
    )
    run(
        test_db_url,
        "INSERT INTO users (name, email, password_hash) VALUES ('N', 'n@example.com', 'h')",
    )
    assert fetch_all(test_db_url, "SELECT role::text FROM users WHERE email = 'n@example.com'") == [
        ("student",)
    ]


def test_the_default_never_changes_an_assigned_role(test_db_url: str) -> None:
    drop_everything(test_db_url)
    command.upgrade(alembic_config(test_db_url), "head")

    insert_user(test_db_url, "t@example.com", "teacher")

    assert fetch_all(test_db_url, "SELECT role::text FROM users WHERE email = 't@example.com'") == [
        ("teacher",)
    ]


def test_downgrade_drops_only_the_default_and_loses_no_user(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0006")
    insert_user(test_db_url, "teacher@example.com", "teacher")
    insert_user(test_db_url, "student@example.com", "student")
    before = fetch_all(test_db_url, "SELECT id, email, role::text FROM users ORDER BY email")

    command.downgrade(config, "0005")

    assert role_default(test_db_url) is None
    assert (
        fetch_all(test_db_url, "SELECT id, email, role::text FROM users ORDER BY email") == before
    )
    command.upgrade(config, "head")  # the round trip leaves the database migrated
    assert role_default(test_db_url) == "'student'::user_role"


def test_models_and_migrations_agree_after_0006(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "head")

    command.check(config)  # raises CommandError when models and the database differ
