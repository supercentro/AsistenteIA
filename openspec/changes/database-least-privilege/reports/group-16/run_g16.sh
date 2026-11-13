#!/usr/bin/env bash
# Group 16: rehearsal of the whole adoption procedure on a RESTORED COPY of the real backup, in a
# completely DISPOSABLE PostgreSQL 15.19 + pgvector 0.8.7 (tasks 16.1 to 16.3).
#
# usage: G16_BACKUP=<dump> G16_RUN_DIR=<empty directory OUTSIDE the repository> bash run_g16.sh
#
# - The backup is only READ (hash before and after); a copy is restored. Own network, own tmpfs data
#   volume, containers named g16*, no published database port, no real credential, synthetic data.
# - The real stack (asistenteia-db-1, asistenteia-worker-1) is never contacted: other networks, other
#   volumes, other credentials. The disposable API is published on 127.0.0.1 at a free temporary port.
# - Refuses to start with less than 8 GB of free memory.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
OUT="$HERE/g16-output.txt"
RUN="${G16_RUN_DIR:?set G16_RUN_DIR to an empty directory OUTSIDE the repository}"
BACKUP="${G16_BACKUP:?set G16_BACKUP to the dump to restore}"
mkdir -p "$RUN"
[ -z "$(ls -A "$RUN" 2>/dev/null)" ] || { echo "G16_RUN_DIR must be an empty directory"; exit 2; }
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "G16_RUN_DIR must be outside the repository"; exit 2;; esac
RUNW="$(cd "$RUN" && pwd -W)"
SUF=$$
NET="g16net$SUF"; PG="g16pg$SUF"; API="g16api$SUF"; WK="g16wk$SUF"; LABEL="purpose=g16-rehearsal"
IMG_PG="pgvector/pgvector:0.8.7-pg15"
IMG_API="asistenteia-backend:g16-branch"; IMG_WK="asistenteia-worker:g16-branch"
DB=asistenteia; DB2=asistenteia_copy2
: > "$OUT"

gen() { python -c "import secrets;print(secrets.token_hex(12))"; }
SECRETS=()
mask() { local s; s="$(cat)"; for v in "${SECRETS[@]}"; do [ -n "$v" ] && s="${s//$v/***}"; done; printf '%s\n' "$s"; }
log() { echo "$@" | mask | tee -a "$OUT"; }
ms() { echo $(( $(date +%s%N) / 1000000 )); }
psqla() { docker exec -i "$PG" psql -U asistente -d "$1" -At -v ON_ERROR_STOP=1 -c "$2" 2>&1; }
sql() { psqla "$DB" "$1"; }
sql_as() { docker exec "$PG" psql -U "$1" -d "${3:-$DB}" -At -c "$2" 2>&1 | head -3 | tr '\n' ' '; }
appx() { local envs=(); while [ "$1" != "--" ]; do envs+=(--env-file "$RUNW/$1"); shift; done; shift
  docker run --rm -i --network "$NET" --label "$LABEL" -m 768m --cpus 1 "${envs[@]}" --entrypoint python "$IMG_API" -m app.cli "$@"; }
cli_run() { appx cli.env -- "$@"; }
envnames() { docker inspect "$1" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | cut -d= -f1 | grep -E '^(POSTGRES_|ADMIN_|DB_|MIGRATION_|CLI_|DATABASE_URL|JWT_|CORS|EMBEDDER|APP_ENV)' | sort | tr '\n' ' '; }
run() { # name command...  -> RC, OUTP; prints the duration and the tail of the (masked) output
  local name="$1"; shift; local a; a=$(ms)
  OUTP="$("$@" 2>&1)"; RC=$?
  log "  [$name] rc=$RC ($(( $(ms) - a )) ms)"
  if [ -n "$OUTP" ]; then printf '%s\n' "$OUTP" | tail -n "${TAILN:-8}" | cut -c1-230 | sed 's/^/      | /' | mask | tee -a "$OUT" > /dev/null; fi
}
owners() { psqla "$1" "select string_agg(tablename||'='||tableowner, ',' order by tablename) from pg_tables where schemaname='public'"; }
owner_set() { psqla "$1" "select coalesce(string_agg(distinct tableowner, ','),'') from pg_tables where schemaname='public'"; }
type_owner_set() { psqla "$1" "select coalesce(string_agg(distinct typowner::regrole::text, ','),'') from pg_type where typnamespace='public'::regnamespace and typtype='e'"; }
types_owners() { psqla "$1" "select coalesce(string_agg(typname||'='||typowner::regrole::text, ',' order by typname),'') from pg_type where typnamespace='public'::regnamespace and typtype='e'"; }
counts() { psqla "$1" "select 'users='||(select count(*) from users)||',subjects='||(select count(*) from subjects)||',enrollments='||(select count(*) from enrollments)||',documents='||(select count(*) from documents)||',chunks='||(select count(*) from document_chunks)||',jobs='||(select count(*) from ingestion_jobs)"; }
fp() { psqla "$1" "select md5(coalesce((select string_agg(c.relname||'.'||a.attname||':'||format_type(a.atttypid,a.atttypmod)||':'||a.attnotnull, ',' order by c.relname, a.attnum) from pg_class c join pg_attribute a on a.attrelid=c.oid where c.relnamespace='public'::regnamespace and c.relkind='r' and a.attnum>0 and not a.attisdropped),'')||coalesce((select string_agg(indexdef, ',' order by indexname) from pg_indexes where schemaname='public'),''))"; }
rev() { psqla "$1" "select version_num from alembic_version"; }
roles_now() { psqla postgres "select coalesce(string_agg(rolname||CASE WHEN rolsuper THEN '(superuser)' ELSE '' END, ',' order by rolname),'') from pg_roles where rolname !~ '^pg_'"; }
datacls() { psqla postgres "select string_agg(datname||'='||coalesce(datacl::text,'(default)'), ' ; ' order by datname) from pg_database"; }
default_of_role() { psqla "$1" "select coalesce((select pg_get_expr(d.adbin,d.adrelid) from pg_attrdef d join pg_attribute a on a.attrelid=d.adrelid and a.attnum=d.adnum where d.adrelid='public.users'::regclass and a.attname='role'),'(none)')"; }
state() { echo "rev=$(rev "$1");owners=$(owners "$1");types=$(types_owners "$1");counts=$(counts "$1");fp=$(fp "$1")"; }

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
  log "--- identity of every resource of this rehearsal, before removal"
  log "containers: $(docker ps -a --filter label=$LABEL --format '{{.Names}}' | tr '\n' ' ')"
  log "networks:   $(docker network ls --filter label=$LABEL --format '{{.Name}}' | tr '\n' ' ')"
  log "names outside the g16 scheme among them (must be empty): $(docker ps -a --filter label=$LABEL --format '{{.Names}}' | grep -v "^g16" | tr '\n' ' ')"
  docker rm -f "$API" "$WK" "$PG" > /dev/null 2>&1
  docker network rm "$NET" > /dev/null 2>&1
  log "after removal: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l) volumes left (tmpfs, none created)=$(docker volume ls --filter label=$LABEL -q | wc -l)"
  docker rmi "$IMG_API" "$IMG_WK" > /dev/null 2>&1
  log "temporary image tags left: $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c 'g16-branch')"
  AFTER_OTHER="$(docker ps --format '{{.Names}}' | grep -v '^g16' | sort | tr '\n' ';')"
  log "other containers (the real stack and other projects) before and after identical: $([ "$BEFORE_OTHER" = "$AFTER_OTHER" ] && echo yes || echo NO)"
  log "original backup untouched: sha $( [ "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "$SHA_BEFORE" ] && echo equal || echo DIFFERENT ), size/mtime $( [ "$(stat -c '%s %Y' "$BACKUP")" = "$STAT_BEFORE" ] && echo equal || echo DIFFERENT )"
  rm -rf "$RUN"/*.env "$RUN"/body.json "$RUN"/*.txt "$RUN"/*.pdf "$RUN"/Dockerfile.worker "$RUN"/backup.dump
}
trap 'teardown' EXIT

# =============================================================================================== 0
log "=== 0 preflight $(date -u +%FT%TZ)"
FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
log "free host RAM before: $FREE GB (the rehearsal needs 8)"
python -c "import sys; sys.exit(0 if float('$FREE') >= 8 else 1)" || { log "RAM below 8 GB: stop"; trap - EXIT; exit 4; }
BEFORE_OTHER="$(docker ps --format '{{.Names}}' | sort | tr '\n' ';')"
log "repo HEAD: $(cd "$REPO" && git rev-parse --short HEAD)"

log "=== 16.1a the backup (read only)"
SHA_BEFORE="$(sha256sum "$BACKUP" | cut -d' ' -f1)"; STAT_BEFORE="$(stat -c '%s %Y' "$BACKUP")"
SHA_FILE="$(cut -d' ' -f1 "$BACKUP.sha256")"
MANIFEST_SHA="$(grep -E '^sha256:' "$BACKUP.manifest.txt" | awk '{print $2}')"
check "sha256 of the dump equals the recorded .sha256 file" "$SHA_FILE" "$SHA_BEFORE"
check "sha256 of the dump equals the manifest" "$MANIFEST_SHA" "$SHA_BEFORE"
log "    manifest: $(grep -E '^(database|format|rows|created)' "$BACKUP.manifest.txt" | tr '\n' ';' | cut -c1-330)"
if [ -n "${G16_BACKUP_COPY:-}" ]; then check "the second copy has the same sha256" "$SHA_BEFORE" "$(sha256sum "$G16_BACKUP_COPY" | cut -d' ' -f1)"; fi
cp "$BACKUP" "$RUN/backup.dump"
check "the working copy has the same sha256 (the original is never written)" "$SHA_BEFORE" "$(sha256sum "$RUN/backup.dump" | cut -d' ' -f1)"

log "=== images (the API from this branch; the worker = main's worker image with this branch's code)"
CTX="$(cd "$REPO/backend" && pwd -W)"
docker build -q --target api -t "$IMG_API" "$CTX" > /dev/null || { log "api image build FAILED"; exit 5; }
printf 'FROM asistenteia-worker:main-f455234\nUSER root\nCOPY app /app/app\nUSER appuser\n' > "$RUN/Dockerfile.worker"
docker build -q -f "$RUNW/Dockerfile.worker" -t "$IMG_WK" "$CTX" > /dev/null || { log "worker image build FAILED"; exit 5; }
log "images built: $IMG_API, $IMG_WK"

PA=$(gen); PM=$(gen); PP=$(gen); PW=$(gen); PC=$(gen); JWT=$(python -c "import secrets;print(secrets.token_urlsafe(40))")
UP1="Pw1-$(gen)"; UP2="Pw2-$(gen)"; TP1="Pt1-$(gen)"; TP2="Pt2-$(gen)"
SECRETS=("$PA" "$PM" "$PP" "$PW" "$PC" "$JWT" "$UP1" "$UP2" "$TP1" "$TP2")
U="postgresql+psycopg"
printf 'ADMIN_DATABASE_URL=%s://asistente:%s@db:5432/postgres\nDB_MIGRATOR_PASSWORD=%s\nDB_APP_PASSWORD=%s\nDB_WORKER_PASSWORD=%s\nDB_CLI_PASSWORD=%s\n' "$U" "$PA" "$PM" "$PP" "$PW" "$PC" > "$RUN/roles.env"
printf 'MIGRATION_DATABASE_URL=%s://asistente_migrator:%s@db:5432/%s\n' "$U" "$PM" "$DB" > "$RUN/migrate.env"
printf 'MIGRATION_DATABASE_URL=%s://asistente_migrator:%s@db:5432/%s\n' "$U" "$PM" "$DB2" > "$RUN/migrate2.env"
printf 'MIGRATION_DATABASE_URL=%s://asistente:%s@db:5432/%s\n' "$U" "$PA" "$DB" > "$RUN/wrong-admin.env"
printf 'MIGRATION_DATABASE_URL=%s://asistente_app:%s@db:5432/%s\n' "$U" "$PP" "$DB" > "$RUN/wrong-app.env"
printf 'ADMIN_DB_URL=%s://asistente:%s@db:5432/%s\n' "$U" "$PA" "$DB" > "$RUN/admin-main.env"
printf 'ADMIN_DB_URL=%s://asistente:%s@db:5432/%s\n' "$U" "$PA" "$DB2" > "$RUN/admin-copy2.env"
printf 'DATABASE_URL=%s://asistente_app:%s@db:5432/%s\nAPP_ENV=development\nLOG_LEVEL=INFO\nJWT_SECRET=%s\nCORS_ORIGINS=http://localhost:5173\n' "$U" "$PP" "$DB" "$JWT" > "$RUN/api.env"
printf 'CLI_DATABASE_URL=%s://asistente_cli:%s@db:5432/%s\n' "$U" "$PC" "$DB" > "$RUN/cli.env"
sed -e "s#asistente_worker:CHANGE_ME@db:5432/asistenteia#asistente_worker:$PW@db:5432/$DB#" "$REPO/backend/.env.worker.example" > "$RUN/worker.env"
[ "$(grep -v '^#' "$RUN/worker.env" | grep -c 'CHANGE_ME')" = "0" ] || { log "worker example still holds a placeholder"; exit 3; }
PORT=$(python -c "
import socket
while True:
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close()
    if p not in (8000, 5173, 5442): print(p); break")

# =============================================================================================== 1
log "=== 16.1b the disposable cluster"
docker network create --label "$LABEL" "$NET" > /dev/null
docker run -d --name "$PG" --label "$LABEL" --network "$NET" --network-alias db --cpus 1 -m 1g --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PA" -e POSTGRES_DB=postgres "$IMG_PG" -c max_prepared_transactions=5 > /dev/null
for _ in $(seq 1 60); do docker exec "$PG" pg_isready -h 127.0.0.1 -U asistente -d postgres > /dev/null 2>&1 && break; sleep 1; done
sleep 2
log "server: $(psqla postgres 'select version()' | cut -c1-70)"
log "pgvector available: $(psqla postgres "select default_version from pg_available_extensions where name='vector'")"
log "identity: container $PG, network $NET (only member network: $(docker inspect "$PG" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'))"
log "published ports: [$(docker port "$PG" | tr '\n' ' ')] | mounts: $(docker inspect "$PG" --format '{{len .Mounts}}') (data on tmpfs)"
DEV_NETS="$(docker inspect asistenteia-db-1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null)"
check "the cluster shares no network with the development stack" "0" "$(for n in $DEV_NETS; do docker network inspect "$n" --format '{{range .Containers}}{{.Name}} {{end}}' | tr ' ' '\n' | grep -c "^$PG$"; done | paste -sd+ | python -c 'import sys;print(eval(sys.stdin.read() or "0"))')"
DEV_VOLS="$(docker inspect asistenteia-db-1 --format '{{range .Mounts}}{{.Name}} {{end}}' 2>/dev/null)"
check "no volume of the development database is mounted in the rehearsal cluster" "0" "$(for v in $DEV_VOLS; do docker inspect "$PG" --format '{{range .Mounts}}{{.Name}} {{end}}' | tr ' ' '
' | grep -c "^$v$"; done | paste -sd+ | python -c 'import sys;print(eval(sys.stdin.read() or "0"))')"
check "initial roles of the cluster" "asistente(superuser)" "$(roles_now)"

log "=== 16.1c restore the backup into two databases (the main one and a second copy for the scoping tests)"
docker cp "$RUNW/backup.dump" "$PG:/tmp/backup.dump"
run "pg_restore --list" docker exec "$PG" pg_restore --list /tmp/backup.dump
check "pg_restore --list has the 51 lines of the manifest (header comments included)" 51 "$(docker exec "$PG" pg_restore --list /tmp/backup.dump | wc -l)"
for d in "$DB" "$DB2"; do
  docker exec "$PG" createdb -U asistente "$d"
  run "pg_restore into $d" docker exec "$PG" pg_restore -U asistente -d "$d" --exit-on-error /tmp/backup.dump
done
for d in "$DB" "$DB2"; do
  log "  restored $d: revision $(rev $d), owners [$(owners $d)], counts [$(counts $d)], vector $(psqla $d "select extversion from pg_extension where extname='vector'")"
  check "$d restored at the revision of the backup" 0004 "$(rev $d)"
  check "$d: every restored table is owned by the original administrator" "asistente" "$(owner_set $d)"
done
F0="$(fp $DB)"; log "  catalog fingerprint of the restored backup: $F0"

# =============================================================================================== 2
log "=== 16.2a bring the copy to the state of the development database (0005, still the original owner)"
run "alembic upgrade 0005 as the original administrator ($DB)" docker run --rm --network "$NET" --label "$LABEL" --env-file "$RUNW/admin-main.env" --entrypoint python "$IMG_API" -c "import os; from alembic import command; from app.db_admin.migrate import alembic_config; command.upgrade(alembic_config(os.environ['ADMIN_DB_URL']), '0005')"
run "alembic upgrade 0005 as the original administrator ($DB2)" docker run --rm --network "$NET" --label "$LABEL" --env-file "$RUNW/admin-copy2.env" --entrypoint python "$IMG_API" -c "import os; from alembic import command; from app.db_admin.migrate import alembic_config; command.upgrade(alembic_config(os.environ['ADMIN_DB_URL']), '0005')"
check "$DB at 0005" 0005 "$(rev $DB)"
check "$DB2 at 0005" 0005 "$(rev $DB2)"
check "every table (including alembic_version) is owned by the original administrator" "asistente|asistente" "$(owner_set $DB)|$(type_owner_set $DB)"
check "users.role has no default yet (it is the 0006 migration)" "(none)" "$(default_of_role $DB)"
log "=== synthetic rows in the second copy (the main copy stays empty like the development database)"
psqla "$DB2" "INSERT INTO users (id,name,email,password_hash,role) VALUES ('00000000-0000-0000-0000-000000000001','Teacher','t@example.com','x','teacher'),('00000000-0000-0000-0000-000000000002','Student','s@example.com','x','student');
INSERT INTO subjects (id,name,teacher_id) VALUES ('00000000-0000-0000-0000-0000000000a1','Subject','00000000-0000-0000-0000-000000000001');
INSERT INTO enrollments (subject_id,student_id) VALUES ('00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-000000000002');
INSERT INTO documents (id,subject_id,filename,content_type,size_bytes,status) VALUES ('00000000-0000-0000-0000-0000000000d1','00000000-0000-0000-0000-0000000000a1','a.txt','text/plain',3,'ready');
INSERT INTO document_chunks (document_id,subject_id,chunk_index,content,embedding) VALUES ('00000000-0000-0000-0000-0000000000d1','00000000-0000-0000-0000-0000000000a1',0,'abc',array_fill(0.1::real, ARRAY[384])::vector);
INSERT INTO ingestion_jobs (document_id) VALUES ('00000000-0000-0000-0000-0000000000d1');
INSERT INTO users (id,name,email,password_hash,role) SELECT gen_random_uuid(),'Bulk '||g,'bulk'||g||'@example.com','x','student' FROM generate_series(1,${G16_BULK:-200000}) g;" > /dev/null
S_MAIN0="$(state $DB)"; S_COPY0="$(state $DB2)"
log "  state before, $DB : $S_MAIN0"
log "  state before, $DB2: $S_COPY0"
log "  database ACLs before the bootstrap: $(datacls)"

# =============================================================================================== 3
log "=== 16.2b bootstrap (roles, access, extension); the ownership drift of the old tables is REPORTED, not repaired (exit 1)"
run "db-bootstrap $DB" appx roles.env -- db-bootstrap --database "$DB"
check "bootstrap reports the drift with exit 1 before the adoption" 1 "$RC"
log "  roles now: $(roles_now)"
log "  database ACLs after the bootstrap (PG-08: PUBLIC is closed on every database of the cluster): $(datacls)"
check "the four roles exist and none but the administrator is a superuser" "asistente(superuser),asistente_app,asistente_cli,asistente_migrator,asistente_worker" "$(roles_now)"
check "the bootstrap did not touch ownership, revision or rows of $DB" "$S_MAIN0" "$(state $DB)"

log "=== failure BEFORE the adoption: verify finds the drift; the migrator cannot migrate tables it does not own"
TAILN=6 run "db-verify before adoption" appx migrate.env roles.env -- db-verify
check "verify before the adoption exits 1" 1 "$RC"
TAILN=4 run "db-migrate before adoption (must fail safe)" appx migrate.env -- db-migrate
check "migrating before the adoption fails" 1 "$RC"
check "nothing changed after the refused migration" "$S_MAIN0" "$(state $DB)"
check "users.role still without default" "(none)" "$(default_of_role $DB)"

log "=== wrong identity"
TAILN=3 run "db-migrate with the administrator URL" appx wrong-admin.env -- db-migrate
check "refused (exit 1)" 1 "$RC"
TAILN=3 run "db-migrate --downgrade with the administrator URL" appx wrong-admin.env -- db-migrate --downgrade 0004
check "refused (exit 1)" 1 "$RC"
TAILN=3 run "db-migrate with the application role URL" appx wrong-app.env -- db-migrate
check "refused (exit 1)" 1 "$RC"
TAILN=3 run "db-verify with the administrator URL" appx wrong-admin.env roles.env -- db-verify
check "refused (exit 1)" 1 "$RC"
check "no change after the wrong identities" "$S_MAIN0" "$(state $DB)"

log "=== wrong database and system databases"
for target in postgres template0 template1 POSTGRES; do
  TAILN=2 run "db-bootstrap --database $target" appx roles.env -- db-bootstrap --database "$target"; check "bootstrap refuses $target" 1 "$RC"
  TAILN=2 run "db-adopt --database $target" appx roles.env -- db-adopt --database "$target"; check "adopt refuses $target" 1 "$RC"
  TAILN=2 run "db-adopt --rollback --apply --database $target" appx roles.env -- db-adopt --rollback --apply --database "$target"; check "rollback refuses $target" 1 "$RC"
done
TAILN=2 run "db-adopt --database a_database_that_does_not_exist" appx roles.env -- db-adopt --database a_database_that_does_not_exist
check "adopt of a missing database fails (exit 1)" 1 "$RC"
TAILN=2 run "db-adopt --rollback --apply --database a_database_that_does_not_exist" appx roles.env -- db-adopt --rollback --apply --database a_database_that_does_not_exist
check "rollback of a missing database is refused (exit 1)" 1 "$RC"
check "nothing changed in the cluster after those refusals" "$S_MAIN0" "$(state $DB)"
check "roles unchanged after those refusals" "asistente(superuser),asistente_app,asistente_cli,asistente_migrator,asistente_worker" "$(roles_now)"

# =============================================================================================== 4
log "=== adoption: dry run, then the partial-failure cases, then the real adoption (in the copy only)"
TAILN=12 run "db-adopt dry run" appx roles.env -- db-adopt --database "$DB"
check "the dry run exits 0" 0 "$RC"
check "the dry run changed nothing" "$S_MAIN0" "$(state $DB)"

log "  a session that holds the database blocks the adoption (guard)"
docker exec -d "$PG" psql -U asistente -d "$DB" -c "select pg_sleep(40)" > /dev/null 2>&1; sleep 2
TAILN=3 run "db-adopt --apply with a foreign session" appx roles.env -- db-adopt --apply --database "$DB"
check "refused while another session holds the database (exit 1)" 1 "$RC"
psqla postgres "select pg_terminate_backend(pid) from pg_stat_activity where datname='$DB' and query like 'select pg_sleep%' and pid<>pg_backend_pid()" > /dev/null; sleep 1
check "nothing changed after the refusal" "$S_MAIN0" "$(state $DB)"

log "  PARTIAL failure: a prepared transaction (no session) holds a lock on one table, so the adoption alters others and then times out"
psqla "$DB" "begin; lock table enrollments in access share mode; prepare transaction 'g16_lock';" > /dev/null
log "    prepared transactions: $(psqla postgres 'select count(*) from pg_prepared_xacts') ; sessions on $DB: $(psqla postgres "select count(*) from pg_stat_activity where datname='$DB' and backend_type='client backend' and pid<>pg_backend_pid()")"
TAILN=3 run "db-adopt --apply with a lock held by a prepared transaction" appx roles.env -- db-adopt --apply --database "$DB"
check "the adoption fails on the lock timeout (exit 1)" 1 "$RC"
check "ATOMIC: owners, types, rows and catalog are exactly as before" "$S_MAIN0" "$(state $DB)"
psqla postgres "rollback prepared 'g16_lock'" > /dev/null 2>&1; psqla "$DB" "rollback prepared 'g16_lock'" > /dev/null 2>&1
check "the lock holder is gone" 0 "$(psqla postgres 'select count(*) from pg_prepared_xacts')"

TAILN=14 run "db-adopt --apply ($DB)" appx roles.env -- db-adopt --apply --database "$DB"
check "adoption applied (exit 0)" 0 "$RC"
check "every table and the enum types now belong to the migrator" "asistente_migrator|asistente_migrator" "$(owner_set $DB)|$(type_owner_set $DB)"
check "revision, rows and catalog are unchanged by the adoption" "$(echo "$S_MAIN0" | sed 's/owners=[^;]*;//; s/types=[^;]*;//')" "$(state $DB | sed 's/owners=[^;]*;//; s/types=[^;]*;//')"

# =============================================================================================== 5
log "=== migration 0006 as the migrator, the grants, and the verifier"
TAILN=6 run "db-migrate ($DB)" appx migrate.env -- db-migrate
check "migrated to head and granted (exit 0)" 0 "$RC"
check "$DB at 0006" 0006 "$(rev $DB)"
check "users.role DEFAULT is 'student'" "'student'::user_role" "$(default_of_role $DB)"
TAILN=4 run "db-grants" appx migrate.env -- db-grants
check "grants applied again (idempotent, exit 0)" 0 "$RC"
TAILN=4 run "db-verify ($DB)" appx migrate.env roles.env -- db-verify
check "db-verify reports no drift on the main copy" 0 "$RC"

log "=== effective privileges of the roles (the verifier recomputes them per column; these are independent probes)"
log "  roles: $(roles_now)"
log "  attributes: $(psqla postgres "select string_agg(rolname||':super='||rolsuper||':createrole='||rolcreaterole||':createdb='||rolcreatedb||':limit='||rolconnlimit, ' ' order by rolname) from pg_roles where rolname like 'asistente_%'")"
check "no working role is a superuser or can create roles or databases" 0 "$(psqla postgres "select count(*) from pg_roles where rolname like 'asistente_%' and (rolsuper or rolcreaterole or rolcreatedb or rolreplication or rolbypassrls)")"
check "API role cannot insert a teacher" "permission denied" "$(sql_as asistente_app "INSERT INTO users (name,email,password_hash,role) VALUES ('x','forged@example.com','h','teacher')" | grep -o 'permission denied' | head -1)"
check "API role cannot change users.role" "permission denied" "$(sql_as asistente_app "UPDATE users SET role='teacher'" | grep -o 'permission denied' | head -1)"
check "worker role cannot read users" "permission denied" "$(sql_as asistente_worker "SELECT email FROM users" | grep -o 'permission denied' | head -1)"
check "CLI role cannot read documents" "permission denied" "$(sql_as asistente_cli "SELECT id FROM documents" | grep -o 'permission denied' | head -1)"
check "no role but the migrator can create objects" "permission denied" "$(sql_as asistente_app "CREATE TABLE public.forged (i int)" | grep -o 'permission denied' | head -1)"

# =============================================================================================== 6
log "=== functional validation with the roles (synthetic data): API as asistente_app, worker as asistente_worker, teachers by the CLI"
docker run -d --name "$API" --network "$NET" --label "$LABEL" -p "127.0.0.1:$PORT:8000" --env-file "$RUNW/api.env" -m 512m --cpus 1 "$IMG_API" \
  uvicorn app.main:app_factory --factory --no-proxy-headers --host 0.0.0.0 --port 8000 > /dev/null
docker run -d --name "$WK" --network "$NET" --label "$LABEL" --env-file "$RUNW/worker.env" -m 2g --cpus 2 "$IMG_WK" > /dev/null
for _ in $(seq 1 60); do curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/api/v1/health" && break; sleep 2; done
for _ in $(seq 1 120); do docker logs "$WK" 2>&1 | grep -q "ingestion worker started" && break; sleep 3; done
log "  API log: $(docker logs "$API" 2>&1 | grep -ciE 'started server|Application startup complete') start line(s) | worker started: $(docker logs "$WK" 2>&1 | grep -c 'ingestion worker started')"
log "  sessions by role: $(sql "select string_agg(usename||'='||n, ' ') from (select usename, count(*) n from pg_stat_activity where usename like 'asistente_%' group by 1 order by 1) s")"
BASE="http://127.0.0.1:$PORT/api/v1"
CURRENT="2026-10-v1"

log "=== functional: health and unauthenticated access"
api GET /health 200 ""
log "    body: $(python -c "import json;print(json.load(open('$BODY')))" 2>&1 | cut -c1-120)"
api GET /users/me 401 ""
api GET /subjects 401 ""
api POST /subjects 401 "" '{"name":"Anonymous subject"}'

log "=== registration (public, students only)"
api POST /auth/register 201 "" "{\"name\":\"Student One\",\"email\":\"student1@example.com\",\"password\":\"$UP1\"}"
S1=$(field id); check "registered role is student" student "$(field role)"
check "stored role in the database" student "$(sql "select role::text from users where email='student1@example.com'")"
api POST /auth/register 201 "" "{\"name\":\"Student Two\",\"email\":\"student2@example.com\",\"password\":\"$UP2\",\"role\":\"teacher\"}"
S2=$(field id); check "a payload asking for role teacher still creates a student" student "$(sql "select role::text from users where email='student2@example.com'")"
api POST /auth/register 409 "" "{\"name\":\"Student One\",\"email\":\"student1@example.com\",\"password\":\"$UP1\"}"
check "a duplicate registration stores no second row" 1 "$(sql "select count(*) from users where email='student1@example.com'")"
api POST /auth/register 422 "" '{"name":"","email":"not-an-email","password":"x"}'
check "users stored so far" 2 "$(sql 'select count(*) from users')"

log "=== login and JWT"
api POST /auth/login 200 "" "{\"email\":\"student1@example.com\",\"password\":\"$UP1\"}"
T_S1=$(field access_token); SECRETS+=("$T_S1")
api POST /auth/login 200 "" "{\"email\":\"student2@example.com\",\"password\":\"$UP2\"}"
T_S2=$(field access_token); SECRETS+=("$T_S2")
api POST /auth/login 401 "" "{\"email\":\"student1@example.com\",\"password\":\"wrong-password-$(gen)\"}"
api GET /users/me 200 "$T_S1"; check "the profile is the caller's" "$S1" "$(field id)"
api GET /users/me 401 "$T_S1.tampered"

log "=== teacher accounts through the administrative command (role asistente_cli)"
printf '%s\n' "$TP1" | cli_run create-teacher --email teacher1@example.com --name "Teacher One" --password-stdin 2>&1 | sed 's/id=[0-9a-f-]*/id=<id>/' | mask | tee -a "$OUT" | tail -2
printf '%s\n' "$TP2" | cli_run create-teacher --email teacher2@example.com --name "Teacher Two" --password-stdin > /dev/null 2>&1
check "stored role of teacher1" teacher "$(sql "select role::text from users where email='teacher1@example.com'")"
check "stored role of teacher2" teacher "$(sql "select role::text from users where email='teacher2@example.com'")"
printf '%s\n' "$TP1" | cli_run create-teacher --email teacher1@example.com --password-stdin 2>&1 | mask | tail -1 | tee -a "$OUT"
check "a duplicate teacher stores no second row" 1 "$(sql "select count(*) from users where email='teacher1@example.com'")"
api POST /auth/login 200 "" "{\"email\":\"teacher1@example.com\",\"password\":\"$TP1\"}"; T_T1=$(field access_token); SECRETS+=("$T_T1")
api POST /auth/login 200 "" "{\"email\":\"teacher2@example.com\",\"password\":\"$TP2\"}"; T_T2=$(field access_token); SECRETS+=("$T_T2")

log "=== consent (200 and the stored evidence)"
api POST /users/me/consent 422 "$T_S1" '{"consent_version":"1999-01-v0"}'
log "    error code: $(field code)"
check "nothing stored after a wrong version" "" "$(sql "select coalesce(consent_version,'') from users where id='$S1'")"
api POST /users/me/consent 200 "$T_S1" "{\"consent_version\":\"$CURRENT\"}"
check "stored consent version" "$CURRENT" "$(sql "select consent_version from users where id='$S1'")"
check "stored consent time is set" t "$(sql "select consent_accepted_at is not null from users where id='$S1'")"
api POST /users/me/consent 200 "$T_S1" "{\"consent_version\":\"$CURRENT\"}"
api POST /users/me/consent 200 "$T_T1" "{\"consent_version\":\"$CURRENT\"}"
api POST /users/me/consent 401 "" "{\"consent_version\":\"$CURRENT\"}"

log "=== subjects (wrong role, other teacher, unauthenticated)"
api POST /subjects 403 "$T_S1" '{"name":"Student subject"}'
check "no subject stored by the student" 0 "$(sql 'select count(*) from subjects')"
api POST /subjects 201 "$T_T1" '{"name":"Calculus","description":"Synthetic course"}'
SUBJ=$(field id); check "stored subject" 1 "$(sql "select count(*) from subjects where id='$SUBJ'")"
check "owner of the stored subject is teacher1" teacher1@example.com "$(sql "select u.email from subjects s join users u on u.id=s.teacher_id where s.id='$SUBJ'")"
api POST /subjects 409 "$T_T1" '{"name":"Calculus"}'
check "a duplicate name stores no second subject" 1 "$(sql "select count(*) from subjects where name='Calculus'")"
api GET /subjects 200 "$T_T1"; check "teacher1 lists one subject" 1 "$(python -c "import json;print(len(json.load(open('$BODY'))))")"
api GET "/subjects/$SUBJ" 200 "$T_T1"
api GET /subjects 200 "$T_T2"; check "teacher2 lists no subject of teacher1" 0 "$(python -c "import json;print(len(json.load(open('$BODY'))))")"
api GET "/subjects/$SUBJ" 404 "$T_T2"
api DELETE "/subjects/$SUBJ" 404 "$T_T2"
check "the subject is still stored after the other teacher's delete" 1 "$(sql "select count(*) from subjects where id='$SUBJ'")"
api GET "/subjects/$SUBJ" 404 "$T_S1"
api GET "/subjects/$SUBJ" 401 ""

log "=== enrollments"
api POST "/subjects/$SUBJ/enrollments" 403 "$T_S1" '{"student_email":"student1@example.com"}'
api POST "/subjects/$SUBJ/enrollments" 404 "$T_T2" '{"student_email":"student1@example.com"}'
api POST "/subjects/$SUBJ/enrollments" 404 "$T_T1" '{"student_email":"nobody@example.com"}'
api POST "/subjects/$SUBJ/enrollments" 201 "$T_T1" '{"student_email":"student1@example.com"}'
check "stored enrollment" 1 "$(sql "select count(*) from enrollments where subject_id='$SUBJ' and student_id='$S1'")"
api POST "/subjects/$SUBJ/enrollments" 409 "$T_T1" '{"student_email":"student1@example.com"}'
check "a duplicate enrollment stores no second row" 1 "$(sql "select count(*) from enrollments where subject_id='$SUBJ'")"
api POST "/subjects/$SUBJ/enrollments" 201 "$T_T1" '{"student_email":"student2@example.com"}'
api GET "/subjects/$SUBJ/enrollments" 200 "$T_T1"; check "the teacher lists two enrollments" 2 "$(python -c "import json;print(len(json.load(open('$BODY'))))")"
api GET "/subjects/$SUBJ/enrollments" 403 "$T_S1"
api GET "/subjects/$SUBJ" 200 "$T_S1"
api DELETE "/subjects/$SUBJ/enrollments/$S2" 204 "$T_T1"
check "the removed enrollment is gone, the other stays" "1" "$(sql "select count(*) from enrollments where subject_id='$SUBJ'")"
api DELETE "/subjects/$SUBJ/enrollments/$S2" 404 "$T_T1"
api GET "/subjects/$SUBJ" 404 "$T_S2"

log "=== documents (TXT, Markdown, PDF) processed by the worker role"
printf 'Derivatives measure the rate of change of a function over time.\n' > "$RUN/notes.txt"
printf '# Limits\n\nA limit describes the value a function approaches near a point.\n' > "$RUN/limits.md"
(cd "$REPO/backend" && PYTHONPATH=. .venv/Scripts/python.exe -c "
from tests.pdf_support import pdf_with_pages
open(r'$(cd "$RUN" && pwd -W)/series.pdf', 'wb').write(pdf_with_pages(['Limits and continuity of functions', 'Series converge when their terms shrink']))")
printf 'MZ synthetic executable bytes' > "$RUN/payload.exe"
upload "/subjects/$SUBJ/documents" 403 "$T_S1" "$RUN/notes.txt" notes.txt text/plain
upload "/subjects/$SUBJ/documents" 401 "" "$RUN/notes.txt" notes.txt text/plain
upload "/subjects/$SUBJ/documents" 404 "$T_T2" "$RUN/notes.txt" notes.txt text/plain
upload "/subjects/$SUBJ/documents" 415 "$T_T1" "$RUN/payload.exe" payload.exe application/octet-stream
check "nothing stored by the refused uploads" 0 "$(sql 'select count(*) from documents')"
upload "/subjects/$SUBJ/documents" 202 "$T_T1" "$RUN/notes.txt" notes.txt text/plain; D_TXT=$(field id)
check "the TXT document is persisted after the 202" 1 "$(sql "select count(*) from documents where id='$D_TXT'")"
upload "/subjects/$SUBJ/documents" 202 "$T_T1" "$RUN/limits.md" limits.md text/markdown; D_MD=$(field id)
upload "/subjects/$SUBJ/documents" 202 "$T_T1" "$RUN/series.pdf" series.pdf application/pdf; D_PDF=$(field id)
for d in "$D_TXT" "$D_MD" "$D_PDF"; do log "    document status after the worker: $(wait_doc "$d")"; done
check "TXT is ready" ready "$(sql "select status from documents where id='$D_TXT'")"
check "Markdown is ready" ready "$(sql "select status from documents where id='$D_MD'")"
check "PDF is ready" ready "$(sql "select status from documents where id='$D_PDF'")"
check "the three documents produced chunks" t "$(sql "select (select count(*) from document_chunks where subject_id='$SUBJ') >= 3")"
check "the PDF chunks carry page numbers" t "$(sql "select count(distinct page_number) >= 2 from document_chunks where document_id='$D_PDF'")"
check "no job keeps the uploaded bytes after processing" 0 "$(sql "select count(*) from ingestion_jobs where payload is not null")"
check "no lease is left" 0 "$(sql "select count(*) from ingestion_jobs where locked_by is not null")"
api GET "/subjects/$SUBJ/documents" 200 "$T_T1"; check "the teacher lists three ready documents" "3 ready" "$(python -c "import json;d=json.load(open('$BODY'));print(len(d), 'ready' if {x['status'] for x in d}=={'ready'} else 'mixed')")"
api GET "/subjects/$SUBJ/documents" 403 "$T_S1"
api GET "/subjects/$SUBJ/documents" 404 "$T_T2"
api DELETE "/subjects/$SUBJ/documents/$D_TXT" 404 "$T_T2"
api DELETE "/subjects/$SUBJ/documents/$D_TXT" 403 "$T_S1"
check "the TXT document survives the refused deletes" 1 "$(sql "select count(*) from documents where id='$D_TXT'")"
api DELETE "/subjects/$SUBJ/documents/$D_TXT" 204 "$T_T1"
check "deleted document is gone" 0 "$(sql "select count(*) from documents where id='$D_TXT'")"
check "its chunks and job are gone (cascade)" 0 "$(sql "select (select count(*) from document_chunks where document_id='$D_TXT') + (select count(*) from ingestion_jobs where document_id='$D_TXT')")"
api DELETE "/subjects/$SUBJ/documents/$D_TXT" 404 "$T_T1"

log "=== subject deletion and cascades"
api DELETE "/subjects/$SUBJ" 204 "$T_T1"
check "subject gone" 0 "$(sql "select count(*) from subjects where id='$SUBJ'")"
check "enrollments, documents, chunks and jobs of the subject are gone" 0 "$(sql "select (select count(*) from enrollments) + (select count(*) from documents) + (select count(*) from document_chunks) + (select count(*) from ingestion_jobs)")"
api DELETE "/subjects/$SUBJ" 404 "$T_T1"
check "the four accounts remain" 4 "$(sql 'select count(*) from users')"

log "=== isolation of the roles, checked with SQL on the live database"
log "  API role: forged teacher insert -> $(sql_as asistente_app "INSERT INTO users (name,email,password_hash,role) VALUES ('x','forged@example.com','h','teacher')")"
log "  API role: update users.role      -> $(sql_as asistente_app "UPDATE users SET role='teacher'")"
log "  API role: DDL (create table)     -> $(sql_as asistente_app "CREATE TABLE public.forged (i int)")"
log "  API role: create role            -> $(sql_as asistente_app "CREATE ROLE forged LOGIN")"
log "  API role: other database         -> $(sql_as asistente_app "select 1" postgres)"
log "  worker: read users               -> $(sql_as asistente_worker "SELECT email FROM users")"
log "  worker: read subjects            -> $(sql_as asistente_worker "SELECT id FROM subjects")"
log "  worker: delete documents         -> $(sql_as asistente_worker "DELETE FROM documents")"
log "  worker: DDL (create table)       -> $(sql_as asistente_worker "CREATE TABLE public.forged (i int)")"
log "  CLI: read documents              -> $(sql_as asistente_cli "SELECT id FROM documents")"
log "  CLI: update users.role           -> $(sql_as asistente_cli "UPDATE users SET role='teacher'")"
log "  CLI: read jobs                   -> $(sql_as asistente_cli "SELECT id FROM ingestion_jobs")"
log "  CLI: read accounts (allowed)     -> $(sql_as asistente_cli "SELECT count(*) FROM users")"
DENIED=$(for q in "asistente_app|INSERT INTO users (name,email,password_hash,role) VALUES ('x','forged2@example.com','h','teacher')" "asistente_app|UPDATE users SET role='teacher'" "asistente_app|CREATE TABLE public.forged (i int)" "asistente_worker|SELECT email FROM users" "asistente_worker|SELECT id FROM subjects" "asistente_worker|DELETE FROM documents" "asistente_cli|SELECT id FROM documents" "asistente_cli|UPDATE users SET role='teacher'" "asistente_cli|SELECT id FROM ingestion_jobs"; do sql_as "${q%%|*}" "${q#*|}" | grep -c "permission denied"; done | paste -sd+ | python -c "import sys;print(eval(sys.stdin.read()))")
check "every unauthorised statement above was refused by PostgreSQL" 9 "$DENIED"
check "no forged table or role was created" 0 "$(sql "select (select count(*) from pg_tables where tablename='forged') + (select count(*) from pg_roles where rolname='forged')")"
check "no forged user exists" 0 "$(sql "select count(*) from users where email like 'forged%'")"
check "no runtime or migrator role is a superuser" 0 "$(sql "select count(*) from pg_roles where rolname like 'asistente_%' and rolsuper")"
log "sessions by role during the run: $(sql "select string_agg(usename||'='||n, ' ') from (select usename, count(*) n from pg_stat_activity where usename like 'asistente_%' group by 1 order by 1) s")"
log "secrets by service (variable NAMES only):"
for c in "$API" "$WK" "$PG"; do log "  $c: $(envnames $c)"; done
log "  cli (run on demand): $(sed 's/=.*//' "$RUN/cli.env" | tr '\n' ' ')"
log "published ports: API $(docker port "$API" | tr '\n' ' ') | database: [$(docker port "$PG" | tr '\n' ' ')] | worker: [$(docker port "$WK" | tr '\n' ' ')]"
TAILN=3 run "db-verify after the functional run ($DB)" appx migrate.env roles.env -- db-verify
check "db-verify has no drift after the functional run" 0 "$RC"
log "  final functional state: $(counts $DB)"

# =============================================================================================== 7
log "=== re-execution and idempotence (everything again on the adopted copy)"
TAILN=3 run "db-bootstrap again" appx roles.env -- db-bootstrap --database "$DB"
check "bootstrap again: exit 0 (no drift any more)" 0 "$RC"
TAILN=3 run "db-adopt again (dry run)" appx roles.env -- db-adopt --database "$DB"
check "adopt again: exit 0, nothing to do" 0 "$RC"
TAILN=3 run "db-adopt --apply again" appx roles.env -- db-adopt --apply --database "$DB"
check "adopt --apply again: exit 0" 0 "$RC"
TAILN=3 run "db-migrate again" appx migrate.env -- db-migrate
check "migrate again: exit 0" 0 "$RC"
TAILN=3 run "db-grants again" appx migrate.env -- db-grants
check "grants again: exit 0" 0 "$RC"
TAILN=3 run "db-verify again" appx migrate.env roles.env -- db-verify
check "verify again: no drift" 0 "$RC"

# =============================================================================================== 8
log "=== PG-05: the grants run after Alembic; a column added by a migration is visible to table-level grants until db-grants"
docker rm -f "$API" "$WK" > /dev/null 2>&1
for t in users subjects enrollments documents document_chunks ingestion_jobs; do
  docker exec "$PG" psql -U asistente_migrator -d "$DB" -At -c "ALTER TABLE public.$t ADD COLUMN g16_probe integer" > /dev/null 2>&1
done
log "  roles that can SELECT the new column, per table: $(psqla $DB "select string_agg(t||'<='||r, ' ' order by t, r) from (select c.relname t, ro.rolname r from pg_class c cross join (select rolname from pg_roles where rolname in ('asistente_app','asistente_worker','asistente_cli')) ro where c.relnamespace='public'::regnamespace and c.relkind='r' and c.relname<>'alembic_version' and has_column_privilege(ro.rolname, c.oid, 'g16_probe', 'SELECT')) s")"
TAILN=5 run "db-verify with the exposed columns" appx migrate.env roles.env -- db-verify
log "  verify exit code with a column added outside db-migrate: $RC (1 = it is detected)"
TAILN=2 run "db-grants heals it" appx migrate.env -- db-grants
TAILN=3 run "db-verify after db-grants" appx migrate.env roles.env -- db-verify
log "  verify after db-grants: $RC"
for t in users subjects enrollments documents document_chunks ingestion_jobs; do
  docker exec "$PG" psql -U asistente_migrator -d "$DB" -At -c "ALTER TABLE public.$t DROP COLUMN g16_probe" > /dev/null 2>&1
done
TAILN=3 run "db-verify after dropping the probe columns" appx migrate.env roles.env -- db-verify
check "the probe columns are gone and the database matches the design" 0 "$RC"

log "=== PG-08: a database whose name has a quote makes the bootstrap abort (availability); nothing is changed"
psqla postgres 'CREATE DATABASE "g16""quote"' > /dev/null
S_BEFORE_Q="$(state $DB)"; R_BEFORE_Q="$(roles_now)"; D_BEFORE_Q="$(datacls)"
TAILN=3 run "db-bootstrap with a quoted database name present" appx roles.env -- db-bootstrap --database "$DB"
check "the bootstrap aborts (exit 1)" 1 "$RC"
check "and changed nothing (state, roles, database ACLs)" "$S_BEFORE_Q|$R_BEFORE_Q|$D_BEFORE_Q" "$(state $DB)|$(roles_now)|$(datacls)"
psqla postgres 'DROP DATABASE "g16""quote"' > /dev/null

# =============================================================================================== 8b
log "=== a second application database in the same cluster (bulk rows): adoption, migration, grants, and what db-verify says about two databases"
TAILN=3 run "db-bootstrap $DB2" appx roles.env -- db-bootstrap --database "$DB2"
check "bootstrap of the second copy reports its ownership drift (exit 1)" 1 "$RC"
A0=$(ms); TAILN=3 run "db-adopt --apply ($DB2, $(psqla $DB2 'select count(*) from users') users)" appx roles.env -- db-adopt --apply --database "$DB2"; A1=$(ms)
check "adoption of the second copy applied (exit 0)" 0 "$RC"
log "    PG-08 / TD-044: this adoption took $((A1 - A0)) ms including the container start; the row counts of every table run inside the exclusive-lock transaction"
TAILN=3 run "db-migrate ($DB2)" appx migrate2.env -- db-migrate
check "second copy migrated (exit 0)" 0 "$RC"
check "$DB2 at 0006" 0006 "$(rev $DB2)"
check "the bulk copy kept its rows through adoption, migration and grants" "$(echo "$S_COPY0" | grep -o 'counts=[^;]*')" "$(state $DB2 | grep -o 'counts=[^;]*')"
TAILN=6 run "db-verify ($DB2)" appx migrate2.env roles.env -- db-verify
log "    db-verify of the second database: exit $RC; findings that are not about the other database: $(echo "$OUTP" | grep '^\[' | grep -vc "can connect to database $DB\$")"
check "the only findings are the CONNECT of the roles to the OTHER application database (verify assumes one application database per cluster)" 0 "$(echo "$OUTP" | grep '^\[' | grep -vc "can connect to database $DB\$")"
TAILN=6 run "db-verify ($DB) now that the second database is bootstrapped" appx migrate.env roles.env -- db-verify
check "the same finding appears on the main database (exit 1)" 1 "$RC"

# =============================================================================================== 9
log "=== rollback and recovery: the way back, one database at a time"
S_MAIN_ADOPTED="$(state $DB)"
log "  1. dry run of the rollback names the database only"
TAILN=2 run "db-adopt --rollback (dry run) $DB" appx roles.env -- db-adopt --rollback --database "$DB"
check "dry run exit 0" 0 "$RC"
check "dry run changed nothing" "$S_MAIN_ADOPTED" "$(state $DB)"
log "  2. --remove-roles while the second database is still owned: refused BEFORE any change (second review R7)"
TAILN=4 run "rollback --remove-roles $DB while $DB2 is still adopted" appx roles.env -- db-adopt --rollback --remove-roles --apply --database "$DB"
check "refused (exit 1)" 1 "$RC"
check "the refusal names the other database" 1 "$(echo "$OUTP" | grep -c "$DB2")"
check "nothing changed, the main copy is still adopted" "$S_MAIN_ADOPTED" "$(state $DB)"
log "  3. rollback of ONE database leaves the other one alone"
TAILN=5 run "db-adopt --rollback --apply $DB" appx roles.env -- db-adopt --rollback --apply --database "$DB"
check "rollback applied (exit 0)" 0 "$RC"
check "the report names the other database still owned by the migrator" 1 "$(echo "$OUTP" | grep -c "$DB2")"
check "main copy: tables and types back to the original administrator" "asistente|asistente" "$(owner_set $DB)|$(type_owner_set $DB)"
check "second copy: still owned by the migrator" "asistente_migrator|asistente_migrator" "$(owner_set $DB2)|$(type_owner_set $DB2)"
check "the main copy kept its rows and catalog through the rollback" "$(echo "$S_MAIN_ADOPTED" | grep -o 'counts=[^;]*;fp=.*')" "$(state $DB | grep -o 'counts=[^;]*;fp=.*')"
TAILN=3 run "db-adopt --rollback --apply $DB again (idempotence)" appx roles.env -- db-adopt --rollback --apply --database "$DB"
check "the rollback can be run again (exit 0)" 0 "$RC"
log "  4. adopt again (idempotence of the way forward) and roll forward the grants"
TAILN=3 run "db-adopt --apply $DB again after a rollback" appx roles.env -- db-adopt --apply --database "$DB"
check "re-adoption works (exit 0)" 0 "$RC"
check "owned by the migrator again" "asistente_migrator|asistente_migrator" "$(owner_set $DB)|$(type_owner_set $DB)"
TAILN=3 run "db-verify after re-adoption" appx migrate.env roles.env -- db-verify
check "no finding after re-adoption except the CONNECT to the other application database" 0 "$(echo "$OUTP" | grep '^\[' | grep -vc "can connect to database $DB2\$")"
log "  5. the whole way back for both databases: downgrade 0006, rollback ownership, remove the roles with the last one"
TAILN=3 run "db-migrate --downgrade 0005 ($DB)" appx migrate.env -- db-migrate --downgrade 0005
check "downgraded (exit 0)" 0 "$RC"
TAILN=3 run "db-migrate --downgrade 0005 ($DB2)" appx migrate2.env -- db-migrate --downgrade 0005
check "downgraded (exit 0)" 0 "$RC"
check "$DB back at 0005 and users.role without default" "0005|(none)" "$(rev $DB)|$(default_of_role $DB)"
TAILN=3 run "rollback $DB" appx roles.env -- db-adopt --rollback --apply --database "$DB"
TAILN=3 run "rollback $DB2 and remove the roles (the last database)" appx roles.env -- db-adopt --rollback --remove-roles --apply --database "$DB2"
check "the last rollback with --remove-roles succeeds (exit 0)" 0 "$RC"
check "the cluster has only the original administrator again" "asistente(superuser)" "$(roles_now)"
check "main copy equals the state before the bootstrap (revision, owners, types, catalog; the rows are those of the functional run)" "$(echo "$S_MAIN0" | sed 's/counts=[^;]*;//')" "$(state $DB | sed 's/counts=[^;]*;//')"
check "main copy keeps the rows of the functional run through the whole way back" "users=4,subjects=0,enrollments=0,documents=0,chunks=0,jobs=0" "$(counts $DB)"
check "second copy equals its state before the bootstrap" "$S_COPY0" "$(state $DB2)"
log "  database ACLs after the whole way back (the closing of PUBLIC is NOT undone by the rollback; PG-08): $(datacls)"

log "=== recovery from the backup: drop the main copy, restore it again from the verified dump"
check "the dump still has its recorded hash" "$SHA_BEFORE" "$(sha256sum "$RUN/backup.dump" | cut -d' ' -f1)"
psqla postgres "DROP DATABASE $DB WITH (FORCE)" > /dev/null
docker exec "$PG" createdb -U asistente "$DB"
run "pg_restore again" docker exec "$PG" pg_restore -U asistente -d "$DB" --exit-on-error /tmp/backup.dump
check "restored at the revision of the backup" 0004 "$(rev $DB)"
check "the catalog of the restored backup equals the first restoration" "$F0" "$(fp $DB)"
check "owners are the original administrator again" "asistente" "$(owner_set $DB)"

log "=== result: $PASS checks passed, $FAIL failed (of $N)"
[ "$FAIL" = "0" ]
