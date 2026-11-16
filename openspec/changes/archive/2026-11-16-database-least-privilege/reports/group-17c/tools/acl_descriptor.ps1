# Export and restore the security descriptors (owner, group, DACL) of a folder and everything directly under it (TD-049).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File acl_descriptor.ps1 -Mode Export  -Path <folder> -Store <file>
#   powershell -NoProfile -ExecutionPolicy Bypass -File acl_descriptor.ps1 -Mode Restore -Path <folder> -Store <file>
#   powershell -NoProfile -ExecutionPolicy Bypass -File acl_descriptor.ps1 -Mode Compare -Path <folder> -Store <file>
#
# The store is one text line per item: `<relative name or .>|<SDDL>` (SDDL holds SIDs; keep the store OUTSIDE the repository).
# Restore: folder first (rules, owner only if different), then each exported child; a child absent now is reported, never created.
# Compare: exit 0 only if every exported item has the same SDDL now. Output: counts and verdicts, never a path or an identity.
param(
    [Parameter(Mandatory = $true)][ValidateSet("Export", "Restore", "Compare")][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Store
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$sections = [System.Security.AccessControl.AccessControlSections]::Owner -bor [System.Security.AccessControl.AccessControlSections]::Group -bor [System.Security.AccessControl.AccessControlSections]::Access

function Sddl([string]$p, [bool]$isDir) {
    if ($isDir) { return ([System.IO.Directory]::GetAccessControl($p, $sections)).GetSecurityDescriptorSddlForm($sections) }
    return ([System.IO.File]::GetAccessControl($p, $sections)).GetSecurityDescriptorSddlForm($sections)
}

$folder = Get-Item -LiteralPath $Path -Force
if (-not $folder.PSIsContainer) { Write-Output "DESCRIPTOR FAIL not a folder"; exit 2 }

if ($Mode -eq "Export") {
    if (Test-Path -LiteralPath $Store) { Write-Output "DESCRIPTOR FAIL the store already exists; not overwriting"; exit 1 }
    $lines = @(".|" + (Sddl $folder.FullName $true))
    foreach ($child in Get-ChildItem -LiteralPath $folder.FullName -Force) {
        $lines += ($child.Name + "|" + (Sddl $child.FullName $child.PSIsContainer))
    }
    [System.IO.File]::WriteAllLines($Store, $lines, (New-Object System.Text.UTF8Encoding($false)))
    Write-Output "DESCRIPTOR OK exported $($lines.Count) descriptors (folder + $($lines.Count - 1) children)"
    exit 0
}

$entries = [System.IO.File]::ReadAllLines($Store)
$bad = 0
foreach ($line in $entries) {
    $name, $sddl = $line.Split("|", 2)
    $isRoot = ($name -eq ".")
    $target = if ($isRoot) { $folder.FullName } else { Join-Path $folder.FullName $name }
    if (-not (Test-Path -LiteralPath $target)) { $bad++; continue }
    $isDir = (Get-Item -LiteralPath $target -Force).PSIsContainer
    if ($Mode -eq "Compare") {
        if ((Sddl $target $isDir) -ne $sddl) { $bad++ }
        continue
    }
    try {
        if ($isDir) { $acl = New-Object System.Security.AccessControl.DirectorySecurity } else { $acl = New-Object System.Security.AccessControl.FileSecurity }
        $acl.SetSecurityDescriptorSddlForm($sddl, $sections)
        $current = if ($isDir) { [System.IO.Directory]::GetAccessControl($target, [System.Security.AccessControl.AccessControlSections]::Owner) } else { [System.IO.File]::GetAccessControl($target, [System.Security.AccessControl.AccessControlSections]::Owner) }
        $sameOwner = $current.GetOwner([System.Security.Principal.SecurityIdentifier]) -eq $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
        if ($sameOwner) {
            # Owner unchanged: write DACL (and its protection flag) only, no privilege needed.
            $dacl = New-Object System.Security.AccessControl.DirectorySecurity
            if (-not $isDir) { $dacl = New-Object System.Security.AccessControl.FileSecurity }
            $dacl.SetSecurityDescriptorSddlForm($acl.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access), [System.Security.AccessControl.AccessControlSections]::Access)
            if ($isDir) { [System.IO.Directory]::SetAccessControl($target, $dacl) } else { [System.IO.File]::SetAccessControl($target, $dacl) }
        } else {
            if ($isDir) { [System.IO.Directory]::SetAccessControl($target, $acl) } else { [System.IO.File]::SetAccessControl($target, $acl) }
        }
    } catch { $bad++ }
}
if ($Mode -eq "Compare") {
    if ($bad -gt 0) { Write-Output "DESCRIPTOR DIFFERS $bad of $($entries.Count) items changed or missing"; exit 1 }
    Write-Output "DESCRIPTOR SAME all $($entries.Count) items match the export"; exit 0
}
# Restore: re-check with the same comparison
$diff = 0
foreach ($line in $entries) {
    $name, $sddl = $line.Split("|", 2)
    $target = if ($name -eq ".") { $folder.FullName } else { Join-Path $folder.FullName $name }
    if (-not (Test-Path -LiteralPath $target)) { $diff++; continue }
    $isDir = (Get-Item -LiteralPath $target -Force).PSIsContainer
    if ((Sddl $target $isDir) -ne $sddl) { $diff++ }
}
if ($bad -gt 0 -or $diff -gt 0) { Write-Output "DESCRIPTOR FAIL restore incomplete: $bad write problems, $diff items still differ"; exit 1 }
Write-Output "DESCRIPTOR OK restored and re-read: $($entries.Count) items identical to the export"
exit 0
