#!/usr/bin/env bash
# Full backend suite on Linux against DISPOSABLE PostgreSQL only (own orchestration, not the
# archived run_gate_local.sh). Phase 1 mirrors the CI `backend` job; phase 2 mirrors the gate steps
# `role-suites` and `roles-mode` on a separate cluster. Internal network, no published port, tmpfs.
set -u
IMG="chat-linux-tests:round4"
PG_IMG="pgvector/pgvector:0.8.7-pg15"
LABEL="purpose=chat-round4-suite"
NET="chatr4net$$"
PW="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
JWT="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export MSYS_NO_PATHCONV=1
mask() { sed "s/$PW/<password>/g; s/$JWT/<jwt>/g"; }
cleanup() { docker rm -f "pga$$" "pgb$$" >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; }
trap cleanup EXIT

echo "# $(date -u +%FT%TZ) free RAM before: $(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r') GB"
docker network create --internal --label "$LABEL" "$NET" >/dev/null

# ---------------------------------------------------------------- phase 1: the CI backend job
docker run -d --name "pga$$" --label "$LABEL" --network "$NET" --network-alias pga --cpus 1 -m 1g \
  --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=ci -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=asistenteia "$PG_IMG" >/dev/null
echo "# cluster A published ports: $(docker port "pga$$" | wc -l)"
cat > /tmp/phase1.sh <<'EOS'
set -u
python - <<'PY'
import os, time, psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
for _ in range(60):
    try:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute("CREATE DATABASE asistenteia_test")
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("cluster A did not come up")
PY
rc_all=0
run() { name="$1"; shift; echo "::group::$name"; "$@"; rc=$?; echo "::endgroup::"; echo "STEP $name exit code $rc"; [ $rc -ne 0 ] && rc_all=1; }
run ruff-check ruff check .
run ruff-format ruff format --check .
run mypy mypy --strict app tests
run unit-tests pytest tests/unit -p no:cacheprovider -q -rs --tb=short
run integration-tests pytest tests/integration -m "not role_bound and not realmodel" -p no:cacheprovider -q -rs --tb=short --cov=app --cov-report=term
echo "PHASE1 RESULT: $rc_all"
EOS
docker run --rm --label "$LABEL" --network "$NET" -m 1500m --cpus 2 \
  -e APP_ENV=test -e "JWT_SECRET=$JWT" \
  -e "DATABASE_URL=postgresql+psycopg://ci:$PW@pga:5432/asistenteia" \
  -e "TEST_DATABASE_URL=postgresql+psycopg://ci:$PW@pga:5432/asistenteia_test" \
  -v "$(cygpath -m /tmp/phase1.sh):/phase1.sh:ro" -w /repo/backend "$IMG" bash /phase1.sh 2>&1 | mask
docker rm -f "pga$$" >/dev/null 2>&1

# ------------------------------------------------ phase 2: role-bound suites and roles mode
docker run -d --name "pgb$$" --label "$LABEL" --network "$NET" --network-alias pgb --cpus 1 -m 1g \
  --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=ci_admin -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres "$PG_IMG" >/dev/null
echo "# cluster B published ports: $(docker port "pgb$$" | wc -l)"
cat > /tmp/phase2.sh <<'EOS'
set -u
export TESTS_ADMIN_URL="$TEST_ADMIN_DATABASE_URL"
python - <<'PY'
import os, time, psycopg
url = os.environ["TEST_ADMIN_DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
for _ in range(60):
    try:
        psycopg.connect(url, autocommit=True).close()
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("cluster B did not come up")
PY
rc_all=0
run() { name="$1"; shift; echo "::group::$name"; "$@"; rc=$?; echo "::endgroup::"; echo "STEP $name exit code $rc"; [ $rc -ne 0 ] && rc_all=1; }
run cluster-is-disposable python /repo/.github/scripts/assert_disposable_cluster.py check tests TESTS_ADMIN_URL
run role-suites pytest tests/integration -m role_bound -p no:cacheprovider -q -rs --tb=short
python - <<'PY'
import os, psycopg
admin = os.environ["TEST_ADMIN_DATABASE_URL"].replace("postgresql+psycopg", "postgresql")
with psycopg.connect(admin, autocommit=True) as conn:
    if conn.execute("SELECT 1 FROM pg_database WHERE datname = 'tstdb_ci_test'").fetchone() is None:
        conn.execute('CREATE DATABASE "tstdb_ci_test"')
PY
run roles-mode pytest tests/integration --least-privilege -m least_privilege -p no:cacheprovider -q -rs --tb=short
echo "PHASE2 RESULT: $rc_all"
EOS
docker run --rm --label "$LABEL" --network "$NET" -m 1500m --cpus 2 \
  -e APP_ENV=test -e "JWT_SECRET=$JWT" -e CI_ALLOWED_HOSTS=pgb -e TEST_CLUSTER_IS_DISPOSABLE=true \
  -e "DATABASE_URL=postgresql+psycopg://asistente_unused:unused@pgb:5432/asistenteia" \
  -e "TEST_DATABASE_URL=postgresql+psycopg://ci_admin:$PW@pgb:5432/tstdb_ci_test" \
  -e "TEST_ADMIN_DATABASE_URL=postgresql+psycopg://ci_admin:$PW@pgb:5432/postgres" \
  -v "$(cygpath -m /tmp/phase2.sh):/phase2.sh:ro" -w /repo/backend "$IMG" bash /phase2.sh 2>&1 | mask
echo "# containers left before cleanup: $(docker ps -aq --filter "label=$LABEL" | wc -l)"
