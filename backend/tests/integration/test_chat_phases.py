"""Request phases of POST /chat (design D3): no connection while the LLM runs, revalidation, races.

The LLM is replaced by a probe that looks at the pool and at PostgreSQL while it "generates" and
that can change the database at that moment, which is when a real provider call would be running.
"""

import asyncio
import contextlib
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models.user import UserRole
from app.rag.embedder import FakeEmbedder
from app.services.llm_service import GeminiLLMService
from tests.integration.helpers import (
    MakeUser,
    TestUser,
    bearer,
    build_app,
    insert_enrollment,
    insert_subject,
    login_token,
)
from tests.sql_support import count, insert_chunk, insert_document, run, scalar

CHAT = "/api/v1/chat"
CONVERSATIONS = "/api/v1/conversations"
CONSENT = "/api/v1/users/me/consent"
CONSENT_VERSION = "2026-10-v1"
CONTENT = "algebra equations formulas"
IDLE_IN_TRANSACTION = (
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
    "AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'"
)


class ProbeLLM:
    """Records the state of the pool while generating and can change the database meanwhile."""

    def __init__(
        self,
        url: str,
        engine: Any,
        side_effect: Callable[[], None] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._url, self._engine = url, engine
        self._side_effect, self._delay = side_effect, delay
        self.seen: list[dict[str, int]] = []

    def _snapshot(self) -> dict[str, int]:
        return {
            "checked_out": int(self._engine.pool.checkedout()),
            "idle_in_transaction": int(scalar(self._url, IDLE_IN_TRANSACTION)),  # type: ignore[call-overload]
        }

    async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
        self.seen.append(await asyncio.to_thread(self._snapshot))
        if self._side_effect:
            await asyncio.to_thread(self._side_effect)
        if self._delay:
            await asyncio.sleep(self._delay)
        return "probe answer"


class _FailingModel:
    async def ainvoke(self, messages: Any) -> Any:
        raise RuntimeError("provider exploded")


class SlowEmbedder:
    def __init__(self, seconds: float, engine: Any = None) -> None:
        self._inner, self._seconds, self._engine = FakeEmbedder(), seconds, engine
        self.checked_out_while_embedding: list[int] = []

    def embed(self, texts: Any) -> list[list[float]]:
        if self._engine is not None:
            self.checked_out_while_embedding.append(int(self._engine.pool.checkedout()))
        time.sleep(self._seconds)
        return self._inner.embed(texts)

    def count_tokens(self, text: str, *, include_special: bool = True) -> int:
        return self._inner.count_tokens(text, include_special=include_special)


def _vector(content: str) -> str:
    return "[" + ",".join(repr(v) for v in FakeEmbedder().embed([content])[0]) + "]"


class World:
    def __init__(self, url: str, teacher: TestUser, student: TestUser, subject: str) -> None:
        self.url, self.teacher, self.student, self.subject = url, teacher, student, subject
        self.document = insert_document(url, uuid.UUID(subject), "phases.pdf", "ready")
        insert_chunk(
            url,
            self.document,
            uuid.UUID(subject),
            embedding=_vector(CONTENT),
            content=CONTENT,
            page_number=2,
        )

    def stored(self) -> tuple[int, int, int]:
        return (
            count(self.url, "conversations"),
            count(self.url, "messages"),
            count(self.url, "message_sources"),
        )


@pytest.fixture
def world(clean_db: str, make_user: MakeUser) -> World:
    teacher = make_user("teacher-phases@example.com", UserRole.TEACHER)
    student = make_user("student-phases@example.com", UserRole.STUDENT)
    subject = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject, student.id)
    return World(clean_db, teacher, student, subject)


@pytest.fixture
def token(client: TestClient, world: World) -> str:
    value = login_token(client, world.student.email)
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(value))
    return value


def _ask(client: TestClient, token: str, world: World, **extra: object) -> Any:
    payload: dict[str, object] = {"subject_id": world.subject, "message": CONTENT}
    payload.update(extra)
    return client.post(CHAT, json=payload, headers=bearer(token))


def _install(monkeypatch: pytest.MonkeyPatch, llm: Any) -> None:
    monkeypatch.setattr("app.api.chat_deps.build_llm_service", lambda settings: llm)


def _probe(client: TestClient, world: World, **kwargs: Any) -> ProbeLLM:
    return ProbeLLM(world.url, client.app.state.engine, **kwargs)  # type: ignore[attr-defined]


# ------------------------------------------------------- no connection while generating


def test_no_connection_is_held_while_the_llm_generates(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe(client, world)
    _install(monkeypatch, probe)

    response = _ask(client, token, world)

    assert response.status_code == 200, response.text
    assert probe.seen == [{"checked_out": 0, "idle_in_transaction": 0}]
    assert client.app.state.engine.pool.checkedout() == 0  # type: ignore[attr-defined]
    assert world.stored() == (1, 2, 1)


def test_a_provider_failure_stores_nothing_and_leaves_no_connection(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, GeminiLLMService(_FailingModel(), 1))

    response = _ask(client, token, world)

    assert response.status_code == 502
    assert world.stored() == (0, 0, 0)
    assert client.app.state.engine.pool.checkedout() == 0  # type: ignore[attr-defined]


def test_a_refused_commit_is_an_error_and_stores_nothing(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(session: Any) -> None:
        session.rollback()
        raise RuntimeError("the database refused the commit")

    monkeypatch.setattr("app.api.v1.endpoints.chat.commit_or_rollback", refuse)

    response = _ask(client, token, world)

    assert response.status_code == 500
    assert world.stored() == (0, 0, 0)
    assert client.app.state.engine.pool.checkedout() == 0  # type: ignore[attr-defined]


# ------------------------------------------------- revalidation after generation


def test_consent_lost_during_generation_stores_nothing(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe(
        client,
        world,
        side_effect=lambda: run(
            world.url,
            "UPDATE users SET consent_version = '2025-01-v0' WHERE id = :u",
            u=world.student.id,
        ),
    )
    _install(monkeypatch, probe)

    response = _ask(client, token, world)

    assert response.status_code == 403 and response.json()["code"] == "CONSENT_REQUIRED"
    assert world.stored() == (0, 0, 0)


def test_unenrolment_during_generation_stores_nothing(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe(
        client,
        world,
        side_effect=lambda: run(
            world.url, "DELETE FROM enrollments WHERE student_id = :s", s=world.student.id
        ),
    )
    _install(monkeypatch, probe)

    response = _ask(client, token, world)

    assert response.status_code == 403
    assert world.stored() == (0, 0, 0)


def test_a_conversation_deleted_during_generation_gets_no_orphan_messages(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = _ask(client, token, world).json()["conversation_id"]
    probe = _probe(
        client,
        world,
        side_effect=lambda: run(
            world.url, "DELETE FROM conversations WHERE id = :c", c=conversation
        ),
    )
    _install(monkeypatch, probe)

    response = _ask(client, token, world, conversation_id=conversation)

    assert response.status_code == 404
    assert world.stored() == (0, 0, 0)


def test_a_subject_deleted_during_generation_stores_nothing(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe(
        client,
        world,
        side_effect=lambda: run(world.url, "DELETE FROM subjects WHERE id = :s", s=world.subject),
    )
    _install(monkeypatch, probe)

    response = _ask(client, token, world)

    assert response.status_code == 404
    assert world.stored() == (0, 0, 0)


def test_a_cited_document_deleted_during_generation_keeps_the_citation_snapshot(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe = _probe(
        client,
        world,
        side_effect=lambda: run(world.url, "DELETE FROM documents WHERE id = :d", d=world.document),
    )
    _install(monkeypatch, probe)

    response = _ask(client, token, world)

    assert response.status_code == 200, response.text
    source = response.json()["sources"][0]
    assert source["chunk_id"] is None and source["document_id"] is None
    assert source["filename"] == "phases.pdf" and source["page_number"] == 2
    assert source["snippet"] == ""  # same as the history: no document text once the chunk is gone
    assert world.stored() == (1, 2, 1)
    history = client.get(
        f"{CONVERSATIONS}/{response.json()['conversation_id']}/messages", headers=bearer(token)
    ).json()
    stored = next(m for m in history if m["role"] == "assistant")["sources"][0]
    assert stored["filename"] == "phases.pdf" and stored["document_id"] is None


# ---------------------------------------------------------------- concurrency


def test_concurrent_turns_on_one_conversation_are_each_stored_whole(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = _ask(client, token, world).json()["conversation_id"]
    _install(monkeypatch, _probe(client, world, delay=0.3))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_ask, client, token, world, conversation_id=conversation) for _ in range(2)
        ]
        statuses = [f.result().status_code for f in futures]

    assert statuses == [200, 200]
    assert world.stored() == (1, 6, 3)
    roles = scalar(
        world.url,
        "SELECT string_agg(role::text, ',' ORDER BY created_at, role) FROM messages",
    )
    assert roles == ",".join(["user", "assistant"] * 3)  # turns never interleave


# ------------------------------------------------------------------ event loop


def test_the_event_loop_stays_responsive_while_the_query_is_embedded(
    client: TestClient, world: World, token: str
) -> None:
    client.app.state.embedder = SlowEmbedder(0.8)  # type: ignore[attr-defined]

    with ThreadPoolExecutor(max_workers=1) as pool:
        slow = pool.submit(_ask, client, token, world)
        time.sleep(0.2)
        started = time.monotonic()
        health = client.get("/api/v1/health")
        elapsed = time.monotonic() - started
        assert slow.result().status_code == 200

    assert health.status_code == 200
    assert elapsed < 0.4, f"health waited {elapsed:.2f}s: the embedding blocks the event loop"


def test_requests_queued_on_the_embedding_lock_hold_no_connection(
    client: TestClient, world: World, token: str
) -> None:
    from app.services import rag_service

    engine = client.app.state.engine  # type: ignore[attr-defined]
    rag_service._EMBED_LOCK.acquire()  # noqa: SLF001 - make every request wait for the embedder
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_ask, client, token, world) for _ in range(4)]
        try:
            time.sleep(0.8)  # all four have authorized and are now waiting for the lock
            assert engine.pool.checkedout() == 0
            assert int(scalar(world.url, IDLE_IN_TRANSACTION)) == 0  # type: ignore[call-overload]
            assert not any(f.done() for f in futures)
        finally:
            rag_service._EMBED_LOCK.release()  # noqa: SLF001 - never leave the threads blocked
        statuses = [f.result(timeout=30).status_code for f in futures]

    assert statuses == [200] * 4


@pytest.mark.parametrize(
    "scenario", ["not_enrolled", "unknown_subject", "search_failure", "llm_failure"]
)
def test_early_exits_leave_no_connection_checked_out(
    client: TestClient,
    world: World,
    token: str,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    payload_subject = world.subject
    if scenario == "not_enrolled":
        run(world.url, "DELETE FROM enrollments WHERE student_id = :s", s=world.student.id)
    elif scenario == "unknown_subject":
        payload_subject = str(uuid.uuid4())
    elif scenario == "search_failure":

        def boom(self: Any, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("search exploded")

        monkeypatch.setattr("app.repositories.chunk_repository.ChunkRepository.find_similar", boom)
    else:
        _install(monkeypatch, GeminiLLMService(_FailingModel(), 1))

    response = client.post(
        CHAT,
        json={"subject_id": payload_subject, "message": CONTENT},
        headers=bearer(token),
    )

    assert response.status_code in (403, 404, 502, 503)
    assert client.app.state.engine.pool.checkedout() == 0  # type: ignore[attr-defined]
    assert int(scalar(world.url, IDLE_IN_TRANSACTION)) == 0  # type: ignore[call-overload]
    assert world.stored() == (0, 0, 0)


def test_a_real_commit_failure_is_an_error_without_leaks_and_stores_nothing(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import OperationalError

    def refuse(self: Any) -> None:
        raise OperationalError("COMMIT", {}, Exception("password=secret-credential refused"))

    monkeypatch.setattr("sqlalchemy.orm.Session.commit", refuse)

    response = _ask(client, token, world)

    monkeypatch.undo()
    assert response.status_code >= 500
    assert "secret-credential" not in response.text and "password" not in response.text
    assert world.stored() == (0, 0, 0)
    assert client.app.state.engine.pool.checkedout() == 0  # type: ignore[attr-defined]


# ---------------------------------------------------------------- cancellation


@pytest.mark.asyncio
async def test_a_request_cancelled_during_generation_stores_nothing_and_holds_nothing(
    clean_db: str, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    teacher = make_user("teacher-cancel@example.com", UserRole.TEACHER)
    student = make_user("student-cancel@example.com", UserRole.STUDENT)
    subject = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject, student.id)
    app = build_app(clean_db)
    started = asyncio.Event()

    class HangingLLM:
        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            started.set()
            await asyncio.sleep(60)
            return "never"

    insert_chunk(
        clean_db,
        insert_document(clean_db, uuid.UUID(subject), "cancel.pdf", "ready"),
        uuid.UUID(subject),
        embedding=_vector(CONTENT),
        content=CONTENT,
    )
    _install(monkeypatch, HangingLLM())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        login = await http.post(
            "/api/v1/auth/login", json={"email": student.email, "password": student.password}
        )
        headers = bearer(login.json()["access_token"])
        await http.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=headers)
        request = asyncio.create_task(
            http.post(CHAT, json={"subject_id": subject, "message": CONTENT}, headers=headers)
        )
        await asyncio.wait_for(started.wait(), timeout=10)
        assert app.state.engine.pool.checkedout() == 0  # nothing held while the provider runs
        request.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await request

    await asyncio.sleep(0.2)
    assert app.state.engine.pool.checkedout() == 0
    assert count(clean_db, "conversations") == 0 and count(clean_db, "messages") == 0
