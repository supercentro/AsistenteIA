"""Migration 0008: `subjects.last_unenrolment_at` (change `activity-privacy-hardening`, A2).

Built from scratch on the guarded test database; fictitious rows only. The backfill rule is the
one decided after looking at each environment: a subject that already holds conversations gets the
time of the migration (its history was possibly readable before the marker existed), a subject
without conversations stays null.
"""

import uuid
from datetime import datetime

from alembic import command
from sqlalchemy import text

from tests.db_support import alembic_config, drop_everything, guarded_engine
from tests.sql_support import insert_enrollment, insert_subject, insert_user, run, scalar


def column_exists(url: str) -> bool:
    return bool(
        scalar(
            url,
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'subjects' AND column_name = 'last_unenrolment_at')",
        )
    )


def test_upgrade_adds_a_nullable_timestamp_and_downgrade_removes_it(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0007")
    assert not column_exists(test_db_url)

    command.upgrade(config, "0008")

    assert column_exists(test_db_url)
    with guarded_engine(test_db_url) as engine, engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'subjects' AND column_name = 'last_unenrolment_at'"
            )
        ).one()
    assert tuple(row) == ("timestamp with time zone", "YES")

    command.downgrade(config, "0007")
    assert not column_exists(test_db_url)
    command.upgrade(config, "head")
    assert column_exists(test_db_url)  # re-upgrade works and leaves the database migrated


def test_the_backfill_marks_only_subjects_that_already_hold_conversations(
    test_db_url: str,
) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0007")
    teacher = insert_user(test_db_url, "teacher-migration@example.com", "teacher")
    student = insert_user(test_db_url, "student-migration@example.com")
    with_history = insert_subject(test_db_url, teacher, "With history")
    empty = insert_subject(test_db_url, teacher, "Empty")
    insert_enrollment(test_db_url, with_history, student)
    run(
        test_db_url,
        "INSERT INTO conversations (id, student_id, subject_id) VALUES (:id, :s, :j)",
        id=uuid.uuid4(),
        s=student,
        j=with_history,
    )
    before = scalar(test_db_url, "SELECT clock_timestamp()")

    command.upgrade(config, "0008")

    marked = scalar(
        test_db_url, "SELECT last_unenrolment_at FROM subjects WHERE id = :id", id=with_history
    )
    unmarked = scalar(
        test_db_url, "SELECT last_unenrolment_at FROM subjects WHERE id = :id", id=empty
    )
    assert isinstance(marked, datetime) and isinstance(before, datetime) and marked >= before
    assert unmarked is None
    drop_everything(test_db_url)
    command.upgrade(config, "head")  # leave the database migrated for the next module


def test_the_models_and_the_migrations_do_not_drift(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "head")

    command.check(config)  # raises when the models and the revisions disagree
