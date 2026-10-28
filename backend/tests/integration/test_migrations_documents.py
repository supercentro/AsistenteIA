"""Migration 0004: documents and document_chunks, verified from the PostgreSQL catalog.

`alembic check` does not compare index operator classes, WITH options or CHECK constraints
(spike incident I1), so those are asserted here from the catalog.
"""

from alembic import command
from sqlalchemy import text

from tests.db_support import alembic_config, drop_everything, guarded_engine
from tests.sql_support import count, insert_subject, insert_user


def fetch_all(url: str, sql: str, **params: object) -> list[tuple[object, ...]]:
    with guarded_engine(url) as engine, engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params)]


def table_exists(url: str, name: str) -> bool:
    return bool(fetch_all(url, "SELECT to_regclass(:n) IS NOT NULL", n=f"public.{name}")[0][0])


def type_exists(url: str, name: str) -> bool:
    return bool(fetch_all(url, "SELECT count(*) FROM pg_type WHERE typname = :n", n=name)[0][0])


def extension_installed(url: str) -> bool:
    return bool(fetch_all(url, "SELECT count(*) FROM pg_extension WHERE extname = 'vector'")[0][0])


def constraint_defs(url: str, table: str) -> dict[str, tuple[str, str]]:
    """name -> (type letter, definition)."""
    rows = fetch_all(
        url,
        "SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = to_regclass(:n)",
        n=f"public.{table}",
    )
    return {str(name): (str(kind), str(definition)) for name, kind, definition in rows}


def index_defs(url: str, table: str) -> dict[str, str]:
    rows = fetch_all(
        url,
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' AND tablename = :t",
        t=table,
    )
    return {str(name): str(definition) for name, definition in rows}


def columns(url: str, table: str) -> dict[str, tuple[str, str, str | None]]:
    """name -> (formatted type, nullable, default)."""
    rows = fetch_all(
        url,
        "SELECT a.attname, format_type(a.atttypid, a.atttypmod), "
        "CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE 'NULL' END, pg_get_expr(d.adbin, d.adrelid) "
        "FROM pg_attribute a LEFT JOIN pg_attrdef d "
        "ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
        "WHERE a.attrelid = to_regclass(:n) AND a.attnum > 0 AND NOT a.attisdropped",
        n=f"public.{table}",
    )
    return {str(r[0]): (str(r[1]), str(r[2]), None if r[3] is None else str(r[3])) for r in rows}


def migrate_to_head(url: str) -> None:
    drop_everything(url)
    command.upgrade(alembic_config(url), "head")


def test_enum_and_tables_exist_after_upgrade(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    assert table_exists(test_db_url, "documents")
    assert table_exists(test_db_url, "document_chunks")
    labels = fetch_all(
        test_db_url,
        "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
        "WHERE t.typname = 'document_status' ORDER BY e.enumsortorder",
    )
    assert [row[0] for row in labels] == ["pending", "processing", "ready", "failed"]


def test_documents_columns_types_and_defaults(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    cols = columns(test_db_url, "documents")
    assert cols["id"][:2] == ("uuid", "NOT NULL")
    assert cols["subject_id"][:2] == ("uuid", "NOT NULL")
    assert cols["filename"][:2] == ("character varying(255)", "NOT NULL")
    assert cols["content_type"][:2] == ("character varying(100)", "NOT NULL")
    assert cols["size_bytes"][:2] == ("bigint", "NOT NULL")
    assert cols["status"][:2] == ("document_status", "NOT NULL")
    assert cols["status"][2] is not None and "pending" in cols["status"][2]
    assert cols["error_message"][:2] == ("text", "NULL")
    assert cols["chunks_count"][:2] == ("integer", "NOT NULL")
    assert cols["chunks_count"][2] == "0"
    assert cols["created_at"][:2] == ("timestamp with time zone", "NOT NULL")
    assert cols["created_at"][2] == "now()"
    assert set(cols) == {
        "id",
        "subject_id",
        "filename",
        "content_type",
        "size_bytes",
        "status",
        "error_message",
        "chunks_count",
        "created_at",
    }


def test_chunk_columns_and_vector_dimension(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    cols = columns(test_db_url, "document_chunks")
    assert cols["embedding"][:2] == ("vector(384)", "NOT NULL")
    assert cols["content"][:2] == ("text", "NOT NULL")
    assert cols["chunk_index"][:2] == ("integer", "NOT NULL")
    assert cols["page_number"][:2] == ("integer", "NULL")
    assert cols["document_id"][:2] == ("uuid", "NOT NULL")
    assert cols["subject_id"][:2] == ("uuid", "NOT NULL")
    assert set(cols) == {
        "id",
        "document_id",
        "subject_id",
        "chunk_index",
        "page_number",
        "content",
        "embedding",
        "created_at",
    }


def test_constraint_names_types_and_definitions(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    documents = constraint_defs(test_db_url, "documents")
    assert documents["pk_documents"][0] == "p"
    assert documents["uq_documents_id"] == ("u", "UNIQUE (id, subject_id)")
    kind, definition = documents["fk_documents_subject_id_subjects"]
    assert kind == "f"
    assert definition == "FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE"
    assert documents["ck_documents_size_bytes_non_negative"][1] == "CHECK ((size_bytes >= 0))"
    assert documents["ck_documents_chunks_count_non_negative"][1] == "CHECK ((chunks_count >= 0))"

    chunks = constraint_defs(test_db_url, "document_chunks")
    assert chunks["pk_document_chunks"][0] == "p"
    assert chunks["uq_document_chunks_document_id"] == ("u", "UNIQUE (document_id, chunk_index)")
    assert chunks["fk_document_chunks_document_id_documents"] == (
        "f",
        "FOREIGN KEY (document_id, subject_id) REFERENCES documents(id, subject_id) "
        "ON DELETE CASCADE",
    )
    assert chunks["ck_document_chunks_chunk_index_non_negative"][1] == "CHECK ((chunk_index >= 0))"
    assert (
        chunks["ck_document_chunks_page_number_positive"][1]
        == "CHECK (((page_number IS NULL) OR (page_number >= 1)))"
    )
    assert chunks["ck_document_chunks_content_not_blank"][1] == r"CHECK ((content ~ '\S'::text))"
    norm = chunks["ck_document_chunks_embedding_norm_range"][1]
    assert "vector_norm(embedding) >= (0.000001)::double precision" in norm, norm
    assert "vector_norm(embedding) <= ('1000000'::numeric)::double precision" in norm, norm
    # no other constraint sneaks in
    assert {name for name, (kind, _) in chunks.items() if kind == "c"} == {
        "ck_document_chunks_chunk_index_non_negative",
        "ck_document_chunks_page_number_positive",
        "ck_document_chunks_content_not_blank",
        "ck_document_chunks_embedding_norm_range",
    }
    assert {name for name, (kind, _) in documents.items() if kind == "c"} == {
        "ck_documents_size_bytes_non_negative",
        "ck_documents_chunks_count_non_negative",
    }


def test_only_the_composite_foreign_key_links_chunks(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    chunks = constraint_defs(test_db_url, "document_chunks")
    assert [name for name, (kind, _) in chunks.items() if kind == "f"] == [
        "fk_document_chunks_document_id_documents"
    ]


def test_hnsw_index_uses_cosine_operator_class_and_default_parameters(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    definition = index_defs(test_db_url, "document_chunks")["ix_document_chunks_embedding"]
    assert "USING hnsw (embedding vector_cosine_ops)" in definition
    assert "m='16'" in definition
    assert "ef_construction='64'" in definition
    access_method = fetch_all(
        test_db_url,
        "SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam "
        "WHERE c.relname = 'ix_document_chunks_embedding'",
    )
    assert access_method == [("hnsw",)]


def test_btree_indexes_on_subject_columns(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    assert (
        "USING btree (subject_id)"
        in index_defs(test_db_url, "document_chunks")["ix_document_chunks_subject_id"]
    )
    assert (
        "USING btree (subject_id)"
        in index_defs(test_db_url, "documents")["ix_documents_subject_id"]
    )
    assert set(index_defs(test_db_url, "document_chunks")) == {
        "pk_document_chunks",
        "uq_document_chunks_document_id",
        "ix_document_chunks_subject_id",
        "ix_document_chunks_embedding",
    }


def test_alembic_check_reports_no_drift(test_db_url: str) -> None:
    migrate_to_head(test_db_url)

    command.check(alembic_config(test_db_url))  # raises CommandError when models and DB differ


def test_downgrade_removes_tables_and_enum_but_keeps_the_extension(test_db_url: str) -> None:
    migrate_to_head(test_db_url)
    config = alembic_config(test_db_url)

    command.downgrade(config, "-1")

    assert not table_exists(test_db_url, "documents")
    assert not table_exists(test_db_url, "document_chunks")
    assert not type_exists(test_db_url, "document_status")
    assert extension_installed(test_db_url)
    for name in ("users", "subjects", "enrollments"):
        assert table_exists(test_db_url, name)

    command.upgrade(config, "head")  # re-upgrade works and leaves the database migrated
    assert table_exists(test_db_url, "documents")
    assert type_exists(test_db_url, "document_status")


def test_upgrade_from_0003_leaves_existing_rows_unchanged(test_db_url: str) -> None:
    drop_everything(test_db_url)
    config = alembic_config(test_db_url)
    command.upgrade(config, "0003")
    teacher = insert_user(test_db_url, "teacher-0004@example.com", "teacher")
    student = insert_user(test_db_url, "student-0004@example.com", "student")
    subject = insert_subject(test_db_url, teacher)
    before = fetch_all(
        test_db_url,
        "SELECT (SELECT md5(string_agg(u::text, '|' ORDER BY u.id)) FROM users u), "
        "(SELECT md5(string_agg(s::text, '|' ORDER BY s.id)) FROM subjects s)",
    )

    command.upgrade(config, "head")

    after = fetch_all(
        test_db_url,
        "SELECT (SELECT md5(string_agg(u::text, '|' ORDER BY u.id)) FROM users u), "
        "(SELECT md5(string_agg(s::text, '|' ORDER BY s.id)) FROM subjects s)",
    )
    assert before == after
    assert count(test_db_url, "users") == 2
    assert count(test_db_url, "subjects", "id = :id", id=subject) == 1
    assert student != teacher
    assert count(test_db_url, "documents") == 0
    assert count(test_db_url, "document_chunks") == 0
