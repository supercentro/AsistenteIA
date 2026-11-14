"""File-level tests of rotate_role_password.py on SYNTHETIC folders (no Docker, no real value). Run: python -I test_rotate_role_password.py [tool path]."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "rotate_role_password.py"
FIXTURE = HERE / "make_migrator_fixture.py"
passed = failed = 0


def check(name: str, ok: bool) -> None:
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL {name}")


def run(*args: str, fail_at: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ROT_TEST_NO_ACL": "1", **({"ROT_TEST_FAIL_AT": fail_at} if fail_at else {})}
    cmd = [sys.executable, "-I", str(TOOL), *args]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)  # noqa: S603 - test harness, fixed argv


def fixture(tmp: Path) -> tuple[Path, Path, Path, str, str]:
    subprocess.run([sys.executable, "-I", str(FIXTURE), str(tmp / "fx"), "db"], check=True)  # noqa: S603 - test harness
    f = tmp / "fx" / "backend"
    out = tmp / "fx" / "outside"
    return f, out / "new.txt", tmp / "fx" / "backup", (out / "old.txt").read_text().strip(), (out / "new.txt").read_text().strip()


def snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def no_secret(text: str, *secrets: str) -> bool:
    return not any(s in text for s in secrets)


with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    f, nf, bk, old, new = fixture(tmp)
    before = snapshot(f)
    # plan
    r = run("plan", str(f), "--new-file", str(nf))
    check("plan exits 0", r.returncode == 0 and "PLAN OK: nothing written" in r.stdout)
    check("plan lists both variables", "DB_MIGRATOR_PASSWORD" in r.stdout and "MIGRATION_DATABASE_URL" in r.stdout)
    check("plan writes nothing", snapshot(f) == before)
    check("plan prints no secret", no_secret(r.stdout + r.stderr, old, new))
    # failure injection: every point restores byte for byte and leaves no temp file
    for point, code in (("temp", 1), ("replace1", 1), ("replace2", 1), ("verify", 1), ("interrupt1", 130), ("interrupt2", 130)):
        sub = tmp / point
        sub.mkdir()
        f2, nf2, bk2, o2, n2 = fixture(sub)
        b2 = snapshot(f2)
        r = run("apply", str(f2), "--new-file", str(nf2), "--backup-dir", str(bk2), fail_at=point)
        check(f"apply fails at {point} with exit {code}", r.returncode == code)
        check(f"apply at {point}: every file restored byte for byte, no temp file left", snapshot(f2) == b2)
        check(f"apply at {point}: no secret in the output", no_secret(r.stdout + r.stderr, o2, n2))
    # a real apply
    r = run("apply", str(f), "--new-file", str(nf), "--backup-dir", str(bk))
    check("apply exits 0", r.returncode == 0 and "APPLY OK" in r.stdout)
    check("apply prints no secret", no_secret(r.stdout + r.stderr, old, new))
    after = snapshot(f)
    check("only .env.roles and .env.migrate changed", {k for k in after if after[k] != before.get(k)} == {".env.roles", ".env.migrate"})
    check("the new value is in both, the old in none of the live env files", all(new.encode() in after[n] for n in (".env.roles", ".env.migrate")) and not any(old.encode() in v for v in after.values()))
    check("comment and every other line kept", b"# synthetic" in after[".env.roles"] and after[".env"] == before[".env"] and after[".env.db"] == before[".env.db"])
    check("backup copies hold the originals", (bk / ".env.roles.old").read_bytes() == before[".env.roles"] and (bk / ".env.migrate.old").read_bytes() == before[".env.migrate"])
    check("apply refuses a non-empty backup folder", run("apply", str(f), "--new-file", str(nf), "--backup-dir", str(bk)).returncode == 1)
    # verify
    r = run("verify", str(f), "--new-file", str(nf), "--old-from", str(bk / ".env.roles.old"))
    check("verify OK after apply", r.returncode == 0 and "VERIFY OK" in r.stdout and no_secret(r.stdout, old, new))
    # verify detects a half-rotated state
    (f / ".env.migrate").write_bytes(before[".env.migrate"])
    r = run("verify", str(f), "--new-file", str(nf), "--old-from", str(bk / ".env.roles.old"))
    check("verify fails when .env.migrate still holds the old value", r.returncode == 1 and ".env.migrate" in r.stdout and no_secret(r.stdout, old, new))
    # rollback restores both
    r = run("rollback", str(f), "--backup-dir", str(bk))
    check("rollback restores the originals", r.returncode == 0 and snapshot(f) == before)
    # orphan files block everything until rollback
    (f / "..env.migrate.rot-4242").write_bytes(b"x")
    check("plan refuses while an orphan temp file exists", run("plan", str(f), "--new-file", str(nf)).returncode == 1)
    run("rollback", str(f), "--backup-dir", str(bk))
    check("rollback removes orphan temp files", not (f / "..env.migrate.rot-4242").exists())
    # refusals
    sub = tmp / "r1"
    sub.mkdir()
    f3, nf3, bk3, o3, n3 = fixture(sub)
    (f3 / ".env.worker").write_text(f"DATABASE_URL=postgresql+psycopg://asistente_worker:{o3}@db:5432/asistenteia\n")
    r = run("plan", str(f3), "--new-file", str(nf3))
    check("plan refuses when ANOTHER env file holds the old value", r.returncode == 1 and ".env.worker" in r.stdout and no_secret(r.stdout, o3, n3))
    sub = tmp / "r2"
    sub.mkdir()
    f4, nf4, bk4, o4, n4 = fixture(sub)
    text = (f4 / ".env.migrate").read_text().replace(o4, "Different" + o4)
    (f4 / ".env.migrate").write_text(text)
    check("plan refuses when the URL and DB_MIGRATOR_PASSWORD disagree", run("plan", str(f4), "--new-file", str(nf4)).returncode == 1)
    sub = tmp / "r3"
    sub.mkdir()
    f5, nf5, bk5, o5, n5 = fixture(sub)
    inside = f5 / "new_inside.txt"
    inside.write_text(n5 + "\n")
    check("plan refuses a new-password file inside the env folder", run("plan", str(f5), "--new-file", str(inside)).returncode == 1)
    bad = sub / "short.txt"
    bad.write_text("short\n")
    check("plan refuses a malformed new password", run("plan", str(f5), "--new-file", str(bad)).returncode == 1)
    same = sub / "same.txt"
    same.write_text(o5 + "\n")
    check("plan refuses a new password equal to the old one", run("plan", str(f5), "--new-file", str(same)).returncode == 1)
    # quoted URL is refused
    sub = tmp / "r4"
    sub.mkdir()
    f6, nf6, bk6, o6, n6 = fixture(sub)
    t6 = (f6 / ".env.migrate").read_text().strip()
    var, val = t6.split("=", 1)
    (f6 / ".env.migrate").write_text(f"{var}='{val}'\n")
    check("plan refuses a quoted URL", run("plan", str(f6), "--new-file", str(nf6)).returncode == 1)
    # discard
    sub = tmp / "d"
    sub.mkdir()
    f7, nf7, bk7, o7, n7 = fixture(sub)
    run("apply", str(f7), "--new-file", str(nf7), "--backup-dir", str(bk7))
    dry = run("discard", str(f7), "--new-file", str(nf7), "--old-from", str(bk7 / ".env.roles.old"), "--backup-dir", str(bk7), "--dry-run")
    check("discard --dry-run removes nothing", dry.returncode == 0 and (bk7 / ".env.roles.old").exists())
    pre = (f7 / ".env.pre-17b").read_bytes()
    real = run("discard", str(f7), "--new-file", str(nf7), "--old-from", str(bk7 / ".env.roles.old"), "--backup-dir", str(bk7))
    check("discard removes the two backup copies and the folder", real.returncode == 0 and not bk7.exists())
    check("discard never touches *.pre-17b", (f7 / ".env.pre-17b").read_bytes() == pre)
    check("the old value is in no file of the fixture", not any(o7 in p.read_text() for p in (tmp / "d" / "fx" / "backend").iterdir() if p.is_file()))
    # three states the first version of this suite did not distinguish (found by the mutation check)
    sub = tmp / "m1"
    sub.mkdir()
    f8, nf8, bk8, o8, n8 = fixture(sub)
    run("apply", str(f8), "--new-file", str(nf8), "--backup-dir", str(bk8))
    (f8 / ".env.migrate").write_text("MIGRATION_DATABASE_URL=postgresql+psycopg://asistente_migrator:Third" + "x" * 40 + "@db:5432/asistenteia\n")
    r = run("verify", str(f8), "--new-file", str(nf8), "--old-from", str(bk8 / ".env.roles.old"))
    check("verify fails when the URL carries a value that is neither old nor new", r.returncode == 1 and "does not carry the new value" in r.stdout)
    sub = tmp / "m2"
    sub.mkdir()
    f9, nf9, bk9, o9, n9 = fixture(sub)
    bk9.mkdir()
    (bk9 / ".env.roles.old").write_bytes((f9 / ".env.roles").read_bytes())
    (bk9 / ".env.migrate.old").write_bytes((f9 / ".env.migrate").read_bytes())
    r = run("discard", str(f9), "--new-file", str(nf9), "--old-from", str(bk9 / ".env.roles.old"), "--backup-dir", str(bk9))
    check("discard refuses while the live files still hold the old value, and keeps the copies", r.returncode == 1 and (bk9 / ".env.roles.old").exists() and (bk9 / ".env.migrate.old").exists())
    sub = tmp / "m3"
    sub.mkdir()
    fa, nfa, bka, oa, na = fixture(sub)
    bka.mkdir()
    (bka / "something").write_bytes(b"x")
    ba = snapshot(fa)
    r = run("apply", str(fa), "--new-file", str(nfa), "--backup-dir", str(bka))
    check("apply refuses a non-empty backup folder and changes nothing", r.returncode == 1 and snapshot(fa) == ba)
    # review findings M1, M2, minors 1 and 2
    sub = tmp / "n1"
    sub.mkdir()
    fb, nfb, bkb, ob, nb = fixture(sub)
    with open(fb / ".env.migrate", "a", encoding="utf-8") as h:
        h.write("OTHER_URL=postgresql://user:PW" + chr(0xFF03) + "SECRETPART@host:5432/db" + chr(10))
    bb = snapshot(fb)
    r = run("plan", str(fb), "--new-file", str(nfb))
    check("a non-ASCII URL never produces a traceback or an echo of the value (M1)", r.returncode == 1 and "Traceback" not in r.stderr + r.stdout and "SECRETPART" not in r.stderr + r.stdout and "FAILED unexpected" in r.stdout)
    r = run("apply", str(fb), "--new-file", str(nfb), "--backup-dir", str(bkb))
    check("apply with that URL changes nothing and leaks nothing (M1)", r.returncode == 1 and snapshot(fb) == bb and "SECRETPART" not in r.stderr + r.stdout and "Traceback" not in r.stderr)
    if os.name == "nt":
        sub = tmp / "n2"
        sub.mkdir()
        fc, nfc, bkc, oc, nc = fixture(sub)
        env = {k: v for k, v in os.environ.items() if k != "ROT_TEST_NO_ACL"}
        cmd = [sys.executable, "-I", str(TOOL), "apply", str(fc), "--new-file", str(nfc), "--backup-dir", str(bkc)]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)  # noqa: S603 - test harness
        check("on Windows apply refuses without --acl-script and writes nothing (M2)", r.returncode == 1 and "--acl-script is required" in r.stdout and not bkc.exists())
    sub = tmp / "n3"
    sub.mkdir()
    fd, nfd, bkd, od, nd = fixture(sub)
    bd = snapshot(fd)
    r = run("apply", str(fd), "--new-file", str(nfd), "--backup-dir", str(bkd), fail_at="interrupt1")
    check("an interruption right after the first os.replace restores BOTH files (minor 2)", r.returncode == 130 and snapshot(fd) == bd)
    sub = tmp / "n3b"
    sub.mkdir()
    fg, nfg, bkg, og, ng = fixture(sub)
    bg = snapshot(fg)
    r = run("apply", str(fg), "--new-file", str(nfg), "--backup-dir", str(bkg), fail_at="interruptmid1")
    check("an interruption between os.replace and its bookkeeping still restores that file (minor 2)", r.returncode == 130 and snapshot(fg) == bg)
    sub = tmp / "n4"
    sub.mkdir()
    fe, nfe, bke, oe, ne = fixture(sub)
    run("apply", str(fe), "--new-file", str(nfe), "--backup-dir", str(bke))
    import importlib.util
    spec = importlib.util.spec_from_file_location("rrp_inproc", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    real_remove = mod.base.overwrite_and_remove
    mod.base.overwrite_and_remove = lambda path, acl=None: False if path.name == ".env.migrate.old" else real_remove(path, acl)
    os.environ["ROT_TEST_NO_ACL"] = "1"
    code = mod.cmd_discard(fe, nfe, bke / ".env.roles.old", bke, False, None)
    check("discard keeps the old-value source copy when another copy is stuck, and a re-run can still verify (minor 1)", code == 1 and (bke / ".env.roles.old").exists() and (bke / ".env.migrate.old").exists())
    mod.base.overwrite_and_remove = real_remove
    code = mod.cmd_discard(fe, nfe, bke / ".env.roles.old", bke, False, None)
    check("the re-run then completes", code == 0 and not bke.exists())
print(f"PASS={passed} FAIL={failed}")
sys.exit(1 if failed else 0)
