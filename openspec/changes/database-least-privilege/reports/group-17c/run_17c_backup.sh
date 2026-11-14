#!/usr/bin/env bash
# Group 17 final preflight: a NEW backup of the development database at 0005 (read only on PostgreSQL) and its
# proof of restorability in a disposable cluster.
#
#   G17C_BACKUPS=<folder outside the repository> G17C_SECOND=<second, independent folder> G17C_TMP=<empty temp folder> bash run_17c_backup.sh
#
# Real stack: only READS. `docker inspect`, read-only SQL sessions (default_transaction_read_only=on), `pg_dump`
# (a read), and one file written in the container's /tmp (removed at the end). No role, grant, schema, service or
# env file is touched. The dump is stored outside the repository with the permissions of its owner only; a second
# copy goes to an independent folder; nothing is printed except file NAMES, hashes, counts and verdicts.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
S17A="$HERE/../group-17a"
TOOLS="$S17A/tools"
OUT="$HERE/g17c-backup-output.txt"
BACKUPS="${G17C_BACKUPS:?}"; SECOND="${G17C_SECOND:?}"; TMP="${G17C_TMP:?}"
REAL=asistenteia-db-1; DB=asistenteia
mkdir -p "$BACKUPS" "$SECOND" "$TMP"
[ -z "$(ls -A "$TMP" 2>/dev/null)" ] || { echo "G17C_TMP must be empty"; exit 2; }
case "$(cd "$TMP" && pwd)" in "$REPO"*) echo "temp folder must be outside the repository"; exit 2;; esac
TMPW="$(cd "$TMP" && pwd -W)"
: > "$OUT"
log() { echo "$@" | tee -a "$OUT"; }
PASS=0; FAIL=0; N=0
check() { N=$((N+1)); if [ "$2" = "$3" ]; then PASS=$((PASS+1)); log "  [$N] PASS $1 | expected $2, obtained $3"; else FAIL=$((FAIL+1)); log "  [$N] FAIL $1 | expected $2, obtained $3"; fi; }
ms() { echo $(( $(date +%s%N) / 1000000 )); }
BKNET="g17cnet$$"; BKC="g17cpg$$"; LABEL="purpose=g17c-restore"
cleanup() { docker rm -f "$BKC" > /dev/null 2>&1; docker network rm "$BKNET" > /dev/null 2>&1
  docker exec "$REAL" rm -f /tmp/asistenteia_pre_17b.dump > /dev/null 2>&1   # also on a failure: no dump is left in the real container
  log "after cleanup: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l)"
  rm -rf "$TMP"/restore.dump "$TMP"/pw.txt; }
trap cleanup EXIT

log "=== 17 final preflight, new backup $(date -u +%FT%TZ); repo HEAD $(cd "$REPO" && git rev-parse --short HEAD)"
log "=== 1 identity of the server, the database and the revision (read only)"
bash "$TOOLS/preflight_readonly.sh" "$REAL" "$DB" "$TMP/pre" > "$TMP/preflight.out" 2>&1
sed -n 's/^\(connected_database\|connected_user\|read_only_session\|state\|compose_project\|image\|databases\|free_ram_gb\|free_disk_gb_where_the_output_goes\)|/  \1: /p' "$TMP/pre/identity.txt" | tee -a "$OUT"
sed 's/^/  /' "$TMP/preflight.out" | grep -E "open_transactions|idle_in|prepared|ungranted|long_running|clients_by|login_roles|revision" | tee -a "$OUT"
check "connected to the development database as the original administrator, read only" "asistenteia|asistente|on" "$(grep -E '^(connected_database|connected_user|read_only_session)\|' "$TMP/pre/identity.txt" | cut -d'|' -f2 | paste -sd'|')"
check "the container is the development one (compose project asistenteia)" "asistenteia" "$(grep '^compose_project|' "$TMP/pre/identity.txt" | cut -d'|' -f2)"
check "revision 0005" "revision|0005" "$(grep '^revision|' "$TMP/pre/snapshot-db.txt")"
check "no open transaction, no idle in transaction, no prepared transaction, no ungranted lock" "0|0|0|0" "$(grep -E '^(open_transactions_older_than_1_min|idle_in_transaction|prepared_transactions|ungranted_locks)\|' "$TMP/pre/activity.txt" | cut -d'|' -f2 | paste -sd'|')"
check "GATE D: the catalog of the real database equals the expected baseline of 0005" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$S17A/expected/snapshot-db-0005.txt" "$TMP/pre/snapshot-db.txt" | grep -o IDENTICAL)"
check "GATE D: the cluster (roles, databases, ACLs) equals the expected baseline" "IDENTICAL" "$(MIN_LINES=5 bash "$TOOLS/compare_snapshots.sh" "$S17A/expected/snapshot-cluster.txt" "$TMP/pre/snapshot-cluster.txt" | grep -o IDENTICAL)"
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$REAL" sh -c 'psql -U "$POSTGRES_USER" -d asistenteia_test -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" > "$TMP/pre/snapshot-test-db.txt" 2>&1
check "asistenteia_test equals the expected baseline" "IDENTICAL" "$(MIN_LINES=5 bash "$TOOLS/compare_snapshots.sh" "$S17A/expected/snapshot-test-db.txt" "$TMP/pre/snapshot-test-db.txt" | grep -o IDENTICAL)"
log "  rows of the real database: $(grep '^rows|' "$TMP/pre/snapshot-db.txt" | cut -d'|' -f2 | tr '\n' ' ')"

log "=== 2 the dump (a read) inside the container, hashes, copies"
STAMP=$(date -u +%Y%m%dT%H%M%SZ); NAME="asistenteia_pre_17b_$STAMP.dump"
for existing in "$BACKUPS"/asistenteia_pre_17b_*.dump; do [ -e "$existing" ] && { log "a 17b backup already exists: not overwriting"; exit 3; }; done
T0=$(ms)
docker exec "$REAL" sh -c 'pg_dump -U "$POSTGRES_USER" -d asistenteia -Fc -f /tmp/asistenteia_pre_17b.dump' || { log "pg_dump failed"; exit 4; }
INSIDE="$(docker exec "$REAL" sha256sum /tmp/asistenteia_pre_17b.dump | cut -d' ' -f1)"
LINES="$(docker exec "$REAL" sh -c 'pg_restore --list /tmp/asistenteia_pre_17b.dump | wc -l')"
docker cp "$REAL:/tmp/asistenteia_pre_17b.dump" "$BACKUPS/$NAME"
OUTSIDE="$(sha256sum "$BACKUPS/$NAME" | cut -d' ' -f1)"
log "  dump taken and copied in $(( $(ms) - T0 )) ms; size $(stat -c %s "$BACKUPS/$NAME") bytes; pg_restore --list lines: $LINES"
check "sha256 outside equals sha256 inside the container" "$INSIDE" "$OUTSIDE"
cp "$BACKUPS/$NAME" "$SECOND/$NAME"
check "the second, independent copy has the same sha256" "$OUTSIDE" "$(sha256sum "$SECOND/$NAME" | cut -d' ' -f1)"
# The .sha256 file names the dump by its file NAME only (Git Bash sha256sum prints " *<absolute path>", which would carry the
# user's folder into the evidence and make `sha256sum -c` of the second copy check the first one: review finding of 17C).
echo "$OUTSIDE  $NAME" > "$BACKUPS/$NAME.sha256"; cp "$BACKUPS/$NAME.sha256" "$SECOND/$NAME.sha256"
check "the .sha256 file holds the hash and the file name only" "$OUTSIDE  $NAME" "$(cat "$BACKUPS/$NAME.sha256")"
{ echo "Backup manifest (no data inside; the dump itself is private)"
  echo "file:            $NAME"
  echo "created (UTC):   $STAMP"
  echo "database:        asistenteia (development), alembic revision 0005"
  echo "format:          pg_dump -Fc (custom), $(docker exec "$REAL" pg_dump --version | cut -c1-40)"
  echo "size (bytes):    $(stat -c %s "$BACKUPS/$NAME")"
  echo "sha256:          $OUTSIDE"
  echo "toc lines:       $LINES (pg_restore --list)"
  echo "rows:            $(grep '^rows|' "$TMP/pre/snapshot-db.txt" | cut -d'|' -f2 | tr '\n' ' ')"
  echo "source:          container $REAL (compose project asistenteia), read-only dump, services untouched"
  echo "restore test:    see reports/group-17c/g17c-backup-output.txt"
} > "$BACKUPS/$NAME.manifest.txt"
cp "$BACKUPS/$NAME.manifest.txt" "$SECOND/$NAME.manifest.txt"
# Restrictive permissions, verified: tools/secure_file_acl.ps1 removes the inheritance, leaves one rule (current user,
# Read), re-reads the descriptor and fails closed. (The first version built an icacls command inside a PowerShell string,
# where "$env:USERNAME:(R)" expands to "(R)"; icacls rejected it and the error was discarded, so the dumps kept their
# inherited ACLs. Found in the final preflight, fixed in 17C.)
ACL_OK=0
for f in "$BACKUPS/$NAME" "$BACKUPS/$NAME.sha256" "$BACKUPS/$NAME.manifest.txt" "$SECOND/$NAME" "$SECOND/$NAME.sha256" "$SECOND/$NAME.manifest.txt"; do
  line="$(powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/tools/secure_file_acl.ps1")" -Path "$(cygpath -w "$f")" 2>&1 | tail -1)"
  log "  $line"; case "$line" in "ACL OK"*) ACL_OK=$((ACL_OK+1));; esac
done
check "the six backup files (both copies) carry the verified restrictive descriptor" 6 "$ACL_OK"
check "the pre_0005 backup is untouched (its hash equals the recorded one)" "OK" "$( [ "$(sha256sum "$BACKUPS/asistenteia_pre_0005_20261112T034241Z.dump" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$BACKUPS/asistenteia_pre_0005_20261112T034241Z.dump.sha256")" ] && echo OK || echo CHANGED )"
docker exec "$REAL" rm -f /tmp/asistenteia_pre_17b.dump
snapshot_after() { docker exec -i "$REAL" sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -c "SET default_transaction_read_only=on" -f -' < "$TOOLS/snapshot_db.sql" 2>&1; }
snapshot_after > "$TMP/post-dump.txt"
grep -v '^SET$' "$TMP/pre/snapshot-db.txt" > "$TMP/pre-clean.txt"; grep -v '^SET$' "$TMP/post-dump.txt" > "$TMP/post-clean.txt"
check "the source did not change while the dump was taken (snapshot after = snapshot before)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$TMP/pre-clean.txt" "$TMP/post-clean.txt" | grep -o IDENTICAL)"

log "=== 3 restore of the SECOND copy into a disposable cluster (waits for 8 GB of free memory)"
for i in $(seq 1 40); do F=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r'); python -c "import sys; sys.exit(0 if float('$F')>=8.0 else 1)" && break; sleep 15; done
log "  free RAM $F GB (8 needed)"
python -c "import sys; sys.exit(0 if float('$F')>=8.0 else 1)" || { log "RAM below 8 GB: stop (NO-GO for the restore)"; exit 5; }
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
cp "$TMP/pre/snapshot-db.txt" "$HERE/evidence/source-snapshot-db.txt"; cp "$TMP/pre/snapshot-cluster.txt" "$HERE/evidence/source-snapshot-cluster.txt"; cp "$TMP/pre/activity.txt" "$HERE/evidence/source-activity.txt"
grep -v '^mounts_json|' "$TMP/pre/identity.txt" | grep -v '^container_id|' > "$HERE/evidence/source-identity.txt"
cp "$TMP/restored.txt" "$HERE/evidence/restored-snapshot-db.txt"
log "=== result: $PASS checks passed, $FAIL failed (of $N); backup file name: $NAME; sha256 $OUTSIDE"
[ "$FAIL" = 0 ]
