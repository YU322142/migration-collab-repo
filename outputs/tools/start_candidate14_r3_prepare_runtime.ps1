$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'run_candidate14_r3_prepare_runtime_detached.py'
$stdout = Join-Path $workspace 'outputs\candidate14-r3-runtime-prepare-supervisor.stdout.log'
$stderr = Join-Path $workspace 'outputs\candidate14-r3-runtime-prepare-supervisor.stderr.log'
foreach ($path in @($python, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing dependency: $path"
    }
}
if (Test-Path -LiteralPath $stdout) { throw "Refusing to overwrite: $stdout" }
if (Test-Path -LiteralPath $stderr) { throw "Refusing to overwrite: $stderr" }
$process = Start-Process -FilePath $python -ArgumentList @('-B', $script) `
    -WorkingDirectory $workspace -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
[ordered]@{
    status = 'STARTED'
    pid = $process.Id
    stdout = $stdout
    stderr = $stderr
    target = 'D:\Trans\migration-audit-work\manual-test-candidate14-r3-runtime-20260812'
    java_started = $false
} | ConvertTo-Json
