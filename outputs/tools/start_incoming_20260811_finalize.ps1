$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'resume_incoming_20260811_finalize_detached.py'
$stdout = Join-Path $workspace 'outputs\incoming-20260811-finalize.stdout.log'
$stderr = Join-Path $workspace 'outputs\incoming-20260811-finalize.stderr.log'
foreach ($path in @($python, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing finalize dependency: $path"
    }
}
if (Test-Path -LiteralPath $stdout) { Remove-Item -LiteralPath $stdout -Force }
if (Test-Path -LiteralPath $stderr) { Remove-Item -LiteralPath $stderr -Force }
$process = Start-Process -FilePath $python `
    -ArgumentList @('-B', $script) `
    -WorkingDirectory $workspace `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru
[ordered]@{
    status = 'STARTED'
    pid = $process.Id
    script = $script
    stdout = $stdout
    stderr = $stderr
} | ConvertTo-Json -Depth 4
