#!/usr/bin/env bash
# Task 6.4: the cold-start scenarios of task 1 (H13) with the REAL commands db-bootstrap and db-migrate.
# Reads the real docker-compose.yml (never modifies it) plus compose.h13.real.override.yml. Own project (g28h13), own
# network and volume, no published port, synthetic random credentials in a directory outside the repository, no real
# env file. Refuses to start with less than 6 GB of free memory.
#
# usage: H13_RUN_DIR=<directory outside the repository> bash run_h13_real.sh
# prerequisites: Docker, images asistenteia-backend:g6-branch (docker build --target api -t asistenteia-backend:g6-branch backend)
#                and asistenteia-worker:main-f455234.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
OUT="$HERE/h13-real-output.txt"
RUN="${H13_RUN_DIR:?set H13_RUN_DIR to a directory OUTSIDE the repository}"
mkdir -p "$RUN"
[ -z "$(ls -A "$RUN" 2>/dev/null)" ] || { echo "H13_RUN_DIR must be an empty directory (the run deletes *.env there)"; exit 2; }
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "H13_RUN_DIR must be outside the repository"; exit 2;; esac
OVERRIDE="openspec/changes/database-least-privilege/reports/group-6/compose.h13.real.override.yml"
P=g28h13
: > "$OUT"

gen() { python -c "import secrets;print(secrets.token_hex(12))"; }
SECRETS=""
mask() { local s; s="$(cat)"; for v in $SECRETS; do s="${s//$v/***}"; done; printf '%s\n' "$s"; }
log() { echo "$@" | mask | tee -a "$OUT"; }
dc() { (cd "$REPO" && H13_DIR="$(cd "$RUN" && pwd -W)" docker compose -p $P -f docker-compose.yml -f "$OVERRIDE" "$@"); }
psqla() { dc exec -T db psql -U asistente -d asistenteia -At -c "$1"; }
wait_healthy() { local i=0; while [ $i -lt "$2" ]; do [ "$(docker inspect "$1" --format '{{.State.Health.Status}}' 2>/dev/null)" = "healthy" ] && return 0; sleep 3; i=$((i+3)); done; return 1; }
state() { dc ps -a --format '{{.Service}}={{.State}}({{.ExitCode}})' 2>/dev/null | sort | tr '\n' ' '; }

mkenv() {  # $1 = admin password override (optional), $2 = migrator password in migrate.env override (optional)
  PA=$(gen); PM=$(gen); PP=$(gen); PW=$(gen); PC=$(gen); JWT=$(python -c "import secrets;print(secrets.token_urlsafe(40))")
  SECRETS="$PA $PM $PP $PW $PC $JWT"
  printf 'POSTGRES_USER=asistente\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=asistenteia\n' "$PA" > "$RUN/db.env"
  printf 'ADMIN_DATABASE_URL=postgresql+psycopg://asistente:%s@db:5432/postgres\nDB_MIGRATOR_PASSWORD=%s\nDB_APP_PASSWORD=%s\nDB_WORKER_PASSWORD=%s\nDB_CLI_PASSWORD=%s\n' "$PA" "$PM" "$PP" "$PW" "$PC" > "$RUN/roles.env"
  printf 'MIGRATION_DATABASE_URL=postgresql+psycopg://asistente_migrator:%s@db:5432/asistenteia\n' "$PM" > "$RUN/migrate.env"
  printf 'DATABASE_URL=postgresql+psycopg://asistente_app:%s@db:5432/asistenteia\nAPP_ENV=development\nLOG_LEVEL=INFO\nJWT_SECRET=%s\nCORS_ORIGINS=http://localhost:5173\n' "$PP" "$JWT" > "$RUN/api.env"
  sed -e "s#postgresql+psycopg://asistente:CHANGE_ME@db:5432/asistenteia#postgresql+psycopg://asistente_worker:$PW@db:5432/asistenteia#" "$REPO/backend/.env.worker.example" > "$RUN/worker.env"
  [ "$(grep -v '^#' "$RUN/worker.env" | grep -c 'CHANGE_ME')" = "0" ] || { echo "worker example still holds a placeholder"; exit 3; }
}
envnames() {  # variable NAMES (never values) of a container
  docker inspect "$1" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | cut -d= -f1 | grep -E '^(POSTGRES_|ADMIN_|DB_|MIGRATION_|DATABASE_URL|JWT_|TEST_|CORS_|MAX_PDF|EMBEDDING)' | sort | tr '\n' ' '
}
fingerprint() { psqla "select md5(string_agg(x, '|' order by x)) from (
  select 'role:'||rolname||rolsuper||rolcreatedb||rolcreaterole||rolreplication||rolbypassrls||rolconnlimit||coalesce(array_to_string(rolconfig, ','), '') x from pg_roles where rolname like 'asistente_%'
  union all select 'rel:'||relname||coalesce(relacl::text, '') from pg_class where relnamespace = 'public'::regnamespace
  union all select 'ns:'||coalesce(nspacl::text, '') from pg_namespace where nspname = 'public'
  union all select 'db:'||datname||coalesce(datacl::text, '') from pg_database) s"; }
verify() { docker run --rm --network ${P}_default --env-file "$RUN/migrate.env" --env-file "$RUN/roles.env" asistenteia-backend:g6-branch python -m app.cli db-verify 2>&1 | tail -3 | mask; }
teardown() {
  dc down -v --remove-orphans > /dev/null 2>&1
  log "teardown: containers left=$(docker ps -a --filter label=com.docker.compose.project=$P -q | wc -l) volumes left=$(docker volume ls --format '{{.Name}}' | grep -c $P) networks left=$(docker network ls --format '{{.Name}}' | grep -c $P)"
}

FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
log "H13 with the real commands $(date -u +%FT%TZ) | free host RAM before: $FREE GB"
python -c "import sys; sys.exit(0 if float('$FREE') >= 6 else 1)" || { log "RAM below 6 GB: stop"; exit 4; }
BEFORE_OTHER="$(docker ps --format '{{.Names}}' | grep -v "^${P}-" | sort | tr '\n' ' ')"
log "repo HEAD: $(cd "$REPO" && git rev-parse --short HEAD) | docker-compose.yml is the branch version, not modified by this run"
mkenv
CFG=$(dc config 2>&1)
log "config valid: $(dc config -q 2>&1 | wc -l) errors | published ports: $(echo "$CFG" | grep -c 'published:') | references to real env files (backend/.env*): $(echo "$CFG" | grep -c 'backend/\.env') | services: $(dc config --services | sort | tr '\n' ' ')"

cold_start() {  # $1 = label
  log "=== $1 cold start from nothing"
  dc up -d > "$RUN/up.txt" 2>&1; log "up -d rc=$? | $(grep -E 'Waiting|Healthy|Exited|Started' "$RUN/up.txt" | sed 's/^ *//' | tr '\n' ';' | cut -c1-420)"
  wait_healthy ${P}-backend-1 150; log "backend healthy: rc=$? (0 = yes)"
  wait_healthy ${P}-worker-1 300; log "worker healthy: rc=$? (0 = yes)"
  log "states: $(state)"
  log "roles: $(psqla "select string_agg(rolname||':'||rolsuper||':'||rolconnlimit, ' ' order by rolname) from pg_roles where rolname like 'asistente_%'")"
  log "alembic revision: $(psqla 'select version_num from alembic_version')"
  log "test database asistenteia_test present (created by docker/db-init): $(psqla "select count(*) from pg_database where datname = 'asistenteia_test'")"
  log "sessions by role: $(psqla "select string_agg(usename||'='||n, ' ') from (select usename, count(*) n from pg_stat_activity where usename like 'asistente_%' group by 1 order by 1) s")"
  log "owners of public tables: $(psqla "select string_agg(distinct r.rolname, ',') from pg_class c join pg_roles r on r.oid=c.relowner where c.relnamespace='public'::regnamespace and c.relkind='r'")"
  log "db-verify: $(verify)"
}

# ---------------------------------------------------------------- A: cold start and behaviours
cold_start "A1"
log "--- A2 secrets by container (variable names only)"
for s in db bootstrap migrate backend worker; do log "$s: $(envnames ${P}-$s-1)"; done
log "published ports of the project: $(docker ps -a --filter label=com.docker.compose.project=$P --format '{{.Ports}}' | grep -c '0.0.0.0\|127.0.0.1')"
log "--- A3 /health through the container network"
log "health: $(docker exec ${P}-backend-1 python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=3).status)" 2>&1 | tail -1)"
FP1=$(fingerprint); IDB=$(docker inspect ${P}-backend-1 --format '{{.Id}}'); IDW=$(docker inspect ${P}-worker-1 --format '{{.Id}}')
SB1=$(docker inspect ${P}-bootstrap-1 --format '{{.State.StartedAt}}'); SM1=$(docker inspect ${P}-migrate-1 --format '{{.State.StartedAt}}')
log "--- A4 second up -d (idempotent)"
dc up -d > "$RUN/up2.txt" 2>&1; log "up -d rc=$?"
log "bootstrap ran again: $([ "$SB1" != "$(docker inspect ${P}-bootstrap-1 --format '{{.State.StartedAt}}')" ] && echo yes || echo no) | migrate ran again: $([ "$SM1" != "$(docker inspect ${P}-migrate-1 --format '{{.State.StartedAt}}')" ] && echo yes || echo no)"
log "fingerprint equal: $([ "$FP1" = "$(fingerprint)" ] && echo yes || echo no) | backend container unchanged: $([ "$IDB" = "$(docker inspect ${P}-backend-1 --format '{{.Id}}')" ] && echo yes || echo no) | worker container unchanged: $([ "$IDW" = "$(docker inspect ${P}-worker-1 --format '{{.Id}}')" ] && echo yes || echo no)"
log "states: $(state)"; log "db-verify: $(verify)"
log "--- A5 restart keeps the old environment, up -d applies a changed one"
sed -i 's/^LOG_LEVEL=.*/LOG_LEVEL=DEBUG/' "$RUN/worker.env"
dc restart worker > /dev/null 2>&1; wait_healthy ${P}-worker-1 300
log "after restart: LOG_LEVEL=$(docker exec ${P}-worker-1 printenv LOG_LEVEL)"
dc up -d > /dev/null 2>&1; wait_healthy ${P}-worker-1 300
log "after up -d: LOG_LEVEL=$(docker exec ${P}-worker-1 printenv LOG_LEVEL) | worker recreated: $([ "$IDW" != "$(docker inspect ${P}-worker-1 --format '{{.Id}}')" ] && echo yes || echo no)"
log "--- A6 credential rotation of the worker password"
OLD=$PW; PW2=$(gen); SECRETS="$SECRETS $PW2"
sed -i "s#^DB_WORKER_PASSWORD=.*#DB_WORKER_PASSWORD=$PW2#" "$RUN/roles.env"
sed -i "s#asistente_worker:$OLD@#asistente_worker:$PW2@#" "$RUN/worker.env"
dc up -d > "$RUN/up3.txt" 2>&1; log "up -d rc=$?"; wait_healthy ${P}-worker-1 300; log "worker healthy after rotation: rc=$? (0 = yes)"
login() {  # $1 = password: connect over the network from another container (inside the db container 127.0.0.1 is trust)
  docker run --rm --network ${P}_default -e PW="$1" asistenteia-backend:g6-branch python -c "
import os, psycopg
try:
    with psycopg.connect(host='db', user='asistente_worker', dbname='asistenteia', password=os.environ['PW'], connect_timeout=5) as c:
        print('accepted as', c.execute('select current_user').fetchone()[0])
except psycopg.OperationalError as e:
    print('refused' if 'password authentication failed' in str(e) else 'error')
" 2>&1 | tail -1
}
log "old password: $(login $OLD) (expected: refused)"
log "new password: $(login $PW2) (expected: accepted as asistente_worker)"
log "db-verify: $(verify)"
teardown

# ---------------------------------------------------------------- B: bootstrap fails
log "=== B bootstrap fails (wrong administrator password), from nothing"
mkenv; GOOD_ROLES=$(cat "$RUN/roles.env"); sed -i "s#^ADMIN_DATABASE_URL=\(.*\):[0-9a-f]*@db#ADMIN_DATABASE_URL=\1:wrong0wrong0wrong0wrong0@db#" "$RUN/roles.env"
dc up -d > "$RUN/upB.txt" 2>&1; log "up -d rc=$? (non-zero expected)"
log "states: $(state)"
log "bootstrap log: $(dc logs bootstrap 2>&1 | tail -2 | mask | cut -c1-200 | tr '\n' '|')"
log "dependants not running: backend=$(docker inspect ${P}-backend-1 --format '{{.State.Status}}') worker=$(docker inspect ${P}-worker-1 --format '{{.State.Status}}') migrate=$(docker inspect ${P}-migrate-1 --format '{{.State.Status}}')"
printf '%s\n' "$GOOD_ROLES" > "$RUN/roles.env"
dc up -d > "$RUN/upB2.txt" 2>&1; log "recovery up -d rc=$?"; wait_healthy ${P}-backend-1 150; log "backend healthy: rc=$?"; wait_healthy ${P}-worker-1 300; log "worker healthy: rc=$?"; log "states: $(state)"
teardown

# ---------------------------------------------------------------- C: migrate fails
log "=== C migrate fails (wrong migrator password), from nothing"
mkenv; GOOD_MIG=$(cat "$RUN/migrate.env"); sed -i "s#asistente_migrator:[0-9a-f]*@#asistente_migrator:wrong0wrong0wrong0wrong0@#" "$RUN/migrate.env"
dc up -d > "$RUN/upC.txt" 2>&1; log "up -d rc=$? (non-zero expected)"
log "states: $(state)"
log "migrate log: $(dc logs migrate 2>&1 | tail -2 | mask | cut -c1-200 | tr '\n' '|')"
log "dependants not running: backend=$(docker inspect ${P}-backend-1 --format '{{.State.Status}}') worker=$(docker inspect ${P}-worker-1 --format '{{.State.Status}}')"
printf '%s\n' "$GOOD_MIG" > "$RUN/migrate.env"
dc up -d > "$RUN/upC2.txt" 2>&1; log "recovery up -d rc=$?"; wait_healthy ${P}-backend-1 150; log "backend healthy: rc=$?"; wait_healthy ${P}-worker-1 300; log "worker healthy: rc=$?"; log "states: $(state)"
log "alembic revision: $(psqla 'select version_num from alembic_version')"
teardown

# ---------------------------------------------------------------- E: the committed optional env files are missing
log "=== E bootstrap and migrate started WITHOUT their env files (the real optional paths backend/.env.roles and backend/.env.migrate do not exist)"
mkenv
python - "$(cd "$HERE" && pwd -W)/compose.h13.real.override.yml" "$(cd "$RUN" && pwd -W)/optional.override.yml" <<'PYEOF'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
for name in ("roles.env", "migrate.env"):
    pattern = r"    env_file: !override\n      - \$\{H13_DIR\}/" + re.escape(name) + r"\n"
    assert len(re.findall(pattern, text)) == 1, name
    text = re.sub(pattern, "", text)
open(sys.argv[2], "w", encoding="utf-8").write(text)
PYEOF
dce() { (cd "$REPO" && H13_DIR="$(cd "$RUN" && pwd -W)" docker compose -p $P -f docker-compose.yml -f "$RUN/optional.override.yml" "$@"); }
log "config valid with the files missing: $(dce config -q 2>&1 | wc -l) errors"
dce up -d > "$RUN/upE.txt" 2>&1; log "up -d rc=$? (non-zero expected)"
log "states: $(dce ps -a --format '{{.Service}}={{.State}}({{.ExitCode}})' | sort | tr '\n' ' ')"
log "bootstrap log: $(dce logs bootstrap 2>&1 | tail -2 | mask | cut -c1-200 | tr '\n' '|')"
log "dependants not running: migrate=$(docker inspect ${P}-migrate-1 --format '{{.State.Status}}') backend=$(docker inspect ${P}-backend-1 --format '{{.State.Status}}') worker=$(docker inspect ${P}-worker-1 --format '{{.State.Status}}')"
dce down -v --remove-orphans > /dev/null 2>&1
log "teardown: containers left=$(docker ps -a --filter label=com.docker.compose.project=$P -q | wc -l) volumes left=$(docker volume ls --format '{{.Name}}' | grep -c $P)"

# ---------------------------------------------------------------- D: repeat
mkenv; cold_start "D"
teardown

AFTER_OTHER="$(docker ps --format '{{.Names}}' | grep -v "^${P}-" | sort | tr '\n' ' ')"
log "other containers before/after identical: $([ "$BEFORE_OTHER" = "$AFTER_OTHER" ] && echo yes || echo no)"
rm -f "$RUN"/*.env
log "run finished; environment files of the run deleted"
