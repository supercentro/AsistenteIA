#!/usr/bin/env bash
# Step 17B orchestrator (TD-030): runs the stages of runbook-17b.md one at a time, fails closed, keeps a state file.
#
#   G17B_STATE_DIR=<folder OUTSIDE the repository> bash run_17b.sh --status
#   G17B_STATE_DIR=...  bash run_17b.sh --plan
#   G17B_STATE_DIR=...  bash run_17b.sh --stage S10          # one stage; the previous ones must be done
#   G17B_STATE_DIR=...  bash run_17b.sh --through S12        # stages in order, stops at the first failure
#
# Stages (17B.1 = read only + images; everything from S20 on WRITES and needs the owner's explicit "GO 17B.2"):
#   S10 preflight         identity, RAM, disk, activity, catalog = expected baseline, services seen     (read only)
#   S11 backup_validate   per-copy manifests, file and folder ACL, hash, backup = real state          (read only)
#   S12 images            tag the images the containers use as pre-17b, build the five images          (no container touched)
#   S13 settings_load     load the settings with the env files in a throw-away container (prints nothing) [real: needs G17B_ALLOW_REAL_SETTINGS=1]
#   S20 stop_services     docker compose stop backend worker                                           [GO 17B.2]
#   S21 prepare_env       prepare_env_files.py --dry-run, then for real with --strip-legacy, then file ACLs
#   S22 bootstrap         first bootstrap, exit 1 EXPECTED (it lists the ownership drift)
#   S23 adopt_dry_run     db-adopt dry run: exactly 9 objects
#   S24 adopt_apply       db-adopt --apply
#   S25 migrate           Alembic 0005 -> 0006 and the grants
#   S26 db_verify         db-verify: no findings
#   S30 switch_services   recreate backend and worker with the new files, wait until healthy
#   S31 verify_sessions   the sessions on the database use the restricted roles, not the administrator
#
# Fail closed: the first problem stops the run (nothing continues), the last completed stage and the failed one are
# recorded WITHOUT secrets, the rollback column of runbook-17b.md that applies is printed, and NOTHING destructive is
# ever run automatically. A stage that is already done is refused (accidental second run), a stage whose predecessor is
# not done is refused, and a lock directory refuses a concurrent run.
#
# Exit codes: 0 ok | 2 usage | 3 cluster identity / preflight NO-GO | 4 not enough RAM or disk | 5 lock held (another run)
#   6 stage order / already done | 7 not authorised (or a test hook in the real profile) | 10 backup invalid
#   11 backup no longer equals the real state: a NEW BACKUP needs the owner's authorisation | 12 image tag or build
#   13 settings do not load | 20 stop services | 21 env files | 22 bootstrap | 23 adoption dry run | 24 adoption
#   25 migration or grants | 26 db-verify | 30 switch | 31 sessions | 40 interrupted | 99 unexpected command failure
#
# Profiles: `real` (default) is hard-wired to the development stack; `test` reads G17B_TEST_CONFIG (a bash file that sets
# the variables below for a DISPOSABLE stack) and is accepted only when the database container carries the label
# purpose=g17b-test and is not the real one. Test hooks (G17B_TEST_FAIL_AT, G17B_TEST_SLEEP_AT) are refused in `real`.
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
REPOW="$(cd "$REPO" && pwd -W 2>/dev/null || echo "$REPO")"
R17A="$REPO/openspec/changes/database-least-privilege/reports/group-17a"
R17C="$REPO/openspec/changes/database-least-privilege/reports/group-17c"
PROFILE="${G17B_PROFILE:-real}"

# ---- configuration (real values; the test profile overrides them from its config file)
PROJECT=asistenteia
DBC=asistenteia-db-1
DBNAME=asistenteia
API_C=asistenteia-backend-1
WORKER_C=asistenteia-worker-1
ENV_DIR="$REPO/backend"
UHOME="$(cygpath -u "${USERPROFILE:-$HOME}")"
BACKUPS="$UHOME/Backups/AsistenteIA"
SECOND="$UHOME/Backups/AsistenteIA-second"
DUMP=asistenteia_pre_17b_20261114T013150Z.dump
DUMP_SHA=d0a2ad6bfc0c392d765473acbaf7bfbec25ff24eea99e2828e3377176d6279d9
DUMP_SIZE=17437
SUFFIX=.integrity.txt
EXPECTED_SNAPSHOT="$R17A/expected/snapshot-db-0005.txt"
EXPECTED_CLUSTER="$R17A/expected/snapshot-cluster.txt"
BACKUP_TIME_SNAPSHOT="$R17C/evidence/source-snapshot-db.txt"
EXPECTED_IMAGES=(asistenteia-bootstrap asistenteia-migrate asistenteia-cli asistenteia-backend asistenteia-worker)
IMG_MIGRATE=asistenteia-migrate:latest
EXPECT_ROLES="asistente_app asistente_worker"
FOLDER_POLICY=1
DC_FILES=(-f "$REPOW/docker-compose.yml")
TEST_PREP_CLEAN=0

if [ "$PROFILE" = test ]; then
  : "${G17B_TEST_CONFIG:?the test profile needs G17B_TEST_CONFIG}"
  # shellcheck disable=SC1090
  . "$G17B_TEST_CONFIG"
elif [ "$PROFILE" != real ]; then
  echo "usage error: unknown profile"; exit 2
else
  if [ -n "${G17B_TEST_FAIL_AT:-}${G17B_TEST_SLEEP_AT:-}${G17B_TEST_CONFIG:-}" ]; then echo "REFUSED: test hooks are not accepted in the real profile"; exit 7; fi
fi
STATE_DIR="${G17B_STATE_DIR:?set G17B_STATE_DIR to a folder OUTSIDE the repository}"
mkdir -p "$STATE_DIR"
STATE_DIR="$(cd "$STATE_DIR" && pwd)"
case "$STATE_DIR" in "$REPO"|"$REPO"/*) echo "G17B_STATE_DIR must be outside the repository"; exit 2;; esac
STATE="$STATE_DIR/state"; LOG="$STATE_DIR/run.log"; LOCK="$STATE_DIR/lock"; OUTD="$STATE_DIR/out"
mkdir -p "$OUTD"
MIN_RAM="${G17B_MIN_RAM_GB:-8}"; MIN_DISK="${G17B_MIN_DISK_GB:-15}"
PY=python
command -v python >/dev/null 2>&1 || PY=python3
MAIN_PID=$BASHPID
CHILD=""

# ---- logging without paths, user names or URLs
san() {
  local s u1 u2 h1 h2
  u1="${USERNAME:-}"; u2="${USER:-}"; h1="${USERPROFILE:-}"; h2="${HOME:-}"
  while IFS= read -r s || [ -n "$s" ]; do
    for v in "$h1" "${h1//\\//}" "$h2"; do [ -n "$v" ] && s="${s//"$v"/<home>}"; done
    for v in "$u1" "$u2"; do [ -n "$v" ] && s="${s//"$v"/<user>}"; done
    printf '%s\n' "$s" | sed -E 's#(postgres(ql)?(\+[a-z0-9]+)?://)[^[:space:]]+#\1<redacted>#g'
  done
}
log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" | san | tee -a "$LOG"; }
die() { local code="$1"; shift; log "STOP [$code] $*"; exit "$code"; }

# ---- state (no secrets: stage names, times, a cluster id)
state_get() { [ -f "$STATE" ] && sed -n "s/^$1=//p" "$STATE" | tail -1 || true; }
state_set() { local tmp="$STATE.tmp.$$"; { [ -f "$STATE" ] && grep -v "^$1=" "$STATE" || true; printf '%s=%s\n' "$1" "$2"; } > "$tmp"; mv "$tmp" "$STATE"; }
is_done() { case ",$(state_get done)," in *",$1,"*) return 0;; esac; return 1; }
mark_done() { local d; d="$(state_get done)"; state_set done "${d:+$d,}$1"; state_set last_completed "$1"; }

STAGES=(S10 S11 S12 S13 S20 S21 S22 S23 S24 S25 S26 S30 S31)
declare -A FN=([S10]=st_preflight [S11]=st_backup_validate [S12]=st_images [S13]=st_settings_load [S20]=st_stop_services [S21]=st_prepare_env
  [S22]=st_bootstrap [S23]=st_adopt_dry [S24]=st_adopt_apply [S25]=st_migrate [S26]=st_db_verify [S30]=st_switch [S31]=st_sessions)
declare -A NAME=([S10]=preflight [S11]=backup_validate [S12]=images [S13]=settings_load [S20]=stop_services [S21]=prepare_env
  [S22]=bootstrap [S23]=adopt_dry_run [S24]=adopt_apply [S25]=migrate [S26]=db_verify [S30]=switch_services [S31]=verify_sessions)
declare -A CODE=([S10]=3 [S11]=10 [S12]=12 [S13]=13 [S20]=20 [S21]=21 [S22]=22 [S23]=23 [S24]=24 [S25]=25 [S26]=26 [S30]=30 [S31]=31)
is_known_stage() { [ -n "${FN[$1]+x}" ]; }
needs_go() { case "$1" in S2*|S3*) return 0;; esac; return 1; }

# ---- rollback guidance: the column of runbook-17b.md that applies. Nothing here is executed.
rollback_hint() { # $1 = stage that failed or was interrupted
  case "$1" in
    S10|S11|S12|S13) echo "no change was made to the database, the services or the files: nothing to roll back (S12 only added image tags and images; the pre-17b tags are the references)";;
    S20) echo "services stopped, nothing else: start the previous stack from main's compose file plus the shipped override (runbook, rollback step 6); a plain 'docker compose start' would load the new code from the mount";;
    S21) echo "runbook rollback steps 5, 6 (prepare_env_files.py --rollback, then the previous stack with the override); check first which files exist (names only)";;
    S22|S23|S24) echo "runbook rollback steps 3, 4, 5, 6 (db-adopt --rollback --remove-roles, restore PUBLIC, prepare_env_files.py --rollback, previous stack); services must be stopped first";;
    S25|S26|S30|S31) echo "runbook rollback steps 2, 3, 4, 5, 6 (db-migrate --downgrade 0005 first, then as above); stop backend and worker first";;
    *) echo "unknown stage: take the rollback column of the stage reached, never improvise on the real database";;
  esac
}
explain_stop() { # $1 stage, $2 code
  log "last completed stage: $(state_get last_completed || true)"
  log "stopped in: $1 (${NAME[$1]:-?}), exit code $2"
  log "rollback that applies: $(rollback_hint "$1")"
  log "NOTHING was rolled back automatically and the next stage was NOT started; decide with the owner (runbook, stop conditions)"
}

# ---- locks and signals
HAVE_LOCK=0; CURRENT=""
release_lock() { if [ "$HAVE_LOCK" = 1 ] && [ "$BASHPID" = "$MAIN_PID" ]; then rm -rf "$LOCK"; HAVE_LOCK=0; fi; }
on_signal() {
  trap - INT TERM
  if [ -n "$CHILD" ]; then
    # stop the stage and whatever it started (best effort; a docker client may need its own Ctrl+C)
    for p in $(ps -ef 2>/dev/null | awk -v c="$CHILD" '$3==c {print $2}'); do kill -TERM "$p" 2>/dev/null || true; done
    kill -TERM "$CHILD" 2>/dev/null || true
  fi
  log "INTERRUPTED while running ${CURRENT:-no stage}"
  state_set interrupted "${CURRENT:-none}"; state_set status interrupted
  [ -n "$CURRENT" ] && explain_stop "$CURRENT" 40
  release_lock
  exit 40
}
trap on_signal INT TERM
trap 'release_lock' EXIT

# ---- primitives
free_ram_gb() { powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" 2>/dev/null | tr -d '\r'; }
free_disk_gb() { df -BG --output=avail "$STATE_DIR" 2>/dev/null | tail -1 | tr -d ' G'; }
gate_resources() {
  local ram disk need="${1:-ram}"
  ram="$(free_ram_gb)"; disk="$(free_disk_gb)"
  [ -n "$ram" ] && [ -n "$disk" ] || die 4 "cannot read free RAM or disk: stop"
  log "free RAM ${ram} GB (need ${MIN_RAM}), free disk ${disk} GB (need ${MIN_DISK})"
  "$PY" -c "import sys; sys.exit(0 if float('$ram') >= float('$MIN_RAM') else 1)" || die 4 "less than ${MIN_RAM} GB of free RAM: NO-GO"
  "$PY" -c "import sys; sys.exit(0 if float('$disk') >= float('$MIN_DISK') else 1)" || die 4 "less than ${MIN_DISK} GB of free disk: NO-GO"
}
dc() { docker compose -p "$PROJECT" --project-directory "$REPOW" "${DC_FILES[@]}" "$@"; }
psql_ro() { docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "$DBC" sh -c "psql -U \"\$POSTGRES_USER\" -d ${2:-$DBNAME} -At -F '|' -v ON_ERROR_STOP=1" <<< "$1"; }
psql_rw() { docker exec -i "$DBC" sh -c "psql -U \"\$POSTGRES_USER\" -d ${2:-$DBNAME} -At -F '|' -v ON_ERROR_STOP=1" <<< "$1"; }
cap() { # cap <file-label> <cmd...> : run, keep the sanitized output in out/, print the last lines, return the command's rc
  local label="$1" rc=0; shift
  "$@" > "$OUTD/$CURRENT-$label.raw" 2>&1 || rc=$?
  san < "$OUTD/$CURRENT-$label.raw" > "$OUTD/$CURRENT-$label.txt"; rm -f "$OUTD/$CURRENT-$label.raw"
  tail -n "${TAILN:-4}" "$OUTD/$CURRENT-$label.txt" | cut -c1-200 | sed 's/^/    | /' | tee -a "$LOG"
  return "$rc"
}
wps() { cygpath -w "$1"; }
hook_fail() { [ "$PROFILE" = test ] && [ "${G17B_TEST_FAIL_AT:-}" = "$CURRENT" ] && die "${CODE[$CURRENT]}" "injected failure (test hook) in $CURRENT"; return 0; }
hook_sleep() { if [ "$PROFILE" = test ] && [ -n "${G17B_TEST_SLEEP_AT:-}" ] && [ "${G17B_TEST_SLEEP_AT%%:*}" = "$CURRENT" ]; then log "test hook: sleeping ${G17B_TEST_SLEEP_AT#*:} s in $CURRENT"; sleep "${G17B_TEST_SLEEP_AT#*:}"; fi; return 0; }

identity_check() {
  local info proj status image sysid db ver
  info="$(docker inspect "$DBC" --format '{{index .Config.Labels "com.docker.compose.project"}}|{{.State.Status}}|{{.Config.Image}}|{{index .Config.Labels "purpose"}}' 2>/dev/null)" || die 3 "the database container does not exist: wrong cluster"
  IFS='|' read -r proj status image purpose <<< "$info"
  [ "$proj" = "$PROJECT" ] || die 3 "cluster identity: compose project '$proj' is not '$PROJECT'"
  [ "$status" = running ] || die 3 "cluster identity: the database container is '$status'"
  case "$image" in *pgvector*) ;; *) die 3 "cluster identity: the image is not the pgvector one";; esac
  if [ "$PROFILE" = test ]; then
    [ "$purpose" = g17b-test ] || die 7 "the test profile needs the label purpose=g17b-test on the database container"
    [ "$DBC" != asistenteia-db-1 ] && [ "$PROJECT" != asistenteia ] || die 7 "the test profile may not point at the real stack"
  fi
  db="$(psql_ro "select current_database()" "$DBNAME")" || die 3 "cannot read the database: wrong cluster or not reachable"
  [ "$db" = "$DBNAME" ] || die 3 "cluster identity: database '$db' is not '$DBNAME'"
  ver="$(psql_ro "show server_version")"; case "$ver" in 15.*) ;; *) die 3 "cluster identity: PostgreSQL $ver is not 15.x";; esac
  sysid="$(psql_ro "select system_identifier from pg_control_system()")"
  if [ -z "$(state_get cluster_id)" ]; then state_set cluster_id "$sysid"; log "cluster identity recorded (container, project, database, PostgreSQL $ver, system id $sysid)"
  else [ "$(state_get cluster_id)" = "$sysid" ] || die 3 "cluster identity changed since the first stage (system id differs): NO-GO"; log "cluster identity unchanged since S10 (system id $sysid)"; fi
}
revision_is() { [ "$(psql_ro "select version_num from alembic_version")" = "$1" ]; }

# ======================================================================== stages
st_preflight() {
  gate_resources
  identity_check
  revision_is 0005 || die 3 "Alembic revision is not 0005"
  local pre="$STATE_DIR/preflight-before"
  rm -rf "$pre"
  cap preflight bash "$R17A/tools/preflight_readonly.sh" "$DBC" "$DBNAME" "$pre" || die 3 "the read-only preflight tool failed"
  cap baseline bash "$R17A/tools/compare_snapshots.sh" "$EXPECTED_SNAPSHOT" "$pre/snapshot-db.txt" || die 3 "gate D: the catalog differs from the expected 0005 baseline"
  MIN_LINES=5 cap cluster bash "$R17A/tools/compare_snapshots.sh" "$EXPECTED_CLUSTER" "$pre/snapshot-cluster.txt" || die 3 "gate D: roles/databases/ACLs differ from the expected cluster"
  local f
  for f in open_transactions_older_than_1_min idle_in_transaction prepared_transactions ungranted_locks long_running_queries_over_30s; do
    [ "$(sed -n "s/^$f|//p" "$pre/activity.txt")" = 0 ] || die 3 "gate E: $f is not 0"
  done
  [ "$(sed -n 's/^login_roles_other_than_the_administrator|//p' "$pre/activity.txt")" = "(none)" ] || die 3 "gate E: a login role other than the administrator exists"
  grep -q '^read_only_session|on' "$pre/identity.txt" || die 3 "the preflight session was not read only"
  log "services seen: db=$(docker inspect -f '{{.State.Status}}' "$DBC") api=$(docker inspect -f '{{.State.Status}}' "$API_C" 2>/dev/null || echo absent) worker=$(docker inspect -f '{{.State.Status}}/{{with index .State "Health"}}{{.Status}}{{else}}none{{end}}/restarts={{.RestartCount}}' "$WORKER_C" 2>/dev/null || echo absent)"
  hook_fail; hook_sleep
  log "S10 ok: nothing was written"
}

st_backup_validate() {
  identity_check
  local dump="$BACKUPS/$DUMP" rc=0 lab dir
  [ -f "$dump" ] && [ -f "$SECOND/$DUMP" ] || die 10 "a copy of the backup is missing"
  for pair in "primary:$BACKUPS" "second:$SECOND"; do
    lab="${pair%%:*}"; dir="${pair#*:}"
    [ "$(sha256sum "$dir/$DUMP" | cut -d' ' -f1)" = "$DUMP_SHA" ] || die 10 "$lab copy: sha256 differs from the recorded one"
    [ "$(stat -c %s "$dir/$DUMP")" = "$DUMP_SIZE" ] || die 10 "$lab copy: size differs from the recorded one"
    cap "manifest-$lab" "$PY" -I "$(wps "$R17C/tools/backup_manifest.py")" verify "$(wps "$dir")" "$DUMP" --copy "$lab" --manifest-suffix "$SUFFIX" || die 10 "$lab copy: manifest verification failed"
    ( cd "$dir" && sha256sum -c "$DUMP.sha256" >/dev/null 2>&1 ) || die 10 "$lab copy: sha256sum -c failed inside its own folder"
    if [ "$FOLDER_POLICY" = 1 ]; then
      cap "folder-$lab" powershell -NoProfile -ExecutionPolicy Bypass -File "$(wps "$R17C/tools/secure_folder_acl.ps1")" -Path "$(wps "$dir")" -VerifyOnly || die 10 "$lab folder: the ACL policy does not hold"
    fi
    for f in "$DUMP" "$DUMP.sha256" "$DUMP$SUFFIX"; do
      TAILN=1 cap "acl-$lab" powershell -NoProfile -ExecutionPolicy Bypass -File "$(wps "$R17C/tools/secure_file_acl.ps1")" -Path "$(wps "$dir/$f")" -VerifyOnly || die 10 "$lab file ACL deviates ($f)"
    done
  done
  [ "$(sha256sum "$BACKUPS/$DUMP" | cut -d' ' -f1)" = "$(sha256sum "$SECOND/$DUMP" | cut -d' ' -f1)" ] || die 10 "the two copies differ from each other"
  log "backup: both copies verified (hash, size, independent manifests, ACLs)"
  # equivalence with the REAL state: the snapshot taken when the backup was made against the current one (schema, catalog,
  # ownership, permissions, row counts, Alembic revision). Any difference means the backup is no longer a faithful copy.
  # A FRESH read-only snapshot, not the one of S10: the database may have changed in between.
  local now="$STATE_DIR/s11-snapshot-db.txt"
  psql_ro "$(cat "$R17A/tools/snapshot_db.sql")" > "$now" 2>&1 || die 11 "the fresh read-only snapshot failed"
  if ! cap equivalence bash "$R17A/tools/compare_snapshots.sh" "$BACKUP_TIME_SNAPSHOT" "$now"; then
    die 11 "the real database no longer equals the state the backup was taken from (schema, catalog, ownership, permissions, counts or revision): a NEW BACKUP is needed and needs the owner's authorisation; nothing was moved, deleted or overwritten"
  fi
  revision_is 0005 || die 11 "Alembic revision is not 0005"
  hook_fail; hook_sleep
  log "S11 ok: the existing backup is valid and equals the real state; it can be reused"
}

# container ids, names, states and the IMAGE ID each one runs (docker ps shows the tag, which moves when a build re-tags 'latest')
container_fingerprint() { docker ps -a --format '{{.ID}}' | sort | while read -r c; do docker inspect -f '{{.Id}} {{.Name}} {{.State.Status}} {{.Image}}' "$c"; done; }

st_images() {
  gate_resources
  identity_check
  local before after cid name img_id tag
  before="$(container_fingerprint)"
  for pair in "backend:$API_C" "worker:$WORKER_C"; do
    name="${pair%%:*}"; cid="${pair#*:}"
    img_id="$(docker inspect -f '{{.Image}}' "$cid" 2>/dev/null)" || die 12 "container $cid is not there: cannot tag its image"
    tag="asistenteia-$name:pre-17b"
    cur="$(docker images --no-trunc --format '{{.ID}}' "$tag" 2>/dev/null | head -1)"
    if [ -n "$cur" ] && [ "$cur" != "$img_id" ]; then die 12 "$tag already exists and points at another image: not touching it"; fi
    [ -n "$cur" ] || docker tag "$img_id" "$tag"
    log "rollback reference $tag -> ${img_id:0:19}"
  done
  hook_fail; hook_sleep
  log "building the five images (the stack stays up; nothing is started)"
  if ! cap build dc build bootstrap migrate cli backend worker; then die 12 "docker compose build failed: NO-GO before anything changed"; fi
  after="$(container_fingerprint)"
  [ "$before" = "$after" ] || die 12 "the list of containers changed during the build"
  for n in "${EXPECTED_IMAGES[@]}"; do
    id="$(docker images --no-trunc --format '{{.ID}}' "$n:latest" | head -1)"; [ -n "$id" ] || die 12 "image $n:latest was not built"
    log "image $n:latest ${id:0:19}"
  done
  cap config_images dc config --images || true
  log "S12 ok: images built; old images kept under the pre-17b tags; no container, volume or network touched"
}

st_settings_load() {
  identity_check
  if [ "$PROFILE" = real ] && [ "${G17B_ALLOW_REAL_SETTINGS:-0}" != 1 ]; then die 7 "loading the settings reads the REAL env files: needs the owner's decision (G17B_ALLOW_REAL_SETTINGS=1)"; fi
  local img_api img_wk
  img_api="${G17B_IMAGE_API:-asistenteia-backend:latest}"; img_wk="${G17B_IMAGE_WORKER:-asistenteia-worker:latest}"
  docker run --rm --env-file "$(wps "$ENV_DIR/.env")" --entrypoint python "$img_api" -c "from app.core.config import load_settings; load_settings()" >/dev/null 2>&1 || die 13 "the API settings do not load with .env (no value printed)"
  docker run --rm --env-file "$(wps "$ENV_DIR/.env.worker")" --entrypoint python "$img_wk" -c "from app.core.config import load_worker_settings; load_worker_settings()" >/dev/null 2>&1 || die 13 "the worker settings do not load with .env.worker (no value printed)"
  hook_fail; hook_sleep
  log "S13 ok: both settings load (nothing printed)"
}

st_stop_services() {
  identity_check
  revision_is 0005 || die 20 "revision is not 0005 before the stop"
  hook_fail; hook_sleep
  cap stop dc stop backend worker || die 20 "docker compose stop failed"
  [ "$(docker inspect -f '{{.State.Running}}' "$WORKER_C" 2>/dev/null || echo false)" = false ] || die 20 "the worker is still running"
  [ "$(docker inspect -f '{{.State.Running}}' "$API_C" 2>/dev/null || echo false)" = false ] || die 20 "the API is still running"
  [ "$(docker inspect -f '{{.State.Status}}' "$DBC")" = running ] || die 20 "the database container is not running"
  local after="$STATE_DIR/after-stop"; rm -rf "$after"
  cap snapshot bash "$R17A/tools/preflight_readonly.sh" "$DBC" "$DBNAME" "$after" || die 20 "snapshot after the stop failed"
  cap same bash "$R17A/tools/compare_snapshots.sh" "$STATE_DIR/preflight-before/snapshot-db.txt" "$after/snapshot-db.txt" || die 20 "something was written between the preflight and the stop: the backup no longer equals the state; take a new backup (owner's authorisation)"
  log "S20 ok: backend and worker stopped; database untouched and identical to the preflight"
}

st_prepare_env() {
  identity_check
  local tool; tool="$(wps "$R17A/tools/prepare_env_files.py")"
  cap dry "$PY" -I "$tool" "$(wps "$ENV_DIR")" --dry-run --strip-legacy || die 21 "prepare_env_files.py dry run refused: fix the cause, never edit by hand"
  hook_fail; hook_sleep
  cap real "$PY" -I "$tool" "$(wps "$ENV_DIR")" --strip-legacy || die 21 "prepare_env_files.py refused or failed"
  for f in .env.roles .env.migrate .env.cli .env.test .env.pre-17b .env.worker.pre-17b .env.db.pre-17b; do [ -f "$ENV_DIR/$f" ] || die 21 "expected file $f is missing"; done
  for f in .env .env.worker; do
    [ "$(grep -cE '^(POSTGRES_(USER|PASSWORD|DB)|TEST_[A-Z0-9_]+)=' "$ENV_DIR/$f" || true)" = 0 ] || die 21 "$f still carries an administrator or TEST_ variable"
  done
  for f in .env.roles .env.migrate .env.cli .env.test; do
    TAILN=1 cap "acl-$f" powershell -NoProfile -ExecutionPolicy Bypass -File "$(wps "$R17C/tools/secure_file_acl.ps1")" -Path "$(wps "$ENV_DIR/$f")" -Rights Modify || die 21 "the ACL of $f could not be restricted"
  done
  log "S21 ok: env files prepared (names only), legacy administrator variables removed, new files restricted"
}

run_expect() { # run_expect <label> <expected rc> <cmd...>
  local label="$1" want="$2" rc=0; shift 2
  cap "$label" "$@" || rc=$?
  [ "$rc" = "$want" ] || return 1
}
st_bootstrap() {
  identity_check
  hook_fail; hook_sleep
  run_expect first 1 dc run --rm --no-deps bootstrap || die 22 "bootstrap did not end with the EXPECTED exit 1 (ownership drift); any other result is a stop"
  grep -q "ownership drift" "$OUTD/$CURRENT-first.txt" || die 22 "bootstrap exited 1 but did not list the ownership drift"
  log "S22 ok: bootstrap ended with the expected exit 1 and listed the drift"
}
st_adopt_dry() {
  identity_check
  hook_fail; hook_sleep
  TAILN=12 cap dry dc run --rm --no-deps bootstrap python -m app.cli db-adopt --database "$DBNAME" || die 23 "db-adopt dry run failed"
  grep -q "dry run (nothing changed; use --apply): 9 object" "$OUTD/$CURRENT-dry.txt" || die 23 "the dry run does not list exactly 9 objects"
  log "S23 ok: 9 objects to adopt"
}
st_adopt_apply() {
  identity_check
  hook_fail; hook_sleep
  cap apply dc run --rm --no-deps bootstrap python -m app.cli db-adopt --apply --database "$DBNAME" || die 24 "db-adopt --apply failed (it is atomic: nothing changed)"
  log "S24 ok: ownership adopted"
}
st_migrate() {
  identity_check
  hook_fail; hook_sleep
  cap migrate dc run --rm --no-deps migrate || die 25 "migration or grants failed"
  revision_is 0006 || die 25 "revision is not 0006 after the migration"
  log "S25 ok: revision 0006 and the grants applied"
}
st_db_verify() {
  identity_check
  hook_fail; hook_sleep
  cap verify docker run --rm --network "${PROJECT}_default" --env-file "$(wps "$ENV_DIR/.env.migrate")" --env-file "$(wps "$ENV_DIR/.env.roles")" --entrypoint python "$IMG_MIGRATE" -m app.cli db-verify || die 26 "db-verify reported findings or failed"
  grep -q "no findings" "$OUTD/$CURRENT-verify.txt" || die 26 "db-verify did not say 'no findings'"
  log "S26 ok: db-verify has no findings"
}
st_switch() {
  identity_check
  hook_fail; hook_sleep
  cap up dc up -d --no-deps --force-recreate backend worker || die 30 "recreating backend and worker failed"
  local i=0 h
  while [ $i -lt 90 ]; do
    h="$(docker inspect -f '{{with index .State "Health"}}{{.Status}}{{else}}none{{end}}' "$WORKER_C" 2>/dev/null || echo absent)"
    [ "$h" = healthy ] && break; sleep 5; i=$((i+1))
  done
  [ "$h" = healthy ] || die 30 "the worker is not healthy after 450 s"
  log "S30 ok: backend and worker recreated, worker healthy"
}
st_sessions() {
  identity_check
  hook_fail; hook_sleep
  local users role
  users="$(psql_ro "select usename from pg_stat_activity where datname='$DBNAME' and usename is not null and backend_type='client backend' group by 1 order by 1" postgres | tr '\n' ' ')"
  log "roles with sessions on the database: $users"
  case " $users " in *" asistente "*) die 31 "the administrator still has sessions on the database";; esac
  for role in $EXPECT_ROLES; do case " $users " in *" $role "*) ;; *) die 31 "no session of $role";; esac; done
  log "S31 ok: only restricted roles use the database"
}

# ======================================================================== driver
usage() { sed -n 2,9p "$0" | sed 's/^# \{0,1\}//'; exit 2; }
status() {
  echo "profile=$PROFILE"
  echo "done=$(state_get done)"; echo "last_completed=$(state_get last_completed)"; echo "failed=$(state_get failed)"; echo "interrupted=$(state_get interrupted)"; echo "status=$(state_get status)"
  local at; at="$(state_get failed)"; [ -n "$at" ] || at="$(state_get interrupted)"
  if [ -n "$at" ] && [ "$at" != none ]; then echo "rollback that applies: $(rollback_hint "$at")"; fi
  # read-only reality check (never writes): what exists now, to decide the rollback with the owner
  if docker inspect "$DBC" >/dev/null 2>&1; then
    echo "revision_now=$(psql_ro "select version_num from alembic_version" 2>/dev/null || echo unreadable)"
    echo "restricted_roles_exist=$(psql_ro "select count(*) from pg_roles where rolname in ('asistente_migrator','asistente_app','asistente_worker','asistente_cli')" postgres 2>/dev/null || echo unreadable)"
  fi
  echo "env_files_present=$(cd "$ENV_DIR" 2>/dev/null && ls -1 .env.roles .env.migrate .env.cli .env.test .env.pre-17b 2>/dev/null | tr '\n' ' ')"
}

run_stage() {
  local st="$1" rc=0
  is_known_stage "$st" || { log "usage error: unknown stage $st"; exit 2; }
  if needs_go "$st" && [ "$PROFILE" = real ]; then
    [ "${G17B_OWNER_GO:-}" = "GO-17B.2" ] || die 7 "$st writes: it needs the owner's explicit 'GO 17B.2' (G17B_OWNER_GO); NOT authorised"
  fi
  is_done "$st" && die 6 "stage $st is already done: refused (accidental second run)"
  # S13 is optional: stages after it need S10..S12 only
  for s in "${STAGES[@]}"; do
    [ "$s" = "$st" ] && break
    [ "$s" = S13 ] && continue
    is_done "$s" || die 6 "stage $s must be done before $st"
  done
  CURRENT="$st"; state_set status "running:$st"; state_set failed ""
  log "=== $st ${NAME[$st]} (profile $PROFILE)"
  set +e
  ( set -Eeuo pipefail; "${FN[$st]}" ) &
  CHILD=$!
  wait "$CHILD" || rc=$?
  CHILD=""
  set -e
  if [ "$rc" != 0 ]; then
    state_set failed "$st"; state_set status "failed:$st"
    explain_stop "$st" "$rc"
    CURRENT=""; release_lock
    exit "$rc"
  fi
  mark_done "$st"; state_set status "ok:$st"; CURRENT=""
}

MODE="${1:-}"; ARG="${2:-}"
case "$MODE" in
  --status) status; exit 0;;
  --plan)
    for s in "${STAGES[@]}"; do printf '%s %-16s %s\n' "$s" "${NAME[$s]}" "$(needs_go "$s" && echo 'WRITES: needs GO 17B.2' || echo 'read only / images')"; done; exit 0;;
  --stage|--through) is_known_stage "$ARG" || usage;;
  *) usage;;
esac

if ! mkdir "$LOCK" 2>/dev/null; then die 5 "another run holds the lock (or a killed run left it: inspect $(basename "$STATE_DIR") before removing it by hand)"; fi
HAVE_LOCK=1; echo "$$" > "$LOCK/pid"
trap 'log "unexpected command failure at line $LINENO (exit $?)"; state_set status "error"; release_lock; exit 99' ERR
[ -f "$STATE" ] || state_set started_utc "$(date -u +%FT%TZ)"
if [ "$MODE" = --stage ]; then
  run_stage "$ARG"
else
  for s in "${STAGES[@]}"; do
    [ "$s" = S13 ] && [ "$ARG" != S13 ] && continue
    is_done "$s" && { log "$s already done: skipped"; [ "$s" = "$ARG" ] && break; continue; }
    run_stage "$s"
    [ "$s" = "$ARG" ] && break
  done
fi
log "finished: last completed stage $(state_get last_completed)"
