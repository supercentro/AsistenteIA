#!/usr/bin/env bash
# Runs the CI privilege gate (.github/scripts/privilege_gate.sh) locally against two DISPOSABLE
# clusters, the way GitHub Actions runs a job: one process per step, the first failing step stops
# the job, only the summary step (`if: always()`) runs after a failure. Change
# database-least-privilege, task 10.1/10.2/10.3; GitHub itself is not available locally.
#
#   usage: run_gate_local.sh <output file> <scenario>
#
# scenarios (the gate must pass in `happy` and fail in every other one, naming the cause):
#   happy                 the code as committed
#   missing-prerequisite  the administrator password is not provided
#   foreign-database      the `tests` cluster already holds a database named asistenteia
#   same-server           both "clusters" are the same server
#   failing-test          the application role loses a privilege the code needs (a test must fail)
#   new-table             a table is added to the model without a matrix decision
#   skipped-test          a role-bound test is skipped instead of run
#   too-few-tests         the role-bound suites run a handful of tests only
#   drift-blind           db-verify is made blind to a privilege outside the matrix
#
# Two PostgreSQL 15 + pgvector 0.8.7 containers (throwaway administrator and passwords, tmpfs data,
# 1 CPU / 1 GB), an internal Docker network with NO published port, a runner container with a COPY of
# the code (no environment file, no virtual environment, no repository mount of the working tree),
# memory gate of 6 GB, everything labelled and removed on exit.
set -u
OUT="$1"; SCENARIO="$2"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../../.." && pwd)"
BACKEND="$ROOT/backend"
export MSYS_NO_PATHCONV=1

FREE_GB=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
if ! awk "BEGIN{exit !($FREE_GB >= 6.0)}"; then
  echo "free memory $FREE_GB GB is below 6 GB: not starting any container" | tee "$OUT"; exit 3
fi

RUN="$(mktemp -d)"
NET="g10net$$"; FLOW="g10flow$$"; TESTS="g10tests$$"; LABEL="purpose=g10-ci-gate"
IMAGE_PG="pgvector/pgvector:0.8.7-pg15"
IMAGE_RUN="${G10_RUNNER_IMAGE:-asistenteia-worker:main-f455234}"
PW="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
W() { cygpath -m "$1"; }
cleanup() {
  docker rm -f "$FLOW" "$TESTS" >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
  rm -rf "$RUN"
}
trap cleanup EXIT

{
echo "# CI gate local run $(date -u +%FT%TZ) | scenario: $SCENARIO | free RAM before: $FREE_GB GB"
echo "# postgres image: $IMAGE_PG | runner image: $IMAGE_RUN"

# 1. a clean copy of the repository layout the tests and the gate expect
python - "$(W "$ROOT")" "$(W "$RUN")/repo" <<'PY'
import pathlib, shutil, sys

root, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])


def ignore(_directory, names):
    skipped = [n for n in names if n.startswith(".env") and not n.endswith(".example")]
    skipped += [n for n in names if n in {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}]
    return skipped + [n for n in names if n.endswith(".pyc")]


shutil.copytree(root / "backend", dst / "backend", ignore=ignore)
shutil.copytree(root / ".github", dst / ".github")
for name in ("docker-compose.yml", ".gitignore"):
    if (root / name).is_file():
        shutil.copy(root / name, dst / name)
shutil.copytree(root / "docs", dst / "docs", ignore=ignore) if (root / "docs").is_dir() else None
PY
echo "# env files in the copy: $(find "$RUN/repo" -name '.env*' ! -name '*.example' | wc -l)"

# 2. the scenario's change, applied to the COPY only
python - "$(W "$RUN")/repo" "$SCENARIO" <<'PY'
import pathlib, re, sys

repo, scenario = pathlib.Path(sys.argv[1]), sys.argv[2]


def edit(rel, old, new, count=1):
    path = repo / rel
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.count(old) == count, (rel, old[:50], text.count(old))
    path.write_text(text.replace(old, new), encoding="utf-8")


if scenario == "failing-test":
    edit("backend/app/db_privileges.py", 'insert=_cols("name", "description", "teacher_id"),', 'insert=_cols("name", "description"),')
elif scenario == "new-table":
    edit(
        "backend/app/models/subject.py",
        "class Enrollment(Base):",
        'class Undecided(Base):\n    """A table nobody decided about."""\n\n    __tablename__ = "undecided_things"\n\n'
        "    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)\n\n\nclass Enrollment(Base):",
    )
    # a realistic pull request adds the migration too, so alembic check passes and only the
    # missing matrix decision can stop the job
    (repo / "backend/alembic/versions/0007_undecided_things.py").write_text(
        '"""A table without a privilege decision (scenario)."""\n\n'
        "import sqlalchemy as sa\nfrom alembic import op\nfrom sqlalchemy.dialects import postgresql\n\n"
        'revision = "0007"\ndown_revision = "0006"\nbranch_labels = None\ndepends_on = None\n\n\n'
        "def upgrade() -> None:\n"
        '    op.create_table("undecided_things", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False))\n\n\n'
        "def downgrade() -> None:\n"
        '    op.drop_table("undecided_things")\n',
        encoding="utf-8",
    )
elif scenario == "skipped-test":
    edit(
        "backend/tests/integration/test_db_roles_effective.py",
        "def test_nothing_is_granted_to_public_and_no_runtime_role_owns_an_object(",
        "import pytest\n\n\n@pytest.mark.skip(reason='scenario: a skipped privilege test')\ndef test_nothing_is_granted_to_public_and_no_runtime_role_owns_an_object(",
    )
elif scenario == "too-few-tests":
    (repo / "backend/tests/integration/test_db_roles_denied.py").unlink()
elif scenario == "drift-blind":
    text = (repo / "backend/app/db_admin/verify.py").read_text(encoding="utf-8")
    assert "def verify(" in text
    (repo / "backend/app/db_admin/verify.py").write_text(
        text + "\n\n_real_verify = verify\n\n\ndef verify(*args, **kwargs):  # scenario: blind verifier\n    return []\n",
        encoding="utf-8",
    )
PY

# 3. test tools into a scratch directory (pinned from uv.lock)
v() { grep -A1 "^name = \"$1\"\$" "$BACKEND/uv.lock" | grep version | head -1 | cut -d'"' -f2; }
mkdir -p "$RUN/libs"
docker run --rm --label "$LABEL" -m 512m -v "$(W "$RUN/libs"):/libs" --entrypoint pip "$IMAGE_RUN" \
  install -q --no-cache-dir --target /libs "pytest==$(v pytest)" "httpx==$(v httpx)" "pyyaml==$(v pyyaml)" 2>&1 | tail -2
echo "# pytest $(v pytest), httpx $(v httpx), pyyaml $(v pyyaml)"

# 4. the two disposable clusters on an internal network
docker network create --internal --label "$LABEL" "$NET" >/dev/null
for pair in "$FLOW:pgflow" "$TESTS:pgtests"; do
  name="${pair%%:*}"; alias="${pair##*:}"
  docker run -d --name "$name" --label "$LABEL" --network "$NET" --network-alias "$alias" \
    --cpus 1 -m 1g --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=ci_admin -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres "$IMAGE_PG" >/dev/null
done
for name in "$FLOW" "$TESTS"; do
  for _ in $(seq 1 40); do
    docker exec "$name" pg_isready -h 127.0.0.1 -U ci_admin -d postgres >/dev/null 2>&1 && break; sleep 1
  done
  echo "# $name: $(docker exec "$name" psql -U ci_admin -d postgres -Atc 'select version()' | cut -c1-40) | published ports: $(docker port "$name" | wc -l)"
done

if [ "$SCENARIO" = "foreign-database" ]; then
  docker exec "$TESTS" psql -U ci_admin -d postgres -c "CREATE DATABASE asistenteia" >/dev/null
fi

# 5. the job, step by step, with the semantics of GitHub Actions
cat > "$RUN/job.sh" <<'JOB'
#!/usr/bin/env bash
failed=""
for step in prerequisites clusters flow drift-selfcheck privilege-unit role-suites roles-mode summary; do
  if [ -n "$failed" ] && [ "$step" != "summary" ]; then echo "::group::$step (skipped: an earlier step failed)"; echo "::endgroup::"; continue; fi
  echo "::group::$step"
  bash /repo/.github/scripts/privilege_gate.sh "$step"; rc=$?
  echo "::endgroup::"
  echo "STEP $step exit code $rc"
  if [ $rc -ne 0 ] && [ -z "$failed" ]; then failed="$step"; fi
done
if [ -n "$failed" ]; then echo "JOB RESULT: failed at step $failed"; exit 1; fi
echo "JOB RESULT: passed"
JOB
ENVS=(-e PYTHONPATH=/libs:/repo/backend -e PYTHONDONTWRITEBYTECODE=1 -e APP_ENV=test -e PYRUN=python
  -e PG_ADMIN_USER=ci_admin -e FLOW_HOST=pgflow -e TESTS_HOST=pgtests -e FLOW_PORT=5432 -e TESTS_PORT=5432
  -e CI_ALLOWED_HOSTS=pgflow,pgtests -e RUNNER_TEMP=/tmp -e MIN_UNIT=60 -e MIN_ROLE_SUITES=400 -e MIN_ROLES_MODE=480)
if [ "$SCENARIO" = "same-server" ]; then ENVS+=(-e TESTS_HOST=pgflow); fi
if [ "$SCENARIO" != "missing-prerequisite" ]; then ENVS+=(-e "PG_ADMIN_PASSWORD=$PW"); fi
if [ "$SCENARIO" = "too-few-tests" ]; then ENVS+=(-e MIN_ROLE_SUITES=400); fi
docker run --rm --label "$LABEL" --network "$NET" -m "${G10_RUNNER_MEM:-1536m}" --cpus 2 \
  -v "$(W "$RUN/repo"):/repo:ro" -v "$(W "$RUN/libs"):/libs:ro" -v "$(W "$RUN/job.sh"):/job.sh:ro" -w /repo/backend \
  "${ENVS[@]}" --entrypoint bash "$IMAGE_RUN" /job.sh 2>&1 | sed "s/$PW/<password>/g"
RC=${PIPESTATUS[0]}
echo "# job exit code: $RC"
echo "# containers left by this run: $(docker ps -aq --filter "label=$LABEL" | wc -l) (the clusters are removed on exit)"
} 2>&1 | tee "$OUT"
