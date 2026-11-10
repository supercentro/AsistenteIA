"""Temporary files and forms are closed explicitly, not by garbage collection (review of 9).

Starlette spools every file part into a `SpooledTemporaryFile`. These tests replace that class with
a tracking subclass that the test keeps referenced, so nothing can be closed by CPython releasing
the last reference: every file opened during a request must be closed by the code under test, on
success and on every failure (rejections, a timeout, an oversize body, a disconnect).
"""

import asyncio
import tempfile
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_upload_asgi import body_chunk, call, make_app, start_of_a_file
from tests.upload_support import (
    MULTIPART,
    PDF,
    TEXT,
    World,
    auth,
    make_world,
    multipart_body,
    part,
    raw_upload,
    upload,
)

ONE_MB = 1024 * 1024


@pytest.fixture
def tracked(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """Every spooled file Starlette opens, kept alive so only an explicit close can close it."""
    opened: list[Any] = []

    class Tracking(tempfile.SpooledTemporaryFile):  # type: ignore[type-arg]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            opened.append(self)

    monkeypatch.setattr("starlette.formparsers.SpooledTemporaryFile", Tracking)
    yield opened


@pytest.fixture
def world(clean_db: str) -> World:
    return make_world(clean_db)


def client_for(url: str, **overrides: object) -> TestClient:
    return TestClient(make_app(url, **overrides), raise_server_exceptions=False)


def assert_all_closed(opened: list[Any]) -> None:
    assert opened, "the scenario opened no spooled file: it proves nothing"
    assert [f for f in opened if not f.closed] == []


def test_a_successful_upload_closes_its_files(
    clean_db: str, world: World, tracked: list[Any]
) -> None:
    client = client_for(clean_db)

    assert upload(client, auth(client, world.teacher), world.subject).status_code == 202

    assert_all_closed(tracked)


def test_a_large_file_that_rolled_to_disk_is_closed(
    clean_db: str, world: World, tracked: list[Any]
) -> None:
    client = client_for(clean_db, max_upload_mb=3)

    response = upload(
        client, auth(client, world.teacher), world.subject, "big.txt", b"a" * (2 * ONE_MB)
    )

    assert response.status_code == 202
    assert any(f._rolled for f in tracked)  # it really went to a temporary file on disk
    assert_all_closed(tracked)


@pytest.mark.parametrize(
    "kind", ["415", "422-empty", "422-two-files", "422-extra-field", "413-file", "409", "503"]
)
def test_every_rejection_after_the_parse_closes_its_files(
    clean_db: str, world: World, tracked: list[Any], kind: str
) -> None:
    client = client_for(clean_db, max_upload_mb=1, max_documents_per_subject=1)
    headers = auth(client, world.teacher)
    if kind == "415":
        response = upload(client, headers, world.subject, "x.exe", b"MZ")
    elif kind == "422-empty":
        response = upload(client, headers, world.subject, "e.txt", b"")
    elif kind == "422-two-files":
        body = multipart_body(part("file", TEXT, "a.txt"), part("file", TEXT, "b.txt"))
        response = raw_upload(client, headers, world.subject, body, MULTIPART)
    elif kind == "422-extra-field":
        body = multipart_body(part("file", TEXT, "a.txt"), part("x", b"y"))
        response = raw_upload(client, headers, world.subject, body, MULTIPART)
    elif kind == "413-file":
        response = upload(client, headers, world.subject, "b.txt", b"a" * (ONE_MB + 1))
    elif kind == "409":
        assert upload(client, headers, world.subject, "a.pdf", PDF).status_code == 202
        tracked.clear()
        tracked.extend([])  # (the first upload is not under test)
        response = upload(client, headers, world.subject)
    else:
        engine = client.app.state.session_factory.kw["bind"]  # type: ignore[attr-defined]
        from sqlalchemy import event
        from sqlalchemy.exc import OperationalError

        @event.listens_for(engine, "commit")
        def boom(connection: object) -> None:
            raise OperationalError("COMMIT", {}, Exception("x"))

        response = upload(client, headers, world.subject)

    assert response.status_code in {409, 413, 415, 422, 503}
    assert_all_closed(tracked)


def test_a_timeout_in_the_middle_of_a_file_closes_its_files(
    clean_db: str, world: World, tracked: list[Any]
) -> None:
    app = make_app(clean_db)
    headers = auth(TestClient(app), world.teacher)

    exchange = asyncio.run(call(app, world, headers, [body_chunk(start_of_a_file())]))

    assert exchange.status == 408
    assert_all_closed(tracked)


def test_an_oversize_body_in_the_middle_of_a_file_closes_its_files(
    clean_db: str, world: World, tracked: list[Any]
) -> None:
    app = make_app(clean_db)
    headers = auth(TestClient(app), world.teacher)
    script: list[Any] = [body_chunk(start_of_a_file())]
    script += [body_chunk(b"a" * 100_000) for _ in range(40)]

    exchange = asyncio.run(call(app, world, headers, script))

    assert exchange.status == 413
    assert_all_closed(tracked)


def test_a_disconnect_in_the_middle_of_a_file_closes_its_files(
    clean_db: str, world: World, tracked: list[Any]
) -> None:
    app = make_app(clean_db)
    headers = auth(TestClient(app), world.teacher)

    asyncio.run(
        call(app, world, headers, [body_chunk(start_of_a_file()), {"type": "http.disconnect"}])
    )

    assert_all_closed(tracked)


def test_an_unexpected_error_after_the_parse_closes_its_files(
    clean_db: str, world: World, tracked: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.document_service import DocumentService

    client = client_for(clean_db)
    headers = auth(client, world.teacher)

    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(DocumentService, "upload", explode)

    assert upload(client, headers, world.subject).status_code == 500
    assert_all_closed(tracked)
