"""Self-test of secure_file_acl.ps1 on throw-away files (Windows only). Prints PASS/FAIL lines and no path."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).with_name("secure_file_acl.ps1")
FAILURES = 0


def check(label: str, condition: bool) -> None:
    global FAILURES
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        FAILURES += 1


def tool(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOL), *args],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def ps(command: str) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True).stdout.strip()


def descriptor(path: Path) -> tuple[bool, int, str]:
    """Independent reading: protected?, number of rules, 'sid|type|rights' of the first rule."""
    out = ps(
        f"$a = Get-Acl -LiteralPath '{path}'; $r = @($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]));"
        " Write-Output $a.AreAccessRulesProtected; Write-Output $r.Count;"
        " if ($r.Count -gt 0) { Write-Output ($r[0].IdentityReference.Value + '|' + $r[0].AccessControlType + '|' + [int]$r[0].FileSystemRights) }"
    ).splitlines()
    return out[0] == "True", int(out[1]), (out[2] if len(out) > 2 else "")


def reset(path: Path) -> None:
    subprocess.run(["icacls", str(path), "/reset"], capture_output=True)


def main() -> int:
    if os.name != "nt":
        print("SKIP: Windows only")
        return 0
    my_sid = ps("[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
    read_rights = 1179785  # FileSystemRights.Read | Synchronize, as Windows stores an Allow Read rule
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        target = folder / "backup.dump"
        target.write_bytes(b"not a real dump")
        protected, count, _ = descriptor(target)
        check("a fresh file inherits several rules (the problem to fix)", not protected and count > 1)

        code, out = tool("-Path", str(target))
        check("apply succeeds and reports ACL OK", code == 0 and "ACL OK backup.dump" in out)
        check("the output names the file only, never its folder", raw not in out and str(folder.parent) not in out)
        protected, count, first = descriptor(target)
        check("independent reading: inheritance disabled, exactly one rule", protected and count == 1)
        check("that rule is Allow Read for the current user's SID", first == f"{my_sid}|Allow|{read_rights}")
        try:
            with target.open("ab") as handle:
                handle.write(b"x")
            writable = True
        except PermissionError:
            writable = False
        check("the effective permission is read only: the owner itself cannot write the file", not writable)
        check("the file is still readable", target.read_bytes() == b"not a real dump")

        code, out = tool("-Path", str(target), "-VerifyOnly")
        check("verify-only passes on a correct descriptor", code == 0 and "verified" in out and "applied" not in out)

        # a rule for Everyone is added behind the tool's back: verify-only must fail closed, apply must remove it
        subprocess.run(["icacls", str(target), "/grant", "*S-1-1-0:(R)"], capture_output=True)
        code, out = tool("-Path", str(target), "-VerifyOnly")
        check("verify-only fails (exit 1) when another identity has access", code == 1 and "ACL FAIL" in out and "found 2" in out and "another identity" in out)
        code, out = tool("-Path", str(target))
        protected, count, first = descriptor(target)
        check("apply removes the foreign rule and verifies again", code == 0 and count == 1 and first.startswith(my_sid))

        # inheritance re-enabled behind the tool's back
        subprocess.run(["icacls", str(target), "/inheritance:e"], capture_output=True)
        code, out = tool("-Path", str(target), "-VerifyOnly")
        check("verify-only fails when inheritance is enabled again", code == 1 and "inheritance" in out)

        code, out = tool("-Path", str(folder / "absent.dump"))
        check("a missing file is exit 2 and reported, not created", code == 2 and "missing" in out and not (folder / "absent.dump").exists())
        code, out = tool("-Path", str(folder), "-VerifyOnly")
        check("a directory is refused (exit 2)", code == 2 and "not a regular file" in out)
        reset(target)
    print(f"{FAILURES} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
