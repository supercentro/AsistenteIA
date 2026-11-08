"""The multi-subject fixture catalog: structure, isolation facts and database-side similarities."""

import pytest
from sqlalchemy import text

from tests import embeddings as emb
from tests.catalog import Catalog, build_catalog
from tests.db_support import guarded_engine, truncate_all
from tests.sql_support import count, scalar


def rows(url: str, sql: str, **params: object) -> list[tuple[object, ...]]:
    with guarded_engine(url) as engine, engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params)]


@pytest.fixture
def catalog(clean_db: str) -> Catalog:
    return build_catalog(clean_db)


def test_catalog_has_several_teachers_students_and_subjects(
    clean_db: str, catalog: Catalog
) -> None:
    assert count(clean_db, "users", "role = 'teacher'") == 2
    assert count(clean_db, "users", "role = 'student'") == 3
    assert count(clean_db, "subjects") == 3
    assert {s for s in (catalog.algebra, catalog.physics, catalog.chemistry)} == {
        row[0] for row in rows(clean_db, "SELECT id FROM subjects")
    }
    assert count(clean_db, "subjects", "teacher_id = :t", t=catalog.teacher_one) == 2
    assert count(clean_db, "subjects", "teacher_id = :t", t=catalog.teacher_two) == 1


def test_enrollments_cover_enrolled_partially_enrolled_and_unenrolled_students(
    clean_db: str, catalog: Catalog
) -> None:
    def subjects_of(student: object) -> set[object]:
        found = rows(
            clean_db, "SELECT subject_id FROM enrollments WHERE student_id = :s", s=student
        )
        return {row[0] for row in found}

    assert subjects_of(catalog.student_both) == {catalog.algebra, catalog.physics}
    assert subjects_of(catalog.student_algebra) == {catalog.algebra}
    assert subjects_of(catalog.student_unenrolled) == set()
    assert count(clean_db, "enrollments", "subject_id = :s", s=catalog.chemistry) == 0


def test_documents_cover_every_status_and_belong_to_their_subject(
    clean_db: str, catalog: Catalog
) -> None:
    statuses = {
        str(name): str(status)
        for name, status in rows(clean_db, "SELECT filename, status::text FROM documents")
    }
    assert statuses == {
        "algebra-ready.pdf": "ready",
        "algebra-pending.pdf": "pending",
        "algebra-processing.pdf": "processing",
        "algebra-failed.pdf": "failed",
        "physics.pdf": "ready",
        "chemistry.pdf": "ready",
    }
    for filename, subject in (
        ("algebra-ready.pdf", catalog.algebra),
        ("physics.pdf", catalog.physics),
        ("chemistry.pdf", catalog.chemistry),
    ):
        assert (
            scalar(clean_db, "SELECT subject_id FROM documents WHERE filename = :f", f=filename)
            == subject
        )


def test_every_chunk_carries_its_documents_subject_and_a_valid_embedding(
    clean_db: str, catalog: Catalog
) -> None:
    assert count(clean_db, "document_chunks") == catalog.chunk_count
    mismatched = scalar(
        clean_db,
        "SELECT count(*) FROM document_chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.subject_id <> d.subject_id",
    )
    assert mismatched == 0
    assert scalar(clean_db, "SELECT min(vector_dims(embedding)) FROM document_chunks") == 384
    low, high = rows(
        clean_db,
        "SELECT min(vector_norm(embedding)), max(vector_norm(embedding)) FROM document_chunks",
    )[0]
    assert float(low) == pytest.approx(1.0, abs=1e-6)  # type: ignore[arg-type]
    assert float(high) == pytest.approx(1.0, abs=1e-6)  # type: ignore[arg-type]


def test_database_similarities_match_the_documented_values(clean_db: str, catalog: Catalog) -> None:
    found = rows(
        clean_db,
        "SELECT d.filename, c.chunk_index, 1 - (c.embedding <=> CAST(:q AS vector)) "
        "FROM document_chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.filename = 'algebra-ready.pdf' ORDER BY 3 DESC, c.chunk_index",
        q=emb.to_literal(catalog.query),
    )
    assert [(str(f), int(str(i))) for f, i, _ in found] == [
        (hit.filename, hit.chunk_index) for hit in catalog.algebra_ready_ranking
    ]
    for (_, _, similarity), hit in zip(found, catalog.algebra_ready_ranking, strict=True):
        assert float(similarity) == pytest.approx(hit.similarity, abs=1e-6)  # type: ignore[arg-type]


def test_expected_ranking_is_strictly_descending_and_documented_in_python(
    catalog: Catalog,
) -> None:
    similarities = [hit.similarity for hit in catalog.algebra_ready_ranking]
    assert similarities == sorted(similarities, reverse=True)
    assert len(set(similarities)) == len(similarities)  # no ties: the order is unambiguous
    assert similarities[0] == pytest.approx(
        emb.cosine_similarity(emb.basis(0), emb.at_angle(0, 1, 10))
    )
    assert similarities[-1] == pytest.approx(-1.0)


def test_other_subjects_hold_chunks_nearer_to_the_query_than_any_algebra_chunk(
    clean_db: str, catalog: Catalog
) -> None:
    """A search over the whole table would be polluted: nearer chunks exist outside Algebra."""
    q = emb.to_literal(catalog.query)

    def best(subject: object) -> float:
        value = scalar(
            clean_db,
            "SELECT max(1 - (embedding <=> CAST(:q AS vector))) FROM document_chunks "
            "WHERE subject_id = :s",
            q=q,
            s=subject,
        )
        return float(value)  # type: ignore[arg-type]

    algebra_best = max(hit.similarity for hit in catalog.algebra_ready_ranking)
    # the pending, processing and failed Algebra documents also hold the exact query direction
    assert best(catalog.algebra) == pytest.approx(1.0, abs=1e-6)
    assert best(catalog.physics) == pytest.approx(1.0, abs=1e-6)
    assert best(catalog.chemistry) == pytest.approx(1.0, abs=1e-6)
    assert algebra_best < 0.99  # even the best READY Algebra chunk is farther than those
    nearest_ready = rows(
        clean_db,
        "SELECT c.subject_id FROM document_chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.status = 'ready' ORDER BY c.embedding <=> CAST(:q AS vector), c.id LIMIT 3",
        q=q,
    )
    assert catalog.algebra not in {row[0] for row in nearest_ready}


def test_building_the_catalog_twice_gives_identical_embeddings(clean_db: str) -> None:
    def fingerprint() -> list[tuple[object, ...]]:
        return rows(
            clean_db,
            "SELECT d.filename, c.chunk_index, md5(c.embedding::text), c.content "
            "FROM document_chunks c JOIN documents d ON d.id = c.document_id "
            "ORDER BY d.filename, c.chunk_index",
        )

    build_catalog(clean_db)
    first = fingerprint()
    truncate_all(clean_db)
    build_catalog(clean_db)
    assert fingerprint() == first
    assert len(first) > 10


def test_catalog_content_is_neutral_text_without_personal_data(
    clean_db: str, catalog: Catalog
) -> None:
    contents = {str(row[0]) for row in rows(clean_db, "SELECT content FROM document_chunks")}
    assert all(content.startswith("fixture chunk ") for content in contents)
    emails = {str(row[0]) for row in rows(clean_db, "SELECT email FROM users")}
    assert all(email.endswith("@fixtures.example.com") for email in emails)
