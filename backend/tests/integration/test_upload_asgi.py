"""The whole application driven at the ASGI level with a scripted client (change 6, task 9.2).

A scripted `receive` stands for a client that sends some bytes and then stalls, trickles or
disconnects. It proves the mapping of the guard's refusals to the `413` and `408` answers, that a
disconnect is absorbed without a response, a log line at error level or a stored row, and that the
upload slot always comes back. The same behaviours against a real Uvicorn are in
`test_upload_server.py`.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message

from tests.integration.helpers import build_app
from tests.upload_support import (
    BOUNDARY,
    MULTIPART,
    NOTHING,
    World,
    auth,
    documents_url,
    make_world,
    multipart_body,
    part,
    stored,
)

ONE_MB = 1024 * 1024


@dataclass
class Exchange:
    sent: list[Message] = field(default_factory=list)

    @property
    def status(self) -> int | None:
        starts = [m for m in self.sent if m["type"] == "http.response.start"]
        return int(starts[0]["status"]) if starts else None

    @property
    def json(self) -> dict[str, Any]:
        body = b"".join(m.get("body", b"") for m in self.sent if m["type"] == "http.response.body")
        loaded = json.loads(body)
        assert isinstance(loaded, dict)
        return loaded


def start_of_a_file() -> bytes:
    return (
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; filename="slow.txt"\r\n\r\n'
    ).encode() + b"a" * 100


async def call(
    app: FastAPI,
    world: World,
    token_headers: dict[str, str],
    script: Sequence[Message | float | Callable[[], None]],
    *,
    declared: int | None = None,
) -> Exchange:
    """Send one upload request whose body follows `script` (a number is a pause in seconds)."""
    headers = [(b"content-type", MULTIPART.encode()), (b"host", b"testserver")]
    headers += [(k.lower().encode(), v.encode()) for k, v in token_headers.items()]
    if declared is not None:
        headers.append((b"content-length", str(declared).encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": documents_url(world.subject),
        "raw_path": documents_url(world.subject).encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    queue = list(script)
    exchange = Exchange()

    async def receive() -> Message:
        while queue:
            item = queue.pop(0)
            if callable(item):
                item()
                continue
            if isinstance(item, (int, float)):
                await asyncio.sleep(item)
                continue
            return item
        await asyncio.sleep(3600)  # the client went silent
        raise AssertionError("unreachable")

    async def send(message: Message) -> None:
        exchange.sent.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=30)
    return exchange


def body_chunk(data: bytes, more: bool = True) -> Message:
    return {"type": "http.request", "body": data, "more_body": more}


@pytest.fixture
def world(clean_db: str) -> World:
    return make_world(clean_db)


def make_app(url: str, **overrides: object) -> FastAPI:
    settings: dict[str, object] = {
        "max_upload_mb": 1,
        "upload_body_idle_seconds": 1,
        "upload_body_timeout_seconds": 2,
    }
    settings.update(overrides)
    return build_app(url, **settings)


def token(app: FastAPI, world: World) -> dict[str, str]:
    return auth(TestClient(app), world.teacher)


def test_a_client_that_goes_silent_gets_408_and_nothing_is_stored(
    clean_db: str, world: World
) -> None:
    app = make_app(clean_db)
    headers = token(app, world)

    exchange = asyncio.run(call(app, world, headers, [body_chunk(start_of_a_file())]))

    assert exchange.status == 408
    assert exchange.json["code"] == "REQUEST_TIMEOUT"
    assert stored(clean_db) == NOTHING
    assert app.state.upload_slots.in_flight == 0


def test_a_slow_drip_gets_408_at_the_total_deadline(clean_db: str, world: World) -> None:
    app = make_app(clean_db)
    headers = token(app, world)
    script: list[Message | float] = [body_chunk(start_of_a_file())]
    for _ in range(40):
        script += [0.4, body_chunk(b"b")]  # always inside the idle window

    exchange = asyncio.run(call(app, world, headers, script))

    assert exchange.status == 408
    assert stored(clean_db) == NOTHING
    assert app.state.upload_slots.in_flight == 0


def test_an_undeclared_body_over_the_limit_is_413_without_reading_the_rest(
    clean_db: str, world: World
) -> None:
    app = make_app(clean_db)
    headers = token(app, world)
    script: list[Message | float] = [body_chunk(start_of_a_file())]
    script += [body_chunk(b"a" * 100_000) for _ in range(40)]  # 4 MB, announced by nobody

    exchange = asyncio.run(call(app, world, headers, script))

    assert exchange.status == 413
    assert exchange.json["code"] == "PAYLOAD_TOO_LARGE"
    assert stored(clean_db) == NOTHING
    assert app.state.upload_slots.in_flight == 0


def test_a_declared_length_over_the_limit_is_413_before_a_byte_is_read(
    clean_db: str, world: World
) -> None:
    app = make_app(clean_db)
    headers = token(app, world)

    exchange = asyncio.run(call(app, world, headers, [], declared=100 * ONE_MB))

    assert exchange.status == 413  # (the script is empty: asking for the body would block)
    assert stored(clean_db) == NOTHING


def test_a_disconnect_is_absorbed_without_a_trace_or_a_row(
    clean_db: str, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    app = make_app(clean_db)
    headers = token(app, world)
    caplog.clear()

    exchange = asyncio.run(
        call(app, world, headers, [body_chunk(start_of_a_file()), {"type": "http.disconnect"}])
    )

    assert stored(clean_db) == NOTHING
    assert app.state.upload_slots.in_flight == 0
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []
    text = " ".join(r.getMessage() + str(r.exc_info) for r in caplog.records)
    assert "ClientDisconnect" not in text
    assert "Traceback" not in text
    assert "slow.txt" not in text
    assert exchange.status in (None, 400)  # nothing is promised to a client that is gone


def test_a_disconnect_before_any_body_leaves_nothing(clean_db: str, world: World) -> None:
    app = make_app(clean_db)
    headers = token(app, world)

    asyncio.run(call(app, world, headers, [{"type": "http.disconnect"}]))

    assert stored(clean_db) == NOTHING
    assert app.state.upload_slots.in_flight == 0


def test_a_complete_body_still_gets_its_202(clean_db: str, world: World) -> None:
    app = make_app(clean_db)
    headers = token(app, world)
    body = multipart_body(part("file", b"hello", "ok.txt"))

    exchange = asyncio.run(
        call(app, world, headers, [body_chunk(body[:30]), 0.1, body_chunk(body[30:], False)])
    )

    assert exchange.status == 202
    assert exchange.json["size_bytes"] == 5
    assert stored(clean_db)["documents"] == 1
    assert app.state.upload_slots.in_flight == 0


def test_the_authorization_runs_before_a_single_byte_is_read(clean_db: str, world: World) -> None:
    app = make_app(clean_db)
    student = auth(TestClient(app), world.student)

    exchange = asyncio.run(call(app, world, student, [], declared=100 * ONE_MB))

    assert exchange.status == 403  # not 413, and the empty script was never asked for a byte


def test_the_api_engine_has_the_statement_and_idle_timeouts(clean_db: str) -> None:
    app = make_app(clean_db, db_statement_timeout_api_seconds=7)
    engine = app.state.session_factory.kw["bind"]

    with engine.connect() as connection:
        statement = connection.exec_driver_sql("SHOW statement_timeout").scalar()
        idle = connection.exec_driver_sql("SHOW idle_in_transaction_session_timeout").scalar()

    assert statement == "7s"
    assert idle == "30s"


def test_no_database_connection_or_transaction_is_held_while_the_body_is_read(
    clean_db: str, world: World
) -> None:
    from tests.service_support import activity, checked_out

    app = make_app(clean_db)
    headers = token(app, world)
    seen: list[tuple[int, int, int]] = []

    def probe() -> None:
        state = activity(clean_db)
        seen.append(
            (
                checked_out(app.state.session_factory.kw["bind"]),
                state.open_transactions,
                state.idle_in_transaction,
            )
        )

    exchange = asyncio.run(call(app, world, headers, [probe, body_chunk(start_of_a_file())]))

    assert exchange.status == 408  # the client then stalled
    assert seen == [(0, 0, 0)]  # no pooled connection, no transaction, nothing idle in one
