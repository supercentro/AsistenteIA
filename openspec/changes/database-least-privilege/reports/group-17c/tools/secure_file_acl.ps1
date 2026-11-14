# Restrict a backup file on Windows to the current user, read only, and verify the resulting security descriptor.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File secure_file_acl.ps1 -Path <file>            # apply, then verify
#   powershell -NoProfile -ExecutionPolicy Bypass -File secure_file_acl.ps1 -Path <file> -VerifyOnly
#
# Why not icacls: the first version of run_17c_backup.sh built an icacls command inside a double-quoted PowerShell string,
# where "$env:USERNAME:(R)" expands to "(R)" (the colon is read as part of a scoped variable name), icacls rejected the
# parameter and the error went to /dev/null, so the dumps kept their inherited ACLs. This tool uses the .NET ACL API
# instead of string building, prints only the file NAME (never its folder), and fails closed: any deviation from the
# expected descriptor is exit 1, a missing or non-regular file is exit 2.
#
# Expected descriptor: inheritance disabled; exactly one access rule: Allow, current user (by SID), FileSystemRights.Read;
# owner = current user. Known limit: a member of Administrators can still take ownership (that is the operating system).
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [switch]$VerifyOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([int]$code, [string]$message) { Write-Output "ACL FAIL ${message}"; exit $code }

$item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
if ($null -eq $item) { Fail 2 "(missing): the file does not exist" }
if ($item.PSIsContainer) { Fail 2 "$($item.Name): not a regular file" }
if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { Fail 2 "$($item.Name): a symbolic link or junction, not the file itself" }
$name = $item.Name
$me = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$mySid = $me.User
$readRights = [System.Security.AccessControl.FileSystemRights]::Read
# Windows stores every Allow rule with Synchronize added, so a Read grant reads back as Read|Synchronize (0x120089).
$expectedRights = $readRights -bor [System.Security.AccessControl.FileSystemRights]::Synchronize

if (-not $VerifyOnly) {
    try {
        $acl = Get-Acl -LiteralPath $item.FullName
        $acl.SetAccessRuleProtection($true, $false)   # stop inheriting and do NOT copy the inherited rules
        foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRule($rule) }
        # The owner may always rewrite the DACL; changing the owner needs a privilege, so it is done only when needed.
        if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]) -ne $mySid) { $acl.SetOwner($mySid) }
        $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($mySid, $readRights, "Allow")))
        # .NET persists only the modified sections (the DACL here); Set-Acl of Windows PowerShell 5.1 also touches
        # the SACL and fails with PrivilegeNotHeldException once the file grants only Read.
        [System.IO.File]::SetAccessControl($item.FullName, $acl)
    } catch {
        Fail 1 "${name}: the descriptor could not be written ($($_.Exception.GetType().Name))"   # type only: the message holds the path
    }
}

# Verify against a fresh read of the descriptor, never against the object just written.
$check = Get-Acl -LiteralPath $item.FullName
$rules = @($check.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
$problems = @()
if (-not $check.AreAccessRulesProtected) { $problems += "inheritance is enabled" }
if ($rules.Count -ne 1) { $problems += "expected 1 access rule, found $($rules.Count)" }
foreach ($rule in $rules) {
    if ($rule.IsInherited) { $problems += "an inherited rule is present" }
    if ($rule.IdentityReference -ne $mySid) { $problems += "a rule for another identity is present" }
    if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { $problems += "a deny rule is present" }
    if ($rule.FileSystemRights -ne $expectedRights) { $problems += "rights are not exactly Read ($([int]$rule.FileSystemRights))" }
}
$owner = $check.GetOwner([System.Security.Principal.SecurityIdentifier])
if ($owner -ne $mySid) { $problems += "the owner is not the current user" }
if ($problems.Count -gt 0) { Fail 1 "${name}: $($problems -join '; ')" }
$mode = if ($VerifyOnly) { "verified" } else { "applied and verified" }
Write-Output "ACL OK ${name}: ${mode}; inheritance disabled; 1 rule: current user, Allow, Read; owner: current user"
exit 0
