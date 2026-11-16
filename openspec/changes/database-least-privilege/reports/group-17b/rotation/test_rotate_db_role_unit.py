"""Unit tests of the password handling of rotate_db_role.py that need no Docker (SYNTHETIC values only). Run: python -I test_rotate_db_role_unit.py"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
TOOL = HERE / "rotate_db_role.py"
spec = importlib.util.spec_from_file_location("rdr", TOOL)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load rotate_db_role.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
failed = 0


def check(label: str, ok: bool) -> None:
    global failed
    print(("PASS " if ok else "FAIL ") + label)
    failed += 0 if ok else 1


def run(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k not in ("ROT_TEST_HOOKS", "ROT_DOCKER_CMD")}, check=False)  # noqa: S603
    return proc.returncode, proc.stdout + proc.stderr


SECRET = "Syn/Pw+0123456789abcdefABCDEF=="  # SYNTHETIC; needs percent-encoding on purpose  # noqa: S105
check("password_of_url percent-decodes the password", mod.password_of_url(f"postgresql://asistente:{quote(SECRET, safe='')}@db:5432/postgres", "asistente") == SECRET)
check("password_of_url accepts the +psycopg dialect", mod.password_of_url(f"postgresql+psycopg://asistente:{quote(SECRET, safe='')}@db:5432/x", "asistente") == SECRET)
for label, url, role in (
    ("a URL of another user", f"postgresql://other:{quote(SECRET, safe='')}@db/x", "asistente"),
    ("a URL without a password", "postgresql://asistente@db/x", "asistente"),
    ("a value that is not a URL", SECRET, "asistente"),
):
    try:
        mod.password_of_url(url, role)
        check(f"password_of_url refuses {label}", False)
    except SystemExit as exc:
        check(f"password_of_url refuses {label}", exc.code == 1)

with tempfile.TemporaryDirectory() as tmp:
    env = Path(tmp) / "env"
    base = ["probe", "--network", "n", "--host", "h", "--role", "asistente", "--database", "postgres", "--from-env-file", str(env), "--var", "X_URL", "--as-url", "--expect", "accept"]
    env.write_text(f"X_URL=postgresql://other:{quote(SECRET, safe='')}@db/x\n", encoding="utf-8")
    code, out = run(*base)
    check("the probe refuses a URL of another user before any Docker call (exit 1), nothing printed", code == 1 and "REFUSED" in out and SECRET not in out and "Traceback" not in out)
    env.write_text("X_URL=postgresql://asistente:PW" + chr(0xFF03) + "SECRETPART@db/x\n", encoding="utf-8")
    code, out = run(*base)
    check("a non-ASCII URL: exit 4, the type only, no traceback and no echo", code == 4 and "FAILED unexpected" in out and "SECRETPART" not in out and "Traceback" not in out)
    env.write_text("OTHER=1\n", encoding="utf-8")
    code, out = run(*base)
    check("a missing variable is refused (exit 1) without printing", code == 1 and "Traceback" not in out)
    code, out = run("probe", "--network", "n", "--host", "h", "--role", "asistente", "--from-env-file", str(Path(tmp) / "absent"), "--var", "X", "--expect", "accept")
    check("a missing env file is refused (exit 2)", code == 2)
    pw = Path(tmp) / "pw.txt"
    pw.write_text("short\n", encoding="utf-8")
    code, out = run("alter", "--container", "c", "--role", "asistente", "--password-file", str(pw))
    check("a malformed password file is refused (exit 1)", code == 1)
    good = Path(tmp) / "good.txt"
    good.write_text("A" * 40 + chr(10), encoding="utf-8")
    code, out = run("alter", "--container", "c", "--role", 'x"; DROP ROLE y; --', "--password-file", str(good))
    check("a role that is not an identifier never reaches Docker (exit 1)", code == 1)

print(f"{failed} failure(s)")
sys.exit(1 if failed else 0)
