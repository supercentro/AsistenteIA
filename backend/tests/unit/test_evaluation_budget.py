"""The persistent ledger of real model requests (change rag-golden-set-evaluation).

The owner authorises a total number of real free-tier requests; the ledger remembers what was
spent across runs, so that a later run cannot exceed the authorisation by forgetting the earlier
ones. Only the owner raises `authorised_total` (by editing the file).
"""

import json
import os
import pathlib
from pathlib import Path

import pytest

from tests.evaluation.budget import (
    BudgetExhaustedError,
    load_ledger,
    record_run,
    remaining,
    require_budget,
)
from tests.evaluation.guards import HarnessRefusedError


def write_ledger(path: Path, authorised: int = 50, spent: int = 10) -> Path:
    path.write_text(
        json.dumps({"authorised_total": authorised, "spent": spent, "entries": []}),
        encoding="utf-8",
    )
    return path


def test_the_remaining_budget_is_the_authorised_total_minus_what_was_spent(tmp_path: Path) -> None:
    ledger = load_ledger(write_ledger(tmp_path / "ledger.json", authorised=50, spent=44))

    assert remaining(ledger) == 6


def test_a_missing_ledger_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HarnessRefusedError, match="ledger"):
        load_ledger(tmp_path / "nope.json")


def test_a_corrupt_ledger_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text("not json", encoding="utf-8")

    with pytest.raises(HarnessRefusedError, match="ledger"):
        load_ledger(path)


def test_a_run_that_needs_more_than_the_remaining_budget_is_stopped_with_the_numbers(
    tmp_path: Path,
) -> None:
    ledger = load_ledger(write_ledger(tmp_path / "ledger.json", authorised=50, spent=44))

    with pytest.raises(BudgetExhaustedError) as stopped:
        require_budget(ledger, needed=7)

    assert "7" in str(stopped.value) and "6" in str(stopped.value)


def test_a_run_within_the_remaining_budget_is_accepted(tmp_path: Path) -> None:
    ledger = load_ledger(write_ledger(tmp_path / "ledger.json", authorised=50, spent=44))

    require_budget(ledger, needed=6)
    require_budget(ledger, needed=0)


def test_an_overspent_ledger_has_no_budget_at_all(tmp_path: Path) -> None:
    ledger = load_ledger(write_ledger(tmp_path / "ledger.json", authorised=50, spent=154))

    assert remaining(ledger) == 0
    with pytest.raises(BudgetExhaustedError):
        require_budget(ledger, needed=1)


def test_recording_a_run_adds_it_to_the_total_and_keeps_the_history(tmp_path: Path) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=50, spent=10)

    record_run(path, calls=7, date="2026-11-21", mode="answers", revision="abc", note="test")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spent"] == 17
    assert data["authorised_total"] == 50
    assert data["entries"][-1] == {
        "date": "2026-11-21",
        "mode": "answers",
        "revision": "abc",
        "calls": 7,
        "note": "test",
    }


def test_recording_never_raises_the_authorised_total(tmp_path: Path) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=50, spent=49)

    record_run(path, calls=10, date="2026-11-21", mode="answers", revision="abc", note="")

    assert json.loads(path.read_text(encoding="utf-8"))["authorised_total"] == 50
    assert remaining(load_ledger(path)) == 0


def test_reserving_records_the_calls_before_they_are_made(tmp_path: Path) -> None:
    from tests.evaluation.budget import reserve_run

    path = write_ledger(tmp_path / "ledger.json", authorised=50, spent=10)

    reserve_run(path, calls=8, date="2026-11-21", mode="answers", revision="abc", note="n")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spent"] == 18
    assert data["entries"][-1]["calls"] == 8
    assert data["entries"][-1]["reserved"] is True


def test_settling_replaces_the_reservation_with_the_calls_really_made(tmp_path: Path) -> None:
    from tests.evaluation.budget import reserve_run, settle_run

    path = write_ledger(tmp_path / "ledger.json", authorised=50, spent=10)
    reserve_run(path, calls=8, date="2026-11-21", mode="answers", revision="abc", note="n")

    settle_run(path, reserved=8, calls=3)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spent"] == 13
    assert data["entries"][-1]["calls"] == 3
    assert "reserved" not in data["entries"][-1]


def test_a_ledger_that_cannot_be_written_stops_the_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.evaluation import budget

    path = write_ledger(tmp_path / "ledger.json", authorised=50, spent=10)

    def refuse(self: Path, *args: object, **kwargs: object) -> int:
        raise PermissionError("read-only")

    monkeypatch.setattr(pathlib.Path, "write_text", refuse)

    with pytest.raises(HarnessRefusedError, match="ledger"):
        budget.reserve_run(path, calls=1, date="d", mode="m", revision="r", note="")


def test_writing_falls_back_to_in_place_when_the_file_cannot_be_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.evaluation import budget

    path = write_ledger(tmp_path / "ledger.json", authorised=50, spent=10)

    def busy(source: object, target: object) -> None:
        raise OSError(16, "device or resource busy")  # a single file bind-mounted in Docker

    monkeypatch.setattr(os, "replace", busy)

    budget.record_run(path, calls=2, date="d", mode="m", revision="r", note="")

    assert json.loads(path.read_text(encoding="utf-8"))["spent"] == 12
