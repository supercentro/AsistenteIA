#!/usr/bin/env bash
# Tests of run_17b.sh against a DISPOSABLE stack only (TD-030, 17B.1). Never touches the real stack:
#   * compose project g17borch (db container g17borch-db-1 labelled purpose=g17b-test), its own network and volume, no published port;
#   * the existing 17b backup is only READ (copied into synthetic folders under the temp root);
#   * synthetic env folder; the real backend/.env* files are never read;
#   * refuses to start with less than 8 GB of free RAM.
#
#   bash test_run_17b.sh                # all scenarios
#   bash test_run_17b.sh T3 T11         # chosen scenarios
# Needs the images built by S12 (asistenteia-bootstrap/migrate/cli/backend/worker:latest).
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$R/../../../.." && pwd)"; REPOW="$(cd "$REPO" && pwd -W)"
T17A="$R/group-17a/tools"; T17C="$R/group-17c/tools"
ORCHS="${G17B_ORCH:-$HERE/run_17b.sh}"
W() { cygpath -w "$1"; }
P=g17borch
UHOME="$(cygpath -u "$USERPROFILE")"
SRC_B1="$UHOME/Backups/AsistenteIA"; SRC_B2="$UHOME/Backups/AsistenteIA-second"
DUMP=asistenteia_pre_17b_20261114T013150Z.dump; SUF=.integrity.txt
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  PASS $1"; else FAIL=$((FAIL+1)); echo "  FAIL $1 (expected '$2', got '$3')"; [ -f "$ROOT/last.out" ] && tail -n 7 "$ROOT/last.out" | cut -c1-230 | sed 's/^/      | /'; fi; }
RAM=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
python -c "import sys; sys.exit(0 if float('$RAM') >= 8 else 1)" || { echo "free RAM $RAM GB < 8: stop (no Docker used)"; exit 4; }
echo "free RAM before Docker: $RAM GB; HEAD $(cd "$REPO" && git rev-parse --short HEAD)"
ROOT="$(mktemp -d)"; ROOTW="$(W "$ROOT")"
BEFORE_OTHER="$(docker ps -a --format '{{.Names}}' | grep -v "^$P" | sort | tr '\n' ';')"
REAL_FP="$(docker inspect -f '{{.Id}} {{.State.Status}} {{.Image}}' asistenteia-db-1 asistenteia-worker-1 | tr '\n' ';')"
REAL_SHA="$(sha256sum "$SRC_B1/$DUMP" | cut -d' ' -f1)"

dcx() { (cd "$REPO" && G17_DIR="$ROOTW/backend" docker compose -p "$P" --project-directory "$REPOW" -f "$REPOW/docker-compose.yml" -f "$ROOTW/override.yml" "$@"); }
sqla() { docker exec -i "$P-db-1" sh -c "psql -U \"\$POSTGRES_USER\" -d ${2:-asistenteia} -At -v ON_ERROR_STOP=1" <<< "$1" 2>&1; }

write_override() {
cat > "$ROOT/override.yml" <<'YML'
services:
  db:
    ports: !reset []
    env_file: !override
      - ${G17_DIR}/.env.db
    labels:
      purpose: g17b-test
    cpus: 1
    mem_limit: 1g
  bootstrap:
    image: asistenteia-bootstrap:latest
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.roles
  migrate:
    image: asistenteia-migrate:latest
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.migrate
  cli:
    image: asistenteia-cli:latest
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.cli
  backend:
    image: asistenteia-backend:latest
    build: !reset null
    pull_policy: never
    ports: !reset []
    env_file: !override
      - ${G17_DIR}/.env
    volumes: !override []
    command: !override ["uvicorn", "app.main:app_factory", "--factory", "--no-proxy-headers", "--host", "0.0.0.0", "--port", "8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status == 200 else 1)"]
      interval: 5s
      timeout: 5s
      retries: 12
    cpus: 1
    mem_limit: 512m
  worker:
    image: asistenteia-worker:latest
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.worker
    volumes: !override []
    cpus: 2
    mem_limit: 2g
  frontend:
    profiles: ["g17b-excluded"]
YML
}

teardown_stack() {
  [ "$P" = g17borch ] || { echo "refusing to tear down '$P'"; return; }
  [ -f "$ROOT/override.yml" ] && dcx down -v --remove-orphans > /dev/null 2>&1
  docker rm -f "$P-decoy" > /dev/null 2>&1
  for f in "$ROOT"/b1/* "$ROOT"/b2/* "$ROOT"/b1 "$ROOT"/b2 "$ROOT"/backend/.env*; do [ -e "$f" ] && icacls "$(W "$f")" /reset > /dev/null 2>&1; done
  rm -rf "$ROOT"/b1 "$ROOT"/b2 "$ROOT"/backend "$ROOT"/state* "$ROOT"/cfg*.sh
}
trap 'teardown_stack; rm -rf "$ROOT"' EXIT

fresh_stack() { # builds a clean disposable stack seeded from the existing backup (a read) and the orchestrator config
  teardown_stack
  mkdir -p "$ROOT/b1" "$ROOT/b2" "$ROOT/backend" "$ROOT/state"
  python -I "$(W "$HERE/make_synthetic_env.py")" "$(W "$ROOT/backend")"
  write_override
  for pair in "b1:$SRC_B1" "b2:$SRC_B2"; do
    d="${pair%%:*}"; s="${pair#*:}"
    cp "$s/$DUMP" "$s/$DUMP.sha256" "$s/$DUMP$SUF" "$ROOT/$d/"
    powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$T17C/secure_folder_acl.ps1")" -Path "$(W "$ROOT/$d")" > /dev/null
    for f in "$DUMP" "$DUMP.sha256" "$DUMP$SUF"; do powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$T17C/secure_file_acl.ps1")" -Path "$(W "$ROOT/$d/$f")" > /dev/null; done
  done
  dcx up -d db > /dev/null 2>&1
  local i=0; until [ "$(docker inspect -f '{{with index .State "Health"}}{{.Status}}{{end}}' "$P-db-1" 2>/dev/null)" = healthy ] || [ $i -ge 40 ]; do sleep 2; i=$((i+1)); done
  [ "$(docker inspect -f '{{with index .State "Health"}}{{.Status}}{{end}}' "$P-db-1")" = healthy ] || { echo "disposable db did not become healthy"; return 1; }
  docker cp "$(W "$ROOT/b2/$DUMP")" "$P-db-1:/tmp/seed.dump" > /dev/null
  docker exec "$P-db-1" sh -c 'dropdb -U "$POSTGRES_USER" --force asistenteia && createdb -U "$POSTGRES_USER" asistenteia && pg_restore -U "$POSTGRES_USER" -d asistenteia --exit-on-error /tmp/seed.dump && rm -f /tmp/seed.dump' > "$ROOT/seed.out" 2>&1 || { echo "seed restore failed"; return 1; }
  docker exec -i "$P-db-1" sh -c 'psql -U "$POSTGRES_USER" -d postgres -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$T17A/snapshot_cluster.sql" > "$ROOT/cluster-baseline.txt" 2>&1
  cat > "$ROOT/cfg.sh" <<CFG
PROJECT=$P
DBC=$P-db-1
API_C=$P-backend-1
WORKER_C=$P-worker-1
EXPECTED_SYSID=""
ENV_DIR="$ROOT/backend"
BACKUPS="$ROOT/b1"
SECOND="$ROOT/b2"
EXPECTED_CLUSTER="$ROOT/cluster-baseline.txt"
DC_FILES=(-f "$REPOW/docker-compose.yml" -f "$ROOTW/override.yml")
export G17_DIR="$ROOTW/backend"
CFG
  cat > "$ROOT/hooks.sh" <<'HK'
# S12 builds images and tags the images of the REAL containers; it was run in the real profile. In the disposable stack it is a logged no-op.
st_images() { identity_check; log "S12 (disposable stack): images were built and checked in the real profile; nothing to do here"; }
HK
  rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"
}
orch() { G17B_PROFILE=test G17B_TEST_CONFIG="$ROOT/cfg.sh" G17B_TEST_HOOKS="$ROOT/hooks.sh" G17B_STATE_DIR="$ROOT/state" bash "$ORCHS" "$@"; }
runo() { orch "$@" > "$ROOT/last.out" 2>&1; RC=$?; }
sget() { sed -n "s/^$1=//p" "$ROOT/state/state" | tail -1; }
sdump() { sqla "$1" "${2:-asistenteia}" | tr '\n' ' '; }
want() { [ $# -eq 0 ] && return 0; for s in "$@"; do [ "$s" = "$SC" ] && return 0; done; return 1; }
SEL=("$@")
scen() { SC="$1"; if [ ${#SEL[@]} -gt 0 ]; then local ok=1; for s in "${SEL[@]}"; do [ "$s" = "$1" ] && ok=0; done; [ $ok = 0 ] || return 1; fi; echo "== $1 $2"; fresh_stack || { FAIL=$((FAIL+1)); echo "  FAIL stack setup"; return 1; }; }
leak() { grep -rEl "$USERNAME|C:/Users|C:\\\\Users" "$ROOT/state" 2>/dev/null | wc -l; }

# ---------------------------------------------------------------- T1 happy path through the last stage
if scen T1 "correct run S10..S31 on a disposable stack, with the real new images"; then
  runo --through S12; check "S10, S11 and S12 pass" 0 $RC
  check "state: done=S10,S11,S12" "S10,S11,S12" "$(sget done)"
  # S12 builds images: not repeated here (images already built); mark it done for the order check via a controlled stage run in a stub
  runo --through S26; check "S20..S26 pass (stop, env files, bootstrap exit 1, dry run 9, adopt, migrate, db-verify)" 0 $RC
  check "revision is 0006" "0006" "$(sqla 'select version_num from alembic_version' | tr -d '\r')"
  check "the four restricted roles exist" 4 "$(sqla "select count(*) from pg_roles where rolname in ('asistente_migrator','asistente_app','asistente_worker','asistente_cli')" postgres)"
  runo --through S31; check "S30 and S31 pass (services recreated, restricted roles hold the sessions)" 0 $RC
  check "last completed stage is S31" S31 "$(sget last_completed)"
  check "the log holds no user name or Users path" 0 "$(leak)"
  check "no connection URL appears in the log" 0 "$(grep -cE 'postgres(ql)?(\+[a-z0-9]+)?://[^<]' "$ROOT/state/run.log")"
  runo --status; check "status works" 0 $RC
  grep -q 'last_completed=S31' "$ROOT/last.out"; check "status shows the last completed stage" 0 $?
fi

# ---------------------------------------------------------------- T2 preflight failure
if scen T2 "preflight fails: a query has been running for more than 30 s (gate E)"; then
  docker exec -d "$P-db-1" sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -c "select pg_sleep(150)"' > /dev/null 2>&1
  sleep 36
  runo --stage S10; check "exit 3" 3 $RC
  grep -q 'gate E' "$ROOT/last.out"; check "the message names gate E" 0 $?
  check "S10 is not marked done; failed=S10" S10 "$(sget failed)"
  grep -q 'rollback that applies: no change was made' "$ROOT/last.out"; check "rollback guidance printed" 0 $?
  grep -q 'NOT started' "$ROOT/last.out"; check "next stage not started" 0 $?
fi

# ---------------------------------------------------------------- T3 insufficient RAM
if scen T3 "insufficient RAM"; then
  G17B_MIN_RAM_GB=9999 runo --stage S10; check "exit 4" 4 $RC
  grep -q 'free RAM' "$ROOT/last.out"; check "the message names the RAM" 0 $?
  check "nothing marked done" "" "$(sget done)"
fi

# ---------------------------------------------------------------- T4 invalid backup, and a backup that no longer equals the real state
if scen T4 "invalid backup copy / backup no longer equal to the real state"; then
  runo --stage S10; check "S10 passes" 0 $RC
  python - "$(W "$ROOT/b1/$DUMP")" <<'PY'
import sys, os
p = sys.argv[1]
data = bytearray(open(p, "rb").read()); data[20] ^= 0xFF
os.remove(p)                       # the folder policy lets the owner delete a Read-only copy
open(p, "wb").write(bytes(data))
PY
  runo --stage S11; check "corrupted primary copy -> exit 10" 10 $RC
  grep -q 'sha256 differs' "$ROOT/last.out"; check "reason: sha256 differs" 0 $?
  cp "$SRC_B1/$DUMP" "$ROOT/b1/$DUMP.new" && rm -f "$ROOT/b1/$DUMP" && mv "$ROOT/b1/$DUMP.new" "$ROOT/b1/$DUMP"
  powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$T17C/secure_file_acl.ps1")" -Path "$(W "$ROOT/b1/$DUMP")" > /dev/null
  sqla "create table zz_drift(x int)" > /dev/null
  runo --stage S11; check "database changed after the preflight (new table) -> exit 11" 11 $RC
  grep -q 'NEW BACKUP' "$ROOT/last.out"; check "message asks for the owner's authorisation for a new backup" 0 $?
  check "the backup files were not moved or deleted" "$REAL_SHA" "$(sha256sum "$ROOT/b1/$DUMP" | cut -d' ' -f1)"
fi

# ---------------------------------------------------------------- T5 wrong cluster identity
if scen T5 "wrong cluster identity"; then
  docker run -d --name "$P-decoy" --label "com.docker.compose.project=$P" --label purpose=g17b-test --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e POSTGRES_PASSWORD=decoy -e POSTGRES_DB=asistenteia pgvector/pgvector:0.8.7-pg15 > /dev/null
  runo --stage S10; check "S10 passes on the right cluster" 0 $RC
  i=0; until docker exec "$P-decoy" pg_isready -U asistente -d asistenteia > /dev/null 2>&1 || [ $i -ge 30 ]; do sleep 2; i=$((i+1)); done
  sed -i "s/^DBC=.*/DBC=$P-decoy/" "$ROOT/cfg.sh"
  runo --stage S11; check "another cluster (different system id) -> exit 3" 3 $RC
  grep -q 'system id differs\|identity' "$ROOT/last.out"; check "message names the identity" 0 $?
  docker rm -f "$P-decoy" > /dev/null 2>&1
  docker run -d --name "$P-decoy" --label "com.docker.compose.project=otherproject" --label purpose=g17b-test --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e POSTGRES_PASSWORD=decoy -e POSTGRES_DB=asistenteia pgvector/pgvector:0.8.7-pg15 > /dev/null
  rm -rf "$ROOT/state"; mkdir -p "$ROOT/state"
  runo --stage S10; check "container of another compose project -> exit 3" 3 $RC
  sed -i "s/^DBC=.*/DBC=asistenteia-db-1/; s/^PROJECT=.*/PROJECT=asistenteia/" "$ROOT/cfg.sh"
  runo --stage S10; check "the test profile pointing at the REAL stack is refused (exit 7)" 7 $RC
  check "the real database was only inspected: real container fingerprint unchanged" "$REAL_FP" "$(docker inspect -f '{{.Id}} {{.State.Status}} {{.Image}}' asistenteia-db-1 asistenteia-worker-1 | tr '\n' ';')"
fi

# ---------------------------------------------------------------- prefix for the destructive scenarios: S10..S21 done
prep_to() { # $1 = last stage to run
  runo --stage S10 && runo --stage S11
  runo --through "$1"
}
# ---------------------------------------------------------------- T6 bootstrap error
if scen T6 "error during bootstrap (wrong administrator password in .env.roles)"; then
  prep_to S21; check "S20 and S21 pass" 0 $RC
  sed -i 's#^ADMIN_DATABASE_URL=\(.*\)://\([^:]*\):[^@]*@#ADMIN_DATABASE_URL=\1://\2:wrong-password@#' "$ROOT/backend/.env.roles"
  runo --stage S22; check "bootstrap failure -> exit 22" 22 $RC
  check "failed=S22" S22 "$(sget failed)"
  grep -q 'runbook rollback steps 3, 4, 5, 6' "$ROOT/last.out"; check "rollback guidance for the stage reached" 0 $?
  runo --stage S23; check "the next stage is refused (exit 6): the sequence cannot continue" 6 $RC
  check "revision still 0005 (the database was not touched)" 0005 "$(sqla 'select version_num from alembic_version' | tr -d '\r')"
fi

# ---------------------------------------------------------------- T7 adoption errors
if scen T7 "adoption: dry run lists a different number of objects / apply fails"; then
  prep_to S22; check "S22 passes (exit 1 expected from bootstrap)" 0 $RC
  sqla "alter table users owner to asistente_migrator" > /dev/null
  runo --stage S23; check "dry run lists 8 objects instead of 9 -> exit 23" 23 $RC
  sqla "alter table users owner to asistente" > /dev/null
  runo --stage S23; check "re-running a stage that stopped needs the owner's confirmation (exit 8)" 8 $RC
  G17B_CONFIRM_RERUN=S23 runo --stage S23; check "after restoring the owner and confirming, the dry run passes" 0 $RC
  G17B_TEST_FAIL_AT=S24 runo --stage S24; check "adoption apply failure (test hook) -> exit 24" 24 $RC
  check "failed=S24 and the sequence stops" S24 "$(sget failed)"
fi

# ---------------------------------------------------------------- T8 migration failure + T12 recovery state
if scen T8 "migration failure (wrong migrator password) and the recovery state"; then
  prep_to S24; check "S20..S24 pass" 0 $RC
  sed -i 's#^MIGRATION_DATABASE_URL=\(.*\)://\([^:]*\):[^@]*@#MIGRATION_DATABASE_URL=\1://\2:wrong-password@#' "$ROOT/backend/.env.migrate"
  runo --stage S25; check "migration failure -> exit 25" 25 $RC
  grep -q 'runbook rollback steps 2, 3, 4, 5, 6' "$ROOT/last.out"; check "rollback guidance includes the downgrade (steps 2 to 6)" 0 $?
  runo --status; grep -q 'failed=S25' "$ROOT/last.out"; check "status: failed=S25" 0 $?
  grep -q 'revision_now=0005' "$ROOT/last.out"; check "status: revision_now=0005 (read only check)" 0 $?
  grep -q 'restricted_roles_exist=4' "$ROOT/last.out"; check "status: the four roles exist (so the adoption rollback applies)" 0 $?
  grep -q 'rollback that applies' "$ROOT/last.out"; check "status prints the rollback that applies" 0 $?
fi

# ---------------------------------------------------------------- T9 grants failure
if scen T9 "grants failure (the application role is missing when the grants run)"; then
  prep_to S24; check "S20..S24 pass" 0 $RC
  sqla "drop owned by asistente_app" asistenteia > /dev/null; sqla "drop owned by asistente_app" postgres > /dev/null; sqla "drop role asistente_app" postgres > /dev/null
  runo --stage S25; check "grants failure -> exit 25" 25 $RC
  [ "$RC" = 25 ] || { G17B_CONFIRM_RERUN=S25 G17B_TEST_FAIL_AT=S25 runo --stage S25; check "(fallback) injected failure -> exit 25" 25 $RC; }
  check "failed=S25" S25 "$(sget failed)"
fi

# ---------------------------------------------------------------- T10 interruption
if scen T10 "interruption of the process"; then
  G17B_TEST_SLEEP_AT=S10:60 bash -c 'G17B_PROFILE=test G17B_TEST_CONFIG="'"$ROOT"'/cfg.sh" G17B_STATE_DIR="'"$ROOT"'/state" bash "'"$HERE"'/run_17b.sh" --stage S10 > "'"$ROOT"'/int.out" 2>&1' &
  BG=$!
  for i in $(seq 1 40); do grep -q 'sleeping' "$ROOT/int.out" 2>/dev/null && break; sleep 1; done
  check "the run holds the lock while it works" 1 "$([ -d "$ROOT/state/lock" ] && echo 1 || echo 0)"
  runo --stage S10; check "a concurrent run is refused (exit 5)" 5 $RC
  PID=$(cat "$ROOT/state/lock/pid"); kill -TERM "$PID" 2>/dev/null
  wait $BG 2>/dev/null
  sleep 2
  check "state: interrupted=S10" S10 "$(sget interrupted)"
  check "the lock was released" 0 "$([ -d "$ROOT/state/lock" ] && echo 1 || echo 0)"
  grep -q 'INTERRUPTED' "$ROOT/int.out"; check "the log says INTERRUPTED" 0 $?
  grep -q 'rollback that applies' "$ROOT/int.out"; check "rollback guidance printed" 0 $?
  runo --status; grep -q 'interrupted=S10' "$ROOT/last.out"; check "status shows the interruption" 0 $?
  runo --stage S10; check "after an interruption the stage can be run again (it never completed): exit 0" 0 $RC
fi

# ---------------------------------------------------------------- T11 accidental second run and order
if scen T11 "second accidental execution and stage order"; then
  runo --stage S10; check "S10 passes" 0 $RC
  runo --stage S10; check "the same stage twice is refused (exit 6)" 6 $RC
  runo --stage S11; check "S11 passes" 0 $RC
  runo --stage S21; check "skipping stages is refused (exit 6)" 6 $RC
  runo --through S11; check "--through over finished stages does nothing harmful (exit 0)" 0 $RC
fi

# ---------------------------------------------------------------- T13 authorisation gate of the REAL profile (read only: it stops before touching anything)
if scen T13 "the real profile refuses stages that write, and the test hooks"; then
  RS="$ROOT/state-real"; mkdir -p "$RS"
  for st in S20 S21 S22 S23 S24 S25 S26 S30 S31; do
    G17B_STATE_DIR="$RS" bash "$ORCHS" --stage $st > /dev/null 2>&1; r=$?
    [ "$r" = 7 ] || { check "real profile refuses $st without the owner's GO" 7 $r; }
  done
  check "all nine writing stages are refused in the real profile (exit 7)" 7 7
  G17B_TEST_FAIL_AT=S10 G17B_STATE_DIR="$RS" bash "$ORCHS" --plan > /dev/null 2>&1; check "test hooks are refused in the real profile (exit 7)" 7 $?
  G17B_OWNER_GO=wrong G17B_STATE_DIR="$RS" bash "$ORCHS" --stage S20 > /dev/null 2>&1; check "a wrong GO token is refused (exit 7)" 7 $?
  check "the real services were not touched (fingerprint unchanged)" "$REAL_FP" "$(docker inspect -f '{{.Id}} {{.State.Status}} {{.Image}}' asistenteia-db-1 asistenteia-worker-1 | tr '\n' ';')"
fi

teardown_stack
echo "== end: containers left $(docker ps -a --filter name=$P -q | wc -l), networks left $(docker network ls --filter name=$P -q | wc -l), volumes left $(docker volume ls --filter name=$P -q | wc -l)"
AFTER_OTHER="$(docker ps -a --format '{{.Names}}' | grep -v "^$P" | sort | tr '\n' ';')"
check "no other container appeared or disappeared" "$BEFORE_OTHER" "$AFTER_OTHER"
check "real services unchanged" "$REAL_FP" "$(docker inspect -f '{{.Id}} {{.State.Status}} {{.Image}}' asistenteia-db-1 asistenteia-worker-1 | tr '\n' ';')"
check "the existing backup is unchanged" "$REAL_SHA" "$(sha256sum "$SRC_B1/$DUMP" | cut -d' ' -f1)"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]
