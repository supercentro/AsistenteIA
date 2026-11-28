"""Bookmark topics during ingestion (change `frequent-questions-and-topics`, task 6.3).

The PDF parsing is replaced by stand-ins, so these run on any system; the real child is covered on
Linux. Fictitious data only.
"""

import uuid

import pytest

from app.models.ingestion import DocumentErrorCode
from app.rag.chunker import Page
from app.rag.loaders import DocumentLoadError, OutlineEntry
from app.services.ingestion_service import Outcome
from tests.ingestion_support import insert_pending
from tests.service_support import built_service, capture_logs, log_text
from tests.sql_support import count, insert_subject, insert_user, run, scalar

PAGES = [Page(1, "Modelo relacional."), Page(2, "Claves."), Page(4, "Formas normales.")]
OUTLINE = [OutlineEntry("Modelo", 1), OutlineEntry("Titulo-secreto-5521", 4)]


def pending(url: str, content_type: str = "application/pdf") -> uuid.UUID:
    teacher = insert_user(url, f"t-{uuid.uuid4().hex[:8]}@example.com", "teacher")
    subject = insert_subject(url, teacher)
    document, _ = insert_pending(
        url, subject, payload=b"%PDF-1.4 stand-in", content_type=content_type
    )
    return document


def pages(_: bytes) -> list[Page]:
    return list(PAGES)


def status(url: str, document: uuid.UUID) -> object:
    return scalar(url, "SELECT status FROM documents WHERE id = :d", d=document)


def topics_of(url: str) -> object:
    return scalar(
        url,
        "SELECT string_agg(title || ':' || start_page || '-' || end_page, '|' "
        "ORDER BY position) FROM document_topics",
    )


def test_topics_are_stored_with_the_ready_document(
    clean_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    document = pending(clean_db)
    capture_logs(caplog)

    with built_service(
        clean_db, pdf_loader=pages, pdf_outline_loader=lambda _: list(OUTLINE)
    ) as built:
        assert built.service.run_once() is Outcome.READY

    assert status(clean_db, document) == "ready"
    assert topics_of(clean_db) == "Modelo:1-3|Titulo-secreto-5521:4-4"
    assert scalar(clean_db, "SELECT source FROM document_topic_sets") == "bookmarks"
    assert scalar(clean_db, "SELECT revision FROM document_topic_sets") == 1
    assert scalar(clean_db, "SELECT ranges_changed_at FROM document_topic_sets") is None
    assert "Titulo-secreto-5521" not in log_text(caplog)


def test_no_usable_bookmarks_means_no_set(clean_db: str) -> None:
    document = pending(clean_db)

    with built_service(
        clean_db, pdf_loader=pages, pdf_outline_loader=lambda _: [OutlineEntry("Solo", 1)]
    ) as built:
        assert built.service.run_once() is Outcome.READY

    assert status(clean_db, document) == "ready"
    assert count(clean_db, "document_topic_sets") == 0


@pytest.mark.parametrize(
    "error",
    [
        DocumentLoadError(DocumentErrorCode.RESOURCE_LIMIT_EXCEEDED),
        DocumentLoadError(DocumentErrorCode.PROCESSING_TIMEOUT),
        RuntimeError("Titulo-secreto-5521"),
        MemoryError(),
        RecursionError(),
    ],
)
def test_a_failure_reading_bookmarks_keeps_the_document_outcome(
    clean_db: str, caplog: pytest.LogCaptureFixture, error: BaseException
) -> None:
    document = pending(clean_db)
    capture_logs(caplog)

    def broken(_: bytes) -> list[OutlineEntry]:
        raise error

    with built_service(clean_db, pdf_loader=pages, pdf_outline_loader=broken) as built:
        assert built.service.run_once() is Outcome.READY

    assert status(clean_db, document) == "ready"
    assert count(clean_db, "document_topic_sets") == 0
    assert "Titulo-secreto-5521" not in log_text(caplog)


@pytest.mark.parametrize("content_type", ["text/plain", "text/markdown"])
def test_text_files_have_no_topics(clean_db: str, content_type: str) -> None:
    document = pending(clean_db, content_type)

    # Calls are recorded, not raised: the service swallows any error of the loader.
    calls: list[bytes] = []

    def recording(payload: bytes) -> list[OutlineEntry]:
        calls.append(payload)
        return list(OUTLINE)

    with built_service(clean_db, pdf_outline_loader=recording) as built:
        built.service.run_once()

    assert status(clean_db, document) == "ready"
    assert calls == [] and count(clean_db, "document_topic_sets") == 0


def test_a_lost_job_stores_no_topic(clean_db: str) -> None:
    document = pending(clean_db)

    def delete_while_reading(_: bytes) -> list[OutlineEntry]:
        run(clean_db, "DELETE FROM documents WHERE id = :d", d=document)
        return list(OUTLINE)

    with built_service(
        clean_db, pdf_loader=pages, pdf_outline_loader=delete_while_reading
    ) as built:
        assert built.service.run_once() is Outcome.LOST

    assert count(clean_db, "document_topic_sets") == 0


def test_bookmarks_are_skipped_when_the_job_is_short_of_time(clean_db: str) -> None:
    document = pending(clean_db)

    calls: list[bytes] = []

    def recording(payload: bytes) -> list[OutlineEntry]:
        calls.append(payload)
        return list(OUTLINE)

    with built_service(
        clean_db, pdf_loader=pages, pdf_outline_loader=recording, deadline_seconds=20
    ) as built:
        assert built.service.run_once() is Outcome.READY

    assert status(clean_db, document) == "ready"
    assert calls == [] and count(clean_db, "document_topic_sets") == 0
