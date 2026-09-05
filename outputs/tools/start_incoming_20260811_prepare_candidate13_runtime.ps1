$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'run_incoming_20260811_prepare_candidate13_runtime_detached.py'
$stdout = Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13-runtime-r2-supervisor.stdout.log'
$stderr = Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13-runtime-r2-supervisor.stderr.log'
foreach ($path in @($python, $script)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing dependency: $path" } }
foreach ($path in @($stdout, $stderr)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }
$process = Start-Process -FilePath $python -ArgumentList @('-B', $script) -WorkingDirectory $workspace `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
[ordered]@{ status='STARTED'; pid=$process.Id; stdout=$stdout; stderr=$stderr; target='<AUDIT_ROOT>\manual-test-candidate13-runtime-r2-20260812' } | ConvertTo-Json
