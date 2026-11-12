#!/bin/sh
# Task 1 (H13): cold start of the planned Compose flow db -> bootstrap -> migrate -> api/worker on a scratch project.
# Reads the real docker-compose.yml, never modifies it. Own project (g27h13), own network and volume, no published port,
# no real env file, temporary random credentials generated here and kept outside the repository.
#
# usage: H13_RUN_DIR=<directory outside the repository> sh run_h13.sh
# prerequisites: Docker, the images asistenteia-backend:latest and asistenteia-worker:latest, at least 6 GB of free host memory.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
OUT="$HERE/h13-output.txt"
[ "$H13_ONLY" = "C" ] && OUT="$HERE/h13-output-roundC.txt"
RUN="${H13_RUN_DIR:?set H13_RUN_DIR to a directory OUTSIDE the repository}"
mkdir -p "$RUN"
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "H13_RUN_DIR must be outside the repository"; exit 2;; esac
OVERRIDE="openspec/changes/database-least-privilege/reports/h13/compose.h13.override.yml"
: > "$OUT"

PWA=dummyA; PWM=dummyM; PWP=dummyP; PWW=dummyW; PWW2=dummyW2; JWT=dummyJ
gen() { python -c "import secrets;print(secrets.token_hex(10))"; }
mask() { sed -e "s/$PWA/***/g" -e "s/$PWM/***/g" -e "s/$PWP/***/g" -e "s/$PWW/***/g" -e "s/$JWT/***/g" -e "s/$PWW2/***/g"; }
log() { echo "$@" | mask | tee -a "$OUT"; }
dc() { (cd "$REPO" && H13_DIR="$(cd "$RUN" && pwd -W)" docker compose -p g27h13 -f docker-compose.yml -f "$OVERRIDE" "$@"); }
dcx() { (cd "$REPO" && H13_DIR="$(cd "$RUN" && pwd -W)" docker compose -p g27h13 -f docker-compose.yml -f "$RUN/profile.full.override.yml" "$@"); }
psqla() { dc exec -T db psql -U asistente -d asistenteia -At -c "$1"; }

mkenv() {
  PWA=$(gen); PWM=$(gen); PWP=$(gen); PWW=$(gen); PWW2=$(gen); JWT=$(python -c "import secrets;print(secrets.token_urlsafe(40))")
  printf 'POSTGRES_USER=asistente\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=asistenteia\n' "$PWA" > "$RUN/db.env"
  printf 'POSTGRES_USER=asistente\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=asistenteia\nPW_MIG=%s\nPW_APP=%s\nPW_WORKER=%s\n' "$PWA" "$PWM" "$PWP" "$PWW" > "$RUN/roles.env"
  printf 'DATABASE_URL=postgresql+psycopg://asistente_migrator:%s@db:5432/asistenteia\nAPP_ENV=development\nLOG_LEVEL=WARNING\nJWT_SECRET=%s\n' "$PWM" "$JWT" > "$RUN/migrate.env"
  printf 'DATABASE_URL=postgresql+psycopg://asistente_app:%s@db:5432/asistenteia\nAPP_ENV=development\nLOG_LEVEL=INFO\nJWT_SECRET=%s\nCORS_ORIGINS=http://localhost:5173\n' "$PWP" "$JWT" > "$RUN/api.env"
  sed -e "s#postgresql+psycopg://asistente:CHANGE_ME@db:5432/asistenteia#postgresql+psycopg://asistente_worker:$PWW@db:5432/asistenteia#" "$REPO/backend/.env.worker.example" > "$RUN/worker.env"
  [ "$(grep -v '^#' "$RUN/worker.env" | grep -c 'CHANGE_ME')" = "0" ] || { echo "worker example still holds a placeholder"; exit 3; }
}

wait_healthy() { # $1 container, $2 seconds
  i=0; while [ $i -lt "$2" ]; do st=$(docker inspect "$1" --format '{{.State.Health.Status}}' 2>/dev/null); [ "$st" = "healthy" ] && return 0; sleep 3; i=$((i+3)); done; return 1
}
state() { dc ps -a --format '{{.Service}} {{.State}} exit={{.ExitCode}}' 2>/dev/null | sort | tr '\n' ';'; }
fingerprint() { psqla "select md5(string_agg(x, '|' order by x)) from (
  select 'role:'||rolname||rolsuper||rolcreatedb||rolcreaterole||rolreplication||rolbypassrls||rolconnlimit||coalesce(array_to_string(rolconfig, ','), '') x from pg_roles where rolname like 'asistente_%'
  union all select 'rel:'||relname||coalesce(relacl::text, '') from pg_class where relnamespace = 'public'::regnamespace
  union all select 'att:'||attrelid::regclass||attname||attacl::text from pg_attribute where attacl is not null and attrelid in (select oid from pg_class where relnamespace = 'public'::regnamespace)
  union all select 'ns:'||coalesce(nspacl::text, '') from pg_namespace where nspname = 'public'
  union all select 'db:'||datname||coalesce(datacl::text, '') from pg_database) s"; }
teardown() {
  dc down -v --remove-orphans > /dev/null 2>&1
  log "teardown: containers left=$(docker ps -a --filter label=com.docker.compose.project=g27h13 -q | wc -l) volumes left=$(docker volume ls --format '{{.Name}}' | grep -c g27h13) networks left=$(docker network ls --format '{{.Name}}' | grep -c g27h13)"
}

roundC() {
  log "=== C bootstrap in a Compose profile that is not active (configuration only)"
  python - "$(cd "$HERE" && pwd -W)/compose.h13.override.yml" "$(cd "$RUN" && pwd -W)/profile.full.override.yml" <<'PYEOF'
import sys
src = open(sys.argv[1], encoding="utf-8").read()
marker = '    entrypoint: ["python", "/h13/bootstrap_standin.py"]\n'
assert src.count(marker) == 1
open(sys.argv[2], "w", encoding="utf-8").write(src.replace(marker, marker + '    profiles: ["admin"]\n'))
PYEOF
  log "config without profile: $(dcx config -q 2>&1 | head -1 | sed 's#compose file .*scratchpad[^ ]*#compose file <scratch>#' | cut -c1-200)"
  log "config with --profile admin: $(dcx --profile admin config -q 2>&1 | wc -l) errors"
}

# ---------------------------------------------------------------- preflight
FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
log "H13 run $(date -u +%FT%TZ) | free host RAM before: $FREE GB"
[ "$H13_ONLY" = "C" ] || python -c "import sys; sys.exit(0 if float('$FREE') >= 6 else 1)" || { log "RAM below 6 GB: stop"; exit 4; }
log "repo HEAD: $(cd "$REPO" && git rev-parse --short HEAD); compose file untouched: $(cd "$REPO" && git status --short docker-compose.yml | wc -l) changes"
mkenv
log "--- config checks"
CFG=$(dc config 2>&1)
log "config valid: $(dc config -q 2>&1 | wc -l) errors | published ports in the rendered config: $(echo "$CFG" | grep -c 'published:') | rendered references to real env files (backend/.env*): $(echo "$CFG" | grep -c 'backend/\.env')"
log "services: $(dc config --services | sort | tr '\n' ' ') | frontend profile-excluded: $(echo "$CFG" | grep -c 'h13-excluded')"
[ "$H13_ONLY" = "C" ] && { roundC; rm -f "$RUN"/*.env "$RUN"/profile.full.override.yml; log "round C finished (configuration only, nothing was started)"; exit 0; }

# ---------------------------------------------------------------- round A: cold start and behaviours
log "=== A1 cold start from nothing (no container, no volume)"
dc up -d > "$RUN/up1.txt" 2>&1; log "up -d rc=$? | dependency lines: $(grep -E 'Waiting|Healthy|Exited' "$RUN/up1.txt" | sed 's/^ *//' | tr '\n' ';' | cut -c1-400)"
wait_healthy g27h13-backend-1 150; log "backend healthy: $?  (0 = yes)"
wait_healthy g27h13-worker-1 150; log "worker healthy: $?  (0 = yes)"
log "state: $(state)"
log "bootstrap: $(dc logs --no-log-prefix bootstrap 2>&1 | tail -1)"
log "migrate:   $(dc logs --no-log-prefix migrate 2>&1 | grep -E 'alembic rc|grants' | tr '\n' '|' | cut -c1-260)"
log "database sessions by role (api and worker): $(psqla "select string_agg(usename||'='||n, ', ' order by usename) from (select usename, count(*) n from pg_stat_activity where datname = 'asistenteia' and usename like 'asistente_%' group by 1) s")"
log "alembic revision: $(psqla 'select version_num from alembic_version')"
log "role attributes: $(psqla "select string_agg(rolname||':'||(case when rolsuper or rolcreatedb or rolcreaterole or rolreplication or rolbypassrls then 'PRIVILEGED' else 'minimal' end), ', ' order by rolname) from pg_roles where rolname like 'asistente_%'")"
log "other databases closed to PUBLIC: $(psqla "select count(*) from pg_database where datname <> 'asistenteia' and has_database_privilege('public', oid, 'CONNECT')" 2>/dev/null)  (0 = all closed)"
log "--- A2 real API write under the application role, with persisted-state check"
EMAIL="h13-$(gen)@example.com"
CODE=$(dc exec -T backend python -c "
import json,urllib.request
r=urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/register',data=json.dumps({'name':'h13','email':'$EMAIL','password':'h13-temporary-pw-0'}).encode(),headers={'Content-Type':'application/json'},method='POST')
print(urllib.request.urlopen(r,timeout=10).status)" 2>&1 | tail -1)
log "POST /auth/register -> HTTP $CODE ; rows stored: $(psqla "select count(*) from users where email = '$EMAIL'") ; role stored: $(psqla "select role from users where email = '$EMAIL'")"
psqla "delete from users where email = '$EMAIL'" > /dev/null
log "--- A3 worker polls for 20 s with its role"
sleep 20
log "worker log lines mentioning an error or a permission problem: $(dc logs worker 2>&1 | grep -ciE 'database error|permission denied|insufficient|ProgrammingError')"
log "--- A4 secrets exposure (variable NAMES only; values are searched, never printed)"
for c in db bootstrap migrate backend worker; do
  cid=$(docker ps -a --filter "label=com.docker.compose.project=g27h13" --filter "label=com.docker.compose.service=$c" -q | head -1)
  names=$(docker inspect "$cid" --format '{{range .Config.Env}}{{println .}}{{end}}' | cut -d= -f1 | grep -E '^(POSTGRES_|PW_|DATABASE_URL|JWT_SECRET|CORS_ORIGINS|TEST_DATABASE_URL|APP_ENV|MIGRATION_|EMBEDDING_)' | sort | tr '\n' ' ')
  admin_pw=$(docker inspect "$cid" | grep -c "$PWA"); mig_pw=$(docker inspect "$cid" | grep -c "$PWM"); app_pw=$(docker inspect "$cid" | grep -c "$PWP"); wk_pw=$(docker inspect "$cid" | grep -c "$PWW")
  log "$c | names: $names | holds admin password: $admin_pw, migrator: $mig_pw, app: $app_pw, worker: $wk_pw (counts of matching lines)"
done
log "--- A5 second 'up -d' on the existing stack"
FP1=$(fingerprint); B1=$(docker inspect g27h13-backend-1 --format '{{.Id}}' | cut -c1-12); W1=$(docker inspect g27h13-worker-1 --format '{{.Id}}' | cut -c1-12)
S1=$(docker inspect g27h13-bootstrap-1 --format '{{.State.StartedAt}}')
dc up -d > "$RUN/up2.txt" 2>&1; log "up -d rc=$?"
sleep 12
FP2=$(fingerprint); B2=$(docker inspect g27h13-backend-1 --format '{{.Id}}' | cut -c1-12); W2=$(docker inspect g27h13-worker-1 --format '{{.Id}}' | cut -c1-12)
S2=$(docker inspect g27h13-bootstrap-1 --format '{{.State.StartedAt}}')
log "bootstrap started again: $([ "$S1" != "$S2" ] && echo yes || echo no) ; second run output: $(dc logs --no-log-prefix bootstrap 2>&1 | tail -1) ; catalog/ACL fingerprint equal: $([ "$FP1" = "$FP2" ] && echo yes || echo NO) ; backend container unchanged: $([ "$B1" = "$B2" ] && echo yes || echo NO) ; worker container unchanged: $([ "$W1" = "$W2" ] && echo yes || echo NO)"
log "--- A6 'restart' keeps the old environment, 'up -d' applies a changed environment"
sed -i 's/^LOG_LEVEL=INFO/LOG_LEVEL=DEBUG/' "$RUN/worker.env"
dc restart worker > /dev/null 2>&1; sleep 4
log "after 'docker compose restart worker': LOG_LEVEL=$(dc exec -T worker printenv LOG_LEVEL) (old value expected)"
W3=$(docker inspect g27h13-worker-1 --format '{{.Id}}' | cut -c1-12)
dc up -d > /dev/null 2>&1; sleep 6
W4=$(docker inspect g27h13-worker-1 --format '{{.Id}}' | cut -c1-12)
log "after plain 'docker compose up -d': LOG_LEVEL=$(dc exec -T worker printenv LOG_LEVEL) ; worker container recreated by compose: $([ "$W3" != "$W4" ] && echo yes || echo no)"
log "--- A7 credential rotation of the worker role through the environment files"
sed -i "s/$PWW/$PWW2/" "$RUN/roles.env" "$RUN/worker.env"
dc up -d > /dev/null 2>&1
wait_healthy g27h13-worker-1 150; log "worker healthy with the new password: $? (0 = yes)"
W5=$(docker inspect g27h13-worker-1 --format '{{.Id}}' | cut -c1-12)
log "worker recreated: $([ "$W4" != "$W5" ] && echo yes || echo no) ; bootstrap applied the new password: $(dc logs --no-log-prefix bootstrap 2>&1 | tail -1)"
OLD=$(dc exec -T -e PGPASSWORD="$PWW" db psql -h db -U asistente_worker -d asistenteia -At -c 'select 1' 2>&1 | tail -1 | cut -c1-90)
NEW=$(dc exec -T -e PGPASSWORD="$PWW2" db psql -h db -U asistente_worker -d asistenteia -At -c 'select current_user' 2>&1 | tail -1 | cut -c1-90)
log "login with the OLD password: $OLD"
log "login with the NEW password: $NEW"
teardown

# ---------------------------------------------------------------- round B: migrate fails, dependants must not start
log "=== B migrate fails (wrong migrator password): api and worker must not start"
mkenv
sed -i "s/$PWM/wrong-$(gen)/" "$RUN/migrate.env"
dc up -d > "$RUN/up3.txt" 2>&1; log "up -d rc=$? (non-zero expected) | message: $(grep -iE 'exited|failed|exit' "$RUN/up3.txt" | head -2 | tr '\n' ';' | cut -c1-200)"
sleep 3
log "state: $(state)"
log "dependants created but never started (state created): $(docker ps -a --filter label=com.docker.compose.project=g27h13 --filter label=com.docker.compose.service=backend -q | wc -l)/$(docker ps -a --filter label=com.docker.compose.project=g27h13 --filter label=com.docker.compose.service=worker -q | wc -l) running: $(docker ps --filter label=com.docker.compose.project=g27h13 --filter label=com.docker.compose.service=backend -q | wc -l)/$(docker ps --filter label=com.docker.compose.project=g27h13 --filter label=com.docker.compose.service=worker -q | wc -l)"
sed -i "s#asistente_migrator:wrong-[0-9a-f]*@#asistente_migrator:$PWM@#" "$RUN/migrate.env"
dc up -d > "$RUN/up4.txt" 2>&1; log "after fixing the password, up -d rc=$?"
wait_healthy g27h13-backend-1 150; log "backend healthy after recovery: $? (0 = yes)"
wait_healthy g27h13-worker-1 150; log "worker healthy after recovery: $? (0 = yes)"
teardown

roundC

# ---------------------------------------------------------------- round D: repeatability
log "=== D second cold start from nothing (repeatability)"
mkenv
dc up -d > "$RUN/up5.txt" 2>&1; log "up -d rc=$?"
wait_healthy g27h13-backend-1 150; log "backend healthy: $?"
wait_healthy g27h13-worker-1 150; log "worker healthy: $?"
log "state: $(state)"
log "database sessions by role: $(psqla "select string_agg(usename||'='||n, ', ' order by usename) from (select usename, count(*) n from pg_stat_activity where datname = 'asistenteia' and usename like 'asistente_%' group by 1) s")"
teardown
rm -f "$RUN"/*.env "$RUN"/profile.full.override.yml "$RUN"/up*.txt
log "H13 finished $(date -u +%FT%TZ) | free host RAM after: $(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r') GB"
