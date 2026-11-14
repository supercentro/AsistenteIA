#!/usr/bin/env bash
# S13 validation (TD-030, 17B.1): are the NEW images compatible with the CURRENT real configuration? READ ONLY.
#
# What it does: reads the real backend env files in memory (never prints a value), simulates the 17B.2 transformation without writing
# anything, and loads each service's settings in a throw-away container of the new image (`--network none`, `--rm`, memory limited,
# no volume, no port) that receives the simulated environment on STDIN (never on a command line, never saved). Then it runs the
# orchestrator's S13 on the real files. It writes no file under backend/, starts no service and never connects to PostgreSQL.
# Refuses to start with less than 8 GB of free RAM.
#   bash run_s13_validation.sh            # prints a sanitized report; redirect it to the evidence file
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../../../.." && pwd)"
R17A="$REPO/openspec/changes/database-least-privilege/reports/group-17a/tools"
ENVD="$REPO/backend"
W() { cygpath -w "$1"; }
PY=python
RAM=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r' | tr ',' '.')
python -c "import sys; sys.exit(0 if float('$RAM') >= 8 else 1)" || { echo "free RAM $RAM GB < 8: stop, no Docker used"; exit 4; }
echo "free RAM before Docker: $RAM GB; HEAD $(cd "$REPO" && git rev-parse --short HEAD)"
fingerprint() { for f in .env .env.worker .env.db; do printf '%s ' "$f"; sha256sum "$ENVD/$f" | cut -d' ' -f1; done | sha256sum | cut -d' ' -f1; }   # compared, never printed
listing() { ls -A "$ENVD" | grep -E '^\.env' | tr '\n' ' '; }
mtimes() { for f in $(ls -A "$ENVD" | grep -E '^\.env'); do stat -c '%n %s %Y' "$ENVD/$f"; done | sha256sum | cut -d' ' -f1; }
FP0="$(fingerprint)"; LS0="$(listing)"; MT0="$(mtimes)"
CONT0="$(docker ps -a --format '{{.ID}}' | sort | while read -r c; do docker inspect -f '{{.Id}} {{.Name}} {{.State.Status}} {{.Image}}' "$c"; done)"
echo "env files in backend/ before (names only): $LS0"

echo; echo "== 1. effects of S13 (read from run_17b.sh st_settings_load)"
echo "   creates and removes two throw-away containers (docker run --rm) from asistenteia-backend:latest and asistenteia-worker:latest; --env-file reads the real .env and .env.worker into their environment; output discarded; no volume, no published port; python imports app.core.config only (no database connection); no write to any env file; no compose, no start/stop/recreate of a service."

echo; echo "== 2. dry run of the transformation (names and verdicts only)"
$PY -I "$(W "$HERE/s13_env_dryrun.py")" report "$(W "$ENVD")"; echo "report exit=$?"
echo; echo "-- prepare_env_files.py --dry-run --strip-legacy on the real folder (writes nothing)"
$PY -I "$(W "$R17A/prepare_env_files.py")" "$(W "$ENVD")" --dry-run --strip-legacy; echo "dry run exit=$?"
echo; echo "-- variable names against the examples (check_env_names.py)"
$PY -I "$(W "$R17A/check_env_names.py")" "$(W "$ENVD")"; echo "names check exit=$?"

echo; echo "== 3. the new images read the configuration (simulated environment on stdin, --network none)"
CODE="$(cat "$HERE/s13_container_loader.py")"
declare -A IMG=([api]=asistenteia-backend:latest [api-asis]=asistenteia-backend:latest [worker]=asistenteia-worker:latest [worker-asis]=asistenteia-worker:latest
                [migrator]=asistenteia-migrate:latest [cli]=asistenteia-cli:latest [roles]=asistenteia-bootstrap:latest [verify]=asistenteia-migrate:latest)
BAD=0
for svc in api-asis worker-asis api worker migrator cli roles verify; do
  $PY -I "$(W "$HERE/s13_env_dryrun.py")" env "$(W "$ENVD")" "$svc" | docker run -i --rm --network none -m 512m --cpus 1 --entrypoint python "${IMG[$svc]}" -c "$CODE" "$svc" 2>&1 | tail -2
  [ "${PIPESTATUS[1]}" = 0 ] || BAD=$((BAD+1))
done
echo "-- the images carry no real env file (names under /app that start with .env):"
for i in asistenteia-backend:latest asistenteia-worker:latest asistenteia-migrate:latest; do
  printf '%s: ' "$i"; docker run --rm --network none --entrypoint sh "$i" -c 'ls -A /app | grep "^\.env" | tr "\n" " "'; echo
done

echo; echo "== 4. S13 of the orchestrator on the REAL files (read only)"
G17B_STATE_DIR="$USERPROFILE/.g17b-state/real" bash "$HERE/run_17b.sh" --stage S13 --allow-real-settings 2>&1 | tail -6
S13RC=${PIPESTATUS[0]}; echo "S13 exit=$S13RC"

echo; echo "== 5. no writes, no side effects"
[ "$(fingerprint)" = "$FP0" ] && echo "contents of .env, .env.worker and .env.db unchanged: yes" || { echo "contents of the real env files CHANGED"; BAD=$((BAD+1)); }
[ "$(listing)" = "$LS0" ] && echo "env file names in backend/ unchanged: yes" || { echo "env file names CHANGED"; BAD=$((BAD+1)); }
[ "$(mtimes)" = "$MT0" ] && echo "sizes and modification times of the env files unchanged: yes" || { echo "sizes/mtimes CHANGED"; BAD=$((BAD+1)); }
CONT1="$(docker ps -a --format '{{.ID}}' | sort | while read -r c; do docker inspect -f '{{.Id}} {{.Name}} {{.State.Status}} {{.Image}}' "$c"; done)"
[ "$CONT0" = "$CONT1" ] && echo "containers (ids, names, states, image ids) before and after identical: yes (no throw-away container left)" || { echo "container list CHANGED"; BAD=$((BAD+1)); }
echo "git status of the tracked tree: $(cd "$REPO" && git status --short | grep -vc '^??') modified tracked file(s)"
echo "RESULT: $([ "$BAD" = 0 ] && [ "$S13RC" = 0 ] && echo 'ALL CHECKS PASSED' || echo "PROBLEMS: $BAD (S13 exit $S13RC)")"
[ "$BAD" = 0 ] && [ "$S13RC" = 0 ]
