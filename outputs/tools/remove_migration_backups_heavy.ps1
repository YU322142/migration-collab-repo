[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$TargetPath = 'D:\Codex\.migration-backups-heavy'
$ProtectedPath = 'D:\Codex\.migration'
$StatusPath = '<TRANS_ROOT>\migration-backups-heavy-cleanup-20260813-status.json'
$LogPath = '<TRANS_ROOT>\migration-backups-heavy-cleanup-20260813.log'
$ExpectedBytes = [int64]29112078243
$ExpectedFiles = 21450
$ExpectedTopDirectory = '20260807-150332'

function Write-Status {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Phase,
        [string]$ErrorText = ''
    )

    $drive = Get-PSDrive -Name D
    $payload = [ordered]@{
        schema = 1
        status = $Status
        phase = $Phase
        target = $TargetPath
        protected_path = $ProtectedPath
        expected_bytes = $ExpectedBytes
        expected_files = $ExpectedFiles
        target_exists = Test-Path -LiteralPath $TargetPath
        protected_path_exists = Test-Path -LiteralPath $ProtectedPath
        d_free_bytes = [int64]$drive.Free
        process_id = $PID
        updated_at = (Get-Date).ToString('o')
        error = $ErrorText
    }

    $temporary = "$StatusPath.tmp-$PID"
    $payload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatusPath -Force
}

try {
    Write-Status -Status 'RUNNING' -Phase 'PREFLIGHT'

    $resolvedTarget = [System.IO.Path]::GetFullPath($TargetPath).TrimEnd('\')
    $resolvedProtected = [System.IO.Path]::GetFullPath($ProtectedPath).TrimEnd('\')
    if ($resolvedTarget -cne 'D:\Codex\.migration-backups-heavy') {
        throw "Unexpected resolved target: $resolvedTarget"
    }
    if ($resolvedProtected -cne 'D:\Codex\.migration') {
        throw "Unexpected protected path: $resolvedProtected"
    }
    if (-not (Test-Path -LiteralPath $resolvedTarget -PathType Container)) {
        throw "Target directory is missing: $resolvedTarget"
    }
    if (-not (Test-Path -LiteralPath $resolvedProtected -PathType Container)) {
        throw "Protected migration log directory is missing: $resolvedProtected"
    }

    $targetItem = Get-Item -LiteralPath $resolvedTarget -Force
    if ($targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Target is a reparse point; refusing recursive removal.'
    }

    $topEntries = @(Get-ChildItem -LiteralPath $resolvedTarget -Force)
    if ($topEntries.Count -ne 1 -or -not $topEntries[0].PSIsContainer -or $topEntries[0].Name -cne $ExpectedTopDirectory) {
        throw 'Target top-level contents no longer match the audited backup layout.'
    }
    if ($topEntries[0].Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Audited timestamp directory became a reparse point; refusing removal.'
    }

    $files = @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force -File -ErrorAction Stop)
    $actualFiles = $files.Count
    $actualBytes = [int64](($files | Measure-Object -Property Length -Sum).Sum)
    if ($actualFiles -ne $ExpectedFiles -or $actualBytes -ne $ExpectedBytes) {
        throw "Audited identity changed: files=$actualFiles bytes=$actualBytes"
    }

    "$(Get-Date -Format o) PRECHECK_PASS files=$actualFiles bytes=$actualBytes target=$resolvedTarget protected=$resolvedProtected" |
        Set-Content -LiteralPath $LogPath -Encoding UTF8
    Write-Status -Status 'RUNNING' -Phase 'DELETE'

    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force -ErrorAction Stop

    if (Test-Path -LiteralPath $resolvedTarget) {
        throw 'Target still exists after Remove-Item.'
    }
    if (-not (Test-Path -LiteralPath $resolvedProtected -PathType Container)) {
        throw 'Protected migration log directory is missing after cleanup.'
    }

    "$(Get-Date -Format o) DELETE_PASS removed_bytes=$ExpectedBytes target=$resolvedTarget protected_preserved=$resolvedProtected" |
        Add-Content -LiteralPath $LogPath -Encoding UTF8
    Write-Status -Status 'PASS' -Phase 'COMPLETE'
    exit 0
}
catch {
    $message = $_.Exception.Message
    "$(Get-Date -Format o) FAILED error=$message" | Add-Content -LiteralPath $LogPath -Encoding UTF8
    try {
        Write-Status -Status 'FAILED' -Phase 'ABORTED' -ErrorText $message
    }
    catch {
        # Preserve the original failure as the process exit condition.
    }
    exit 1
}
