param(
    [Parameter(Mandatory = $true)][string]$ServerDirectory,
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = 'Stop'
$server = (Resolve-Path -LiteralPath $ServerDirectory).Path.TrimEnd('\')
if ((Split-Path -Leaf $server) -notmatch '^toms-storage-create-6\.0\.10-smoke[0-9]+$') {
    throw "Refusing unexpected smoke directory: $server"
}
$tempRoot = '<AUDIT_ROOT>\tmp-toms-create-smoke'
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$env:GRADLE_USER_HOME = '<AUDIT_ROOT>\gradle-cache-toms-neoforge'

$stdoutPath = Join-Path $server 'smoke-stdout.log'
$stderrPath = Join-Path $server 'smoke-stderr.log'
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = 'java'
$startInfo.Arguments = '-Xms1G -Xmx4G @user_jvm_args.txt @libraries/net/neoforged/neoforge/21.1.241/win_args.txt nogui'
$startInfo.WorkingDirectory = $server
$startInfo.UseShellExecute = $false
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $startInfo
$startedAt = [DateTime]::UtcNow
if (-not $process.Start()) {
    throw 'Failed to start Minecraft server process'
}
$stdoutLines = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()
$stderrLines = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()
$process.add_OutputDataReceived({
    param($sender, $event)
    if ($null -ne $event.Data) {
        $stdoutLines.Enqueue($event.Data)
    }
})
$process.add_ErrorDataReceived({
    param($sender, $event)
    if ($null -ne $event.Data) {
        $stderrLines.Enqueue($event.Data)
    }
})
$process.BeginOutputReadLine()
$process.BeginErrorReadLine()
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$ready = $false
$lastLog = ''
try {
    while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
        $latestLog = Join-Path $server 'logs\latest.log'
        if (Test-Path -LiteralPath $latestLog -PathType Leaf) {
            try {
                $lastLog = [IO.File]::ReadAllText($latestLog)
            } catch [IO.IOException] {
                # Log4j can hold the file briefly while rotating/flushing.
            }
            $observed = (($stdoutLines.ToArray() -join [Environment]::NewLine) + [Environment]::NewLine + $lastLog)
            if ($observed -match 'Done \(.+\)! For help, type "help"') {
                $ready = $true
                break
            }
        }
        Start-Sleep -Milliseconds 500
    }
    if ($ready) {
        $process.StandardInput.WriteLine('list')
        $process.StandardInput.Flush()
        Start-Sleep -Milliseconds 500
        $process.StandardInput.WriteLine('stop')
        $process.StandardInput.Flush()
        if (-not $process.WaitForExit(90000)) {
            throw 'Server did not stop cleanly within 90 seconds'
        }
    } elseif (-not $process.HasExited) {
        $process.StandardInput.WriteLine('stop')
        $process.StandardInput.Flush()
        if (-not $process.WaitForExit(30000)) {
            $process.Kill()
            $process.WaitForExit()
        }
        throw "Server did not reach ready state within $TimeoutSeconds seconds"
    } else {
        throw "Server exited before ready; exit code $($process.ExitCode)"
    }
} finally {
    if (-not $process.HasExited) {
        try {
            $process.Kill()
            $process.WaitForExit()
        } catch {
        }
    }
    [IO.File]::WriteAllText($stdoutPath, ($stdoutLines.ToArray() -join [Environment]::NewLine),
        (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($stderrPath, ($stderrLines.ToArray() -join [Environment]::NewLine),
        (New-Object System.Text.UTF8Encoding($false)))
}

$latestPath = Join-Path $server 'logs\latest.log'
$logText = if (Test-Path -LiteralPath $latestPath) {
    [IO.File]::ReadAllText($latestPath)
} else {
    $lastLog
}
$fatal = @($logText -split '\r?\n' | Where-Object {
    $_ -match '(?i)(ModLoadingException|Exception in server tick|NoSuchMethodError|NoClassDefFoundError|Failed to load|Could not execute entrypoint|crash report)'
})
$signals = [ordered]@{
    ready = $ready
    exit_code = $process.ExitCode
    elapsed_seconds = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 1)
    minecraft_1_21_1 = ($logText -match 'starting minecraft server version 1\.21\.1')
    neoforge_241 = ($logText -match '21\.1\.241')
    create_loaded = ($logText -match '(?i)(create|Create).*6\.0\.10|Constructing mod.*create')
    toms_loaded = ($logText -match '(?i)(Tom.?s Simple Storage|toms_storage).*config|Loading.*toms_storage')
    done = ($logText -match 'Done \(.+\)!')
    fatal_count = $fatal.Count
    fatal_tail = @($fatal | Select-Object -Last 20)
}
$signals | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $server 'smoke-report.json') -Encoding utf8
if ($fatal.Count -gt 0) {
    throw ('fatal log signals: ' + ($fatal -join ' | '))
}
if (-not $ready) {
    throw 'ready signal missing'
}
Write-Output ($signals | ConvertTo-Json -Compress)
