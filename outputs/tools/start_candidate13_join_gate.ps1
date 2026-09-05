$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'run_candidate13_join_gate.py'
$stdout = Join-Path $workspace 'outputs\candidate13-join-gate-r2.stdout.log'
$stderr = Join-Path $workspace 'outputs\candidate13-join-gate-r2.stderr.log'

foreach ($path in @($python, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Candidate13 join-gate dependency: $path"
    }
}

$java = Get-Process -Name java,javaw -ErrorAction SilentlyContinue
if ($null -ne $java) {
    throw "Refusing to start while Java is already running: $($java.Id -join ',')"
}

foreach ($path in @($stdout, $stderr)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}

$process = Start-Process -FilePath $python -ArgumentList @('-B', $script) `
    -WorkingDirectory $workspace -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

[ordered]@{
    status = 'STARTED'
    pid = $process.Id
    script = $script
    stdout = $stdout
    stderr = $stderr
    target = '<AUDIT_ROOT>\manual-test-candidate13-runtime-r2-20260812'
    client_root = (Join-Path $workspace 'outputs\tmp\client-gate-candidate13\.minecraft')
    ports = [ordered]@{ server = 12341; rcon = 12342; voice = 26341 }
    teleport_pause_seconds = 10
    settle_seconds = 15
    bootstrap_timeout_seconds = 120
    dedicated_startup_timeout_seconds = 20
} | ConvertTo-Json -Depth 5
