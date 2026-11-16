#!/usr/bin/env bash
# Mutation checks of the task 15.2 controls against a DISPOSABLE PostgreSQL (task 4.6).
#   usage: run_group5_mutations.sh <output file> [first index] [last index]
# Same isolation as run_group5_tests.sh. Each mutation edits a COPY of the code in a scratch
# directory (the repository is never modified), runs the tests that must notice it, and records
# whether they failed (caught) or passed (survived). Each target set is first run on the unedited
# copy to prove that it passes.
set -u
OUT="$1"; FIRST="${2:-0}"; LAST="${3:-999}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$(cd "$HERE/../../../../../backend" && pwd)"
export MSYS_NO_PATHCONV=1

FREE_GB=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
if ! awk "BEGIN{exit !($FREE_GB >= 6.0)}"; then
  echo "free memory $FREE_GB GB is below 6 GB: not starting any container" | tee "$OUT"; exit 3
fi

RUN="$(mktemp -d)"
NET="g15mnet$$"; PG="g15mpg$$"; LABEL="purpose=g15-mutations"
IMAGE_PG="pgvector/pgvector:0.8.7-pg15"
IMAGE_RUN="${G5_RUNNER_IMAGE:-asistenteia-backend:main-f455234}"
PW="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
cleanup() { docker rm -f "$PG" >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; rm -rf "$RUN"; }
trap cleanup EXIT
W() { cygpath -m "$1"; }

copy_code() {  # $1 = destination
  python - "$(W "$BACKEND")" "$(W "$1")" <<'PY'
import shutil, sys
ignore = shutil.ignore_patterns(".env*", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "*.pyc")
shutil.copytree(sys.argv[1], sys.argv[2], ignore=ignore)
PY
}

URL="postgresql+psycopg://tstadmin:$PW@pgdb:5432"
start_pg() {  # a brand-new cluster: state left by an earlier run must not mask a mutation
  docker rm -f "$PG" >/dev/null 2>&1
  docker run -d --name "$PG" --label "$LABEL" --network "$NET" --network-alias pgdb \
    --cpus 1 -m 1g --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=tstadmin -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres "$IMAGE_PG" >/dev/null
  for _ in $(seq 1 40); do docker exec "$PG" pg_isready -h 127.0.0.1 -U tstadmin -d postgres >/dev/null 2>&1 && break; sleep 1; done
  docker exec "$PG" psql -U tstadmin -d postgres -c "CREATE DATABASE tstdb_guard_test" >/dev/null  # the guard of tests/db_support.py
}
run_tests() {  # $1 = code dir, rest = pytest targets
  local dir="$1"; shift
  start_pg
  docker run --rm --label "$LABEL" --network "$NET" -m "${G5_RUNNER_MEM:-768m}" --cpus 1 \
    -v "$(W "$dir"):/work:ro" -v "$(W "$RUN/libs"):/libs:ro" -w /work \
    -e PYTHONPATH=/libs:/work -e PYTHONDONTWRITEBYTECODE=1 -e APP_ENV=test \
    -e "DATABASE_URL=postgresql+psycopg://notused:notused@pgdb:5432/notused_app" \
    -e "TEST_DATABASE_URL=$URL/tstdb_guard_test" -e "TEST_ADMIN_DATABASE_URL=$URL/postgres" \
    -e TEST_CLUSTER_IS_DISPOSABLE=true --entrypoint python "$IMAGE_RUN" \
    -m pytest -p no:cacheprovider -q -x "$@" 2>&1 | sed "s/$PW/<password>/g"
  return "${PIPESTATUS[0]}"
}

{
echo "# group 15.2 mutation run $(date -u +%FT%TZ) | free RAM before: $FREE_GB GB | images: $IMAGE_PG, $IMAGE_RUN"
copy_code "$RUN/pristine"
echo "# env files in the copy: $(find "$RUN/pristine" -name '.env*' ! -name '*.example' | wc -l)"
python "$(cygpath -m "$HERE")/mutations.py" check "$(W "$RUN/pristine")" || exit 4

PYTEST_V=$(grep -A1 '^name = "pytest"$' "$BACKEND/uv.lock" | grep version | head -1 | cut -d'"' -f2)
HTTPX_V=$(grep -A1 '^name = "httpx"$' "$BACKEND/uv.lock" | grep version | head -1 | cut -d'"' -f2)
mkdir -p "$RUN/libs"
docker run --rm --label "$LABEL" -m 512m -v "$(W "$RUN/libs"):/libs" --entrypoint pip "$IMAGE_RUN" \
  install -q --no-cache-dir --target /libs "pytest==$PYTEST_V" "httpx==$HTTPX_V" 2>&1 | grep -v notice

docker network create --internal --label "$LABEL" "$NET" >/dev/null
start_pg
echo "# $(docker exec "$PG" psql -U tstadmin -d postgres -Atc 'select version()' | cut -c1-60) | published ports: $(docker port "$PG" | wc -l)"

caught=0; survived=0; baseline_bad=0
python "$(cygpath -m "$HERE")/mutations.py" list | while IFS=$'\t' read -r index label; do
  [ "$index" -lt "$FIRST" ] && continue; [ "$index" -gt "$LAST" ] && continue
  rm -rf "$RUN/work"; copy_code "$RUN/work"
  targets=$(python "$(cygpath -m "$HERE")/mutations.py" apply "$index" "$(W "$RUN/work")")
  # shellcheck disable=SC2086
  run_tests "$RUN/pristine" $targets >/dev/null 2>&1; base=$?
  # shellcheck disable=SC2086
  run_tests "$RUN/work" $targets > "$RUN/mutant.out" 2>&1; mut=$?
  first_fail=$(grep -m1 -E "^FAILED |^ERROR tests/" "$RUN/mutant.out" | cut -c1-110)
  pattern=$(echo "$targets" | sed 's/::[^ ]*//g; s/ /|/g')
  if [ $base -ne 0 ]; then verdict="BASELINE-FAILS (invalid check)"
  elif [ $mut -eq 1 ] && echo "$first_fail" | grep -qE "$pattern"; then verdict="CAUGHT"
  elif [ $mut -ne 0 ]; then verdict="FAILED-ELSEWHERE (check manually: rc=$mut)"
  else verdict="SURVIVED"; fi
  echo "[$index] $verdict | $label | baseline rc=$base mutant rc=$mut | ${first_fail:-no failing test}"
  if [ -n "${SHOW_CAUSE:-}" ]; then grep -E "^E  |^>  |assert " "$RUN/mutant.out" | head -12 | cut -c1-200 | sed "s/^/      cause: /"; fi
done
echo "# repository files modified by this run: 0 (mutations are applied to copies in a scratch directory)"
} 2>&1 | tee "$OUT"
