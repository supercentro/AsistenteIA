"""Migration 0005: `ingestion_jobs` and `documents.error_code`, verified from the catalog.

As for 0004, `alembic check` does not see CHECK constraints or partial-index predicates, so they are
asserted here from the catalog.
"""

import hashlib
import uuid
from pathlib import Path

from alembic import command
from alembic.script import ScriptDirectory

from tests.db_support import BACKEND_DIR, alembic_config, drop_everything
from tests.integration.test_migrations_documents import (
    columns,
    constraint_defs,
    fetch_all,
    index_defs,
    migrate_to_head,
    table_exists,
)
from tests.sql_support import count, insert_document, insert_subject, insert_user, run

# SHA-256 of migration 0004 as published in `main` (commit 3960132), line endings normalised to
# LF so a Windows checkout with CRLF gives the same value. A merged migration is never edited.
MIGRATION_0004_SHA256 = "30a47018e7d026eaac5146f6c0c01801a5b7e35bfd6ee3f86108599d4e5f32f9"
JOB_TABLE_COLUMNS = {
    "id",
    "document_id",
    "payload",
    "attempts",
    "locked_by",
    "locked_until",
    "available_at",
    "created_at",
    "updated_at",
}


def catalog_snapshot(url: str) -> dict[str, object]:
    return {
        table: (
            columns(url, table),
            constraint_defs(url, table),
            index_defs(url, table),
        )
        for table in ("documents", "ingestion_jobs")
    }


def test_revision_chain_ends_in_0005_after_0004() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql+psycopg://x/y_test"))

    assert script.get_heads() == ["0005"]
    revision = script.get_revision("0005")
    assert revision is not None
    assert revision.down_revision == "0004"


def test_migration_0004_is_unchanged_from_main() -> None:
    path = next((BACKEND_DIR / "alembic" / "versions").glob("0004_*.py"))

    content = Path(path).read_bytes().replace(b"\r\n", b"\n")

    assert hashlib.sha256(content).hexdigest() == MIGRATION_0004_SHA256


def test_ingestion_jobs_columns_types_and_defaults(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    cols = columns(test_db_url, "ingestion_jobs")
    assert set(cols) == JOB_TABLE_COLUMNS
    assert cols["id"][:2] == ("uuid", "NOT NULL")
    assert cols["id"][2] is not None and "gen_random_uuid()" in cols["id"][2]
    assert cols["document_id"][:2] == ("uuid", "NOT NULL")
    assert cols["payload"][:2] == ("bytea", "NULL")
    assert cols["attempts"][:2] == ("integer", "NOT NULL")
    assert cols["attempts"][2] == "0"
    assert cols["locked_by"][:2] == ("character varying(64)", "NULL")
    assert cols["locked_until"][:2] == ("timestamp with time zone", "NULL")
    assert cols["available_at"][:2] == ("timestamp with time zone", "NOT NULL")
    assert cols["available_at"][2] == "now()"
    assert cols["created_at"][:2] == ("timestamp with time zone", "NOT NULL")
    assert cols["created_at"][2] == "now()"
    assert cols["updated_at"][:2] == ("timestamp with time zone", "NOT NULL")
    assert cols["updated_at"][2] == "now()"


def test_ingestion_jobs_constraints(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    jobs = constraint_defs(test_db_url, "ingestion_jobs")
    assert jobs["pk_ingestion_jobs"][0] == "p"
    assert jobs["uq_ingestion_jobs_document_id"] == ("u", "UNIQUE (document_id)")
    assert jobs["fk_ingestion_jobs_document_id_documents"] == (
        "f",
        "FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE",
    )
    assert jobs["ck_ingestion_jobs_attempts_non_negative"][1] == "CHECK ((attempts >= 0))"
    assert (
        jobs["ck_ingestion_jobs_lease_consistent"][1]
        == "CHECK (((locked_by IS NULL) = (locked_until IS NULL)))"
    )
    assert {name for name, (kind, _) in jobs.items() if kind == "c"} == {
        "ck_ingestion_jobs_attempts_non_negative",
        "ck_ingestion_jobs_lease_consistent",
    }
    assert [name for name, (kind, _) in jobs.items() if kind == "f"] == [
        "fk_ingestion_jobs_document_id_documents"
    ]


def test_claimable_jobs_have_a_partial_index(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    indexes = index_defs(test_db_url, "ingestion_jobs")
    assert set(indexes) == {
        "pk_ingestion_jobs",
        "uq_ingestion_jobs_document_id",
        "ix_ingestion_jobs_claimable",
    }
    definition = indexes["ix_ingestion_jobs_claimable"]
    assert "USING btree (available_at)" in definition
    assert "WHERE (payload IS NOT NULL)" in definition


def test_documents_gain_a_nullable_error_code_with_a_check(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    cols = columns(test_db_url, "documents")
    assert cols["error_code"] == ("character varying(40)", "NULL", None)
    assert "error_message" in cols and "status" in cols
    documents = constraint_defs(test_db_url, "documents")
    assert documents["ck_documents_error_code_only_when_failed"][1] == (
        "CHECK (((error_code IS NULL) OR (status = 'failed'::document_status)))"
    )
    assert {name for name, (kind, _) in documents.items() if kind == "c"} == {
        "ck_documents_size_bytes_non_negative",
        "ck_documents_chunks_count_non_negative",
        "ck_documents_error_code_only_when_failed",
    }


def test_alembic_check_reports_no_drift(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    command.check(alembic_config(test_db_url))  # raises CommandError when models and DB differ


def test_downgrade_to_0004_drops_the_table_and_the_column_only(test_db_url: str) -> None:
    migrate_to_head(test_db_url)
    config = alembic_config(test_db_url)

    command.downgrade(config, "0004")

    assert not table_exists(test_db_url, "ingestion_jobs")
    assert "error_code" not in columns(test_db_url, "documents")
    assert "ck_documents_error_code_only_when_failed" not in constraint_defs(
        test_db_url, "documents"
    )
    for name in ("users", "subjects", "enrollments", "documents", "document_chunks"):
        assert table_exists(test_db_url, name)
    revision = fetch_all(test_db_url, "SELECT version_num FROM alembic_version")
    assert revision == [("0004",)]


def test_round_trip_leaves_the_same_catalog(test_db_url: str) -> None:
    migrate_to_head(test_db_url)
    first = catalog_snapshot(test_db_url)
    config = alembic_config(test_db_url)

    command.downgrade(config, "0004")
    command.upgrade(config, "head")

    assert catalog_snapshot(test_db_url) == first
    command.check(config)


def test_downgrade_keeps_ready_documents_and_their_chunks(test_db_url: str) -> None:
    from tests.sql_support import insert_chunk

    migrate_to_head(test_db_url)
    teacher = insert_user(test_db_url, "teacher-0005@example.com", "teacher")
    subject = insert_subject(test_db_url, teacher)
    ready = insert_document(test_db_url, subject, "ready.pdf", "ready")
    insert_chunk(test_db_url, ready, subject)
    failed = insert_document(test_db_url, subject, "failed.pdf", "failed")
    run(
        test_db_url,
        "UPDATE documents SET error_code = 'CORRUPT_FILE' WHERE id = :id",
        id=failed,
    )
    pending = insert_document(test_db_url, subject, "pending.pdf", "pending")
    run(
        test_db_url,
        "INSERT INTO ingestion_jobs (document_id, payload) VALUES (:id, :payload)",
        id=pending,
        payload=b"%PDF-1.7 bytes",
    )

    command.downgrade(alembic_config(test_db_url), "0004")

    assert count(test_db_url, "documents") == 3
    assert count(test_db_url, "document_chunks") == 1
    assert count(test_db_url, "documents", "id = :id AND status = 'ready'", id=ready) == 1


def test_upgrade_from_0004_leaves_existing_rows_unchanged(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0004")
    teacher = insert_user(test_db_url, "teacher-up@example.com", "teacher")
    subject = insert_subject(test_db_url, teacher)
    from tests.sql_support import insert_chunk

    for status in ("pending", "processing", "ready", "failed"):
        document = insert_document(test_db_url, subject, f"{status}.pdf", status)
        if status == "ready":
            insert_chunk(test_db_url, document, subject)
    query = (
        "SELECT md5(string_agg(d::text, '|' ORDER BY d.id)) FROM "
        "(SELECT id, subject_id, filename, content_type, size_bytes, status, error_message, "
        "chunks_count, created_at FROM documents) d"
    )
    before = fetch_all(test_db_url, query)

    command.upgrade(config, "head")

    assert fetch_all(test_db_url, query) == before
    assert count(test_db_url, "documents") == 4
    assert count(test_db_url, "document_chunks") == 1
    assert count(test_db_url, "documents", "error_code IS NULL") == 4
    assert count(test_db_url, "ingestion_jobs") == 0


def test_job_defaults_are_filled_by_the_database(test_db_url: str) -> None:
    migrate_to_head(test_db_url)
    teacher = insert_user(test_db_url, "teacher-defaults@example.com", "teacher")
    subject = insert_subject(test_db_url, teacher)
    document = insert_document(test_db_url, subject, "d.pdf", "pending")

    run(test_db_url, "INSERT INTO ingestion_jobs (document_id) VALUES (:id)", id=document)

    with_row = fetch_all(
        test_db_url,
        "SELECT attempts, locked_by, locked_until, payload, id IS NOT NULL, "
        "available_at IS NOT NULL, created_at IS NOT NULL, updated_at IS NOT NULL "
        "FROM ingestion_jobs",
    )
    assert with_row == [(0, None, None, None, True, True, True, True)]
    job_id = fetch_all(test_db_url, "SELECT id FROM ingestion_jobs")[0][0]
    assert isinstance(uuid.UUID(str(job_id)), uuid.UUID)
