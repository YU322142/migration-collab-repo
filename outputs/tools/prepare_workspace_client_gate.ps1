param(
    [Parameter(Mandatory = $true)] [string] $SourceMinecraftRoot,
    [Parameter(Mandatory = $true)] [string] $ClientMods,
    [Parameter(Mandatory = $true)] [string] $BundleManifest,
    [Parameter(Mandatory = $true)] [string] $OutputRoot,
    [Parameter(Mandatory = $true)] [string] $Report
)

$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath($SourceMinecraftRoot)
$mods = [IO.Path]::GetFullPath($ClientMods)
$manifestPath = [IO.Path]::GetFullPath($BundleManifest)
$output = [IO.Path]::GetFullPath($OutputRoot)
$reportPath = [IO.Path]::GetFullPath($Report)
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\') + '\'
if (-not $output.StartsWith($workspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputRoot must be inside the current workspace'
}
if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite client gate root: $output" }
foreach ($path in @($source, $mods)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Directory missing: $path" }
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Bundle manifest missing: $manifestPath"
}

function File-Sha256([string] $Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([string]$manifest.side -ne 'client') { throw 'Bundle manifest side is not client' }
$actualJars = @(Get-ChildItem -LiteralPath $mods -File -Filter '*.jar' | Sort-Object Name)
if ($actualJars.Count -ne [int]$manifest.file_count) {
    throw "Client mod count mismatch: $($actualJars.Count) != $($manifest.file_count)"
}
$actualByName = @{}
foreach ($jar in $actualJars) { $actualByName[$jar.Name] = $jar }
$bundle = [Security.Cryptography.SHA256]::Create()
try {
    $stream = [IO.MemoryStream]::new()
    foreach ($row in @($manifest.files)) {
        $name = [string]$row.file
        if (-not $actualByName.ContainsKey($name)) { throw "Missing client JAR: $name" }
        $jar = $actualByName[$name]
        $hash = File-Sha256 $jar.FullName
        if ($hash -ne [string]$row.sha256 -or $jar.Length -ne [long]$row.bytes) {
            throw "Client JAR hash/size mismatch: $($jar.Name)"
        }
        $record = [Text.Encoding]::UTF8.GetBytes($jar.Name + [char]0 + $hash + "`n")
        $stream.Write($record, 0, $record.Length)
    }
    $stream.Position = 0
    $computedBundle = ([BitConverter]::ToString($bundle.ComputeHash($stream))).Replace('-', '')
} finally {
    if ($null -ne $stream) { $stream.Dispose() }
    $bundle.Dispose()
}
if ($computedBundle -ne [string]$manifest.bundle_sha256) {
    throw "Client bundle digest mismatch: $computedBundle"
}

New-Item -ItemType Directory -Path $output | Out-Null
foreach ($name in @('assets', 'libraries', 'versions')) {
    $target = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw "Shared input missing: $target" }
    New-Item -ItemType Junction -Path (Join-Path $output $name) -Target $target | Out-Null
}
foreach ($name in @('config', 'defaultconfigs', 'resourcepacks', 'saves', 'schematics', 'data', 'journeymap')) {
    $from = Join-Path $source $name
    if (Test-Path -LiteralPath $from) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $output $name) -Recurse
    }
}
foreach ($name in @('options.txt', 'launcher_profiles.json', 'usercache.json', 'usernamecache.json')) {
    $from = Join-Path $source $name
    if (Test-Path -LiteralPath $from -PathType Leaf) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $output $name)
    }
}
Copy-Item -LiteralPath $mods -Destination (Join-Path $output 'mods') -Recurse
New-Item -ItemType Directory -Path (Join-Path $output 'natives') | Out-Null

$value = [ordered]@{
    schema = 1
    status = 'PREPARED'
    source_minecraft_root = $source
    output_root = $output
    shared_read_only_directories = @('assets', 'libraries', 'versions')
    copied_client_bundle = [ordered]@{
        source = $mods
        file_count = $actualJars.Count
        bundle_sha256 = $computedBundle
        manifest = $manifestPath
        manifest_sha256 = File-Sha256 $manifestPath
    }
    production_source_written = $false
}
New-Item -ItemType Directory -Path (Split-Path -Parent $reportPath) -Force | Out-Null
[IO.File]::WriteAllText(
    $reportPath,
    ($value | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$value
