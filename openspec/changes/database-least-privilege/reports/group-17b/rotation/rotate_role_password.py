"""Rotate the password of ONE restricted database role in the env FILES (SEC-17B-01: `asistente_migrator`). Names and verdicts only; never a value.

    python rotate_role_password.py plan     <backend folder> --new-file <file>
    python rotate_role_password.py apply    <backend folder> --new-file <file> --backup-dir <dir> [--acl-script <secure_file_acl.ps1>]
    python rotate_role_password.py verify   <backend folder> --new-file <file> --old-from <backup>/.env.roles.old
    python rotate_role_password.py rollback <backend folder> --backup-dir <dir>
    python rotate_role_password.py discard  <backend folder> --new-file <file> --old-from <backup>/.env.roles.old --backup-dir <dir> [--dry-run]

Scope (profile `migrator`): `.env.roles` (DB_MIGRATOR_PASSWORD) and `.env.migrate` (every URL variable whose user is `asistente_migrator`,
today MIGRATION_DATABASE_URL). The database side is `rotate_db_role.py alter --role asistente_migrator`; nothing here talks to the server.
It reuses the checks and the atomic write/restore pattern of `rotate_admin_password.py` (same new-value format, same refusals) and differs
in the files, the variables, the temporary-file names and the old-value source (DB_MIGRATOR_PASSWORD of `.env.roles`, which must agree with
the URL of `.env.migrate`). No other env file may hold the old value (plan refuses; the `*.pre-17b` copies predate the roles and are only reported).
`discard` removes the two `*.old` backup copies (they hold the OLD, dead value) after `verify` is clean; it never touches `*.pre-17b`.
Exit codes: 0 ok, 1 refused or failed (nothing changed, or everything restored), 2 usage or missing file, 3 rollback incomplete, 130 interrupted (restored).
Test hook: ROT_TEST_FAIL_AT=<temp|replace1|replace2|verify|interrupt1|interrupt2|interruptmid1> makes the tool fail at that point (it can only make it fail).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

_spec = importlib.util.spec_from_file_location("rotate_admin_password", Path(__file__).with_name("rotate_admin_password.py"))
if _spec is None or _spec.loader is None:
    raise SystemExit("cannot load rotate_admin_password.py from the same folder")
base = importlib.util.module_from_spec(_spec)
sys.modules["rotate_admin_password"] = base
_spec.loader.exec_module(base)

Refused, say, fail_at, decode, read_bytes, split_value, holds_old, restrict, remove_quietly, read_new, LINE = (
    base.Refused, base.say, base.fail_at, base.decode, base.read_bytes, base.split_value, base.holds_old, base.restrict,
    base.remove_quietly, base.read_new, base.LINE,
)

ROLE = "asistente_migrator"
PASSWORD_FILE, URL_FILE = ".env.roles", ".env.migrate"
PASSWORD_VAR = "DB_MIGRATOR_PASSWORD"  # noqa: S105 - a variable NAME, not a value
TARGETS = (PASSWORD_FILE, URL_FILE)
PRE_17B = base.PRE_17B


def require_acl(acl_script: str | None) -> None:
    """On Windows the temporary files and backup copies hold secrets: without the owner-only descriptor script the tool refuses."""
    if os.name == "nt" and acl_script is None and os.environ.get("ROT_TEST_NO_ACL") != "1":
        raise Refused("on Windows --acl-script is required (the temporary files and backup copies must be owner-only)")


def orphans(folder: Path) -> list[Path]:
    return [p for p in sorted(folder.iterdir()) if re.fullmatch(r"\.\.env\.(roles|migrate)\.(rot|restore)-\d+", p.name) and p.is_file()]


def role_url_vars(text: str) -> list[tuple[str, str]]:
    """(variable, value) of every URL variable whose user is the role."""
    found = []
    for raw in text.splitlines():
        match = LINE.match(raw)
        if match and "://" in match.group(2) and match.group(1).endswith("URL"):
            value = split_value(match.group(2))[0]
            if unquote(urlsplit(value.strip("'\"")).username or "") == ROLE:
                found.append((match.group(1), value))
    return found


def old_of(text: str) -> str | None:
    value: str | None = base.password_of(text, PASSWORD_VAR)
    return value


def transform(name: str, text: str, old: str, new: str) -> tuple[str, list[str]]:
    out: list[str] = []
    changed: list[str] = []
    for raw in text.splitlines(keepends=True):
        match = LINE.match(raw)
        if not match:
            out.append(raw)
            continue
        var, rest, eol = match.groups()
        value, comment = split_value(rest)
        if name == PASSWORD_FILE and var == PASSWORD_VAR:
            if value != old:
                raise Refused(f"{name}: {PASSWORD_VAR} is not the value the plan was made from")
            out.append(f"{var}={new}{comment}{eol}")
            changed.append(var)
            continue
        if "://" in value and var.endswith("URL"):
            parts = urlsplit(value.strip("'\""))
            if unquote(parts.username or "") == ROLE:
                if value[:1] in "'\"":
                    raise Refused(f"{name}: {var} is quoted; unquote it first (the tools never edit quoted URLs)")
                if unquote(parts.password or "") != old:
                    raise Refused(f"{name}: {var} names the role with a different password")
                userinfo = parts.netloc.rsplit("@", 1)[0]
                user_part = userinfo.partition(":")[0]
                out.append(f"{var}={value.replace(userinfo + '@', user_part + ':' + quote(new, safe='') + '@', 1)}{comment}{eol}")
                changed.append(var)
                continue
        out.append(raw)
    return "".join(out), changed


def plan(folder: Path, new_file: Path) -> tuple[str, str, dict[str, tuple[bytes, bytes, list[str]]]]:
    roles_text, _ = decode(read_bytes(folder / PASSWORD_FILE), PASSWORD_FILE)
    old = old_of(roles_text)
    if not old:
        raise Refused(f"{PASSWORD_FILE}: {PASSWORD_VAR} missing or empty")
    new = read_new(new_file, old)
    if folder.resolve() in new_file.resolve().parents:
        raise Refused("the new-password file is inside the env folder: keep it elsewhere")
    left = orphans(folder)
    if left:
        raise Refused(f"temporary files of an interrupted run are present ({', '.join(p.name for p in left)}): run 'rollback' first")
    result: dict[str, tuple[bytes, bytes, list[str]]] = {}
    for name in TARGETS:
        raw = read_bytes(folder / name)
        text, bom = decode(raw, name)
        new_text, changed = transform(name, text, old, new)
        if not changed:
            raise Refused(f"{name}: holds no password of {ROLE} to rotate")
        if holds_old(new_text, old):
            raise Refused(f"{name}: the old value would remain in a variable the tool does not rotate")
        result[name] = (raw, (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8"), changed)
    if PASSWORD_VAR not in result[PASSWORD_FILE][2] or not role_url_vars(decode(result[URL_FILE][0], URL_FILE)[0]):
        raise Refused(f"{URL_FILE} or {PASSWORD_FILE} does not describe {ROLE}")
    for other in sorted(os.listdir(folder)):
        path = folder / other
        watched = other.startswith(".env") and other not in TARGETS and other not in PRE_17B and not other.endswith(".example")
        if watched and path.is_file() and not path.is_symlink() and holds_old(path.read_bytes().decode("utf-8", errors="ignore"), old):
            raise Refused(f"{other}: another env file holds the old value; it would not be rotated")
    return old, new, result


def cmd_plan(folder: Path, new_file: Path) -> int:
    _, _, result = plan(folder, new_file)
    for name, (_, _, changed) in result.items():
        say(f"PLAN {name}: would update {len(changed)} variable(s): {', '.join(changed)}; every other line kept byte for byte")
    held = [n for n in PRE_17B if (folder / n).is_file() and holds_old((folder / n).read_bytes().decode("utf-8", errors="ignore"), plan_old(folder))]
    say(f"PLAN pre-17b copies holding the old value (expected none: they predate the roles): {held or 'none'}")
    say("PLAN OK: nothing written")
    return 0


def plan_old(folder: Path) -> str:
    return old_of(decode(read_bytes(folder / PASSWORD_FILE), PASSWORD_FILE)[0]) or ""


def restore(folder: Path, backup_dir: Path, replaced: list[str], acl_script: str | None) -> int:
    bad = 0
    for name in replaced:
        try:
            raw = (backup_dir / (name + ".old")).read_bytes()
            temp = folder / f".{name}.restore-{os.getpid()}"
            temp.write_bytes(b"")
            restrict(acl_script, temp, "Modify")
            temp.write_bytes(raw)
            os.replace(temp, folder / name)
            restrict(acl_script, folder / name, "Modify")
            if (folder / name).read_bytes() != raw:
                bad += 1
        except (OSError, Refused):
            bad += 1
    for left in orphans(folder):
        remove_quietly(left)
    return bad


def cmd_apply(folder: Path, new_file: Path, backup_dir: Path, acl_script: str | None) -> int:
    require_acl(acl_script)
    for parent in [backup_dir.resolve(), *backup_dir.resolve().parents]:
        if (parent / ".git").exists() or parent == folder.resolve():
            raise Refused("the backup folder must be outside the repository and outside the env folder")
    if backup_dir.exists() and any(backup_dir.iterdir()):
        raise Refused("the backup folder is not empty; not overwriting")
    old, new, result = plan(folder, new_file)
    held = [n for n in PRE_17B if (folder / n).is_file() and holds_old((folder / n).read_bytes().decode("utf-8", errors="ignore"), old)]
    if held:
        say(f"NOTE pre-17b copies holding the old value (not rotated; dead after the database change): {', '.join(held)}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    temps: list[Path] = []
    replaced: list[str] = []
    replacing = False  # once true every backup copy is complete and verified: restore ALL targets (idempotent), even one whose os.replace was interrupted
    try:
        for name, (raw, _, _) in result.items():
            copy = backup_dir / (name + ".old")
            copy.write_bytes(b"")
            restrict(acl_script, copy, "Modify")
            copy.write_bytes(raw)
            if copy.read_bytes() != raw:
                raise Refused(f"{name}: the backup copy differs from the original")
            restrict(acl_script, copy, "Read")
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
        base.post_check(folder, result, old, new)
        say(f"APPLY OK: {', '.join(result)} updated and re-read; the old value is gone from them")
        return 0
    except BaseException as exc:  # an interruption must restore the files too
        say(f"APPLY FAILED ({type(exc).__name__}: {exc if isinstance(exc, Refused) else 'file operation failed or interrupted'}); restoring")
        bad = restore(folder, backup_dir, list(result) if replacing else replaced, acl_script)
        say("ROLLBACK COMPLETE: every replaced file restored byte for byte" if bad == 0 else f"ROLLBACK INCOMPLETE: {bad} file(s) differ from their backup")
        if isinstance(exc, KeyboardInterrupt):
            return 130 if bad == 0 else 3
        if not isinstance(exc, Exception):
            raise
        return 1 if bad == 0 else 3
    finally:
        for temp in temps:
            remove_quietly(temp)


def cmd_rollback(folder: Path, backup_dir: Path, acl_script: str | None) -> int:
    require_acl(acl_script)
    present = [n for n in TARGETS if (backup_dir / (n + ".old")).is_file()]
    if not present:
        raise Refused("the backup folder holds no original file")
    bad = restore(folder, backup_dir, present, acl_script)
    say("ROLLBACK COMPLETE (orphan temporary files removed)" if bad == 0 else f"ROLLBACK INCOMPLETE: {bad} file(s)")
    return 0 if bad == 0 else 3


def verify_state(folder: Path, new_file: Path, old_source: Path) -> list[str]:
    old = old_of(decode(read_bytes(old_source), old_source.name)[0])
    if not old:
        raise Refused(f"{old_source.name}: {PASSWORD_VAR} missing")
    try:
        lines = new_file.read_bytes().decode("utf-8-sig").splitlines() if new_file.is_file() else []
    except UnicodeDecodeError:
        lines = []
    new = lines[0] if len(lines) == 1 else ""
    problems: list[str] = []
    if not base.NEW_VALUE.fullmatch(new):
        problems.append("the new-password file is unreadable or malformed")
    for path in (folder / n for n in sorted(os.listdir(folder)) if n.startswith(".env") and not n.endswith(".example") and n not in PRE_17B):
        if not path.is_symlink() and path.is_file() and holds_old(path.read_bytes().decode("utf-8", errors="ignore"), old):
            problems.append(f"{path.name}: still holds the old value")
    try:
        if old_of(decode(read_bytes(folder / PASSWORD_FILE), PASSWORD_FILE)[0]) != new:
            problems.append(f"{PASSWORD_FILE}: {PASSWORD_VAR} is not the new value")
        urls = role_url_vars(decode(read_bytes(folder / URL_FILE), URL_FILE)[0])
        if not urls:
            problems.append(f"{URL_FILE}: no URL names {ROLE}")
        for var, value in urls:
            if unquote(urlsplit(value).password or "") != new:
                problems.append(f"{URL_FILE}: {var} does not carry the new value")
    except Refused as exc:
        problems.append(str(exc))
    left = orphans(folder)
    if left:
        problems.append(f"temporary files of an interrupted run are present: {', '.join(p.name for p in left)}")
    return problems


def cmd_verify(folder: Path, new_file: Path, old_source: Path) -> int:
    problems = verify_state(folder, new_file, old_source)
    if problems:
        for problem in problems:
            say(f"VERIFY FAIL {problem}")
        return 1
    say(f"VERIFY OK: the new value is in {PASSWORD_FILE} and {URL_FILE}, the old one in no live env file")
    return 0


def cmd_discard(folder: Path, new_file: Path, old_source: Path, backup_dir: Path, dry_run: bool, acl_script: str | None) -> int:
    if not dry_run:
        require_acl(acl_script)
    problems = verify_state(folder, new_file, old_source)
    if problems:
        for problem in problems:
            say(f"DISCARD REFUSED {problem}")
        return 1
    copies = [backup_dir / (n + ".old") for n in (URL_FILE, PASSWORD_FILE) if (backup_dir / (n + ".old")).is_file() and not (backup_dir / (n + ".old")).is_symlink()]
    stuck: list[str] = []
    for path in copies:  # .env.roles.old is the --old-from source of a re-run: it goes last and stays if anything is stuck
        if stuck and path.name == PASSWORD_FILE + ".old":
            say(f"DISCARD KEEP {path.name} so that the discard can be run again")
            continue
        say(f"DISCARD {'WOULD REMOVE' if dry_run else 'REMOVE'} {path.name}")
        if not dry_run and not base.overwrite_and_remove(path, acl_script):
            stuck.append(path.name)
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["plan", "apply", "verify", "rollback", "discard"])
    parser.add_argument("folder")
    parser.add_argument("--new-file")
    parser.add_argument("--backup-dir")
    parser.add_argument("--old-from")
    parser.add_argument("--acl-script")
    parser.add_argument("--dry-run", action="store_true")
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
    except Refused as exc:
        say(f"REFUSED {exc}")
        return 1
    except OSError as exc:
        say(f"FAILED a file operation failed ({type(exc).__name__}); nothing secret is shown")
        return 1
    except Exception as exc:  # a parser error (urlsplit, decode) can echo the offending value: show the type only, never a traceback
        say(f"FAILED unexpected {type(exc).__name__}; no detail is shown because it could contain a secret")
        return 1
    say("missing argument for this command")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
