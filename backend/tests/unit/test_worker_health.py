"""The worker reports real health and ends itself when it stalls (review finding R-02).

A restart policy only restarts a container whose process ends; a worker that is alive but stuck
would stay `running` for ever. The beacon writes a health file only while the loop is demonstrably
making progress (a short idle gap, or a job still inside its deadline plus a margin) and ends the
process with a distinct code when it is not, so Docker restarts it. The lease, the fencing and the
retries are untouched: a job interrupted this way is recovered by the lease like after any crash.
"""

import os
import threading
from pathlib import Path

import pytest

from app.services.ingestion_service import Outcome
from app.worker import WorkerLoop
from app.worker_health import (
    EXIT_STALLED,
    HEALTH_FILE,
    HEALTH_MAX_AGE_SECONDS,
    Beacon,
    check,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_beacon(
    tmp_path: Path, clock: Clock, exits: list[int] | None = None, **kwargs: float
) -> Beacon:
    recorded = exits if exits is not None else []
    return Beacon(
        tmp_path / "health",
        busy_limit=kwargs.pop("busy_limit", 720.0),
        idle_limit=kwargs.pop("idle_limit", 120.0),
        clock=clock,
        exit_fn=recorded.append,
        **kwargs,
    )


# --- what "healthy" means -------------------------------------------------------------------------


def test_a_fresh_idle_worker_is_healthy(tmp_path: Path) -> None:
    clock = Clock()
    beacon = make_beacon(tmp_path, clock)

    assert beacon.healthy() is True


def test_an_idle_worker_that_stops_making_steps_becomes_unhealthy(tmp_path: Path) -> None:
    clock = Clock()
    beacon = make_beacon(tmp_path, clock, idle_limit=120.0)
    beacon.step_finished()

    clock.now += 119
    assert beacon.healthy() is True
    clock.now += 2
    assert beacon.healthy() is False


def test_a_long_job_inside_its_deadline_is_not_a_false_positive(tmp_path: Path) -> None:
    clock = Clock()
    beacon = make_beacon(tmp_path, clock, busy_limit=720.0)
    beacon.step_started()

    clock.now += 600  # the whole job deadline of inference
    assert beacon.healthy() is True
    clock.now += 119
    assert beacon.healthy() is True


def test_a_step_that_never_returns_becomes_unhealthy_after_the_deadline_and_its_margin(
    tmp_path: Path,
) -> None:
    clock = Clock()
    beacon = make_beacon(tmp_path, clock, busy_limit=720.0)
    beacon.step_started()

    clock.now += 721

    assert beacon.healthy() is False


def test_finishing_a_step_resets_both_clocks(tmp_path: Path) -> None:
    clock = Clock()
    beacon = make_beacon(tmp_path, clock)
    beacon.step_started()
    clock.now += 700
    beacon.step_finished()
    clock.now += 100

    assert beacon.healthy() is True


# --- the file and the exit ------------------------------------------------------------------------


def test_beat_writes_the_health_file_only_while_healthy(tmp_path: Path) -> None:
    clock = Clock()
    exits: list[int] = []
    beacon = make_beacon(tmp_path, clock, exits)

    beacon.beat()

    assert (tmp_path / "health").exists()
    assert exits == []


def test_beat_ends_the_process_with_the_stalled_code_when_unhealthy(tmp_path: Path) -> None:
    clock = Clock()
    exits: list[int] = []
    beacon = make_beacon(tmp_path, clock, exits)
    clock.now += 500  # idle for far longer than the idle limit

    beacon.beat()

    assert exits == [EXIT_STALLED]
    assert EXIT_STALLED not in (0, 2)  # distinct from a clean stop and from a refusal to start


def test_an_unhealthy_beacon_does_not_refresh_the_file(tmp_path: Path) -> None:
    clock = Clock()
    beacon = make_beacon(tmp_path, clock)
    beacon.beat()
    os.utime(tmp_path / "health", (1.0, 1.0))
    clock.now += 500

    beacon.beat()

    assert (tmp_path / "health").stat().st_mtime == 1.0


def test_an_unwritable_health_file_is_not_a_crash(tmp_path: Path) -> None:
    clock = Clock()
    beacon = Beacon(
        tmp_path / "missing-dir" / "health",
        busy_limit=720.0,
        clock=clock,
        exit_fn=lambda code: None,
    )

    beacon.beat()  # must not raise

    assert not (tmp_path / "missing-dir").exists()


def test_the_thread_beats_and_stops_cleanly(tmp_path: Path) -> None:
    beacon = Beacon(tmp_path / "health", busy_limit=720.0, interval=0.01, exit_fn=lambda c: None)

    beacon.start()
    for _ in range(200):
        if (tmp_path / "health").exists():
            break
        threading.Event().wait(0.01)
    beacon.stop()

    assert (tmp_path / "health").exists()
    assert not beacon.is_running


# --- the healthcheck command ----------------------------------------------------------------------


def test_the_check_passes_for_a_fresh_file(tmp_path: Path) -> None:
    path = tmp_path / "health"
    path.touch()

    assert check(path, now=path.stat().st_mtime + 5) == 0


def test_the_check_fails_for_a_stale_file(tmp_path: Path) -> None:
    path = tmp_path / "health"
    path.touch()

    assert check(path, now=path.stat().st_mtime + HEALTH_MAX_AGE_SECONDS + 1) == 1


def test_the_check_fails_when_the_file_does_not_exist(tmp_path: Path) -> None:
    assert check(tmp_path / "absent", now=1e12) == 1


def test_the_defaults_leave_room_for_the_beat_interval() -> None:
    assert HEALTH_MAX_AGE_SECONDS >= 30
    # writable by the non-root user and outside /app
    assert str(HEALTH_FILE).startswith("/tmp/")  # noqa: S108


def test_the_health_module_needs_nothing_heavy() -> None:
    import subprocess
    import sys

    code = (
        "import sys, app.worker_health\n"
        "heavy = [m for m in ('torch', 'sqlalchemy', 'sentence_transformers', 'fastapi')"
        " if m in sys.modules]\n"
        "print(','.join(heavy))\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed arguments, test-only
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


# --- the loop reports its steps -------------------------------------------------------------------


class RecordingBeacon:
    def __init__(self) -> None:
        self.events: list[str] = []

    def step_started(self) -> None:
        self.events.append("start")

    def step_finished(self) -> None:
        self.events.append("end")


class StepService:
    def __init__(self, stop: threading.Event, fail: bool = False) -> None:
        self.stop = stop
        self.fail = fail
        self.runs = 0

    def run_once(self) -> Outcome:
        self.runs += 1
        self.stop.set()
        if self.fail:
            raise RuntimeError("boom")
        return Outcome.IDLE

    def sweep(self) -> None:
        return None


def test_the_loop_reports_every_step_start_and_end() -> None:
    stop = threading.Event()
    beacon = RecordingBeacon()
    loop = WorkerLoop(StepService(stop), stop, wait=lambda s: True, beacon=beacon)  # type: ignore[arg-type]

    loop.run()

    assert beacon.events == ["start", "end", "start", "end"]  # the sweep, then one job step


def test_a_failing_step_still_reports_its_end() -> None:
    stop = threading.Event()
    beacon = RecordingBeacon()
    loop = WorkerLoop(
        StepService(stop, fail=True),  # type: ignore[arg-type]
        stop,
        wait=lambda s: True,
        beacon=beacon,
    )

    loop.run()

    assert beacon.events.count("start") == beacon.events.count("end") == 2


# --- the wiring in run_worker ---------------------------------------------------------------------


def test_run_worker_starts_the_beacon_gives_it_to_the_loop_and_stops_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import worker as worker_module
    from app.core.config import WorkerSettings
    from app.worker_health import BUSY_MARGIN_SECONDS

    seen: dict[str, object] = {"events": []}
    events: list[str] = seen["events"]  # type: ignore[assignment]

    class FakeBeacon:
        def __init__(self, path: Path, *, busy_limit: float) -> None:
            seen["path"] = path
            seen["busy_limit"] = busy_limit

        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

        def step_started(self) -> None: ...

        def step_finished(self) -> None: ...

    class FakeLoop:
        def __init__(
            self, service: object, stop: threading.Event, *, beacon: object = None
        ) -> None:
            seen["loop_beacon"] = beacon

        def run(self) -> None:
            events.append("run")

    monkeypatch.setattr(worker_module, "Beacon", FakeBeacon)
    monkeypatch.setattr(worker_module, "WorkerLoop", FakeLoop)
    settings = WorkerSettings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost/db",
        app_env="test",
        embedder_backend="fake",
        embedding_model_path=tmp_path / "missing-model",
        ingestion_job_deadline_seconds=600,
    )

    code = worker_module.run_worker(
        settings, platform="linux", stop=threading.Event(), health_file=tmp_path / "health"
    )

    assert code == 0
    assert events == ["start", "run", "stop"]
    assert isinstance(seen["loop_beacon"], FakeBeacon)
    assert seen["path"] == tmp_path / "health"
    assert seen["busy_limit"] == 600 + BUSY_MARGIN_SECONDS


# --- a stale health file must not outlive its process (second review, S-02) ------------------


def test_clear_removes_a_stale_file_and_tolerates_a_missing_one(tmp_path: Path) -> None:
    from app.worker_health import clear

    path = tmp_path / "health"
    path.touch()

    clear(path)
    clear(path)  # already gone: no error

    assert not path.exists()


def test_run_worker_removes_the_previous_health_file_before_anything_else(
    tmp_path: Path,
) -> None:
    from app import worker as worker_module
    from app.core.config import WorkerSettings

    stale = tmp_path / "health"
    stale.touch()
    settings = WorkerSettings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@localhost/db",
        app_env="test",
        embedder_backend="fake",
        embedding_model_path=tmp_path / "missing-model",
    )

    code = worker_module.run_worker(
        settings, platform="win32", stop=threading.Event(), health_file=stale
    )

    assert code == worker_module.EXIT_REFUSED  # it refused to start, yet the old file is gone
    assert not stale.exists()
