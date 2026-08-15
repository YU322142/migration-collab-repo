param(
    [Parameter(Mandatory = $true)][string]$ServerDirectory,
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = 'Stop'
$server = (Resolve-Path -LiteralPath $ServerDirectory).Path.TrimEnd('\')
if ((Split-Path -Leaf $server) -notmatch '^cookery-fullstack-smoke[0-9]+$') {
    throw "Refusing unexpected smoke directory: $server"
}

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
if (-not $process.Start()) {
    throw 'Failed to start Minecraft server process'
}

$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
$ready = $false
while (-not $process.HasExited -and [DateTime]::UtcNow -lt $deadline) {
    $latestLog = Join-Path $server 'logs\latest.log'
    if (Test-Path -LiteralPath $latestLog -PathType Leaf) {
        $tail = [IO.File]::ReadAllText($latestLog)
        if ($tail -match 'Done \(.+\)! For help, type "help"') {
            $ready = $true
            break
        }
    }
    Start-Sleep -Milliseconds 500
}

if ($ready) {
    $process.StandardInput.WriteLine('stop')
    $process.StandardInput.Flush()
    if (-not $process.WaitForExit(90000)) {
        $process.Kill()
        throw 'Server did not stop cleanly within 90 seconds'
    }
} elseif (-not $process.HasExited) {
    $process.StandardInput.WriteLine('stop')
    $process.StandardInput.Flush()
    if (-not $process.WaitForExit(30000)) {
        $process.Kill()
    }
    throw "Server did not reach ready state within $TimeoutSeconds seconds"
}

$stdout = $stdoutTask.Result
$stderr = $stderrTask.Result
[IO.File]::WriteAllText($stdoutPath, $stdout)
[IO.File]::WriteAllText($stderrPath, $stderr)
if (-not $ready) {
    throw "Server exited before ready; exit code $($process.ExitCode)"
}
if ($process.ExitCode -ne 0) {
    throw "Server exited with code $($process.ExitCode)"
}

Write-Output "Server reached ready state and stopped cleanly"
Write-Output "Exit code: $($process.ExitCode)"
