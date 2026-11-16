"""Mutations of the CI privilege gate (task 10.3), applied to a COPY of the repository, never to it.

usage: python mutate_gate.py <repository root> <scratch directory>

Each mutation edits one file of the copy of `.github/` and runs the unit tests that guard the
workflow and the gate scripts on it; a mutation is caught when they fail. The behaviour of the job
(exit codes, skipped tests, missing prerequisites, foreign databases, new tables) is proved
against real clusters by `run_gate_local.sh` and the `gate-*.txt` files of this folder.
"""

import shutil
import subprocess
import sys
from pathlib import Path

WORKFLOW = ".github/workflows/ci.yml"
GATE = ".github/scripts/privilege_gate.sh"
RESULTS = ".github/scripts/check_results.py"
CLUSTER = ".github/scripts/assert_disposable_cluster.py"

MUTATIONS: list[tuple[str, str, str, str]] = [
    ("the gate job may fail without failing the workflow", WORKFLOW, "    timeout-minutes: 40\n", "    timeout-minutes: 40\n    continue-on-error: true\n"),
    ("the workflow token gets default rights", WORKFLOW, "permissions:\n  contents: read\n\njobs:", "jobs:"),
    ("the summary no longer runs after a failure", WORKFLOW, "        if: always()\n", ""),
    ("the workflow runs on pull_request_target", WORKFLOW, "  pull_request:\n\n# The workflow token", "  pull_request_target:\n\n# The workflow token"),
    ("a gate step hides its failure", WORKFLOW, "privilege_gate.sh roles-mode", "privilege_gate.sh roles-mode || true"),
    (
        "the gate checkout keeps the token",
        WORKFLOW,
        '          persist-credentials: false\n      - uses: astral-sh/setup-uv@v5\n        with:\n          version: "0.12.9"\n      - name: Install dependencies',
        '          persist-credentials: true\n      - uses: astral-sh/setup-uv@v5\n        with:\n          version: "0.12.9"\n      - name: Install dependencies',
    ),
    ("the gate runs on a self-hosted runner", WORKFLOW, "  privileges:\n    runs-on: ubuntu-latest", "  privileges:\n    runs-on: self-hosted"),
    ("the two clusters share a port", WORKFLOW, "          - 5434:5432", "          - 5433:5432"),
    ("an administrator URL is job-wide", WORKFLOW, "      APP_ENV: test\n      FLOW_PORT", "      APP_ENV: test\n      ADMIN_DATABASE_URL: x\n      FLOW_PORT"),
    ("the backend job runs the role-bound tests again", WORKFLOW, ' -m "not role_bound and not realmodel"', ""),
    ("the cluster check step is dropped", WORKFLOW, "privilege_gate.sh clusters", "privilege_gate.sh prerequisites"),
    ("the gate script ignores command errors", GATE, "set -euo pipefail\n\nHERE=", "set -u\n\nHERE="),
    ("the disposable flag is exported before the cluster proved itself", GATE, '  mkdir -p "$REPORTS"\n  umask 077', '  mkdir -p "$REPORTS"\n  export TEST_CLUSTER_IS_DISPOSABLE=true\n  umask 077'),
    ("skipped tests are accepted", RESULTS, "        if skipped:\n", "        if False:\n"),
    ("a shortfall of tests is accepted", RESULTS, "        if tests < minimum:\n", "        if False:\n"),
    ("problems do not fail the process", RESULTS, "    return 1 if problems else 0\n\n\nif __name__", "    return 0\n\n\nif __name__"),
    ("any PostgreSQL version is accepted", CLUSTER, '    if not facts.version.startswith("PostgreSQL 15."):\n', "    if False:\n"),
    ("a cluster with foreign databases is accepted", CLUSTER, "        if database not in DEFAULT_DATABASES and not scratch:\n", "        if False:\n"),
    ("a cluster with project roles is accepted", CLUSTER, '        if role.startswith("asistente") or (role.startswith("tstrole_") and not scratch):\n', "        if False:\n"),
    ("a remote host is accepted", CLUSTER, "    if facts.host not in allowed_hosts:\n", "    if False:\n"),
    ("the summary stops checking the role-bound suites", GATE, '    "role-bound suites=$REPORTS/role-suites.xml:${MIN_ROLE_SUITES:-400}" \\\n', ""),
    ("the minimum of role-bound tests is lowered to nothing", GATE, "MIN_ROLE_SUITES:-400", "MIN_ROLE_SUITES:-1"),
    ("the role-bound step selects another marker", GATE, "tests/integration -m role_bound", "tests/integration -m least_privilege"),
    ("the roles-mode step loses its option", GATE, "--least-privilege -m least_privilege", "-m least_privilege"),
    ("the second idempotent pass disappears", GATE, '  echo "second pass: bootstrap, migrate and verify are idempotent"\n  bootstrap\n  migrate\n  verify\n', ""),
    ("the drift self-check accepts any failure", GATE, '    *"that the matrix does not grant"*) ;;\n', "    *) ;;\n"),
    ("the role-bound prefixes stop covering the cluster tests", "backend/tests/conftest.py", '    "test_db_",\n', ""),
    ("the revision check accepts a database behind the head", ".github/scripts/alembic_check.py", "or current != head", "or False"),
    ("two names for one server are accepted", CLUSTER, "return (_address(a.hostname), a.port) == (_address(b.hostname), b.port)", "return (a.hostname, a.port) == (b.hostname, b.port)"),
]


def main() -> int:
    repo, scratch = Path(sys.argv[1]), Path(sys.argv[2])
    python = str(repo / "backend/.venv/Scripts/python.exe")
    caught = 0
    for index, (label, rel, old, new) in enumerate(MUTATIONS):
        work = scratch / f"m{index}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for name in ("app", "tests"):
            shutil.copytree(repo / "backend" / name, work / "backend" / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(repo / "backend/pyproject.toml", work / "backend/pyproject.toml")
        shutil.copytree(repo / ".github", work / ".github")
        target = work / rel
        text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
        if text.count(old) != 1:
            print(f"SKIPPED   {label} (pattern found {text.count(old)} times)")
            continue
        target.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        result = subprocess.run(  # noqa: S603 - fixed arguments, test-only
            [python, "-m", "pytest", "tests/unit/test_ci_workflow.py", "tests/unit/test_ci_gate_scripts.py", "-q", "-p", "no:cacheprovider", "-x"],
            cwd=work / "backend", capture_output=True, text=True, check=False,
        )
        failed = [line for line in result.stdout.splitlines() if line.startswith("FAILED")]
        test = failed[0].split("::")[-1].split(" - ")[0] if failed else ""
        status = "CAUGHT   " if result.returncode == 1 and test else "SURVIVED "
        caught += status.startswith("CAUGHT")
        print(f"{status} {label} | {test}")
        shutil.rmtree(work, ignore_errors=True)
    print(f"mutations: {len(MUTATIONS)}, caught: {caught}")
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
