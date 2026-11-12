"""The API against a real Uvicorn process (change 6, task 10.1).

Completes the real-server checks started in `test_upload_server.py` (early 413, 408 to connected
clients, disconnects): abusive multipart structures answered `422` quickly, many slow clients,
`202` only after the commit with the process killed between the steps, the order of the dependency
exit and the response, and temporary files that do not accumulate. The server runs with the
production arguments on a free port (never 8000 or 5173). Linux only.
"""

import os
import socket
import sys
import textwrap
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.models.user import UserRole
from tests.integration.helpers import insert_subject, insert_user
from tests.server_support import (
    HOST,
    Reply,
    Server,
    connect,
    kill,
    login,
    multipart_post,
    open_fds_in,
    read_reply,
    request,
    running_server,
)
from tests.service_support import wait_until
from tests.sql_support import count, scalar
from tests.upload_support import BOUNDARY, MULTIPART, NOTHING, TEXT, multipart_body, part, stored

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="runs in the Linux container")

ONE_MB = 1024 * 1024
IDLE_SECONDS = 1
TOTAL_SECONDS = 3
IN_FLIGHT = 4


@dataclass(frozen=True)
class Scene:
    server: Server
    url: str
    token: str
    subject: str
    email: str

    @property
    def path(self) -> str:
        return f"/api/v1/subjects/{self.subject}/documents"


def make_scene(server: Server, url: str) -> Scene:
    teacher = insert_user(url, f"t-{uuid.uuid4().hex[:6]}@example.com", UserRole.TEACHER)
    subject = insert_subject(url, teacher.id)
    return Scene(server, url, login(server, teacher.email), subject, teacher.email)


@pytest.fixture(scope="module")
def server(migrated_db: str) -> Iterator[Server]:
    with running_server(
        migrated_db,
        MAX_UPLOAD_MB="2",
        INGESTION_PENDING_BYTES_MAX_MB="100",
        UPLOAD_BODY_IDLE_SECONDS=str(IDLE_SECONDS),
        UPLOAD_BODY_TIMEOUT_SECONDS=str(TOTAL_SECONDS),
        UPLOAD_MAX_IN_FLIGHT=str(IN_FLIGHT),
    ) as running:
        yield running


@pytest.fixture
def scene(server: Server, clean_db: str) -> Scene:
    return make_scene(server, clean_db)


def head(scene: Scene, length: int) -> bytes:
    return (
        f"POST {scene.path} HTTP/1.1\r\nHost: {HOST}\r\nAuthorization: Bearer {scene.token}\r\n"
        f"Content-Type: {MULTIPART}\r\nContent-Length: {length}\r\n\r\n"
    ).encode()


def start_of_a_file() -> bytes:
    return (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="slow.txt"\r\n\r\n'
    ).encode() + b"a" * 100


def settled(scene: Scene) -> None:
    """No temporary file of the server process is left, on disk or held open."""
    assert wait_until(
        lambda: (
            list(scene.server.temp_dir.iterdir()) == []
            and open_fds_in(scene.server, scene.server.temp_dir) == []
        ),
        timeout=5,
    ), open_fds_in(scene.server, scene.server.temp_dir)


# --- abusive multipart structures --------------------------------------------------------------


def abusive_bodies() -> dict[str, tuple[bytes, str]]:
    return {
        "500-fields": (multipart_body(*[part(f"f{i}", b"x") for i in range(500)]), MULTIPART),
        "100-files": (
            multipart_body(*[part("file", TEXT, f"n{i}.txt") for i in range(100)]),
            MULTIPART,
        ),
        "huge-header": (
            f"--{BOUNDARY}\r\nX-H: ".encode() + b"h" * 200_000 + b"\r\n\r\n",
            MULTIPART,
        ),
        "no-boundary": (b"--x\r\n\r\n", "multipart/form-data"),
        "truncated": (f"--{BOUNDARY}\r\nContent-Disp".encode(), MULTIPART),
        "binary-garbage": (os.urandom(100_000), MULTIPART),
        "json": (b'{"file": "x"}', "application/json"),
    }


@pytest.mark.parametrize("name", list(abusive_bodies()))
def test_an_abusive_multipart_structure_is_422_quickly(scene: Scene, name: str) -> None:
    body, content_type = abusive_bodies()[name]
    started = time.monotonic()

    reply = multipart_post(scene.server, scene.path, scene.token, body, content_type)

    assert time.monotonic() - started < 2
    assert reply.status == 422, name
    payload = reply.json()
    assert isinstance(payload, dict)
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["details"]["reason"] in {"MALFORMED_MULTIPART", "FILE_PART_MISSING"}
    assert stored(scene.url) == NOTHING
    settled(scene)


# --- many slow clients -------------------------------------------------------------------------


def test_many_slow_clients_get_a_fast_503_or_a_408_and_nothing_is_left(scene: Scene) -> None:
    server = scene.server
    sockets: list[socket.socket] = []
    try:
        for _ in range(60):
            sock = connect(server)
            sock.sendall(head(scene, ONE_MB) + start_of_a_file())
            sockets.append(sock)
        started = time.monotonic()
        refused = [read_reply(sock, 3) for sock in sockets]
        elapsed = time.monotonic() - started
        health = time.monotonic()
        assert request(server, "GET", "/api/v1/health").status == 200
        health = time.monotonic() - health
        statuses = [r.status if r else None for r in refused]
        fast_503 = [s for s in statuses if s == 503]
        timed_out = [s for s in statuses if s == 408]
        # four uploads hold the slots (and then time out), the rest are refused at once
        assert len(fast_503) >= 60 - IN_FLIGHT - 1, statuses
        assert len(timed_out) + len(fast_503) == len([s for s in statuses if s]), statuses
        assert health < 1.5
        assert elapsed < TOTAL_SECONDS + 4
    finally:
        for sock in sockets:
            sock.close()
    assert wait_until(lambda: stored(scene.url) == NOTHING, timeout=5)
    body = multipart_body(part("file", TEXT, "after.txt"))
    assert request(server, "POST", scene.path, scene.token, body, MULTIPART).status == 202
    settled(scene)


# --- temporary files do not accumulate ---------------------------------------------------------


def test_temporary_files_do_not_accumulate_over_mixed_uploads(scene: Scene) -> None:
    big = multipart_body(part("file", b"a" * (ONE_MB + ONE_MB // 2), "big.txt"))  # spools to disk
    over = multipart_body(part("file", b"a" * (2 * ONE_MB + 1), "over.txt"))
    bad_type = multipart_body(part("file", b"MZ" + b"a" * (ONE_MB + 10), "x.exe"))
    two = multipart_body(part("file", b"a" * ONE_MB, "a.txt"), part("file", b"b", "b.txt"))
    plan = [big, over, bad_type, two] * 5

    def send(body: bytes) -> int:
        return multipart_post(scene.server, scene.path, scene.token, body, MULTIPART).status

    with closing(connect(scene.server)):  # (one idle connection must not matter)
        results: list[int] = []
        threads = [
            threading.Thread(target=lambda body=body: results.append(send(body))) for body in plan
        ]
        for thread in threads:
            thread.start()
            time.sleep(0.05)
        for thread in threads:
            thread.join()

    assert set(results) <= {202, 413, 415, 422, 503}
    assert 202 in results
    settled(scene)


# --- 202 only after the commit: the process is killed between the steps ------------------------

PAUSE_SERVER = textwrap.dedent(
    """
    import os, time
    from sqlalchemy import event
    import app.main as main

    FLAG = os.environ["PAUSE_FLAG"]
    MODE = os.environ["PAUSE_AT"]
    real_create_app = main.create_app

    def create_app(*args, **kwargs):
        app = real_create_app(*args, **kwargs)
        engine = app.state.session_factory.kw["bind"]
        if MODE == "before_commit":
            @event.listens_for(engine, "commit")
            def hold(connection):
                if os.path.exists(FLAG):
                    open(FLAG + ".reached", "w").close()
                    time.sleep(600)
        else:
            from app.schemas import document
            original = document.Document.model_validate.__func__

            def slow(cls, *args, **kwargs):
                if os.path.exists(FLAG):
                    open(FLAG + ".reached", "w").close()
                    time.sleep(600)
                return original(cls, *args, **kwargs)

            document.Document.model_validate = classmethod(slow)
        return app

    main.create_app = create_app
    import uvicorn
    uvicorn.run("app.main:app_factory", factory=True, proxy_headers=False,
                host="127.0.0.1", port=int(os.environ["PORT"]))
    """
)


def paused_upload(url: str, mode: str, tmp_path: Path) -> tuple[Reply | None, Scene, Server]:
    """Upload against a server that stops at `mode`, wait until it is there, then kill it."""
    flag = tmp_path / "pause.flag"
    with running_server(url, PAUSE_SERVER, PAUSE_AT=mode, PAUSE_FLAG=str(flag)) as server:
        scene = make_scene(server, url)
        flag.write_text("go")
        sock = connect(server)
        body = multipart_body(part("file", TEXT, "durable.txt"))
        sock.sendall(head(scene, len(body)) + body)
        assert wait_until(lambda: Path(str(flag) + ".reached").exists(), timeout=30)
        before = stored(url)
        early_reply = read_reply(sock, 1.0)  # nothing may arrive while the server is paused
        kill(server.process)
        late_reply = read_reply(sock, 2.0)  # and nothing arrives from a dead process
        sock.close()
        assert early_reply is None
        assert before is not None
        return late_reply, scene, server


def test_killed_before_the_commit_the_client_has_no_202_and_nothing_remains(
    clean_db: str, tmp_path: Path
) -> None:
    reply, _, _ = paused_upload(clean_db, "before_commit", tmp_path)

    assert reply is None
    assert stored(clean_db) == NOTHING  # the uncommitted transaction died with the process


def test_killed_after_the_commit_and_before_the_response_the_promise_holds(
    clean_db: str, tmp_path: Path
) -> None:
    reply, _, _ = paused_upload(clean_db, "after_commit", tmp_path)

    assert reply is None  # the client never saw a 202 ...
    assert stored(clean_db) == {"documents": 1, "jobs": 1, "payloads": 1, "chunks": 0}
    state = scalar(clean_db, "SELECT status::text FROM documents")
    assert state == "pending"  # ... but the document is durable and a worker will take it


def test_the_rows_are_visible_before_the_response_leaves_the_server(
    clean_db: str, tmp_path: Path
) -> None:
    """While the server is paused after the commit, another connection already sees everything."""
    flag = tmp_path / "pause.flag"
    with running_server(clean_db, PAUSE_SERVER, PAUSE_AT="after_commit", PAUSE_FLAG=str(flag)) as s:
        scene = make_scene(s, clean_db)
        flag.write_text("go")
        sock = connect(s)
        body = multipart_body(part("file", TEXT, "visible.txt"))
        sock.sendall(head(scene, len(body)) + body)
        assert wait_until(lambda: Path(str(flag) + ".reached").exists(), timeout=30)

        visible = stored(clean_db)
        reply = read_reply(sock, 0.5)
        kill(s.process)
        sock.close()

    assert visible == {"documents": 1, "jobs": 1, "payloads": 1, "chunks": 0}
    assert reply is None


# --- the order of the dependency exit and the response ------------------------------------------

EXIT_SERVER = textwrap.dedent(
    """
    import os, time
    import app.main as main
    from app.api import deps
    from fastapi import Request

    STAMP = os.environ["EXIT_STAMP"]
    original = deps.get_db
    real_create_app = main.create_app

    def slow_get_db(request: Request):
        generator = original(request)
        session = next(generator)
        try:
            yield session
        except BaseException as error:
            generator.throw(error)
            return
        time.sleep(2)  # the exit of the dependency (and the commit of get_db) is late
        if request.method == "DELETE":
            with open(STAMP, "w") as handle:
                handle.write(str(time.time()))
        try:
            next(generator)
        except StopIteration:
            pass

    def create_app(*args, **kwargs):
        app = real_create_app(*args, **kwargs)
        app.dependency_overrides[deps.get_db] = slow_get_db
        return app

    main.create_app = create_app
    import uvicorn
    uvicorn.run("app.main:app_factory", factory=True, proxy_headers=False,
                host="127.0.0.1", port=int(os.environ["PORT"]))
    """
)


def test_the_response_leaves_before_the_dependency_exit_so_the_delete_commits_first(
    clean_db: str, tmp_path: Path
) -> None:
    """Pins the order of FastAPI 0.162: the response is sent, then the `yield` dependency exits.

    That is why the delete (like the upload) commits explicitly before building its answer: at
    the moment the client has its `204` the deletion is already durable, whatever happens to the
    exit of the dependency afterwards.
    """
    stamp = tmp_path / "exit.stamp"
    with running_server(clean_db, EXIT_SERVER, EXIT_STAMP=str(stamp)) as server:
        scene = make_scene(server, clean_db)
        body = multipart_body(part("file", TEXT, "gone.txt"))
        uploaded = request(server, "POST", scene.path, scene.token, body, MULTIPART)
        assert uploaded.status == 202
        payload = uploaded.json()
        assert isinstance(payload, dict)
        document = payload["id"]

        started = time.monotonic()
        reply = request(server, "DELETE", f"{scene.path}/{document}", scene.token)
        answered = time.monotonic() - started
        gone = count(clean_db, "documents")
        exit_done_at_reply = stamp.exists()

        assert wait_until(stamp.exists, timeout=10)  # the exit does happen, later

    assert reply.status == 204
    assert answered < 1.5  # the exit takes 2 s: the response did not wait for it
    assert exit_done_at_reply is False
    assert gone == 0  # and the deletion was already committed when the client had its 204
