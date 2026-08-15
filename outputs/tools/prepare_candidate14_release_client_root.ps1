param(
    [Parameter(Mandatory=$true)][string] $ReleaseRoot,
    [Parameter(Mandatory=$true)][string] $ReadySha256,
    [Parameter(Mandatory=$true)][string] $BuildReport,
    [Parameter(Mandatory=$true)][string] $BuildReportSha256,
    [Parameter(Mandatory=$true)][string] $SourceMinecraftRoot,
    [Parameter(Mandatory=$true)][string] $OutputRoot,
    [Parameter(Mandatory=$true)][string] $Report,
    [Parameter(Mandatory=$true)][string] $LocalResourcePack,
    [string] $ServerAddress = 'play.example.invalid:12341',
    [switch] $PreflightOnly
)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = 'C:\Python314\python.exe'
$script = Join-Path $PSScriptRoot 'prepare_candidate14_release_client_root.py'
foreach ($path in @($python, $script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Candidate14 client preparation dependency: $path"
    }
}
$arguments = @(
    '-B', $script,
    '--release-root', $ReleaseRoot,
    '--ready-sha256', $ReadySha256,
    '--build-report', $BuildReport,
    '--build-report-sha256', $BuildReportSha256,
    '--source-minecraft-root', $SourceMinecraftRoot,
    '--output-root', $OutputRoot,
    '--report', $Report,
    '--local-resource-pack', $LocalResourcePack,
    '--server-address', $ServerAddress
)
if ($PreflightOnly.IsPresent) { $arguments += '--preflight-only' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "Candidate14 client preparation failed ($LASTEXITCODE)" }
