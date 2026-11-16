#!/usr/bin/env bash
# Group 13 (tasks 13.1 to 13.3): manual endpoint testing with curl on a completely DISPOSABLE instance.
#
# usage: G13_RUN_DIR=<empty directory OUTSIDE the repository> bash run_g13.sh
#
# - Docker project g13scratch (its own network and volume), the REAL docker-compose.yml read and never modified,
#   plus compose.g13.override.yml. PostgreSQL 15.19 + pgvector 0.8.7 is not published; the API is published only on
#   127.0.0.1 at a temporary free port (never 8000, 5173 or 5442). No frontend. No real env file: synthetic random
#   credentials in G13_RUN_DIR. Bootstrap, migration to 0006, grants and db-verify are the real commands.
# - The API runs as asistente_app, the worker as asistente_worker, the administrative command as asistente_cli.
# - Refuses to start with less than 6 GB of free memory. Everything it creates is identified by the project name and
#   removed at the end after its identity is printed; nothing of the real stack is touched.
# - No password, token or document content is written to the output: secrets are masked.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
OUT="$HERE/g13-output.txt"
RUN="${G13_RUN_DIR:?set G13_RUN_DIR to an empty directory OUTSIDE the repository}"
mkdir -p "$RUN"
[ -z "$(ls -A "$RUN" 2>/dev/null)" ] || { echo "G13_RUN_DIR must be an empty directory"; exit 2; }
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "G13_RUN_DIR must be outside the repository"; exit 2;; esac
OVERRIDE="openspec/changes/database-least-privilege/reports/group-13/compose.g13.override.yml"
P=g13scratch
: > "$OUT"

gen() { python -c "import secrets;print(secrets.token_hex(12))"; }
SECRETS=()
mask() { local s; s="$(cat)"; for v in "${SECRETS[@]}"; do [ -n "$v" ] && s="${s//$v/***}"; done; printf '%s\n' "$s"; }
log() { echo "$@" | mask | tee -a "$OUT"; }
dc() { (cd "$REPO" && G13_DIR="$(cd "$RUN" && pwd -W)" G13_PORT="$PORT" docker compose -p $P -f docker-compose.yml -f "$OVERRIDE" "$@"); }
sql() { dc exec -T db psql -U asistente -d asistenteia -At -c "$1"; }
sql_as() { dc exec -T db psql -U "$1" -d "${3:-asistenteia}" -At -c "$2" 2>&1 | head -3 | tr '\n' ' '; }  # as a role, local trust
wait_healthy() { local i=0; while [ $i -lt "$2" ]; do [ "$(docker inspect "$1" --format '{{.State.Health.Status}}' 2>/dev/null)" = "healthy" ] && return 0; sleep 3; i=$((i+3)); done; return 1; }
envnames() { docker inspect "$1" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | cut -d= -f1 | grep -E '^(POSTGRES_|ADMIN_|DB_|MIGRATION_|CLI_|DATABASE_URL|JWT_|TEST_|CORS_|EMBEDDER|APP_ENV)' | sort | tr '\n' ' '; }

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

FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
log "G13 manual endpoint testing $(date -u +%FT%TZ) | free host RAM before: $FREE GB"
python -c "import sys; sys.exit(0 if float('$FREE') >= 6 else 1)" || { log "RAM below 6 GB: stop"; exit 4; }
BEFORE_OTHER="$(docker ps --format '{{.Names}} {{.Status}}' | grep -v "^${P}-" | sed 's/Up [^(]*//' | sort | tr '\n' ';')"
log "repo HEAD: $(cd "$REPO" && git rev-parse --short HEAD); the REAL docker-compose.yml is read, not modified"

# ---- images: the API from this branch, the worker = main's worker image with the branch code on top
PORT=$(python -c "
import socket
while True:
    s = socket.socket(); s.bind(('127.0.0.1', 0)); p = s.getsockname()[1]; s.close()
    if p not in (8000, 5173, 5442): print(p); break")
log "temporary API port: 127.0.0.1:$PORT (never 8000, 5173 or 5442)"
CTX="$(cd "$REPO/backend" && pwd -W)"  # the Windows docker client needs a Windows path for the build context
docker build -q --target api -t asistenteia-backend:g13-branch "$CTX" > /dev/null || { log "api image build FAILED"; exit 5; }
log "image asistenteia-backend:g13-branch built from the working tree (target api)"
printf 'FROM asistenteia-worker:main-f455234\nUSER root\nCOPY app /app/app\nUSER appuser\n' > "$RUN/Dockerfile.worker"
docker build -q -f "$(cd "$RUN" && pwd -W)/Dockerfile.worker" -t asistenteia-worker:g13-branch "$CTX" > /dev/null || { log "worker image build FAILED"; exit 5; }
log "image asistenteia-worker:g13-branch = main's worker image with backend/app of this branch (uv.lock unchanged: same dependencies)"

# ---- synthetic credentials, never printed
PA=$(gen); PM=$(gen); PP=$(gen); PW=$(gen); PC=$(gen); JWT=$(python -c "import secrets;print(secrets.token_urlsafe(40))")
UP1="Pw1-$(gen)"; UP2="Pw2-$(gen)"; TP1="Pt1-$(gen)"; TP2="Pt2-$(gen)"
SECRETS=("$PA" "$PM" "$PP" "$PW" "$PC" "$JWT" "$UP1" "$UP2" "$TP1" "$TP2")
printf 'POSTGRES_USER=asistente\nPOSTGRES_PASSWORD=%s\nPOSTGRES_DB=asistenteia\n' "$PA" > "$RUN/db.env"
printf 'ADMIN_DATABASE_URL=postgresql+psycopg://asistente:%s@db:5432/postgres\nDB_MIGRATOR_PASSWORD=%s\nDB_APP_PASSWORD=%s\nDB_WORKER_PASSWORD=%s\nDB_CLI_PASSWORD=%s\n' "$PA" "$PM" "$PP" "$PW" "$PC" > "$RUN/roles.env"
printf 'MIGRATION_DATABASE_URL=postgresql+psycopg://asistente_migrator:%s@db:5432/asistenteia\n' "$PM" > "$RUN/migrate.env"
printf 'DATABASE_URL=postgresql+psycopg://asistente_app:%s@db:5432/asistenteia\nAPP_ENV=development\nLOG_LEVEL=INFO\nJWT_SECRET=%s\nCORS_ORIGINS=http://localhost:5173\n' "$PP" "$JWT" > "$RUN/api.env"
printf 'CLI_DATABASE_URL=postgresql+psycopg://asistente_cli:%s@db:5432/asistenteia\n' "$PC" > "$RUN/cli.env"
sed -e "s#postgresql+psycopg://asistente:CHANGE_ME@db:5432/asistenteia#postgresql+psycopg://asistente_worker:$PW@db:5432/asistenteia#" "$REPO/backend/.env.worker.example" > "$RUN/worker.env"
[ "$(grep -v '^#' "$RUN/worker.env" | grep -c 'CHANGE_ME')" = "0" ] || { log "worker example still holds a placeholder"; exit 3; }

teardown() {
  log "--- identity of every resource of the disposable project, before removal"
  log "containers: $(docker ps -a --filter label=com.docker.compose.project=$P --format '{{.Names}}' | tr '\n' ' ')"
  log "networks:   $(docker network ls --filter label=com.docker.compose.project=$P --format '{{.Name}}' | tr '\n' ' ')"
  log "volumes:    $(docker volume ls --filter label=com.docker.compose.project=$P --format '{{.Name}}' | tr '\n' ' ')"
  log "names outside the project among them (must be empty): $(docker ps -a --filter label=com.docker.compose.project=$P --format '{{.Names}}' | grep -v "^${P}-" | tr '\n' ' ')"
  dc down -v --remove-orphans > /dev/null 2>&1
  log "after removal: containers left=$(docker ps -a --filter label=com.docker.compose.project=$P -q | wc -l) networks left=$(docker network ls --filter label=com.docker.compose.project=$P -q | wc -l) volumes left=$(docker volume ls --filter label=com.docker.compose.project=$P -q | wc -l)"
  docker rmi asistenteia-backend:g13-branch asistenteia-worker:g13-branch > /dev/null 2>&1
  log "temporary image tags removed: $(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c 'g13-branch') left"
  AFTER_OTHER="$(docker ps --format '{{.Names}} {{.Status}}' | grep -v "^${P}-" | sed 's/Up [^(]*//' | sort | tr '\n' ';')"
  log "other containers (the real stack and other projects) before and after identical: $([ "$BEFORE_OTHER" = "$AFTER_OTHER" ] && echo yes || echo NO)"
  rm -f "$RUN"/*.env "$RUN"/body.json "$RUN"/*.txt "$RUN"/*.pdf "$RUN"/Dockerfile.worker
}
trap 'teardown' EXIT

# ---- 13.1 the stack on the scratch project
log "=== 13.1 cold start of the scratch project (db, bootstrap, migrate, backend, worker)"
dc up -d > "$RUN/up.txt" 2>&1; log "up -d rc=$? | $(grep -E 'Healthy|Exited|Started' "$RUN/up.txt" | sed 's/^ *//' | tr '\n' ';' | cut -c1-300)"
wait_healthy ${P}-backend-1 150; log "backend healthy rc=$? (0 = yes)"
wait_healthy ${P}-worker-1 300; log "worker healthy rc=$? (0 = yes)"
log "published ports: $(for c in $(docker ps --filter label=com.docker.compose.project=$P --format '{{.Names}}'); do echo "$c:[$(docker port $c | tr '\n' ' ')]"; done)"
log "alembic revision: $(sql 'select version_num from alembic_version')"
log "roles: $(sql "select string_agg(rolname||':superuser='||rolsuper||':limit='||rolconnlimit, ' ' order by rolname) from pg_roles where rolname like 'asistente_%'")"
log "sessions by role: $(sql "select string_agg(usename||'='||n, ' ') from (select usename, count(*) n from pg_stat_activity where usename like 'asistente_%' group by 1 order by 1) s")"
log "db-verify: $(docker run --rm --network ${P}_default --env-file "$RUN/migrate.env" --env-file "$RUN/roles.env" asistenteia-backend:g13-branch python -m app.cli db-verify 2>&1 | tail -2 | mask | tr '\n' ' ')"
BASE="http://127.0.0.1:$PORT/api/v1"
CURRENT="2026-10-v1"

log "=== 13.2 health and unauthenticated access"
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
printf '%s\n' "$TP1" | dc run --rm -T --no-deps cli create-teacher --email teacher1@example.com --name "Teacher One" --password-stdin 2>&1 | sed 's/id=[0-9a-f-]*/id=<id>/' | mask | tee -a "$OUT" | tail -2
printf '%s\n' "$TP2" | dc run --rm -T --no-deps cli create-teacher --email teacher2@example.com --name "Teacher Two" --password-stdin > /dev/null 2>&1
check "stored role of teacher1" teacher "$(sql "select role::text from users where email='teacher1@example.com'")"
check "stored role of teacher2" teacher "$(sql "select role::text from users where email='teacher2@example.com'")"
printf '%s\n' "$TP1" | dc run --rm -T --no-deps cli create-teacher --email teacher1@example.com --password-stdin 2>&1 | mask | tail -1 | tee -a "$OUT"
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

log "=== 13.3 isolation of the roles, checked with SQL on the live database"
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
for c in db backend worker; do log "  $c: $(envnames ${P}-${c}-1)"; done
for c in bootstrap migrate; do log "  $c (exited one-shot): $(envnames ${P}-${c}-1)"; done
log "  cli (run on demand, removed): $(sed 's/=.*//' "$RUN/cli.env" | tr '\n' ' ')"
log "published ports at the end: $(for c in $(docker ps --filter label=com.docker.compose.project=$P --format '{{.Names}}'); do echo "$c:[$(docker port $c | tr '\n' ' ')]"; done)"
log "db-verify after the run: $(docker run --rm --network ${P}_default --env-file "$RUN/migrate.env" --env-file "$RUN/roles.env" asistenteia-backend:g13-branch python -m app.cli db-verify 2>&1 | tail -2 | mask | tr '\n' ' ')"
log "final state of the scratch database: $(sql "select 'users='||(select count(*) from users)||' subjects='||(select count(*) from subjects)||' documents='||(select count(*) from documents)||' chunks='||(select count(*) from document_chunks)||' jobs='||(select count(*) from ingestion_jobs)")"
log "=== result: $PASS checks passed, $FAIL failed (of $N)"
[ "$FAIL" = "0" ]
