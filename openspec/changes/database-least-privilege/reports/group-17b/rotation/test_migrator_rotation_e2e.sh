#!/usr/bin/env bash
# End-to-end rehearsal of the SEC-17B-01 rotation of `asistente_migrator` on a DISPOSABLE PostgreSQL with SYNTHETIC credentials.
# Never touches the real stack: own network, own volume, container labelled purpose=g17b-rot-test, no published port. A `docker` shim
# records every argument and the standard input. Refuses to start with less than 8 GB of free RAM.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
W() { cygpath -w "$1"; }
DBTOOL="$HERE/rotate_db_role.py"; FILETOOL="${ROT_FILE_TOOL:-$HERE/rotate_role_password.py}"
ACL="$HERE/../../group-17c/tools/secure_file_acl.ps1"
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  PASS $1"; else FAIL=$((FAIL+1)); echo "  FAIL $1 (expected '$2', got '$3')"; fi; }
RAM=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r' | tr ',' '.')
python -c "import sys; sys.exit(0 if float('$RAM') >= 8 else 1)" || { echo "free RAM $RAM GB < 8: stop, no Docker used"; exit 4; }
echo "free RAM before Docker: $RAM GB"
IMG=pgvector/pgvector:0.8.7-pg15; NET=g17bmig-net; VOL=g17bmig-vol; C=g17bmig-db; LABEL=purpose=g17b-rot-test
T="$(mktemp -d)"; ARGLOG="$T/docker-argv.log"; STDINLOG="$T/docker-stdin.log"
REALDOCKER="$(command -v docker.exe || command -v docker)"
export ROT_TEST_HOOKS=1 ROT_SHIM_ARGLOG="$(W "$ARGLOG")" ROT_SHIM_STDINLOG="$(W "$STDINLOG")" ROT_SHIM_REAL="$(W "$REALDOCKER")"
export ROT_DOCKER_CMD="[\"$(cygpath -m "$(command -v python)")\", \"$(cygpath -m "$HERE/docker_shim.py")\"]"
cleanup() { docker rm -f $C >/dev/null 2>&1; docker volume rm -f $VOL >/dev/null 2>&1; docker network rm $NET >/dev/null 2>&1; rm -rf "$T"; }
trap cleanup EXIT
docker network create --label $LABEL $NET >/dev/null && docker volume create --label $LABEL $VOL >/dev/null || exit 5
python -I "$(W "$HERE/make_migrator_fixture.py")" "$(W "$T/fx")" "$C"
F="$T/fx/backend"; OLDF="$T/fx/outside/old.txt"; NEWF="$T/fx/outside/new.txt"; ADMF="$T/fx/outside/admin.txt"; BK="$T/fx/backup"
OLD="$(cat "$OLDF")"; NEW="$(cat "$NEWF")"; ADM="$(cat "$ADMF")"
start_db() {
  docker rm -f $C >/dev/null 2>&1
  docker run -d --name $C --label $LABEL --network $NET --network-alias db --env-file "$(W "$F/.env.db")" -v $VOL:/var/lib/postgresql/data -m 1g --cpus 1 $IMG >/dev/null
  for i in $(seq 1 40); do docker exec $C pg_isready -U asistente -d asistenteia >/dev/null 2>&1 && return 0; sleep 2; done
  return 1
}
db() { python -I "$(W "$DBTOOL")" "$@"; }
probe() { db probe --network $NET --host $C --role asistente_migrator --database asistenteia --password-file "$(W "$1")" --expect "$2" >/dev/null 2>&1; echo $?; }
probe_admin() { db probe --network $NET --host $C --role asistente --database postgres --password-file "$(W "$ADMF")" --expect accept >/dev/null 2>&1; echo $?; }
start_db; check "disposable PostgreSQL is up" 0 $?
# the synthetic role, with the OLD password, created through standard input (fixture setup, not the tool under test)
printf "CREATE ROLE asistente_migrator LOGIN PASSWORD '%s';\nGRANT CONNECT ON DATABASE asistenteia TO asistente_migrator;\n" "$OLD" | docker exec -i $C sh -c 'psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 -q -f -' >/dev/null 2>&1; check "synthetic migrator role created" 0 $?

echo "== 1. baseline"
check "old password accepted over the network" 0 "$(probe "$OLDF" accept)"
db probe --network $NET --host $C --role asistente_migrator --database asistenteia --from-env-file "$(W "$F/.env.roles")" --var DB_MIGRATOR_PASSWORD --expect accept >/dev/null 2>&1; check "the CURRENT password read from .env.roles is accepted" 0 $?
check "new password not yet accepted" 1 "$(probe "$NEWF" accept)"
check "probe 'reject' on the VALID password fails" 1 "$(probe "$OLDF" reject)"
check "new password rejected before the change" 0 "$(probe "$NEWF" reject)"
check "the administrator is accepted (control)" 0 "$(probe_admin)"

echo "== 2. files: dry run"
python -I "$(W "$FILETOOL")" plan "$(W "$F")" --new-file "$(W "$NEWF")" > "$T/plan.out" 2>&1; check "plan (exit 0)" 0 $?

echo "== 3. SQL: ALTER ROLE through standard input with a client-side SCRAM verifier"
db alter --container $C --role asistente_migrator --password-file "$(W "$NEWF")" > "$T/alter.out" 2>&1; check "alter (exit 0)" 0 $?
check "new password accepted over the network" 0 "$(probe "$NEWF" accept)"
check "old password rejected over the network" 0 "$(probe "$OLDF" reject)"
check "the administrator password is unchanged" 0 "$(probe_admin)"
check "no secret in the output of the tools" 0 "$(cat "$T/alter.out" "$T/plan.out" | grep -c -e "$OLD" -e "$NEW" -e "$ADM")"
check "no secret in any docker argument (shim log)" 0 "$(grep -c -e "$OLD" -e "$NEW" -e "$ADM" "$ARGLOG")"
check "no probe passes the password as a docker environment argument" 0 "$(grep -c -e '-e PGPASSWORD' "$ARGLOG")"
check "standard input holds a SCRAM verifier and not the cleartext" "1 0" "$(grep -c 'SCRAM-SHA-256\$4096:' "$STDINLOG") $(grep -c -e "$OLD" -e "$NEW" "$STDINLOG")"

echo "== 4. partial failure: ALTER ROLE done, the files fail half way"
ROT_TEST_FAIL_AT=replace2 python -I "$(W "$FILETOOL")" apply "$(W "$F")" --new-file "$(W "$NEWF")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" > "$T/apply-fail.out" 2>&1; check "apply fails (exit 1)" 1 $?
check "both files restored: the old value is back in .env.roles and .env.migrate" "1 1" "$(grep -c "DB_MIGRATOR_PASSWORD=$OLD" "$F/.env.roles") $(grep -c "$OLD" "$F/.env.migrate")"
echo "  -- recovery A (revert): put the OLD password back in the database from the backup copy"
db alter --container $C --role asistente_migrator --from-env-file "$(W "$BK/.env.roles.old")" --var DB_MIGRATOR_PASSWORD >/dev/null 2>&1; check "revert (exit 0)" 0 $?
check "old accepted again" 0 "$(probe "$OLDF" accept)"
check "new rejected again" 0 "$(probe "$NEWF" reject)"
rm -rf "$BK"
echo "  -- recovery B (forward): alter again, retry the files"
db alter --container $C --role asistente_migrator --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "alter again (exit 0)" 0 $?
python -I "$(W "$FILETOOL")" apply "$(W "$F")" --new-file "$(W "$NEWF")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" > "$T/apply.out" 2>&1; check "apply (exit 0)" 0 $?
check "no secret in the apply output" 0 "$(cat "$T/apply.out" "$T/apply-fail.out" | grep -c -e "$OLD" -e "$NEW" -e "$ADM")"
python -I "$(W "$FILETOOL")" verify "$(W "$F")" --new-file "$(W "$NEWF")" --old-from "$(W "$BK/.env.roles.old")" > "$T/verify.out" 2>&1; check "verify (exit 0)" 0 $?

echo "== 5. the credentials the tools wrote are the ones that work"
db probe --network $NET --host $C --role asistente_migrator --database asistenteia --from-env-file "$(W "$F/.env.roles")" --var DB_MIGRATOR_PASSWORD --expect accept >/dev/null 2>&1; check "password read from the NEW .env.roles is accepted" 0 $?
URLPW="$(python -I -c "
import sys
from urllib.parse import unquote, urlsplit
line=[l for l in open(sys.argv[1],encoding='utf-8').read().splitlines() if l.startswith('MIGRATION_DATABASE_URL=')][0].split('=',1)[1]
print(unquote(urlsplit(line.replace('+psycopg','')).password))" "$(W "$F/.env.migrate")")"
check "the password inside the NEW MIGRATION_DATABASE_URL equals the new password" "$NEW" "$URLPW"
check "no server restart was needed: the same container answers with the new password" 0 "$(probe "$NEWF" accept)"

echo "== 6. discard the backup copies (they hold the dead old value)"
python -I "$(W "$FILETOOL")" discard "$(W "$F")" --new-file "$(W "$NEWF")" --old-from "$(W "$BK/.env.roles.old")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" > "$T/discard.out" 2>&1; check "discard (exit 0)" 0 $?
check "backup folder gone, *.pre-17b untouched" "0 1" "$([ -d "$BK" ] && echo 1 || echo 0) $(ls -A "$F" | grep -c '^.env.pre-17b$')"
check "the old value is in no file under the fixture (except the owner's old.txt)" 0 "$(grep -rl -e "$OLD" "$T/fx" 2>/dev/null | grep -vc 'outside/old.txt' | tr -d ' ')"
check "no secret in the verify and discard output" 0 "$(cat "$T/discard.out" "$T/verify.out" | grep -c -e "$OLD" -e "$NEW")"

echo "== 7. refusals"
db alter --container g17bmig-nonexistent --role asistente_migrator --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "unknown container -> exit 3" 3 $?
printf 'short\n' > "$T/bad.txt"; db alter --container $C --role asistente_migrator --password-file "$(W "$T/bad.txt")" >/dev/null 2>&1; check "malformed password file -> refused (exit 1)" 1 $?
db alter --container $C --role 'x"; DROP ROLE y; --' --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "role name that is not an identifier -> refused (exit 1)" 1 $?
check "the new password is still the valid one at the end" 0 "$(probe "$NEWF" accept)"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]
