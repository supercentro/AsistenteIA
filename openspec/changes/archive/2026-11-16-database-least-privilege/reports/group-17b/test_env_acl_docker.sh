#!/usr/bin/env bash
# Synthetic test (TD-030, 17B.1): the env files that prepare_env_files.py creates, restricted with secure_file_acl.ps1 -Rights Modify,
# stay usable: readable and editable by the current user, readable by Docker Desktop (`docker run --env-file` and a compose
# `env_file`), and the tool's own rollback still works on them. Synthetic files only; no real .env is read or written;
# Docker is used only after the 8 GB RAM gate, with a throw-away container and a throw-away compose project.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
R="$(cd "$HERE/.." && pwd)"
TOOLS17A="$R/group-17a/tools"; TOOLS17C="$R/group-17c/tools"
W() { cygpath -w "$1"; }
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 (expected $2, got $3)"; fi; }
RAM=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r')
python -c "import sys; sys.exit(0 if float('$RAM') >= 8 else 1)" || { echo "RAM below 8 GB ($RAM): stop"; exit 4; }
echo "free RAM before Docker: $RAM GB"
T="$(mktemp -d)"; F="$T/backend"; mkdir -p "$F"
cleanup() { for p in "$T"/backend/.env* "$T"/backend/probe.env "$T"/compose.yml; do [ -e "$p" ] && powershell -NoProfile -Command "icacls '$(W "$p")' /reset | Out-Null" 2>/dev/null; done; docker compose -p g17benv -f "$(W "$T/compose.yml")" down -v --remove-orphans >/dev/null 2>&1; rm -rf "$T"; }
trap cleanup EXIT

# 1. synthetic env folder with the legacy variables, then the real tool with --strip-legacy
python -I "$(W "$HERE/make_synthetic_env.py")" "$(W "$F")"
python -I "$(W "$TOOLS17A/prepare_env_files.py")" "$(W "$F")" --dry-run --strip-legacy > /dev/null; check "dry run accepts the synthetic folder" 0 $?
python -I "$(W "$TOOLS17A/prepare_env_files.py")" "$(W "$F")" --strip-legacy > "$T/tool.out" 2>&1; check "prepare_env_files.py --strip-legacy runs" 0 $?
check "no legacy name is left in .env and .env.worker" 0 "$(grep -cE '^(POSTGRES_(USER|PASSWORD|DB)|TEST_[A-Z0-9_]+)=' "$F/.env" "$F/.env.worker" | awk -F: '{s+=$2} END {print s+0}')"
# 2. restrict the four new files
for f in .env.roles .env.migrate .env.cli .env.test; do
  powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$TOOLS17C/secure_file_acl.ps1")" -Path "$(W "$F/$f")" -Rights Modify > "$T/acl.out"; check "$f: restricted (single rule, current user, Modify)" 0 $?
  powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$TOOLS17C/secure_file_acl.ps1")" -Path "$(W "$F/$f")" -Rights Modify -VerifyOnly > /dev/null; check "$f: verify-only agrees" 0 $?
  powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$TOOLS17C/secure_file_acl.ps1")" -Path "$(W "$F/$f")" -VerifyOnly > /dev/null; check "$f: it is NOT the Read-only descriptor" 1 $?
done
# 3. the owner can still read and edit them (the rotation edits .env.roles, .env.migrate and .env.test)
cp "$F/.env.roles" "$T/roles.copy"; echo "# edited" >> "$F/.env.roles"; check "the current user can edit .env.roles after the restriction" 0 $?
check "the edit is there and the file is still readable" 1 "$(grep -c '^# edited' "$F/.env.roles")"
# 4. Docker Desktop reads them: docker run --env-file (count of variables only, nothing printed)
IMG="${G17B_ENV_TEST_IMAGE:-asistenteia-backend:latest}"
N=$(docker run --rm --env-file "$(W "$F/.env.roles")" --entrypoint python "$IMG" -c "import os; print(sum(1 for k in os.environ if k.startswith('DB_') or k == 'ADMIN_DATABASE_URL'))" 2>/dev/null)
check "docker run --env-file reads the restricted .env.roles (5 variables seen)" 5 "$N"
# 5. compose env_file reads them too (throw-away project, one container, removed afterwards)
cat > "$T/compose.yml" <<YML
services:
  t:
    image: $IMG
    env_file:
      - path: ./backend/.env.migrate
        required: false
    entrypoint: ["python", "-c", "import os; print(sum(1 for k in os.environ if k == 'MIGRATION_DATABASE_URL'))"]
YML
OUT=$(docker compose -p g17benv --project-directory "$(W "$T")" -f "$(W "$T/compose.yml")" run --rm --no-deps t 2>/dev/null | tail -1 | tr -d '\r')
check "compose env_file reads the restricted .env.migrate" 1 "$OUT"
# 6. the tool's own rollback works on restricted files (new files renamed, .env and .env.worker restored)
python -I "$(W "$TOOLS17A/prepare_env_files.py")" "$(W "$F")" --rollback > "$T/rb.out" 2>&1; check "prepare_env_files.py --rollback works with the restricted files" 0 $?
check "the three role files were renamed *.rolled-back" 3 "$(ls -A "$F" | grep -c '^\.env\.\(roles\|migrate\|cli\)\.rolled-back$')"
# 7. why Modify and not Read: with the Read descriptor an edit is refused
echo "X=1" > "$F/probe.env"
powershell -NoProfile -ExecutionPolicy Bypass -File "$(W "$TOOLS17C/secure_file_acl.ps1")" -Path "$(W "$F/probe.env")" > /dev/null 2>&1; check "probe file restricted to Read" 0 $?
( echo "# x" >> "$F/probe.env" ) 2>/dev/null; check "a Read-only descriptor blocks the rotation's edit (so Modify is used for env files)" 1 $?
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]
