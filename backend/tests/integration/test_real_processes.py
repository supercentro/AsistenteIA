"""Real API and worker processes working together (change 6, task 10.2).

An API process (production arguments, free port) and `python -m app.worker` processes share the
test database. Everything goes through HTTP: upload, poll the list until `ready`, delete while a
worker is processing, kill a worker in the middle of a job and let another one finish it, restart
the API with `pending` documents, and exhaust the attempts so the sweep ends the document `failed`
with `PROCESSING_INTERRUPTED`. Linux only.
"""

import sys
import textwrap
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from subprocess import Popen

import pytest

from app.models.ingestion import DOCUMENT_ERROR_MESSAGES, DocumentErrorCode
from app.models.user import UserRole
from tests.ingestion_support import expire_lease
from tests.integration.helpers import insert_subject, insert_user
from tests.server_support import (
    Server,
    kill,
    login,
    request,
    running_server,
    running_worker,
)
from tests.service_support import LONG_TEXT, wait_until
from tests.sql_support import count, scalar
from tests.upload_support import MULTIPART, TEXT, multipart_body, part, stored

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="runs in the Linux container")

# A worker whose embedder blocks on every call after the start-up probe.
STUCK_WORKER = textwrap.dedent(
    """
    import time
    from app.rag import embedder

    original = embedder.FakeEmbedder.embed
    state = {"calls": 0}

    def slow(self, texts):
        state["calls"] += 1
        if state["calls"] > 1:
            time.sleep(SECONDS)
        return original(self, texts)

    embedder.FakeEmbedder.embed = slow
    from app.worker import main

    raise SystemExit(main())
    """
)


def slow_worker(seconds: int) -> str:
    return STUCK_WORKER.replace("SECONDS", str(seconds))


@dataclass(frozen=True)
class Scene:
    url: str
    email: str
    subject: str


@pytest.fixture
def scene(clean_db: str) -> Scene:
    teacher = insert_user(clean_db, f"t-{uuid.uuid4().hex[:6]}@example.com", UserRole.TEACHER)
    return Scene(clean_db, teacher.email, insert_subject(clean_db, teacher.id))


class Api:
    """A logged-in teacher talking to one API process."""

    def __init__(self, server: Server, scene: Scene) -> None:
        self.server = server
        self.scene = scene
        self.token = login(server, scene.email)
        self.path = f"/api/v1/subjects/{scene.subject}/documents"

    def upload(self, name: str = "notes.txt", content: bytes = LONG_TEXT) -> str:
        body = multipart_body(part("file", content, name))
        reply = request(self.server, "POST", self.path, self.token, body, MULTIPART)
        assert reply.status == 202, reply.body
        payload = reply.json()
        assert isinstance(payload, dict)
        return str(payload["id"])

    def documents(self) -> dict[str, dict[str, object]]:
        reply = request(self.server, "GET", self.path, self.token)
        assert reply.status == 200
        items = reply.json()
        assert isinstance(items, list)
        return {str(item["id"]): item for item in items}

    def state(self, document: str) -> str:
        item = self.documents().get(document)
        return str(item["status"]) if item else "gone"

    def delete(self, document: str) -> int:
        return request(self.server, "DELETE", f"{self.path}/{document}", self.token).status


@contextmanager
def api_for(scene: Scene, **env: str) -> Iterator[Api]:
    with running_server(scene.url, **env) as server:
        yield Api(server, scene)


def attempts(url: str, document: str) -> int:
    value = scalar(
        url,
        "SELECT attempts FROM ingestion_jobs WHERE document_id = CAST(:d AS uuid)",
        d=document,
    )
    return int(str(value))


def attempts_are(url: str, document: str, expected: int) -> bool:
    return attempts(url, document) == expected


def wait_status(api: Api, document: str, wanted: str, timeout: float = 60) -> None:
    assert wait_until(lambda: api.state(document) == wanted, timeout=timeout), api.state(document)


def test_upload_poll_until_ready_and_search_data_is_complete(scene: Scene) -> None:
    with api_for(scene) as api, running_worker(scene.url):
        document = api.upload()
        assert api.state(document) in {"pending", "processing", "ready"}

        wait_status(api, document, "ready")

        item = api.documents()[document]
    chunks = count(scene.url, "document_chunks")
    assert chunks > 1
    assert item["chunks_count"] == chunks
    assert item["error_code"] is None
    assert stored(scene.url)["payloads"] == 0  # the bytes were erased with the final transaction


def test_a_failed_document_shows_its_stable_code_through_the_api(scene: Scene) -> None:
    with api_for(scene) as api, running_worker(scene.url):
        document = api.upload("scan.pdf", b"%PDF-1.7 not really a pdf at all")

        wait_status(api, document, "failed")

        item = api.documents()[document]
    assert item["error_code"] in {code.value for code in DocumentErrorCode}
    assert item["error_message"] == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode(item["error_code"])]
    assert stored(scene.url)["payloads"] == 0


def test_a_delete_during_processing_ends_the_worker_without_writing(scene: Scene) -> None:
    with api_for(scene) as api:
        with running_worker(scene.url, slow_worker(5)) as worker:
            document = api.upload()
            wait_status(api, document, "processing")

            assert api.delete(document) == 204
            assert api.state(document) == "gone"

            # the worker comes back from its slow embedding, finds nothing and stays alive
            time.sleep(7)
            assert worker.poll() is None
            assert stored(scene.url) == {"documents": 0, "jobs": 0, "payloads": 0, "chunks": 0}
        with running_worker(scene.url):  # and the queue is healthy for the next document
            follow_up = api.upload()
            wait_status(api, follow_up, "ready")
    assert count(scene.url, "document_chunks") > 0


def test_a_worker_killed_in_the_middle_of_a_job_is_replaced_without_duplicates(
    scene: Scene,
) -> None:
    with api_for(scene) as api:
        with running_worker(scene.url, slow_worker(120)) as victim:
            document = api.upload()
            wait_status(api, document, "processing")
            kill(victim)
        assert count(scene.url, "document_chunks") == 0
        assert api.state(document) == "processing"  # the lease has not expired yet

        with running_worker(scene.url):
            wait_status(api, document, "ready")

        item = api.documents()[document]
    assert attempts(scene.url, document) == 2
    total = count(scene.url, "document_chunks")
    assert item["chunks_count"] == total
    indexes = scalar(
        scene.url,
        "SELECT string_agg(chunk_index::text, ',' ORDER BY chunk_index) FROM document_chunks",
    )
    assert indexes == ",".join(str(i) for i in range(total))


def test_pending_documents_survive_a_restart_of_the_api(scene: Scene) -> None:
    with api_for(scene) as first:
        documents = [first.upload(f"n{i}.txt") for i in range(3)]
        assert {first.state(d) for d in documents} == {"pending"}
        kill(first.server.process)  # no graceful shutdown

    assert stored(scene.url)["documents"] == 3
    with api_for(scene) as second, running_worker(scene.url):
        for document in documents:
            wait_status(second, document, "ready")
    assert count(scene.url, "document_chunks") >= 3


def test_exhausted_attempts_end_failed_with_processing_interrupted(scene: Scene) -> None:
    with api_for(scene) as api:
        document = api.upload()
        for expected in (1, 2, 3):
            with running_worker(scene.url, slow_worker(120)) as victim:
                assert wait_until(partial(attempts_are, scene.url, document, expected), timeout=60)
                wait_status(api, document, "processing")
                kill(victim)
            job = scalar(
                scene.url,
                "SELECT id FROM ingestion_jobs WHERE document_id = CAST(:d AS uuid)",
                d=document,
            )
            expire_lease(scene.url, uuid.UUID(str(job)))

        with running_worker(scene.url):  # the sweep at start fails it; nothing is processed
            wait_status(api, document, "failed")
        item = api.documents()[document]

    assert item["error_code"] == "PROCESSING_INTERRUPTED"
    assert (
        item["error_message"] == DOCUMENT_ERROR_MESSAGES[DocumentErrorCode.PROCESSING_INTERRUPTED]
    )
    assert attempts(scene.url, document) == 3
    assert stored(scene.url)["payloads"] == 0
    assert count(scene.url, "document_chunks") == 0


def test_isolation_between_teachers_holds_with_real_processes(scene: Scene) -> None:
    other = insert_user(scene.url, "other@example.com", UserRole.TEACHER)
    student = insert_user(scene.url, "student@example.com", UserRole.STUDENT)
    with api_for(scene) as api, running_worker(scene.url):
        document = api.upload()
        wait_status(api, document, "ready")

        intruder = login(api.server, other.email)
        pupil = login(api.server, student.email)
        for token, expected in ((intruder, 404), (pupil, 403)):
            assert request(api.server, "GET", api.path, token).status == expected
            assert request(api.server, "DELETE", f"{api.path}/{document}", token).status == expected
        assert request(api.server, "GET", api.path).status == 401
        assert api.state(document) == "ready"  # untouched by every refused attempt


def test_the_text_of_a_file_never_reaches_the_logs_of_either_process(scene: Scene) -> None:
    marker = "MARKER-PROCESS-LOG-9917"
    content = (marker + " " + TEXT.decode()).encode()
    with api_for(scene) as api:
        with running_worker(scene.url):
            document = api.upload(f"{marker}.txt", content)
            wait_status(api, document, "ready")
        log = api.server.log_text()
    assert marker not in log


def test_no_popen_is_left_running(scene: Scene) -> None:
    """The context managers stop every process they start (guards against a leaking test)."""
    started: list[Popen[bytes]] = []
    with api_for(scene) as api, running_worker(scene.url) as worker:
        started += [api.server.process, worker]
    assert all(p.poll() is not None for p in started)
