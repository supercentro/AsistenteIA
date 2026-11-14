#!/usr/bin/env bash
# Mutation testing of the stages that need containers (TD-030, 17B.1): each mutation of run_17b.sh must make the matching scenario of
# test_run_17b.sh fail. Disposable stack only; the 8 GB RAM gate of test_run_17b.sh applies to every run.
HERE="$(cd "$(dirname "$0")" && pwd)"
MUT="$HERE/run_17b.mut.sh"; trap 'rm -f "$MUT"' EXIT
BAD=0
mut() { # name, scenario, old, new
  python - "$(cygpath -w "$HERE/run_17b.sh")" "$(cygpath -w "$MUT")" "$3" "$4" <<'PY' || { echo "FAIL mutation '$1': pattern not found"; BAD=$((BAD+1)); return; }
import sys
src, dst, old, new = sys.argv[1:5]
text = open(src, encoding="utf-8").read()
if old not in text:
    sys.exit(3)
open(dst, "w", encoding="utf-8", newline="\n").write(text.replace(old, new, 1))
PY
  G17B_ORCH="$MUT" bash "$HERE/test_run_17b.sh" "$2" > "$HERE/.mut-$2.out" 2>&1; rc=$?
  n=$(grep -c '^  FAIL' "$HERE/.mut-$2.out"); rm -f "$HERE/.mut-$2.out"
  if [ "$rc" != 0 ] && [ "$n" -gt 0 ]; then echo "PASS mutation '$1' is detected by $2 ($n check(s) fail)"; else echo "FAIL mutation '$1' SURVIVED in $2"; BAD=$((BAD+1)); fi
}
# (equivalent mutant, not listed: accepting any bootstrap exit code is still caught by the second check, the listing of the ownership drift;
#  the mutation below removes that second check and is detected)
mut "bootstrap does not require the drift listing" T6 'grep -q "ownership drift" "$OUTD/$CURRENT-first.txt" || die 22' 'true || die 22'
mut "backup/real-state equivalence ignored" T4 'die 11 "the real database no longer equals' 'true "the real database no longer equals'
mut "cluster identity pin ignored" T5 '"cluster identity changed since the first stage (system id differs): NO-GO"' '"x" || true #'
mut "adoption dry run count not checked" T7 'grep -q "dry run (nothing changed; use --apply): 9 object" "$OUTD/$CURRENT-dry.txt" || die 23 "the dry run does not list exactly 9 objects"' 'true'
mut "prepared transaction gate removed" T2 'die 3 "gate E: $f is not 0"' 'true'
mut "S13 ignores a settings load failure" T14 'die 13 "the $svc settings do not load in the new image (variable names above, no value printed)"; }' 'true; }'
echo "docker mutation problems: $BAD"
[ "$BAD" = 0 ]
