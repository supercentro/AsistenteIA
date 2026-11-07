"""A mixed-subject dataset for recall and plan checks, inserted in bulk by SQL.

One target subject holds a few dozen ready chunks that are *not* the nearest to the query of the
whole table; many other subjects hold chunks that are all nearer. The exact (Python, double
precision) ranking of the target subject is the reference every search is compared with.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text

from tests import embeddings as emb
from tests.db_support import guarded_engine
from tests.sql_support import insert_enrollment, insert_subject, insert_user


@dataclass(frozen=True)
class MixedDataset:
    teacher_id: uuid.UUID
    student_id: uuid.UUID
    target_subject: uuid.UUID
    other_subjects: tuple[uuid.UUID, ...]
    query: list[float]
    target_vectors: dict[
        int, list[float]
    ]  # chunk_index -> vector (the target subject's ready chunks)
    chunk_total: int


def _near_query(seed: int) -> list[float]:
    """A vector close to the query axis (angle 1 to 20 degrees): nearer than the target chunks."""
    degrees = 1.0 + (seed % 19)
    return emb.at_angle(0, 1 + (seed % 200), degrees)


def build_mixed_dataset(
    url: str,
    other_subject_count: int = 40,
    chunks_per_other_subject: int = 25,
    target_chunks: int = 60,
) -> MixedDataset:
    teacher = insert_user(url, f"mixed-teacher@{emb_domain()}", "teacher")
    student = insert_user(url, f"mixed-student@{emb_domain()}", "student")
    target = insert_subject(url, teacher, "Target")
    insert_enrollment(url, target, student)
    others = tuple(insert_subject(url, teacher, f"Other {i}") for i in range(other_subject_count))

    query = emb.basis(0)
    # target chunks lie 30 to 150 degrees away, never as near as any other subject's chunk
    target_vectors = {
        index: emb.at_angle(0, 300 + (index % 80), 30.0 + (index * 2.0))
        for index in range(target_chunks)
    }

    with guarded_engine(url) as engine, engine.begin() as conn:
        documents: list[dict[str, object]] = []
        chunks: list[dict[str, object]] = []

        def add_document(subject: uuid.UUID, filename: str, vectors: list[list[float]]) -> None:
            document_id = uuid.uuid4()
            documents.append({"id": document_id, "subject": subject, "filename": filename})
            for index, vector in enumerate(vectors):
                chunks.append(
                    {
                        "document": document_id,
                        "subject": subject,
                        "idx": index,
                        "page": index + 1,
                        "content": f"mixed chunk {filename} {index}",
                        "embedding": emb.to_literal(vector),
                    }
                )

        add_document(target, "target.pdf", [target_vectors[i] for i in range(target_chunks)])
        counter = 0
        for subject in others:
            vectors = []
            for _ in range(chunks_per_other_subject):
                vectors.append(_near_query(counter))
                counter += 1
            add_document(subject, "other.pdf", vectors)

        conn.execute(
            text(
                "INSERT INTO documents (id, subject_id, filename, content_type, size_bytes, "
                "status) "
                "VALUES (:id, :subject, :filename, 'application/pdf', 10, "
                "CAST('ready' AS document_status))"
            ),
            documents,
        )
        conn.execute(
            text(
                "INSERT INTO document_chunks (document_id, subject_id, chunk_index, page_number, "
                "content, embedding) VALUES (:document, :subject, :idx, :page, :content, "
                "CAST(:embedding AS vector))"
            ),
            chunks,
        )
        conn.execute(text("ANALYZE document_chunks"))
    return MixedDataset(
        teacher_id=teacher,
        student_id=student,
        target_subject=target,
        other_subjects=others,
        query=query,
        target_vectors=target_vectors,
        chunk_total=len(chunks),
    )


def emb_domain() -> str:
    return "fixtures.example.com"
