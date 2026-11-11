"""Health of the ingestion worker (review finding R-02). Standard library only.

Two jobs, one file:

- `Beacon` runs inside the worker. A small thread writes `HEALTH_FILE` every few seconds **only
  while the loop is making progress**: the gap since the last finished step is short, or the step
  in progress is still inside the job deadline plus a margin (so a long inference is not a false
  positive). When neither holds the thread ends the process with `EXIT_STALLED`, so the Compose
  restart policy brings a fresh worker; a healthcheck alone restarts nothing. The lease, fencing
  and retries are not involved: a job cut this way is recovered like after any crash.
- `python -m app.worker_health` is the Compose healthcheck: exit 0 when the file is recent.
"""

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

HEALTH_FILE = Path("/tmp/ingestion-worker.health")  # noqa: S108 - the container's own /tmp
HEALTH_MAX_AGE_SECONDS = 60
BEAT_INTERVAL_SECONDS = 10.0
IDLE_LIMIT_SECONDS = 120.0  # sweep every 60 s + a database statement timeout of 60 s
BUSY_MARGIN_SECONDS = 120.0  # added to the job deadline
EXIT_STALLED = 3


class Beacon:
    """Tracks the worker steps, writes the health file and ends a stalled process."""

    def __init__(
        self,
        path: Path = HEALTH_FILE,
        *,
        busy_limit: float,
        idle_limit: float = IDLE_LIMIT_SECONDS,
        interval: float = BEAT_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        exit_fn: Callable[[int], object] = os._exit,
    ) -> None:
        self._path = path
        self._busy_limit = busy_limit
        self._idle_limit = idle_limit
        self._interval = interval
        self._clock = clock
        self._exit = exit_fn
        self._lock = threading.Lock()
        self._busy_since: float | None = None
        self._last_progress = clock()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def step_started(self) -> None:
        with self._lock:
            self._busy_since = self._clock()

    def step_finished(self) -> None:
        with self._lock:
            self._busy_since = None
            self._last_progress = self._clock()

    def healthy(self) -> bool:
        with self._lock:
            now = self._clock()
            if self._busy_since is not None:
                return now - self._busy_since <= self._busy_limit
            return now - self._last_progress <= self._idle_limit

    def beat(self) -> bool:
        """One watchdog round: refresh the file when healthy, otherwise end the process."""
        if not self.healthy():
            logger.error("ingestion worker stalled: ending the process so it is restarted")
            self._exit(EXIT_STALLED)
            return False
        try:
            self._path.touch()
        except OSError as error:
            logger.warning("cannot write the health file: %s", type(error).__name__)
        return True

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self.beat()
        self._thread = threading.Thread(target=self._run, name="worker-health", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        while not self._stopped.wait(self._interval):
            self.beat()


def clear(path: Path = HEALTH_FILE) -> None:
    """Remove a file left by a previous run, so a restarted worker is not reported healthy by it."""
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        logger.warning("cannot remove the old health file: %s", type(error).__name__)


def check(path: Path = HEALTH_FILE, *, now: float | None = None) -> int:
    """0 when the health file exists and is recent, otherwise 1."""
    try:
        age = (time.time() if now is None else now) - path.stat().st_mtime
    except OSError:
        return 1
    return 0 if age <= HEALTH_MAX_AGE_SECONDS else 1


def main() -> int:
    return check()


if __name__ == "__main__":
    sys.exit(main())
