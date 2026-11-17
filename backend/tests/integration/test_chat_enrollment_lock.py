"""M2: persisting a chat turn and removing an enrollment are serialised per student and subject.

The races are made deterministic by a separate database session that stands for the other
transaction (it holds the lock, or has an uncommitted change) while real HTTP requests wait on it.
The test releases it only after PostgreSQL reports the waiter (`pg_locks`, `granted = false`).
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.models.user import UserRole
from app.repositories.enrollment_repository import ENROLLMENT_LOCK_SPACE, enrollment_lock_key
from app.services.rag_service import RAGService
from tests.integration.helpers import (
    MakeUser,
    bearer,
    build_app,
    insert_enrollment,
    insert_subject,
    login_token,
)
from tests.integration.test_chat_phases import CONSENT, CONSENT_VERSION, CONTENT, World, _ask
from tests.sql_support import count, scalar


@pytest.fixture
def world(clean_db: str, make_user: MakeUser) -> World:
    teacher = make_user("teacher-lock@example.com", UserRole.TEACHER)
    student = make_user("student-lock@example.com", UserRole.STUDENT)
    subject = insert_subject(clean_db, teacher.id)
    insert_enrollment(clean_db, subject, student.id)
    return World(clean_db, teacher, student, subject)


@pytest.fixture
def token(client: TestClient, world: World) -> str:
    value = login_token(client, world.student.email)
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(value))
    return value


ENROLLMENTS = "/api/v1/subjects/{subject}/enrollments"
# only the locks of this family: the two-integer form has `classid` = the space and `objsubid` = 2
OURS = f"locktype = 'advisory' AND classid = {ENROLLMENT_LOCK_SPACE} AND objsubid = 2"
WAITERS = f"SELECT count(*) FROM pg_locks WHERE {OURS} AND NOT granted"  # noqa: S608 - a fixed integer constant, no input
HELD = f"SELECT count(*) FROM pg_locks WHERE {OURS} AND granted"  # noqa: S608 - same constant


_OPEN: list["OtherTransaction"] = []


class OtherTransaction:
    """A separate session standing for the transaction of another request."""

    def __init__(self, url: str) -> None:
        self._engine = create_engine(url)
        self._conn = self._engine.connect()
        _OPEN.append(self)

    def lock(self, student: str, subject: str) -> None:
        self._conn.execute(
            text("SELECT pg_advisory_xact_lock(:space, :key)"),
            {
                "space": ENROLLMENT_LOCK_SPACE,
                "key": enrollment_lock_key(uuid.UUID(student), uuid.UUID(subject)),
            },
        )

    def execute(self, sql: str, **params: object) -> None:
        self._conn.execute(text(sql), params)

    def commit(self) -> None:
        self._conn.commit()
        self.close()

    def rollback(self) -> None:
        self._conn.rollback()
        self.close()

    def close(self) -> None:
        """Idempotent; closing a connection with an open transaction rolls it back."""
        if not self._conn.closed:
            self._conn.close()
        self._engine.dispose()


@pytest.fixture(autouse=True)
def _release_other_transactions() -> Iterator[None]:
    """A failing assertion must not leave a lock held: later tests would hang instead of failing."""
    yield
    for other in _OPEN:
        other.close()
    _OPEN.clear()


def advisory_locks(url: str) -> int:
    value = scalar(url, f"SELECT count(*) FROM pg_locks WHERE {OURS}")  # noqa: S608 - same constant
    assert isinstance(value, int)
    return value


def wait_for_a_waiter(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if int(scalar(url, WAITERS)) >= 1:  # type: ignore[call-overload]
            return
        time.sleep(0.02)
    raise AssertionError("no transaction is waiting for the advisory lock")


def teacher_headers(client: TestClient, world: World) -> dict[str, str]:
    return bearer(login_token(client, world.teacher.email))


def unenrol(client: TestClient, world: World, student_id: str | None = None) -> Any:
    path = ENROLLMENTS.format(subject=world.subject) + f"/{student_id or world.student.id}"
    return client.delete(path, headers=teacher_headers(client, world))


def enrol(client: TestClient, world: World, email: str) -> Any:
    return client.post(
        ENROLLMENTS.format(subject=world.subject),
        json={"student_email": email},
        headers=teacher_headers(client, world),
    )


def in_thread(function: Callable[[], Any]) -> tuple[ThreadPoolExecutor, Future[Any]]:
    pool = ThreadPoolExecutor(max_workers=1)
    return pool, pool.submit(function)


# ------------------------------------------------------ the two orders of the race


def test_an_unenrolment_waits_for_an_in_flight_persist_and_completes_after_it(
    client: TestClient, world: World, token: str
) -> None:
    in_flight = OtherTransaction(world.url)
    in_flight.lock(world.student.id, world.subject)  # a persist that holds the lock

    pool, removal = in_thread(lambda: unenrol(client, world))
    try:
        wait_for_a_waiter(world.url)
        assert not removal.done()
        assert count(world.url, "enrollments") == 1  # nothing was deleted yet
        in_flight.commit()
        assert removal.result(timeout=15).status_code == 204
    finally:
        in_flight.close()  # first, so a parked request is never left waiting
        pool.shutdown(wait=True)
    assert count(world.url, "enrollments") == 0


def test_a_persist_waits_for_an_in_flight_unenrolment_then_gets_403_and_stores_nothing(
    client: TestClient, world: World, token: str
) -> None:
    removal = OtherTransaction(world.url)
    removal.lock(world.student.id, world.subject)  # the unenrolment takes the lock first...
    removal.execute("DELETE FROM enrollments WHERE student_id = :s", s=world.student.id)

    pool, chat = in_thread(lambda: _ask(client, token, world))
    try:
        wait_for_a_waiter(world.url)
        assert not chat.done()  # the persist is parked on the lock, before revalidating
        removal.commit()
        response = chat.result(timeout=15)
    finally:
        removal.close()  # first, so a parked request is never left waiting
        pool.shutdown(wait=True)

    assert response.status_code == 403
    assert world.stored() == (0, 0, 0)


def test_a_rolled_back_unenrolment_releases_the_lock_and_the_turn_is_stored(
    client: TestClient, world: World, token: str
) -> None:
    removal = OtherTransaction(world.url)
    removal.lock(world.student.id, world.subject)
    removal.execute("DELETE FROM enrollments WHERE student_id = :s", s=world.student.id)

    pool, chat = in_thread(lambda: _ask(client, token, world))
    try:
        wait_for_a_waiter(world.url)
        removal.rollback()
        response = chat.result(timeout=15)
    finally:
        removal.close()  # first, so a parked request is never left waiting
        pool.shutdown(wait=True)

    assert response.status_code == 200
    assert world.stored() == (1, 2, 1)
    assert count(world.url, "enrollments") == 1
    assert int(scalar(world.url, HELD)) == 0  # type: ignore[call-overload]


def test_consent_that_stops_being_current_while_the_persist_waits_gives_403(
    client: TestClient, world: World, token: str
) -> None:
    other = OtherTransaction(world.url)
    other.lock(world.student.id, world.subject)

    pool, chat = in_thread(lambda: _ask(client, token, world))
    try:
        wait_for_a_waiter(world.url)
        other.execute(
            "UPDATE users SET consent_version = '2025-01-v0' WHERE id = :u", u=world.student.id
        )
        other.commit()
        response = chat.result(timeout=15)
    finally:
        other.close()  # first, so a parked request is never left waiting
        pool.shutdown(wait=True)

    assert response.status_code == 403 and response.json()["code"] == "CONSENT_REQUIRED"
    assert world.stored() == (0, 0, 0)


def test_a_persist_in_flight_commits_before_the_unenrolment_that_arrives_meanwhile(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, proceed = threading.Event(), threading.Event()
    original = RAGService._write_turn

    def paused(self: Any, *args: Any, **kwargs: Any) -> Any:
        entered.set()  # the persist holds the lock and has not written yet
        assert proceed.wait(20)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RAGService, "_write_turn", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        chat = pool.submit(_ask, client, token, world)
        assert entered.wait(15)
        removal = pool.submit(unenrol, client, world)
        try:
            wait_for_a_waiter(world.url)
            assert not removal.done() and not chat.done()
        finally:
            proceed.set()
        assert chat.result(timeout=15).status_code == 200
        assert removal.result(timeout=15).status_code == 204

    assert world.stored() == (1, 2, 1)  # the turn came first, the unenrolment after it
    assert count(world.url, "enrollments") == 0


# ------------------------------------------------------- what it must not block


def test_other_students_and_other_subjects_are_not_blocked(
    client: TestClient, world: World, token: str, make_user: MakeUser
) -> None:
    classmate = make_user("classmate-lock@example.com", UserRole.STUDENT)
    insert_enrollment(world.url, world.subject, classmate.id)
    classmate_token = login_token(client, classmate.email)
    client.post(CONSENT, json={"consent_version": CONSENT_VERSION}, headers=bearer(classmate_token))
    other_subject = insert_subject(world.url, world.teacher.id, name="Other")
    insert_enrollment(world.url, other_subject, world.student.id)

    holder = OtherTransaction(world.url)
    holder.lock(world.student.id, world.subject)  # this pair is busy
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            same_subject_other_student = pool.submit(_ask, client, classmate_token, world)
            same_student_other_subject = pool.submit(
                client.post,
                "/api/v1/chat",
                json={"subject_id": other_subject, "message": CONTENT},
                headers=bearer(token),
            )
            try:
                assert same_subject_other_student.result(timeout=15).status_code == 200
                assert same_student_other_subject.result(timeout=15).status_code == 200
                # only afterwards: removing the classmate while the classmate's own turn is in
                # flight would, correctly, make that turn wait or be refused
                other_student_removal = pool.submit(unenrol, client, world, classmate.id)
                assert other_student_removal.result(timeout=15).status_code == 204
            finally:
                holder.close()  # inside the block: a parked request must not hang the shutdown
        assert int(scalar(world.url, WAITERS)) == 0  # type: ignore[call-overload]
    finally:
        holder.rollback()


def test_no_advisory_lock_is_held_during_generation_or_embedding(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []

    class Probe:
        async def generate(self, system_prompt: str, user_messages: list[dict[str, str]]) -> str:
            seen.append(advisory_locks(world.url))
            return "probe answer"

    class EmbedProbe:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def embed(self, texts: Any) -> list[list[float]]:
            seen.append(advisory_locks(world.url))
            return self._inner.embed(texts)  # type: ignore[no-any-return]

        def count_tokens(self, text: str, *, include_special: bool = True) -> int:
            return self._inner.count_tokens(text, include_special=include_special)  # type: ignore[no-any-return]

    client.app.state.embedder = EmbedProbe(client.app.state.embedder)  # type: ignore[attr-defined]
    monkeypatch.setattr("app.api.chat_deps.build_llm_service", lambda settings: Probe())

    assert _ask(client, token, world).status_code == 200

    assert seen == [0, 0]  # during the embedding and during the generation
    assert int(scalar(world.url, HELD)) == 0  # type: ignore[call-overload]


def test_a_failed_persist_releases_the_lock_so_the_unenrolment_is_not_stuck(
    client: TestClient, world: World, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(session: Any) -> None:
        session.rollback()
        raise RuntimeError("the database refused the commit")

    monkeypatch.setattr("app.api.v1.endpoints.chat.commit_or_rollback", refuse)
    assert _ask(client, token, world).status_code == 500
    monkeypatch.undo()

    assert int(scalar(world.url, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")) == 0  # type: ignore[call-overload]
    started = time.monotonic()
    assert unenrol(client, world).status_code == 204
    assert time.monotonic() - started < 5


# ------------------------------------------------------------------- no deadlock


def test_concurrent_turns_and_unenrolments_never_deadlock(clean_db: str, world: World) -> None:
    app = build_app(clean_db, chat_rate_limit="100000/minute")
    with TestClient(app) as client:
        student_token = login_token(client, world.student.email)
        client.post(
            CONSENT,
            json={"consent_version": CONSENT_VERSION},
            headers=bearer(student_token),
        )
        statuses: dict[str, list[int]] = {"chat": [], "unenrol": [], "enrol": []}

        def chats() -> None:
            for _ in range(8):
                statuses["chat"].append(_ask(client, student_token, world).status_code)

        def toggler() -> None:
            for _ in range(8):
                statuses["unenrol"].append(unenrol(client, world).status_code)
                statuses["enrol"].append(enrol(client, world, world.student.email).status_code)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(chats) for _ in range(3)] + [pool.submit(toggler)]
            for future in futures:
                future.result(timeout=120)

    everything = [code for codes in statuses.values() for code in codes]
    assert not [code for code in everything if code >= 500], statuses  # a deadlock would be a 500
    assert set(statuses["chat"]) <= {200, 403, 404}
    assert statuses["unenrol"] == [204] * 8 and statuses["enrol"] == [201] * 8
    stored = world.stored()
    assert stored[1] == 2 * statuses["chat"].count(
        200
    )  # every 200 stored its turn, nothing else did
    assert int(scalar(world.url, "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")) == 0  # type: ignore[call-overload]


# ------------------------------------------------------------------ negative paths


def test_removing_an_enrollment_that_does_not_exist_is_404_and_leaves_no_lock(
    client: TestClient, world: World, token: str, make_user: MakeUser
) -> None:
    stranger = make_user("stranger-lock@example.com", UserRole.STUDENT)  # never enrolled

    response = unenrol(client, world, stranger.id)

    assert response.status_code == 404
    assert advisory_locks(world.url) == 0  # the lock was taken and released with the transaction
    assert count(world.url, "enrollments") == 1


def test_a_teacher_who_does_not_own_the_subject_cannot_remove_the_enrollment(
    client: TestClient, world: World, token: str, make_user: MakeUser
) -> None:
    other_teacher = make_user("other-teacher-lock@example.com", UserRole.TEACHER)
    path = ENROLLMENTS.format(subject=world.subject) + f"/{world.student.id}"

    response = client.delete(path, headers=bearer(login_token(client, other_teacher.email)))

    assert response.status_code == 404
    assert count(world.url, "enrollments") == 1
    assert advisory_locks(world.url) == 0


def test_a_persist_that_waits_longer_than_the_statement_timeout_is_a_clean_503(
    clean_db: str, world: World
) -> None:
    app = build_app(clean_db, chat_rate_limit="100000/minute", db_statement_timeout_api_seconds=1)
    holder = OtherTransaction(world.url)
    holder.lock(world.student.id, world.subject)  # an unenrolment that is taking too long
    try:
        with TestClient(app) as client:
            student_token = login_token(client, world.student.email)
            client.post(
                CONSENT,
                json={"consent_version": CONSENT_VERSION},
                headers=bearer(student_token),
            )
            response = _ask(client, student_token, world)
    finally:
        holder.rollback()

    assert response.status_code == 503 and response.json()["code"] == "SERVICE_UNAVAILABLE"
    for leaked in ("pg_advisory", "statement", "SELECT", "timeout"):
        assert leaked not in response.text
    assert world.stored() == (0, 0, 0)
