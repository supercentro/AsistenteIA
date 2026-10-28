"""Scenarios of the `document-storage` spec, exercised on a real PostgreSQL with pgvector."""

import uuid

import pytest
from sqlalchemy.exc import DataError, IntegrityError

from tests.sql_support import (
    DIM,
    count,
    insert_chunk,
    insert_document,
    insert_enrollment,
    insert_subject,
    insert_user,
    run,
    scalar,
    seed_basic,
    uniform_vector,
    unit_vector,
    vector_literal,
)

CHECK_VIOLATION = "ck_document_chunks_embedding_norm_range"


# ---------------------------------------------------------------- embeddings


def test_valid_embedding_is_stored_and_read_back(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=unit_vector(3, 1.0))

    assert count(clean_db, "document_chunks") == 1
    assert scalar(clean_db, "SELECT vector_dims(embedding) FROM document_chunks") == DIM
    assert scalar(clean_db, "SELECT vector_norm(embedding) FROM document_chunks") == 1.0


@pytest.mark.parametrize("dimension", [0, 1, 383, 385])
def test_wrong_dimension_is_rejected(clean_db: str, dimension: int) -> None:
    seed = seed_basic(clean_db)
    literal = vector_literal([0.5] * dimension)

    with pytest.raises(DataError):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=literal)

    assert count(clean_db, "document_chunks") == 0


def test_missing_embedding_is_rejected(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError):
        run(
            clean_db,
            "INSERT INTO document_chunks (document_id, subject_id, chunk_index, content) "
            "VALUES (:d, :s, 0, 'text')",
            d=seed.document_id,
            s=seed.subject_id,
        )


def test_zero_vector_is_rejected_by_the_norm_check(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError) as raised:
        insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=uniform_vector(0.0))

    assert CHECK_VIOLATION in str(raised.value.orig)
    assert count(clean_db, "document_chunks") == 0


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_values_are_rejected(clean_db: str, token: str) -> None:
    seed = seed_basic(clean_db)
    literal = "[" + token + "," + ",".join(["0"] * (DIM - 1)) + "]"

    with pytest.raises(DataError):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=literal)


@pytest.mark.parametrize("scale", [5e-7, 1e-7, 1e-30, 2e6, 1e7, 1e38])
def test_magnitude_outside_the_reliable_range_is_rejected_on_insert(
    clean_db: str, scale: float
) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError) as raised:
        insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=unit_vector(0, scale))

    assert CHECK_VIOLATION in str(raised.value.orig)
    assert count(clean_db, "document_chunks") == 0


@pytest.mark.parametrize("scale", [1.5e-6, 1e-3, 1.0, 15.0, 9e5])
def test_magnitude_inside_the_reliable_range_is_accepted(clean_db: str, scale: float) -> None:
    seed = seed_basic(clean_db)

    insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=unit_vector(0, scale))

    assert count(clean_db, "document_chunks") == 1


def test_update_to_zero_or_out_of_range_is_rejected(clean_db: str) -> None:
    seed = seed_basic(clean_db)
    insert_chunk(clean_db, seed.document_id, seed.subject_id, embedding=unit_vector(0))

    for literal in (uniform_vector(0.0), unit_vector(0, 1e38)):
        with pytest.raises(IntegrityError):
            run(
                clean_db,
                "UPDATE document_chunks SET embedding = CAST(:e AS vector)",
                e=literal,
            )
    assert scalar(clean_db, "SELECT vector_norm(embedding) FROM document_chunks") == 1.0


# ------------------------------------------------------------- subject coupling


def test_consistent_chunk_is_stored(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    insert_chunk(clean_db, seed.document_id, seed.subject_id)

    assert count(clean_db, "document_chunks") == 1


def test_chunk_with_another_subject_than_its_document_is_rejected(clean_db: str) -> None:
    seed = seed_basic(clean_db)
    other_subject = insert_subject(clean_db, seed.teacher_id, "Geometry")

    with pytest.raises(IntegrityError) as raised:
        insert_chunk(clean_db, seed.document_id, other_subject)

    assert "fk_document_chunks_document_id_documents" in str(raised.value.orig)
    assert count(clean_db, "document_chunks") == 0


def test_chunk_of_a_missing_document_is_rejected(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError):
        insert_chunk(clean_db, uuid.uuid4(), seed.subject_id)


def test_document_subject_cannot_change_while_chunks_exist(clean_db: str) -> None:
    seed = seed_basic(clean_db)
    other_subject = insert_subject(clean_db, seed.teacher_id, "Geometry")
    insert_chunk(clean_db, seed.document_id, seed.subject_id)

    with pytest.raises(IntegrityError):
        run(
            clean_db,
            "UPDATE documents SET subject_id = :s WHERE id = :d",
            s=other_subject,
            d=seed.document_id,
        )

    assert (
        scalar(clean_db, "SELECT subject_id FROM documents WHERE id = :d", d=seed.document_id)
        == seed.subject_id
    )


def test_document_subject_can_change_when_it_has_no_chunks(clean_db: str) -> None:
    # Documents never change subject in the MVP; the composite key only protects existing chunks.
    seed = seed_basic(clean_db)
    other_subject = insert_subject(clean_db, seed.teacher_id, "Geometry")

    run(
        clean_db,
        "UPDATE documents SET subject_id = :s WHERE id = :d",
        s=other_subject,
        d=seed.document_id,
    )


# ------------------------------------------------------------------- cascades


def test_deleting_a_document_deletes_only_its_chunks(clean_db: str) -> None:
    seed = seed_basic(clean_db)
    other_document = insert_document(clean_db, seed.subject_id, "other.pdf")
    for index in range(3):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, index)
        insert_chunk(clean_db, other_document, seed.subject_id, index)

    run(clean_db, "DELETE FROM documents WHERE id = :d", d=seed.document_id)

    assert count(clean_db, "document_chunks", "document_id = :d", d=seed.document_id) == 0
    assert count(clean_db, "document_chunks", "document_id = :d", d=other_document) == 3
    assert count(clean_db, "documents") == 1


def test_deleting_a_subject_deletes_documents_and_chunks_only_of_that_subject(
    clean_db: str,
) -> None:
    seed = seed_basic(clean_db)
    other_teacher = insert_user(clean_db, "other-teacher@example.com", "teacher")
    other_subject = insert_subject(clean_db, other_teacher, "Physics")
    other_student = insert_user(clean_db, "other-student@example.com", "student")
    insert_enrollment(clean_db, other_subject, other_student)
    other_document = insert_document(clean_db, other_subject)
    for index in range(300):  # a few hundred chunks in one cascade
        insert_chunk(clean_db, seed.document_id, seed.subject_id, index)
    for index in range(5):
        insert_chunk(clean_db, other_document, other_subject, index)

    run(clean_db, "DELETE FROM subjects WHERE id = :s", s=seed.subject_id)

    assert count(clean_db, "documents", "subject_id = :s", s=seed.subject_id) == 0
    assert count(clean_db, "document_chunks", "subject_id = :s", s=seed.subject_id) == 0
    assert count(clean_db, "document_chunks", "subject_id = :s", s=other_subject) == 5
    assert count(clean_db, "documents", "subject_id = :s", s=other_subject) == 1
    assert count(clean_db, "enrollments", "subject_id = :s", s=other_subject) == 1
    assert count(clean_db, "users") == 4


def test_teacher_who_owns_subjects_with_documents_stays_protected(clean_db: str) -> None:
    seed = seed_basic(clean_db)
    insert_chunk(clean_db, seed.document_id, seed.subject_id)

    with pytest.raises(IntegrityError):
        run(clean_db, "DELETE FROM users WHERE id = :t", t=seed.teacher_id)

    assert count(clean_db, "users", "id = :t", t=seed.teacher_id) == 1
    assert count(clean_db, "document_chunks") == 1


# ------------------------------------------------------------- integrity checks


@pytest.mark.parametrize(
    ("column", "value"),
    [("size_bytes", -1), ("chunks_count", -1)],
)
def test_negative_document_numbers_are_rejected(clean_db: str, column: str, value: int) -> None:
    seed = seed_basic(clean_db)
    sql = {
        "size_bytes": "UPDATE documents SET size_bytes = :v WHERE id = :d",
        "chunks_count": "UPDATE documents SET chunks_count = :v WHERE id = :d",
    }[column]

    with pytest.raises(IntegrityError):
        run(clean_db, sql, v=value, d=seed.document_id)


def test_negative_chunk_index_is_rejected(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, chunk_index=-1)


@pytest.mark.parametrize("page", [0, -3])
def test_page_number_below_one_is_rejected_and_null_is_allowed(clean_db: str, page: int) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, page_number=page)
    insert_chunk(clean_db, seed.document_id, seed.subject_id, page_number=None)
    assert count(clean_db, "document_chunks") == 1


@pytest.mark.parametrize("content", ["", "   ", "\n\t "])
def test_blank_content_is_rejected(clean_db: str, content: str) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(IntegrityError):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, content=content)


def test_duplicate_chunk_index_in_one_document_is_rejected_but_not_across_documents(
    clean_db: str,
) -> None:
    seed = seed_basic(clean_db)
    other_document = insert_document(clean_db, seed.subject_id, "other.pdf")
    insert_chunk(clean_db, seed.document_id, seed.subject_id, chunk_index=0)

    with pytest.raises(IntegrityError):
        insert_chunk(clean_db, seed.document_id, seed.subject_id, chunk_index=0)
    insert_chunk(clean_db, other_document, seed.subject_id, chunk_index=0)

    assert count(clean_db, "document_chunks") == 2


def test_invalid_status_is_rejected(clean_db: str) -> None:
    seed = seed_basic(clean_db)

    with pytest.raises(DataError):
        insert_document(clean_db, seed.subject_id, status="archived")


@pytest.mark.parametrize("status", ["pending", "processing", "ready", "failed"])
def test_every_status_value_is_accepted(clean_db: str, status: str) -> None:
    seed = seed_basic(clean_db)

    insert_document(clean_db, seed.subject_id, status=status)


def test_defaults_are_applied_by_the_database(clean_db: str) -> None:
    seed = seed_basic(clean_db)
    document_id = uuid.uuid4()

    run(
        clean_db,
        "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes) "
        "VALUES (:id, :s, 'a.txt', 'text/plain', 0)",
        id=document_id,
        s=seed.subject_id,
    )

    assert scalar(clean_db, "SELECT status::text FROM documents WHERE id = :i", i=document_id) == (
        "pending"
    )
    assert scalar(clean_db, "SELECT chunks_count FROM documents WHERE id = :i", i=document_id) == 0
    assert (
        scalar(clean_db, "SELECT error_message FROM documents WHERE id = :i", i=document_id) is None
    )
    created = scalar(clean_db, "SELECT created_at FROM documents WHERE id = :i", i=document_id)
    assert created is not None
