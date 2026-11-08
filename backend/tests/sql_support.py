"""Raw-SQL helpers for storage tests: users, subjects, documents and chunks without repositories.

Rows are inserted by SQL on purpose: the write repositories belong to later changes, and these tests
must exercise the database constraints themselves. Embeddings are deterministic; no model is used.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text

from tests.db_support import guarded_engine

DIM = 384


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(value) for value in values) + "]"


def unit_vector(index: int, scale: float = 1.0, dim: int = DIM) -> str:
    """Vector literal with one component equal to `scale` (norm == scale) at `index`."""
    values = [0.0] * dim
    values[index] = scale
    return vector_literal(values)


def uniform_vector(value: float, dim: int = DIM) -> str:
    return vector_literal([value] * dim)


def run(url: str, sql: str, **params: object) -> None:
    with guarded_engine(url) as engine, engine.connect() as conn:
        conn.execute(text(sql), params)


def scalar(url: str, sql: str, **params: object) -> object:
    with guarded_engine(url) as engine, engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def count(url: str, table: str, where: str = "true", **params: object) -> int:
    # `table` and `where` are fixed strings written by the tests, never user input.
    value = scalar(url, "SELECT count(*) FROM " + table + " WHERE " + where, **params)  # noqa: S608
    assert isinstance(value, int)
    return value


@dataclass(frozen=True)
class Seed:
    teacher_id: uuid.UUID
    student_id: uuid.UUID
    subject_id: uuid.UUID
    document_id: uuid.UUID


def insert_user(url: str, email: str, role: str = "student") -> uuid.UUID:
    user_id = uuid.uuid4()
    run(
        url,
        "INSERT INTO users (id, name, email, password_hash, role) "
        "VALUES (:id, 'Test', :email, 'not-a-real-hash', CAST(:role AS user_role))",
        id=user_id,
        email=email,
        role=role,
    )
    return user_id


def insert_subject(url: str, teacher_id: uuid.UUID, name: str = "Algebra") -> uuid.UUID:
    subject_id = uuid.uuid4()
    run(
        url,
        "INSERT INTO subjects (id, name, teacher_id) VALUES (:id, :name, :teacher)",
        id=subject_id,
        name=name,
        teacher=teacher_id,
    )
    return subject_id


def insert_enrollment(url: str, subject_id: uuid.UUID, student_id: uuid.UUID) -> None:
    run(
        url,
        "INSERT INTO enrollments (subject_id, student_id) VALUES (:subject, :student)",
        subject=subject_id,
        student=student_id,
    )


def insert_document(
    url: str, subject_id: uuid.UUID, filename: str = "notes.pdf", status: str = "ready"
) -> uuid.UUID:
    document_id = uuid.uuid4()
    run(
        url,
        "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, status) "
        "VALUES (:id, :subject, :filename, 'application/pdf', 10, "
        "CAST(:status AS document_status))",
        id=document_id,
        subject=subject_id,
        filename=filename,
        status=status,
    )
    return document_id


def insert_chunk(
    url: str,
    document_id: uuid.UUID,
    subject_id: uuid.UUID,
    chunk_index: int = 0,
    embedding: str | None = None,
    content: str = "chunk text",
    page_number: int | None = 1,
) -> None:
    run(
        url,
        "INSERT INTO document_chunks (document_id, subject_id, chunk_index, page_number, content, "
        "embedding) VALUES (:document, :subject, :idx, :page, :content, "
        "CAST(:embedding AS vector))",
        document=document_id,
        subject=subject_id,
        idx=chunk_index,
        page=page_number,
        content=content,
        embedding=embedding if embedding is not None else unit_vector(chunk_index % DIM),
    )


def seed_basic(url: str) -> Seed:
    """Teacher, enrolled student, one subject and one ready document (no chunks)."""
    teacher = insert_user(url, f"t-{uuid.uuid4().hex[:8]}@example.com", "teacher")
    student = insert_user(url, f"s-{uuid.uuid4().hex[:8]}@example.com", "student")
    subject = insert_subject(url, teacher)
    insert_enrollment(url, subject, student)
    return Seed(teacher, student, subject, insert_document(url, subject))
