"""Real API and worker processes for the end-to-end tests (change 6, group 10).

The API is started with the production Uvicorn arguments (`--factory --no-proxy-headers`) on a free
port (never 8000 or 5173); a `script` runs the same entry point through `uvicorn.run` after the
test patched something inside the process (a delay, a hook), which is how a test pauses the server
between two steps and kills it there. Workers are `python -m app.worker` or a patched copy.
Everything needs Linux (the worker refuses to start elsewhere).
"""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from tests.constants import TEST_JWT_SECRET
from tests.integration.helpers import DEFAULT_PASSWORD

BACKEND = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"


def free_port() -> int:
    with closing(socket.socket()) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class Server:
    port: int
    temp_dir: Path
    log: Path
    process: subprocess.Popen[bytes]

    @property
    def pid(self) -> int:
        return self.process.pid

    def log_text(self) -> str:
        return self.log.read_text(errors="replace")


def base_environment(url: str, **extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in ("PATH", "HOME", "LANG")}
    env.update(
        APP_ENV="test",
        DATABASE_URL=url,
        JWT_SECRET=TEST_JWT_SECRET,
        EMBEDDER_BACKEND="fake",
        UPLOAD_RATE_LIMIT="10000/minute",
        LOGIN_RATE_LIMIT="10000/minute",
        PYTHONUNBUFFERED="1",
    )
    env.update(extra)
    return env


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


UVICORN_ARGS = ["--factory", "--no-proxy-headers", "--host", HOST]


@contextmanager
def running_server(url: str, script: str | None = None, **env: str) -> Iterator[Server]:
    """The API with the production arguments; `script` (Python source) replaces the command.

    The script receives the port in `PORT` and must end by starting the same application with the
    same arguments. The server's temporary directory is private to it.
    """
    port = free_port()
    with tempfile.TemporaryDirectory() as work:
        temp_dir = Path(work) / "tmp"
        temp_dir.mkdir()
        log = Path(work) / "server.log"
        environment = base_environment(url, TMPDIR=str(temp_dir), PORT=str(port), **env)
        command = (
            [sys.executable, "-c", script]
            if script
            else [sys.executable, "-m", "uvicorn", "app.main:app_factory", *UVICORN_ARGS]
            + ["--port", str(port)]
        )
        with log.open("wb") as sink:
            process = subprocess.Popen(  # noqa: S603 - fixed command, no outside input
                command,
                cwd=BACKEND,
                env=environment,
                stdout=sink,
                stderr=subprocess.STDOUT,
            )
            server = Server(port, temp_dir, log, process)
            try:
                wait_for_port(port, process)
                yield server
            finally:
                stop(process)


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def kill(process: subprocess.Popen[bytes]) -> None:
    """SIGKILL: no handler runs, nothing is flushed, nothing is rolled back by the process."""
    process.send_signal(signal.SIGKILL)
    process.wait(timeout=30)


@contextmanager
def running_worker(
    url: str, script: str | None = None, **env: str
) -> Iterator[subprocess.Popen[bytes]]:
    command = [sys.executable, "-c", script] if script else [sys.executable, "-m", "app.worker"]
    environment = base_environment(
        url,
        INGESTION_LEASE_SECONDS="3",
        INGESTION_JOB_DEADLINE_SECONDS="60",
        INGESTION_BATCH_SIZE="2",
        **env,
    )
    process = subprocess.Popen(  # noqa: S603 - fixed command, no outside input
        command,
        cwd=BACKEND,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=30)


# --- raw HTTP -----------------------------------------------------------------------------------


def connect(server: Server) -> socket.socket:
    return socket.create_connection((HOST, server.port), timeout=10)


@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> object:
        return json.loads(self.body)


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
    server: Server,
    method: str,
    path: str,
    token: str | None = None,
    body: bytes = b"",
    content_type: str = "application/json",
    timeout: float = 15,
) -> Reply:
    lines = [f"{method} {path} HTTP/1.1", f"Host: {HOST}", "Connection: close"]
    if token:
        lines.append(f"Authorization: Bearer {token}")
    if method in ("POST", "PUT"):
        lines += [f"Content-Type: {content_type}", f"Content-Length: {len(body)}"]
    with closing(connect(server)) as sock:
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode() + body)
        reply = read_reply(sock, timeout)
    assert reply is not None, f"no answer to {method} {path}"
    return reply


def login(server: Server, email: str) -> str:
    body = json.dumps({"email": email, "password": DEFAULT_PASSWORD}).encode()
    reply = request(server, "POST", "/api/v1/auth/login", body=body)
    assert reply.status == 200
    payload = reply.json()
    assert isinstance(payload, dict)
    return str(payload["access_token"])


def multipart_post(
    server: Server, path: str, token: str, body: bytes, content_type: str, timeout: float = 30
) -> Reply:
    return request(server, "POST", path, token, body, content_type, timeout)


def open_fds_in(server: Server, directory: Path) -> list[str]:
    """Files of `directory` that the server process still holds open (deleted or not)."""
    return [
        target
        for fd in Path(f"/proc/{server.pid}/fd").iterdir()
        if (target := os.readlink(fd)).startswith(str(directory))
    ]
