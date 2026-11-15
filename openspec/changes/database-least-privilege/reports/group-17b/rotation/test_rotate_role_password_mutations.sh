#!/usr/bin/env bash
# Mutation check of rotate_role_password.py: each mutation must make test_rotate_role_password.py FAIL (SEC-17B-01). Copies only; the tool is never edited.
HERE="$(cd "$(dirname "$0")" && pwd)"; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
WT="$(cygpath -m "$T" 2>/dev/null || echo "$T")"; WH="$(cygpath -m "$HERE" 2>/dev/null || echo "$HERE")"
cp "$HERE/rotate_admin_password.py" "$T/"; cp "$HERE/rotate_role_password.py" "$T/"
python -I "$WH/test_rotate_role_password.py" "$WT/rotate_role_password.py" >/dev/null 2>&1 || { echo "BASELINE FAILS: the unmutated copy must pass"; exit 2; }
echo "  baseline: the unmutated copy passes"
n=0; caught=0
mutate() { # description, python-literal old, python-literal new
  n=$((n+1)); cp "$HERE/rotate_admin_password.py" "$T/"; cp "$HERE/rotate_role_password.py" "$T/rotate_role_password.py"
  python -I - "$WT/rotate_role_password.py" "$2" "$3" <<'PY'
import sys
p, a, b = sys.argv[1:]
s = open(p, encoding="utf-8").read()
assert s.count(a) == 1, "mutation anchor not unique: " + a[:40]
open(p, "w", encoding="utf-8").write(s.replace(a, b))
PY
  if python -I "$WH/test_rotate_role_password.py" "$WT/rotate_role_password.py" >/dev/null 2>&1; then echo "  SURVIVED $1"; else caught=$((caught+1)); echo "  caught   $1"; fi
}
mutate "another env file may hold the old value" 'raise Refused(f"{other}: another env file holds the old value; it would not be rotated")' 'pass'
mutate "a failed apply does not restore" 'bad = restore(folder, backup_dir, list(result) if replacing else replaced, acl_script)' 'bad = 0'
mutate "verify ignores the URL password" 'if unquote(urlsplit(value).password or "") != new:' 'if False:'
mutate "orphans are never detected" 'r"\.\.env\.(roles|migrate)\.(rot|restore)-\d+"' 'r"NEVERMATCH"'
mutate "the password variable is not rewritten" 'out.append(f"{var}={new}{comment}{eol}")
            changed.append(var)
            continue
        if "://"' 'out.append(raw)
            changed.append(var)
            continue
        if "://"'
mutate "the URL may name the role with another password" 'raise Refused(f"{name}: {var} names the role with a different password")' 'pass'
mutate "plan accepts a new file inside the env folder" 'raise Refused("the new-password file is inside the env folder: keep it elsewhere")' 'pass'
mutate "discard skips verify" 'problems = verify_state(folder, new_file, old_source)
    if problems:
        for problem in problems:
            say(f"DISCARD REFUSED' 'problems = []
    if problems:
        for problem in problems:
            say(f"DISCARD REFUSED'
mutate "the backup folder may be non-empty" 'raise Refused("the backup folder is not empty; not overwriting")' 'pass'
mutate "an unexpected parser error is not caught (traceback may echo a URL)" '    except Exception as exc:  # a parser error' '    except ZeroDivisionError as exc:  # a parser error'
mutate "apply restores only the files already replaced" 'list(result) if replacing else replaced' 'replaced'
mutate "Windows apply without --acl-script is allowed" 'if os.name == "nt" and acl_script is None and os.environ.get("ROT_TEST_NO_ACL") != "1":' 'if False:'
mutate "rollback trusts any .old, as before the fix" 'present = base.check_backup(backup_dir, TARGETS)' 'present = [n for n in TARGETS if (backup_dir / (n + ".old")).is_file()]'
mutate "discard removes the old-value source copy first" 'for n in (URL_FILE, PASSWORD_FILE) if' 'for n in (PASSWORD_FILE, URL_FILE) if'
echo "MUTATIONS caught=$caught of $n"; [ "$caught" = "$n" ]
