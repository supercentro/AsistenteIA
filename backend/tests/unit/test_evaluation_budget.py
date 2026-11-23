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
    reserve_run,
    settle_run,
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
        "authorised_total": 50,
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


# --- one authorisation, one run (2026-11-23) -----------------------------------------------------


def test_one_authorisation_covers_one_run_a_reservation_remembers_the_total_it_used(
    tmp_path: Path,
) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=204, spent=154)

    reserve_run(path, calls=45, date="2026-11-24", mode="answers", revision="x", note="n")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["entries"][-1]["authorised_total"] == 204
    assert data["authorised_total"] == 204  # the harness never writes the owner's number


def test_one_authorisation_a_second_run_under_the_same_total_is_refused_even_with_room_left(
    tmp_path: Path,
) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=204, spent=154)
    reserve_run(path, calls=45, date="2026-11-24", mode="answers", revision="x", note="n")
    settle_run(path, reserved=45, calls=3)  # the run aborted early: 47 of the 50 are still unspent

    ledger = load_ledger(path)

    assert remaining(ledger) == 47
    with pytest.raises(BudgetExhaustedError, match="already used"):
        require_budget(ledger, 1)


def test_one_authorisation_a_new_value_of_the_total_is_a_new_authorisation(tmp_path: Path) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=204, spent=154)
    reserve_run(path, calls=45, date="2026-11-24", mode="answers", revision="x", note="n")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["authorised_total"] = 260  # the owner decides it, by editing the file
    path.write_text(json.dumps(data), encoding="utf-8")

    require_budget(load_ledger(path), 45)  # no error: 260 was never used


def test_one_authorisation_the_history_without_the_field_does_not_count(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "authorised_total": 204,
                "spent": 154,
                "entries": [{"date": "2026-11-20", "mode": "answers", "calls": 44, "note": "old"}],
            }
        ),
        encoding="utf-8",
    )

    require_budget(load_ledger(path), 45)  # the first run, from before the field existed, is kept


def test_one_authorisation_the_refusal_names_the_total_and_what_the_owner_must_do(
    tmp_path: Path,
) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=204, spent=154)
    reserve_run(path, calls=45, date="2026-11-24", mode="answers", revision="x", note="n")

    with pytest.raises(BudgetExhaustedError) as error:
        require_budget(load_ledger(path), 1)

    message = str(error.value)
    assert "204" in message and "2026-11-24" in message and "new authorisation" in message


def test_one_authorisation_the_recorded_runs_of_the_old_helper_carry_the_total_too(
    tmp_path: Path,
) -> None:
    path = write_ledger(tmp_path / "ledger.json", authorised=80, spent=10)

    record_run(path, calls=5, date="2026-11-24", mode="answers", revision="x", note="n")

    assert json.loads(path.read_text(encoding="utf-8"))["entries"][-1]["authorised_total"] == 80


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        '{"authorised_total": 1e999, "spent": 0}',
        '{"authorised_total": 50, "spent": 0, "entries": [["authorised_total"]]}',
        '{"authorised_total": 50, "spent": 0, "entries": [{"authorised_total": "x"}]}',
        '{"authorised_total": 50, "spent": 0, "entries": 7}',
    ],
)
def test_one_authorisation_an_odd_ledger_is_refused_cleanly_not_with_a_raw_exception(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / "ledger.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(HarnessRefusedError, match="ledger"):
        load_ledger(path)
