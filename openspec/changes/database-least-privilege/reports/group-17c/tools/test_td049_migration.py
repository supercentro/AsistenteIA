"""Synthetic tests of migrate_legacy_sha256.py, acl_descriptor.ps1 and the manifest suffix option (TD-049). No real backup."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIGRATE, MANIFEST = HERE / "migrate_legacy_sha256.py", HERE / "backup_manifest.py"
FILE_ACL, FOLDER_ACL, DESC = HERE / "secure_file_acl.ps1", HERE / "secure_folder_acl.ps1", HERE / "acl_descriptor.ps1"
NAME = "synthetic_pre_17b.dump"
PAYLOAD = b"\x00pgdump-synthetic\x01" * 200
SHA = hashlib.sha256(PAYLOAD).hexdigest()
USER = os.environ.get("USERNAME") or os.environ.get("USER") or "nobody"
FAILURES = 0


def check(label: str, ok: bool) -> None:
    global FAILURES
    print(("PASS " if ok else "FAIL ") + label)
    FAILURES += 0 if ok else 1


def run(cmd: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})})
    return proc.returncode, proc.stdout + proc.stderr


def ps(script: Path, *args: str) -> tuple[int, str]:
    return run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args])


def mig(root: Path, *, extra: list[str] | None = None, env: dict[str, str] | None = None, sha: str = SHA) -> tuple[int, str]:
    cmd = [sys.executable, "-I", str(MIGRATE), "--name", NAME, "--expect-sha256", sha, "--expect-size", str(len(PAYLOAD)),
           "--stash", str(root / "stash"), "--suffix", ".integrity.txt", "--pair", f"primary={root / 'a'}", "--pair", f"second={root / 'b'}",
           "--file-acl", str(FILE_ACL)]
    return run(cmd + (extra or []), env)


def build(parent: Path) -> Path:
    root = Path(tempfile.mkdtemp(prefix="td049-", dir=parent))
    (root / "stash").mkdir()
    for folder in ("a", "b"):
        d = root / folder
        d.mkdir()
        (d / NAME).write_bytes(PAYLOAD)
        (d / (NAME + ".manifest.txt")).write_text("legacy manifest, no data\n", encoding="utf-8")
        (d / (NAME + ".sha256")).write_text(f"{SHA} *C:/Users/someone/Backups/a/{NAME}\n", encoding="ascii")
        ps(FOLDER_ACL, "-Path", str(d))
        for f in (NAME, NAME + ".manifest.txt", NAME + ".sha256"):
            ps(FILE_ACL, "-Path", str(d / f))
    return root


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file() and "stash" not in p.parts}


def main() -> int:
    parent = Path(tempfile.mkdtemp(prefix="td049-parent-"))
    try:
        # manifest suffix option
        d = parent / "suffix"
        d.mkdir()
        (d / NAME).write_bytes(PAYLOAD)
        code, out = run([sys.executable, "-I", str(MANIFEST), "write", str(d), NAME, "--copy", "primary", "--manifest-suffix", ".integrity.txt"])
        check("write with a custom suffix succeeds", code == 0 and (d / (NAME + ".integrity.txt")).is_file() and not (d / (NAME + ".manifest.txt")).exists())
        code, _ = run([sys.executable, "-I", str(MANIFEST), "verify", str(d), NAME, "--copy", "primary", "--manifest-suffix", ".integrity.txt"])
        check("verify with the same suffix passes", code == 0)
        code, _ = run([sys.executable, "-I", str(MANIFEST), "verify", str(d), NAME, "--copy", "primary"])
        check("verify without the suffix fails closed (manifest missing)", code == 1)
        code, _ = run([sys.executable, "-I", str(MANIFEST), "verify", str(d), NAME, "--copy", "second", "--manifest-suffix", ".integrity.txt"])
        check("verify with another copy label fails", code == 1)
        code, _ = run([sys.executable, "-I", str(MANIFEST), "write", str(d), NAME, "--copy", "x", "--manifest-suffix", "../evil.txt"])
        check("a malformed suffix is refused", code == 2)

        # happy path
        root = build(parent)
        before = snapshot(root)
        code, out = mig(root)
        check("migration succeeds (exit 0)", code == 0 and "MIGRATE OK" in out)
        check("output holds no path or user name", USER.lower() not in out.lower() and str(root).lower() not in out.lower())
        for lab, f in (("primary", "a"), ("second", "b")):
            code, _ = run([sys.executable, "-I", str(MANIFEST), "verify", str(root / f), NAME, "--copy", lab, "--manifest-suffix", ".integrity.txt"])
            check(f"independent verify of {lab}", code == 0)
            text = (root / f / (NAME + ".sha256")).read_text(encoding="ascii")
            check(f"{lab} .sha256 has two relative lines, no path", len(text.splitlines()) == 2 and "/" not in text and "*" not in text and USER.lower() not in text.lower())
        after = snapshot(root)
        check("dumps byte-identical", all(after[k] == before[k] for k in before if k.endswith(".dump")))
        check("legacy manifests untouched", all(after[k] == before[k] for k in before if k.endswith("manifest.txt")))
        check("legacy sha256 kept in the stash, byte-identical to the original",
              (root / "stash" / "primary.sha256.orig").read_text() .startswith(SHA) and "someone" in (root / "stash" / "primary.sha256.orig").read_text())
        check("stage folders removed", not list((root / "stash").glob("stage-*")))
        code, _ = ps(FILE_ACL, "-Path", str(root / "a" / (NAME + ".sha256")), "-VerifyOnly")
        check("new .sha256 restricted to Read (verified)", code == 0)
        # cross-reference negatives on copies
        x = parent / "cross"
        shutil.copytree(root / "b", x)
        shutil.copyfile(root / "a" / (NAME + ".integrity.txt"), x / (NAME + ".integrity.txt"))
        code, _ = run([sys.executable, "-I", str(MANIFEST), "verify", str(x), NAME, "--copy", "second", "--manifest-suffix", ".integrity.txt"])
        check("manifest taken from the other folder is rejected", code == 1)
        (x / (NAME + ".sha256")).write_text(f"{SHA}  C:/abs/{NAME}\n", encoding="ascii")
        code, _ = run([sys.executable, "-I", str(MANIFEST), "verify", str(x), NAME, "--manifest-suffix", ".integrity.txt"])
        check("absolute path in .sha256 is rejected", code == 1)
        # descriptor round trip on the folder policy

        # rollback at each injection point
        for point in ("stage", "after_manifest", "after_sha", "verify", "acl"):
            for lab in ("primary", "second"):
                r = build(parent)
                snap = snapshot(r)
                code, out = mig(r, env={"TD049_FAIL_AT": f"{point}:{lab}"})
                now = snapshot(r)
                clean = now == snap
                check(f"failure at {point}:{lab} -> exit 1, rolled back, files identical to before", code == 1 and "rolled back" in out and "PROBLEM" not in out and clean)
                check(f"failure at {point}:{lab} -> no new manifest left", not (r / "a" / (NAME + ".integrity.txt")).exists() and not (r / "b" / (NAME + ".integrity.txt")).exists())
                code, _ = ps(FILE_ACL, "-Path", str(r / "a" / (NAME + ".sha256")), "-VerifyOnly")
                check(f"failure at {point}:{lab} -> legacy .sha256 Read-only descriptor restored", code == 0)
                code, _ = ps(FILE_ACL, "-Path", str(r / "b" / (NAME + ".sha256")), "-VerifyOnly")
                check(f"failure at {point}:{lab} -> legacy .sha256 of the second folder also restricted", code == 0)
        # preconditions
        r = build(parent)
        snap_r = snapshot(r)
        code, out = mig(r, sha="0" * 64)
        check("wrong expected hash is refused before any change", code == 1 and snapshot(r) == snap_r)
        code, out = mig(r, extra=["--dry-run"])
        check("dry run writes nothing", code == 0 and not (r / "a" / (NAME + ".integrity.txt")).exists())
        (r / "b" / (NAME + ".integrity.txt")).write_text("x")
        code, out = mig(r)
        check("existing new manifest -> refused, legacy intact", code == 1 and (r / "a" / (NAME + ".sha256")).read_text().startswith(SHA + " *"))
        r2 = build(parent)
        (r2 / "b" / (NAME + ".sha256")).unlink()
        (r2 / "b" / (NAME + ".sha256")).write_text("deadbeef\n")
        code, out = mig(r2)
        check("legacy .sha256 not holding the dump hash -> refused", code == 1 and "MIGRATE OK" not in out)

        # descriptor export / restore round trip
        r3 = build(parent)
        code, _ = ps(DESC, "-Mode", "Export", "-Path", str(r3 / "a"), "-Store", str(r3 / "x.sddl"))
        check("descriptor export", code == 0)
        code, _ = ps(DESC, "-Mode", "Export", "-Path", str(r3 / "a"), "-Store", str(r3 / "x.sddl"))
        check("export never overwrites", code == 1)
        run(["icacls", str(r3 / "a"), "/inheritance:e"])
        code, _ = ps(DESC, "-Mode", "Compare", "-Path", str(r3 / "a"), "-Store", str(r3 / "x.sddl"))
        check("compare detects a changed folder descriptor", code == 1)
        code, out = ps(DESC, "-Mode", "Restore", "-Path", str(r3 / "a"), "-Store", str(r3 / "x.sddl"))
        check("restore brings every descriptor back (re-read identical)", code == 0)
        code, _ = ps(FOLDER_ACL, "-Path", str(r3 / "a"), "-VerifyOnly")
        check("restored folder satisfies the policy again", code == 0)
    finally:
        for p in parent.rglob("*"):
            ps_cmd = ["icacls", str(p), "/reset"]
            subprocess.run(ps_cmd, capture_output=True)
        shutil.rmtree(parent, ignore_errors=True)
    print(f"{FAILURES} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
