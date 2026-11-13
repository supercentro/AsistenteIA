"""Helpers for the ingestion service and worker tests (change 6, group 8).

`built_service` creates an `IngestionService` on its own engine against the guarded test
database; `HookEmbedder` is the fake embedder with a hook that runs while "inference" is in
progress, which is where the tests inspect the database, expire leases or delete documents.
`activity` reads what the sessions of the test database are doing; given the `backends` of a
`Built` service it looks only at the connections that service opened, so a maintenance pass or
a neighbouring test cannot be mistaken for the service holding a lock or a transaction.
"""

import logging
import threading
from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.database import create_db_engine, create_session_factory
from app.rag.chunker import Page
from app.rag.embedder import Embedder, FakeEmbedder
from app.services.ingestion_service import IngestionLimits, IngestionService
from tests.least_privilege import role_url

# About 700 words: nine chunks of roughly 100 words with the fake embedder.
WORDS = [f"term{i}" for i in range(700)]
LONG_TEXT = (" ".join(WORDS) + ".").encode("utf-8")
SHORT_TEXT = b"Derivatives measure the rate of change of a function. Integrals add it up."


class HookEmbedder(FakeEmbedder):
    """The deterministic fake embedder; `hook(call_number)` runs before every `embed` call."""

    def __init__(self, hook: Callable[[int], None] | None = None) -> None:
        self.hook = hook
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        if self.hook is not None:
            self.hook(self.calls)
        return super().embed(texts)


def default_limits(**overrides: object) -> IngestionLimits:
    values: dict[str, object] = {
        "lease_seconds": 120,
        "deadline_seconds": 600,
        "max_attempts": 3,
        "batch_size": 4,
        "max_chunks": 2000,
        "max_chars": 2_000_000,
        "max_age_hours": 24,
    }
    values.update(overrides)
    return IngestionLimits(**values)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Built:
    service: IngestionService
    engine: Engine
    factory: sessionmaker[Session]
    backends: set[int]  # server process ids of the connections this service currently has open


@contextmanager
def built_service(
    url: str,
    embedder: Embedder | None = None,
    *,
    pdf_loader: Callable[[bytes], list[Page]] | None = None,
    clock: Callable[[], float] | None = None,
    **limit_overrides: object,
) -> Iterator[Built]:
    engine = create_db_engine(role_url("worker", url))  # the worker role in the roles mode
    backends = track_backends(engine)
    factory = create_session_factory(engine)
    extra: dict[str, object] = {}
    if clock is not None:
        extra["clock"] = clock
    try:
        yield Built(
            IngestionService(
                factory,
                embedder if embedder is not None else HookEmbedder(),
                default_limits(**limit_overrides),
                pdf_loader=pdf_loader,
                **extra,  # type: ignore[arg-type]
            ),
            engine,
            factory,
            backends,
        )
    finally:
        engine.dispose()


def track_backends(engine: Engine) -> set[int]:
    """The server process ids of the engine's open connections (kept up to date by events)."""
    backends: set[int] = set()

    @event.listens_for(engine, "connect")
    def remember(dbapi_connection: Any, _record: Any) -> None:
        backends.add(int(dbapi_connection.info.backend_pid))

    @event.listens_for(engine, "close")
    def forget(dbapi_connection: Any, _record: Any) -> None:
        backends.discard(int(dbapi_connection.info.backend_pid))

    return backends


def checked_out(engine: Engine) -> int:
    """Connections of the engine's pool currently in use (0 when none is held)."""
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    return pool.checkedout()


@dataclass(frozen=True)
class Activity:
    """What the sessions of the test database hold at one instant."""

    idle_in_transaction: int
    open_transactions: int
    locks: int
    stuck_in_transaction: int  # idle in a transaction for more than one second


def activity(url: str, backends: Collection[int] | None = None) -> Activity:
    """Idle-in-transaction, open transactions and held locks of the client backends.

    Without `backends` every client backend of the database counts (apart from this probe).
    With the `backends` of a service only its own connections count: the locks of an autovacuum
    worker, of another test's leftover session or of anything else are not its doing.
    """
    engine = create_db_engine(url)
    only = list(backends) if backends is not None else None
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT "
                    "count(*) FILTER (WHERE state LIKE 'idle in transaction%'), "
                    "count(*) FILTER (WHERE xact_start IS NOT NULL), "
                    "count(*) FILTER (WHERE state LIKE 'idle in transaction%' "
                    " AND now() - state_change > interval '1 second'), "
                    "(SELECT count(*) FROM pg_locks l WHERE l.pid <> pg_backend_pid() "
                    " AND l.granted "
                    " AND l.locktype IN ('relation','tuple','transactionid','advisory') "
                    " AND l.pid IN (SELECT pid FROM pg_stat_activity "
                    "               WHERE datname = current_database() "
                    "               AND backend_type = 'client backend' "
                    "               AND (CAST(:only AS int[]) IS NULL "
                    "                    OR pid = ANY(CAST(:only AS int[]))))) "
                    "FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                    "AND backend_type = 'client backend' "
                    "AND (CAST(:only AS int[]) IS NULL OR pid = ANY(CAST(:only AS int[])))"
                ),
                {"only": only},
            ).one()
    finally:
        engine.dispose()
    return Activity(int(row[0]), int(row[1]), int(row[3]), int(row[2]))


def capture_logs(caplog: object) -> None:
    """Capture every logger at DEBUG (the tests look for text that must never appear)."""
    caplog.set_level(logging.DEBUG)  # type: ignore[attr-defined]


def log_text(caplog: object) -> str:
    records = caplog.records  # type: ignore[attr-defined]
    parts = [record.getMessage() for record in records]
    parts += [str(record.exc_info) for record in records if record.exc_info]
    parts += [record.exc_text or "" for record in records]
    return "\n".join(parts)


def wait_until(condition: Callable[[], bool], timeout: float = 20.0, step: float = 0.05) -> bool:
    event = threading.Event()
    waited = 0.0
    while waited < timeout:
        if condition():
            return True
        event.wait(step)
        waited += step
    return condition()
