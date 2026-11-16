"""Write and verify the integrity files of ONE copy of a backup (TD-049, group 17C).

    python backup_manifest.py write  <folder> <dump-name> --copy <label> [--meta key=value ...]
    python backup_manifest.py verify <folder> <dump-name> [--copy <label>]

Each copy gets its own `<dump>.sha256` (two lines in `sha256sum` format: the dump and the manifest, named by FILE NAME
only, so `sha256sum -c <dump>.sha256` works inside the folder and never points at another folder) and its own
`<dump>.manifest.txt` (`key: value` lines: the copy label, the file name, size, sha256, creation time and the metadata
given). No absolute path, no user name and no data of the database ever go into these files or into the output.

Fail closed: `verify` prints `MANIFEST FAIL <name>: <reasons>` and exits 1 on ANY inconsistency (hash of the dump or of
the manifest, a name that is not the dump's own, a size mismatch, a wrong copy label, a path or a user name inside a
value, a missing or malformed line); a missing dump is exit 2. Only names, sizes, hashes and verdicts are printed.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

MANIFEST_VERSION = "1"
FORBIDDEN_CHARS = ("/", "\\", "*", "\n", "\r", "\t")
LINE = re.compile(r"^([a-z0-9_]+): (.*)$")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sensitive(value: str) -> bool:
    """A value that would carry a location or an identity into the evidence."""
    if any(char in value for char in FORBIDDEN_CHARS):
        return True
    user = os.environ.get("USERNAME") or os.environ.get("USER") or getpass.getuser()
    return bool(user) and user.lower() in value.lower()


DEFAULT_SUFFIX = ".manifest.txt"
SUFFIX_RULE = re.compile(r"\.[a-z0-9][a-z0-9.-]*\.txt")


def companions(folder: Path, name: str, suffix: str = DEFAULT_SUFFIX) -> tuple[Path, Path, Path]:
    return folder / name, folder / (name + ".sha256"), folder / (name + suffix)


def write(folder: Path, name: str, copy: str, meta: list[str], suffix: str = DEFAULT_SUFFIX) -> int:
    dump, sha_file, manifest = companions(folder, name, suffix)
    if not dump.is_file():
        print(f"MANIFEST FAIL {name}: the dump is missing")
        return 2
    if sensitive(name) or sensitive(copy):
        print("MANIFEST FAIL: the dump name or the copy label holds a path separator or the user name")
        return 1
    fields: list[tuple[str, str]] = []
    for item in meta:
        key, sep, value = item.partition("=")
        if not sep or not re.fullmatch(r"[a-z0-9_]+", key) or key in {"manifest", "copy", "file", "size", "sha256", "created_utc"}:
            print(f"MANIFEST FAIL {name}: malformed or reserved metadata key")
            return 1
        if sensitive(value):
            print(f"MANIFEST FAIL {name}: the value of '{key}' holds a path separator or the user name; refused")
            return 1
        fields.append((key, value))
    for existing in (sha_file, manifest):
        if existing.exists():
            print(f"MANIFEST FAIL {name}: {existing.name} already exists; not overwriting")
            return 1
    digest = sha256_of(dump)
    lines = [
        ("manifest", MANIFEST_VERSION),
        ("copy", copy),
        ("file", name),
        ("size", str(dump.stat().st_size)),
        ("sha256", digest),
        ("created_utc", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
        *fields,
    ]
    manifest.write_bytes(("".join(f"{key}: {value}\n" for key, value in lines)).encode("utf-8"))
    sha_file.write_bytes(f"{digest}  {name}\n{sha256_of(manifest)}  {manifest.name}\n".encode("ascii"))
    print(f"MANIFEST OK {name} (copy {copy}): written; size {dump.stat().st_size}; sha256 {digest}")
    return 0


def parse_sha_file(text: str, expected_names: tuple[str, str]) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    problems: list[str] = []
    rows = text.splitlines()
    if len(rows) != 2:
        problems.append(f".sha256 must hold exactly 2 lines, found {len(rows)}")
    for row in rows:
        match = re.fullmatch(r"([0-9a-f]{64})  (\S+)", row)
        if not match:
            problems.append(".sha256 holds a malformed line")
            continue
        digest, listed = match.groups()
        if listed not in expected_names or sensitive(listed):
            problems.append(".sha256 names a file that is not this dump or its manifest")
            continue
        entries[listed] = digest
    return entries, problems


def verify(folder: Path, name: str, copy: str | None, suffix: str = DEFAULT_SUFFIX) -> int:
    dump, sha_file, manifest = companions(folder, name, suffix)
    if not dump.is_file():
        print(f"MANIFEST FAIL {name}: the dump is missing")
        return 2
    problems: list[str] = []
    if sensitive(name):
        problems.append("the dump name holds a path separator or the user name")
    if not sha_file.is_file():
        problems.append(".sha256 is missing")
    if not manifest.is_file():
        problems.append("manifest is missing")
    if problems:
        print(f"MANIFEST FAIL {name}: " + "; ".join(problems))
        return 1
    actual = sha256_of(dump)
    entries, problems = parse_sha_file(sha_file.read_text(encoding="ascii", errors="replace"), (name, manifest.name))
    if entries.get(name) != actual:
        problems.append("sha256 of the dump differs from .sha256")
    if entries.get(manifest.name) != sha256_of(manifest):
        problems.append("sha256 of the manifest differs from .sha256")
    values: dict[str, str] = {}
    for row in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LINE.fullmatch(row)
        if not match:
            problems.append("manifest holds a malformed line")
            continue
        key, value = match.groups()
        if key in values:
            problems.append(f"manifest repeats '{key}'")
        values[key] = value
        if key != "file" and sensitive(value):
            problems.append(f"manifest value '{key}' holds a path separator or the user name")
    if values.get("manifest") != MANIFEST_VERSION:
        problems.append("manifest version is not 1")
    if values.get("file") != name:
        problems.append("manifest names another file")
    if values.get("size") != str(dump.stat().st_size):
        problems.append("manifest size differs from the dump")
    if values.get("sha256") != actual:
        problems.append("manifest sha256 differs from the dump")
    if not values.get("copy"):
        problems.append("manifest has no copy label")
    elif copy is not None and values["copy"] != copy:
        problems.append("manifest belongs to another copy")
    if problems:
        print(f"MANIFEST FAIL {name}: " + "; ".join(problems))
        return 1
    print(f"MANIFEST OK {name} (copy {values['copy']}): size {dump.stat().st_size}; sha256 {actual}; .sha256 and manifest consistent")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("write", "verify"):
        branch = sub.add_parser(command)
        branch.add_argument("folder")
        branch.add_argument("name")
        branch.add_argument("--copy", required=(command == "write"))
        # A different manifest file name lets an older folder that already holds a legacy `<dump>.manifest.txt` get a
        # new-format manifest next to it without touching the legacy file (TD-049 migration).
        branch.add_argument("--manifest-suffix", default=DEFAULT_SUFFIX)
        if command == "write":
            branch.add_argument("--meta", action="append", default=[])
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    if not folder.is_dir():
        print("MANIFEST FAIL: the folder does not exist")
        return 2
    if not SUFFIX_RULE.fullmatch(args.manifest_suffix) or sensitive(args.manifest_suffix):
        print("MANIFEST FAIL: the manifest suffix is malformed")
        return 2
    if args.command == "write":
        return write(folder, args.name, args.copy, args.meta, args.manifest_suffix)
    return verify(folder, args.name, args.copy, args.manifest_suffix)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
