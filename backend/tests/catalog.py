"""A small multi-subject dataset inserted by SQL, with embeddings whose similarities are known.

Layout (query direction = axis 0):

    teacher_one owns Algebra and Physics, teacher_two owns Chemistry
    student_both: Algebra + Physics   student_algebra: Algebra   student_unenrolled: nothing
    Algebra   algebra-ready.pdf (ready): six chunks at 10, 30, 45, 60, 90 and 180 degrees
              algebra-pending / -processing / -failed.pdf: one chunk each, exactly on the query
    Physics   physics.pdf (ready): one chunk on the query and one at 5 degrees
    Chemistry chemistry.pdf (ready): one chunk on the query

Physics and Chemistry therefore hold chunks nearer to the query than any ready Algebra chunk, and
Algebra holds chunks of documents that are not ready: the traps that retrieval tests must resist.
"""

import uuid
from dataclasses import dataclass

from tests import embeddings as emb
from tests.sql_support import (
    insert_chunk,
    insert_document,
    insert_enrollment,
    insert_subject,
    insert_user,
)

EMAIL_DOMAIN = "fixtures.example.com"


@dataclass(frozen=True)
class ExpectedHit:
    filename: str
    chunk_index: int
    similarity: float


@dataclass(frozen=True)
class Catalog:
    teacher_one: uuid.UUID
    teacher_two: uuid.UUID
    student_both: uuid.UUID
    student_algebra: uuid.UUID
    student_unenrolled: uuid.UUID
    algebra: uuid.UUID
    physics: uuid.UUID
    chemistry: uuid.UUID
    documents: dict[str, uuid.UUID]
    query: list[float]
    algebra_ready_ranking: tuple[ExpectedHit, ...]
    chunk_count: int


def build_catalog(url: str) -> Catalog:
    """Insert the dataset into an empty, migrated test database."""
    teacher_one = insert_user(url, f"teacher-one@{EMAIL_DOMAIN}", "teacher")
    teacher_two = insert_user(url, f"teacher-two@{EMAIL_DOMAIN}", "teacher")
    student_both = insert_user(url, f"student-both@{EMAIL_DOMAIN}", "student")
    student_algebra = insert_user(url, f"student-algebra@{EMAIL_DOMAIN}", "student")
    student_unenrolled = insert_user(url, f"student-unenrolled@{EMAIL_DOMAIN}", "student")

    algebra = insert_subject(url, teacher_one, "Algebra")
    physics = insert_subject(url, teacher_one, "Physics")
    chemistry = insert_subject(url, teacher_two, "Chemistry")
    insert_enrollment(url, algebra, student_both)
    insert_enrollment(url, physics, student_both)
    insert_enrollment(url, algebra, student_algebra)

    query = emb.basis(0)
    documents: dict[str, uuid.UUID] = {}
    chunk_count = 0

    def add_document(
        subject: uuid.UUID, filename: str, status: str, vectors: list[list[float]]
    ) -> None:
        nonlocal chunk_count
        document = insert_document(url, subject, filename, status)
        documents[filename] = document
        for index, vector in enumerate(vectors):
            insert_chunk(
                url,
                document,
                subject,
                chunk_index=index,
                embedding=emb.to_literal(vector),
                content=f"fixture chunk {filename} {index}",
                page_number=index + 1,
            )
            chunk_count += 1

    ranking_vectors = [
        emb.at_angle(0, 1, 10),
        emb.at_angle(0, 1, 30),
        emb.at_angle(0, 1, 45),
        emb.at_angle(0, 1, 60),
        emb.basis(1),  # orthogonal
        emb.negate(emb.basis(0)),  # opposite
    ]
    add_document(algebra, "algebra-ready.pdf", "ready", ranking_vectors)
    for status in ("pending", "processing", "failed"):
        add_document(algebra, f"algebra-{status}.pdf", status, [emb.basis(0)])
    add_document(physics, "physics.pdf", "ready", [emb.basis(0), emb.at_angle(0, 2, 5)])
    add_document(chemistry, "chemistry.pdf", "ready", [emb.basis(0)])

    ranking = tuple(
        ExpectedHit("algebra-ready.pdf", index, emb.cosine_similarity(query, vector))
        for index, vector in enumerate(ranking_vectors)
    )
    return Catalog(
        teacher_one=teacher_one,
        teacher_two=teacher_two,
        student_both=student_both,
        student_algebra=student_algebra,
        student_unenrolled=student_unenrolled,
        algebra=algebra,
        physics=physics,
        chemistry=chemistry,
        documents=documents,
        query=query,
        algebra_ready_ranking=ranking,
        chunk_count=chunk_count,
    )
