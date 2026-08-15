param(
    [Parameter(Mandatory=$true)][string] $ReleaseRoot,
    [Parameter(Mandatory=$true)][string] $ReadySha256,
    [Parameter(Mandatory=$true)][string] $BuildReport,
    [Parameter(Mandatory=$true)][string] $BuildReportSha256,
    [Parameter(Mandatory=$true)][string] $Target,
    [Parameter(Mandatory=$true)][string] $ClientRoot,
    [Parameter(Mandatory=$true)][string] $PrepareReport,
    [Parameter(Mandatory=$true)][string] $ClientPrepareReport,
    [Parameter(Mandatory=$true)][string] $Report
)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'run_candidate14_release_gate.py'
$stdout = Join-Path $workspace 'outputs\candidate14-release-gate.stdout.log'
$stderr = Join-Path $workspace 'outputs\candidate14-release-gate.stderr.log'
foreach ($path in @($python, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Candidate14 runtime gate dependency: $path"
    }
}
# Other Java applications (for example Gradle daemons) are allowed.  Refuse
# only an existing Candidate14 gate/same target so an unrelated build process
# cannot block the private acceptance run or be mistaken for Minecraft.
$candidate14Processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.Name -match '^(java|javaw|python|pythonw)\.exe$') -and
        ($_.CommandLine -match 'run_candidate14_release_gate\.py|candidate14-r3-runtime-attempt2-20260812')
    }
if ($candidate14Processes) {
    throw 'Refusing to start while a Candidate14 gate for this release/target is already running'
}
if (Get-NetTCPConnection -LocalPort 12341,12342 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while Candidate14 TCP gate ports are occupied'
}
foreach ($path in @($stdout, $stderr)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}
$arguments = @(
    '-B', $script,
    '--release-root', $ReleaseRoot,
    '--ready-sha256', $ReadySha256,
    '--build-report', $BuildReport,
    '--build-report-sha256', $BuildReportSha256,
    '--target', $Target,
    '--client-root', $ClientRoot,
    '--prepare-report', $PrepareReport,
    '--client-prepare-report', $ClientPrepareReport,
    '--report', $Report,
    '--server-port', '12341',
    '--rcon-port', '12342',
    '--voice-port', '26341',
    '--ledger-workers', '20'
)
$process = Start-Process -FilePath $python -ArgumentList $arguments `
    -WorkingDirectory $workspace -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
[ordered]@{
    status = 'STARTED'
    pid = $process.Id
    release = $ReleaseRoot
    target = $Target
    client_root = $ClientRoot
    report = $Report
    stdout = $stdout
    stderr = $stderr
    ports = [ordered]@{ server = 12341; rcon = 12342; voice = 26341 }
    ledger_workers = 20
    release_scoped_exactness = $true
    permanent_mod_count_cap = $false
} | ConvertTo-Json -Depth 6
