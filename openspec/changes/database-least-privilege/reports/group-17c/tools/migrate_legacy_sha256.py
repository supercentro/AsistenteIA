"""Replace the legacy `.sha256` of an existing backup, in several folders at once, all or nothing (TD-049).

    python migrate_legacy_sha256.py --name <dump> --expect-sha256 <hex> --expect-size <n> --stash <dir> \
        --suffix .integrity.txt --pair primary=<folder> --pair second=<folder> [--file-acl <secure_file_acl.ps1>]

What it does, in this order, and stops (exit 1, nothing changed or everything rolled back) at the first problem:
  1. Preconditions per folder: the dump has the expected size and SHA-256; the legacy `.sha256` exists and its hash is the
     dump's; the new manifest does not exist; the stash holds no file of this run.
  2. Stash (outside the repository): a byte-identical copy of every legacy `.sha256`, verified.
  3. Stage: in the stash, a copy of the dump and the new `<dump>.sha256` + `<dump><suffix>` written by backup_manifest.py and
     verified there. The dump in the folder is only read.
  4. Commit per folder: the new manifest is moved in, then the new `.sha256` replaces the legacy one; backup_manifest.py
     `verify` runs inside the folder; optionally both new files are restricted to Read for the current user.
  5. If any step of any folder fails: every folder is rolled back (new manifest removed, legacy `.sha256` restored from the
     stash and re-restricted) and the hash of the restored file is checked against the stash.
Output: labels, file names and verdicts only; never a folder path, a user name or an error text that could hold one.
Test hook: environment TD049_FAIL_AT=<stage|after_manifest|after_sha|verify|acl>:<label> raises a failure there (synthetic tests).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_TOOL = HERE / "backup_manifest.py"
LEGACY_LINE = re.compile(r"([0-9a-f]{64}) [ *](.+)")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_tool(*args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-I", str(MANIFEST_TOOL), *args], capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def file_acl(script: str | None, target: Path) -> bool:
    if script is None:
        return True
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Path", str(target)],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def hook(point: str, label: str) -> None:
    if os.environ.get("TD049_FAIL_AT") == f"{point}:{label}":
        raise RuntimeError(f"injected failure at {point}")


def remove(path: Path) -> None:
    """Delete a file whose own descriptor may be Read-only: the folder's delete-child right is what allows it."""
    if path.exists():
        path.unlink()


def say(message: str) -> None:
    print(message, flush=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--expect-sha256", required=True)
    parser.add_argument("--expect-size", required=True, type=int)
    parser.add_argument("--stash", required=True)
    parser.add_argument("--suffix", required=True)
    parser.add_argument("--pair", action="append", required=True)
    parser.add_argument("--file-acl", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    name, suffix = args.name, args.suffix
    pairs: dict[str, Path] = {}
    for item in args.pair:
        label, sep, folder = item.partition("=")
        if not sep or not re.fullmatch(r"[a-z0-9]+", label) or label in pairs:
            say("MIGRATE FAIL: malformed or repeated --pair")
            return 1
        pairs[label] = Path(folder)
    stash = Path(args.stash)
    if not stash.is_dir():
        say("MIGRATE FAIL: the stash folder does not exist")
        return 1

    # 1. Preconditions (no change yet)
    for label, folder in pairs.items():
        dump, sha, new_manifest = folder / name, folder / (name + ".sha256"), folder / (name + suffix)
        problems = []
        if not folder.is_dir():
            problems.append("folder missing")
        elif not dump.is_file():
            problems.append("dump missing")
        else:
            if dump.stat().st_size != args.expect_size:
                problems.append("dump size differs from the expected one")
            if sha256_of(dump) != args.expect_sha256:
                problems.append("dump sha256 differs from the expected one")
            if not sha.is_file():
                problems.append("legacy .sha256 missing")
            else:
                match = LEGACY_LINE.fullmatch(sha.read_text(encoding="utf-8", errors="replace").strip())
                if not match or match.group(1) != args.expect_sha256:
                    problems.append("legacy .sha256 is not a single line holding the dump's hash")
            if new_manifest.exists():
                problems.append("the new manifest already exists; not overwriting")
        if (stash / f"{label}.sha256.orig").exists() or (stash / f"stage-{label}").exists():
            problems.append("the stash already holds files of this run")
        if problems:
            say(f"MIGRATE FAIL {label}: " + "; ".join(problems))
            return 1
    say(f"MIGRATE preconditions OK for {len(pairs)} folders (dump {name}: size and sha256 as expected)")
    if args.dry_run:
        say("MIGRATE dry run: nothing written")
        return 0

    created: list[Path] = []
    committed: list[str] = []
    try:
        # 2. Stash the legacy files
        for label, folder in pairs.items():
            copy = stash / f"{label}.sha256.orig"
            shutil.copyfile(folder / (name + ".sha256"), copy)
            if copy.read_bytes() != (folder / (name + ".sha256")).read_bytes():
                raise RuntimeError("stash copy differs")
            say(f"MIGRATE stash {label}: legacy .sha256 copied and verified")
        # 3. Stage and verify away from the folders
        for label, folder in pairs.items():
            stage = stash / f"stage-{label}"
            stage.mkdir()
            shutil.copyfile(folder / name, stage / name)
            hook("stage", label)
            code, _ = manifest_tool("write", str(stage), name, "--copy", label, "--manifest-suffix", suffix, "--meta", "migrated=td049")
            if code != 0:
                raise RuntimeError("staging write failed")
            code, text = manifest_tool("verify", str(stage), name, "--copy", label, "--manifest-suffix", suffix)
            if code != 0:
                raise RuntimeError("staging verify failed")
            say(f"MIGRATE stage {label}: {text}")
        # 4. Commit
        for label, folder in pairs.items():
            stage = stash / f"stage-{label}"
            new_manifest, new_sha = folder / (name + suffix), folder / (name + ".sha256")
            shutil.copyfile(stage / (name + suffix), new_manifest)
            created.append(new_manifest)
            hook("after_manifest", label)
            if new_sha.exists():
                new_sha.unlink()  # allowed by the folder's delete-child right even when the file is Read-only
            shutil.copyfile(stage / (name + ".sha256"), new_sha)
            committed.append(label)
            hook("after_sha", label)
            code, text = manifest_tool("verify", str(folder), name, "--copy", label, "--manifest-suffix", suffix)
            hook("verify", label)
            if code != 0:
                raise RuntimeError("verify failed in the folder")
            say(f"MIGRATE commit {label}: {text}")
            ok = file_acl(args.file_acl, new_manifest) and file_acl(args.file_acl, new_sha)
            if os.environ.get("TD049_FAIL_AT") == f"acl:{label}":
                ok = False
            if not ok:
                raise RuntimeError("file ACL failed")
            say(f"MIGRATE acl {label}: new .sha256 and manifest restricted")
    except Exception as exc:  # noqa: BLE001 - every failure must roll back
        say(f"MIGRATE ERROR ({type(exc).__name__}); rolling back every folder")
        bad = 0
        for label, folder in pairs.items():
            remove(folder / (name + suffix))
            target, orig = folder / (name + ".sha256"), stash / f"{label}.sha256.orig"
            if orig.is_file():
                remove(target)
                shutil.copyfile(orig, target)
                if sha256_of(target) != sha256_of(orig):
                    bad += 1
                if not file_acl(args.file_acl, target):
                    bad += 1
            ok_dump = sha256_of(folder / name) == args.expect_sha256
            same = orig.is_file() and target.is_file() and sha256_of(target) == sha256_of(orig)
            bad += 0 if same else 1
            say(f"MIGRATE rollback {label}: legacy .sha256 {'restored, hash equal to the stash' if same else 'NOT RESTORED'}; dump {'intact' if ok_dump else 'CHANGED'}; new manifest removed")
            bad += 0 if ok_dump else 1
        say("MIGRATE rolled back" + ("" if bad == 0 else f" WITH {bad} PROBLEM(S)"))
        return 1
    for stage in (stash / f"stage-{label}" for label in pairs):
        shutil.rmtree(stage, ignore_errors=True)
    say(f"MIGRATE OK: {len(committed)} folders migrated; dumps untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
