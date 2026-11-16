#!/usr/bin/env bash
# Mutation testing of rotate_db_role.py through the disposable-PostgreSQL rehearsal: each mutant must make the rehearsal fail.
HERE="$(cd "$(dirname "$0")" && pwd)"
MUT="$HERE/rotate_db_role.mut.py"; trap 'rm -f "$MUT"' EXIT
BAD=0
mut() { # name, old, new
  python - "$(cygpath -w "$HERE/rotate_db_role.py")" "$(cygpath -w "$MUT")" "$2" "$3" <<'PY' || { echo "FAIL mutation '$1': pattern not found"; BAD=$((BAD+1)); return; }
import sys
src, dst, old, new = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
if old not in text:
    sys.exit(3)
open(dst, "w", encoding="utf-8", newline="\n").write(text.replace(old, new, 1))
PY
  ROT_DB_TOOL="$MUT" bash "$HERE/test_rotation_e2e.sh" > "$HERE/.mut.out" 2>&1; rc=$?
  n=$(grep -c '^  FAIL' "$HERE/.mut.out"); rm -f "$HERE/.mut.out"
  if [ "$rc" != 0 ] && [ "$n" -gt 0 ]; then echo "PASS mutation '$1' is detected ($n check(s) fail)"; else echo "FAIL mutation '$1' SURVIVED"; BAD=$((BAD+1)); fi
}
mut "the cleartext password is sent instead of the verifier" "verifier = scram_verifier(password)" "verifier = password"
mut "the password goes in an argument of docker exec" "proc = docker([\"exec\", \"-i\", container, \"sh\", \"-c\", 'psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -q -f -'], stdin=sql)" "proc = docker([\"exec\", \"-i\", \"-e\", \"X=\" + verifier, container, \"sh\", \"-c\", 'psql -U \"\$POSTGRES_USER\" -d postgres -v ON_ERROR_STOP=1 -q -f -'], stdin=sql + verifier.encode())"
mut "probe always succeeds" "return 0 if rejected else 1" "return 0"
mut "role name not validated" "if not ROLE.fullmatch(role):" "if False:"
echo "mutation problems: $BAD"
[ "$BAD" = 0 ]
