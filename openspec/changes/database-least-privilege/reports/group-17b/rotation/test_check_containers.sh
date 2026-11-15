#!/usr/bin/env bash
# Test of check_containers_for_value.py with SYNTHETIC values on CREATED (never started) disposable containers.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"; W() { cygpath -w "$1"; }
IMG=pgvector/pgvector:0.8.7-pg15; LABEL=purpose=g17b-rot-test; PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  PASS $1"; else FAIL=$((FAIL+1)); echo "  FAIL $1 (expected '$2', got '$3')"; fi; }
T="$(mktemp -d)"; trap 'docker rm -f g17bchk-a g17bchk-b >/dev/null 2>&1; rm -rf "$T"' EXIT
mkdir -p "$T/backend"; VAL="Syn$(python -c 'import secrets;print(secrets.token_urlsafe(30))')"
printf 'DB_MIGRATOR_PASSWORD=%s\n' "$VAL" > "$T/backend/.env.roles"
docker create --name g17bchk-a --label $LABEL -e "SOME_URL=postgresql://x:$VAL@h/db" $IMG >/dev/null 2>&1; check "container with the value created" 0 $?
docker create --name g17bchk-b --label $LABEL -e "OTHER=nothing" $IMG >/dev/null 2>&1; check "container without the value created" 0 $?
python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/backend")" > "$T/out.txt" 2>&1; rc=$?
check "exit 1 when a container holds the value" 1 $rc
check "it names the holder and not the other one" "1 0" "$(grep -c 'g17bchk-a' "$T/out.txt") $(grep -c 'g17bchk-b' "$T/out.txt")"
check "the value is never printed" 0 "$(grep -c -e "$VAL" "$T/out.txt")"
docker rm -f g17bchk-a >/dev/null 2>&1
python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/backend")" > "$T/out2.txt" 2>&1; check "exit 0 once the holder is removed" 0 $?
printf 'DB_MIGRATOR_PASSWORD="%s"\n' "$VAL" > "$T/backend/.env.roles"; docker create --name g17bchk-a --label $LABEL -e "SOME_URL=postgresql://x:$VAL@h/db" $IMG >/dev/null 2>&1
python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/backend")" >/dev/null 2>&1; check "a QUOTED variable is unquoted before the scan: the holder is found (exit 1)" 1 $?
docker rm -f g17bchk-a >/dev/null 2>&1
VAL2='Syn&Pw<x>0123456789abcdefABCDEF'; printf 'DB_MIGRATOR_PASSWORD=%s\n' "$VAL2" > "$T/backend/.env.roles"; docker create --name g17bchk-a --label $LABEL -e "SOME=$VAL2" $IMG >/dev/null 2>&1
python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/backend")" > "$T/out3.txt" 2>&1; rc3=$?; check "a value with & < > is found although Go's JSON encoder escapes them in docker inspect (exit 1), and is not printed" "1 0" "$rc3 $(grep -c -F -e "$VAL2" "$T/out3.txt")"
docker rm -f g17bchk-a >/dev/null 2>&1
printf 'OTHER=1\n' > "$T/backend/.env.roles"; python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/backend")" >/dev/null 2>&1; check "exit 2 when the variable is missing" 2 $?
python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/nonexistent")" >/dev/null 2>&1; check "exit 2 when the folder is missing" 2 $?
echo "PASS=$PASS FAIL=$FAIL"; [ "$FAIL" = 0 ]
