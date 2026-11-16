"""Self-test of backup_manifest.py on throw-away files, with negative mutations. Prints PASS/FAIL lines, no path."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).with_name("backup_manifest.py")
FAILURES = 0
USER = os.environ.get("USERNAME") or os.environ.get("USER") or "nobody"


def check(label: str, condition: bool) -> None:
    global FAILURES
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        FAILURES += 1


def tool(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def fresh(folder: Path, name: str, payload: bytes = b"\x00pgdump-synthetic\x01" * 100) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(payload)


def mutate(folder: Path, name: str, kind: str) -> None:
    dump, sha_file, manifest = folder / name, folder / (name + ".sha256"), folder / (name + ".manifest.txt")
    if kind == "dump-byte":
        data = bytearray(dump.read_bytes())
        data[10] ^= 0xFF
        dump.write_bytes(bytes(data))
    elif kind == "dump-truncated":
        dump.write_bytes(dump.read_bytes()[:-1])
    elif kind == "sha-other-name":
        sha_file.write_text(sha_file.read_text().replace(f"  {name}\n", "  other.dump\n"))
    elif kind == "sha-path":
        sha_file.write_text(sha_file.read_text().replace(f"  {name}\n", f" *C:/Users/someone/{name}\n"))
    elif kind == "sha-one-line":
        sha_file.write_text(sha_file.read_text().splitlines()[0] + "\n")
    elif kind == "manifest-size":
        manifest.write_text(manifest.read_text().replace("size: ", "size: 1"))
    elif kind == "manifest-other-file":
        manifest.write_text(manifest.read_text().replace(f"file: {name}", "file: other.dump"))
    elif kind == "manifest-relabelled-with-hash":
        manifest.write_text(manifest.read_text().replace("copy: primary", "copy: tampered"))
        rows = sha_file.read_text().splitlines()
        rows[1] = hashlib.sha256(manifest.read_bytes()).hexdigest() + f"  {name}.manifest.txt"
        sha_file.write_text("\n".join(rows) + "\n")
    elif kind == "manifest-path-value":
        manifest.write_text(manifest.read_text() + "note: C:\\Users\\someone\\Backups\n")
    elif kind == "manifest-missing":
        manifest.unlink()
    elif kind == "sha-missing":
        sha_file.unlink()


def main() -> int:
    name = "asistenteia_pre_17b_20990101T000000Z.dump"
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        first, second = root / "first", root / "second"
        fresh(first, name)
        code, out = tool("write", str(first), name, "--copy", "primary", "--meta", "revision=0005", "--meta", "format=pg_dump -Fc")
        check("write succeeds and reports OK with size and sha256", code == 0 and "MANIFEST OK" in out and "sha256 " in out)
        check("the output names the file only (no folder, no user name)", raw not in out and USER.lower() not in out.lower())
        sha_text = (first / (name + ".sha256")).read_text()
        manifest_text = (first / (name + ".manifest.txt")).read_text()
        check(
            ".sha256 holds two sha256sum lines naming the dump and the manifest by file name only",
            sha_text.count("\n") == 2 and f"  {name}\n" in sha_text and f"  {name}.manifest.txt\n" in sha_text and not any(c in sha_text for c in "/\\*"),
        )
        check("the manifest has no absolute path and no user name", "\\" not in manifest_text and ":/" not in manifest_text and USER.lower() not in manifest_text.lower())
        check("the manifest carries the copy label, the file name and the metadata", "copy: primary\n" in manifest_text and f"file: {name}\n" in manifest_text and "revision: 0005\n" in manifest_text)
        code, out = tool("verify", str(first), name, "--copy", "primary")
        check("verify passes on an intact copy", code == 0 and "MANIFEST OK" in out and "consistent" in out)
        if shutil.which("sha256sum"):
            proc = subprocess.run(["sha256sum", "-c", name + ".sha256"], cwd=first, capture_output=True, text=True)
            check("sha256sum -c accepts the .sha256 inside its folder (standard format)", proc.returncode == 0 and proc.stdout.count(": OK") == 2)
        code, out = tool("write", str(first), name, "--copy", "primary")
        check("a second write is refused: the integrity files are never overwritten", code == 1 and "already exists" in out)

        second.mkdir()
        shutil.copy2(first / name, second / name)
        code, out = tool("write", str(second), name, "--copy", "second")
        check("the second copy gets its own manifest and .sha256", code == 0 and (second / (name + ".manifest.txt")).is_file())
        code, out = tool("verify", str(second), name, "--copy", "second")
        check("the second copy verifies against its own files", code == 0)
        code, out = tool("verify", str(second), name, "--copy", "primary")
        check("the second copy is refused when checked as the primary (label mismatch)", code == 1 and "another copy" in out)
        shutil.copy2(first / (name + ".manifest.txt"), second / (name + ".manifest.txt"))
        code, out = tool("verify", str(second), name, "--copy", "second")
        check("a manifest copied from the other folder is refused (its hash is not in this folder's .sha256)", code == 1 and "manifest differs" in out)

        cases = [
            ("one byte of the dump flipped", "dump-byte", "sha256 of the dump differs"),
            ("the dump truncated by one byte", "dump-truncated", "size differs"),
            (".sha256 names another file", "sha-other-name", "not this dump"),
            (".sha256 carries an absolute path (the old ` *path` format)", "sha-path", "malformed"),
            (".sha256 lost its manifest line", "sha-one-line", "exactly 2 lines"),
            ("manifest size edited", "manifest-size", "size differs"),
            ("manifest names another file", "manifest-other-file", "another file"),
            ("manifest relabelled with its hash re-computed: caught by the copy label", "manifest-relabelled-with-hash", "another copy"),
            ("manifest value with an absolute path", "manifest-path-value", "path separator"),
            ("manifest missing", "manifest-missing", "manifest is missing"),
            (".sha256 missing", "sha-missing", ".sha256 is missing"),
        ]
        for label, kind, expect in cases:
            with tempfile.TemporaryDirectory() as mraw:
                folder = Path(mraw) / "m"
                shutil.copytree(first, folder)
                mutate(folder, name, kind)
                code, out = tool("verify", str(folder), name, "--copy", "primary")
                check(f"mutation rejected (exit 1, reason named): {label}", code == 1 and "MANIFEST FAIL" in out and expect in out and mraw not in out)

        code, out = tool("verify", str(first), "absent.dump")
        check("a missing dump is exit 2", code == 2 and "missing" in out)
        code, out = tool("write", str(first), name + "2", "--copy", "x")
        check("write refuses a missing dump (exit 2)", code == 2)
        fresh(root / "w", name)
        code, out = tool("write", str(root / "w"), name, "--copy", "primary", "--meta", f"source=C:/Users/{USER}/x")
        check("write refuses a metadata value with a path or the user name, without echoing it", code == 1 and "refused" in out and USER.lower() not in out.lower())
        check("nothing was written after the refusal", not (root / "w" / (name + ".sha256")).exists() and not (root / "w" / (name + ".manifest.txt")).exists())
        code, out = tool("write", str(root / "w"), name, "--copy", "primary", "--meta", "sha256=abc")
        check("write refuses a reserved metadata key", code == 1 and "reserved" in out)
        code, out = tool("verify", str(root / "nowhere"), name)
        check("a missing folder is exit 2", code == 2)
    print(f"{FAILURES} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
