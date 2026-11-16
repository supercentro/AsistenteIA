#!/usr/bin/env bash
# Runs the group 12 tests against a DISPOSABLE PostgreSQL (change database-least-privilege).
#
#   usage: run_group5_tests.sh <output file> [pytest arguments...]
#
# - PostgreSQL 15 + pgvector 0.8.7 (pgvector/pgvector:0.8.7-pg15), throwaway superuser and random
#   password, tmpfs data, 1 CPU / 1 GB, on an internal Docker network: NO published port, no route to
#   the real databases (which live in another Compose network).
# - The runner is the Python 3.12 backend image of main with a COPY of app/, alembic/, tests/ and the
#   project files: no .env file, no .venv, no repository mount. pytest and httpx are installed from
#   PyPI into a scratch directory in a first step (default network); the tests then run on the
#   internal network.
# - Refuses to start with less than 6 GB of free memory (owner condition).
# - Everything it creates carries the label purpose=g12-linux-tests and is removed on exit.
set -u
OUT="$1"; shift
HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$(cd "$HERE/../../../../../backend" && pwd)"
export MSYS_NO_PATHCONV=1

FREE_GB=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
if ! awk "BEGIN{exit !($FREE_GB >= 6.0)}"; then
  echo "free memory $FREE_GB GB is below 6 GB: not starting any container" | tee "$OUT"; exit 3
fi

RUN="$(mktemp -d)"
NET="g12net$$"; PG="g12pg$$"; LABEL="purpose=g12-linux-tests"
IMAGE_PG="pgvector/pgvector:0.8.7-pg15"
IMAGE_RUN="${G5_RUNNER_IMAGE:-asistenteia-backend:main-f455234}"
PW="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
cleanup() {
  docker rm -f "$PG" >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
  rm -rf "$RUN"
}
trap cleanup EXIT

{
echo "# group 12 test run $(date -u +%FT%TZ) | free RAM before: $FREE_GB GB"
echo "# postgres image: $IMAGE_PG | runner image: $IMAGE_RUN | pytest args: $*"

# 1. a clean copy of the code (no environment file, no virtual environment, no caches)
python - "$(cygpath -m "$BACKEND")" "$(cygpath -m "$RUN")/repo" <<'PY'
import pathlib, shutil, sys

# The repository layout the tests expect (REPO/backend, REPO/docker-compose.yml, ...), with no real
# environment file: only the `.example` ones are copied, never `.env`, `.env.db`, `.env.worker`...
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])


def ignore(_directory, names):
    skipped = [n for n in names if n.startswith(".env") and not n.endswith(".example")]
    skipped += [n for n in names if n in {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}]
    return skipped + [n for n in names if n.endswith(".pyc")]


shutil.copytree(src, dst / "backend", ignore=ignore)
root = src.parent
for name in ("docker-compose.yml", ".gitignore"):
    if (root / name).is_file():
        shutil.copy(root / name, dst / name)
for folder in (".github", "docs"):
    if (root / folder).is_dir():
        shutil.copytree(root / folder, dst / folder, ignore=ignore)
policy = root / "frontend/src/lib/privacyPolicy.ts"  # a unit test compares it with the backend constant
if policy.is_file():
    (dst / "frontend/src/lib").mkdir(parents=True)
    shutil.copy(policy, dst / "frontend/src/lib/privacyPolicy.ts")
PY
echo "# env files in the copy: $(find "$RUN/repo" -name '.env*' ! -name '*.example' | wc -l)"

# 2. test tools into a scratch directory (default network, pinned from uv.lock)
PYTEST_V=$(grep -A1 '^name = "pytest"$' "$BACKEND/uv.lock" | grep version | head -1 | cut -d'"' -f2)
HTTPX_V=$(grep -A1 '^name = "httpx"$' "$BACKEND/uv.lock" | grep version | head -1 | cut -d'"' -f2)
YAML_V=$(grep -A1 '^name = "pyyaml"$' "$BACKEND/uv.lock" | grep version | head -1 | cut -d'"' -f2)
mkdir -p "$RUN/libs"
docker run --rm --label "$LABEL" -m 512m -v "$(cygpath -m "$RUN/libs"):/libs" --entrypoint pip "$IMAGE_RUN" \
  install -q --no-cache-dir --target /libs "pytest==$PYTEST_V" "httpx==$HTTPX_V" "pyyaml==$YAML_V" 2>&1 | tail -2
echo "# pytest $PYTEST_V, httpx $HTTPX_V"

# 3. the disposable cluster on an internal network
docker network create --internal --label "$LABEL" "$NET" >/dev/null
docker run -d --name "$PG" --label "$LABEL" --network "$NET" --network-alias pgdb \
  --cpus 1 -m 1g --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=tstadmin -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres "$IMAGE_PG" >/dev/null
for _ in $(seq 1 40); do
  docker exec "$PG" pg_isready -h 127.0.0.1 -U tstadmin -d postgres >/dev/null 2>&1 && break; sleep 1
done
echo "# $(docker exec "$PG" psql -U tstadmin -d postgres -Atc 'select version()' | cut -c1-60)"
echo "# pgvector $(docker exec "$PG" psql -U tstadmin -d postgres -Atc "select default_version from pg_available_extensions where name='vector'")"
echo "# published ports: $(docker port "$PG" | wc -l)"

# the database the pre-existing integration tests expect (CI creates its own); the group 5 fixtures drop it
docker exec "$PG" psql -U tstadmin -d postgres -c "CREATE DATABASE tstdb_guard_test" >/dev/null
# 4. the tests, inside the internal network
URL="postgresql+psycopg://tstadmin:$PW@pgdb:5432"
docker run --rm --label "$LABEL" --network "$NET" -m "${G5_RUNNER_MEM:-768m}" --cpus 1 \
  -v "$(cygpath -m "$RUN/repo"):/repo:ro" -v "$(cygpath -m "$RUN/libs"):/libs:ro" -w /repo/backend \
  -e PYTHONPATH=/libs:/repo/backend -e PYTHONDONTWRITEBYTECODE=1 -e APP_ENV=test \
  -e "DATABASE_URL=postgresql+psycopg://notused:notused@pgdb:5432/notused_app" \
  -e "TEST_DATABASE_URL=$URL/tstdb_guard_test" -e "TEST_ADMIN_DATABASE_URL=$URL/postgres" \
  -e TEST_CLUSTER_IS_DISPOSABLE=true --entrypoint python "$IMAGE_RUN" \
  -m pytest -p no:cacheprovider -q "$@" 2>&1 | sed "s/$PW/<password>/g"
RC=${PIPESTATUS[0]}
echo "# pytest exit code: $RC"
echo "# containers left by this run: $(docker ps -aq --filter "label=$LABEL" | wc -l) (the PostgreSQL one is removed on exit)"
} 2>&1 | tee "$OUT"
