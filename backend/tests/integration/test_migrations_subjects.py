from alembic import command
from sqlalchemy import text

from tests.db_support import alembic_config, drop_everything, guarded_engine


def fetch_all(url: str, sql: str, **params: object) -> list[tuple[object, ...]]:
    with guarded_engine(url) as engine, engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params)]


def table_exists(url: str, name: str) -> bool:
    rows = fetch_all(url, "SELECT to_regclass(:name) IS NOT NULL", name=f"public.{name}")
    return bool(rows[0][0])


def constraints(url: str, table: str) -> dict[str, str]:
    """Constraint name -> type letter ('p', 'u', 'f', 'c')."""
    rows = fetch_all(
        url,
        "SELECT conname, contype FROM pg_constraint WHERE conrelid = to_regclass(:name)",
        name=f"public.{table}",
    )
    return {str(name): str(kind) for name, kind in rows}


def foreign_key_actions(url: str, table: str) -> dict[str, str]:
    """FK name -> ON DELETE action ('c' cascade, 'r' restrict, 'a' no action)."""
    rows = fetch_all(
        url,
        "SELECT conname, confdeltype FROM pg_constraint "
        "WHERE conrelid = to_regclass(:name) AND contype = 'f'",
        name=f"public.{table}",
    )
    return {str(name): str(action) for name, action in rows}


def index_names(url: str, table: str) -> set[str]:
    rows = fetch_all(
        url,
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :table",
        table=table,
    )
    return {str(row[0]) for row in rows}


def test_upgrade_creates_subjects_and_enrollments_with_constraints_and_indexes(
    test_db_url: str,
) -> None:
    drop_everything(test_db_url)
    command.upgrade(alembic_config(test_db_url), "head")

    assert table_exists(test_db_url, "subjects")
    assert table_exists(test_db_url, "enrollments")

    subjects = constraints(test_db_url, "subjects")
    assert subjects["pk_subjects"] == "p"
    assert subjects["uq_subjects_teacher_id"] == "u"
    assert subjects["fk_subjects_teacher_id_users"] == "f"

    enrollments = constraints(test_db_url, "enrollments")
    assert enrollments["pk_enrollments"] == "p"
    assert enrollments["uq_enrollments_subject_id"] == "u"
    assert enrollments["fk_enrollments_subject_id_subjects"] == "f"
    assert enrollments["fk_enrollments_student_id_users"] == "f"
    assert "ix_enrollments_student_id" in index_names(test_db_url, "enrollments")


def test_foreign_keys_restrict_teacher_deletion_and_cascade_enrollments(test_db_url: str) -> None:
    drop_everything(test_db_url)
    command.upgrade(alembic_config(test_db_url), "head")

    assert foreign_key_actions(test_db_url, "subjects") == {"fk_subjects_teacher_id_users": "r"}
    assert foreign_key_actions(test_db_url, "enrollments") == {
        "fk_enrollments_subject_id_subjects": "c",
        "fk_enrollments_student_id_users": "c",
    }


def test_unique_constraints_cover_the_documented_column_pairs(test_db_url: str) -> None:
    drop_everything(test_db_url)
    command.upgrade(alembic_config(test_db_url), "head")

    rows = fetch_all(
        test_db_url,
        "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE contype = 'u' AND conrelid::regclass::text IN ('subjects', 'enrollments')",
    )
    definitions = {str(table): str(definition) for table, definition in rows}
    assert definitions["subjects"] == "UNIQUE (teacher_id, name)"
    assert definitions["enrollments"] == "UNIQUE (subject_id, student_id)"


def test_downgrade_one_step_removes_both_tables_and_keeps_users(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "head")

    command.downgrade(config, "0002")  # explicit: later revisions sit above 0003

    assert not table_exists(test_db_url, "subjects")
    assert not table_exists(test_db_url, "enrollments")
    assert table_exists(test_db_url, "users")

    command.upgrade(config, "head")  # re-upgrade works and leaves the database migrated
    assert table_exists(test_db_url, "subjects")
    assert table_exists(test_db_url, "enrollments")
