"""Persistent ledger of the real model requests, so that no run can forget the earlier ones.

The owner decides `authorised_total` (the number of real free-tier requests allowed in total) by
editing the file; the harness only adds to `spent`. A run is stopped before its first call when it
needs more than what is left. **One authorisation covers one run**: every run records the value of
`authorised_total` it ran under, and a later run under the same value is refused even when room is
left, so that the owner must give a new authorisation (a different value) for each run. The harness
never writes `authorised_total` and never rewrites the history. The provider's own quota is not
visible from here: the ledger is the authorisation, not the provider's counter.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.evaluation.guards import HarnessRefusedError


class BudgetExhaustedError(HarnessRefusedError):
    """The ledger has no room for the requests a run needs; raised before any call."""


@dataclass(frozen=True)
class Ledger:
    path: Path
    authorised_total: int
    spent: int
    # (date, authorised_total) of the runs that recorded the total they ran under
    used_authorisations: tuple[tuple[str, int], ...] = ()


def load_ledger(path: Path) -> Ledger:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        used = tuple(
            (str(entry.get("date", "?")), int(entry["authorised_total"]))
            for entry in data.get("entries", [])
            if "authorised_total" in entry
        )
        return Ledger(path, int(data["authorised_total"]), int(data["spent"]), used)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
        raise HarnessRefusedError(
            f"the request ledger {path.name!r} is missing or invalid (see the step 3.3 report)"
        ) from None


def remaining(ledger: Ledger) -> int:
    return max(0, ledger.authorised_total - ledger.spent)


def require_budget(ledger: Ledger, needed: int) -> None:
    for date, total in ledger.used_authorisations:
        if total == ledger.authorised_total:
            raise BudgetExhaustedError(
                f"budget: the authorisation of {total} real requests was already used by the run "
                f"of {date}; each run needs a new authorisation (a different authorised_total "
                "set by the owner), even when requests are left"
            )
    left = remaining(ledger)
    if needed > left:
        raise BudgetExhaustedError(
            f"budget: {needed} real requests are needed but {left} are left of "
            f"{ledger.authorised_total} authorised ({ledger.spent} already spent); only the "
            "owner raises authorised_total in the ledger"
        )


def _write(path: Path, data: dict[str, Any]) -> None:
    """Replace the file atomically; where that is impossible (a single file bind-mounted in
    Docker) write it in place; if neither works the run must not go on."""
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
        return
    except OSError:
        pass
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        raise HarnessRefusedError(
            "the request ledger cannot be written: mount its directory writable"
        ) from None
    finally:
        temporary.unlink(missing_ok=True)


def _read(path: Path) -> dict[str, Any]:
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        int(data["spent"])
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise HarnessRefusedError("the request ledger is missing or invalid") from None


def reserve_run(path: Path, *, calls: int, date: str, mode: str, revision: str, note: str) -> None:
    """Record the calls of a run BEFORE the first one: a killed process still leaves them spent."""
    data = _read(path)
    data["spent"] = int(data["spent"]) + calls
    data.setdefault("entries", []).append(
        {
            "date": date,
            "mode": mode,
            "revision": revision,
            "calls": calls,
            "reserved": True,
            "authorised_total": int(data["authorised_total"]),
            "note": note,
        }
    )
    _write(path, data)


def settle_run(path: Path, *, reserved: int, calls: int) -> None:
    """Replace the reservation of the run by the calls it really made (never more)."""
    data = _read(path)
    data["spent"] = int(data["spent"]) - reserved + calls
    for entry in reversed(data.get("entries", [])):
        if entry.get("reserved"):
            entry["calls"] = calls
            del entry["reserved"]
            break
    _write(path, data)


def record_run(path: Path, *, calls: int, date: str, mode: str, revision: str, note: str) -> None:
    """Add the calls of a run to the ledger; never changes `authorised_total`."""
    data = _read(path)
    data["spent"] = int(data["spent"]) + calls
    data.setdefault("entries", []).append(
        {
            "date": date,
            "mode": mode,
            "revision": revision,
            "calls": calls,
            "authorised_total": int(data["authorised_total"]),
            "note": note,
        }
    )
    _write(path, data)
