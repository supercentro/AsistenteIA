"""Leak tests of the document endpoints (change 6, task 9.3).

A recognisable marker travels in the file name, the content, the PDF metadata and the text of a
database error. Whatever happens (every rejection, a failed commit, an unexpected exception) it
must appear in no error response and in no captured log line (DEBUG, including `exc_info`).
A successful response legitimately returns the cleaned name of the owner's own document.
"""

import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.services.document_service import DocumentService
from tests.ingestion_support import insert_pending
from tests.integration.helpers import build_app
from tests.service_support import capture_logs, log_text
from tests.upload_support import (
    MULTIPART,
    NOTHING,
    TEXT,
    World,
    auth,
    document_url,
    documents_url,
    make_world,
    multipart_body,
    part,
    raw_upload,
    stored,
    upload,
)

NAME = "MARKER-NAME-8842"
CONTENT = "MARKER-CONTENT-5517"
META = "MARKER-PDF-META-3306"
DB_TEXT = "MARKER-DB-TEXT-7719"
ERROR_TEXT = "MARKER-EXCEPTION-1204"
MARKERS = (NAME, CONTENT, META, DB_TEXT, ERROR_TEXT)

PDF_WITH_METADATA = (
    b"%PDF-1.7\n1 0 obj\n<< /Title (" + META.encode() + b") /Author (" + META.encode() + b") >>\n"
    b"endobj\ntrailer\n<< /Info 1 0 R >>\n%%EOF\n"
)
CONTENT_BYTES = (CONTENT + " is the text of the file").encode()


@pytest.fixture
def world(clean_db: str) -> World:
    return make_world(clean_db)


@pytest.fixture
def client(clean_db: str) -> TestClient:
    return TestClient(
        build_app(clean_db, max_upload_mb=1, max_documents_per_subject=2),
        raise_server_exceptions=False,
    )


def assert_clean(response_text: str, headers: object, caplog: pytest.LogCaptureFixture) -> None:
    visible = response_text + repr(headers)
    for marker in MARKERS:
        assert marker not in visible, marker
        assert marker not in log_text(caplog), marker


# --- every kind of failure ----------------------------------------------------------------------


def rejected(client: TestClient, world: World, kind: str) -> object:
    headers = auth(client, world.teacher)
    name = NAME + ".exe"
    if kind == "415-name":
        return upload(client, headers, world.subject, name, CONTENT_BYTES)
    if kind == "415-content":
        return upload(client, headers, world.subject, NAME + ".txt", b"\xff\xfe" + CONTENT_BYTES)
    if kind == "413":
        return upload(
            client, headers, world.subject, NAME + ".txt", CONTENT_BYTES + b"a" * (1024 * 1024)
        )
    if kind == "422-empty":
        return upload(client, headers, world.subject, NAME + ".txt", b"")
    if kind == "422-name":
        body = multipart_body(part("file", CONTENT_BYTES, NAME + "‮" + "a" * 300))
        return raw_upload(client, headers, world.subject, body, MULTIPART)
    if kind == "422-fields":
        body = multipart_body(
            part("file", CONTENT_BYTES, NAME + ".txt"), part(NAME, CONTENT_BYTES, NAME)
        )
        return raw_upload(client, headers, world.subject, body, MULTIPART)
    if kind == "422-malformed":
        return raw_upload(client, headers, world.subject, CONTENT_BYTES, "multipart/form-data")
    if kind == "422-pdf-meta":
        body = multipart_body(part("file", PDF_WITH_METADATA, NAME), part(NAME, b"x"))
        return raw_upload(client, headers, world.subject, body, MULTIPART)
    if kind == "404-subject":
        return upload(client, headers, "00000000-0000-0000-0000-000000000000", NAME + ".txt")
    if kind == "403":
        return upload(client, auth(client, world.student), world.subject, NAME + ".txt")
    if kind == "401":
        return upload(client, None, world.subject, NAME + ".txt", CONTENT_BYTES)
    raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind",
    [
        "415-name",
        "415-content",
        "413",
        "422-empty",
        "422-name",
        "422-fields",
        "422-malformed",
        "422-pdf-meta",
        "404-subject",
        "403",
        "401",
    ],
)
def test_no_marker_appears_in_a_rejection_or_in_the_logs(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    capture_logs(caplog)

    response = rejected(client, world, kind)

    assert response.status_code in {401, 403, 404, 413, 415, 422}  # type: ignore[attr-defined]
    assert_clean(response.text, response.headers, caplog)  # type: ignore[attr-defined]
    assert stored(world.url) == NOTHING


def test_the_quota_and_queue_rejections_are_clean(
    clean_db: str, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    capture_logs(caplog)
    client = TestClient(
        build_app(clean_db, max_documents_per_subject=1, ingestion_queue_max=2),
        raise_server_exceptions=False,
    )
    headers = auth(client, world.teacher)
    assert upload(client, headers, world.subject, NAME + ".txt", CONTENT_BYTES).status_code == 202
    quota = upload(client, headers, world.subject, NAME + ".txt", CONTENT_BYTES)  # 1 of 2 jobs
    insert_pending(clean_db, uuid.UUID(world.other_subject))  # now the queue holds 2 of 2
    queue = upload(client, headers, world.subject, NAME + ".txt", CONTENT_BYTES)

    assert quota.status_code == 409
    assert queue.status_code == 503
    for response in (quota, queue):
        assert_clean(response.text, response.headers, caplog)


def test_a_database_error_at_commit_is_clean(
    clean_db: str, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    capture_logs(caplog)
    client = TestClient(build_app(clean_db), raise_server_exceptions=False)
    headers = auth(client, world.teacher)
    engine = client.app.state.session_factory.kw["bind"]  # type: ignore[attr-defined]

    @event.listens_for(engine, "commit")
    def boom(connection: object) -> None:
        raise OperationalError(
            "COMMIT", {"name": NAME, "content": CONTENT}, Exception(DB_TEXT + " " + CONTENT)
        )

    response = upload(client, headers, world.subject, NAME + ".txt", CONTENT_BYTES)

    assert response.status_code == 503
    assert_clean(response.text, response.headers, caplog)
    assert stored(world.url) == NOTHING


def test_an_unexpected_exception_gives_the_generic_error_and_logs_only_its_type(
    client: TestClient,
    world: World,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_logs(caplog)

    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError(ERROR_TEXT + " " + NAME + " " + CONTENT)

    monkeypatch.setattr(DocumentService, "upload", explode)

    response = upload(
        client, auth(client, world.teacher), world.subject, NAME + ".txt", CONTENT_BYTES
    )

    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL_ERROR", "message": "Internal server error"}
    assert_clean(response.text, response.headers, caplog)
    logged = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any("RuntimeError" in r.getMessage() and "POST" in r.getMessage() for r in logged)
    assert any(world.subject in r.getMessage() for r in logged)  # the path: an identifier only


def test_an_unexpected_exception_while_reading_the_body_is_clean(
    client: TestClient,
    world: World,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    capture_logs(caplog)

    async def explode(self: Request, **kwargs: object) -> object:
        raise ValueError(ERROR_TEXT + CONTENT)

    monkeypatch.setattr(Request, "form", explode)

    response = upload(client, auth(client, world.teacher), world.subject, NAME + ".txt")

    assert response.status_code == 500
    assert_clean(response.text, response.headers, caplog)


# --- success and the other operations -----------------------------------------------------------


def test_a_successful_upload_logs_no_name_content_or_metadata(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    capture_logs(caplog)
    headers = auth(client, world.teacher)

    text = upload(client, headers, world.subject, NAME + ".txt", CONTENT_BYTES)
    pdf = upload(client, headers, world.subject, NAME + ".pdf", PDF_WITH_METADATA)

    assert text.status_code == pdf.status_code == 202
    assert NAME in text.text  # the owner's own document legitimately carries its name
    assert META not in pdf.text  # the metadata is never read by the API
    for marker in (CONTENT, META, DB_TEXT, ERROR_TEXT, NAME):
        assert marker not in log_text(caplog), marker


def test_listing_and_deleting_log_no_name(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    capture_logs(caplog)
    headers = auth(client, world.teacher)
    document = upload(client, headers, world.subject, NAME + ".txt", CONTENT_BYTES).json()["id"]

    assert client.get(documents_url(world.subject), headers=headers).status_code == 200
    assert client.delete(document_url(world.subject, document), headers=headers).status_code == 204

    for marker in (CONTENT, NAME):
        assert marker not in log_text(caplog), marker


def test_the_upload_log_names_identifiers_only(
    client: TestClient, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    capture_logs(caplog)
    headers = auth(client, world.teacher)

    document = upload(client, headers, world.subject, "unit1.txt", TEXT).json()["id"]

    messages = [r.getMessage() for r in caplog.records if "upload" in r.getMessage().lower()]
    assert any(document in message for message in messages)
    assert all("unit1" not in message for message in messages)
