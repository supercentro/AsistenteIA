"""Pure ASGI guard on the body of an upload (change 6, task 9.2; design A8).

It wraps `receive` for `POST /api/v1/subjects/{id}/documents` and judges the body by the bytes that
actually arrive, never by `Content-Length` alone:

* the first read refuses a declared length above the limit (`UploadTooLarge`) without taking a
  byte from the client, so authentication and ownership, which run before the body is read,
  decide first;
* every chunk is counted and the one that crosses the limit is refused, whatever was declared;
* the total deadline starts with the first read, and the idle gap is the time since the last
  non-empty chunk (empty chunks are not progress), so neither a stalled client nor a slow drip can
  hold an upload forever.

The refusals are exceptions raised out of `receive`; the endpoint turns them into the `413` and
`408` answers. The guard keeps no state between requests and holds nothing while it waits.
`UploadSlots` bounds how many uploads are being received at once.
"""

import asyncio
import re
import threading
import time
from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Starlette's multipart framing (boundary, part headers) added to the file bytes.
MULTIPART_OVERHEAD_BYTES = 64 * 1024

_UPLOAD_PATH = re.compile(r"^/api/v1/subjects/[^/]+/documents/?$")


class UploadAborted(Exception):  # noqa: N818 - a family of control-flow signals, not an error
    """The body of an upload is not going to be read to the end."""


class UploadTooLarge(UploadAborted):  # noqa: N818
    """More bytes than allowed were declared or received."""


class UploadTimedOut(UploadAborted):  # noqa: N818
    """The client did not send the body within the total deadline or the idle gap."""


def is_upload_request(scope: Scope) -> bool:
    """True for the upload route (`POST` on the documents collection of a subject)."""
    return (
        scope.get("type") == "http"
        and scope.get("method") == "POST"
        and _UPLOAD_PATH.match(str(scope.get("path", ""))) is not None
    )


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-length":
            text = value.decode("latin-1").strip()
            return int(text) if text.isascii() and text.isdigit() else None
    return None


class UploadBodyGuard:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int,
        body_timeout_seconds: float,
        idle_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self._max_body = max_body_bytes
        self._total = body_timeout_seconds
        self._idle = idle_seconds
        self._clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not is_upload_request(scope):
            await self.app(scope, receive, send)
            return
        await self.app(scope, self._guarded(scope, receive), send)

    def _guarded(self, scope: Scope, receive: Receive) -> Receive:
        declared = _declared_length(scope)
        started: float | None = None
        last_progress = 0.0
        received = 0

        async def guarded() -> Message:
            nonlocal started, last_progress, received
            if started is None:
                if declared is not None and declared > self._max_body:
                    raise UploadTooLarge
                started = last_progress = self._clock()
            while True:
                now = self._clock()
                left = min(started + self._total - now, last_progress + self._idle - now)
                if left <= 0:
                    raise UploadTimedOut
                try:
                    async with asyncio.timeout(left):
                        message = await receive()
                except TimeoutError:
                    raise UploadTimedOut from None
                if message["type"] != "http.request":
                    return message
                body: bytes = message.get("body", b"")
                if body:
                    received += len(body)
                    if received > self._max_body:
                        raise UploadTooLarge
                    last_progress = self._clock()
                elif message.get("more_body", False):
                    continue  # an empty chunk is not progress
                return message

        return guarded


class UploadSlots:
    """A counter of uploads being received; `try_acquire` never blocks.

    Every read-modify-write of the counter happens under `_lock`: without it two threads could both
    pass the limit check (or both lose an update on release). `pause_between_read_and_write` is a
    test seam called inside the critical section between the read and the write, so the tests can
    force the interleaving that the lock prevents; production leaves it unset.
    """

    def __init__(
        self, limit: int, *, pause_between_read_and_write: Callable[[], None] | None = None
    ) -> None:
        self._limit = limit
        self._in_flight = 0
        self._lock = threading.Lock()
        self._pause = pause_between_read_and_write

    @property
    def in_flight(self) -> int:
        return self._in_flight

    def try_acquire(self) -> bool:
        with self._lock:
            current = self._in_flight
            if current >= self._limit:
                return False
            self._between()
            self._in_flight = current + 1
            return True

    def release(self) -> None:
        with self._lock:
            current = self._in_flight
            self._between()
            self._in_flight = max(0, current - 1)

    def _between(self) -> None:
        if self._pause is not None:
            self._pause()
