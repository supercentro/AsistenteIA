"""Rotate the database administrator password in the env FILES of step 17B.6 (TD-038). Names and verdicts only; never a value.

    python rotate_admin_password.py plan    <backend folder> --new-file <file>
    python rotate_admin_password.py apply   <backend folder> --new-file <file> --backup-dir <dir> [--acl-script <secure_file_acl.ps1>]
    python rotate_admin_password.py verify  <backend folder> --new-file <file> --old-from <env file with POSTGRES_PASSWORD>
    python rotate_admin_password.py rollback <backend folder> --backup-dir <dir>
    python rotate_admin_password.py cleanup <backend folder> --new-file <file> --old-from <env file> [--backup-dir <dir>] [--dry-run]   (NO-GO while the *.pre-17b copies are the only tested file-level rollback)
    python rotate_admin_password.py discard <backend folder> --new-file <file> --old-from <backup>/.env.db.old --backup-dir <dir> [--dry-run] [--acl-script <secure_file_acl.ps1>]

The new value lives in a file OUTSIDE the repository (one line, letters, digits, `-` and `_`, 32 to 128 characters); it is never an
argument of a process, never printed, never logged. The tool updates, as ONE unit, the files that hold the administrator password:
`.env.db` (POSTGRES_PASSWORD), `.env.roles` (ADMIN_DATABASE_URL) and, when it exists, `.env.test` (URL variables whose user is the
administrator). Every other line is kept byte for byte (line endings, comments, BOM).

apply: validate everything first (nothing is written if any check fails), copy the originals to the backup folder (owner-only),
write temporary files next to the targets, check them, replace each target atomically, re-read and compare; if ANY step fails
the targets already replaced are restored from the backup and compared byte for byte. Temporary files are always removed.
cleanup: only after `verify` is clean, and only the EXACT names the 17B tools created (`.env.pre-17b`, `.env.worker.pre-17b`,
`.env.db.pre-17b`, `.env.test.pre-17b`, `.env.test.absent-before-17b`; with --backup-dir the `*.old` copies); no wildcard.
Exit codes: 0 ok, 1 refused or failed (nothing changed, or everything restored), 2 usage or missing file, 3 rollback incomplete, 130 interrupted (restored).
Backups: each `<name>.old` is written through a temporary name (fsynced) and a `.backup-complete` marker (name, size and SHA-256 of each copy, written atomically) is written last, before any live file is touched; `rollback` refuses without the marker or when a copy is missing, empty, of another size or of another content. `apply` takes an exclusive `.apply.lock` in the backup folder: of two concurrent runs exactly one proceeds.
Test hook: environment ROT_TEST_FAIL_AT=<temp|marker|markermid|replace1|replace2|replace3|verify|interruptmid1> (and ROT_TEST_HOLD_LOCK_SECONDS) (and ROT_TEST_NO_ACL=1 disables the Windows ACL requirement in file-level tests) makes the tool fail at that point (it can only make it fail).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus, unquote, urlsplit

ADMIN_FILE, ROLES_FILE, TEST_FILE = ".env.db", ".env.roles", ".env.test"
TARGETS = (ADMIN_FILE, ROLES_FILE, TEST_FILE)
PRE_17B = (".env.pre-17b", ".env.worker.pre-17b", ".env.db.pre-17b", ".env.test.pre-17b", ".env.test.absent-before-17b")
NEW_VALUE = re.compile(r"[A-Za-z0-9_-]{32,128}")
LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*?)(\r?\n?)$", re.DOTALL)


class Refused(Exception):
    """A check failed; the message names files and variables, never a value."""


def holds_old(text: str, old: str) -> bool:
    """The old value in any plausible spelling: raw, percent-encoded (any hex case), form-encoded."""
    lowered = text.lower()
    forms = {quote(old, safe=""), quote_plus(old), quote(old, safe="/")}
    return old in text or any(form in text or form.lower() in lowered for form in forms)


def require_acl(acl_script: str | None) -> None:
    """On Windows the temporary files and backup copies hold secrets: without the owner-only descriptor script the tool refuses (SEC-17B-01 review M2)."""
    if os.name == "nt" and acl_script is None and os.environ.get("ROT_TEST_NO_ACL") != "1":
        raise Refused("on Windows --acl-script is required (the temporary files and backup copies must be owner-only)")


BACKUP_MARK = ".backup-complete"
LOCK_NAME = ".apply.lock"


def sha256_hex(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def write_backup_copy(backup_dir: Path, name: str, raw: bytes, acl_script: str | None) -> None:
    """Write `<name>.old` through a temporary name, fsynced, then rename: a kill can never leave an empty or partial `.old` under the real name."""
    final, temp = backup_dir / (name + ".old"), backup_dir / ("." + name + ".old.tmp")
    temp.write_bytes(b"")
    restrict(acl_script, temp, "Modify")
    with open(temp, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if temp.read_bytes() != raw:
        remove_quietly(temp)
        raise Refused(f"{name}: the backup copy differs from the original")
    restrict(acl_script, temp, "Read")
    os.replace(temp, final)


def write_marker(backup_dir: Path, copies: dict[str, bytes], acl_script: str | None) -> None:
    """The marker (name, size and SHA-256 of each copy) says that every copy is complete and verified; `rollback` refuses without it.

    It is written to a temporary name, fsynced and renamed, so an interrupted write leaves no marker at all (and then no live file was touched yet).
    """
    fail_at("marker")
    marker, temp = backup_dir / BACKUP_MARK, backup_dir / (BACKUP_MARK + ".tmp")
    temp.write_bytes(b"")
    restrict(acl_script, temp, "Modify")
    with open(temp, "wb") as handle:
        handle.write("".join(f"{n} {len(raw)} {sha256_hex(raw)}\n" for n, raw in copies.items()).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    if os.environ.get("ROT_TEST_FAIL_AT") == "markermid":
        raise KeyboardInterrupt  # the window between the temporary marker and its rename
    os.replace(temp, marker)


def check_backup(backup_dir: Path, targets: tuple[str, ...]) -> dict[str, bytes]:
    """Names the marker lists whose `.old` exists, is not a link and has exactly the recorded non-zero size AND SHA-256; anything else refuses."""
    marker = backup_dir / BACKUP_MARK
    if not marker.is_file() or marker.is_symlink():
        raise Refused("the backup folder holds no complete backup (no marker): do not roll back from it; compare the live files with the .old copies by hand")
    verified: dict[str, bytes] = {}
    for line in marker.read_text(encoding="utf-8").splitlines():
        name, _, rest = line.partition(" ")
        size, _, digest = rest.partition(" ")
        copy = backup_dir / (name + ".old")
        if name not in targets or not size.isdigit() or int(size) == 0 or len(digest) != 64 or not copy.is_file() or copy.is_symlink() or copy.stat().st_size != int(size):
            raise Refused(f"{name or '?'}: the backup copy is missing, empty or incomplete: do not roll back from it")
        data = copy.read_bytes()
        if sha256_hex(data) != digest:
            raise Refused(f"{name}: the backup copy changed after it was written (same size, other content): do not roll back from it")
        verified[name] = data  # the restore writes THESE bytes, not a second read of the file
    if not verified:
        raise Refused("the backup marker lists no file")
    for target in targets:
        if target not in verified and (backup_dir / (target + ".old")).exists():
            raise Refused(f"{target}: a backup copy exists that the marker does not list: do not roll back from this folder")
    return verified


def acquire_lock(backup_dir: Path) -> None:
    """Exclusive creation: of two applies on the same folder, exactly one gets the lock."""
    try:
        os.close(os.open(backup_dir / LOCK_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        raise Refused("another apply is using this backup folder (or a killed one left .apply.lock): use a fresh folder") from None


def release_lock(backup_dir: Path) -> None:
    remove_quietly(backup_dir / LOCK_NAME)


def remove_leftovers(backup_dir: Path, targets: tuple[str, ...], dry_run: bool, acl_script: str | None) -> None:
    """Hidden files a killed apply can leave in the folder; the temporary copies hold the old value, so they are overwritten before removal."""
    for name in [f".{n}.old.tmp" for n in targets] + [BACKUP_MARK + ".tmp", LOCK_NAME]:
        path = backup_dir / name
        if path.is_file() and not path.is_symlink() and path.stat().st_nlink <= 1:  # a hard link to a live file must never be overwritten
            say(f"DISCARD {'WOULD REMOVE' if dry_run else 'REMOVE'} leftover {name}")
            if not dry_run:
                overwrite_and_remove(path, acl_script)


def orphans(folder: Path) -> list[Path]:
    """Temporary files an interrupted run may have left (they can hold the old or the new value)."""
    return [p for p in sorted(folder.iterdir()) if re.fullmatch(r"\.\.env\.(db|roles|test)\.(rot|restore)-\d+", p.name) and p.is_file()]


def say(message: str) -> None:
    print(message, flush=True)


def fail_at(point: str) -> None:
    if os.environ.get("ROT_TEST_FAIL_AT") == point:
        raise Refused(f"injected failure at {point}")


# ------------------------------------------------------------------------------------------------ reading
def read_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise Refused(f"{path.name}: missing or not a regular file")
    return path.read_bytes()


def decode(raw: bytes, name: str) -> tuple[str, bool]:
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw[3:].decode("utf-8") if bom else raw.decode("utf-8"), bom
    except UnicodeDecodeError:
        raise Refused(f"{name}: not UTF-8") from None


def split_value(rest: str) -> tuple[str, str]:
    """`value  # comment` -> (value, ' # comment')."""
    cut = rest.find(" #")
    if cut < 0:
        return rest, ""
    value = rest[:cut].rstrip()
    return value, rest[len(value):]  # the comment keeps the exact spacing before it


def password_of(env_text: str, name: str) -> str | None:
    for raw in env_text.splitlines():
        match = LINE.match(raw)
        if match and match.group(1) == name:
            return split_value(match.group(2))[0]
    return None


def read_old(source: Path) -> tuple[str, str]:
    """(administrator user, old password) from an env file with POSTGRES_USER and POSTGRES_PASSWORD."""
    text, _ = decode(read_bytes(source), source.name)
    user, password = password_of(text, "POSTGRES_USER"), password_of(text, "POSTGRES_PASSWORD")
    if not user or not password:
        raise Refused(f"{source.name}: POSTGRES_USER or POSTGRES_PASSWORD missing")
    return user, password


def read_new(path: Path, old: str) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024:
        raise Refused("the new-password file is missing, a link, or larger than 1 KB")
    for parent in [path.resolve().parent, *path.resolve().parents]:
        if (parent / ".git").exists():
            raise Refused("the new-password file is inside a Git repository: keep it outside")
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        raise Refused("the new-password file is UTF-16 (a PowerShell redirect does that): save it as UTF-8 or ASCII")
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        raise Refused("the new-password file is not UTF-8") from None
    if len(lines) != 1 or not NEW_VALUE.fullmatch(lines[0]):
        raise Refused("the new-password file must hold ONE line of 32 to 128 letters, digits, '-' or '_'")
    new = lines[0]
    if new == old or old in new or new in old:
        raise Refused("the new password equals or contains the old one")
    if any(marker in new.lower() for marker in ("change_me", "changeme", "password", "example", "secret")):
        raise Refused("the new password looks like a placeholder")
    return new


# ------------------------------------------------------------------------------------------------ transformation
def transform(name: str, text: str, admin: str, old: str, new: str) -> tuple[str, list[str]]:
    """New text of one file and the NAMES of the variables changed. Refuses on any ambiguity."""
    out: list[str] = []
    changed: list[str] = []
    for raw in text.splitlines(keepends=True):
        match = LINE.match(raw)
        if not match:
            out.append(raw)
            continue
        var, rest, eol = match.groups()
        value, comment = split_value(rest)
        if var == "POSTGRES_PASSWORD" and name == ADMIN_FILE:
            if value != old:
                raise Refused(f"{name}: POSTGRES_PASSWORD is not the value the plan was made from")
            out.append(f"{var}={new}{comment}{eol}")
            changed.append(var)
            continue
        if "://" in value and var.endswith("URL"):
            parts = urlsplit(value.strip("'\""))
            if unquote(parts.username or "") == admin:
                if value[:1] in "'\"":
                    raise Refused(f"{name}: {var} is quoted; unquote it first (the tools never edit quoted URLs)")
                if unquote(parts.password or "") != old:
                    raise Refused(f"{name}: {var} names the administrator with a different password")
                userinfo = parts.netloc.rsplit("@", 1)[0]
                user_part = userinfo.partition(":")[0]
                out.append(f"{var}={value.replace(userinfo + '@', user_part + ':' + quote(new, safe='') + '@', 1)}{comment}{eol}")
                changed.append(var)
                continue
        out.append(raw)
    return "".join(out), changed


def plan(folder: Path, new_file: Path, old_source: Path | None = None) -> tuple[str, str, str, dict[str, tuple[bytes, bytes, list[str]]]]:
    admin, old = read_old(old_source or folder / ADMIN_FILE)
    new = read_new(new_file, old)
    if folder.resolve() in new_file.resolve().parents:
        raise Refused("the new-password file is inside the env folder: keep it elsewhere")
    left = orphans(folder)
    if left:
        raise Refused(f"temporary files of an interrupted run are present ({', '.join(p.name for p in left)}): run 'rollback' first")
    result: dict[str, tuple[bytes, bytes, list[str]]] = {}
    for name in TARGETS:
        path = folder / name
        if not path.exists():
            if name == TEST_FILE:
                continue
            raise Refused(f"{name}: missing")
        raw = read_bytes(path)
        text, bom = decode(raw, name)
        new_text, changed = transform(name, text, admin, old, new)
        if name in (ADMIN_FILE, ROLES_FILE) and not changed:
            raise Refused(f"{name}: holds no administrator password to rotate")
        if holds_old(new_text, old):
            raise Refused(f"{name}: the old value would remain in a variable the tool does not rotate")
        if name == TEST_FILE and not changed:
            continue  # nothing to rotate there (an empty or unrelated file): it needs no backup copy, and a zero-byte copy could never be rolled back from
        encoded = (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8")
        result[name] = (raw, encoded, changed)
    if "ADMIN_DATABASE_URL" not in result[ROLES_FILE][2]:
        raise Refused(f"{ROLES_FILE}: ADMIN_DATABASE_URL is not the administrator of {ADMIN_FILE}")
    for other in sorted(os.listdir(folder)):
        path = folder / other
        watched = other.startswith(".env") and other not in TARGETS and other not in PRE_17B and not other.endswith(".example")
        if watched and path.is_file() and not path.is_symlink() and holds_old(path.read_bytes().decode("utf-8", errors="ignore"), old):
            raise Refused(f"{other}: another env file holds the old value; it would not be rotated")
    return admin, old, new, result


def restrict(acl_script: str | None, path: Path, rights: str) -> None:
    if os.name != "nt":
        os.chmod(path, 0o600)
        return
    if acl_script is None:
        return
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", acl_script, "-Path", str(path), "-Rights", rights],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise Refused(f"{path.name}: the owner-only descriptor could not be applied")


def remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------------------------------------ commands
def cmd_plan(folder: Path, new_file: Path) -> int:
    _, _, _, result = plan(folder, new_file)
    for name, (_, _, changed) in result.items():
        say(f"PLAN {name}: would update {len(changed)} variable(s): {', '.join(changed) or 'none'}; every other line kept byte for byte")
    other = [n for n in sorted(p.name for p in folder.glob(".env*")) if n not in TARGETS and n not in PRE_17B and not n.endswith(".example")]
    say(f"PLAN other env files in the folder (not touched): {other or 'none'}")
    say("PLAN OK: nothing written")
    return 0


def cmd_apply(folder: Path, new_file: Path, backup_dir: Path, acl_script: str | None) -> int:
    require_acl(acl_script)
    for parent in [backup_dir.resolve(), *backup_dir.resolve().parents]:
        if (parent / ".git").exists() or parent == folder.resolve():
            raise Refused("the backup folder must be outside the repository and outside the env folder")
    if backup_dir.exists() and any(backup_dir.iterdir()):
        raise Refused("the backup folder is not empty; not overwriting")
    _, old, new, result = plan(folder, new_file)
    held = [n for n in PRE_17B if (folder / n).is_file() and holds_old((folder / n).read_bytes().decode("utf-8", errors="ignore"), old)]
    if held:
        say(f"NOTE recovery copies that keep the old value (the file-level rollback material; dead after the database change, not rotated): {', '.join(held)}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    acquire_lock(backup_dir)
    if [p for p in backup_dir.iterdir() if p.name != LOCK_NAME]:
        release_lock(backup_dir)
        raise Refused("the backup folder is not empty; not overwriting")
    if os.environ.get("ROT_TEST_HOLD_LOCK_SECONDS"):
        import time

        time.sleep(float(os.environ["ROT_TEST_HOLD_LOCK_SECONDS"]))  # test hook: keeps the lock long enough for a concurrent run to collide
    temps: list[Path] = []
    replaced: list[str] = []
    replacing = False  # once true every backup copy is complete and verified: restore ALL targets (idempotent)
    try:
        for name, (raw, _, _) in result.items():
            write_backup_copy(backup_dir, name, raw, acl_script)
        write_marker(backup_dir, {n: v[0] for n, v in result.items()}, acl_script)  # only now may a rollback trust the copies
        say(f"BACKUP {len(result)} original file(s) copied to the backup folder (owner-only); {', '.join(result)}")
        fail_at("temp")
        for name, (_, encoded, _) in result.items():
            temp = folder / f".{name}.rot-{os.getpid()}"
            temps.append(temp)
            temp.write_bytes(b"")
            restrict(acl_script, temp, "Modify")
            with open(temp, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if temp.read_bytes() != encoded:
                raise Refused(f"{name}: the temporary file differs from the intended content")
        replacing = True
        for index, name in enumerate(result, start=1):
            fail_at(f"replace{index}")
            os.replace(folder / f".{name}.rot-{os.getpid()}", folder / name)
            if os.environ.get("ROT_TEST_FAIL_AT") == f"interruptmid{index}":
                raise KeyboardInterrupt  # the window between the replacement and its bookkeeping
            replaced.append(name)
            restrict(acl_script, folder / name, "Modify")
            if os.environ.get("ROT_TEST_FAIL_AT") == f"interrupt{index}":
                raise KeyboardInterrupt
        fail_at("verify")
        post_check(folder, result, old, new)
        say(f"APPLY OK: {', '.join(result)} updated and re-read; the old value is gone from them")
        return 0
    except BaseException as exc:  # an interruption must restore the files too
        say(f"APPLY FAILED ({type(exc).__name__}: {exc if isinstance(exc, Refused) else 'file operation failed or interrupted'}); restoring")
        bad = restore(folder, backup_dir, list(result) if replacing else replaced, acl_script, {n: v[0] for n, v in result.items()})
        say("ROLLBACK COMPLETE: every replaced file restored byte for byte" if bad == 0 else f"ROLLBACK INCOMPLETE: {bad} file(s) differ from their backup")
        if isinstance(exc, KeyboardInterrupt):
            return 130 if bad == 0 else 3
        if not isinstance(exc, Exception):
            raise
        return 1 if bad == 0 else 3
    finally:
        for temp in temps:
            remove_quietly(temp)
        release_lock(backup_dir)


def post_check(folder: Path, result: dict[str, tuple[bytes, bytes, list[str]]], old: str, new: str) -> None:
    for name, (raw, encoded, changed) in result.items():
        now = read_bytes(folder / name)
        if now != encoded:
            raise Refused(f"{name}: the file on disk is not the intended content")
        text, _ = decode(now, name)
        if holds_old(text, old):
            raise Refused(f"{name}: the old value is still present")
        if changed and new not in text:
            raise Refused(f"{name}: the new value is missing")
        before = decode(raw, name)[0].splitlines()
        after = text.splitlines()
        if len(before) != len(after):
            raise Refused(f"{name}: the number of lines changed")
        untouched = [(a, b) for a, b in zip(before, after, strict=True) if not any(a.startswith(v + "=") for v in changed)]
        if any(a != b for a, b in untouched):
            raise Refused(f"{name}: a line outside the rotated variables changed")


def restore(folder: Path, backup_dir: Path, replaced: list[str], acl_script: str | None, verified: dict[str, bytes] | None = None) -> int:
    """Put the originals back. `verified` holds bytes already checked (digest, or the in-memory originals): they are used instead of re-reading the `.old` file."""
    bad = 0
    for name in replaced:
        try:
            raw = (verified or {})[name]  # only bytes that were verified (a digest, or the in-memory originals) are ever written back; a name without them is a bug and counts as a failure
            temp = folder / f".{name}.restore-{os.getpid()}"
            temp.write_bytes(b"")
            restrict(acl_script, temp, "Modify")
            with open(temp, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, folder / name)
            restrict(acl_script, folder / name, "Modify")
            if (folder / name).read_bytes() != raw:
                bad += 1
        except (OSError, Refused, KeyError):
            bad += 1
    for left in orphans(folder):
        remove_quietly(left)
    return bad


def cmd_rollback(folder: Path, backup_dir: Path, acl_script: str | None) -> int:
    require_acl(acl_script)
    contents = check_backup(backup_dir, TARGETS)
    present = list(contents)
    bad = restore(folder, backup_dir, present, acl_script, contents)
    say("ROLLBACK COMPLETE (orphan temporary files removed)" if bad == 0 else f"ROLLBACK INCOMPLETE: {bad} file(s)")
    return 0 if bad == 0 else 3


def verify_state(folder: Path, new_file: Path, old_source: Path) -> list[str]:
    admin, old = read_old(old_source)
    try:
        new_lines = new_file.read_bytes().decode("utf-8-sig").splitlines() if new_file.is_file() else []
    except UnicodeDecodeError:
        new_lines = []
    new = new_lines[0] if len(new_lines) == 1 else ""
    problems: list[str] = []
    if not NEW_VALUE.fullmatch(new):
        problems.append("the new-password file is unreadable or malformed")
    live = [folder / n for n in sorted(os.listdir(folder)) if n.startswith(".env") and not n.endswith(".example") and n not in PRE_17B]
    for path in live:
        if path.is_symlink() or not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", errors="ignore")
        if holds_old(text, old):
            problems.append(f"{path.name}: still holds the old value")
    cur_user, cur_pw = (None, None)
    try:
        cur_user, cur_pw = read_old(folder / ADMIN_FILE)
    except Refused as exc:
        problems.append(str(exc))
    if cur_pw is not None and cur_pw != new:
        problems.append(f"{ADMIN_FILE}: POSTGRES_PASSWORD is not the new value")
    if cur_user is not None and cur_user != admin:
        problems.append(f"{ADMIN_FILE}: POSTGRES_USER changed")
    test_file = folder / TEST_FILE
    if test_file.is_file():
        for raw_line in decode(test_file.read_bytes(), TEST_FILE)[0].splitlines():
            match = LINE.match(raw_line)
            if match and "://" in match.group(2) and match.group(1).endswith("URL"):
                parts = urlsplit(split_value(match.group(2))[0])
                if unquote(parts.username or "") == admin and unquote(parts.password or "") != new:
                    problems.append(f"{TEST_FILE}: {match.group(1)} names the administrator without the new value")
    left = orphans(folder)
    if left:
        problems.append(f"temporary files of an interrupted run are present: {', '.join(p.name for p in left)}")
    roles = folder / ROLES_FILE
    if roles.is_file():
        url = password_of(decode(roles.read_bytes(), ROLES_FILE)[0], "ADMIN_DATABASE_URL")
        parts = urlsplit(url or "")
        if unquote(parts.password or "") != new:
            problems.append(f"{ROLES_FILE}: ADMIN_DATABASE_URL does not carry the new value")
    else:
        problems.append(f"{ROLES_FILE}: missing")
    return problems


def cmd_verify(folder: Path, new_file: Path, old_source: Path) -> int:
    problems = verify_state(folder, new_file, old_source)
    pre = [n for n in PRE_17B if (folder / n).exists()]
    say(f"VERIFY pre-17b copies still present (they hold the old value until cleanup): {pre or 'none'}")
    if problems:
        for problem in problems:
            say(f"VERIFY FAIL {problem}")
        return 1
    say("VERIFY OK: the new value is in .env.db and .env.roles, the old one in no live env file")
    return 0


def overwrite_and_remove(path: Path, acl_script: str | None = None) -> bool:
    """Best effort: grant Modify, overwrite with zeros, delete. True when the file is gone."""
    try:
        restrict(acl_script, path, "Modify")
        size = path.stat().st_size
        with open(path, "r+b") as handle:
            handle.write(b"\0" * size)
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, Refused):
        pass  # not overwritten; the deletion below still tries
    try:
        path.unlink()
    except OSError:
        return False
    return True


def cmd_discard(folder: Path, new_file: Path, old_source: Path, backup_dir: Path, dry_run: bool, acl_script: str | None) -> int:
    """Remove ONLY the `*.old` backup copies of this rotation (they hold the old, by then dead, value); never a `*.pre-17b` copy."""
    if not dry_run:
        require_acl(acl_script)
    problems = verify_state(folder, new_file, old_source)
    if problems:
        for problem in problems:
            say(f"DISCARD REFUSED {problem}")
        return 1
    order = (TEST_FILE, ROLES_FILE, ADMIN_FILE)  # .env.db.old is the --old-from source of a re-run: it goes last and stays if anything is stuck
    copies = [backup_dir / (n + ".old") for n in order if (backup_dir / (n + ".old")).is_file() and not (backup_dir / (n + ".old")).is_symlink()]
    stuck: list[str] = []
    for path in copies:
        if stuck and path.name == ADMIN_FILE + ".old":
            say(f"DISCARD KEEP {path.name} so that the discard can be run again")
            continue
        say(f"DISCARD {'WOULD REMOVE' if dry_run else 'REMOVE'} {path.name}")
        if not dry_run and not overwrite_and_remove(path, acl_script):
            stuck.append(path.name)
    if not stuck:
        remove_leftovers(backup_dir, order, dry_run, acl_script)
    if not dry_run and not stuck:
        (backup_dir / BACKUP_MARK).unlink(missing_ok=True)
    if not dry_run:
        try:
            backup_dir.rmdir()
        except OSError:
            say("DISCARD backup folder kept (it holds other files)")
    if stuck:
        say(f"DISCARD INCOMPLETE: {', '.join(stuck)} could not be removed")
        return 1
    say(f"DISCARD OK: {len(copies)} backup copy(ies) {'would be ' if dry_run else ''}removed; the *.pre-17b copies were not touched")
    return 0


def cmd_cleanup(folder: Path, new_file: Path, old_source: Path, backup_dir: Path | None, dry_run: bool, acl_script: str | None = None) -> int:
    if not dry_run:
        require_acl(acl_script)
    problems = verify_state(folder, new_file, old_source)
    if problems:
        for problem in problems:
            say(f"CLEANUP REFUSED {problem}")
        return 1
    _, old = read_old(old_source)
    targets: list[Path] = []
    for name in PRE_17B:
        path = folder / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise Refused(f"{name}: a link or not a regular file; not touching it")
        text = path.read_bytes().decode("utf-8", errors="ignore")
        is_marker = name.endswith("absent-before-17b")
        if not is_marker and not holds_old(text, old):
            say(f"CLEANUP KEEP {name}: does not hold the old value (not recognised as the exposed copy)")
            continue
        targets.append(path)
    stuck: list[str] = []
    for path in targets:
        say(f"CLEANUP {'WOULD REMOVE' if dry_run else 'REMOVE'} {path.name}")
        if not dry_run and not overwrite_and_remove(path, acl_script):
            stuck.append(path.name)
            say(f"CLEANUP NOT REMOVED {path.name}: the file could not be deleted (permissions); fix and run cleanup again")
    # the backup copies go LAST and only when nothing is stuck: `.env.db.old` is what a re-run reads the old value from
    if backup_dir is not None:
        backups = [backup_dir / (n + ".old") for n in TARGETS if (backup_dir / (n + ".old")).is_file() and not (backup_dir / (n + ".old")).is_symlink()]
        if stuck:
            say(f"CLEANUP KEEP the {len(backups)} backup copy(ies) so that the clean-up can be run again")
            backups = []
        for path in backups:
            say(f"CLEANUP {'WOULD REMOVE' if dry_run else 'REMOVE'} {path.name}")
            if not dry_run and not overwrite_and_remove(path, acl_script):
                stuck.append(path.name)
                say(f"CLEANUP NOT REMOVED {path.name}: the file could not be deleted (permissions); fix and run cleanup again")
        targets = [*targets, *backups]
    if backup_dir is not None and not dry_run:
        if not stuck:
            remove_leftovers(backup_dir, TARGETS, False, acl_script)
            (backup_dir / BACKUP_MARK).unlink(missing_ok=True)
        try:
            backup_dir.rmdir()
        except OSError:
            say("CLEANUP backup folder kept (it holds other files)")
    left = [n for n in PRE_17B if (folder / n).exists()]
    if stuck:
        say(f"CLEANUP INCOMPLETE: {len(stuck)} file(s) could not be removed: {', '.join(stuck)}")
        return 1
    say(f"CLEANUP OK: {len(targets)} file(s) {'would be ' if dry_run else ''}removed; pre-17b names still present: {left or 'none'}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["plan", "apply", "verify", "rollback", "cleanup", "discard"])
    parser.add_argument("folder")
    parser.add_argument("--new-file")
    parser.add_argument("--backup-dir")
    parser.add_argument("--old-from")
    parser.add_argument("--acl-script")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--i-know-this-removes-the-only-file-rollback", dest="ack_cleanup", action="store_true", help="required for a real cleanup, which removes the *.pre-17b copies")
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    if not folder.is_dir():
        say("folder missing")
        return 2
    new_file = Path(args.new_file) if args.new_file else None
    backup = Path(args.backup_dir) if args.backup_dir else None
    old_from = Path(args.old_from) if args.old_from else None
    try:
        if args.command == "plan" and new_file:
            return cmd_plan(folder, new_file)
        if args.command == "apply" and new_file and backup:
            return cmd_apply(folder, new_file, backup, args.acl_script)
        if args.command == "verify" and new_file and old_from:
            return cmd_verify(folder, new_file, old_from)
        if args.command == "rollback" and backup:
            return cmd_rollback(folder, backup, args.acl_script)
        if args.command == "discard" and new_file and old_from and backup:
            return cmd_discard(folder, new_file, old_from, backup, args.dry_run, args.acl_script)
        if args.command == "cleanup" and new_file and old_from:
            if not args.dry_run and not args.ack_cleanup:
                raise Refused("cleanup removes the *.pre-17b copies, the only tested file-level rollback (NO-GO in the 17B plan): a real run needs --i-know-this-removes-the-only-file-rollback")
            return cmd_cleanup(folder, new_file, old_from, backup, args.dry_run, args.acl_script)
    except Refused as exc:
        say(f"REFUSED {exc}")
        return 1
    except KeyboardInterrupt:
        say("INTERRUPTED: if an apply was running run rollback (the backup marker exists once the live files may be touched); if a rollback or discard was running run it again (both are safe to repeat)")
        return 130
    except OSError as exc:
        say(f"FAILED a file operation failed ({type(exc).__name__}); nothing secret is shown")
        return 1
    except Exception as exc:  # a parser error (urlsplit, decode) can echo the offending value: type only, never a traceback
        say(f"FAILED unexpected {type(exc).__name__}; no detail is shown because it could contain a secret")
        return 1
    say("missing argument for this command")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
