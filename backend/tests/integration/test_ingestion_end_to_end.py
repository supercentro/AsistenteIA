"""Ingest a file without HTTP, then search it as the student and as the owner (task 8.3)."""

import sys
import uuid

import pytest

from app.core.database import create_db_engine, create_session_factory
from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from app.rag.loaders import PdfLimits
from app.repositories.chunk_repository import ChunkRepository, ScoredChunk, SearchActor
from app.services.ingestion_service import Outcome
from tests.ingestion_support import Scene, insert_pending, make_scene
from tests.least_privilege import role_url
from tests.pdf_support import pdf_with_pages
from tests.service_support import built_service
from tests.sql_support import insert_chunk, insert_enrollment, insert_user, scalar
from tests.unit.test_pdf_outline import with_outline

PDF_LIMITS = PdfLimits(
    max_pages=300,
    max_chars=2_000_000,
    memory_mb=768,
    cpu_seconds=20,
    timeout_seconds=30,
    max_output_bytes=8 * 1024 * 1024,
)
linux_only = pytest.mark.skipif(
    sys.platform != "linux", reason="PDF parsing runs only on Linux (isolated child process)"
)


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def search(url: str, actor: SearchActor, subject: uuid.UUID, question: str) -> list[ScoredChunk]:
    engine = create_db_engine(role_url("app", url))  # the application role in the roles mode
    try:
        with create_session_factory(engine)() as session:
            vector = FakeEmbedder().embed([question])[0]
            return ChunkRepository(session).find_similar(actor, subject, vector, top_k=5)
    finally:
        engine.dispose()


def enrolled_student(scene: Scene) -> SearchActor:
    student = insert_user(scene.url, f"s-{uuid.uuid4().hex[:8]}@example.com", "student")
    insert_enrollment(scene.url, scene.subject, student)
    return SearchActor(student, UserRole.STUDENT)


def test_a_text_file_is_found_by_the_student_and_the_owner(scene: Scene) -> None:
    document, _ = insert_pending(
        scene.url,
        scene.subject,
        payload=b"Derivatives measure the rate of change of a function over time.",
        filename="calculus.txt",
        content_type="text/plain",
    )
    with built_service(scene.url) as built:
        assert built.service.run_once() is Outcome.READY

    for actor in (enrolled_student(scene), SearchActor(scene.teacher, UserRole.TEACHER)):
        hits = search(scene.url, actor, scene.subject, "rate of change of a function")
        assert [hit.document_id for hit in hits] == [document]
        assert hits[0].page_number is None
        assert hits[0].document_filename == "calculus.txt"
        assert "rate of change" in hits[0].content


@linux_only
def test_a_generated_pdf_is_found_with_its_page_numbers(scene: Scene) -> None:
    document, _ = insert_pending(
        scene.url,
        scene.subject,
        payload=pdf_with_pages(
            ["Limits and continuity of functions", "Series converge when their terms shrink"]
        ),
        filename="analysis.pdf",
    )
    with built_service(scene.url, pdf=PDF_LIMITS) as built:
        assert built.service.run_once() is Outcome.READY

    hits = search(
        scene.url,
        SearchActor(scene.teacher, UserRole.TEACHER),
        scene.subject,
        "series converge when their terms shrink",
    )
    assert {hit.document_id for hit in hits} == {document}
    assert hits[0].page_number == 2
    assert {hit.page_number for hit in hits} == {1, 2}


@linux_only
def test_the_bookmarks_of_a_real_pdf_become_topics_under_the_worker_role(scene: Scene) -> None:
    document, _ = insert_pending(
        scene.url,
        scene.subject,
        payload=with_outline([("Limits", 0), ("Series", 1)]),
        filename="analysis.pdf",
    )
    with built_service(scene.url, pdf=PDF_LIMITS) as built:
        assert built.service.run_once() is Outcome.READY

    assert (
        scalar(
            scene.url,
            "SELECT string_agg(title || ':' || start_page || '-' || end_page, '|' "
            "ORDER BY position) FROM document_topics WHERE document_id = :d",
            d=document,
        )
        == "Limits:1-1|Series:2-6"
    )


def test_failed_and_pending_documents_are_never_returned(scene: Scene) -> None:
    ready, _ = insert_pending(
        scene.url,
        scene.subject,
        payload=b"integrals add up small pieces of area",
        filename="ready.txt",
        content_type="text/plain",
    )
    failed, _ = insert_pending(
        scene.url, scene.subject, payload=b"   ", filename="blank.txt", content_type="text/plain"
    )
    with built_service(scene.url) as built:
        outcomes = {built.service.run_once(), built.service.run_once()}
    assert outcomes == {Outcome.READY, Outcome.FAILED}
    pending, _ = insert_pending(
        scene.url, scene.subject, payload=b"x", filename="queued.txt", content_type="text/plain"
    )
    query = "integrals add up small pieces of area"
    embedding = "[" + ",".join(str(value) for value in FakeEmbedder().embed([query])[0]) + "]"
    for other in (failed, pending):  # even chunks that match exactly stay invisible
        insert_chunk(scene.url, other, scene.subject, embedding=embedding, content=query)

    hits = search(scene.url, SearchActor(scene.teacher, UserRole.TEACHER), scene.subject, query)

    assert {hit.document_id for hit in hits} == {ready}
