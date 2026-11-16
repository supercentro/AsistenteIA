#!/usr/bin/env bash
# End-to-end rehearsal of the TD-038 rotation on a DISPOSABLE PostgreSQL with SYNTHETIC credentials (TD-030, 17B.6 preparation).
# Never touches the real stack: own network, own volume, container labelled purpose=g17b-rot-test, no published port.
# Proves: the SQL step keeps the password out of argv/stdout/logs (a `docker` shim records every argument and the standard input),
# the new password is accepted and the old rejected, the container env is irrelevant until recreated, partial-failure recovery
# (revert and forward), and the clean-up. Refuses to start with less than 8 GB of free RAM.
export MSYS_NO_PATHCONV=1
HERE="$(cd "$(dirname "$0")" && pwd)"
W() { cygpath -w "$1"; }
DBTOOL="${ROT_DB_TOOL:-$HERE/rotate_db_role.py}"
FILETOOL="$HERE/rotate_admin_password.py"
ACL="$HERE/../../group-17c/tools/secure_file_acl.ps1"
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then PASS=$((PASS+1)); echo "  PASS $1"; else FAIL=$((FAIL+1)); echo "  FAIL $1 (expected '$2', got '$3')"; fi; }
RAM=$(powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r' | tr ',' '.')
python -c "import sys; sys.exit(0 if float('$RAM') >= 8 else 1)" || { echo "free RAM $RAM GB < 8: stop, no Docker used"; exit 4; }
echo "free RAM before Docker: $RAM GB"
IMG=pgvector/pgvector:0.8.7-pg15; NET=g17brot-net; VOL=g17brot-vol; C=g17brot-db; LABEL=purpose=g17b-rot-test
T="$(mktemp -d)"; SHIMBIN="$T/shimbin"; mkdir -p "$SHIMBIN"; ARGLOG="$T/docker-argv.log"; STDINLOG="$T/docker-stdin.log"
REALDOCKER="$(command -v docker.exe || command -v docker)"
export ROT_TEST_HOOKS=1 ROT_SHIM_ARGLOG="$(W "$ARGLOG")" ROT_SHIM_STDINLOG="$(W "$STDINLOG")" ROT_SHIM_REAL="$(W "$REALDOCKER")"
export ROT_DOCKER_CMD="[\"$(cygpath -m "$(command -v python)")\", \"$(cygpath -m "$HERE/docker_shim.py")\"]"
cleanup() { docker rm -f $C >/dev/null 2>&1; docker volume rm -f $VOL >/dev/null 2>&1; docker network rm $NET >/dev/null 2>&1; rm -rf "$T"; }
trap cleanup EXIT
docker network create --label $LABEL $NET >/dev/null && docker volume create --label $LABEL $VOL >/dev/null || exit 5
python -I "$(W "$HERE/make_rotation_fixture.py")" "$(W "$T/fx")" "$C"
F="$T/fx/backend"; OLDF="$T/fx/outside/old.txt"; NEWF="$T/fx/outside/new.txt"; BK="$T/fx/backup"
OLD="$(cat "$OLDF")"; NEW="$(cat "$NEWF")"
start_db() {  # optional argument: the env file the container is created with (default: the fixture .env.db)
  docker rm -f $C >/dev/null 2>&1
  docker run -d --name $C --label $LABEL --network $NET --network-alias db --env-file "$(W "${1:-$F/.env.db}")" -v $VOL:/var/lib/postgresql/data -m 1g --cpus 1 $IMG >/dev/null
  for i in $(seq 1 40); do docker exec $C pg_isready -U asistente -d asistenteia >/dev/null 2>&1 && return 0; sleep 2; done
  return 1
}
db() { python -I "$(W "$DBTOOL")" "$@"; }
probe() { db probe --network $NET --host $C --role asistente --password-file "$(W "$1")" --expect "$2" >/dev/null 2>&1; echo $?; }
start_db; check "disposable PostgreSQL is up" 0 $?
# SEC-17B-01 / 17B.6 preparation: synthetic restricted roles, an object owned by the migrator and a grant, to prove the administrator rotation touches none of them
MIG="Mig$(python -c 'import secrets;print(secrets.token_urlsafe(30))')"; APPPW="App$(python -c 'import secrets;print(secrets.token_urlsafe(30))')"; printf '%s\n' "$MIG" > "$T/mig.txt"
printf "CREATE ROLE asistente_migrator LOGIN PASSWORD '%s';\nCREATE ROLE asistente_app LOGIN PASSWORD '%s';\nGRANT CONNECT ON DATABASE asistenteia TO asistente_migrator, asistente_app;\nCREATE TABLE public.g17b_marker(id int primary key, note text);\nALTER TABLE public.g17b_marker OWNER TO asistente_migrator;\nGRANT SELECT ON public.g17b_marker TO asistente_app;\nINSERT INTO public.g17b_marker VALUES (1, 'before');\n" "$MIG" "$APPPW" | docker exec -i $C sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -v ON_ERROR_STOP=1 -q -f -' >/dev/null 2>&1; check "synthetic roles, owned object and grant created" 0 $?
SNAPSQL="select relname, pg_get_userbyid(relowner), relacl::text from pg_class where relname='g17b_marker'; select rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolconnlimit, md5(coalesce(rolpassword,'')) from pg_roles where rolname like 'asistente%' and rolname <> 'asistente' order by 1; select count(*) from public.g17b_marker;"
snap() { printf '%s\n' "$SNAPSQL" | docker exec -i $C sh -c 'psql -U "$POSTGRES_USER" -d asistenteia -At -f -' | sha256sum | cut -c1-16; }
SNAP0="$(snap)"
check "local connections inside the container are trusted by pg_hba (what makes alter work without any password)" 1 "$(docker exec $C sh -c 'grep -cE "^local +all +all +trust" "$PGDATA/pg_hba.conf"')"
check "network connections are NOT trusted (they need a password)" 0 "$(docker exec $C sh -c 'grep -E "^host +all +all +(all|0.0.0.0/0|::/0) +trust" "$PGDATA/pg_hba.conf"' | wc -l | tr -d ' ')"
db alter --container $C --role asistente_migrator --require-superuser --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "alter --require-superuser REFUSES a restricted role (exit 3) and changes nothing" "3 $SNAP0" "$? $(snap)"

echo "== 1. baseline: the old password is the real one"
check "old password accepted over the network" 0 "$(probe "$OLDF" accept)"
db probe --network $NET --host $C --role asistente --from-env-file "$(W "$F/.env.db")" --var POSTGRES_PASSWORD --expect accept >/dev/null 2>&1; check "the CURRENT password read from .env.db is accepted (no extra password file)" 0 $?
check "new password not yet accepted (probe 'accept' fails)" 1 "$(probe "$NEWF" accept)"
check "probe 'reject' on the VALID password fails (a probe that always says yes would be caught here)" 1 "$(probe "$OLDF" reject)"
check "new password rejected before the change" 0 "$(probe "$NEWF" reject)"
db check --container $C | grep -q "password_encryption=scram-sha-256"; check "the server stores SCRAM verifiers" 0 $?
echo "-- POSTGRES_PASSWORD alone does NOT change the password of an existing role (the image reads it only to initialise an empty data directory)"
sed "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW/" "$F/.env.db" > "$T/env.db.newonly"
start_db "$T/env.db.newonly"; check "container recreated with the NEW value only in its environment" 0 $?
check "the OLD password still works after that recreation" 0 "$(probe "$OLDF" accept)"
check "the NEW password is NOT accepted although it is in POSTGRES_PASSWORD" 0 "$(probe "$NEWF" reject)"
start_db; check "container recreated again with the original .env.db" 0 $?
rm -f "$T/env.db.newonly"

echo "-- the stored FORMS of the password work: the URL variables are parsed like an application would (--as-url)"
db probe --network $NET --host $C --role asistente --database postgres --from-env-file "$(W "$F/.env.roles")" --var ADMIN_DATABASE_URL --as-url --expect accept >/dev/null 2>&1; check "the CURRENT password inside ADMIN_DATABASE_URL (.env.roles) is accepted" 0 $?
db probe --network $NET --host $C --role asistente --database postgres --from-env-file "$(W "$F/.env.test")" --var TEST_DATABASE_URL --as-url --expect accept >/dev/null 2>&1; check "the CURRENT password inside TEST_DATABASE_URL (.env.test) is accepted" 0 $?
db probe --network $NET --host $C --role someone_else --database postgres --from-env-file "$(W "$F/.env.roles")" --var ADMIN_DATABASE_URL --as-url --expect accept >/dev/null 2>&1; check "--as-url refuses a URL whose user is not the probed role (exit 1)" 1 $?
echo "== 2. files: dry run"
python -I "$(W "$FILETOOL")" plan "$(W "$F")" --new-file "$(W "$NEWF")" > "$T/plan.out" 2>&1; check "plan (exit 0)" 0 $?

echo "== 3. SQL: ALTER ROLE through standard input with a client-side SCRAM verifier"
db alter --container $C --role asistente --require-superuser --password-file "$(W "$NEWF")" > "$T/alter.out" 2>&1; check "alter (exit 0)" 0 $?
check "new password accepted over the network" 0 "$(probe "$NEWF" accept)"
check "old password rejected over the network" 0 "$(probe "$OLDF" reject)"
check "the container environment still carries the OLD value (irrelevant: the password is stored in the data directory)" 1 "$(docker exec $C sh -c 'echo $POSTGRES_PASSWORD' | grep -c "^$OLD$")"
check "no secret in the output of the tool" 0 "$(cat "$T/alter.out" "$T/plan.out" | grep -c -e "$OLD" -e "$NEW")"
check "no secret in any docker argument (shim log)" 0 "$(grep -c -e "$OLD" -e "$NEW" "$ARGLOG")"
check "no probe passes the password as a docker environment argument (-e PGPASSWORD)" 0 "$(grep -c -e '-e PGPASSWORD' "$ARGLOG")"
check "the statement travelled on standard input" 1 "$([ -s "$STDINLOG" ] && echo 1 || echo 0)"
check "standard input holds SCRAM verifiers (the refused migrator alter and the administrator alter) and never the cleartext" "2 0" "$(grep -c 'SCRAM-SHA-256\$4096:' "$STDINLOG") $(grep -c -e "$OLD" -e "$NEW" "$STDINLOG")"

db probe --network $NET --host $C --role asistente_migrator --database asistenteia --password-file "$(W "$T/mig.txt")" --expect accept >/dev/null 2>&1; check "the migrator password (synthetic) still works after the administrator ALTER ROLE" 0 $?
check "roles, grants, ownership, data and every role verifier other than the administrator's are unchanged by the administrator ALTER ROLE" "$SNAP0" "$(snap)"
check "no synthetic restricted-role password in any docker argument" 0 "$(grep -c -e "$MIG" -e "$APPPW" "$ARGLOG")"
echo "-- container scan (the running container still carries the OLD value until it is recreated)"
mkdir -p "$T/scanold" && cp "$F/.env.db" "$T/scanold/.env.db.cur"; cp "$OLDF" "$T/scanold/old.txt"; printf 'POSTGRES_PASSWORD=%s\n' "$OLD" > "$T/scanold/.env.db.old"
env -u ROT_TEST_HOOKS -u ROT_DOCKER_CMD python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/scanold")" --file .env.db.old --var POSTGRES_PASSWORD > "$T/scan1.out" 2>&1; check "the scan finds the database container still holding the OLD value (exit 1)" 1 $?
check "the scan names the container and prints no value" "1 0" "$(grep -c "$C" "$T/scan1.out") $(grep -c -e "$OLD" "$T/scan1.out")"
echo "== 4. partial failure: ALTER ROLE done, the files fail half way"
ROT_TEST_FAIL_AT=replace2 python -I "$(W "$FILETOOL")" apply "$(W "$F")" --new-file "$(W "$NEWF")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" > "$T/apply-fail.out" 2>&1; check "apply fails (exit 1)" 1 $?
check "all files restored (the old value is still in .env.db: the files and the database now disagree)" 1 "$(grep -c "POSTGRES_PASSWORD=$OLD" "$F/.env.db")"
echo "  -- recovery A (revert): put the OLD password back in the database"
db alter --container $C --role asistente --require-superuser --from-env-file "$(W "$BK/.env.db.old")" --var POSTGRES_PASSWORD >/dev/null 2>&1; check "revert from the backup copy of .env.db (exit 0)" 0 $?
check "old accepted again" 0 "$(probe "$OLDF" accept)"
check "new rejected again" 0 "$(probe "$NEWF" reject)"
rm -rf "$BK"
echo "  -- recovery B (forward): alter again, retry the files"
db alter --container $C --role asistente --require-superuser --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "alter again (exit 0)" 0 $?
python -I "$(W "$FILETOOL")" apply "$(W "$F")" --new-file "$(W "$NEWF")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" > "$T/apply.out" 2>&1; check "apply (exit 0)" 0 $?
check "no secret in the apply output" 0 "$(grep -c -e "$OLD" -e "$NEW" "$T/apply.out" "$T/apply-fail.out" | awk -F: '{s+=$NF} END {print s+0}')"
python -I "$(W "$FILETOOL")" verify "$(W "$F")" --new-file "$(W "$NEWF")" --old-from "$(W "$BK/.env.db.old")" > "$T/verify.out" 2>&1; check "verify (exit 0)" 0 $?

db probe --network $NET --host $C --role asistente --database postgres --from-env-file "$(W "$F/.env.roles")" --var ADMIN_DATABASE_URL --as-url --expect accept >/dev/null 2>&1; check "the NEW password inside ADMIN_DATABASE_URL (.env.roles, written by the tool) is accepted" 0 $?
db probe --network $NET --host $C --role asistente --database postgres --from-env-file "$(W "$F/.env.test")" --var TEST_DATABASE_URL --as-url --expect accept >/dev/null 2>&1; check "the NEW password inside TEST_DATABASE_URL (.env.test, written by the tool) is accepted" 0 $?
db probe --network $NET --host $C --role asistente --database postgres --from-env-file "$(W "$F/.env.db")" --var POSTGRES_PASSWORD --expect accept >/dev/null 2>&1; check "the NEW POSTGRES_PASSWORD (.env.db) is accepted" 0 $?
echo "== 5. recreate the database container with the updated .env.db (what compose does), same volume"
start_db; check "container recreated and ready" 0 $?
check "new password accepted after the recreation" 0 "$(probe "$NEWF" accept)"
check "old password rejected after the recreation" 0 "$(probe "$OLDF" reject)"
check "the container environment now carries the NEW value" 1 "$(docker exec $C sh -c 'echo $POSTGRES_PASSWORD' | grep -c "^$NEW$")"

check "the data volume survived the recreation (marker row still there, ownership and grants identical)" "$SNAP0" "$(snap)"
check "the migrator password still works after the container was recreated with the new .env.db" 0 "$(db probe --network $NET --host $C --role asistente_migrator --database asistenteia --password-file "$(W "$T/mig.txt")" --expect accept >/dev/null 2>&1; echo $?)"
env -u ROT_TEST_HOOKS -u ROT_DOCKER_CMD python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$T/scanold")" --file .env.db.old --var POSTGRES_PASSWORD > "$T/scan2.out" 2>&1; check "after the recreation no container holds the OLD value (exit 0)" 0 $?
env -u ROT_TEST_HOOKS -u ROT_DOCKER_CMD python -I "$(W "$HERE/check_containers_for_value.py")" "$(W "$F")" --file .env.db --var POSTGRES_PASSWORD > "$T/scan3.out" 2>&1; check "the database container now carries the NEW value (the scan of the new value names it, exit 1)" 1 $?
python -I "$(W "$FILETOOL")" discard "$(W "$F")" --new-file "$(W "$NEWF")" --old-from "$(W "$BK/.env.db.old")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" --dry-run > "$T/discard-dry.out" 2>&1; check "discard --dry-run (exit 0)" 0 $?
check "discard --dry-run names exactly the three .old copies and removed nothing" "3 3" "$(grep -c 'WOULD REMOVE \.env\.\(db\|roles\|test\)\.old$' "$T/discard-dry.out") $(ls -A "$BK" | grep -c '\.old$')"
echo "== 6. clean-up of the old copies"
python -I "$(W "$FILETOOL")" cleanup "$(W "$F")" --new-file "$(W "$NEWF")" --old-from "$(W "$BK/.env.db.old")" --backup-dir "$(W "$BK")" --acl-script "$(W "$ACL")" --i-know-this-removes-the-only-file-rollback > "$T/cleanup.out" 2>&1; check "cleanup (exit 0)" 0 $?
check "no pre-17b copy and no backup folder left" "0 0" "$(ls -A "$F" | grep -c 'pre-17b') $([ -d "$BK" ] && echo 1 || echo 0)"
check "the old value is in no file under the fixture any more (except the owner's old.txt)" 0 "$(grep -rl -e "$OLD" "$T/fx" 2>/dev/null | grep -vc 'outside/old.txt' | tr -d ' ')"
check "no secret in the clean-up and verify output" 0 "$(cat "$T/cleanup.out" "$T/verify.out" | grep -c -e "$OLD" -e "$NEW")"

echo "== 7. refusals"
db alter --container g17brot-nonexistent --role asistente --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "unknown container -> exit 3" 3 $?
printf 'short\n' > "$T/bad.txt"; db alter --container $C --role asistente --require-superuser --password-file "$(W "$T/bad.txt")" >/dev/null 2>&1; check "malformed password file -> refused (exit 1)" 1 $?
db alter --container $C --role 'x"; DROP ROLE y; --' --password-file "$(W "$NEWF")" >/dev/null 2>&1; check "role name that is not an identifier -> refused (exit 1)" 1 $?
check "after all this the new password is still the valid one" 0 "$(probe "$NEWF" accept)"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]
