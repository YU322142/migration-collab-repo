param(
    [Parameter(Mandatory = $true)][string]$ServerDirectory
)

$ErrorActionPreference = 'Stop'
$server = (Resolve-Path -LiteralPath $ServerDirectory).Path.TrimEnd('\')
if ((Split-Path -Leaf $server) -notmatch '^cookery-fullstack-smoke[0-9]+$') {
    throw "Refusing unexpected smoke directory: $server"
}
$stdout = Join-Path $server 'smoke-background-stdout.log'
$stderr = Join-Path $server 'smoke-background-stderr.log'
$process = Start-Process -FilePath 'java' `
        -ArgumentList '-Xms1G', '-Xmx4G', '@user_jvm_args.txt',
            '@libraries/net/neoforged/neoforge/21.1.241/win_args.txt', 'nogui' `
        -WorkingDirectory $server -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
        -WindowStyle Hidden -PassThru
[IO.File]::WriteAllText((Join-Path $server 'smoke-wrapper.pid'), [string]$process.Id)
Write-Output "Started Java wrapper PID $($process.Id)"
