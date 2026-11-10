"""The ASGI upload guard on the bytes actually received (change 6, task 9.2).

The guard is driven here without a server: a scripted `receive` stands for the client. It counts
the bytes that arrive, never trusts `Content-Length` for more than the early check, and enforces
the total deadline and the idle gap. Real-server behaviour (the `408` seen by a connected client,
a disconnect without a trace) is covered in `tests/integration/test_upload_server.py`.
"""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

import pytest
from starlette.types import Message, Receive, Scope, Send

from app.core.upload_guard import (
    UploadAborted,
    UploadBodyGuard,
    UploadSlots,
    UploadTimedOut,
    UploadTooLarge,
    is_upload_request,
)

LIMIT = 1_000
UPLOAD_PATH = "/api/v1/subjects/11111111-2222-3333-4444-555555555555/documents"


def scope(
    method: str = "POST", path: str = UPLOAD_PATH, content_length: int | str | None = None
) -> Scope:
    headers: list[tuple[bytes, bytes]] = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {"type": "http", "method": method, "path": path, "headers": headers}


def chunk(size: int, more: bool = True) -> Message:
    return {"type": "http.request", "body": b"x" * size, "more_body": more}


@dataclass
class Outcome:
    received: int = 0
    error: BaseException | None = None
    finished: bool = False
    seen: list[Message] = field(default_factory=list)


def reader(outcome: Outcome) -> Callable[[Scope, Receive, Send], Awaitable[None]]:
    """An application that reads the whole body and records what happened."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            while True:
                message = await receive()
                outcome.seen.append(message)
                if message["type"] == "http.disconnect":
                    return
                outcome.received += len(message.get("body", b""))
                if not message.get("more_body", False):
                    outcome.finished = True
                    return
        except UploadAborted as error:
            outcome.error = error

    return app


def scripted(messages: list[Message | float]) -> Receive:
    """A client that sends the given messages; a number is a pause (seconds) before the next."""
    queue = list(messages)

    async def receive() -> Message:
        while queue:
            item = queue.pop(0)
            if isinstance(item, (int, float)):
                await asyncio.sleep(item)
                continue
            return item
        await asyncio.sleep(3600)  # the client went silent
        raise AssertionError("unreachable")

    return receive


async def nothing(_: Message) -> None:
    return None


async def drive(
    messages: list[Message | float],
    *,
    request: Scope | None = None,
    limit: int = LIMIT,
    total: float = 5.0,
    idle: float = 5.0,
) -> Outcome:
    outcome = Outcome()
    guard = UploadBodyGuard(
        reader(outcome),
        max_body_bytes=limit,
        body_timeout_seconds=total,
        idle_seconds=idle,
    )
    await guard(request or scope(), scripted(messages), nothing)
    return outcome


def run(coroutine: Awaitable[Any]) -> Any:
    return asyncio.run(coroutine)  # type: ignore[arg-type]


# --- which requests are guarded -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", UPLOAD_PATH, True),
        ("POST", UPLOAD_PATH + "/", True),
        ("POST", "/api/v1/subjects/not-a-uuid/documents", True),
        ("GET", UPLOAD_PATH, False),
        ("DELETE", UPLOAD_PATH + "/abc", False),
        ("POST", UPLOAD_PATH + "/abc", False),
        ("POST", "/api/v1/auth/login", False),
        ("POST", "/api/v1/subjects", False),
        ("POST", "/api/v1/subjects//documents", False),
        ("POST", "/other/api/v1/subjects/x/documents", False),
    ],
)
def test_only_the_upload_route_is_guarded(method: str, path: str, expected: bool) -> None:
    assert is_upload_request(scope(method, path)) is expected


def test_other_requests_are_passed_through_untouched() -> None:
    seen: list[Receive] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(receive)

    guard = UploadBodyGuard(app, max_body_bytes=1, body_timeout_seconds=1, idle_seconds=1)
    original = scripted([])

    run(guard(scope("POST", "/api/v1/auth/login"), original, nothing))
    run(guard({"type": "websocket", "path": UPLOAD_PATH}, original, nothing))
    run(guard({"type": "lifespan"}, original, nothing))

    assert seen == [original, original, original]


# --- counting the bytes that arrive -------------------------------------------------------------


def test_a_body_within_the_limit_is_delivered_unchanged() -> None:
    outcome = run(drive([chunk(400), chunk(500, more=False)]))

    assert outcome.finished
    assert outcome.received == 900
    assert outcome.error is None


def test_a_body_exactly_at_the_limit_is_accepted() -> None:
    outcome = run(drive([chunk(LIMIT, more=False)]))

    assert outcome.finished
    assert outcome.received == LIMIT


def test_one_byte_over_the_limit_is_refused_without_reading_further() -> None:
    outcome = run(drive([chunk(LIMIT), chunk(1), chunk(500)]))

    assert isinstance(outcome.error, UploadTooLarge)
    assert outcome.received == LIMIT  # the chunk that crossed the limit was never delivered
    assert not outcome.finished


def test_a_body_without_content_length_is_judged_by_what_arrives() -> None:
    chunks: list[Message | float] = [chunk(300) for _ in range(5)]

    outcome = run(drive(chunks))

    assert isinstance(outcome.error, UploadTooLarge)
    assert outcome.received <= LIMIT


def test_a_declared_length_over_the_limit_is_refused_before_the_body_is_read() -> None:
    outcome = run(drive([chunk(10, more=False)], request=scope(content_length=LIMIT + 1)))

    assert isinstance(outcome.error, UploadTooLarge)
    assert outcome.received == 0  # not a single byte was taken from the client
    assert outcome.seen == []


def test_a_declared_length_at_the_limit_is_not_refused() -> None:
    outcome = run(drive([chunk(10, more=False)], request=scope(content_length=LIMIT)))

    assert outcome.finished


def test_a_lying_small_declaration_does_not_protect_a_large_body() -> None:
    outcome = run(drive([chunk(LIMIT), chunk(LIMIT)], request=scope(content_length=10)))

    assert isinstance(outcome.error, UploadTooLarge)


@pytest.mark.parametrize("declared", ["abc", "-5", "", "1e3", " "])
def test_an_unusable_declared_length_is_ignored_and_the_bytes_decide(declared: str) -> None:
    outcome = run(drive([chunk(200, more=False)], request=scope(content_length=declared)))

    assert outcome.finished
    assert outcome.received == 200


def test_the_declared_length_check_happens_on_the_first_read_not_at_the_start() -> None:
    """Authentication runs before the body is read: the guard must not answer on its own."""
    sent: list[Message] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        return None  # never reads the body (for instance a `401`)

    async def collect(message: Message) -> None:
        sent.append(message)

    guard = UploadBodyGuard(app, max_body_bytes=LIMIT, body_timeout_seconds=5, idle_seconds=5)

    run(guard(scope(content_length=LIMIT * 100), scripted([]), collect))

    assert sent == []


# --- deadlines ----------------------------------------------------------------------------------


def test_a_client_that_goes_silent_hits_the_idle_limit() -> None:
    started = time.monotonic()
    outcome = run(drive([chunk(10)], idle=0.2, total=30))

    assert isinstance(outcome.error, UploadTimedOut)
    assert time.monotonic() - started < 5  # about the idle limit, not the 30 s total


def test_the_idle_limit_is_measured_from_the_last_byte() -> None:
    script: list[Message | float] = [chunk(10)]
    for _ in range(4):
        script += [0.15, chunk(10)]
    script[-1] = chunk(10, more=False)
    outcome = run(drive(script, idle=0.3, total=30))

    assert outcome.finished  # no single gap reached the idle limit although the total is longer


def test_a_slow_drip_that_never_idles_hits_the_total_deadline() -> None:
    drip: list[Message | float] = []
    for _ in range(40):
        drip += [chunk(1), 0.05]

    outcome = run(drive(drip, idle=0.5, total=0.4))

    assert isinstance(outcome.error, UploadTimedOut)
    assert outcome.received < 40


def test_empty_chunks_are_not_progress() -> None:
    empty: Message = {"type": "http.request", "body": b"", "more_body": True}
    spam: list[Message | float] = []
    for _ in range(30):
        spam += [empty, 0.03]

    outcome = run(drive(spam, idle=0.25, total=30))

    assert isinstance(outcome.error, UploadTimedOut)
    assert outcome.seen == []  # the application never woke up for an empty chunk


def test_the_total_deadline_starts_with_the_first_read() -> None:
    """Time spent before the body is read (authentication) does not count."""

    async def scenario() -> Outcome:
        outcome = Outcome()

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            await asyncio.sleep(0.5)  # slower than the deadline, before reading
            await reader(outcome)(scope, receive, send)

        guard = UploadBodyGuard(
            app, max_body_bytes=LIMIT, body_timeout_seconds=0.3, idle_seconds=0.3
        )
        await guard(scope(), scripted([chunk(10, more=False)]), nothing)
        return outcome

    assert run(scenario()).finished


def test_the_limits_are_configurable_per_guard() -> None:
    short = run(drive([chunk(10)], idle=0.1, total=30))
    long = run(drive([chunk(10), 0.3, chunk(10, more=False)], idle=1.0, total=30))

    assert isinstance(short.error, UploadTimedOut)
    assert long.finished


def test_a_disconnect_is_delivered_to_the_application() -> None:
    outcome = run(drive([chunk(10), {"type": "http.disconnect"}]))

    assert outcome.seen[-1]["type"] == "http.disconnect"
    assert outcome.error is None


def test_the_guard_does_not_swallow_other_exceptions() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("boom")

    guard = UploadBodyGuard(app, max_body_bytes=1, body_timeout_seconds=1, idle_seconds=1)

    with pytest.raises(RuntimeError):
        run(guard(scope(), scripted([]), nothing))


# --- uploads being received at the same time ----------------------------------------------------


def test_slots_are_limited_and_released() -> None:
    slots = UploadSlots(2)

    assert slots.try_acquire()
    assert slots.try_acquire()
    assert not slots.try_acquire()
    slots.release()
    assert slots.try_acquire()
    assert slots.in_flight == 2


def test_a_release_without_acquire_never_goes_negative() -> None:
    slots = UploadSlots(1)

    slots.release()
    slots.release()

    assert slots.in_flight == 0
    assert slots.try_acquire()
    assert not slots.try_acquire()


def test_slots_are_exact_under_threads() -> None:
    import threading

    slots = UploadSlots(5)
    barrier = threading.Barrier(40)
    granted: list[bool] = []

    def attempt() -> None:
        barrier.wait()
        granted.append(slots.try_acquire())

    threads = [threading.Thread(target=attempt) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(granted) == 5
    assert slots.in_flight == 5


# --- the atomicity of the slot counter, with the interleaving forced (task 10, review of 9) -----


class Meeting:
    """A pause that makes two threads reach the same point of the critical section together.

    With the lock the second thread cannot get in, so the meeting never happens and the barrier
    times out (the first thread then goes on alone). Without the lock both threads meet between
    reading the counter and writing it: the interleaving that loses an update. It does nothing
    until `arm()` (so the set-up of a test does not use up the barrier).
    """

    def __init__(self) -> None:
        self._barrier: threading.Barrier | None = None

    def arm(self) -> None:
        self._barrier = threading.Barrier(2, timeout=0.5)

    def __call__(self) -> None:
        barrier = self._barrier
        if barrier is not None:
            with suppress(threading.BrokenBarrierError):
                barrier.wait()


def together(count: int, work: Callable[[], object]) -> list[object]:
    results: list[object] = []
    start = threading.Barrier(count)

    def task() -> None:
        start.wait()
        results.append(work())

    threads = [threading.Thread(target=task) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_two_uploads_cannot_both_take_the_last_slot_even_if_interleaved() -> None:
    meeting = Meeting()
    slots = UploadSlots(1, pause_between_read_and_write=meeting)
    meeting.arm()

    granted = together(2, slots.try_acquire)

    assert granted.count(True) == 1
    assert slots.in_flight == 1


def test_two_releases_cannot_lose_an_update_even_if_interleaved() -> None:
    meeting = Meeting()
    slots = UploadSlots(2, pause_between_read_and_write=meeting)
    assert slots.try_acquire() and slots.try_acquire()
    meeting.arm()

    together(2, slots.release)

    assert slots.in_flight == 0  # a lost update would leave one slot taken forever


def test_a_release_interleaved_with_an_acquire_keeps_the_count_exact() -> None:
    meeting = Meeting()
    slots = UploadSlots(2, pause_between_read_and_write=meeting)
    assert slots.try_acquire()
    meeting.arm()
    results: list[object] = []
    start = threading.Barrier(2)

    def acquire() -> None:
        start.wait()
        results.append(slots.try_acquire())

    def release() -> None:
        start.wait()
        slots.release()

    threads = [threading.Thread(target=acquire), threading.Thread(target=release)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [True]
    assert slots.in_flight == 1  # one taken before, one released, one acquired


# --- coverage of the security-relevant edges (group 12) -----------------------------------------


def test_a_deadline_that_passes_between_two_reads_is_caught_before_waiting() -> None:
    """The check happens before `receive` is awaited: an expired client is not waited for."""
    now = [0.0]
    outcome = Outcome()
    asked = {"times": 0}

    async def receive() -> Message:
        asked["times"] += 1
        return chunk(10)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await receive()
            now[0] += 10  # the application took longer than the idle limit
            await receive()
        except UploadAborted as error:
            outcome.error = error

    guard = UploadBodyGuard(
        app, max_body_bytes=LIMIT, body_timeout_seconds=100, idle_seconds=5, clock=lambda: now[0]
    )

    run(guard(scope(), receive, nothing))

    assert isinstance(outcome.error, UploadTimedOut)
    assert asked["times"] == 1  # the second read never reached the client
