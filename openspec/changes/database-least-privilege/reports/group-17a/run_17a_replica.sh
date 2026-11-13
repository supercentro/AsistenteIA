#!/usr/bin/env bash
# Group 17A: a REPLICA of the development stack (Docker Compose project g17arep, completely disposable)
# on which step 17B is rehearsed with the real mechanics: the real docker-compose.yml of this branch
# (new) and of main (old, for the way back), the real one-shot services, the env-file tool, the backup
# procedure, the adoption, the switch of the two DATABASE_URL values, the rotation of the administrator
# password, the full rollback and the recovery from the dump.
#
# usage: G17A_BACKUP=<dump> G17A_RUN_DIR=<empty directory OUTSIDE the repository> bash run_17a_replica.sh
#
# Nothing here touches the development stack: another Compose project name, its own network and named
# volume, no published database port, the API published only on 127.0.0.1 at a free temporary port,
# synthetic credentials, files in G17A_RUN_DIR. The real docker-compose.yml is only read.
# Refuses to start with less than 8 GB of free memory.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
REPOW="$(cd "$REPO" && pwd -W)"
OUT="$HERE/g17a-replica-output.txt"
TOOLS="$HERE/tools"
TOOLSW="$(cd "$TOOLS" && pwd -W)"
RUN="${G17A_RUN_DIR:?set G17A_RUN_DIR to an empty directory OUTSIDE the repository}"
BACKUP="${G17A_BACKUP:?set G17A_BACKUP to the verified dump of revision 0004}"
mkdir -p "$RUN"
[ -z "$(ls -A "$RUN" 2>/dev/null)" ] || { echo "G17A_RUN_DIR must be an empty directory"; exit 2; }
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "G17A_RUN_DIR must be outside the repository"; exit 2;; esac
RUNW="$(cd "$RUN" && pwd -W)"
ENVDIR="$RUN/env"; ENVW="$RUNW/env"; mkdir -p "$ENVDIR" "$RUN/durable"
P=g17arep; NET="${P}_default"; DBC="${P}-db-1"; API="${P}-backend-1"; WK="${P}-worker-1"
LABEL="com.docker.compose.project=$P"
IMG_OLD_API="asistenteia-backend:g17a-old"; IMG_OLD_WK="asistenteia-worker:g17a-old"
IMG_NEW_API="asistenteia-backend:g17a-new"; IMG_NEW_WK="asistenteia-worker:g17a-new"
BKC="g17abk$$"; BKNET="g17abknet$$"; BKLABEL="purpose=g17a-backup-restore"
IMG_PG="pgvector/pgvector:0.8.7-pg15"
: > "$OUT"

gen() { python -c "import secrets;print(secrets.token_hex(12))"; }
SECRETS=()
mask() { local s; s="$(cat)"; for v in "${SECRETS[@]}"; do [ -n "$v" ] && s="${s//$v/***}"; done; printf '%s\n' "$s"; }
log() { echo "$@" | mask | tee -a "$OUT"; }
ms() { echo $(( $(date +%s%N) / 1000000 )); }
STEP_MS=0
run() { local name="$1"; shift; local a; a=$(ms); OUTP="$("$@" 2>&1)"; RC=$?; STEP_MS=$(( $(ms) - a ))
  log "  [$name] rc=$RC (${STEP_MS} ms)"
  if [ -n "$OUTP" ]; then printf '%s\n' "$OUTP" | tail -n "${TAILN:-6}" | cut -c1-220 | sed 's/^/      | /' | mask | tee -a "$OUT" > /dev/null; fi; }
dcx() { local which="$1"; shift; local file="$REPOW/docker-compose.yml"; local over="$RUNW/override.new.yml"
  if [ "$which" = old ]; then file="$RUNW/compose.main.yml"; over="$RUNW/override.old.yml"; fi
  (cd "$REPO" && G17_DIR="$ENVW" G17_PORT="$PORT" docker compose -p "$P" --project-directory "$REPOW" -f "$file" -f "$over" "$@"); }
sqlc() { docker exec -i "$1" sh -c "psql -U \"\$POSTGRES_USER\" -d ${2:-postgres} -At -v ON_ERROR_STOP=1" <<< "$3" 2>&1; }
psqla() { sqlc "$DBC" "$1" "$2"; }
sql() { docker exec -i "$DBC" sh -c "psql -U \"\$POSTGRES_USER\" -d $DB -At -v ON_ERROR_STOP=1" <<< "$1" 2>&1; }
sql_as() { docker exec "$DBC" psql -U "$1" -d "$DB" -At -c "$2" 2>&1 | head -3 | tr '\n' ' '; }
snap_db() { docker exec -i "$1" sh -c "psql -U \"\$POSTGRES_USER\" -d $2 -At -F '|' -v ON_ERROR_STOP=1 -f -" < "$TOOLS/snapshot_db.sql" > "$3" 2>&1; }
snap_cluster() { docker exec -i "$1" sh -c "psql -U \"\$POSTGRES_USER\" -d postgres -At -F '|' -v ON_ERROR_STOP=1 -f -" < "$TOOLS/snapshot_cluster.sql" > "$2" 2>&1; }
appx() { local envs=(); while [ "$1" != "--" ]; do envs+=(--env-file "$ENVW/$1"); shift; done; shift
  docker run --rm -i --network "$NET" --label "$LABEL" -m 768m --cpus 1 "${envs[@]}" --entrypoint python "${APPIMG:-$IMG_NEW_API}" -m app.cli "$@"; }
rev() { sql "select version_num from alembic_version"; }
DB=asistenteia

PASS=0; FAIL=0; N=0
check() { # $1 label, $2 expected, $3 obtained
  N=$((N+1))
  if [ "$2" = "$3" ]; then PASS=$((PASS+1)); log "  [$N] PASS $1 | expected $2, obtained $3"
  else FAIL=$((FAIL+1)); log "  [$N] FAIL $1 | expected $2, obtained $3"; fi
}
BODY="$RUN/body.json"
api() { # METHOD PATH EXPECTED TOKEN [JSON]   -> sets CODE and BODY
  local method="$1" path="$2" expected="$3" token="$4" json="${5:-}" args=(-s -o "$BODY" -w '%{http_code}' --max-time 30 -X "$1" "$BASE$2")
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  [ -n "$json" ] && args+=(-H 'Content-Type: application/json' -d "$json")
  CODE=$(curl "${args[@]}")
  check "$method $path" "$expected" "$CODE"
}
upload() { # PATH EXPECTED TOKEN FILE NAME CTYPE -> sets CODE and BODY
  local args=(-s -o "$BODY" -w '%{http_code}' --max-time 60 -X POST "$BASE$1" -F "file=@$4;filename=$5;type=$6")
  [ -n "$3" ] && args+=(-H "Authorization: Bearer $3")
  CODE=$(curl "${args[@]}")
  check "POST $1 (upload $5)" "$2" "$CODE"
}
field() { python -c "import json,sys;d=json.load(open(sys.argv[1]));v=d
for k in sys.argv[2].split('.'): v=v[int(k)] if k.isdigit() else v.get(k) if isinstance(v,dict) else None
print('' if v is None else v)" "$BODY" "$1"; }
wait_doc() { local i=0 s; while [ $i -lt 240 ]; do s=$(sql "select status from documents where id='$1'"); [ "$s" = "ready" ] || [ "$s" = "failed" ] && { echo "$s"; return; }; sleep 3; i=$((i+3)); done; echo "timeout"; }

teardown() {
  log "--- identity of every resource of this replica, before removal"
  log "containers: $(docker ps -a --filter label=$LABEL --format '{{.Names}}' | tr '\n' ' ')$(docker ps -a --filter label=$BKLABEL --format '{{.Names}}' | tr '\n' ' ')"
  log "networks:   $(docker network ls --filter label=$LABEL --format '{{.Name}}' | tr '\n' ' ')$(docker network ls --filter label=$BKLABEL --format '{{.Name}}' | tr '\n' ' ')"
  log "volumes:    $(docker volume ls --filter label=$LABEL --format '{{.Name}}' | tr '\n' ' ')"
  log "names outside the g17a scheme among them (must be empty): $(docker ps -a --filter label=$LABEL --format '{{.Names}}' | grep -v "^$P" | tr '\n' ' ')"
  dcx new down -v --remove-orphans > /dev/null 2>&1
  docker rm -f "$BKC" > /dev/null 2>&1; docker network rm "$BKNET" > /dev/null 2>&1
  log "after removal: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l) volumes left=$(docker volume ls --filter label=$LABEL -q | wc -l)"
  docker rmi "$IMG_OLD_API" "$IMG_OLD_WK" "$IMG_NEW_API" "$IMG_NEW_WK" > /dev/null 2>&1
  log "temporary image tags left: $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c 'g17a-')"
  log "other containers (the real stack and other projects) before and after identical: $([ "$BEFORE_OTHER" = "$(docker ps --format '{{.Names}}' | grep -v "^$P\|^g17a" | sort | tr '\n' ';')" ] && echo yes || echo NO)"
  log "original backup untouched: sha $( [ "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "$SHA_BEFORE" ] && echo equal || echo DIFFERENT )"
  rm -rf "$RUN"/env "$RUN"/*.yml "$RUN"/Dockerfile.worker "$RUN"/*.pdf "$RUN"/body.json "$RUN"/*.txt "$RUN"/backup.dump
}
trap 'teardown' EXIT

# =================================================================================== 0
log "=== 0 preflight $(date -u +%FT%TZ)"
FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
log "free host RAM before: $FREE GB (8 needed)"
python -c "import sys; sys.exit(0 if float('$FREE') >= 8 else 1)" || { log "RAM below 8 GB: stop"; trap - EXIT; exit 4; }
BEFORE_OTHER="$(docker ps --format '{{.Names}}' | grep -v "^$P\|^g17a" | sort | tr '\n' ';')"
log "repo HEAD: $(cd "$REPO" && git rev-parse --short HEAD)"
SHA_BEFORE="$(sha256sum "$BACKUP" | cut -d' ' -f1)"
check "the base backup has the recorded sha256" "$(cut -d' ' -f1 "$BACKUP.sha256")" "$SHA_BEFORE"
cp "$BACKUP" "$RUN/backup.dump"

log "=== images: OLD = the images of main that the development stack runs; NEW = built from this branch"
docker tag asistenteia-backend:main-f455234 "$IMG_OLD_API" && docker tag asistenteia-worker:main-f455234 "$IMG_OLD_WK" || { log "old images missing"; exit 5; }
CTX="$(cd "$REPO/backend" && pwd -W)"
docker build -q --target api -t "$IMG_NEW_API" "$CTX" > /dev/null || { log "api image build FAILED"; exit 5; }
printf 'FROM asistenteia-worker:main-f455234\nUSER root\nCOPY app /app/app\nUSER appuser\n' > "$RUN/Dockerfile.worker"
docker build -q -f "$RUNW/Dockerfile.worker" -t "$IMG_NEW_WK" "$CTX" > /dev/null || { log "worker image build FAILED"; exit 5; }
log "built $IMG_NEW_API and $IMG_NEW_WK; tagged $IMG_OLD_API and $IMG_OLD_WK from main-f455234"
(cd "$REPO" && git show main:docker-compose.yml) > "$RUN/compose.main.yml"
PORT=$(python -c "
import socket
while True:
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close()
    if p not in (8000, 5173, 5442): print(p); break")
BASE="http://127.0.0.1:$PORT/api/v1"

cat > "$RUN/override.new.yml" <<'YML'
services:
  db:
    ports: !reset []
    env_file: !override
      - ${G17_DIR}/.env.db
    cpus: 1
    mem_limit: 1g
  bootstrap:
    image: asistenteia-backend:g17a-new
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.roles
  migrate:
    image: asistenteia-backend:g17a-new
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.migrate
  cli:
    image: asistenteia-backend:g17a-new
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.cli
  backend:
    image: asistenteia-backend:g17a-new
    build: !reset null
    pull_policy: never
    ports: !override
      - "127.0.0.1:${G17_PORT}:8000"
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
    image: asistenteia-worker:g17a-new
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.worker
    volumes: !override []
    cpus: 2
    mem_limit: 2g
  frontend:
    profiles: ["g17a-excluded"]
YML
cat > "$RUN/override.old.yml" <<'YML'
services:
  db:
    ports: !reset []
    env_file: !override
      - ${G17_DIR}/.env.db
    cpus: 1
    mem_limit: 1g
  backend:
    image: asistenteia-backend:g17a-old
    build: !reset null
    pull_policy: never
    ports: !override
      - "127.0.0.1:${G17_PORT}:8000"
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
    image: asistenteia-worker:g17a-old
    build: !reset null
    pull_policy: never
    env_file: !override
      - ${G17_DIR}/.env.worker
    volumes: !override []
    cpus: 2
    mem_limit: 2g
  frontend:
    profiles: ["g17a-excluded"]
YML

# synthetic credentials and the OLD environment files (the shape of the development ones: the administrator everywhere)
PA=$(gen); PA2=$(gen); JWT=$(python -c "import secrets;print(secrets.token_urlsafe(40))")
UP1="Pw1-$(gen)"; UP2="Pw2-$(gen)"; TP1="Pt1-$(gen)"
SECRETS=("$PA" "$PA2" "$JWT" "$UP1" "$UP2" "$TP1")
printf 'POSTGRES_USER=asistente\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=asistenteia\n' "$PA" > "$ENVDIR/.env.db"
printf 'APP_ENV=development\nLOG_LEVEL=INFO\nDATABASE_URL=postgresql+psycopg://asistente:%s@db:5432/asistenteia\nCORS_ORIGINS=http://localhost:5173\nJWT_SECRET=%s\n' "$PA" "$JWT" > "$ENVDIR/.env"
sed -e "s#asistente_worker:CHANGE_ME@db:5432/asistenteia#asistente:$PA@db:5432/asistenteia#" "$REPO/backend/.env.worker.example" > "$ENVDIR/.env.worker"
[ "$(grep -v '^#' "$ENVDIR/.env.worker" | grep -c CHANGE_ME)" = 0 ] || { log "worker example placeholder"; exit 3; }
cp -r "$ENVDIR" "$RUN/env.original"

# =================================================================================== 1
log "=== 1 the replica of the development stack, OLD code and OLD files (everything as the administrator)"
run "compose up db (old spec)" dcx old up -d db
for _ in $(seq 1 60); do [ "$(docker inspect "$DBC" --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break; sleep 2; done
log "  db health: $(docker inspect "$DBC" --format '{{.State.Health.Status}}') | databases: $(psqla postgres 'select string_agg(datname, chr(44) order by datname) from pg_database')"
docker cp "$RUNW/backup.dump" "$DBC:/tmp/backup.dump"
run "restore the 0004 dump into asistenteia" docker exec "$DBC" sh -c 'pg_restore -U "$POSTGRES_USER" -d asistenteia --exit-on-error /tmp/backup.dump'
run "alembic upgrade 0005 as the administrator" docker run --rm --network "$NET" --label "$LABEL" --env-file "$ENVW/.env.db" -e "ADMIN_DB_URL=postgresql+psycopg://asistente:$PA@db:5432/asistenteia" --entrypoint python "$IMG_NEW_API" -c "import os; from alembic import command; from app.db_admin.migrate import alembic_config; command.upgrade(alembic_config(os.environ['ADMIN_DB_URL']), '0005')"
check "the replica database is at 0005 like the development database" 0005 "$(rev)"
run "compose up backend worker (old spec, old images)" dcx old up -d backend worker
for _ in $(seq 1 60); do curl -s -o /dev/null --max-time 2 "$BASE/health" && break; sleep 2; done
for _ in $(seq 1 100); do [ "$(docker inspect "$WK" --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break; sleep 3; done
check "old API answers" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health")"
check "old worker healthy" healthy "$(docker inspect "$WK" --format '{{.State.Health.Status}}')"
api POST /auth/register 201 "" "{\"name\":\"Old Student\",\"email\":\"g17b-old@example.com\",\"password\":\"$UP1\"}"
check "a student written by the OLD stack exists" 1 "$(sql "select count(*) from users where email='g17b-old@example.com'")"
log "  sessions by user in the old stack: $(sql "select string_agg(usename||'='||n, ' ') from (select usename, count(*) n from pg_stat_activity where datname='asistenteia' group by 1) s")"
S0="$RUN/snap0"; mkdir -p "$S0"
snap_db "$DBC" asistenteia "$S0/db.txt"; snap_db "$DBC" asistenteia_test "$S0/test.txt"; snap_cluster "$DBC" "$S0/cluster.txt"
log "  S0 (state of the replica before 17B): $(wc -l < "$S0/db.txt") + $(wc -l < "$S0/test.txt") + $(wc -l < "$S0/cluster.txt") lines; revision $(grep '^revision|' "$S0/db.txt"); rows: $(grep '^rows|' "$S0/db.txt" | tr '\n' ' ')"

# =================================================================================== 2
log "=== 2 step 17B.1 preflight with the read-only tool, the backup procedure and the proof that it restores"
run "preflight_readonly.sh" bash "$TOOLS/preflight_readonly.sh" "$DBC" asistenteia "$RUN/preflight-before"
TAILN=10 run "show identity" cat "$RUN/preflight-before/identity.txt"
check "preflight snapshot of the database equals S0 (the tool is read only and complete)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$S0/db.txt" "$RUN/preflight-before/snapshot-db.txt" | grep -o IDENTICAL)"
check "preflight snapshot of the cluster equals S0" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$S0/cluster.txt" "$RUN/preflight-before/snapshot-cluster.txt" | grep -o IDENTICAL)"
check "no open transaction, no idle-in-transaction session, no prepared transaction" "0|0|0" "$(grep -E '^(open_transactions_older_than_1_min|idle_in_transaction|prepared_transactions)\|' "$RUN/preflight-before/activity.txt" | cut -d'|' -f2 | paste -sd'|')"

log "  backup procedure (the commands planned for 17B.1, run on the replica)"
T0=$(ms)
run "pg_dump inside the container" docker exec "$DBC" sh -c 'pg_dump -U "$POSTGRES_USER" -d asistenteia -Fc -f /tmp/asistenteia_pre_17b.dump'
INSIDE="$(docker exec "$DBC" sha256sum /tmp/asistenteia_pre_17b.dump | cut -d' ' -f1)"
run "pg_restore --list inside" docker exec "$DBC" sh -c 'pg_restore --list /tmp/asistenteia_pre_17b.dump | wc -l'
docker cp "$DBC:/tmp/asistenteia_pre_17b.dump" "$RUNW/durable/asistenteia_pre_17b.dump"
OUTSIDE="$(sha256sum "$RUN/durable/asistenteia_pre_17b.dump" | cut -d' ' -f1)"
check "the copy outside the container has the same sha256 as inside" "$INSIDE" "$OUTSIDE"
cp "$RUN/durable/asistenteia_pre_17b.dump" "$RUN/durable/second-copy.dump"
check "the second copy has the same sha256" "$INSIDE" "$(sha256sum "$RUN/durable/second-copy.dump" | cut -d' ' -f1)"
log "  backup taken and verified in $(( $(ms) - T0 )) ms"
docker network create --label "$BKLABEL" "$BKNET" > /dev/null
docker run -d --name "$BKC" --label "$BKLABEL" --network "$BKNET" -m 1g --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PA2" -e POSTGRES_DB=postgres "$IMG_PG" > /dev/null
for _ in $(seq 1 60); do docker exec "$BKC" pg_isready -h 127.0.0.1 -U asistente > /dev/null 2>&1 && break; sleep 1; done; sleep 2
docker cp "$RUNW/durable/second-copy.dump" "$BKC:/tmp/restore.dump"
docker exec "$BKC" createdb -U asistente asistenteia
T0=$(ms); run "pg_restore into the disposable cluster" docker exec "$BKC" pg_restore -U asistente -d asistenteia --exit-on-error /tmp/restore.dump
log "  restore took $(( $(ms) - T0 )) ms"
snap_db "$BKC" asistenteia "$RUN/restored-db.txt"
check "the restored copy is identical to the source (catalog, revision, owners, ACLs, grants, constraints, defaults, row counts)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$S0/db.txt" "$RUN/restored-db.txt" | grep -o IDENTICAL)"
docker rm -f "$BKC" > /dev/null; docker network rm "$BKNET" > /dev/null

# =================================================================================== 3
log "=== 3 step 17B.2: stop the services, prepare the files with the tool, bootstrap, adopt, migrate, verify, switch"
T_FWD=$(ms)
run "compose stop backend worker (old spec)" dcx old stop backend worker
TAILN=3 run "prepare_env_files.py --dry-run" python "$TOOLSW/prepare_env_files.py" "$ENVW" --dry-run
check "dry run writes nothing" 0 "$(ls -a "$ENVDIR" | grep -c -E 'pre-17b|env.roles|env.migrate|env.cli')"
TAILN=4 run "prepare_env_files.py" python "$TOOLSW/prepare_env_files.py" "$ENVW"
check "the tool succeeded" 0 "$RC"
check "the tool printed no value (no password, no URL)" 0 "$(echo "$OUTP" | grep -c -E "postgresql|$PA|@db")"
TAILN=2 run "prepare_env_files.py again must refuse" python "$TOOLSW/prepare_env_files.py" "$ENVW"
check "a second run refuses (nothing is overwritten)" 1 "$RC"
check "the new files exist and the backups too" 6 "$(ls -a "$ENVDIR" | grep -c -E '^\.env\.(roles|migrate|cli)$|pre-17b$')"
check "only the user and password of DATABASE_URL changed in .env (the other lines are byte for byte)" 0 "$(diff <(grep -v '^DATABASE_URL=' "$ENVDIR/.env.pre-17b") <(grep -v '^DATABASE_URL=' "$ENVDIR/.env") | wc -l)"
check "API file now names the application role, worker file the worker role" "asistente_app|asistente_worker" "$(grep '^DATABASE_URL=' "$ENVDIR/.env" | sed -E 's#.*//([^:]*):.*#\1#')|$(grep '^DATABASE_URL=' "$ENVDIR/.env.worker" | sed -E 's#.*//([^:]*):.*#\1#')"
cat > "$RUN/collect.py" <<'PY'
import re, sys
from urllib.parse import urlsplit, unquote
for line in open(sys.argv[1], encoding="utf-8"):
    m = re.match(r"^[A-Z_]*(URL|PASSWORD|SECRET)=(.*)$", line.strip())
    if not m:
        continue
    v = m.group(2)
    if "://" in v:
        p = urlsplit(v).password
        if p:
            print(unquote(p))
    elif len(v) >= 12:
        print(v)
PY
for f in .env.roles .env.migrate .env.cli .env .env.worker; do
  while IFS= read -r v; do [ -n "$v" ] && SECRETS+=("$v"); done < <(python "$RUNW/collect.py" "$ENVDIR/$f")
done

APPIMG="$IMG_NEW_API"
TAILN=10 run "bootstrap (compose one-shot, first run)" dcx new run --rm --no-deps bootstrap
check "the first bootstrap reports the drift of the old tables with exit 1" 1 "$RC"
TAILN=10 run "db-adopt dry run" dcx new run --rm --no-deps bootstrap python -m app.cli db-adopt --database asistenteia
check "the dry run exits 0" 0 "$RC"
T0=$(ms); TAILN=4 run "db-adopt --apply" dcx new run --rm --no-deps bootstrap python -m app.cli db-adopt --apply --database asistenteia; A_MS=$STEP_MS
check "adoption applied" 0 "$RC"
TAILN=6 run "migrate (compose one-shot: db-migrate)" dcx new run --rm --no-deps migrate
check "migration 0006 and grants" 0 "$RC"
check "revision 0006 and users.role default" "0006|'student'::user_role" "$(rev)|$(sql "select pg_get_expr(d.adbin,d.adrelid) from pg_attrdef d join pg_attribute a on a.attrelid=d.adrelid and a.attnum=d.adnum where d.adrelid='public.users'::regclass and a.attname='role'")"
TAILN=4 run "db-verify" appx .env.migrate .env.roles -- db-verify
check "db-verify has no findings" 0 "$RC"
T_SWITCH=$(ms)
TAILN=6 run "up -d --no-deps --force-recreate backend worker (new spec)" dcx new up -d --no-deps --force-recreate backend worker
for _ in $(seq 1 60); do curl -s -o /dev/null --max-time 2 "$BASE/health" && break; sleep 2; done
for _ in $(seq 1 100); do [ "$(docker inspect "$WK" --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break; sleep 3; done
log "  services back in $(( $(ms) - T_SWITCH )) ms after the switch; forward procedure (without the backup) $(( $(ms) - T_FWD )) ms"
check "new API answers" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health")"
check "new worker healthy" healthy "$(docker inspect "$WK" --format '{{.State.Health.Status}}')"
log "  who is who (SELECT current_user per session): $(sql "select string_agg(usename||'='||n, ' ') from (select usename, count(*) n from pg_stat_activity where datname='asistenteia' and backend_type='client backend' and usename is not null group by 1 order by 1) s")"
check "the application and the worker connect as their own roles, nobody else (the session of this very check excluded)" "asistente_app,asistente_worker" "$(sql "select string_agg(distinct usename, ',') from pg_stat_activity where datname='asistenteia' and backend_type='client backend' and usename like 'asistente%' and pid<>pg_backend_pid() and application_name not like 'psql%'")"
check "the new API process refuses the administrator URL (the code of 15.2)" 1 "$(docker run --rm --network "$NET" --env-file "$ENVW/.env" -e "DATABASE_URL=postgresql+psycopg://asistente:$PA@db:5432/asistenteia" --entrypoint python "$IMG_NEW_API" -c 'from app.main import app_factory; app_factory()' 2>&1 | grep -c 'refusing to start')"

# =================================================================================== 4
log "=== 4 step 17B.3 functional validation with synthetic data under the roles"
api POST /auth/login 200 "" "{\"email\":\"g17b-old@example.com\",\"password\":\"$UP1\"}"; T_OLD=$(field access_token); SECRETS+=("$T_OLD")
api GET /users/me 200 "$T_OLD"
api POST /auth/register 201 "" "{\"name\":\"New Student\",\"email\":\"g17b-new@example.com\",\"password\":\"$UP2\"}"
check "the new student is a student" student "$(sql "select role::text from users where email='g17b-new@example.com'")"
printf '%s\n' "$TP1" | dcx new run --rm -T --no-deps cli create-teacher --email g17b-teacher@example.com --name "Teacher" --password-stdin > /dev/null 2>&1
check "teacher created by the CLI role" teacher "$(sql "select role::text from users where email='g17b-teacher@example.com'")"
api POST /auth/login 200 "" "{\"email\":\"g17b-teacher@example.com\",\"password\":\"$TP1\"}"; T_T=$(field access_token); SECRETS+=("$T_T")
api POST /subjects 403 "$T_OLD" '{"name":"Student subject"}'
api POST /subjects 201 "$T_T" '{"name":"G17B course"}'; SUBJ=$(field id)
api POST "/subjects/$SUBJ/enrollments" 201 "$T_T" '{"student_email":"g17b-old@example.com"}'
printf 'Derivatives measure the rate of change of a function.\n' > "$RUN/notes.txt"
upload "/subjects/$SUBJ/documents" 202 "$T_T" "$RUN/notes.txt" notes.txt text/plain; D1=$(field id)
check "the worker role processed the upload" ready "$(wait_doc "$D1")"
api GET "/subjects/$SUBJ" 200 "$T_OLD"
check "API role cannot create a teacher" "permission denied" "$(sql_as asistente_app "INSERT INTO users (name,email,password_hash,role) VALUES ('x','forged@example.com','h','teacher')" | grep -o 'permission denied' | head -1)"
check "worker role cannot read users" "permission denied" "$(sql_as asistente_worker "SELECT email FROM users" | grep -o 'permission denied' | head -1)"
TAILN=3 run "db-verify after the functional run" appx .env.migrate .env.roles -- db-verify
check "no drift after the functional run" 0 "$RC"

# =================================================================================== 5
log "=== 5 rotation of the administrator password (TD-038 and the incident of 2026-11-13)"
NEWADMIN=$(gen); SECRETS+=("$NEWADMIN")
T0=$(ms)
printf "ALTER ROLE asistente PASSWORD '%s';\n" "$NEWADMIN" | docker exec -i "$DBC" sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -q -f -' > /dev/null 2>&1
cat > "$RUN/rotate.py" <<'PY'
import sys, pathlib
folder, old, new = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
for name in (".env.db", ".env.roles"):
    p = folder / name
    p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8", newline="")
PY
python "$RUNW/rotate.py" "$ENVDIR" "$PA" "$NEWADMIN"
SECRETS+=("$NEWADMIN")
run "recreate the db container only (new environment)" dcx new up -d --no-deps --force-recreate db
for _ in $(seq 1 60); do [ "$(docker inspect "$DBC" --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break; sleep 2; done
log "  rotation including the recreation of the database container took $(( $(ms) - T0 )) ms (the services were running and reconnected)"
check "the OLD password is refused over TCP" 1 "$(docker run --rm --network "$NET" -e "PGPASSWORD=$PA" "$IMG_PG" psql -h db -U asistente -d postgres -Atc 'select 1' 2>&1 | grep -c 'authentication failed')"
check "the NEW password is accepted over TCP" 1 "$(docker run --rm --network "$NET" -e "PGPASSWORD=$NEWADMIN" "$IMG_PG" psql -h db -U asistente -d postgres -Atc 'select 1' 2>&1)"
check "the API survived the recreation of the database (pool reconnects)" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health")"
api POST /auth/login 200 "" "{\"email\":\"g17b-old@example.com\",\"password\":\"$UP1\"}"
TAILN=3 run "bootstrap again with the new administrator password" dcx new run --rm --no-deps bootstrap
check "idempotent bootstrap after the rotation (exit 0)" 0 "$RC"
check "the old password is not in any file of the replica environment any more" 0 "$(grep -l "$PA" "$ENVDIR"/.env "$ENVDIR"/.env.db "$ENVDIR"/.env.worker "$ENVDIR"/.env.roles "$ENVDIR"/.env.migrate "$ENVDIR"/.env.cli 2>/dev/null | wc -l)"
check "the .pre-17b copies still hold it: they must be destroyed after the acceptance (documented step)" 3 "$(grep -l "$PA" "$ENVDIR"/.env.pre-17b "$ENVDIR"/.env.db.pre-17b "$ENVDIR"/.env.worker.pre-17b 2>/dev/null | wc -l)"
snap_db "$DBC" asistenteia "$RUN/S_forward_db.txt"; snap_cluster "$DBC" "$RUN/S_forward_cluster.txt"

# =================================================================================== 6
log "=== 6 THE FULL ROLLBACK (scenario: everything done, data written under the roles, administrator password rotated)"
T_RB=$(ms)
TAILN=2 run "R1 stop and remove the new services" dcx new rm -sf backend worker
TAILN=4 run "R2 db-migrate --downgrade 0005" appx .env.migrate -- db-migrate --downgrade 0005
check "downgraded" 0005 "$(rev)"
TAILN=5 run "R3 db-adopt --rollback --remove-roles --apply" appx .env.roles -- db-adopt --rollback --remove-roles --apply --database asistenteia
check "ownership returned and roles removed (exit 0)" 0 "$RC"
check "only the administrator is left" "asistente" "$(sqlc "$DBC" postgres "select string_agg(rolname, ',' order by rolname) from pg_roles where rolname !~ '^pg_'")"
log "  database ACL of asistenteia after the rollback of the roles (PUBLIC closed, not restored yet): $(sqlc "$DBC" postgres "select coalesce(datacl::text,'(default)') from pg_database where datname='asistenteia'")"
TAILN=3 run "R4a restore_public_cluster.sql" bash -c "docker exec -i $DBC sh -c 'psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -f -' < '$TOOLS/restore_public_cluster.sql'"
TAILN=3 run "R4b restore_public_schema.sql" bash -c "docker exec -i $DBC sh -c 'psql -U \"\$POSTGRES_USER\" -d asistenteia -v ON_ERROR_STOP=1 -f -' < '$TOOLS/restore_public_schema.sql'"
check "after the restore PUBLIC can connect again (explicit ACL equivalent to the default one)" 1 "$(sqlc "$DBC" postgres "select count(*) from pg_database where datname='asistenteia' and datacl::text like '%,=Tc/asistente%' or datname='asistenteia' and datacl::text like '{=Tc/asistente%'")"
TAILN=4 run "R5 restore the old files (administrator URL with the CURRENT administrator password)" python "$TOOLSW/prepare_env_files.py" "$ENVW" --rollback
check "the rollback of the files succeeded" 0 "$RC"
check "the old API file names the administrator again" "asistente" "$(grep '^DATABASE_URL=' "$ENVDIR/.env" | sed -E 's#.*//([^:]*):.*#\1#')"
check "the restored files carry the rotated password, not the exposed one" "0" "$(grep -l "$PA" "$ENVDIR"/.env "$ENVDIR"/.env.worker 2>/dev/null | wc -l)"
check "the new roles files are gone from the active names" 0 "$(ls -a "$ENVDIR" | grep -c -E '^\.env\.(roles|migrate|cli)$')"
T_UP=$(ms)
TAILN=4 run "R6 up -d --no-deps backend worker with the OLD compose file, OLD images and OLD code" dcx old up -d --no-deps backend worker
for _ in $(seq 1 60); do curl -s -o /dev/null --max-time 2 "$BASE/health" && break; sleep 2; done
for _ in $(seq 1 100); do [ "$(docker inspect "$WK" --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && break; sleep 3; done
log "  services available again $(( $(ms) - T_UP )) ms after starting them; the whole rollback took $(( $(ms) - T_RB )) ms"
check "API answers (old image)" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health")"
check "worker healthy (old image)" healthy "$(docker inspect "$WK" --format '{{.State.Health.Status}}')"
check "the services run the OLD images" "$IMG_OLD_API|$IMG_OLD_WK" "$(docker inspect "$API" --format '{{.Config.Image}}')|$(docker inspect "$WK" --format '{{.Config.Image}}')"
check "the services connect as the administrator again" "asistente" "$(sql "select string_agg(distinct usename, ',') from pg_stat_activity where datname='asistenteia' and backend_type='client backend' and usename is not null and pid<>pg_backend_pid() and usename like 'asistente%'")"
api POST /auth/login 200 "" "{\"email\":\"g17b-old@example.com\",\"password\":\"$UP1\"}"; T_OLD=$(field access_token); SECRETS+=("$T_OLD")
api GET /users/me 200 "$T_OLD"
api POST /auth/register 201 "" "{\"name\":\"After Rollback\",\"email\":\"g17b-after@example.com\",\"password\":\"$UP2\"}"
api POST /auth/login 200 "" "{\"email\":\"g17b-teacher@example.com\",\"password\":\"$TP1\"}"; T_T=$(field access_token); SECRETS+=("$T_T")
api GET "/subjects/$SUBJ/documents" 200 "$T_T"
check "the data written under the roles survived the rollback" "4|1|1" "$(sql "select count(*) from users where email like 'g17b-%'")|$(sql "select count(*) from subjects")|$(sql "select count(*) from documents")"
upload "/subjects/$SUBJ/documents" 202 "$T_T" "$RUN/notes.txt" notes.txt text/plain; D2=$(field id)
check "the OLD worker processes an upload on the rolled-back database" ready "$(wait_doc "$D2")"
log "=== state after the rollback against S0 (rows are ignored here, the services wrote some)"
snap_db "$DBC" asistenteia "$RUN/S_after_db.txt"; snap_db "$DBC" asistenteia_test "$RUN/S_after_test.txt"; snap_cluster "$DBC" "$RUN/S_after_cluster.txt"
bash "$TOOLS/compare_snapshots.sh" "$S0/db.txt" "$RUN/S_after_db.txt" '^rows\|' > "$RUN/diff_db.txt" 2>&1; log "  database asistenteia vs S0: $(grep -c '^[<>]' "$RUN/diff_db.txt") differing line(s)"; sed 's/^/      | /' "$RUN/diff_db.txt" | cut -c1-230 | head -12 | tee -a "$OUT" > /dev/null
bash "$TOOLS/compare_snapshots.sh" "$S0/test.txt" "$RUN/S_after_test.txt" > "$RUN/diff_test.txt" 2>&1; log "  database asistenteia_test vs S0: $(grep -c '^[<>]' "$RUN/diff_test.txt") differing line(s)"; sed 's/^/      | /' "$RUN/diff_test.txt" | cut -c1-230 | head -6 | tee -a "$OUT" > /dev/null
bash "$TOOLS/compare_snapshots.sh" "$S0/cluster.txt" "$RUN/S_after_cluster.txt" > "$RUN/diff_cluster.txt" 2>&1; log "  cluster vs S0: $(grep -c '^[<>]' "$RUN/diff_cluster.txt") differing line(s)"; sed 's/^/      | /' "$RUN/diff_cluster.txt" | cut -c1-260 | head -12 | tee -a "$OUT" > /dev/null
cp "$RUN/diff_db.txt" "$HERE/g17a-diff-db.txt"; cp "$RUN/diff_test.txt" "$HERE/g17a-diff-test.txt"; cp "$RUN/diff_cluster.txt" "$HERE/g17a-diff-cluster.txt"

# =================================================================================== 7
log "=== 7 cleanup of the synthetic data and the last resort: recovery from the dump"
TAILN=2 run "stop the old services" dcx old stop backend worker
sql "delete from document_chunks; delete from ingestion_jobs; delete from documents; delete from enrollments; delete from subjects; delete from users where email like 'g17b-%' and email <> 'g17b-old@example.com';" > /dev/null
check "after the cleanup the rows are those of S0" "$(grep '^rows|' "$S0/db.txt" | sort | tr '\n' ' ')" "$(snap_db "$DBC" asistenteia "$RUN/S_clean.txt"; grep '^rows|' "$RUN/S_clean.txt" | sort | tr '\n' ' ')"
check "after the cleanup only the representation of the default ACLs differs from S0 (database asistenteia, strict ownership)" "IDENTICAL" "$(snap_db "$DBC" asistenteia "$RUN/S_clean2.txt"; NORMALIZE=1 bash "$TOOLS/compare_snapshots.sh" "$S0/db.txt" "$RUN/S_clean2.txt" | grep -o IDENTICAL)"
check "asistenteia_test: only the ACL representation differs" "IDENTICAL" "$(NORMALIZE=1 bash "$TOOLS/compare_snapshots.sh" "$S0/test.txt" "$RUN/S_after_test.txt" | grep -o IDENTICAL)"
check "the cluster: roles, memberships, settings and database owners identical, only the ACL representation differs" "IDENTICAL" "$(NORMALIZE=1 bash "$TOOLS/compare_snapshots.sh" "$S0/cluster.txt" "$RUN/S_after_cluster.txt" | grep -o IDENTICAL)"
T0=$(ms)
sqlc "$DBC" postgres "DROP DATABASE asistenteia WITH (FORCE)" > /dev/null
docker exec "$DBC" sh -c 'createdb -U "$POSTGRES_USER" asistenteia'
docker cp "$RUNW/durable/asistenteia_pre_17b.dump" "$DBC:/tmp/recover.dump"
run "pg_restore from the verified dump over a dropped database" docker exec "$DBC" sh -c 'pg_restore -U "$POSTGRES_USER" -d asistenteia --exit-on-error /tmp/recover.dump'
log "  recovery from the dump took $(( $(ms) - T0 )) ms"
snap_db "$DBC" asistenteia "$RUN/S_recovered.txt"
check "the recovered database is identical to S0 (the whole catalog, ACLs, owners, constraints, defaults and rows)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$S0/db.txt" "$RUN/S_recovered.txt" | grep -o IDENTICAL)"

log "=== result: $PASS checks passed, $FAIL failed (of $N)"
[ "$FAIL" = "0" ]
