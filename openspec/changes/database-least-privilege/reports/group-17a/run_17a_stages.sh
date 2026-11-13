#!/usr/bin/env bash
# Group 17A: rollback from EACH stage of the forward procedure (after the bootstrap, after the adoption,
# after the migration and the grants), on a disposable PostgreSQL 15.19 + pgvector 0.8.7.
#
# usage: G17A_BACKUP=<dump of revision 0004> G17A_RUN_DIR=<empty directory OUTSIDE the repository> bash run_17a_stages.sh
#
# For every stage: restore the backup into a new database, bring it to 0005 as the original administrator,
# snapshot it (S0), go forward to the stage, run the documented rollback (downgrade when migrated,
# `db-adopt --rollback --remove-roles --apply`, restore_public_cluster.sql, restore_public_schema.sql) and
# compare with S0: ownership, roles, grants, defaults and rows must be identical; the only tolerated
# difference is the representation of default ACLs (NORMALIZE=1 of compare_snapshots.sh).
# Nothing real is touched: own network and container, tmpfs data, no published port, synthetic credentials.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
TOOLS="$HERE/tools"
OUT="$HERE/g17a-stages-output.txt"
RUN="${G17A_RUN_DIR:?set G17A_RUN_DIR to an empty directory OUTSIDE the repository}"
BACKUP="${G17A_BACKUP:?set G17A_BACKUP to the verified dump of revision 0004}"
mkdir -p "$RUN"
[ -z "$(ls -A "$RUN" 2>/dev/null)" ] || { echo "G17A_RUN_DIR must be an empty directory"; exit 2; }
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "G17A_RUN_DIR must be outside the repository"; exit 2;; esac
RUNW="$(cd "$RUN" && pwd -W)"
SUF=$$; NET="g17stnet$SUF"; PG="g17stpg$SUF"; LABEL="purpose=g17a-stages"
IMG_PG="pgvector/pgvector:0.8.7-pg15"; IMG_API="asistenteia-backend:g17a-stage"
: > "$OUT"
gen() { python -c "import secrets;print(secrets.token_hex(12))"; }
SECRETS=()
mask() { local s; s="$(cat)"; for v in "${SECRETS[@]}"; do [ -n "$v" ] && s="${s//$v/***}"; done; printf '%s\n' "$s"; }
log() { echo "$@" | mask | tee -a "$OUT"; }
ms() { echo $(( $(date +%s%N) / 1000000 )); }
PASS=0; FAIL=0; N=0
check() { N=$((N+1)); if [ "$2" = "$3" ]; then PASS=$((PASS+1)); log "  [$N] PASS $1 | expected $2, obtained $3"; else FAIL=$((FAIL+1)); log "  [$N] FAIL $1 | expected $2, obtained $3"; fi; }
run() { local name="$1"; shift; local a; a=$(ms); OUTP="$("$@" 2>&1)"; RC=$?; STEP_MS=$(( $(ms) - a )); log "  [$name] rc=$RC (${STEP_MS} ms)"
  if [ -n "$OUTP" ]; then printf '%s\n' "$OUTP" | tail -n "${TAILN:-3}" | cut -c1-200 | sed 's/^/      | /' | mask | tee -a "$OUT" > /dev/null; fi; }
sqlc() { docker exec -i "$PG" sh -c "psql -U asistente -d ${1} -At -v ON_ERROR_STOP=1" <<< "$2" 2>&1; }
snap_db() { docker exec -i "$PG" sh -c "psql -U asistente -d $1 -At -F '|' -v ON_ERROR_STOP=1 -f -" < "$TOOLS/snapshot_db.sql" > "$2" 2>&1; }
snap_cluster() { docker exec -i "$PG" sh -c "psql -U asistente -d postgres -At -F '|' -v ON_ERROR_STOP=1 -f -" < "$TOOLS/snapshot_cluster.sql" > "$1" 2>&1; }
appx() { local envs=(); while [ "$1" != "--" ]; do envs+=(--env-file "$RUNW/$1"); shift; done; shift
  docker run --rm -i --network "$NET" --label "$LABEL" -m 768m --cpus 1 "${envs[@]}" --entrypoint python "$IMG_API" -m app.cli "$@"; }
teardown() {
  log "--- identity before removal: containers [$(docker ps -a --filter label=$LABEL --format '{{.Names}}' | tr '\n' ' ')] networks [$(docker network ls --filter label=$LABEL --format '{{.Name}}' | tr '\n' ' ')]; outside the scheme: [$(docker ps -a --filter label=$LABEL --format '{{.Names}}' | grep -v '^g17st' | tr '\n' ' ')]"
  docker rm -f "$PG" > /dev/null 2>&1; docker network rm "$NET" > /dev/null 2>&1; docker rmi "$IMG_API" > /dev/null 2>&1
  log "after removal: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l) image tags left=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -c 'g17a-stage')"
  log "original backup untouched: sha $( [ "$(sha256sum "$BACKUP" | cut -d' ' -f1)" = "$SHA_BEFORE" ] && echo equal || echo DIFFERENT )"
  rm -f "$RUN"/*.env "$RUN"/backup.dump
}
trap 'teardown' EXIT

log "=== rollback from each stage $(date -u +%FT%TZ)"
FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
log "free RAM $FREE GB (8 needed); repo HEAD $(cd "$REPO" && git rev-parse --short HEAD)"
python -c "import sys; sys.exit(0 if float('$FREE') >= 8 else 1)" || { log "RAM below 8 GB: stop"; trap - EXIT; exit 4; }
SHA_BEFORE="$(sha256sum "$BACKUP" | cut -d' ' -f1)"
check "the backup has its recorded sha256" "$(cut -d' ' -f1 "$BACKUP.sha256")" "$SHA_BEFORE"
cp "$BACKUP" "$RUN/backup.dump"
docker build -q --target api -t "$IMG_API" "$(cd "$REPO/backend" && pwd -W)" > /dev/null || { log "image build FAILED"; exit 5; }
PA=$(gen); PM=$(gen); PP=$(gen); PW=$(gen); PC=$(gen); SECRETS=("$PA" "$PM" "$PP" "$PW" "$PC")
printf 'ADMIN_DATABASE_URL=postgresql+psycopg://asistente:%s@db:5432/postgres\nDB_MIGRATOR_PASSWORD=%s\nDB_APP_PASSWORD=%s\nDB_WORKER_PASSWORD=%s\nDB_CLI_PASSWORD=%s\n' "$PA" "$PM" "$PP" "$PW" "$PC" > "$RUN/roles.env"
docker network create --label "$LABEL" "$NET" > /dev/null
docker run -d --name "$PG" --label "$LABEL" --network "$NET" --network-alias db --cpus 1 -m 1g --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PA" -e POSTGRES_DB=postgres "$IMG_PG" > /dev/null
for _ in $(seq 1 60); do docker exec "$PG" pg_isready -h 127.0.0.1 -U asistente > /dev/null 2>&1 && break; sleep 1; done; sleep 2
docker cp "$RUNW/backup.dump" "$PG:/tmp/backup.dump"
log "cluster $(sqlc postgres 'select version()' | cut -c1-40), published ports [$(docker port "$PG" | tr '\n' ' ')], mounts $(docker inspect "$PG" --format '{{len .Mounts}}')"

stage() { # name last-step (1 bootstrap, 2 adoption, 3 migration and grants)
  local name="$1" last="$2" db="stage_${1//-/_}"
  log "=== stage $name: forward up to step $last, then the full rollback"
  printf 'MIGRATION_DATABASE_URL=postgresql+psycopg://asistente_migrator:%s@db:5432/%s\n' "$PM" "$db" > "$RUN/migrate-$name.env"
  printf 'ADMIN_DB_URL=postgresql+psycopg://asistente:%s@db:5432/%s\n' "$PA" "$db" > "$RUN/admin-$name.env"
  sqlc postgres "CREATE DATABASE $db" > /dev/null
  docker exec "$PG" pg_restore -U asistente -d "$db" --exit-on-error /tmp/backup.dump
  docker run --rm --network "$NET" --label "$LABEL" --env-file "$RUNW/admin-$name.env" --entrypoint python "$IMG_API" -c "import os; from alembic import command; from app.db_admin.migrate import alembic_config; command.upgrade(alembic_config(os.environ['ADMIN_DB_URL']), '0005')" > /dev/null 2>&1
  check "$name: at 0005 before the stage" 0005 "$(sqlc "$db" "select version_num from alembic_version")"
  snap_db "$db" "$RUN/$name-s0-db.txt"; snap_cluster "$RUN/$name-s0-cluster.txt"
  local t0; t0=$(ms)
  TAILN=1 run "$name: bootstrap" appx roles.env -- db-bootstrap --database "$db"
  [ "$last" -ge 2 ] && { TAILN=1 run "$name: adopt --apply" appx roles.env -- db-adopt --apply --database "$db"; check "$name: adoption applied" 0 "$RC"; }
  [ "$last" -ge 3 ] && { TAILN=1 run "$name: migrate" appx "migrate-$name.env" -- db-migrate; check "$name: migration and grants" 0 "$RC"
                         TAILN=2 run "$name: verify" appx "migrate-$name.env" roles.env -- db-verify; log "    (verify exit $RC: the only findings can be the CONNECT of the roles to the databases of earlier stages: none remain, they were removed)"; }
  log "  forward to step $last took $(( $(ms) - t0 )) ms"
  local r0; r0=$(ms)
  [ "$last" -ge 3 ] && { TAILN=1 run "$name: downgrade 0005" appx "migrate-$name.env" -- db-migrate --downgrade 0005; check "$name: downgraded" 0 "$RC"; }
  TAILN=2 run "$name: rollback --remove-roles" appx roles.env -- db-adopt --rollback --remove-roles --apply --database "$db"
  check "$name: rollback succeeded" 0 "$RC"
  docker exec -i "$PG" sh -c 'psql -U asistente -d postgres -v ON_ERROR_STOP=1 -q -f -' < "$TOOLS/restore_public_cluster.sql" > /dev/null 2>&1
  docker exec -i "$PG" sh -c "psql -U asistente -d $db -v ON_ERROR_STOP=1 -q -f -" < "$TOOLS/restore_public_schema.sql" > /dev/null 2>&1
  log "  rollback took $(( $(ms) - r0 )) ms"
  snap_db "$db" "$RUN/$name-s1-db.txt"; snap_cluster "$RUN/$name-s1-cluster.txt"
  check "$name: database identical to S0 (ownership, grants, defaults, rows; default ACL representation normalised)" IDENTICAL "$(NORMALIZE=1 bash "$TOOLS/compare_snapshots.sh" "$RUN/$name-s0-db.txt" "$RUN/$name-s1-db.txt" | grep -o IDENTICAL)"
  check "$name: cluster identical to S0 (roles, memberships, settings, database owners)" IDENTICAL "$(NORMALIZE=1 bash "$TOOLS/compare_snapshots.sh" "$RUN/$name-s0-cluster.txt" "$RUN/$name-s1-cluster.txt" | grep -o IDENTICAL)"
  check "$name: only the original administrator exists again" asistente "$(sqlc postgres "select string_agg(rolname, ',' order by rolname) from pg_roles where rolname !~ '^pg_'")"
  sqlc postgres "DROP DATABASE $db WITH (FORCE)" > /dev/null
}
stage after-bootstrap 1
stage after-adoption 2
stage after-migration 3

log "=== result: $PASS checks passed, $FAIL failed (of $N)"
[ "$FAIL" = "0" ]
