"""Self-test of secure_folder_acl.ps1 on a throw-away folder (Windows only): policy, lifecycle of a copy, fail closed."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
FOLDER_TOOL = HERE / "secure_folder_acl.ps1"
FILE_TOOL = HERE / "secure_file_acl.ps1"
FAILURES = 0


def check(label: str, condition: bool) -> None:
    global FAILURES
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        FAILURES += 1


def tool(script: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def ps(command: str) -> str:
    return subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True).stdout.strip()


def rules(path: Path) -> list[str]:
    """Independent reading: 'sid|type|rights|inheritance|inherited' per rule, plus 'protected=<bool>' first."""
    out = ps(
        f"$a = Get-Acl -LiteralPath '{path}'; Write-Output ('protected=' + $a.AreAccessRulesProtected);"
        " foreach ($r in $a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]))"
        " { Write-Output ($r.IdentityReference.Value + '|' + $r.AccessControlType + '|' + [int]$r.FileSystemRights + '|' + $r.InheritanceFlags + '|' + $r.IsInherited) }"
    )
    return out.splitlines()


def main() -> int:
    if os.name != "nt":
        print("SKIP: Windows only")
        return 0
    my_sid = ps("[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value")
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw) / "Backups-synthetic"
        folder.mkdir()
        before = rules(folder)
        check("a fresh folder inherits its rules from the profile (the state to replace)", before[0] == "protected=False" and len(before) > 1)

        code, out = tool(FOLDER_TOOL, "-Path", str(folder))
        check("apply succeeds and reports FOLDER ACL OK", code == 0 and "FOLDER ACL OK Backups-synthetic" in out)
        check("the output names the folder only", raw not in out)
        after = rules(folder)
        check("independent reading: inheritance disabled and exactly 3 explicit rules", after[0] == "protected=True" and len(after) == 4 and all(r.endswith("|False") for r in after[1:]))
        check("SYSTEM and Administrators keep Full Control with inheritance to subfolders and files", any(r.startswith("S-1-5-18|Allow|2032127|ContainerInherit, ObjectInherit") for r in after) and any(r.startswith("S-1-5-32-544|Allow|2032127|ContainerInherit, ObjectInherit") for r in after))
        check("the current user has Modify + DeleteSubdirectoriesAndFiles, not Full Control", any(r.startswith(f"{my_sid}|Allow|1245695|ContainerInherit, ObjectInherit") for r in after))
        code, out = tool(FOLDER_TOOL, "-Path", str(folder), "-VerifyOnly")
        check("verify-only passes on the applied policy", code == 0 and "verified" in out and "applied" not in out)

        # lifecycle of a synthetic copy: create, read, restrict, verify, delete (controlled)
        copy = folder / "synthetic.dump"
        copy.write_bytes(b"synthetic")
        check("a copy can be created in the folder", copy.is_file())
        code, out = tool(FILE_TOOL, "-Path", str(copy))
        check("the copy can be restricted to Read with secure_file_acl.ps1", code == 0 and "ACL OK synthetic.dump" in out)
        check("the restricted copy is still readable", copy.read_bytes() == b"synthetic")
        try:
            copy.write_bytes(b"x")
            overwritten = True
        except PermissionError:
            overwritten = False
        check("the restricted copy cannot be overwritten by its owner", not overwritten)
        try:
            copy.unlink()
            deleted = True
        except PermissionError:
            deleted = False
        check("the restricted copy CAN be deleted in a controlled way through the folder's delete-child right", deleted and not copy.exists())

        # fail closed
        subprocess.run(["icacls", str(folder), "/grant", "*S-1-1-0:(R)"], capture_output=True)
        code, out = tool(FOLDER_TOOL, "-Path", str(folder), "-VerifyOnly")
        check("verify-only fails (exit 1) when Everyone has a rule", code == 1 and "FOLDER ACL FAIL" in out and "outside the policy" in out)
        code, out = tool(FOLDER_TOOL, "-Path", str(folder))
        check("apply removes the foreign rule", code == 0 and len(rules(folder)) == 4)
        subprocess.run(["icacls", str(folder), "/grant", f"*{my_sid}:(F)"], capture_output=True)
        code, out = tool(FOLDER_TOOL, "-Path", str(folder), "-VerifyOnly")
        check("verify-only fails when the current user is raised to Full Control", code == 1 and "differ from the policy" in out)
        subprocess.run(["icacls", str(folder), "/inheritance:e"], capture_output=True)
        code, out = tool(FOLDER_TOOL, "-Path", str(folder), "-VerifyOnly")
        check("verify-only fails when inheritance is enabled again", code == 1 and "inheritance is enabled" in out)
        plain = Path(raw) / "plain.txt"
        plain.write_text("x")
        code, out = tool(FOLDER_TOOL, "-Path", str(plain))
        check("a file instead of a folder is refused (exit 2)", code == 2 and "not a folder" in out)
        code, out = tool(FOLDER_TOOL, "-Path", str(Path(raw) / "absent"))
        check("a missing folder is exit 2", code == 2 and "missing" in out)
        subprocess.run(["icacls", str(folder), "/reset", "/T"], capture_output=True)
    print(f"{FAILURES} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
