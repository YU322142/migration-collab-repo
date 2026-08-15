[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$TargetPath = 'D:\Codex\.migration-backups-heavy'
$ProtectedPath = 'D:\Codex\.migration'
$StatusPath = 'D:\Trans\migration-backups-heavy-cleanup-20260813-resume-status.json'
$LogPath = 'D:\Trans\migration-backups-heavy-cleanup-20260813-resume.ndjson'
$ExpectedTopDirectory = '20260807-150332'

function Write-JsonLine {
    param([Parameter(Mandatory = $true)]$Value)
    $Value | ConvertTo-Json -Compress -Depth 8 | Add-Content -LiteralPath $LogPath -Encoding UTF8
}

function Write-Status {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Phase,
        [int]$DeletedFiles = 0,
        [int64]$DeletedBytes = 0,
        [array]$Failures = @(),
        [string]$ErrorText = ''
    )

    $remainingFiles = @()
    if (Test-Path -LiteralPath $TargetPath) {
        $remainingFiles = @(Get-ChildItem -LiteralPath $TargetPath -Recurse -Force -File -ErrorAction SilentlyContinue)
    }
    $remainingBytes = [int64](($remainingFiles | Measure-Object -Property Length -Sum).Sum)
    $payload = [ordered]@{
        schema = 1
        status = $Status
        phase = $Phase
        target = $TargetPath
        protected_path = $ProtectedPath
        target_exists = Test-Path -LiteralPath $TargetPath
        protected_path_exists = Test-Path -LiteralPath $ProtectedPath
        deleted_files_this_pass = $DeletedFiles
        deleted_bytes_this_pass = $DeletedBytes
        remaining_files = $remainingFiles.Count
        remaining_bytes = $remainingBytes
        failures = $Failures
        d_free_bytes = [int64](Get-PSDrive -Name D).Free
        process_id = $PID
        updated_at = (Get-Date).ToString('o')
        error = $ErrorText
    }
    $temporary = "$StatusPath.tmp-$PID"
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatusPath -Force
}

try {
    Set-Content -LiteralPath $LogPath -Value '' -Encoding UTF8
    Write-Status -Status 'RUNNING' -Phase 'PREFLIGHT'

    $resolvedTarget = [System.IO.Path]::GetFullPath($TargetPath).TrimEnd('\')
    $resolvedProtected = [System.IO.Path]::GetFullPath($ProtectedPath).TrimEnd('\')
    if ($resolvedTarget -cne 'D:\Codex\.migration-backups-heavy') {
        throw "Unexpected resolved target: $resolvedTarget"
    }
    if ($resolvedProtected -cne 'D:\Codex\.migration') {
        throw "Unexpected protected path: $resolvedProtected"
    }
    if (-not (Test-Path -LiteralPath $resolvedProtected -PathType Container)) {
        throw "Protected migration log directory is missing: $resolvedProtected"
    }
    if (-not (Test-Path -LiteralPath $resolvedTarget)) {
        Write-Status -Status 'PASS' -Phase 'ALREADY_REMOVED'
        exit 0
    }

    $rootItem = Get-Item -LiteralPath $resolvedTarget -Force
    if (-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Target is not an ordinary directory.'
    }
    $topEntries = @(Get-ChildItem -LiteralPath $resolvedTarget -Force)
    if ($topEntries.Count -ne 1 -or -not $topEntries[0].PSIsContainer -or $topEntries[0].Name -cne $ExpectedTopDirectory) {
        throw 'Remaining top-level layout does not match the audited backup.'
    }
    $reparseEntries = @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force -ErrorAction Stop |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
    if ($reparseEntries.Count -ne 0) {
        throw 'A reparse point appeared inside the cleanup target.'
    }

    $files = @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force -File -ErrorAction Stop)
    $startingBytes = [int64](($files | Measure-Object -Property Length -Sum).Sum)
    Write-JsonLine ([ordered]@{
        event = 'PRECHECK_PASS'
        at = (Get-Date).ToString('o')
        files = $files.Count
        bytes = $startingBytes
        target = $resolvedTarget
        protected = $resolvedProtected
    })

    $deletedFiles = 0
    $deletedBytes = [int64]0
    $failures = [System.Collections.Generic.List[object]]::new()
    foreach ($file in $files) {
        $deleted = $false
        $lastError = ''
        for ($attempt = 1; $attempt -le 3 -and -not $deleted; $attempt++) {
            try {
                Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
                $deleted = $true
                $deletedFiles++
                $deletedBytes += [int64]$file.Length
            }
            catch {
                $lastError = $_.Exception.Message
                if ($attempt -lt 3) {
                    Start-Sleep -Milliseconds 500
                }
            }
        }
        if (-not $deleted) {
            $failure = [ordered]@{
                path = $file.FullName
                bytes = [int64]$file.Length
                error = $lastError
            }
            $failures.Add($failure)
            Write-JsonLine ([ordered]@{ event = 'FILE_RETAINED'; at = (Get-Date).ToString('o'); detail = $failure })
        }
    }

    $directories = @(Get-ChildItem -LiteralPath $resolvedTarget -Recurse -Force -Directory -ErrorAction Stop |
        Sort-Object { $_.FullName.Length } -Descending)
    foreach ($directory in $directories) {
        try {
            Remove-Item -LiteralPath $directory.FullName -Force -ErrorAction Stop
        }
        catch {
            # A directory containing a retained locked file is expected to remain.
        }
    }
    try {
        Remove-Item -LiteralPath $resolvedTarget -Force -ErrorAction Stop
    }
    catch {
        # Root remains if one or more locked files remain.
    }

    if (-not (Test-Path -LiteralPath $resolvedProtected -PathType Container)) {
        throw 'Protected migration log directory disappeared during cleanup.'
    }

    if (Test-Path -LiteralPath $resolvedTarget) {
        Write-JsonLine ([ordered]@{
            event = 'PARTIAL_COMPLETE'
            at = (Get-Date).ToString('o')
            deleted_files = $deletedFiles
            deleted_bytes = $deletedBytes
            retained_files = $failures.Count
        })
        Write-Status -Status 'PARTIAL_LOCKED_FILES_REMAIN' -Phase 'COMPLETE' -DeletedFiles $deletedFiles -DeletedBytes $deletedBytes -Failures $failures.ToArray()
        exit 2
    }

    Write-JsonLine ([ordered]@{
        event = 'DELETE_PASS'
        at = (Get-Date).ToString('o')
        deleted_files = $deletedFiles
        deleted_bytes = $deletedBytes
        protected_preserved = $resolvedProtected
    })
    Write-Status -Status 'PASS' -Phase 'COMPLETE' -DeletedFiles $deletedFiles -DeletedBytes $deletedBytes
    exit 0
}
catch {
    $message = $_.Exception.Message
    Write-JsonLine ([ordered]@{ event = 'FAILED'; at = (Get-Date).ToString('o'); error = $message })
    try {
        Write-Status -Status 'FAILED' -Phase 'ABORTED' -ErrorText $message
    }
    catch {
        # Preserve the original failure.
    }
    exit 1
}
