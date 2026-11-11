"""The worker loop and start-up of `python -m app.worker` (change 6, task 8.2), with fakes."""

import logging
import signal
import threading
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.core.config import WorkerSettings
from app.rag.loaders import UnsupportedPlatformError
from app.repositories.ingestion_job_repository import SweepResult
from app.services.ingestion_service import Outcome
from app.worker import (
    EXIT_REFUSED,
    WorkerLoop,
    ensure_supported_platform,
    install_signal_handlers,
    run_worker,
)

DB_URL = "postgresql+psycopg://user:pw@localhost:5432/asistenteia"


class FakeService:
    def __init__(self, outcomes: Sequence[Outcome | BaseException], stop: threading.Event) -> None:
        self.outcomes = list(outcomes)
        self.stop = stop
        self.sweeps = 0
        self.runs = 0

    def run_once(self) -> Outcome:
        self.runs += 1
        if not self.outcomes:
            self.stop.set()
            return Outcome.IDLE
        item = self.outcomes.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def sweep(self) -> SweepResult:
        self.sweeps += 1
        return SweepResult(0, 0, 0)


class Timeline:
    """A fake clock that advances by every wait, and a record of the waits."""

    def __init__(self, stop: threading.Event) -> None:
        self.now = 0.0
        self.waits: list[float] = []
        self.stop = stop

    def clock(self) -> float:
        return self.now

    def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        self.now += seconds
        return self.stop.is_set()


def make_loop(
    outcomes: Sequence[Outcome | BaseException], **kwargs: float
) -> tuple[WorkerLoop, FakeService, Timeline, threading.Event]:
    stop = threading.Event()
    service = FakeService(outcomes, stop)
    timeline = Timeline(stop)
    loop = WorkerLoop(service, stop, clock=timeline.clock, wait=timeline.wait, **kwargs)
    return loop, service, timeline, stop


class TestIdleBackOff:
    def test_waits_grow_up_to_the_cap(self) -> None:
        loop, _, timeline, _ = make_loop([Outcome.IDLE] * 6, idle_min=0.5, idle_max=5.0)

        loop.run()

        assert timeline.waits[:6] == [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]

    def test_work_resets_the_wait_and_needs_no_wait_between_jobs(self) -> None:
        outcomes = [Outcome.IDLE, Outcome.IDLE, Outcome.READY, Outcome.FAILED, Outcome.IDLE]
        loop, service, timeline, _ = make_loop(outcomes, idle_min=0.5, idle_max=5.0)

        loop.run()

        assert timeline.waits[:3] == [0.5, 1.0, 0.5]  # after READY and FAILED: no wait at all
        assert service.runs == 6

    @pytest.mark.parametrize("outcome", [Outcome.LOST, Outcome.ABANDONED])
    def test_a_lost_or_abandoned_job_also_counts_as_work(self, outcome: Outcome) -> None:
        loop, _, timeline, _ = make_loop([Outcome.IDLE, outcome, Outcome.IDLE], idle_min=1.0)

        loop.run()

        assert timeline.waits[:2] == [1.0, 1.0]


class TestSweepSchedule:
    def test_sweeps_at_start_and_every_interval(self) -> None:
        loop, service, timeline, _ = make_loop(
            [Outcome.IDLE] * 40, idle_min=5.0, idle_max=5.0, sweep_every=60.0
        )

        loop.run()

        # 40 idle rounds of 5 s = 200 s: at 0, 60, 120 and 180.
        assert service.sweeps == 4
        assert timeline.now >= 200

    def test_a_failing_sweep_does_not_stop_the_worker(self) -> None:
        loop, service, _, _ = make_loop([Outcome.READY, Outcome.IDLE])

        def broken() -> SweepResult:
            raise RuntimeError("sweep failed")

        service.sweep = broken  # type: ignore[method-assign]

        loop.run()

        assert service.runs == 3  # READY, IDLE, then the stop


class TestResilienceAndStop:
    def test_an_unexpected_error_is_logged_by_type_only_and_the_loop_goes_on(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        loop, service, timeline, _ = make_loop(
            [RuntimeError("SECRET-LOOP-MARKER"), Outcome.READY], idle_min=0.5
        )

        loop.run()

        text = "\n".join(record.getMessage() + str(record.exc_info) for record in caplog.records)
        assert "RuntimeError" in text
        assert "SECRET-LOOP-MARKER" not in text
        assert service.runs == 3
        assert timeline.waits[0] == 0.5  # it backs off after an error

    def test_the_current_job_finishes_and_no_new_one_is_claimed_after_the_signal(self) -> None:
        stop = threading.Event()
        started = []

        class Service(FakeService):
            def run_once(self) -> Outcome:
                started.append(1)
                stop.set()  # the signal arrives while this job runs
                return Outcome.READY

        service = Service([], stop)
        timeline = Timeline(stop)
        WorkerLoop(service, stop, clock=timeline.clock, wait=timeline.wait).run()

        assert started == [1]

    def test_a_stop_during_the_idle_wait_ends_the_loop_at_once(self) -> None:
        stop = threading.Event()
        service = FakeService([Outcome.IDLE] * 100, stop)
        loop = WorkerLoop(service, stop, idle_min=30.0, idle_max=30.0)
        timer = threading.Timer(0.2, stop.set)
        timer.start()

        loop.run()  # real Event.wait: returns as soon as the event is set

        timer.join()
        assert service.runs <= 2

    def test_signals_set_the_stop_event_and_are_restored(self) -> None:
        stop = threading.Event()
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

        restore = install_signal_handlers(stop)
        try:
            handler = signal.getsignal(signal.SIGTERM)
            assert callable(handler)
            handler(signal.SIGTERM, None)
            assert stop.is_set()
            stop.clear()
            interrupt = signal.getsignal(signal.SIGINT)
            assert callable(interrupt)
            interrupt(signal.SIGINT, None)
            assert stop.is_set()
        finally:
            restore()

        assert {sig: signal.getsignal(sig) for sig in previous} == previous


def settings(tmp_path: Path, **overrides: object) -> WorkerSettings:
    values: dict[str, object] = {
        "app_env": "test",
        "database_url": DB_URL,
        "embedder_backend": "fake",
        "embedding_model_path": tmp_path / "missing-model",
    }
    values.update(overrides)
    return WorkerSettings(_env_file=None, **values)  # type: ignore[arg-type]


def stopped() -> threading.Event:
    """An already-set stop event: a worker that wrongly starts exits at once instead of hanging."""
    event = threading.Event()
    event.set()
    return event


class TestStartupRefusals:
    def test_pdf_parsing_outside_linux_is_refused(self) -> None:
        with pytest.raises(UnsupportedPlatformError):
            ensure_supported_platform("win32")
        with pytest.raises(UnsupportedPlatformError):
            ensure_supported_platform("darwin")
        ensure_supported_platform("linux")

    def test_the_worker_does_not_start_outside_linux(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        code = run_worker(settings(tmp_path), platform="win32", stop=stopped())

        assert code == EXIT_REFUSED
        assert "refused to start" in caplog.text

    def test_the_worker_does_not_start_without_the_model(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        code = run_worker(
            settings(tmp_path, embedder_backend="local"), platform="linux", stop=stopped()
        )

        assert code == EXIT_REFUSED
        assert "refused to start" in caplog.text
        assert str(tmp_path) not in caplog.text  # no paths in the log

    def test_the_fake_embedder_is_refused_in_production(self, tmp_path: Path) -> None:
        # The settings validator already refuses it; the worker must never fall back silently.
        with pytest.raises(ValueError, match="EMBEDDER_BACKEND=fake"):
            settings(tmp_path, app_env="production")

    def test_a_failing_startup_probe_refuses_to_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app import worker as worker_module
        from app.rag.embedder import EmbedderStartupError

        def probe(embedder: object) -> None:
            raise EmbedderStartupError("the embedder startup check failed")

        monkeypatch.setattr(worker_module, "startup_check", probe)
        caplog.set_level(logging.INFO)

        code = run_worker(settings(tmp_path), platform="linux", stop=stopped())

        assert code == EXIT_REFUSED
        assert "refused to start" in caplog.text


class TestRunAndMain:
    def test_a_stopped_worker_starts_and_exits_cleanly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        code = run_worker(settings(tmp_path), platform="linux", stop=stopped(), handle_signals=True)

        assert code == 0
        assert "ingestion worker started" in caplog.text
        assert "ingestion worker stopped" in caplog.text

    def test_the_signal_handlers_are_restored_after_the_run(self, tmp_path: Path) -> None:
        before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

        run_worker(settings(tmp_path), platform="linux", stop=stopped(), handle_signals=True)

        assert {sig: signal.getsignal(sig) for sig in before} == before

    def test_main_runs_the_worker_with_the_loaded_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import worker as worker_module

        loaded = settings(tmp_path)
        received: list[tuple[WorkerSettings, bool]] = []

        def fake_run(config: WorkerSettings, *, handle_signals: bool = False, **_: object) -> int:
            received.append((config, handle_signals))
            return 0

        monkeypatch.setattr(worker_module, "load_worker_settings", lambda: loaded)
        monkeypatch.setattr(worker_module, "run_worker", fake_run)

        assert worker_module.main() == 0
        assert received == [(loaded, True)]

    def test_main_refuses_to_start_with_an_invalid_configuration(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from app import worker as worker_module
        from app.core.config import ConfigurationError

        def broken() -> WorkerSettings:
            raise ConfigurationError("DATABASE_URL: SECRET-CONFIG-MARKER")

        monkeypatch.setattr(worker_module, "load_worker_settings", broken)
        caplog.set_level(logging.INFO)

        assert worker_module.main() == EXIT_REFUSED
        assert "refused to start" in caplog.text
        assert "SECRET-CONFIG-MARKER" not in caplog.text
