"""`POST`, `GET` and `DELETE` on `/subjects/{id}/documents` (change 6, task 9.1).

Authorization first (401, 403, 404 identical for a foreign and an unknown subject), then the happy
paths, every rejection of the upload (413, 415, 422 with its fixed reason, 409, 429, 503) with the
proof that nothing was stored, the explicit commit before the `202`, and listing and deletion
(including the document of another subject and a document being processed).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.core.database import create_db_engine, create_session_factory
from app.main import create_app
from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.repositories.ingestion_job_repository import IngestionJobRepository
from tests.ingestion_support import insert_pending
from tests.integration.helpers import FAST_PASSWORDS, build_app, build_settings
from tests.sql_support import count, insert_chunk, run, scalar
from tests.upload_support import (
    MULTIPART,
    NOTHING,
    PDF,
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

ONE_MB = 1024 * 1024


@pytest.fixture
def world(clean_db: str) -> World:
    return make_world(clean_db)


@pytest.fixture
def teacher_headers(client: TestClient, world: World) -> dict[str, str]:
    return auth(client, world.teacher)


def make_client(url: str, **overrides: object) -> TestClient:
    return TestClient(build_app(url, **overrides), raise_server_exceptions=False)


def reason(response: object) -> object:
    body = response.json()  # type: ignore[attr-defined]
    return body["details"]["reason"]


# --- authorization ------------------------------------------------------------------------------


def calls(world: World, subject: str) -> list[tuple[str, str]]:
    """The three operations as (method, url) pairs against `subject`."""
    document = str(uuid.uuid4())
    return [
        ("POST", documents_url(subject)),
        ("GET", documents_url(subject)),
        ("DELETE", document_url(subject, document)),
    ]


def send(client: TestClient, method: str, url: str, headers: dict[str, str] | None) -> object:
    if method == "POST":
        return client.post(url, files={"file": ("notes.txt", TEXT)}, headers=headers or {})
    return client.request(method, url, headers=headers or {})


@pytest.mark.parametrize("operation", [0, 1, 2], ids=["POST", "GET", "DELETE"])
def test_a_request_without_credentials_is_401_and_nothing_is_stored(
    client: TestClient, world: World, operation: int
) -> None:
    method, url = calls(world, world.subject)[operation]

    response = send(client, method, url, None)

    assert response.status_code == 401  # type: ignore[attr-defined]
    assert response.json()["code"] == "UNAUTHORIZED"  # type: ignore[attr-defined]
    assert stored(world.url) == NOTHING


@pytest.mark.parametrize("operation", [0, 1, 2], ids=["POST", "GET", "DELETE"])
def test_a_garbage_token_is_401(client: TestClient, world: World, operation: int) -> None:
    method, url = calls(world, world.subject)[operation]

    response = send(client, method, url, {"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401  # type: ignore[attr-defined]


@pytest.mark.parametrize("operation", [0, 1, 2], ids=["POST", "GET", "DELETE"])
def test_a_student_is_403_even_when_enrolled_and_nothing_is_read_or_written(
    client: TestClient, world: World, operation: int
) -> None:
    run(
        world.url,
        "INSERT INTO enrollments (subject_id, student_id) VALUES (:s, :u)",
        s=uuid.UUID(world.subject),
        u=uuid.UUID(world.student.id),
    )
    method, url = calls(world, world.subject)[operation]

    response = send(client, method, url, auth(client, world.student))

    assert response.status_code == 403  # type: ignore[attr-defined]
    assert response.json()["code"] == "FORBIDDEN"  # type: ignore[attr-defined]
    assert stored(world.url) == NOTHING


@pytest.mark.parametrize("operation", [0, 1, 2], ids=["POST", "GET", "DELETE"])
def test_another_teachers_subject_and_an_unknown_subject_give_the_same_404(
    client: TestClient, world: World, operation: int
) -> None:
    headers = auth(client, world.other_teacher)
    foreign = calls(world, world.subject)[operation]
    unknown = calls(world, str(uuid.uuid4()))[operation]

    first = send(client, foreign[0], foreign[1], headers)
    second = send(client, unknown[0], unknown[1], headers)

    assert first.status_code == second.status_code == 404  # type: ignore[attr-defined]
    assert first.json() == second.json()  # type: ignore[attr-defined]
    assert first.json()["code"] == "NOT_FOUND"  # type: ignore[attr-defined]
    assert stored(world.url) == NOTHING


@pytest.mark.parametrize("subject", ["not-a-uuid", "123", "%00", "..", "1" * 200])
def test_a_malformed_subject_id_is_the_same_404_for_every_operation(
    client: TestClient, world: World, teacher_headers: dict[str, str], subject: str
) -> None:
    assert upload(client, teacher_headers, subject).status_code == 404
    assert client.get(documents_url(subject), headers=teacher_headers).status_code == 404
    deleted = client.delete(document_url(subject, uuid.uuid4()), headers=teacher_headers)
    assert deleted.status_code == 404
    assert stored(world.url) == NOTHING


def test_a_malformed_document_id_is_404(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = client.delete(document_url(world.subject, "not-a-uuid"), headers=teacher_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_the_document_of_another_subject_is_404_and_untouched(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    other_document, _ = insert_pending(world.url, uuid.UUID(world.other_subject))

    response = client.delete(document_url(world.subject, other_document), headers=teacher_headers)

    assert response.status_code == 404
    assert count(world.url, "documents", "id = :d", d=other_document) == 1
    assert count(world.url, "ingestion_jobs") == 1


def test_the_owner_of_a_document_cannot_delete_it_through_another_teachers_subject(
    client: TestClient, world: World
) -> None:
    document, _ = insert_pending(world.url, uuid.UUID(world.subject))
    headers = auth(client, world.other_teacher)

    response = client.delete(document_url(world.other_subject, document), headers=headers)

    assert response.status_code == 404
    assert count(world.url, "documents", "id = :d", d=document) == 1


# --- the happy path -----------------------------------------------------------------------------


def test_a_teacher_uploads_a_text_file_and_gets_a_pending_document(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = upload(client, teacher_headers, world.subject, "unit1.txt", TEXT)

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "id",
        "subject_id",
        "filename",
        "content_type",
        "size_bytes",
        "status",
        "error_code",
        "error_message",
        "chunks_count",
        "created_at",
    }
    assert body["subject_id"] == world.subject
    assert body["filename"] == "unit1.txt"
    assert body["content_type"] == "text/plain"
    assert body["size_bytes"] == len(TEXT)
    assert body["status"] == "pending"
    assert body["error_code"] is None
    assert body["error_message"] is None
    assert body["chunks_count"] == 0
    uuid.UUID(body["id"])


def test_the_document_its_job_and_the_bytes_are_stored_together(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = upload(client, teacher_headers, world.subject, "unit1.pdf", PDF)

    assert response.status_code == 202
    document = uuid.UUID(response.json()["id"])
    assert stored(world.url) == {"documents": 1, "jobs": 1, "payloads": 1, "chunks": 0}
    assert scalar(
        world.url,
        "SELECT status::text FROM documents WHERE id = :d",
        d=document,
    ) == "pending"
    assert scalar(
        world.url,
        "SELECT j.payload = :p FROM ingestion_jobs j WHERE j.document_id = :d",
        d=document,
        p=PDF,
    )
    assert scalar(
        world.url, "SELECT attempts FROM ingestion_jobs WHERE document_id = :d", d=document
    ) == 0
    assert scalar(
        world.url, "SELECT size_bytes FROM documents WHERE id = :d", d=document
    ) == len(PDF)


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("unit1.pdf", PDF, "application/pdf"),
        ("notes.txt", TEXT, "text/plain"),
        ("notes.md", b"# Title\n\ntext", "text/markdown"),
    ],
)
def test_the_three_allowed_types_are_accepted(
    client: TestClient,
    world: World,
    teacher_headers: dict[str, str],
    name: str,
    content: bytes,
    expected: str,
) -> None:
    response = upload(client, teacher_headers, world.subject, name, content)

    assert response.status_code == 202
    assert response.json()["content_type"] == expected


def test_the_client_content_type_is_ignored(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = upload(
        client, teacher_headers, world.subject, "notes.txt", TEXT, client_type="application/pdf"
    )

    assert response.status_code == 202
    assert response.json()["content_type"] == "text/plain"


def test_the_stored_name_is_cleaned(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = upload(client, teacher_headers, world.subject, r"..\..\notes/unit1.pdf", PDF)

    assert response.status_code == 202
    assert response.json()["filename"] == "unit1.pdf"
    assert scalar(world.url, "SELECT filename FROM documents") == "unit1.pdf"


def test_hostile_characters_of_the_name_are_neither_stored_nor_returned(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = upload(client, teacher_headers, world.subject, "re‮gnp.txt ", TEXT)

    assert response.status_code == 202
    assert response.json()["filename"] == "regnp.txt"
    assert scalar(world.url, "SELECT filename FROM documents") == "regnp.txt"


def test_a_file_exactly_at_the_size_limit_is_accepted(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1, ingestion_pending_bytes_max_mb=4)
    content = b"a" * ONE_MB

    response = upload(client, auth(client, world.teacher), world.subject, "big.txt", content)

    assert response.status_code == 202
    assert response.json()["size_bytes"] == ONE_MB
    assert scalar(world.url, "SELECT octet_length(payload) FROM ingestion_jobs") == ONE_MB


def test_two_uploads_of_the_same_file_are_two_documents(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    first = upload(client, teacher_headers, world.subject)
    second = upload(client, teacher_headers, world.subject)

    assert first.status_code == second.status_code == 202
    assert first.json()["id"] != second.json()["id"]
    assert stored(world.url)["jobs"] == 2


# --- the explicit commit before the 202 ---------------------------------------------------------


def test_the_upload_is_committed_before_the_response_is_built(
    clean_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From another connection, the rows are already visible when the `202` body is made."""
    from app.schemas import document as schema

    world = make_world(clean_db)
    client = make_client(clean_db)
    seen: list[dict[str, int]] = []
    original = schema.Document.model_validate.__func__  # type: ignore[attr-defined]

    def probing(cls: type, *args: object, **kwargs: object) -> object:
        seen.append(stored(clean_db))
        return original(cls, *args, **kwargs)

    monkeypatch.setattr(schema.Document, "model_validate", classmethod(probing))

    response = upload(client, auth(client, world.teacher), world.subject)

    assert response.status_code == 202
    assert seen
    assert seen[0] == {"documents": 1, "jobs": 1, "payloads": 1, "chunks": 0}


def failing_commit(client: TestClient) -> None:
    """Make every commit of the application's engine fail like an unreachable database."""
    engine = client.app.state.session_factory.kw["bind"]  # type: ignore[attr-defined]

    @event.listens_for(engine, "commit")
    def boom(connection: object) -> None:
        raise OperationalError("COMMIT", {}, Exception("DB-TEXT-MARKER-commit"))


def test_a_failed_commit_is_503_and_nothing_remains(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db)
    headers = auth(client, world.teacher)
    failing_commit(client)

    response = upload(client, headers, world.subject)

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "DB-TEXT-MARKER" not in response.text
    assert stored(clean_db) == NOTHING


def test_a_failure_while_writing_the_job_rolls_the_document_back(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db)
    headers = auth(client, world.teacher)
    engine = client.app.state.session_factory.kw["bind"]  # type: ignore[attr-defined]

    @event.listens_for(engine, "before_cursor_execute")
    def refuse_job(conn: object, cursor: object, statement: str, *rest: object) -> None:
        if statement.startswith("INSERT INTO ingestion_jobs"):
            raise OperationalError(statement, {}, Exception("DB-TEXT-MARKER-job"))

    response = upload(client, headers, world.subject)

    assert response.status_code == 503
    assert "DB-TEXT-MARKER" not in response.text
    assert stored(clean_db) == NOTHING


# --- size -----------------------------------------------------------------------------------------


def test_a_file_one_byte_over_the_limit_is_413_and_nothing_is_stored(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1)

    response = upload(
        client, auth(client, world.teacher), world.subject, "big.txt", b"a" * (ONE_MB + 1)
    )

    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert stored(clean_db) == NOTHING


def test_a_body_far_over_the_limit_is_413(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1)

    response = upload(
        client, auth(client, world.teacher), world.subject, "big.txt", b"a" * (3 * ONE_MB)
    )

    assert response.status_code == 413
    assert stored(clean_db) == NOTHING


def test_a_declared_length_over_the_limit_is_413_whatever_the_body_is(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1)
    headers = auth(client, world.teacher)
    body = multipart_body(part("file", b"small", "small.txt"))

    response = raw_upload(
        client,
        headers,
        world.subject,
        body,
        MULTIPART,
        {"Content-Length": str(50 * ONE_MB)},
    )

    assert response.status_code == 413
    assert stored(clean_db) == NOTHING


def test_a_small_declared_length_does_not_protect_a_large_body(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1)
    headers = auth(client, world.teacher)
    body = multipart_body(part("file", b"a" * (3 * ONE_MB), "big.txt"))

    response = raw_upload(client, headers, world.subject, body, MULTIPART, {"Content-Length": "10"})

    assert response.status_code == 413
    assert stored(clean_db) == NOTHING


def test_a_student_with_an_oversized_declaration_is_403_not_413(clean_db: str) -> None:
    """Authorization decides before the body (and its declared size) is looked at."""
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1)
    body = multipart_body(part("file", b"small", "small.txt"))

    response = raw_upload(
        client,
        auth(client, world.student),
        world.subject,
        body,
        MULTIPART,
        {"Content-Length": str(50 * ONE_MB)},
    )

    assert response.status_code == 403


# --- type -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("tool.exe", b"MZ\x90\x00"),
        ("unit1.pdf", b"MZ\x90\x00 an executable renamed"),
        ("notes.txt", b"MZ\x90\x00 an executable renamed"),
        ("notes.docx", b"PK\x03\x04"),
        ("noextension", TEXT),
        ("notes.txt", b"caf\xe9 not utf-8"),
        ("notes.md", b"with\x00nul"),
    ],
)
def test_a_type_that_is_not_allowed_or_does_not_match_is_415(
    client: TestClient,
    world: World,
    teacher_headers: dict[str, str],
    name: str,
    content: bytes,
) -> None:
    response = upload(client, teacher_headers, world.subject, name, content)

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert stored(world.url) == NOTHING


# --- the multipart request ----------------------------------------------------------------------


def post_parts(
    client: TestClient, headers: dict[str, str], subject: str, *parts: bytes
) -> object:
    return raw_upload(client, headers, subject, multipart_body(*parts), MULTIPART)


def test_a_request_without_a_file_part_is_422_file_part_missing(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = post_parts(client, teacher_headers, world.subject)

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert response.json()["code"] == "VALIDATION_ERROR"  # type: ignore[attr-defined]
    assert reason(response) == "FILE_PART_MISSING"
    assert stored(world.url) == NOTHING


@pytest.mark.parametrize(
    "parts",
    [
        [part("upload", b"x", "notes.txt")],  # a file with another field name
        [part("file", b"just text, not a file part")],  # `file` without a filename
        [part("note", b"x")],  # only other fields
    ],
    ids=["other-name", "no-filename", "only-fields"],
)
def test_a_file_part_that_is_not_called_file_is_422_file_part_missing(
    client: TestClient, world: World, teacher_headers: dict[str, str], parts: list[bytes]
) -> None:
    response = post_parts(client, teacher_headers, world.subject, *parts)

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert reason(response) == "FILE_PART_MISSING"


@pytest.mark.parametrize("files", [2, 3, 5])
def test_several_files_are_422_unexpected_fields(
    client: TestClient, world: World, teacher_headers: dict[str, str], files: int
) -> None:
    parts = [part("file", TEXT, f"n{i}.txt") for i in range(files)]

    response = post_parts(client, teacher_headers, world.subject, *parts)

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert reason(response) == "UNEXPECTED_FIELDS"
    assert stored(world.url) == NOTHING


def test_an_extra_form_field_is_422_unexpected_fields(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = post_parts(
        client,
        teacher_headers,
        world.subject,
        part("file", TEXT, "notes.txt"),
        part("subject_id", str(uuid.uuid4()).encode()),
    )

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert reason(response) == "UNEXPECTED_FIELDS"
    assert stored(world.url) == NOTHING


def test_an_extra_file_with_another_name_is_422_unexpected_fields(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = post_parts(
        client,
        teacher_headers,
        world.subject,
        part("file", TEXT, "notes.txt"),
        part("attachment", TEXT, "other.txt"),
    )

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert reason(response) == "UNEXPECTED_FIELDS"


def test_an_empty_file_is_422_empty_file(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = upload(client, teacher_headers, world.subject, "empty.txt", b"")

    assert response.status_code == 422
    assert reason(response) == "EMPTY_FILE"
    assert stored(world.url) == NOTHING


@pytest.mark.parametrize("name", ["", "..", "/", "‮", "a" * 300 + ".txt"])
def test_an_invalid_filename_is_422_invalid_filename(
    client: TestClient, world: World, teacher_headers: dict[str, str], name: str
) -> None:
    response = post_parts(client, teacher_headers, world.subject, part("file", TEXT, name))

    assert response.status_code == 422  # type: ignore[attr-defined]
    assert reason(response) == "INVALID_FILENAME"
    assert stored(world.url) == NOTHING


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("multipart/form-data", b"--x\r\n\r\n"),  # no boundary
        ("application/json", b'{"file": "x"}'),
        ("application/x-www-form-urlencoded", b"file=x"),
        ("text/plain", b"hello"),
        ("multipart/form-data; boundary=" + "b" * 5, b"--b\r\nContent-Disposition: form-data; "),
        (
            MULTIPART,
            f"--{'testboundary7f3a'}\r\n".encode() + b"X-Header: " + b"h" * 70_000 + b"\r\n\r\n",
        ),
    ],
    ids=["no-boundary", "json", "urlencoded", "plain", "truncated", "huge-header"],
)
def test_a_body_that_is_not_a_valid_multipart_is_422_malformed_multipart(
    client: TestClient,
    world: World,
    teacher_headers: dict[str, str],
    content_type: str,
    body: bytes,
) -> None:
    response = raw_upload(client, teacher_headers, world.subject, body, content_type)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert reason(response) == "MALFORMED_MULTIPART"
    assert stored(world.url) == NOTHING


def test_an_abusive_number_of_parts_is_422_malformed_multipart_quickly(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    fields = [part(f"f{i}", b"x") for i in range(500)]
    files = [part("file", TEXT, f"n{i}.txt") for i in range(100)]

    many_fields = post_parts(client, teacher_headers, world.subject, *fields)
    many_files = post_parts(client, teacher_headers, world.subject, *files)

    for response in (many_fields, many_files):
        assert response.status_code == 422  # type: ignore[attr-defined]
        assert reason(response) == "MALFORMED_MULTIPART"
    assert stored(world.url) == NOTHING


def test_the_framework_default_400_is_never_returned(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    bodies = [b"", b"\r\n", b"--", b"\x00" * 64, b"--testboundary7f3a", b"--testboundary7f3a--"]

    for body in bodies:
        response = raw_upload(client, teacher_headers, world.subject, body, MULTIPART)
        assert response.status_code == 422, body
        assert reason(response) in {"MALFORMED_MULTIPART", "FILE_PART_MISSING"}, body
    assert stored(world.url) == NOTHING


def test_parser_text_never_reaches_the_response(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = raw_upload(client, teacher_headers, world.subject, b"x", "multipart/form-data")

    text = response.text.lower()
    assert "boundary" not in text
    assert "multipart" not in text.replace("malformed_multipart", "")
    assert response.json()["message"]


# --- quotas and saturation ----------------------------------------------------------------------


def fill(world: World, documents: int, **kwargs: object) -> None:
    for _ in range(documents):
        insert_pending(world.url, uuid.UUID(world.subject), **kwargs)  # type: ignore[arg-type]


def test_a_subject_at_the_document_cap_answers_409(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_documents_per_subject=3)
    headers = auth(client, world.teacher)
    fill(world, 3)

    response = upload(client, headers, world.subject)

    assert response.status_code == 409
    assert response.json()["code"] == "DOCUMENT_QUOTA_EXCEEDED"
    assert count(clean_db, "documents") == 3


def test_every_status_counts_towards_the_document_cap(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_documents_per_subject=4)
    headers = auth(client, world.teacher)
    for status in ("pending", "processing", "ready", "failed"):
        insert_pending(world.url, uuid.UUID(world.subject), payload=None, status=status)

    assert upload(client, headers, world.subject).status_code == 409


def test_the_cap_is_per_subject(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_documents_per_subject=2)
    headers = auth(client, world.teacher)
    fill(world, 2)
    second_subject = scalar(
        clean_db,
        "INSERT INTO subjects (name, teacher_id) VALUES ('Second', :t) RETURNING id",
        t=uuid.UUID(world.teacher.id),
    )

    assert upload(client, headers, world.subject).status_code == 409
    assert upload(client, headers, str(second_subject)).status_code == 202


def test_space_freed_by_a_deletion_is_usable_at_once(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_documents_per_subject=2)
    headers = auth(client, world.teacher)
    first = upload(client, headers, world.subject)
    upload(client, headers, world.subject)
    assert upload(client, headers, world.subject).status_code == 409

    assert client.delete(
        document_url(world.subject, first.json()["id"]), headers=headers
    ).status_code == 204

    assert upload(client, headers, world.subject).status_code == 202


def test_a_full_queue_answers_503_with_retry_after(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, ingestion_queue_max=2)
    headers = auth(client, world.teacher)
    fill(world, 2)

    response = upload(client, headers, world.subject)

    assert response.status_code == 503
    assert response.json()["code"] == "INGESTION_QUEUE_FULL"
    assert int(response.headers["Retry-After"]) >= 1
    assert count(clean_db, "documents") == 2


def test_finished_jobs_do_not_count_towards_the_queue(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, ingestion_queue_max=2)
    headers = auth(client, world.teacher)
    for status in ("ready", "failed", "ready"):
        insert_pending(world.url, uuid.UUID(world.subject), payload=None, status=status)

    assert upload(client, headers, world.subject).status_code == 202


def test_too_many_pending_bytes_answer_503_and_store_nothing(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1, ingestion_pending_bytes_max_mb=1)
    headers = auth(client, world.teacher)
    fill(world, 1, payload=b"a" * 600_000, content_type="text/plain", filename="a.txt")

    response = upload(client, headers, world.subject, "b.txt", b"b" * 600_000)

    assert response.status_code == 503
    assert response.json()["code"] == "INGESTION_QUEUE_FULL"
    assert "Retry-After" in response.headers
    assert count(clean_db, "documents") == 1


def test_a_file_that_still_fits_the_pending_bytes_is_accepted(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1, ingestion_pending_bytes_max_mb=1)
    headers = auth(client, world.teacher)
    fill(world, 1, payload=b"a" * 400_000, content_type="text/plain", filename="a.txt")

    assert upload(client, headers, world.subject, "b.txt", b"b" * 600_000).status_code == 202


def test_an_obviously_full_queue_is_refused_before_the_body_is_read(clean_db: str) -> None:
    """The cheap early check: a client with a huge body gets the 503 without sending it."""
    world = make_world(clean_db)
    client = make_client(clean_db, ingestion_queue_max=1)
    headers = auth(client, world.teacher)
    fill(world, 1)
    read = {"bytes": 0}
    guard_scope_receive = client.app  # the application under test

    class Counting:
        def __init__(self, app: object) -> None:
            self.app = app

        async def __call__(self, scope: dict, receive: object, send: object) -> None:  # type: ignore[type-arg]
            async def counting(*_: object) -> dict:  # type: ignore[type-arg]
                message = await receive()  # type: ignore[operator]
                read["bytes"] += len(message.get("body", b""))
                return message  # type: ignore[no-any-return]

            await self.app(scope, counting, send)  # type: ignore[operator]

    counted = TestClient(Counting(guard_scope_receive), raise_server_exceptions=False)
    body = multipart_body(part("file", b"a" * 200_000, "a.txt"))

    response = raw_upload(counted, headers, world.subject, body, MULTIPART)

    assert response.status_code == 503
    assert response.json()["code"] == "INGESTION_QUEUE_FULL"
    assert read["bytes"] == 0


def test_too_many_uploads_in_flight_answer_503_with_retry_after(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, upload_max_in_flight=2)
    headers = auth(client, world.teacher)
    slots = client.app.state.upload_slots  # type: ignore[attr-defined]
    assert slots.try_acquire() and slots.try_acquire()  # two uploads being received

    refused = upload(client, headers, world.subject)
    slots.release()
    accepted = upload(client, headers, world.subject)

    assert refused.status_code == 503
    assert refused.json()["code"] == "INGESTION_QUEUE_FULL"
    assert int(refused.headers["Retry-After"]) >= 1
    assert accepted.status_code == 202
    assert slots.in_flight == 1  # the finished upload gave its slot back


@pytest.mark.parametrize("outcome", ["success", "413", "415", "422", "409", "404"])
def test_the_upload_slot_is_always_given_back(clean_db: str, outcome: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, max_upload_mb=1, max_documents_per_subject=1)
    headers = auth(client, world.teacher)
    slots = client.app.state.upload_slots  # type: ignore[attr-defined]
    if outcome == "409":
        fill(world, 1)

    if outcome == "success":
        upload(client, headers, world.subject)
    elif outcome == "413":
        upload(client, headers, world.subject, "big.txt", b"a" * (ONE_MB + 1))
    elif outcome == "415":
        upload(client, headers, world.subject, "x.exe", b"MZ")
    elif outcome == "422":
        upload(client, headers, world.subject, "empty.txt", b"")
    elif outcome == "409":
        upload(client, headers, world.subject)
    else:
        upload(client, headers, str(uuid.uuid4()))

    assert slots.in_flight == 0


def test_the_upload_rate_is_limited_per_client_with_retry_after(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, upload_rate_limit="2/minute")
    headers = auth(client, world.teacher)

    first = upload(client, headers, world.subject)
    second = upload(client, headers, world.subject)
    third = upload(client, headers, world.subject)

    assert (first.status_code, second.status_code) == (202, 202)
    assert third.status_code == 429
    assert third.json()["code"] == "RATE_LIMITED"
    assert int(third.headers["Retry-After"]) >= 1
    assert count(clean_db, "documents") == 2


def test_a_refused_request_does_not_use_the_upload_rate(clean_db: str) -> None:
    world = make_world(clean_db)
    client = make_client(clean_db, upload_rate_limit="1/minute")
    teacher = auth(client, world.teacher)

    assert upload(client, None, world.subject).status_code == 401
    assert upload(client, auth(client, world.student), world.subject).status_code == 403
    assert upload(client, teacher, str(uuid.uuid4())).status_code == 404
    assert upload(client, teacher, world.subject).status_code == 202


# --- listing ------------------------------------------------------------------------------------


def test_an_empty_subject_lists_an_empty_array(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = client.get(documents_url(world.subject), headers=teacher_headers)

    assert response.status_code == 200
    assert response.json() == []


def test_the_list_is_newest_first_with_the_state_of_every_document(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    ready, _ = insert_pending(world.url, uuid.UUID(world.subject), None, "ready", "ready.txt")
    failed, _ = insert_pending(world.url, uuid.UUID(world.subject), None, "failed", "failed.pdf")
    run(
        world.url,
        "UPDATE documents SET error_code = :c, error_message = :m WHERE id = :d",
        c=DocumentErrorCode.ENCRYPTED_PDF.value,
        m=DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.ENCRYPTED_PDF],
        d=failed,
    )
    insert_chunk(world.url, ready, uuid.UUID(world.subject))
    run(world.url, "UPDATE documents SET chunks_count = 1 WHERE id = :d", d=ready)
    pending = upload(client, teacher_headers, world.subject, "pending.txt").json()["id"]

    response = client.get(documents_url(world.subject), headers=teacher_headers)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [pending, str(failed), str(ready)]
    by_name = {item["filename"]: item for item in body}
    assert by_name["pending.txt"]["status"] == "pending"
    assert by_name["pending.txt"]["error_code"] is None
    assert by_name["ready.txt"]["status"] == "ready"
    assert by_name["ready.txt"]["chunks_count"] == 1
    assert by_name["failed.pdf"]["status"] == "failed"
    assert by_name["failed.pdf"]["error_code"] == "ENCRYPTED_PDF"
    assert by_name["failed.pdf"]["error_message"] == DOCUMENT_ERROR_MESSAGES[
        DocumentErrorCode.ENCRYPTED_PDF
    ]


def test_the_list_never_carries_content_embeddings_or_bytes(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    document, _ = insert_pending(
        world.url, uuid.UUID(world.subject), b"BYTES-MARKER-1", "ready", "a.txt"
    )
    insert_chunk(world.url, document, uuid.UUID(world.subject), content="CHUNK-MARKER-2")

    response = client.get(documents_url(world.subject), headers=teacher_headers)

    assert "BYTES-MARKER-1" not in response.text
    assert "CHUNK-MARKER-2" not in response.text
    assert "embedding" not in response.text
    assert "payload" not in response.text


def test_the_list_holds_only_the_documents_of_the_subject(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    mine, _ = insert_pending(world.url, uuid.UUID(world.subject), filename="mine.txt")
    insert_pending(world.url, uuid.UUID(world.other_subject), filename="theirs.txt")

    response = client.get(documents_url(world.subject), headers=teacher_headers)

    assert [item["id"] for item in response.json()] == [str(mine)]


def test_a_document_being_processed_shows_no_error_code(
    clean_db: str, client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    document, _ = insert_pending(world.url, uuid.UUID(world.subject))
    factory = create_session_factory(create_db_engine(clean_db))
    with factory() as session:
        assert IngestionJobRepository(session).claim(120, 3) is not None
        session.commit()

    item = client.get(documents_url(world.subject), headers=teacher_headers).json()[0]

    assert item["id"] == str(document)
    assert item["status"] == "processing"
    assert item["error_code"] is None


# --- deletion -----------------------------------------------------------------------------------


def test_deleting_a_ready_document_removes_everything_derived_from_it(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    document, _ = insert_pending(world.url, uuid.UUID(world.subject), None, "ready")
    insert_chunk(world.url, document, uuid.UUID(world.subject))

    response = client.delete(document_url(world.subject, document), headers=teacher_headers)

    assert response.status_code == 204
    assert response.content == b""
    assert stored(world.url) == NOTHING
    assert client.get(documents_url(world.subject), headers=teacher_headers).json() == []


def test_deleting_a_pending_document_removes_its_job_and_bytes(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    document = upload(client, teacher_headers, world.subject).json()["id"]

    response = client.delete(document_url(world.subject, document), headers=teacher_headers)

    assert response.status_code == 204
    assert stored(world.url) == NOTHING


def test_a_worker_whose_document_is_deleted_ends_without_writing(
    clean_db: str, client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    document, _ = insert_pending(world.url, uuid.UUID(world.subject))
    factory = create_session_factory(create_db_engine(clean_db))
    with factory() as session:
        job = IngestionJobRepository(session).claim(120, 3)
        session.commit()
    assert job is not None

    response = client.delete(document_url(world.subject, document), headers=teacher_headers)

    assert response.status_code == 204
    with factory() as session:
        repository = IngestionJobRepository(session)
        assert repository.renew(job.job_id, job.token, 120) is False
        assert repository.complete(job.job_id, job.token, [], []) is False
        session.rollback()
    assert stored(world.url) == NOTHING


def test_an_unknown_document_is_404(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    response = client.delete(document_url(world.subject, uuid.uuid4()), headers=teacher_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_a_second_delete_is_404(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    document = upload(client, teacher_headers, world.subject).json()["id"]
    url = document_url(world.subject, document)

    assert client.delete(url, headers=teacher_headers).status_code == 204
    assert client.delete(url, headers=teacher_headers).status_code == 404


def test_the_delete_is_committed_before_the_response(
    clean_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.endpoints import documents as router

    world = make_world(clean_db)
    client = make_client(clean_db)
    headers = auth(client, world.teacher)
    document = upload(client, headers, world.subject).json()["id"]
    seen: list[int] = []
    original = router.Response

    def probing(*args: object, **kwargs: object) -> object:
        seen.append(count(clean_db, "documents"))
        return original(*args, **kwargs)

    monkeypatch.setattr(router, "Response", probing)

    response = client.delete(document_url(world.subject, document), headers=headers)

    assert response.status_code == 204
    assert seen == [0]  # the other connection already saw the deletion


def test_other_methods_are_405(
    client: TestClient, world: World, teacher_headers: dict[str, str]
) -> None:
    for method in ("PUT", "PATCH"):
        response = client.request(method, documents_url(world.subject), headers=teacher_headers)
        assert response.status_code == 405


# --- the contract -------------------------------------------------------------------------------


def test_the_application_documents_the_routes_it_serves() -> None:
    app = create_app(
        build_settings("postgresql+psycopg://user:pw@localhost:5432/contract_test"),
        password_service=FAST_PASSWORDS,
    )
    paths = app.openapi()["paths"]
    collection = paths["/api/v1/subjects/{subject_id}/documents"]
    item = paths["/api/v1/subjects/{subject_id}/documents/{document_id}"]

    assert set(collection) == {"get", "post"}
    assert set(item) == {"delete"}
    assert collection["post"]["requestBody"]["required"] is True
    assert "multipart/form-data" in collection["post"]["requestBody"]["content"]
    assert [p["name"] for p in collection["post"]["parameters"]] == ["subject_id"]
    assert [p["name"] for p in item["delete"]["parameters"]] == ["subject_id", "document_id"]
