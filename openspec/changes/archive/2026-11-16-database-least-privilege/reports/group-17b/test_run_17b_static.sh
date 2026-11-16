#!/usr/bin/env bash
# Static tests of the DRIVER of run_17b.sh (TD-030, 17B.1): authorisation gate, lock, stage order, state file, signals, exit codes,
# rollback guidance, log sanitizing, resource gates. NO container is started and Docker is never called: the stages are replaced by
# stubs through G17B_TEST_HOOKS (accepted only in the test profile); the real profile is exercised only up to the refusals that
# happen before any command. Mutation testing at the end runs a mutated copy next to the script.
#
#   bash test_run_17b_static.sh                # tests + mutations
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
ORCH_REAL="$HERE/run_17b.sh"; ORCH="$ORCH_REAL"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"; rm -f "$HERE/run_17b.mut.sh"' EXIT
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  PASS $1"; else FAIL=$((FAIL+1)); echo "  FAIL $1 (expected '$2', got '$3')"; fi; }
STAGES="S10 S11 S12 S20 S21 S22 S23 S24 S25 S26 S30 S31"
declare -A CODE=([S10]=3 [S11]=10 [S12]=12 [S13]=13 [S20]=20 [S21]=21 [S22]=22 [S23]=23 [S24]=24 [S25]=25 [S26]=26 [S30]=30 [S31]=31)
declare -A HINT=([S10]="nothing to roll back" [S11]="nothing to roll back" [S12]="nothing to roll back" [S20]="shipped override" [S21]="steps 5, 6"
  [S22]="steps 3, 4, 5, 6" [S23]="steps 3, 4, 5, 6" [S24]="steps 3, 4, 5, 6" [S25]="steps 2, 3, 4, 5, 6" [S26]="steps 2, 3, 4, 5, 6" [S30]="steps 2, 3, 4, 5, 6" [S31]="steps 2, 3, 4, 5, 6")

cat > "$TMP/hooks.sh" <<'H'
stub_stage() {
  hook_sleep; hook_fail
  log "stub stage $CURRENT done"
  [ "${STUB_RAW:-}" = "$CURRENT" ] && false
  [ "${STUB_LEAK:-}" = "$CURRENT" ] && log "path $USERPROFILE/x user $USERNAME url postgresql://u:topsecret@h:5432/d"
  [ "${STUB_GATE:-}" = "$CURRENT" ] && gate_resources
  return 0
}
st_preflight() { state_set cluster_id stub-1; stub_stage; }; st_backup_validate() { stub_stage; }; st_images() { stub_stage; }; st_settings_load() { stub_stage; }
st_stop_services() { stub_stage; }; st_prepare_env() { stub_stage; }; st_bootstrap() { stub_stage; }; st_adopt_dry() { stub_stage; }
st_adopt_apply() { stub_stage; }; st_migrate() { stub_stage; }; st_db_verify() { stub_stage; }; st_switch() { stub_stage; }; st_sessions() { stub_stage; }
H
cat > "$TMP/cfg.sh" <<'C'
PROJECT=g17bstat
DBC=g17bstat-db-1
API_C=g17bstat-backend-1
WORKER_C=g17bstat-worker-1
EXPECTED_SYSID=""
ENV_DIR="/tmp/g17bstat-env"
BACKUPS="/tmp/g17bstat-b1"
SECOND="/tmp/g17bstat-b2"
DC_FILES=(-f "/tmp/g17bstat/a.yml" -f "/tmp/g17bstat/b.yml")
C
newstate() { rm -rf "$TMP/state"; mkdir -p "$TMP/state"; }
o() { G17B_PROFILE=test G17B_TEST_CONFIG="$TMP/cfg.sh" G17B_TEST_HOOKS="$TMP/hooks.sh" G17B_STATE_DIR="$TMP/state" bash "$ORCH" "$@" > "$TMP/out.txt" 2>&1; RC=$?; }
real() { G17B_STATE_DIR="$TMP/state" "$@" > "$TMP/out.txt" 2>&1; RC=$?; }
sget() { sed -n "s/^$1=//p" "$TMP/state/state" | tail -1; }
upto() { # run stages in order until (not including) $1
  for s in $STAGES; do [ "$s" = "$1" ] && return; o --stage "$s"; done
}

t_syntax() {
  echo "== syntax"
  bash -n "$ORCH_REAL"; check "bash -n run_17b.sh" 0 $?
  for f in test_run_17b.sh test_run_17b_static.sh test_env_acl_docker.sh; do bash -n "$HERE/$f"; check "bash -n $f" 0 $?; done
}
t_gate() {
  echo "== authorisation gate (real profile; every refusal happens before any command)"
  newstate
  for st in S20 S21 S22 S23 S24 S25 S26 S30 S31; do
    real bash "$ORCH" --stage $st; check "real profile refuses $st without the owner's GO (exit 7)" 7 $RC
  done
  G17B_OWNER_GO=yes real bash "$ORCH" --stage S20; check "a wrong token is refused (exit 7)" 7 $RC
  G17B_OWNER_GO=go-17b.2 real bash "$ORCH" --stage S20; check "a token with other case is refused (exit 7)" 7 $RC
  newstate
  G17B_OWNER_GO=GO-17B.2 real bash "$ORCH" --stage S31; check "the right token does not skip the order: S10 must be done first (exit 6, no command reached)" 6 $RC
  grep -q 'must be done before' "$TMP/out.txt"; check "the message names the missing predecessor" 0 $?
  check "nothing was marked done" "" "$(sget done)"
  for v in G17B_TEST_FAIL_AT G17B_TEST_SLEEP_AT G17B_TEST_CONFIG G17B_TEST_HOOKS; do
    env "$v=x" G17B_STATE_DIR="$TMP/state" bash "$ORCH" --plan > "$TMP/out.txt" 2>&1; check "$v is refused in the real profile (exit 7)" 7 $?
  done
}
t_usage() {
  echo "== usage and state-dir rules"
  newstate
  G17B_PROFILE=bogus G17B_STATE_DIR="$TMP/state" bash "$ORCH" --plan > /dev/null 2>&1; check "unknown profile (exit 2)" 2 $?
  G17B_STATE_DIR="$REPO/zz-state-should-not-exist" bash "$ORCH" --plan > /dev/null 2>&1; check "a state dir inside the repository is refused (exit 2)" 2 $?
  [ ! -e "$REPO/zz-state-should-not-exist/state" ]; check "and it holds no state" 0 $?
  rm -rf "$REPO/zz-state-should-not-exist"
  real bash "$ORCH"; check "no argument (usage, exit 2)" 2 $RC
  real bash "$ORCH" --stage S99; check "unknown stage (exit 2)" 2 $RC
  real bash "$ORCH" --plan; check "--plan works" 0 $RC
  check "plan lists 13 stages" 13 "$(grep -c '^S[0-9]' "$TMP/out.txt")"
  check "nine of them are marked as writing" 9 "$(grep -c 'WRITES' "$TMP/out.txt")"
}
t_sequence() {
  echo "== complete sequence on stubs, state file"
  newstate; o --through S31; check "S10..S31 on stubs (exit 0)" 0 $RC
  check "done lists the twelve stages (S13 is optional)" "S10,S11,S12,S20,S21,S22,S23,S24,S25,S26,S30,S31" "$(sget done)"
  check "last_completed=S31" S31 "$(sget last_completed)"
  o --stage S13; check "the optional S13 can run afterwards" 0 $RC
  check "the state file holds only known keys and no secret" "" "$(grep -vE '^(started_utc|done|chain|last_completed|failed|interrupted|uncertain|status|cluster_id)=' "$TMP/state/state")"
  o --through S31; check "--through over finished stages changes nothing (exit 0)" 0 $RC
}
t_double() {
  echo "== accidental second run and order"
  newstate; o --stage S10; check "S10 (exit 0)" 0 $RC
  o --stage S10; check "S10 again is refused (exit 6)" 6 $RC
  o --stage S21; check "skipping to S21 is refused (exit 6)" 6 $RC
  o --stage S11; check "S11 (exit 0)" 0 $RC
}
t_lock() {
  echo "== concurrent run"
  newstate
  G17B_TEST_SLEEP_AT=S10:12 bash -c 'G17B_PROFILE=test G17B_TEST_CONFIG="'"$TMP"'/cfg.sh" G17B_TEST_HOOKS="'"$TMP"'/hooks.sh" G17B_STATE_DIR="'"$TMP"'/state" bash "'"$ORCH"'" --stage S10 > "'"$TMP"'/bg.out" 2>&1' &
  BG=$!
  for i in $(seq 1 160); do grep -q 'sleeping' "$TMP/bg.out" 2>/dev/null && break; sleep 0.5; done
  o --stage S10; check "a concurrent run is refused (exit 5)" 5 $RC
  wait $BG; check "the first run finishes (exit 0)" 0 $?
  check "the lock is gone afterwards" 0 "$([ -d "$TMP/state/lock" ] && echo 1 || echo 0)"
  check "and S10 is done exactly once" S10 "$(sget done)"
}
t_codes() {
  echo "== exit codes, failed stage, rollback guidance, and the sequence stops"
  for target in $STAGES; do
    newstate; upto "$target"
    G17B_TEST_FAIL_AT=$target o --stage "$target"
    check "$target failure -> exit ${CODE[$target]}" "${CODE[$target]}" $RC
    check "$target: failed=$target" "$target" "$(sget failed)"
    grep -q "${HINT[$target]}" "$TMP/out.txt"; check "$target: rollback guidance mentions '${HINT[$target]}'" 0 $?
    grep -q 'NOT started' "$TMP/out.txt"; check "$target: says the next stage was not started" 0 $?
    nxt=$(echo $STAGES | tr ' ' '\n' | grep -A1 "^$target$" | tail -1)
    if [ "$nxt" != "$target" ]; then o --stage "$nxt"; check "$target: the next stage $nxt is refused (exit 6)" 6 $RC; fi
    check "$target: not marked done" 0 "$(case ",$(sget done)," in *",$target,"*) echo 1;; *) echo 0;; esac)"
  done
  newstate; STUB_RAW=S10 o --stage S10; check "an unexpected command failure -> exit 99" 99 $RC
  check "state: failed=S10 and status=failed:S10" "failed:S10|S10" "$(sget status)|$(sget failed)"
  check "the lock was released after an unexpected failure" 0 "$([ -d "$TMP/state/lock" ] && echo 1 || echo 0)"
}
t_ram() {
  echo "== RAM and disk gates"
  newstate; STUB_GATE=S10 G17B_MIN_RAM_GB=9999 o --stage S10; check "RAM below the threshold -> exit 4" 4 $RC
  newstate; STUB_GATE=S10 G17B_MIN_DISK_GB=99999 o --stage S10; check "disk below the threshold -> exit 4" 4 $RC
  newstate; STUB_GATE=S10 o --stage S10; check "enough RAM and disk -> exit 0 (default 8 GB / 15 GB)" 0 $RC
}
t_leak() {
  echo "== sanitized log"
  newstate; STUB_LEAK=S10 o --stage S10; check "stage with a path, user and URL runs" 0 $RC
  check "the log has no user name" 0 "$(grep -c "$USERNAME" "$TMP/state/run.log")"
  check "the log has no profile path" 0 "$(grep -ci 'C:/Users\|C:\\\\Users' "$TMP/state/run.log")"
  check "the log has no URL credentials" 0 "$(grep -c 'topsecret' "$TMP/state/run.log")"
  check "the URL is replaced by a marker" 1 "$(grep -c 'redacted' "$TMP/state/run.log")"
  check "console output is sanitized too" 0 "$(grep -c "topsecret\|$USERNAME" "$TMP/out.txt")"
}
t_signal() {
  echo "== SIGTERM and SIGINT"
  for sig in TERM INT; do
    newstate
    set -m   # job control: a background job otherwise ignores SIGINT from the start (as a Ctrl+C in a terminal does not)
    G17B_TEST_SLEEP_AT=S10:90 bash -c 'G17B_PROFILE=test G17B_TEST_CONFIG="'"$TMP"'/cfg.sh" G17B_TEST_HOOKS="'"$TMP"'/hooks.sh" G17B_STATE_DIR="'"$TMP"'/state" bash "'"$ORCH"'" --stage S10 > "'"$TMP"'/int.out" 2>&1' &
    BG=$!; set +m
    for i in $(seq 1 160); do grep -q 'sleeping' "$TMP/int.out" 2>/dev/null && break; sleep 0.5; done
    PID=$(cat "$TMP/state/lock/pid"); kill -$sig "$PID" 2>/dev/null
    wait $BG; RC=$?
    check "SIG$sig -> exit 40" 40 $RC
    check "SIG$sig: interrupted=S10" S10 "$(sget interrupted)"
    check "SIG$sig: lock released" 0 "$([ -d "$TMP/state/lock" ] && echo 1 || echo 0)"
    grep -q 'INTERRUPTED' "$TMP/int.out"; check "SIG$sig: the log says INTERRUPTED" 0 $?
    grep -q 'rollback that applies' "$TMP/int.out"; check "SIG$sig: rollback guidance printed" 0 $?
    sleep 1
    check "SIG$sig: no 'sleep 90' left running" 0 "$(ps -ef | grep -c '[s]leep 90')"
    check "SIG$sig: S10 not marked done" "" "$(sget done)"
    o --stage S10; check "SIG$sig: after the interruption the stage can run again" 0 $RC
  done
  newstate; STUB_RAW=S10 o --stage S10 > /dev/null; o --status; check "--status works after a failure without any container" 0 $RC
  grep -q 'failed=S10' "$TMP/out.txt"; check "status prints failed=S10" 0 $?
  grep -q 'rollback that applies' "$TMP/out.txt"; check "status prints the rollback that applies" 0 $?
}


t_guard() {
  echo "== test profile cannot name the real stack"
  newstate
  for v in "DBC=asistenteia-db-1" "PROJECT=asistenteia" "API_C=asistenteia-backend-1" "WORKER_C=asistenteia-worker-1"; do
    cp "$TMP/cfg.sh" "$TMP/cfg.keep"; echo "$v" >> "$TMP/cfg.sh"
    o --plan; check "test profile naming the real object ($v) is refused (exit 7)" 7 $RC
    cp "$TMP/cfg.keep" "$TMP/cfg.sh"
  done
  U="$(cygpath -u "$USERPROFILE")"
  for v in 'ENV_DIR="'"$REPO"'/backend"' 'ENV_DIR="'"$REPO"'/backend/sub"' 'BACKUPS="'"$U"'/Backups/AsistenteIA"' 'SECOND="'"$U"'/Backups/AsistenteIA-second/x"' 'DC_FILES=(-f "'"$REPO"'/docker-compose.yml")'; do
    cp "$TMP/cfg.sh" "$TMP/cfg.keep"; echo "$v" >> "$TMP/cfg.sh"
    o --plan; check "test profile keeping a real path or compose file is refused (exit 7): ${v%%=*}" 7 $RC
    cp "$TMP/cfg.keep" "$TMP/cfg.sh"
  done
  o --plan; check "a config with only disposable names works (exit 0)" 0 $RC
}
t_rerun() {
  echo "== a write stage that did not finish cleanly needs the owner's confirmation to run again"
  newstate; upto S20
  G17B_TEST_FAIL_AT=S20 o --stage S20; check "S20 fails (exit 20)" 20 $RC
  o --stage S20; check "rerun of the failed write stage is refused (exit 8)" 8 $RC
  G17B_CONFIRM_RERUN=S21 o --stage S20; check "a confirmation for another stage does not help (exit 8)" 8 $RC
  G17B_CONFIRM_RERUN=S20 o --stage S20; check "with G17B_CONFIRM_RERUN=S20 the rerun is accepted (exit 0)" 0 $RC
  # interrupted write stage: outcome unknown
  newstate; upto S20; set -m
  G17B_TEST_SLEEP_AT=S20:90 bash -c 'G17B_PROFILE=test G17B_TEST_CONFIG="'"$TMP"'/cfg.sh" G17B_TEST_HOOKS="'"$TMP"'/hooks.sh" G17B_STATE_DIR="'"$TMP"'/state" bash "'"$ORCH"'" --stage S20 > "'"$TMP"'/int.out" 2>&1' &
  BG=$!; set +m
  for i in $(seq 1 160); do grep -q 'sleeping' "$TMP/int.out" 2>/dev/null && break; sleep 0.5; done
  kill -TERM "$(cat "$TMP/state/lock/pid")" 2>/dev/null; wait $BG; check "interrupted write stage -> exit 40" 40 $?
  check "state: uncertain=S20" S20 "$(sget uncertain)"
  grep -q 'UNKNOWN' "$TMP/int.out"; check "the log says the outcome is unknown" 0 $?
  o --stage S20; check "rerun after the interruption is refused (exit 8)" 8 $RC
  o --status; grep -q 'uncertain=S20' "$TMP/out.txt"; check "status shows uncertain=S20" 0 $?
  G17B_CONFIRM_RERUN=S20 o --stage S20; check "confirmed rerun works" 0 $RC
  check "uncertain is cleared once the stage completes" "" "$(sget uncertain)"
}
t_state() {
  echo "== state integrity and pinned identity"
  newstate; upto S21
  sed -i 's/^done=.*/done=S10,S11,S12,S20,S21,S22,S23/' "$TMP/state/state"
  o --stage S24; check "a hand-edited done list is refused (exit 6)" 6 $RC
  grep -q 'edited by hand' "$TMP/out.txt"; check "the message says the state was edited" 0 $?
  o --status; grep -q 'state_integrity=EDITED-OR-CORRUPT' "$TMP/out.txt"; check "status reports the edit" 0 $?
  newstate; upto S12
  sed -i '/^cluster_id=/d' "$TMP/state/state"
  o --stage S12; check "removing the cluster id also breaks the chain: refused (exit 6)" 6 $RC
  # a forged state: no cluster id AND a chain recomputed for it (an informed edit) is still refused by the pinned-identity rule
  c=g17b; for st in S10 S11; do c=$(printf '%s|%s|%s' "$c" "$st" "" | sha256sum | cut -d' ' -f1); done
  sed -i "s/^chain=.*/chain=$c/" "$TMP/state/state"
  o --stage S12; check "no cluster id pinned by S10, even with a consistent chain, is refused (exit 3)" 3 $RC
  newstate; mkdir -p "$TMP/state/lock"; echo 999999 > "$TMP/state/lock/pid"
  o --stage S10; check "a stale lock is refused (exit 5)" 5 $RC
  grep -q 'stale lock' "$TMP/out.txt"; check "and the message says the lock is stale" 0 $?
  rm -rf "$TMP/state/lock"
}

t_s13() {
  echo "== S13 reads the real env files only with the owner's flag (refused before any docker call)"
  newstate; upto S20    # S10..S12 on stubs: a valid state file with a pinned (stub) identity
  G17B_STATE_DIR="$TMP/state" bash "$ORCH" --stage S13 > "$TMP/out.txt" 2>&1; RC=$?
  check "real profile: S13 without --allow-real-settings is refused (exit 7)" 7 $RC
  grep -q 'allow-real-settings' "$TMP/out.txt"; check "the message names the flag" 0 $?
  check "S13 is not marked done" "" "$(case ",$(sget done)," in *",S13,"*) echo done;; esac)"
}

run_all() { t_syntax; t_gate; t_usage; t_guard; t_sequence; t_double; t_lock; t_codes; t_rerun; t_state; t_s13; t_ram; t_leak; t_signal; }
run_all
echo "== tests: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ] || { echo "tests failed: mutation testing skipped"; exit 1; }

# ------------------------------------------------------------------ mutation testing: a mutated copy next to the script
echo "== mutation testing (each mutation must make at least one check fail)"
MUT="$HERE/run_17b.mut.sh"
MFAIL=0
mutate() { # name, python-expression old, new, test function
  local name="$1" old="$2" new="$3" fn="$4"
  python - "$(cygpath -w "$ORCH_REAL")" "$(cygpath -w "$MUT")" "$old" "$new" <<'PY'
import sys
src, dst, old, new = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
if old not in text:
    print("MUTATION TEXT NOT FOUND"); sys.exit(3)
open(dst, "w", encoding="utf-8", newline="\n").write(text.replace(old, new, 1))
PY
  [ $? = 0 ] || { echo "  FAIL mutation '$name': pattern not found"; MFAIL=$((MFAIL+1)); return; }
  ORCH="$MUT"; local b=$FAIL; "$fn" > "$TMP/mut.out" 2>&1; ORCH="$ORCH_REAL"
  local d=$((FAIL-b)); FAIL=$b; PASS=$PASS
  if [ "$d" -gt 0 ]; then echo "  PASS mutation '$name' is detected ($d check(s) fail)"; else echo "  FAIL mutation '$name' SURVIVED"; MFAIL=$((MFAIL+1)); fi
}
mutate "authorisation gate removed" 'needs_go() { case "$1" in S2*|S3*) return 0;; esac; return 1; }' 'needs_go() { return 1; }' t_gate
mutate "token compared loosely" '[ "${G17B_OWNER_GO:-}" = "GO-17B.2" ] || die 7 "$st writes' '[ -n "${G17B_OWNER_GO:-}" ] || die 7 "$st writes' t_gate
mutate "lock not exclusive" 'if ! mkdir "$LOCK" 2>/dev/null; then' 'if ! mkdir -p "$LOCK" 2>/dev/null; then' t_lock
mutate "done stage not refused" '  is_done "$st" && die 6 "stage $st is already done: refused (accidental second run)"' '  :' t_double
mutate "stage order not enforced" '    is_done "$s" || die 6 "stage $s must be done before $st"' '    :' t_double
mutate "rollback guidance of the adoption lost" '    S22|S23|S24) echo' '    S2X) echo' t_codes
mutate "failed stage not recorded" '    state_set failed "$st"; state_set status "failed:$st"' '    state_set status "failed:$st"' t_codes
mutate "log not sanitized" "log() { printf '%s %s\\n' \"\$(date -u +%H:%M:%S)\" \"\$*\" | san | tee -a \"\$LOG\"; }" "log() { printf '%s %s\\n' \"\$(date -u +%H:%M:%S)\" \"\$*\" | tee -a \"\$LOG\"; }" t_leak
mutate "RAM gate does not stop" 'die 4 "less than ${MIN_RAM} GB of free RAM: NO-GO"' 'true' t_ram
mutate "interruption not recorded" 'state_set interrupted "${CURRENT:-none}"; state_set status interrupted' ':' t_signal
mutate "next stage not refused after a failure" '    is_done "$s" || die 6 "stage $s must be done before $st"' '    :' t_codes
mutate "test profile may name the real stack" 'echo "REFUSED: the test profile may not name any object of the real stack"; exit 7' ':' t_guard
mutate "test profile may keep the real env folder" 'echo "REFUSED: the test profile must set its own ENV_DIR (it points at the real env folder)"; exit 7' ':' t_guard
mutate "S13 flag not required in the real profile" 'if [ "$PROFILE" = real ] && [ "$ALLOW_REAL_SETTINGS" != 1 ]; then die 7 "loading the settings' 'if false; then die 7 "loading the settings' t_s13
mutate "write stage rerun without confirmation" 'die 8 "$st started before' 'true "$st started before' t_rerun
mutate "hand-edited state accepted" 'die 6 "the state file was edited by hand' 'true "the state file was edited by hand' t_state
mutate "missing cluster pin accepted by the driver" 'die 3 "no cluster identity pinned by S10 in the state file: refused"; fi' 'true; fi' t_state
mutate "stale lock indistinguishable" 'die 5 "stale lock:' 'die 0 "stale lock:' t_state
echo "== mutations: $MFAIL survived or not applicable"
echo "== final: tests PASS=$PASS FAIL=$FAIL; mutation problems=$MFAIL"
[ "$FAIL" = 0 ] && [ "$MFAIL" = 0 ]
