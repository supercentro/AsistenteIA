#!/usr/bin/env bash
# Group 17: a NEW backup of the development database at 0005 (read only on PostgreSQL), two independent copies with their
# own integrity files and verified permissions, and the proof of restorability in a disposable cluster.
#
#   G17C_BACKUPS=<folder outside the repository> G17C_SECOND=<second, independent folder> G17C_TMP=<empty temp folder> bash run_17c_backup.sh
#
# Source stack: only READS. `docker inspect`, read-only SQL sessions (default_transaction_read_only=on), `pg_dump` (a read)
# and one file written in the source container's /tmp (removed by the EXIT trap, also on a failure). No role, grant,
# schema, service or env file is touched. Nothing is printed except file NAMES, hashes, counts and verdicts.
#
# Fail closed: an integrity, permission or manifest problem stops the run at once (`require`); the files this run created
# and did not verify are removed by the trap (never a pre-existing file); an interruption (Ctrl+C, TERM) does the same.
#
# Synthetic rehearsal (run_17c_synthetic_e2e.sh): the same script against a disposable source, selected by
#   G17C_SOURCE=<container> G17C_EXPECTED_PROJECT=<compose project label> G17C_EXPECTED_DIR=<baseline folder>
#   G17C_FAIL_AT=<copy|manifest|interrupt> (test hooks: a corrupted copy, a corrupted manifest, a simulated Ctrl+C).
# The hooks are refused against the real source container.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
S17A="$HERE/../group-17a"
TOOLS="$S17A/tools"
MANIFEST="$(cygpath -w "$HERE/tools/backup_manifest.py")"   # a Windows path: python.exe does not understand MSYS paths
FILE_ACL="$(cygpath -w "$HERE/tools/secure_file_acl.ps1")"
FOLDER_ACL="$(cygpath -w "$HERE/tools/secure_folder_acl.ps1")"
OUT="${G17C_OUT:-$HERE/g17c-backup-output.txt}"
BACKUPS="${G17C_BACKUPS:?}"; SECOND="${G17C_SECOND:?}"; TMP="${G17C_TMP:?}"
REAL="${G17C_SOURCE:-asistenteia-db-1}"; DB=asistenteia
EXPECTED_PROJECT="${G17C_EXPECTED_PROJECT:-asistenteia}"; EXPECTED="${G17C_EXPECTED_DIR:-$S17A/expected}"
MIN_RAM_GB="${G17C_MIN_RAM_GB:-8}"
FAIL_AT="${G17C_FAIL_AT:-}"
if [ -n "$FAIL_AT" ] && [ "$REAL" = "asistenteia-db-1" ]; then echo "test hooks are refused against the real source"; exit 2; fi
mkdir -p "$BACKUPS" "$SECOND" "$TMP"
[ -z "$(ls -A "$TMP" 2>/dev/null)" ] || { echo "G17C_TMP must be empty"; exit 2; }
case "$(cd "$TMP" && pwd)" in "$REPO"*) echo "temp folder must be outside the repository"; exit 2;; esac
[ "$(cd "$BACKUPS" && pwd)" != "$(cd "$SECOND" && pwd)" ] || { echo "the two copies must go to different folders"; exit 2; }
: > "$OUT"
log() { echo "$@" | tee -a "$OUT"; }
PASS=0; FAIL=0; N=0
check() { N=$((N+1)); if [ "$2" = "$3" ]; then PASS=$((PASS+1)); log "  [$N] PASS $1 | expected $2, obtained $3"; else FAIL=$((FAIL+1)); log "  [$N] FAIL $1 | expected $2, obtained $3"; fi; }
require() { check "$@"; [ "$2" = "$3" ] || { log "STOP: a required check failed (fail closed); the files of this run are removed"; exit 6; }; }
ms() { echo $(( $(date +%s%N) / 1000000 )); }
BKNET="g17cnet$$"; BKC="g17cpg$$"; LABEL="purpose=g17c-restore"
NEW_FILES=(); VERIFIED=0; DUMP_IN_SOURCE=0
cleanup() {
  code=$?
  docker rm -f "$BKC" > /dev/null 2>&1; docker network rm "$BKNET" > /dev/null 2>&1
  [ "$DUMP_IN_SOURCE" = 1 ] && docker exec "$REAL" rm -f /tmp/asistenteia_pre_17b.dump > /dev/null 2>&1   # only a dump THIS run created, also on a failure
  if [ "$VERIFIED" = 0 ] && [ "${#NEW_FILES[@]}" -gt 0 ]; then
    for f in "${NEW_FILES[@]}"; do [ -e "$f" ] && { icacls "$(cygpath -w "$f")" /reset > /dev/null 2>&1; rm -f "$f"; }; done
    log "cleanup: the ${#NEW_FILES[@]} file(s) created by this run were NOT verified and have been removed (exit code $code)"
  fi
  log "after cleanup: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l); new files left=$(for f in "${NEW_FILES[@]}"; do [ -e "$f" ] && echo x; done | wc -l)"
  rm -rf "$TMP"/restore.dump "$TMP"/pw.txt
}
trap cleanup EXIT
trap 'log "interrupted"; exit 130' INT TERM
hook() { [ "$FAIL_AT" = "$1" ] || return 0; log "  (test hook: $1)"; case "$1" in interrupt) kill -INT $$; sleep 5;; acl_done) exit 7;; esac; }

log "=== group 17 backup $(date -u +%FT%TZ); repo HEAD $(cd "$REPO" && git rev-parse --short HEAD); source container $REAL"
log "=== 1 identity of the server, the database and the revision (read only)"
bash "$TOOLS/preflight_readonly.sh" "$REAL" "$DB" "$TMP/pre" > "$TMP/preflight.out" 2>&1 || { sed 's/^/  /' "$TMP/preflight.out" | tail -3 | tee -a "$OUT"; log "STOP: the read-only preflight failed"; exit 6; }
sed -n 's/^\(connected_database\|connected_user\|read_only_session\|state\|compose_project\|image\|databases\|free_ram_gb\|free_disk_gb_where_the_output_goes\)|/  \1: /p' "$TMP/pre/identity.txt" | tee -a "$OUT"
sed 's/^/  /' "$TMP/preflight.out" | grep -E "open_transactions|idle_in|prepared|ungranted|long_running|clients_by|login_roles|revision" | tee -a "$OUT"
require "connected to the source database as the original administrator, read only" "asistenteia|asistente|on" "$(grep -E '^(connected_database|connected_user|read_only_session)\|' "$TMP/pre/identity.txt" | cut -d'|' -f2 | paste -sd'|')"
require "the container is the expected one (compose project $EXPECTED_PROJECT)" "$EXPECTED_PROJECT" "$(grep '^compose_project|' "$TMP/pre/identity.txt" | cut -d'|' -f2)"
require "revision 0005" "revision|0005" "$(grep '^revision|' "$TMP/pre/snapshot-db.txt")"
require "no open transaction, no idle in transaction, no prepared transaction, no ungranted lock" "0|0|0|0" "$(grep -E '^(open_transactions_older_than_1_min|idle_in_transaction|prepared_transactions|ungranted_locks)\|' "$TMP/pre/activity.txt" | cut -d'|' -f2 | paste -sd'|')"
require "GATE D: the catalog of the source database equals the expected baseline of 0005" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$EXPECTED/snapshot-db-0005.txt" "$TMP/pre/snapshot-db.txt" | grep -o IDENTICAL)"
require "GATE D: the cluster (roles, databases, ACLs) equals the expected baseline" "IDENTICAL" "$(MIN_LINES=5 bash "$TOOLS/compare_snapshots.sh" "$EXPECTED/snapshot-cluster.txt" "$TMP/pre/snapshot-cluster.txt" | grep -o IDENTICAL)"
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$REAL" sh -c 'psql -U "$POSTGRES_USER" -d asistenteia_test -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" > "$TMP/pre/snapshot-test-db.txt" 2>&1
check "asistenteia_test equals the expected baseline (informative: its public schema owner differs after the fixtures)" "IDENTICAL" "$(MIN_LINES=5 bash "$TOOLS/compare_snapshots.sh" "$EXPECTED/snapshot-test-db.txt" "$TMP/pre/snapshot-test-db.txt" | grep -o IDENTICAL)"
log "  rows of the source database: $(grep '^rows|' "$TMP/pre/snapshot-db.txt" | cut -d'|' -f2 | tr '\n' ' ')"

log "=== 2 the destination folders: policy verified, nothing overwritten"
for d in "$BACKUPS" "$SECOND"; do
  line="$(powershell -NoProfile -ExecutionPolicy Bypass -File "$FOLDER_ACL" -Path "$(cygpath -w "$d")" -VerifyOnly 2>&1 | tail -1)"; log "  $line"
  case "$line" in "FOLDER ACL OK"*) ;; *) [ "${G17C_REQUIRE_FOLDER_POLICY:-0}" = 1 ] && { log "STOP: the folder does not carry the minimal policy and G17C_REQUIRE_FOLDER_POLICY=1"; exit 6; }; log "  (warning) the folder does not carry the minimal policy (secure_folder_acl.ps1); set G17C_REQUIRE_FOLDER_POLICY=1 to make this a stop";; esac
done
STAMP=$(date -u +%Y%m%dT%H%M%SZ); NAME="asistenteia_pre_17b_$STAMP.dump"
for existing in "$BACKUPS"/asistenteia_pre_17b_*.dump "$SECOND"/asistenteia_pre_17b_*.dump; do [ -e "$existing" ] && { log "a 17b backup already exists in a destination folder: not overwriting (move it away or choose another folder)"; exit 3; }; done
BASELINE_OK=0; BASELINE_N=0
for shaf in "$BACKUPS"/*.sha256 "$SECOND"/*.sha256; do   # every pre-existing integrity file still matches its dump (old or new format)
  [ -e "$shaf" ] || continue; BASELINE_N=$((BASELINE_N+1)); dump="${shaf%.sha256}"
  [ "$(sha256sum "$dump" | cut -d' ' -f1)" = "$(head -1 "$shaf" | cut -d' ' -f1)" ] && BASELINE_OK=$((BASELINE_OK+1))
done
require "the pre-existing backups are untouched (their hashes equal the recorded ones)" "$BASELINE_N" "$BASELINE_OK"

log "=== 3 the dump (a read) inside the container, two copies, integrity files, permissions"
T0=$(ms)
docker exec "$REAL" test ! -e /tmp/asistenteia_pre_17b.dump || { log "STOP: /tmp/asistenteia_pre_17b.dump already exists in the source container; not touching it"; exit 3; }
DUMP_IN_SOURCE=1
docker exec "$REAL" sh -c 'pg_dump -U "$POSTGRES_USER" -d asistenteia -Fc -f /tmp/asistenteia_pre_17b.dump' || { log "STOP: pg_dump failed"; exit 4; }
INSIDE="$(docker exec "$REAL" sha256sum /tmp/asistenteia_pre_17b.dump | cut -d' ' -f1)"
LINES="$(docker exec "$REAL" sh -c 'pg_restore --list /tmp/asistenteia_pre_17b.dump | wc -l')"
NEW_FILES+=("$BACKUPS/$NAME"); docker cp "$REAL:/tmp/asistenteia_pre_17b.dump" "$BACKUPS/$NAME"
OUTSIDE="$(sha256sum "$BACKUPS/$NAME" | cut -d' ' -f1)"
log "  dump taken and copied in $(( $(ms) - T0 )) ms; size $(stat -c %s "$BACKUPS/$NAME") bytes; pg_restore --list lines: $LINES"
require "sha256 outside equals sha256 inside the container" "$INSIDE" "$OUTSIDE"
NEW_FILES+=("$SECOND/$NAME"); cp "$BACKUPS/$NAME" "$SECOND/$NAME"
hook interrupt
[ "$FAIL_AT" = copy ] && { log "  (test hook: copy)"; printf 'x' >> "$SECOND/$NAME"; }
require "the second, independent copy has the same sha256" "$OUTSIDE" "$(sha256sum "$SECOND/$NAME" | cut -d' ' -f1)"
PGV="$(docker exec "$REAL" pg_dump --version | sed -E 's/[^0-9. ]//g; s/^ +//')"
ROWS="$(grep '^rows|' "$TMP/pre/snapshot-db.txt" | cut -d'|' -f2 | tr '\n' ' ' | sed 's/ $//')"
META=(--meta "database=asistenteia development" --meta "alembic_revision=0005" --meta "format=pg_dump custom (-Fc) $PGV" --meta "toc_lines=$LINES" --meta "rows=$ROWS" --meta "source=read-only pg_dump of the source container, services untouched" --meta "restore_test=reports group-17c g17c-backup-output.txt")
for pair in "$BACKUPS|primary" "$SECOND|second"; do
  d="${pair%|*}"; label="${pair#*|}"
  NEW_FILES+=("$d/$NAME.sha256" "$d/$NAME.manifest.txt")
  line="$(python -I "$MANIFEST" write "$(cygpath -w "$d")" "$NAME" --copy "$label" "${META[@]}" 2>&1 | tail -1)"
  case "$line" in MANIFEST*) log "  $line";; *) log "  (the manifest tool failed; its message is withheld: it may hold a path)"; line="MANIFEST ERROR";; esac
  require "the integrity files of the $label copy were written" "MANIFEST OK" "$(echo "$line" | cut -c1-11)"
done
[ "$FAIL_AT" = manifest ] && { log "  (test hook: manifest)"; sed -i 's/^size: /size: 9/' "$SECOND/$NAME.manifest.txt"; }
for pair in "$BACKUPS|primary" "$SECOND|second"; do
  d="${pair%|*}"; label="${pair#*|}"
  line="$(python -I "$MANIFEST" verify "$(cygpath -w "$d")" "$NAME" --copy "$label" 2>&1 | tail -1)"
  case "$line" in MANIFEST*) log "  $line";; *) log "  (the manifest tool failed; its message is withheld: it may hold a path)"; line="MANIFEST ERROR";; esac
  require "the $label copy verifies against its own .sha256 and manifest" "MANIFEST OK" "$(echo "$line" | cut -c1-11)"
done
ACL_OK=0
for f in "$BACKUPS/$NAME" "$BACKUPS/$NAME.sha256" "$BACKUPS/$NAME.manifest.txt" "$SECOND/$NAME" "$SECOND/$NAME.sha256" "$SECOND/$NAME.manifest.txt"; do
  line="$(powershell -NoProfile -ExecutionPolicy Bypass -File "$FILE_ACL" -Path "$(cygpath -w "$f")" 2>&1 | tail -1)"
  log "  $line"; case "$line" in "ACL OK"*) ACL_OK=$((ACL_OK+1));; esac
done
require "the six backup files (both copies) carry the verified restrictive descriptor" 6 "$ACL_OK"
hook acl_done   # test hook: a failure AFTER the files became read-only for their owner
docker exec "$REAL" rm -f /tmp/asistenteia_pre_17b.dump; DUMP_IN_SOURCE=0
snapshot_after() { docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$REAL" sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" 2>&1; }
snapshot_after > "$TMP/post-dump.txt"
require "the source did not change while the dump was taken (snapshot after = snapshot before)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$TMP/pre/snapshot-db.txt" "$TMP/post-dump.txt" | grep -o IDENTICAL)"
VERIFIED=1
log "  the two copies are complete and verified: from here on the trap keeps them"

log "=== 4 restore of the SECOND copy into a disposable cluster (waits for $MIN_RAM_GB GB of free memory)"
for i in $(seq 1 40); do F=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r'); python -c "import sys; sys.exit(0 if float('$F')>=float('$MIN_RAM_GB') else 1)" && break; sleep 15; done
log "  free RAM $F GB ($MIN_RAM_GB needed)"
python -c "import sys; sys.exit(0 if float('$F')>=float('$MIN_RAM_GB') else 1)" || { log "RAM below $MIN_RAM_GB GB: stop (the copies are kept; run run_17c_restore.sh later)"; exit 5; }
PW="$(python -c "import secrets;print(secrets.token_hex(12))")"
docker network create --label "$LABEL" "$BKNET" > /dev/null
docker run -d --name "$BKC" --label "$LABEL" --network "$BKNET" -m 1g --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres pgvector/pgvector:0.8.7-pg15 > /dev/null
for _ in $(seq 1 60); do docker exec "$BKC" pg_isready -h 127.0.0.1 -U asistente > /dev/null 2>&1 && break; sleep 1; done; sleep 2
log "  disposable cluster: $(docker exec "$BKC" psql -U asistente -d postgres -Atc 'select version()' | cut -c1-40), published ports [$(docker port "$BKC" | tr '\n' ' ')], mounts $(docker inspect "$BKC" --format '{{len .Mounts}}'), network $BKNET only"
python -I "$MANIFEST" verify "$(cygpath -w "$SECOND")" "$NAME" --copy second > /dev/null || { log "STOP: the second copy no longer verifies"; exit 6; }
docker cp "$SECOND/$NAME" "$BKC:/tmp/restore.dump"
docker exec "$BKC" createdb -U asistente "$DB"
T0=$(ms); docker exec "$BKC" pg_restore -U asistente -d "$DB" --exit-on-error /tmp/restore.dump; RC=$?
log "  pg_restore rc=$RC in $(( $(ms) - T0 )) ms"
check "pg_restore succeeded" 0 "$RC"
docker exec -i "$BKC" sh -c 'psql -U asistente -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" > "$TMP/restored.txt" 2>&1
check "the restored copy is IDENTICAL to the source (revision, schema, owners, table/column/schema ACLs, constraints, defaults, enum types, row counts)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$TMP/pre/snapshot-db.txt" "$TMP/restored.txt" | grep -o IDENTICAL)"
log "  restored: revision $(grep '^revision|' "$TMP/restored.txt" | cut -d'|' -f2); owners $(grep '^table|' "$TMP/restored.txt" | sed -E 's/^table\|([a-z_]+) owner=([a-z_]+).*/\1=\2/' | tr '\n' ' '); table ACLs $(grep '^table|' "$TMP/restored.txt" | grep -o 'acl=[^ ]*' | sort | uniq -c | tr '\n' ' '); rows $(grep '^rows|' "$TMP/restored.txt" | cut -d'|' -f2 | tr '\n' ' ')"
check "the revision, the owners and the row counts of the restored copy are those of the expected 0005" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$EXPECTED/snapshot-db-0005.txt" "$TMP/restored.txt" | grep -o IDENTICAL)"
EVID="${G17C_EVIDENCE:-$HERE/evidence}"; mkdir -p "$EVID"
cp "$TMP/pre/snapshot-db.txt" "$EVID/source-snapshot-db.txt"; cp "$TMP/pre/snapshot-cluster.txt" "$EVID/source-snapshot-cluster.txt"; cp "$TMP/pre/activity.txt" "$EVID/source-activity.txt"
grep -v '^mounts_json|' "$TMP/pre/identity.txt" | grep -v '^container_id|' > "$EVID/source-identity.txt"
cp "$TMP/restored.txt" "$EVID/restored-snapshot-db.txt"
log "=== result: $PASS checks passed, $FAIL failed (of $N); backup file name: $NAME; sha256 $OUTSIDE"
[ "$FAIL" = 0 ]
