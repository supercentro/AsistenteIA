# Minimal folder policy for a backup folder on Windows (TD-049, group 17C), applied or verified; fails closed.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File secure_folder_acl.ps1 -Path <folder> [-VerifyOnly]
#
# Policy (explicit rules, inheritance from the parent disabled so that a change above never adds an identity here):
#   NT AUTHORITY\SYSTEM        Allow FullControl  (this folder, subfolders and files)  -- the operating system and its services
#   BUILTIN\Administrators     Allow FullControl  (this folder, subfolders and files)  -- legitimate administrative recovery
#   current user               Allow Modify + DeleteSubdirectoriesAndFiles (this folder, subfolders and files)
#                              -- create a copy, read it, verify it and delete it in a controlled way, even once the file
#                                 itself has been restricted to Read by secure_file_acl.ps1 (deletion then needs the
#                                 folder's delete-child right); no Full Control: the user cannot change the folder's ACL
#                                 or take ownership through the folder rules
#   owner                      current user
# Nothing else: Everyone, Authenticated Users, Users and any other inherited identity are removed. SYSTEM and Administrators
# are kept on purpose (they would regain access anyway and the owner asked not to remove them); the gap that remains is the
# operating system's: an administrator can still delete or replace a file through this folder.
# Files created here inherit the three rules until secure_file_acl.ps1 protects them (Read for the current user only).
# Output: the folder NAME only, never its path. Exit 1 on any deviation (verify), exit 2 on a missing or non-folder path.
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [switch]$VerifyOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([int]$code, [string]$message) { Write-Output "FOLDER ACL FAIL ${message}"; exit $code }

$item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
if ($null -eq $item) { Fail 2 "(missing): the folder does not exist" }
if (-not $item.PSIsContainer) { Fail 2 "$($item.Name): not a folder" }
if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { Fail 2 "$($item.Name): a junction or symbolic link, not the folder itself" }
$name = $item.Name
$mySid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = New-Object System.Security.Principal.SecurityIdentifier([System.Security.Principal.WellKnownSidType]::LocalSystemSid, $null)
$adminsSid = New-Object System.Security.Principal.SecurityIdentifier([System.Security.Principal.WellKnownSidType]::BuiltinAdministratorsSid, $null)
$full = [System.Security.AccessControl.FileSystemRights]::FullControl
# Synchronize is included explicitly: Windows adds it to every Allow rule, so a stored Modify rule reads back as Modify|Synchronize.
$userRights = [System.Security.AccessControl.FileSystemRights]::Modify -bor [System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [System.Security.AccessControl.FileSystemRights]::Synchronize
$inherit = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
$none = [System.Security.AccessControl.PropagationFlags]::None
$allow = [System.Security.AccessControl.AccessControlType]::Allow
$expected = @{ $systemSid.Value = $full; $adminsSid.Value = $full; $mySid.Value = $userRights }

if (-not $VerifyOnly) {
    try {
        $acl = Get-Acl -LiteralPath $item.FullName
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRule($rule) }
        if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]) -ne $mySid) { $acl.SetOwner($mySid) }
        foreach ($sid in @($systemSid, $adminsSid, $mySid)) {
            $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($sid, $expected[$sid.Value], $inherit, $none, $allow)))
        }
        [System.IO.Directory]::SetAccessControl($item.FullName, $acl)
    } catch {
        Fail 1 "${name}: the descriptor could not be written ($($_.Exception.GetType().Name))"
    }
}

$check = Get-Acl -LiteralPath $item.FullName
$rules = @($check.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
$problems = @()
if (-not $check.AreAccessRulesProtected) { $problems += "inheritance is enabled" }
if ($rules.Count -ne 3) { $problems += "expected 3 access rules, found $($rules.Count)" }
$seen = @{}
foreach ($rule in $rules) {
    $sid = $rule.IdentityReference.Value
    if ($rule.IsInherited) { $problems += "an inherited rule is present" }
    if ($rule.AccessControlType -ne $allow) { $problems += "a deny rule is present" }
    if (-not $expected.ContainsKey($sid)) { $problems += "a rule for an identity outside the policy is present"; continue }
    if ($seen.ContainsKey($sid)) { $problems += "an identity has more than one rule" }
    $seen[$sid] = $true
    if ($rule.FileSystemRights -ne $expected[$sid]) { $problems += "rights of one identity differ from the policy ($([int]$rule.FileSystemRights))" }
    if ($rule.InheritanceFlags -ne $inherit -or $rule.PropagationFlags -ne $none) { $problems += "inheritance flags of one rule differ from the policy" }
}
foreach ($sid in $expected.Keys) { if (-not $seen.ContainsKey($sid)) { $problems += "a policy identity has no rule" } }
if ($check.GetOwner([System.Security.Principal.SecurityIdentifier]) -ne $mySid) { $problems += "the owner is not the current user" }
if ($problems.Count -gt 0) { Fail 1 "${name}: $(($problems | Select-Object -Unique) -join '; ')" }
$mode = if ($VerifyOnly) { "verified" } else { "applied and verified" }
Write-Output "FOLDER ACL OK ${name}: ${mode}; inheritance disabled; 3 rules: SYSTEM Full, Administrators Full, current user Modify+DeleteChild; owner: current user"
exit 0
