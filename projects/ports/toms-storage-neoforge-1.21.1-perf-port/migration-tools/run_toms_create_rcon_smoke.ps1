param(
    [Parameter(Mandatory = $true)][string]$ServerDirectory,
    [int]$Port = 10762,
    [int]$TimeoutSeconds = 240
)

$ErrorActionPreference = 'Stop'
$server = (Resolve-Path -LiteralPath $ServerDirectory).Path.TrimEnd('\')
if ((Split-Path -Leaf $server) -notmatch '^toms-storage-create-6\.0\.10-smoke[0-9]+$') {
    throw "Refusing unexpected smoke directory: $server"
}
$tempRoot = '<AUDIT_ROOT>\tmp-toms-create-rcon-smoke'
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$env:GRADLE_USER_HOME = '<AUDIT_ROOT>\gradle-cache-toms-neoforge'

function Read-Exact([IO.Stream]$Stream, [int]$Count) {
    $buffer = New-Object byte[] $Count
    $offset = 0
    while ($offset -lt $Count) {
        $read = $Stream.Read($buffer, $offset, $Count - $offset)
        if ($read -le 0) { throw 'RCON connection closed' }
        $offset += $read
    }
    return $buffer
}

function Write-Packet([IO.Stream]$Stream, [int]$Id, [int]$Type, [string]$Body) {
    $bodyBytes = [Text.Encoding]::UTF8.GetBytes($Body)
    $length = 4 + 4 + $bodyBytes.Length + 2
    $packet = New-Object byte[] ($length + 4)
    [BitConverter]::GetBytes($length).CopyTo($packet, 0)
    [BitConverter]::GetBytes($Id).CopyTo($packet, 4)
    [BitConverter]::GetBytes($Type).CopyTo($packet, 8)
    $bodyBytes.CopyTo($packet, 12)
    $Stream.Write($packet, 0, $packet.Length)
    $Stream.Flush()
}

function Read-Packet([IO.Stream]$Stream) {
    $length = [BitConverter]::ToInt32((Read-Exact $Stream 4), 0)
    if ($length -lt 10 -or $length -gt 1048576) { throw "Invalid RCON length $length" }
    $data = Read-Exact $Stream $length
    [pscustomobject]@{
        Id = [BitConverter]::ToInt32($data, 0)
        Type = [BitConverter]::ToInt32($data, 4)
        Body = [Text.Encoding]::UTF8.GetString($data, 8, $length - 10)
    }
}

function Invoke-Rcon([int]$RconPort, [string]$Password, [string]$Command) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $RconPort, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(1000)) { throw 'RCON connect timeout' }
        $client.EndConnect($async)
        $stream = $client.GetStream()
        $stream.ReadTimeout = 3000
        $stream.WriteTimeout = 3000
        Write-Packet $stream 41 3 $Password
        $auth = Read-Packet $stream
        if ($auth.Id -eq -1) { throw 'RCON authentication failed' }
        Write-Packet $stream 42 2 $Command
        try { return (Read-Packet $stream).Body } catch [IO.IOException] { return '' }
    } finally {
        $client.Dispose()
    }
}

$stdoutPath = Join-Path $server 'smoke-stdout.log'
$stderrPath = Join-Path $server 'smoke-stderr.log'
$argList = @('-Xms1G','-Xmx4G','@user_jvm_args.txt','@libraries/net/neoforged/neoforge/21.1.241/win_args.txt','nogui')
$start = Start-Process -FilePath 'java' -ArgumentList $argList -WorkingDirectory $server -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
$startedAt = [DateTime]::UtcNow
$ready = $false
$listResponse = ''
$password = 'toms-smoke-local-only'
try {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $listResponse = Invoke-Rcon $Port $password 'list'
            $ready = $true
            break
        } catch {
            if ($start.HasExited) { throw "server exited before RCON ready: $($start.ExitCode)" }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "RCON did not become ready within $TimeoutSeconds seconds" }
    try { Invoke-Rcon $Port $password 'stop' | Out-Null } catch { }
    if (-not $start.WaitForExit(90000)) {
        $start.Kill()
        $start.WaitForExit()
        throw 'server did not stop cleanly'
    }
} catch {
    if (-not $start.HasExited) {
        try { Invoke-Rcon $Port $password 'stop' | Out-Null } catch { }
        if (-not $start.WaitForExit(30000)) {
            $start.Kill()
            $start.WaitForExit()
        }
    }
    throw
}

$latestPath = Join-Path $server 'logs\latest.log'
$logText = if (Test-Path -LiteralPath $latestPath) { [IO.File]::ReadAllText($latestPath) } else { '' }
$fatal = @($logText -split '\r?\n' | Where-Object {
    $_ -match '(?i)(ModLoadingException|Exception in server tick|NoSuchMethodError|NoClassDefFoundError|Failed to load|Could not execute entrypoint|crash report)'
})
$logErrors = @($logText -split '\r?\n' | Where-Object {
    $_ -match '\[.*?/ERROR\]'
})
$start.Refresh()
$exitCode = $start.ExitCode
$signals = [ordered]@{
    ready = $ready
    exit_code = $exitCode
    elapsed_seconds = [Math]::Round(([DateTime]::UtcNow - $startedAt).TotalSeconds, 1)
    minecraft_1_21_1 = ($logText -match 'starting minecraft server version 1\.21\.1')
    neoforge_241 = ($logText -match '21\.1\.241')
    create_loaded = ($logText -match '(?i)Create 6\.0\.10 initializing')
    toms_loaded = ($logText -match '(?i)Loaded Tom.?s Simple Storage config')
    done = ($logText -match 'Done \(.+\)!')
    rcon_list = $listResponse
    fatal_count = $fatal.Count
    fatal_tail = @($fatal | Select-Object -Last 20)
    error_count = $logErrors.Count
    error_tail = @($logErrors | Select-Object -Last 20)
}
$signals | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $server 'smoke-report.json') -Encoding utf8
if ($fatal.Count -gt 0) { throw ('fatal log signals: ' + ($fatal -join ' | ')) }
if (-not $ready -or -not $signals.done) { throw 'ready/done signal missing' }
Write-Output ($signals | ConvertTo-Json -Compress)
