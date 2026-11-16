#!/usr/bin/env bash
# Group 17A: generate the EXPECTED snapshots of the development database at revision 0005 (gate D of the
# checklist), from the verified backup (revision 0004) brought to 0005 as the original administrator, in a
# disposable cluster built like the development one (database `asistenteia` created by POSTGRES_DB and
# `asistenteia_test` by the real `docker/db-init` script, a single administrator role).
#
#   G17A_BACKUP=<dump> G17A_RUN_DIR=<empty directory OUTSIDE the repository> bash run_17a_baseline.sh
#
# Output: reports/group-17a/expected/{snapshot-db-0005.txt,snapshot-test-db.txt,snapshot-cluster.txt}
# Gate D compares the read-only snapshots of the REAL database with these files (compare_snapshots.sh).
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
TOOLS="$HERE/tools"
EXPECTED="$HERE/expected"
RUN="${G17A_RUN_DIR:?set G17A_RUN_DIR to an empty directory OUTSIDE the repository}"
BACKUP="${G17A_BACKUP:?set G17A_BACKUP to the verified dump of revision 0004}"
mkdir -p "$RUN" "$EXPECTED"
[ -z "$(ls -A "$RUN" 2>/dev/null)" ] || { echo "G17A_RUN_DIR must be an empty directory"; exit 2; }
case "$(cd "$RUN" && pwd)" in "$REPO"*) echo "G17A_RUN_DIR must be outside the repository"; exit 2;; esac
RUNW="$(cd "$RUN" && pwd -W)"
SUF=$$; NET="g17bsnet$SUF"; PG="g17bspg$SUF"; LABEL="purpose=g17a-baseline"; IMG_API="asistenteia-backend:g17a-baseline"
SHA="$(sha256sum "$BACKUP" | cut -d' ' -f1)"
[ "$SHA" = "$(cut -d' ' -f1 "$BACKUP.sha256")" ] || { echo "the backup does not match its recorded sha256"; exit 3; }
FREE=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
python -c "import sys; sys.exit(0 if float('$FREE') >= 8 else 1)" || { echo "RAM below 8 GB ($FREE): stop"; exit 4; }
cleanup() { docker rm -f "$PG" > /dev/null 2>&1; docker network rm "$NET" > /dev/null 2>&1; docker rmi "$IMG_API" > /dev/null 2>&1; }
trap cleanup EXIT
PA=$(python -c "import secrets;print(secrets.token_hex(12))")
docker build -q --target api -t "$IMG_API" "$(cd "$REPO/backend" && pwd -W)" > /dev/null || exit 5
docker network create --label "$LABEL" "$NET" > /dev/null
docker run -d --name "$PG" --label "$LABEL" --network "$NET" --network-alias db -m 1g --tmpfs /var/lib/postgresql/data \
  -v "$(cd "$REPO/docker/db-init" && pwd -W):/docker-entrypoint-initdb.d:ro" \
  -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PA" -e POSTGRES_DB=asistenteia pgvector/pgvector:0.8.7-pg15 > /dev/null
for _ in $(seq 1 60); do docker exec "$PG" pg_isready -h 127.0.0.1 -U asistente -d asistenteia > /dev/null 2>&1 && docker exec "$PG" psql -U asistente -d postgres -Atc "select 1 from pg_database where datname='asistenteia_test'" 2>/dev/null | grep -q 1 && break; sleep 1; done
docker cp "$BACKUP" "$PG:/tmp/backup.dump"
docker exec "$PG" pg_restore -U asistente -d asistenteia --exit-on-error /tmp/backup.dump || exit 6
printf 'ADMIN_DB_URL=postgresql+psycopg://asistente:%s@db:5432/asistenteia\n' "$PA" > "$RUN/admin.env"
docker run --rm --network "$NET" --env-file "$RUNW/admin.env" --entrypoint python "$IMG_API" -c "import os; from alembic import command; from app.db_admin.migrate import alembic_config; command.upgrade(alembic_config(os.environ['ADMIN_DB_URL']), '0005')" > /dev/null 2>&1 || exit 7
snap() { docker exec -i "$PG" sh -c "psql -U asistente -d $1 -At -F '|' -v ON_ERROR_STOP=1 -f -" < "$TOOLS/$2"; }
snap asistenteia snapshot_db.sql > "$EXPECTED/snapshot-db-0005.txt"
snap asistenteia_test snapshot_db.sql > "$EXPECTED/snapshot-test-db.txt"
snap postgres snapshot_cluster.sql > "$EXPECTED/snapshot-cluster.txt"
{
  echo "expected snapshots of the development database at revision 0005 (generated $(date -u +%FT%TZ) from the backup with sha256 $SHA)"
  echo "code HEAD: $(cd "$REPO" && git rev-parse --short HEAD)"
  wc -l "$EXPECTED"/snapshot-*.txt
  grep -h '^revision|' "$EXPECTED/snapshot-db-0005.txt"
  grep -h '^rows|' "$EXPECTED/snapshot-db-0005.txt" | tr '\n' ' '; echo
} > "$EXPECTED/README.txt"
cat "$EXPECTED/README.txt"
grep -c -E '^(psql:|ERROR:)' "$EXPECTED"/snapshot-*.txt | grep -v ':0' && { echo "a snapshot holds an error"; exit 8; }
exit 0
