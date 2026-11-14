"""Tests of rotate_admin_password.py on SYNTHETIC files only, with mutation testing. Prints PASS/FAIL lines, no secret."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
REAL_TOOL = HERE / "rotate_admin_password.py"
TOOL = REAL_TOOL
FAILURES = 0
# SYNTHETIC test values: not credentials of anything, never used outside these tests
OLD = "Old/Admin+pw=0123456789abcdefABCDEF"  # SYNTHETIC; needs URL quoting on purpose
NEW = "Nw9-Fresh_Value_0123456789abcdefghijKLMNOP"  # SYNTHETIC
USER = os.environ.get("USERNAME") or os.environ.get("USER") or "nobody"


def check(label: str, ok: bool) -> None:
    global FAILURES
    print(("PASS " if ok else "FAIL ") + label)
    FAILURES += 0 if ok else 1


def run(*args: str, env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False)
    return proc.returncode, proc.stdout + proc.stderr


def snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file()}


def build(root: Path, test_file: bool = True, crlf: bool = False, bom: bool = False) -> tuple[Path, Path, Path]:
    folder, new_file, backup = root / "backend", root / "outside" / "new.txt", root / "backup"
    folder.mkdir(parents=True)
    new_file.parent.mkdir()
    eol = "\r\n" if crlf else "\n"
    q = quote(OLD, safe="")
    b = "\ufeff" if bom else ""
    (folder / ".env.db").write_text(f"{b}POSTGRES_USER=asistente{eol}POSTGRES_PASSWORD={OLD}  # admin{eol}POSTGRES_DB=asistenteia{eol}", encoding="utf-8", newline="")
    (folder / ".env.roles").write_text(
        f"ADMIN_DATABASE_URL=postgresql+psycopg://asistente:{q}@db:5432/postgres{eol}DB_APP_PASSWORD=AppPw_0123456789abcdefghijklmnop{eol}# keep this comment{eol}", encoding="utf-8", newline="")
    if test_file:
        (folder / ".env.test").write_text(
            f"TEST_DATABASE_URL=postgresql+psycopg://asistente:{q}@127.0.0.1:5442/asistenteia_test{eol}"
            f"TEST_ADMIN_DATABASE_URL=postgresql+psycopg://asistente:{q}@127.0.0.1:5442/postgres{eol}"
            f"OTHER_URL=postgresql+psycopg://segregated:Other_pw_0123456789@127.0.0.1:5442/x{eol}", encoding="utf-8", newline="")
    (folder / ".env.pre-17b").write_text(f"DATABASE_URL=postgresql://asistente:{q}@db/x\n", encoding="utf-8")
    (folder / ".env.worker.pre-17b").write_text(f"DATABASE_URL=postgresql://asistente:{q}@db/x\n", encoding="utf-8")
    (folder / ".env.db.pre-17b").write_text(f"POSTGRES_USER=asistente\nPOSTGRES_PASSWORD={OLD}\n", encoding="utf-8")
    (folder / ".env.test.absent-before-17b").write_text("", encoding="utf-8")
    new_file.write_text(NEW + "\n", encoding="utf-8")
    return folder, new_file, backup


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)

        def fresh(**kw: bool) -> tuple[Path, Path, Path]:
            root = Path(tempfile.mkdtemp(dir=tmp_root))
            return build(root, **kw)

        # plan: names only, writes nothing
        folder, nf, bk = fresh()
        before = snapshot(folder)
        code, out = run("plan", str(folder), "--new-file", str(nf))
        check("plan succeeds (exit 0)", code == 0)
        check("plan prints no password (old, new, or quoted old)", OLD not in out and NEW not in out and quote(OLD, safe="") not in out)
        check("plan names the variables it would update", "POSTGRES_PASSWORD" in out and "ADMIN_DATABASE_URL" in out and "TEST_ADMIN_DATABASE_URL" in out)
        check("plan writes nothing", snapshot(folder) == before and not bk.exists())

        # apply, plain
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        check("apply succeeds (exit 0)", code == 0)
        check("apply output holds no password", OLD not in out and NEW not in out and quote(OLD, safe="") not in out and quote(NEW, safe="") not in out)
        after = snapshot(folder)
        check("no temporary file left", not [n for n in after if ".rot-" in n or ".restore-" in n])
        check(".env.db carries the new value, the comment and the other lines", f"POSTGRES_PASSWORD={NEW}  # admin" in after[".env.db"].decode() and "POSTGRES_DB=asistenteia" in after[".env.db"].decode())
        check(".env.roles: URL carries the new value, other variables and the comment are identical", f":{NEW}@db:5432/postgres" in after[".env.roles"].decode() and "DB_APP_PASSWORD=AppPw_0123456789abcdefghijklmnop" in after[".env.roles"].decode() and "# keep this comment" in after[".env.roles"].decode())
        check(".env.test: both administrator URLs updated, the segregated user's URL untouched", after[".env.test"].decode().count(NEW) == 2 and "segregated:Other_pw_0123456789@" in after[".env.test"].decode())
        check("the old value (raw and quoted) is in no live env file", all(OLD not in v.decode() and quote(OLD, safe="") not in v.decode() for k, v in after.items() if k in (".env.db", ".env.roles", ".env.test")))
        check("the pre-17b copies were not touched by apply", after[".env.db.pre-17b"] == before[".env.db.pre-17b"])
        check("backups are byte-identical to the originals", all((bk / (n + ".old")).read_bytes() == before[n] for n in (".env.db", ".env.roles", ".env.test")))

        # verify / second apply
        code, out = run("verify", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"))
        check("verify OK after apply", code == 0 and "VERIFY OK" in out)
        check("verify reports the pre-17b copies still present", ".env.db.pre-17b" in out)
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk.with_name("backup2")))
        check("a second apply is refused (new equals current)", code == 1 and "REFUSED" in out)
        (folder / ".env.extra").write_text(f"X={OLD}\n", encoding="utf-8")
        code, out = run("verify", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"))
        check("verify fails if another env file still holds the old value", code == 1 and ".env.extra" in out)
        (folder / ".env.extra").unlink()

        # rollback
        code, out = run("rollback", str(folder), "--backup-dir", str(bk))
        check("rollback restores the originals byte for byte", code == 0 and all(snapshot(folder)[n] == before[n] for n in (".env.db", ".env.roles", ".env.test")))
        code, out = run("rollback", str(folder), "--backup-dir", str(bk.with_name("nothing")))
        check("rollback without backups is refused", code == 1)

        # failure injection at every point: everything restored, nothing left
        for point in ("temp", "replace1", "replace2", "replace3", "verify"):
            folder, nf, bk = fresh()
            before = snapshot(folder)
            code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk), env={"ROT_TEST_FAIL_AT": point})
            now = snapshot(folder)
            check(f"failure at {point}: exit 1 and every file identical to before", code == 1 and now == before)
            check(f"failure at {point}: no temp file, no secret in the output", not [n for n in now if ".rot-" in n or ".restore-" in n] and OLD not in out and NEW not in out)

        # refusals
        folder, nf, bk = fresh()
        before = snapshot(folder)

        def refused(label: str, *args: str, expect: int = 1) -> None:
            c, o = run(*args)
            check(f"refused: {label}", c == expect and snapshot(folder) == before and OLD not in o and NEW not in o)

        for label, content in (("too short", "Short_0123456789"), ("bad characters", "has space_0123456789abcdefghijklmnopqrstuv"), ("placeholder", "Password_0123456789abcdefghijklmnopqrstuvwx"), ("two lines", NEW + "\n" + NEW + "\n"), ("equals the old one", "Old-same")):
            nf.write_text(content + "\n", encoding="utf-8")
            refused(f"new password {label}", "apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        nf.write_text(OLD.replace("/", "x").replace("+", "y").replace("=", "z") * 1 + "\n", encoding="utf-8")
        nf.write_text(NEW + "\n", encoding="utf-8")
        repo = tmp_root / "repo"
        (repo / ".git").mkdir(parents=True)
        inside = repo / "new.txt"
        inside.write_text(NEW + "\n", encoding="utf-8")
        refused("new-password file inside a Git repository", "apply", str(folder), "--new-file", str(inside), "--backup-dir", str(bk))
        refused("backup folder inside the env folder", "apply", str(folder), "--new-file", str(nf), "--backup-dir", str(folder / "bk"))
        (tmp_root / "full").mkdir()
        (tmp_root / "full" / "x").write_text("x", encoding="utf-8")
        refused("backup folder not empty", "apply", str(folder), "--new-file", str(nf), "--backup-dir", str(tmp_root / "full"))
        refused("plan with a missing new-password file", "plan", str(folder), "--new-file", str(tmp_root / "nope.txt"))
        q = quote(OLD, safe="")
        original_test = (folder / ".env.test").read_text(encoding="utf-8")
        (folder / ".env.test").write_text(f"TEST_DATABASE_URL='postgresql+psycopg://asistente:{q}@h/x'\n", encoding="utf-8")
        before = snapshot(folder)
        refused("a quoted administrator URL", "apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        (folder / ".env.test").write_text("TEST_DATABASE_URL=postgresql+psycopg://asistente:Other_value_0123456789@h/x\n", encoding="utf-8")
        before = snapshot(folder)
        refused("an administrator URL with a different password", "apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        (folder / ".env.test").write_text(original_test, encoding="utf-8")
        (folder / ".env.roles").unlink()
        before = snapshot(folder)
        refused("missing .env.roles", "apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        code, _ = run("plan", str(tmp_root / "no-folder"), "--new-file", str(nf))
        check("a missing folder is exit 2", code == 2)

        # the old value in a place the tool does not rotate (an unrelated variable): the rotation must fail and restore everything
        folder, nf, bk = fresh()
        with open(folder / ".env.test", "a", encoding="utf-8") as handle:
            handle.write("LEGACY_NOTE=" + OLD + chr(10))
        before = snapshot(folder)
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        check("the old value left in an unrelated variable is refused before anything is written", code == 1 and snapshot(folder) == before and OLD not in out and not bk.exists())

        # ---- review findings: other env files, orphans, interruption, input formats, Windows ACL and read-only files
        folder, nf, bk = fresh()
        (folder / ".env.worker").write_text("DATABASE_URL=postgresql://asistente:" + quote(OLD, safe="").lower() + "@db/x" + chr(10), encoding="utf-8")
        before = snapshot(folder)
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        check("another env file holding the old value (lower-case percent-encoding) is refused BEFORE any write", code == 1 and ".env.worker" in out and snapshot(folder) == before and not bk.exists() and OLD not in out)

        folder, nf, bk = fresh()
        with open(folder / ".env.roles", "a", encoding="utf-8") as handle:
            handle.write("NOTE_PW=" + OLD + chr(10))
        before = snapshot(folder)
        code, out = run("plan", str(folder), "--new-file", str(nf))
        check("plan refuses when the old value would remain in a variable that is not rotated", code == 1 and "NOTE" not in out and snapshot(folder) == before)

        folder, nf, bk = fresh()
        (folder / "..env.db.rot-99999").write_text("leftover", encoding="utf-8")
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        check("a leftover temporary file of an interrupted run blocks apply", code == 1 and "rollback" in out and not bk.exists())
        (folder / "..env.db.rot-99999").unlink()
        run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        (folder / "..env.roles.restore-4242").write_text("leftover", encoding="utf-8")
        code, out = run("rollback", str(folder), "--backup-dir", str(bk))
        check("rollback also removes the orphan temporary files", code == 0 and not (folder / "..env.roles.restore-4242").exists())

        folder, nf, bk = fresh()
        before = snapshot(folder)
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk), env={"ROT_TEST_FAIL_AT": "interrupt2"})
        now = snapshot(folder)
        check("an interruption (KeyboardInterrupt) between replacements restores every file (exit 130)", code == 130 and now == before and not [n for n in now if ".rot-" in n or ".restore-" in n])

        folder, nf, bk = fresh()
        for label, raw in (("UTF-16", ("﻿" + NEW + chr(10)).encode("utf-16")), ("empty", b""), ("only a newline", b"\n")):
            nf.write_bytes(raw)
            code, out = run("plan", str(folder), "--new-file", str(nf))
            check(f"new-password file {label}: refused without a traceback", code == 1 and "Traceback" not in out)
        nf.write_bytes(b"")
        code, out = run("verify", str(folder), "--new-file", str(nf), "--old-from", str(folder / ".env.db"))
        check("verify with an empty new-password file: exit 1 without a traceback", code == 1 and "Traceback" not in out)
        nf.write_text(NEW + chr(10), encoding="utf-8")
        inside = folder / "new-inside.txt"
        inside.write_text(NEW + chr(10), encoding="utf-8")
        before = snapshot(folder)
        code, out = run("plan", str(folder), "--new-file", str(inside))
        check("a new-password file inside the env folder is refused", code == 1 and snapshot(folder) == before)

        if os.name == "nt":
            acl = HERE.parent.parent / "group-17c" / "tools" / "secure_file_acl.ps1"

            def acl_ok(path: Path, rights: str) -> bool:
                proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(acl), "-Path", str(path), "-Rights", rights, "-VerifyOnly"], capture_output=True, text=True, check=False)
                return proc.returncode == 0

            folder, nf, bk = fresh()
            code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk), "--acl-script", str(acl))
            check("apply with the real owner-only ACL script succeeds", code == 0 and OLD not in out and NEW not in out)
            check("ALL THREE targets, including .env.db, carry the owner-only descriptor after the replacement", all(acl_ok(folder / n, "Modify") for n in (".env.db", ".env.roles", ".env.test")))
            check("the backup copies carry the owner-only Read descriptor", all(acl_ok(bk / (n + ".old"), "Read") for n in (".env.db", ".env.roles", ".env.test")))
            check("no temporary file left", not [p for p in folder.iterdir() if ".rot-" in p.name])
            code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"), "--backup-dir", str(bk), "--acl-script", str(acl))
            check("cleanup removes the Read-only backup copies and the pre-17b copies without a traceback", code == 0 and "Traceback" not in out and not bk.exists() and not (folder / ".env.db.pre-17b").exists())

            folder, nf, bk = fresh()
            run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
            stuck = folder / ".env.db.pre-17b"
            os.chmod(stuck, 0o444)  # on Windows the read-only attribute blocks the overwrite and the deletion
            code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"), "--backup-dir", str(bk))
            check("a file that cannot be deleted is reported, not a traceback; the others are still removed (exit 1)", code == 1 and "NOT REMOVED .env.db.pre-17b" in out and "Traceback" not in out and not (folder / ".env.pre-17b").exists())
            check("the backup copies are kept so that the clean-up can run again", all((bk / (n + ".old")).exists() for n in (".env.db", ".env.roles", ".env.test")))
            os.chmod(stuck, 0o666)
            code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"), "--backup-dir", str(bk))
            check("after fixing the permission the clean-up completes and removes the backups last", code == 0 and not stuck.exists() and not bk.exists())

        # variants: no .env.test, CRLF and BOM
        folder, nf, bk = fresh(test_file=False)
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        check("works without .env.test", code == 0 and not (folder / ".env.test").exists())
        folder, nf, bk = fresh(crlf=True, bom=True)
        before = snapshot(folder)
        code, out = run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        after = snapshot(folder)
        check("CRLF and BOM are preserved", code == 0 and after[".env.db"].startswith(b"\xef\xbb\xbf") and after[".env.db"].count(b"\r\n") == before[".env.db"].count(b"\r\n") and after[".env.roles"].count(b"\r\n") == before[".env.roles"].count(b"\r\n"))

        # cleanup
        folder, nf, bk = fresh()
        run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        for decoy in ("notes.pre-17b", "copy.env.pre-17b", "my.env.db.pre-17b", ".env.example"):
            (folder / decoy).write_text(f"OLD={OLD}" + chr(10) if "env.example" not in decoy else "A=" + chr(10), encoding="utf-8")
        old_src = bk / ".env.db.old"
        code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(old_src), "--backup-dir", str(bk), "--dry-run")
        check("cleanup dry run lists the exact names and removes nothing", code == 0 and "WOULD REMOVE .env.db.pre-17b" in out and (folder / ".env.db.pre-17b").exists())
        code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(old_src), "--backup-dir", str(bk))
        check("cleanup removes the five exact 17B names", code == 0 and not any((folder / n).exists() for n in (".env.pre-17b", ".env.worker.pre-17b", ".env.db.pre-17b", ".env.test.absent-before-17b")))
        check("cleanup keeps every decoy (no wildcard)", all((folder / d).exists() for d in ("notes.pre-17b", "copy.env.pre-17b", "my.env.db.pre-17b", ".env.example")))
        check("cleanup removes the backup copies and the backup folder", not bk.exists())
        check("cleanup output holds no password", OLD not in out and NEW not in out)
        check("the live env files are untouched by cleanup", all(NEW in (folder / n).read_text(encoding="utf-8") for n in (".env.db", ".env.roles")))
        folder, nf, bk = fresh()
        code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(folder / ".env.db.pre-17b"))
        check("cleanup before the rotation is refused (exit 1) and removes nothing", code == 1 and (folder / ".env.db.pre-17b").exists())
        run("apply", str(folder), "--new-file", str(nf), "--backup-dir", str(bk))
        (folder / ".env.worker.pre-17b").write_text("DATABASE_URL=postgresql://other:nothing@db/x\n", encoding="utf-8")
        (folder / ".env.pre-17b").unlink()
        (folder / ".env.pre-17b").mkdir()
        code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"))
        check("a directory named like a target is refused, nothing removed", code == 1 and (folder / ".env.db.pre-17b").exists())
        (folder / ".env.pre-17b").rmdir()
        code, out = run("cleanup", str(folder), "--new-file", str(nf), "--old-from", str(bk / ".env.db.old"))
        check("a pre-17b file that does not hold the old value is kept", code == 0 and (folder / ".env.worker.pre-17b").exists() and "KEEP .env.worker.pre-17b" in out)

        # no secret in argv: the tool takes only paths
        check("the interface has no argument that could carry a password", "--password" not in REAL_TOOL.read_text(encoding="utf-8"))

        # mutation testing
        if TOOL == REAL_TOOL and os.environ.get("ROT_NO_MUTATION") != "1":
            mutants = [
                ("rollback does not restore", "bad = restore(folder, backup_dir, replaced, acl_script)", "bad = 0"),
                ("the plan does not refuse a variable that would keep the old value", 'if holds_old(new_text, old):', "if False:"),
                ("quoted URL accepted", 'if value[:1] in "\'\\"":', "if False:"),
                ("different password accepted", "if unquote(parts.password or \"\") != old:", "if False:"),
                ("cleanup uses a wildcard", "for name in PRE_17B:\n        path = folder / name", "for name in sorted(p.name for p in folder.glob('*pre-17b*')):\n        path = folder / name"),
                ("output leaks the new value", 'say(f"APPLY OK: {', 'say(f"APPLY OK {new}: {'),
                ("the owner-only descriptors are not applied", "def restrict(acl_script: str | None, path: Path, rights: str) -> None:" + chr(10), "def restrict(acl_script: str | None, path: Path, rights: str) -> None:" + chr(10) + "    return" + chr(10)),
                ("an interruption does not restore", "except BaseException as exc:  # an interruption must restore the files too", "except (Refused, OSError) as exc:"),
                ("other env files are not scanned for the old value", 'if watched and path.is_file() and not path.is_symlink() and holds_old(', "if False and holds_old("),
                ("cleanup does not tolerate an undeletable file", "    except OSError:" + chr(10) + "        return False", "    except OSError:" + chr(10) + "        raise"),
                ("temporary files are never removed", "def remove_quietly(path: Path) -> None:" + chr(10) + "    try:", "def remove_quietly(path: Path) -> None:" + chr(10) + "    return" + chr(10) + "    try:"),
            ]
            mutant_path = HERE / "rotate_admin_password.mut.py"
            try:
                for label, old_text, new_text in mutants:
                    source = REAL_TOOL.read_text(encoding="utf-8")
                    if old_text not in source:
                        check(f"mutation '{label}': pattern found", False)
                        continue
                    mutant_path.write_text(source.replace(old_text, new_text, 1), encoding="utf-8", newline="\n")
                    proc = subprocess.run([sys.executable, str(Path(__file__)), "--mutant"], capture_output=True, text=True, env={**os.environ, "ROT_NO_MUTATION": "1", "ROT_TOOL": str(mutant_path)}, check=False)
                    fails = proc.stdout.count("\nFAIL ") + (1 if proc.stdout.startswith("FAIL ") else 0)
                    check(f"mutation '{label}' is detected ({fails} check(s) fail)", fails > 0)
            finally:
                mutant_path.unlink(missing_ok=True)
    print(f"{FAILURES} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    if os.environ.get("ROT_TOOL"):
        TOOL = Path(os.environ["ROT_TOOL"])
    sys.exit(main())
