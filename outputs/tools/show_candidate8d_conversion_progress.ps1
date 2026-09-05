param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$taskName = 'Codex-Candidate8d-WorldConversion-20260811'
$reports = '<AUDIT_ROOT>\cutover-staging-candidate8d-20260811-reports'
$stdoutPath = Join-Path $reports 'scheduled-conversion.stdout.log'
$stderrPath = Join-Path $reports 'scheduled-conversion.stderr.log'
$statusPath = Join-Path $reports 'scheduled-conversion-status.json'

$Host.UI.RawUI.WindowTitle = 'Candidate8d world conversion progress (8 workers)'
Write-Host 'Candidate8d world conversion' -ForegroundColor Cyan
Write-Host '8 continuously drained region workers; balanced against 27.6 GB memory.'
Write-Host 'This window is only a monitor. Closing it does not stop conversion.'
Write-Host ''

$stdoutOffset = 0L
$stderrOffset = 0L
$lastTaskState = ''

function Show-NewText {
    param(
        [Parameter(Mandatory = $true)] [string] $Path,
        [Parameter(Mandatory = $true)] [ref] $Offset,
        [Parameter(Mandatory = $true)] [ConsoleColor] $Color
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        if ($Offset.Value -gt $stream.Length) {
            $Offset.Value = 0L
        }
        $stream.Position = $Offset.Value
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8, $true, 4096, $true)
        try {
            $text = $reader.ReadToEnd()
            $Offset.Value = $stream.Position
        }
        finally {
            $reader.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
    if ($text.Length -gt 0) {
        Write-Host $text.TrimEnd("`r", "`n") -ForegroundColor $Color
    }
}

while ($true) {
    Show-NewText -Path $stdoutPath -Offset ([ref]$stdoutOffset) -Color Gray
    Show-NewText -Path $stderrPath -Offset ([ref]$stderrOffset) -Color Red

    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    $taskState = if ($null -eq $task) { 'NotFound' } else { [string]$task.State }
    if ($taskState -ne $lastTaskState) {
        Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] task=$taskState" -ForegroundColor DarkCyan
        $lastTaskState = $taskState
    }

    if (Test-Path -LiteralPath $statusPath) {
        Show-NewText -Path $stdoutPath -Offset ([ref]$stdoutOffset) -Color Gray
        Show-NewText -Path $stderrPath -Offset ([ref]$stderrOffset) -Color Red
        $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
        $color = if ($status.status -eq 'PASS') { 'Green' } else { 'Red' }
        Write-Host ''
        Write-Host "Final status: $($status.status) (exit $($status.exit_code))" -ForegroundColor $color
        Write-Host "Elapsed: $($status.elapsed_seconds) seconds"
        Write-Host "Report: $($status.report)"
        Write-Host 'This progress window will close in 30 seconds.'
        Start-Sleep -Seconds 30
        break
    }
    Start-Sleep -Seconds 1
}
