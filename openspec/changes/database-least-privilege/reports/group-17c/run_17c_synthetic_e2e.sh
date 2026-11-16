#!/usr/bin/env bash
# End-to-end rehearsal of run_17c_backup.sh on SYNTHETIC resources (TD-049, group 17C). The real stack is not touched.
#
#   G17C_E2E_ROOT=<empty folder outside the repository> bash run_17c_synthetic_e2e.sh
#
# A disposable PostgreSQL 15.19 + pgvector 0.8.7 plays the source: it receives a restore of the 17b backup's second copy
# (a read of that backup) so that its catalog is the real 0005 one, gets an `asistenteia_test` database and the compose
# project label the script expects; two synthetic backup folders get the minimal folder policy. Then:
#   run 1  happy path: preflight, dump, two copies, independent manifests, file ACLs, restore, equivalence, cleanup
#   run 2  a corrupted second copy (test hook `copy`): must stop at once and remove every file it created
#   run 3  a corrupted manifest (hook `manifest`): must stop at once and remove every file it created
#   run 4  a simulated Ctrl+C after the copies, before verification (hook `interrupt`): must clean up the same way
#   run 4b a failure after the six files became Read-only for their owner (hook `acl_done`): the trap must still remove them
#   run 5  the folder already holds a 17b backup: must refuse without touching anything
# The synthetic folders and cluster are removed at the end; the pgvector image stays.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
TOOLS="$HERE/../group-17a/tools"
ROOT="${G17C_E2E_ROOT:?}"
OUT="$HERE/g17c-synthetic-e2e-output.txt"
mkdir -p "$ROOT"; [ -z "$(ls -A "$ROOT")" ] || { echo "G17C_E2E_ROOT must be empty"; exit 2; }
case "$(cd "$ROOT" && pwd)" in "$REPO"*) echo "the e2e root must be outside the repository"; exit 2;; esac
: > "$OUT"
log() { echo "$@" | tee -a "$OUT"; }
PASS=0; FAIL=0; N=0
check() { N=$((N+1)); if [ "$2" = "$3" ]; then PASS=$((PASS+1)); log "[$N] PASS $1 | expected $2, obtained $3"; else FAIL=$((FAIL+1)); log "[$N] FAIL $1 | expected $2, obtained $3"; fi; }
SRC="g17esrc$$"; NET="g17enet$$"; LABEL="purpose=g17c-e2e"; PROJECT="g17synthetic"
cleanup() { mkdir -p "$HERE/e2e-inner-outputs"; for o in "$ROOT"/out-*.txt; do [ -f "$o" ] && cp "$o" "$HERE/e2e-inner-outputs/$(basename "$o")"; done   # names/hashes/verdicts only
  docker rm -f "$SRC" > /dev/null 2>&1; docker network rm "$NET" > /dev/null 2>&1
  for d in "$ROOT"/*; do [ -d "$d" ] && icacls "$(cygpath -w "$d")" /reset /T > /dev/null 2>&1; done; rm -rf "$ROOT"
  log "e2e cleanup: containers left=$(docker ps -a --filter label=$LABEL -q | wc -l) restore containers left=$(docker ps -a --filter label=purpose=g17c-restore -q | wc -l) networks left=$(docker network ls --filter label=$LABEL -q | wc -l) root removed=$([ -e "$ROOT" ] && echo no || echo yes)"; }
trap cleanup EXIT
SEED="${G17C_SEED_DUMP:?set G17C_SEED_DUMP to the path of the 17b backup copy to seed the synthetic source (read only)}"
[ -f "$SEED" ] || { echo "seed dump not found"; exit 2; }

log "=== synthetic e2e $(date -u +%FT%TZ); repo HEAD $(cd "$REPO" && git rev-parse --short HEAD)"
log "=== 0 the synthetic source and folders"
F=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r'); log "free RAM before: $F GB"
PW="$(python -c "import secrets;print(secrets.token_hex(12))")"
docker network create --label "$LABEL" "$NET" > /dev/null
docker run -d --name "$SRC" --label "$LABEL" --label "com.docker.compose.project=$PROJECT" --network "$NET" -m 1g --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=asistente -e "POSTGRES_PASSWORD=$PW" -e POSTGRES_DB=postgres pgvector/pgvector:0.8.7-pg15 > /dev/null
for _ in $(seq 1 60); do docker exec "$SRC" pg_isready -h 127.0.0.1 -U asistente > /dev/null 2>&1 && break; sleep 1; done; sleep 2
docker cp "$SEED" "$SRC:/tmp/seed.dump"
docker exec "$SRC" createdb -U asistente asistenteia && docker exec "$SRC" createdb -U asistente asistenteia_test
docker exec "$SRC" pg_restore -U asistente -d asistenteia --exit-on-error /tmp/seed.dump; check "the synthetic source holds the restored 0005 catalog" 0 "$?"
docker exec "$SRC" rm -f /tmp/seed.dump
EXP="$ROOT/expected"; mkdir -p "$EXP"
docker exec -i "$SRC" sh -c 'psql -U asistente -d asistenteia -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" > "$EXP/snapshot-db-0005.txt" 2>&1
docker exec -i "$SRC" sh -c 'psql -U asistente -d postgres -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_cluster.sql" > "$EXP/snapshot-cluster.txt" 2>&1
docker exec -i "$SRC" sh -c 'psql -U asistente -d asistenteia_test -At -F "|" -v ON_ERROR_STOP=1 -f -' < "$TOOLS/snapshot_db.sql" > "$EXP/snapshot-test-db.txt" 2>&1
check "the synthetic catalog equals the REAL expected baseline of 0005 (so the rehearsal exercises the real gate D)" "IDENTICAL" "$(bash "$TOOLS/compare_snapshots.sh" "$HERE/../group-17a/expected/snapshot-db-0005.txt" "$EXP/snapshot-db-0005.txt" | grep -o IDENTICAL)"
B1="$ROOT/copy-a"; B2="$ROOT/copy-b"; mkdir -p "$B1" "$B2"
for d in "$B1" "$B2"; do powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$HERE/tools/secure_folder_acl.ps1")" -Path "$(cygpath -w "$d")" | tee -a "$OUT"; done
# a pre-existing backup of another kind, with an integrity file in the OLD format, must survive every run untouched
printf 'older backup' > "$B1/asistenteia_pre_0005_synthetic.dump"; echo "$(sha256sum "$B1/asistenteia_pre_0005_synthetic.dump" | cut -d' ' -f1) *C:/somewhere/asistenteia_pre_0005_synthetic.dump" > "$B1/asistenteia_pre_0005_synthetic.dump.sha256"
OLD_HASH="$(sha256sum "$B1/asistenteia_pre_0005_synthetic.dump" | cut -d' ' -f1)"

run_backup() {  # $1 label, $2 hook ('' for none); prints the exit code
  local label="$1" hook="$2"
  local tmp="$ROOT/tmp-$label" out="$ROOT/out-$label.txt"
  mkdir -p "$tmp"
  G17C_SOURCE="$SRC" G17C_EXPECTED_PROJECT="$PROJECT" G17C_EXPECTED_DIR="$EXP" G17C_BACKUPS="$B1" G17C_SECOND="$B2" G17C_TMP="$tmp" \
    G17C_REQUIRE_FOLDER_POLICY=1 G17C_OUT="$out" G17C_EVIDENCE="$ROOT/evidence-$label" G17C_FAIL_AT="$hook" bash "$HERE/run_17c_backup.sh" > /dev/null 2>&1
  echo $?
}
count_new() { ls "$B1" "$B2" 2>/dev/null | grep -c "asistenteia_pre_17b_"; }

log "=== run 1: happy path"
RC=$(run_backup happy ""); OUT1="$ROOT/out-happy.txt"
sed 's/^/    /' "$OUT1" | grep -E "PASS|FAIL|STOP|cleanup|result|MANIFEST|ACL" | cut -c1-200 | tee -a "$OUT" > /dev/null
check "run 1 exits 0" 0 "$RC"
check "run 1: every check passed ($(grep -o 'result: [0-9]* checks passed, [0-9]* failed' "$OUT1"))" "0 failed" "$(grep -o '[0-9]* failed' "$OUT1" | head -1)"
check "run 1: six new files (dump, .sha256, manifest in each folder)" 6 "$(count_new)"
NAME1="$(ls "$B1" | grep -E '^asistenteia_pre_17b_.*\.dump$' | head -1)"
check "run 1: the two copies verify independently with their own labels" "OK OK" "$(python -I "$(cygpath -w "$HERE/tools/backup_manifest.py")" verify "$(cygpath -w "$B1")" "$NAME1" --copy primary | cut -c10-11) $(python -I "$(cygpath -w "$HERE/tools/backup_manifest.py")" verify "$(cygpath -w "$B2")" "$NAME1" --copy second | cut -c10-11)"
check "run 1: sha256sum -c works inside each folder" "2 2" "$( (cd "$B1" && sha256sum -c "$NAME1.sha256" 2>/dev/null | grep -c ': OK') ) $( (cd "$B2" && sha256sum -c "$NAME1.sha256" 2>/dev/null | grep -c ': OK') )"
check "run 1: no absolute path and no user name in the integrity files" 0 "$(cat "$B1/$NAME1.sha256" "$B1/$NAME1.manifest.txt" "$B2/$NAME1.sha256" "$B2/$NAME1.manifest.txt" | grep -ciE "[a-z]:[/\\\\]|$USERNAME")"
check "run 1: no absolute path of the folders and no user name in the output" 0 "$(grep -ciE "$(echo "$ROOT" | sed 's#/#.#g')|$USERNAME" "$OUT1")"
check "run 1: the restored copy was IDENTICAL to the source" "IDENTICAL" "$(grep -o 'IDENTICAL, obtained IDENTICAL' "$OUT1" | head -1 | cut -d, -f1)"
check "run 1: the dump was removed from the source container" 0 "$(docker exec "$SRC" sh -c 'ls /tmp/*.dump 2>/dev/null | wc -l')"
check "run 1: the older backup is untouched" "$OLD_HASH" "$(sha256sum "$B1/asistenteia_pre_0005_synthetic.dump" | cut -d' ' -f1)"
mkdir -p "$ROOT/keep/a" "$ROOT/keep/b"; mv "$B1"/asistenteia_pre_17b_* "$ROOT/keep/a/"; mv "$B2"/asistenteia_pre_17b_* "$ROOT/keep/b/"
check "run 1: the new files were moved away so that the next runs start from the same folders" 0 "$(count_new)"; sleep 1

for pair in "copy|run 2: corrupted second copy" "manifest|run 3: corrupted manifest" "interrupt|run 4: simulated Ctrl+C before verification" "acl_done|run 4b: failure AFTER the files became read-only"; do
  hook="${pair%%|*}"; title="${pair#*|}"
  log "=== $title"
  RC=$(run_backup "$hook" "$hook"); O="$ROOT/out-$hook.txt"
  sed 's/^/    /' "$O" | grep -E "FAIL|STOP|cleanup|interrupted|hook|new files" | cut -c1-200 | tee -a "$OUT" > /dev/null
  check "$title: exits non-zero" "non-zero" "$([ "$RC" != 0 ] && echo non-zero || echo zero)"
  check "$title: no file of the run is left in either folder" 0 "$(count_new)"
  check "$title: the trap reported the removal of the unverified files" 1 "$(grep -c 'were NOT verified and have been removed' "$O")"
  check "$title: no restore container or network left" "0 0" "$(docker ps -a --filter label=purpose=g17c-restore -q | wc -l) $(docker network ls --filter label=purpose=g17c-restore -q | wc -l)"
  check "$title: the dump was removed from the source container" 0 "$(docker exec "$SRC" sh -c 'ls /tmp/*.dump 2>/dev/null | wc -l')"
  check "$title: the older backup is untouched" "$OLD_HASH" "$(sha256sum "$B1/asistenteia_pre_0005_synthetic.dump" | cut -d' ' -f1)"
  sleep 1
done

log "=== run 5: a 17b backup already present"
cp "$ROOT/keep/a/$NAME1" "$B1/$NAME1"; BEFORE="$(ls -l "$B1" "$B2" | sha256sum | cut -d' ' -f1)"
RC=$(run_backup present ""); check "run 5: refused with exit 3" 3 "$RC"
check "run 5: the folders are unchanged" "$BEFORE" "$(ls -l "$B1" "$B2" | sha256sum | cut -d' ' -f1)"
check "run 5: no dump left in the source container" 0 "$(docker exec "$SRC" sh -c 'ls /tmp/*.dump 2>/dev/null | wc -l')"
log "=== result: $PASS checks passed, $FAIL failed (of $N)"
[ "$FAIL" = 0 ]
