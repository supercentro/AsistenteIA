#!/usr/bin/env bash
# Group 17 final preflight, part 2: restore the SECOND copy of the new backup into a disposable cluster and compare it with
# the source snapshot taken by run_17c_backup.sh (kept in G17C_TMP/pre). Nothing real is touched: the disposable cluster has
# its own network, tmpfs data, no published port. Waits up to 30 minutes for 8 GB of free memory.
#
#   G17C_SECOND=<second folder> G17C_TMP=<folder with pre/> G17C_NAME=<dump file name> bash run_17c_restore.sh
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
S17A="$HERE/../group-17a"; TOOLS="$S17A/tools"
OUT="$HERE/g17c-restore-output.txt"
SECOND="${G17C_SECOND:?}"; TMP="${G17C_TMP:?}"; NAME="${G17C_NAME:?}"; DB=asistenteia
[ -f "$SECOND/$NAME" ] && [ -f "$TMP/pre/snapshot-db.txt" ] || { echo "second copy or source snapshot missing"; exit 2; }
: > "$OUT"
log() { echo "$@" | tee -a "$OUT"; }
PASS=0; FAIL=0; N=0
check() { N=$((N+1)); if [ "$2" = "$3" ]; then PASS=$((PASS+1)); log "  [$N] PASS $1 | expected $2, obtained $3"; else FAIL=$((FAIL+1)); log "  [$N] FAIL $1 | expected $2, obtained $3"; fi; }
ms() { echo $(( $(date +%s%N) / 1000000 )); }
BKNET="g17cnet$$"; BKC="g17cpg$$"; LABEL="purpose=g17c-restore"
cleanup() { docker rm -f "$BKC" > /dev/null 2>&1; docker network rm "$BKNET" > /dev/null 2>&1
  log "after cleanup: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l)"; }
trap cleanup EXIT
log "=== restore of the second copy $(date -u +%FT%TZ); repo HEAD $(cd "$REPO" && git rev-parse --short HEAD)"
check "the second copy has the recorded sha256" "$(cut -d' ' -f1 "$SECOND/$NAME.sha256")" "$(sha256sum "$SECOND/$NAME" | cut -d' ' -f1)"
for i in $(seq 1 90); do F=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d ''); python -c "import sys; sys.exit(0 if float('$F')>=8.0 else 1)" && break; sleep 20; done
log "  free RAM $F GB (8 needed)"
python -c "import sys; sys.exit(0 if float('$F')>=8.0 else 1)" || { log "RAM below 8 GB after 30 minutes: stop (NO-GO for the restore)"; exit 5; }
PW="$(python -c "import secrets;print(secrets.token_hex(12))")"
docker network create --label "$LABEL" "$BKNET" > /dev/null
docker run -d --name "$BKC" --label "$LABEL" --network "$BKNET" -m 1g --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres pgvector/pgvector:0.8.7-pg15 > /dev/null
for _ in $(seq 1 60); do docker exec "$BKC" pg_isready -h 127.0.0.1 -U asistente > /dev/null 2>&1 && break; sleep 1; done; sleep 2
log "  disposable cluster: $(docker exec "$BKC" psql -U asistente -d postgres -Atc 'select version()' | cut -c1-40), published ports [$(docker port "$BKC" | tr '\n' ' ')], mounts $(docker inspect "$BKC" --format '{{len .Mounts}}'), network $BKNET only"
docker cp "$SECOND/$NAME" "$BKC:/tmp/restore.dump"
docker exec "$BKC" createdb -U asistente "$DB"
T0=$(ms); docker exec "$BKC" pg_restore -U asistente -d "$DB" --exit-on-error /tmp/restore.dump; RC=$?
log "  pg_restore rc=$RC in $(( $(ms) - T0 )) ms"
check "pg_restore succeeded" 0 "$RC"
docker exec -i "$BKC" sh -c 'psql -U asistente -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" > "$TMP/restored.txt" 2>&1
check "the restored copy is IDENTICAL to the source (revision, schema, owners, table/column/schema ACLs, constraints, defaults, enum types, row counts)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$TMP/pre/snapshot-db.txt" "$TMP/restored.txt" | grep -o IDENTICAL)"
log "  restored: revision $(grep '^revision|' "$TMP/restored.txt" | cut -d'|' -f2); owners $(grep '^table|' "$TMP/restored.txt" | sed -E 's/^table\|([a-z_]+) owner=([a-z_]+).*/\1=\2/' | tr '\n' ' '); table ACLs $(grep '^table|' "$TMP/restored.txt" | grep -o 'acl=[^ ]*' | sort | uniq -c | tr '\n' ' '); rows $(grep '^rows|' "$TMP/restored.txt" | cut -d'|' -f2 | tr '\n' ' ')"
check "the revision, the owners and the row counts of the restored copy are those of the expected 0005" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$S17A/expected/snapshot-db-0005.txt" "$TMP/restored.txt" | grep -o IDENTICAL)"
mkdir -p "$HERE/evidence"
# Only the restored snapshot is written here: the source evidence belongs to the backup run (a rerun must not overwrite it).
cp "$TMP/restored.txt" "$HERE/evidence/restored-snapshot-db.txt"
log "=== result: $PASS checks passed, $FAIL failed (of $N); backup file name: $NAME; sha256 $(sha256sum "$SECOND/$NAME" | cut -d' ' -f1)"
[ "$FAIL" = 0 ]
