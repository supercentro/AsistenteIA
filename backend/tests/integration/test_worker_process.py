"""A real `python -m app.worker` process against the test database (change 6, task 8.2).

Linux only: the worker refuses to start elsewhere because PDFs are parsed in an isolated child
that needs POSIX limits. The CI job and the worker image run these tests.
"""

import os
import signal
import subprocess
import sys
import textwrap
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.constants import TEST_JWT_SECRET
from tests.ingestion_support import (
    Scene,
    chunk_count,
    document_state,
    expire_lease,
    insert_pending,
    job_state,
    make_scene,
)
from tests.service_support import LONG_TEXT, wait_until
from tests.sql_support import scalar

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="the worker refuses to start outside Linux"
)

BACKEND = Path(__file__).resolve().parents[2]

SLOW_WORKER = textwrap.dedent(
    """
    import time
    from app.rag import embedder

    original = embedder.FakeEmbedder.embed
    state = {"calls": 0}

    def slow(self, texts):
        state["calls"] += 1
        if state["calls"] > 1:  # the first call is the start-up probe
            time.sleep(120)
        return original(self, texts)

    embedder.FakeEmbedder.embed = slow
    from app.worker import main

    raise SystemExit(main())
    """
)


@pytest.fixture
def scene(clean_db: str) -> Scene:
    return make_scene(clean_db)


def worker_environment(url: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in ("PATH", "HOME", "LANG")}
    env.update(
        APP_ENV="test",
        DATABASE_URL=url,
        JWT_SECRET=TEST_JWT_SECRET,
        EMBEDDER_BACKEND="fake",
        INGESTION_LEASE_SECONDS="3",
        INGESTION_JOB_DEADLINE_SECONDS="60",
        INGESTION_BATCH_SIZE="2",
        PYTHONUNBUFFERED="1",
    )
    return env


@contextmanager
def worker(url: str, script: str | None = None) -> Iterator[subprocess.Popen[bytes]]:
    command = [sys.executable, "-c", script] if script else [sys.executable, "-m", "app.worker"]
    process = subprocess.Popen(  # noqa: S603 - fixed command, no input from outside
        command,
        cwd=BACKEND,
        env=worker_environment(url),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=30)


def status(url: str, document: uuid.UUID) -> str:
    return str(document_state(url, document).get("status"))


def test_a_worker_process_ingests_a_document_and_stops_on_sigterm(scene: Scene) -> None:
    document, job = insert_pending(
        scene.url, scene.subject, payload=LONG_TEXT, filename="a.txt", content_type="text/plain"
    )

    with worker(scene.url) as process:
        assert wait_until(lambda: status(scene.url, document) == "ready", timeout=60)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=30) == 0  # graceful stop

    assert chunk_count(scene.url, document) == document_state(scene.url, document)["chunks_count"]
    assert job_state(scene.url, job)["has_payload"] is False


def test_a_job_of_a_killed_worker_is_completed_by_another_without_duplicates(
    scene: Scene,
) -> None:
    document, job = insert_pending(
        scene.url, scene.subject, payload=LONG_TEXT, filename="a.txt", content_type="text/plain"
    )

    with worker(scene.url, SLOW_WORKER) as victim:
        assert wait_until(lambda: status(scene.url, document) == "processing", timeout=60)
        victim.kill()  # killed in the middle of the job
        victim.wait(timeout=30)
    assert chunk_count(scene.url, document) == 0
    expire_lease(scene.url, job)  # (the lease would expire by itself in 3 seconds)

    with worker(scene.url) as rescuer:
        assert wait_until(lambda: status(scene.url, document) == "ready", timeout=60)
        rescuer.send_signal(signal.SIGTERM)
        rescuer.wait(timeout=30)

    state = document_state(scene.url, document)
    count = chunk_count(scene.url, document)
    assert count > 1
    assert count == state["chunks_count"]
    assert job_state(scene.url, job)["attempts"] == 2
    indexes = scalar(
        scene.url,
        "SELECT string_agg(chunk_index::text, ',' ORDER BY chunk_index) FROM document_chunks "
        "WHERE document_id = :d",
        d=document,
    )
    assert indexes == ",".join(str(i) for i in range(count))  # one set, no duplicates
