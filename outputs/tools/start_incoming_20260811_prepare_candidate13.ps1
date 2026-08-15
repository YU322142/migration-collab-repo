$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'run_incoming_20260811_prepare_candidate13_detached.py'
$stdout = Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13.stdout.log'
$stderr = Join-Path $workspace 'outputs\incoming-20260811-prepare-candidate13.stderr.log'
foreach ($path in @($python, $script)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing dependency: $path" } }
if (Test-Path -LiteralPath $stdout) { Remove-Item -LiteralPath $stdout -Force }
if (Test-Path -LiteralPath $stderr) { Remove-Item -LiteralPath $stderr -Force }
$process = Start-Process -FilePath $python -ArgumentList @('-B', $script) -WorkingDirectory $workspace `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
[ordered]@{ status='STARTED'; pid=$process.Id; stdout=$stdout; stderr=$stderr } | ConvertTo-Json
