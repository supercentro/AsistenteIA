"""Mutation checks of the consent endpoint fix (group 7). The repository is never edited: the unit
tests run on a scratch copy of backend/app and backend/tests, one mutation at a time, and the run
prints which test failed. Against the disposable PostgreSQL the first mutation (no commit in the
handler) is the code before the fix: `run-integration-red.txt` shows the integration tests failing
with it. The other mutations are not run against PostgreSQL.

usage: python mutate_consent.py <repo root> <scratch dir>
"""

import shutil
import subprocess
import sys
from pathlib import Path

ENDPOINT = "app/api/v1/endpoints/users.py"
COMMIT = "        db.commit()\n"
PYTHON = str(Path(sys.argv[1]) / "backend/.venv/Scripts/python.exe")
ROLLBACK = "        db.rollback()\n        raise\n"

MUTATIONS: list[tuple[str, str, str]] = [
    ("the commit is removed (the original defect)", COMMIT, "        pass\n"),
    ("the commit is only a flush", COMMIT, "        db.flush()\n"),
    ("the rollback is removed", ROLLBACK, "        raise\n"),
    ("the database error is swallowed", ROLLBACK, "        db.rollback()\n"),
    (
        "the commit happens before the user is updated",
        "    updated = service.record(user, body.consent_version)\n    try:\n",
        "    db.commit()\n    updated = service.record(user, body.consent_version)\n    try:\n",
    ),
    ("only ValueError is rolled back", "    except Exception:\n", "    except ValueError:\n"),
    ("the commit happens twice", COMMIT, "        db.commit()\n        db.commit()\n"),
    (
        "the version is not validated before committing",
        "    updated = service.record(user, body.consent_version)\n",
        "    updated = user\n",
    ),
]


def run_tests(work: Path) -> tuple[int, str]:
    result = subprocess.run(
        [PYTHON, "-m", "pytest", "tests/unit/test_consent_endpoint.py",
         "-q", "-p", "no:cacheprovider", "-x"],
        cwd=work, capture_output=True, text=True, check=False,
    )
    failed = [line for line in result.stdout.splitlines() if line.startswith("FAILED")]
    return result.returncode, (failed[0].split("::")[-1].split(" - ")[0] if failed else "")


def main() -> int:
    repo, scratch = Path(sys.argv[1]), Path(sys.argv[2])
    caught = 0
    for index, (label, old, new) in enumerate(MUTATIONS):
        work = scratch / f"m{index}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for name in ("app", "tests"):
            shutil.copytree(repo / "backend" / name, work / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(repo / "backend/pyproject.toml", work / "pyproject.toml")
        target = work / ENDPOINT
        text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
        if text.count(old) != 1:
            print(f"SKIPPED   {label} (pattern found {text.count(old)} times)")
            continue
        target.write_text(text.replace(old, new), encoding="utf-8")
        code, test = run_tests(work)
        status = "CAUGHT   " if code == 1 and test else "SURVIVED "
        caught += status.startswith("CAUGHT")
        print(f"{status} {label} | {test}")
        shutil.rmtree(work, ignore_errors=True)
    print(f"mutations: {len(MUTATIONS)}, caught: {caught}")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
