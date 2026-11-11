"""The ingestion worker: `python -m app.worker` (change 6, task 8.2; design D1, A2, A10).

A separate process from the HTTP application. It checks at start that PDFs can be parsed (Linux)
and that the embedder works (the model is loaded once, no fallback), then loops: sweep every 60
seconds, claim a job, process it with `IngestionService`, back off when idle. A signal stops it
after the current job. Logs carry identifiers and codes only.
"""

import logging
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import Protocol

from app.core.config import ConfigurationError, WorkerSettings, load_worker_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.logging import configure_logging
from app.rag.embedder import (
    EmbedderConfigurationError,
    EmbedderStartupError,
    build_embedder,
    startup_check,
)
from app.rag.loaders import UnsupportedPlatformError
from app.repositories.ingestion_job_repository import SweepResult
from app.services.ingestion_service import IngestionLimits, IngestionService, Outcome
from app.worker_health import BUSY_MARGIN_SECONDS, HEALTH_FILE, Beacon

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_REFUSED = 2
IDLE_MIN_SECONDS = 0.5
IDLE_MAX_SECONDS = 5.0
SWEEP_EVERY_SECONDS = 60.0

_REFUSAL_REASONS: dict[type[Exception], str] = {
    UnsupportedPlatformError: "PDF parsing is supported only on Linux",
    EmbedderConfigurationError: "the embedder configuration is not allowed here",
    EmbedderStartupError: "the embedder is not ready (model files, dimension or probe)",
    ConfigurationError: "the configuration is invalid",
}


class _Service(Protocol):
    def run_once(self) -> Outcome: ...

    def sweep(self) -> SweepResult: ...


def ensure_supported_platform(platform: str = sys.platform) -> None:
    """Raise `UnsupportedPlatformError` unless PDFs can be parsed in an isolated child (Linux)."""
    if not platform.startswith("linux"):
        raise UnsupportedPlatformError


class _Progress(Protocol):
    def step_started(self) -> None: ...

    def step_finished(self) -> None: ...


class WorkerLoop:
    """Sweep on a schedule, claim and process jobs, back off while idle, stop on request."""

    def __init__(
        self,
        service: _Service,
        stop: threading.Event,
        *,
        idle_min: float = IDLE_MIN_SECONDS,
        idle_max: float = IDLE_MAX_SECONDS,
        sweep_every: float = SWEEP_EVERY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], bool] | None = None,
        beacon: _Progress | None = None,
    ) -> None:
        self._beacon = beacon
        self._service = service
        self._stop = stop
        self._idle_min = idle_min
        self._idle_max = idle_max
        self._sweep_every = sweep_every
        self._clock = clock
        self._wait = wait if wait is not None else stop.wait

    def run(self) -> None:
        delay = self._idle_min
        last_sweep: float | None = None
        while not self._stop.is_set():
            now = self._clock()
            if last_sweep is None or now - last_sweep >= self._sweep_every:
                last_sweep = now
                self._guarded(self._service.sweep)
            outcome = self._guarded(self._service.run_once)
            if outcome is None or outcome is Outcome.IDLE:
                self._wait(delay)
                delay = min(delay * 2, self._idle_max)
            else:
                delay = self._idle_min  # more work may be waiting: no pause between jobs

    def _guarded[T](self, step: Callable[[], T]) -> T | None:
        """Run a step; an unexpected error is logged by type only and never ends the worker."""
        if self._beacon is not None:
            self._beacon.step_started()
        try:
            return step()
        except Exception as error:  # noqa: BLE001 - the text of the error is never logged
            logger.error("worker step failed: %s", type(error).__name__)
            return None
        finally:
            if self._beacon is not None:
                self._beacon.step_finished()


def install_signal_handlers(stop: threading.Event) -> Callable[[], None]:
    """Make SIGINT and SIGTERM request a graceful stop; return a function that restores them."""
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

    def request_stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    for sig in previous:
        signal.signal(sig, request_stop)

    def restore() -> None:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    return restore


def run_worker(
    settings: WorkerSettings,
    *,
    platform: str = sys.platform,
    stop: threading.Event | None = None,
    handle_signals: bool = False,
    health_file: Path = HEALTH_FILE,
) -> int:
    """Start-up checks, then the loop until `stop`; returns the process exit code."""
    stop = stop if stop is not None else threading.Event()
    try:
        ensure_supported_platform(platform)
        embedder = build_embedder(settings)
        startup_check(embedder)
    except (UnsupportedPlatformError, EmbedderConfigurationError, EmbedderStartupError) as error:
        logger.error("worker refused to start: %s", _REFUSAL_REASONS[type(error)])
        return EXIT_REFUSED

    engine = create_db_engine(
        settings.database_url,
        settings.db_connect_timeout_seconds,
        statement_timeout_seconds=settings.db_statement_timeout_worker_seconds,
        idle_in_transaction_timeout_seconds=settings.db_idle_in_transaction_timeout_seconds,
    )
    service = IngestionService(
        create_session_factory(engine), embedder, IngestionLimits.from_settings(settings)
    )
    restore = install_signal_handlers(stop) if handle_signals else None
    beacon = Beacon(
        health_file, busy_limit=settings.ingestion_job_deadline_seconds + BUSY_MARGIN_SECONDS
    )
    beacon.start()
    logger.info("ingestion worker started")
    try:
        WorkerLoop(service, stop, beacon=beacon).run()
    finally:
        beacon.stop()
        if restore is not None:
            restore()
        engine.dispose()
    logger.info("ingestion worker stopped")
    return EXIT_OK


def main() -> int:
    try:
        settings = load_worker_settings()
    except ConfigurationError:
        configure_logging("INFO")
        logger.error("worker refused to start: %s", _REFUSAL_REASONS[ConfigurationError])
        return EXIT_REFUSED
    configure_logging(settings.log_level)
    return run_worker(settings, handle_signals=True)


if __name__ == "__main__":
    raise SystemExit(main())
