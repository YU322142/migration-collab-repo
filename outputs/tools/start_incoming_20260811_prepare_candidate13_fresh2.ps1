$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$runner = Join-Path $PSScriptRoot 'run_incoming_20260811_prepare_candidate13_fresh2_detached.py'
$stdout = Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13-fresh2.launch.stdout.log'
$stderr = Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13-fresh2.launch.stderr.log'
if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) { throw "Missing detached runner: $runner" }
$process = Start-Process -FilePath $python -ArgumentList @('-B', $runner) -WorkingDirectory $workspace `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
[pscustomobject]@{
    status = 'STARTED'
    supervisor_pid = $process.Id
    status_file = (Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13-fresh2.status.json')
    output = 'D:\Trans\migration-audit-work\manual-test-candidate13-fresh2-20260812'
    java_started = $false
    conversion_repeated = $false
} | ConvertTo-Json -Depth 4
