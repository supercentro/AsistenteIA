"""The upload guard against a real Uvicorn process (change 6, tasks 9.2 and 9.3).

Behaviour that depends on the server, the transport and the production arguments cannot be proved
with `TestClient` (base standards, section 9.2): an early `413` while the client is still sending,
a `408` delivered to a client that stays connected, a disconnect that leaves nothing behind and no
trace in the logs, and other endpoints that keep answering during slow uploads. The server is
started with the production arguments on a free port (never 8000 or 5173). The complete set of
real-server checks (task 10.1) is a later group.

Linux only: the application is meant to run in the Linux container and the temporary directory of
the server process is inspected.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.models.user import UserRole
from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import DEFAULT_PASSWORD, insert_subject, insert_user
from tests.sql_support import count
from tests.upload_support import BOUNDARY, MULTIPART, NOTHING, TEXT, multipart_body, part, stored

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="runs in the Linux container")

BACKEND = Path(__file__).resolve().parents[2]
ONE_MB = 1024 * 1024
HOST = "127.0.0.1"
IDLE_SECONDS = 1
TOTAL_SECONDS = 3
IN_FLIGHT = 4


def free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class Server:
    port: int
    temp_dir: Path
    log: Path


def wait_for_port(port: int, process: subprocess.Popen[bytes], timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert process.poll() is None, "the server stopped while starting"
        try:
            with closing(socket.create_connection((HOST, port), timeout=0.5)):
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError("the server did not start")


@pytest.fixture(scope="module")
def server(migrated_db: str) -> Iterator[Server]:
    port = free_port()
    with tempfile.TemporaryDirectory() as work:
        temp_dir = Path(work) / "tmp"
        temp_dir.mkdir()
        log = Path(work) / "server.log"
        env = {key: value for key, value in os.environ.items() if key in ("PATH", "HOME", "LANG")}
        env.update(
            APP_ENV="test",
            DATABASE_URL=migrated_db,
            JWT_SECRET=TEST_JWT_SECRET,
            MAX_UPLOAD_MB="1",
            INGESTION_PENDING_BYTES_MAX_MB="50",
            UPLOAD_BODY_IDLE_SECONDS=str(IDLE_SECONDS),
            UPLOAD_BODY_TIMEOUT_SECONDS=str(TOTAL_SECONDS),
            UPLOAD_MAX_IN_FLIGHT=str(IN_FLIGHT),
            UPLOAD_RATE_LIMIT="10000/minute",
            LOGIN_RATE_LIMIT="10000/minute",
            TMPDIR=str(temp_dir),
            PYTHONUNBUFFERED="1",
        )
        with log.open("wb") as sink:
            process = subprocess.Popen(  # noqa: S603 - fixed command, production arguments
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app_factory",
                    "--factory",
                    "--no-proxy-headers",
                    "--host",
                    HOST,
                    "--port",
                    str(port),
                ],
                cwd=BACKEND,
                env=env,
                stdout=sink,
                stderr=subprocess.STDOUT,
            )
            try:
                wait_for_port(port, process)
                yield Server(port, temp_dir, log)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


# --- raw HTTP -----------------------------------------------------------------------------------


def connect(server: Server) -> socket.socket:
    return socket.create_connection((HOST, server.port), timeout=10)


@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, object]:
        loaded = json.loads(self.body)
        assert isinstance(loaded, dict)
        return loaded


def read_reply(sock: socket.socket, timeout: float) -> Reply | None:
    """The next response on the socket, or None if none arrives within `timeout`."""
    sock.settimeout(timeout)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(65536)
            if not chunk:
                return None
            data += chunk
        head, _, rest = data.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        status = int(lines[0].split()[1])
        headers = {k.lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:])}
        length = int(headers.get("content-length", "0"))
        while len(rest) < length:
            more = sock.recv(65536)
            if not more:
                break
            rest += more
        return Reply(status, headers, rest[:length])
    except (TimeoutError, ConnectionError):
        return None


def request(
    server: Server, method: str, path: str, token: str | None = None, body: bytes = b""
) -> Reply:
    headers = [f"{method} {path} HTTP/1.1", f"Host: {HOST}", "Connection: close"]
    if token:
        headers.append(f"Authorization: Bearer {token}")
    if method in ("POST", "PUT"):
        headers += ["Content-Type: application/json", f"Content-Length: {len(body)}"]
    with closing(connect(server)) as sock:
        sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode() + body)
        reply = read_reply(sock, 15)
    assert reply is not None
    return reply


def login(server: Server, email: str) -> str:
    body = json.dumps({"email": email, "password": DEFAULT_PASSWORD}).encode()
    reply = request(server, "POST", "/api/v1/auth/login", body=body)
    assert reply.status == 200
    return str(reply.json()["access_token"])


@dataclass(frozen=True)
class Scene:
    server: Server
    url: str
    token: str
    subject: str

    @property
    def path(self) -> str:
        return f"/api/v1/subjects/{self.subject}/documents"


@pytest.fixture
def scene(server: Server, clean_db: str) -> Scene:
    teacher = insert_user(clean_db, f"t-{uuid.uuid4().hex[:6]}@example.com", UserRole.TEACHER)
    subject = insert_subject(clean_db, teacher.id)
    return Scene(server, clean_db, login(server, teacher.email), subject)


def upload_head(scene: Scene, *, length: int | None, chunked: bool = False) -> bytes:
    lines = [
        f"POST {scene.path} HTTP/1.1",
        f"Host: {HOST}",
        f"Authorization: Bearer {scene.token}",
        f"Content-Type: {MULTIPART}",
    ]
    if chunked:
        lines.append("Transfer-Encoding: chunked")
    elif length is not None:
        lines.append(f"Content-Length: {length}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def beginning_of_a_file() -> bytes:
    return (
        f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; "
        'filename="slow.txt"\r\n\r\n'
    ).encode() + b"a" * 100


def quiet(scene: Scene) -> None:
    """No temporary file is left in the server process's temporary directory."""
    time.sleep(0.3)
    assert list(scene.server.temp_dir.iterdir()) == []


# --- the size limit ------------------------------------------------------------------------------


def test_a_declared_length_above_the_limit_is_413_before_any_body_is_sent(scene: Scene) -> None:
    with closing(connect(scene.server)) as sock:
        sock.sendall(upload_head(scene, length=50 * ONE_MB))  # and no body at all

        reply = read_reply(sock, 5)

    assert reply is not None
    assert reply.status == 413
    assert reply.json()["code"] == "PAYLOAD_TOO_LARGE"
    assert stored(scene.url) == NOTHING
    quiet(scene)


def test_a_chunked_body_above_the_limit_is_413_while_the_client_is_still_sending(
    scene: Scene,
) -> None:
    chunk = b"a" * 65_536
    framed = f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n"
    sent = 0
    reply = None
    with closing(connect(scene.server)) as sock:
        sock.sendall(upload_head(scene, length=None, chunked=True))
        sock.sendall(
            f"{len(beginning_of_a_file()):x}\r\n".encode() + beginning_of_a_file() + b"\r\n"
        )
        started = time.monotonic()
        while sent < 20 * ONE_MB and time.monotonic() - started < 30:
            try:
                sock.sendall(framed)
            except (BrokenPipeError, ConnectionError):
                break
            sent += len(chunk)
            reply = read_reply(sock, 0.001)
            if reply is not None:
                break
        if reply is None:
            reply = read_reply(sock, 5)

    assert reply is not None
    assert reply.status == 413
    assert sent < 4 * ONE_MB  # the server did not wait for the rest of a 20 MB body
    assert stored(scene.url) == NOTHING
    quiet(scene)


def test_a_valid_upload_over_a_raw_connection_is_accepted_and_the_size_is_what_arrived(
    scene: Scene,
) -> None:
    """The guard is not too eager: an ordinary upload still gets its `202`."""
    body = multipart_body(part("file", TEXT, "ok.txt"))
    head = upload_head(scene, length=len(body))
    with closing(connect(scene.server)) as sock:
        sock.sendall(head + body)

        reply = read_reply(sock, 10)

    assert reply is not None
    assert reply.status == 202
    assert reply.json()["size_bytes"] == len(TEXT)
    assert stored(scene.url)["documents"] == 1
    quiet(scene)


def test_a_large_valid_upload_spools_to_disk_and_leaves_nothing_behind(scene: Scene) -> None:
    body = multipart_body(part("file", b"a" * (ONE_MB - 1024), "big.txt"))
    with closing(connect(scene.server)) as sock:
        sock.sendall(upload_head(scene, length=len(body)) + body)

        reply = read_reply(sock, 20)

    assert reply is not None
    assert reply.status == 202
    quiet(scene)


# --- deadlines ----------------------------------------------------------------------------------


def test_an_idle_client_that_stays_connected_gets_408(scene: Scene) -> None:
    with closing(connect(scene.server)) as sock:
        sock.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
        started = time.monotonic()

        reply = read_reply(sock, 15)
        elapsed = time.monotonic() - started

    assert reply is not None
    assert reply.status == 408
    assert reply.json()["code"] == "REQUEST_TIMEOUT"
    assert IDLE_SECONDS * 0.8 <= elapsed < TOTAL_SECONDS + 3  # about the idle limit
    assert stored(scene.url) == NOTHING
    quiet(scene)


def test_a_slow_drip_that_never_idles_gets_408_at_the_total_deadline(scene: Scene) -> None:
    reply = None
    with closing(connect(scene.server)) as sock:
        sock.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
        started = time.monotonic()
        while time.monotonic() - started < TOTAL_SECONDS * 4:
            try:
                sock.sendall(b"b")
            except (BrokenPipeError, ConnectionError):
                break
            reply = read_reply(sock, IDLE_SECONDS / 2)  # a byte inside every idle window
            if reply is not None:
                break
        elapsed = time.monotonic() - started

    assert reply is not None
    assert reply.status == 408
    assert TOTAL_SECONDS * 0.8 <= elapsed < TOTAL_SECONDS + 4
    assert stored(scene.url) == NOTHING
    quiet(scene)


def test_a_client_that_disconnects_leaves_nothing_and_no_trace(
    scene: Scene, server: Server
) -> None:
    before = server.log.read_text(errors="replace")
    with closing(connect(scene.server)) as sock:
        sock.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
        time.sleep(0.3)
    time.sleep(TOTAL_SECONDS + 1)  # longer than every deadline: the abandoned request is over

    assert stored(scene.url) == NOTHING
    quiet(scene)
    new_log = server.log.read_text(errors="replace")[len(before) :]
    for forbidden in ("Traceback", "ClientDisconnect", "Exception", "slow.txt", "aaaa"):
        assert forbidden not in new_log, forbidden
    assert request(server, "GET", "/api/v1/health").status == 200  # and the server is fine


def test_many_disconnects_leave_the_server_healthy(scene: Scene, server: Server) -> None:
    for _ in range(12):
        with closing(connect(scene.server)) as sock:
            sock.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
    time.sleep(TOTAL_SECONDS + 1)

    assert stored(scene.url) == NOTHING
    assert request(server, "GET", "/api/v1/health").status == 200
    quiet(scene)


# --- other requests during slow uploads ---------------------------------------------------------


def test_other_endpoints_keep_answering_while_slow_uploads_are_in_progress(
    scene: Scene, server: Server
) -> None:
    slow: list[socket.socket] = []
    stalled: list[socket.socket] = []
    try:
        for _ in range(IN_FLIGHT):  # these hold every upload slot
            sock = connect(server)
            sock.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
            slow.append(sock)
        for _ in range(20):  # and these have not even finished their headers
            sock = connect(server)
            sock.sendall(f"POST {scene.path} HTTP/1.1\r\nHost: x\r\n".encode())
            stalled.append(sock)
        time.sleep(0.3)
        timings: list[float] = []
        for path in (
            "/api/v1/health",
            "/api/v1/subjects",
            scene.path,
            "/api/v1/health",
            "/api/v1/users/me",
        ):
            started = time.monotonic()
            reply = request(server, "GET", path, token=scene.token)
            timings.append(time.monotonic() - started)
            assert reply.status == 200, path
        login_started = time.monotonic()
        login(server, _email_of(scene))
        timings.append(time.monotonic() - login_started)

        extra = connect(server)
        try:
            extra.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
            refused = read_reply(extra, 5)
        finally:
            extra.close()
    finally:
        for sock in (*slow, *stalled):
            sock.close()

    assert max(timings) < 1.5, timings
    assert refused is not None
    assert refused.status == 503  # no slot is free for a fifth upload
    assert refused.json()["code"] == "INGESTION_QUEUE_FULL"
    assert int(refused.headers["retry-after"]) >= 1
    assert stored(scene.url) == NOTHING


def _email_of(scene: Scene) -> str:
    from tests.sql_support import scalar

    return str(scalar(scene.url, "SELECT email FROM users LIMIT 1"))


def test_the_slots_come_back_after_the_slow_uploads_end(scene: Scene, server: Server) -> None:
    sockets = []
    for _ in range(IN_FLIGHT):
        sock = connect(server)
        sock.sendall(upload_head(scene, length=ONE_MB // 2) + beginning_of_a_file())
        sockets.append(sock)
    try:
        replies = [read_reply(sock, TOTAL_SECONDS + 5) for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()

    assert [r.status if r else None for r in replies] == [408] * IN_FLIGHT
    body = multipart_body(part("file", TEXT, "after.txt"))
    with closing(connect(server)) as sock:
        sock.sendall(upload_head(scene, length=len(body)) + body)
        reply = read_reply(sock, 10)
    assert reply is not None
    assert reply.status == 202
    assert count(scene.url, "documents") == 1
