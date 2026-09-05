param(
    [string] $SourceMinecraftRoot = '',
    [string] $ClientMods = '',
    [string] $BundleManifest = '',
    [string] $OutputRoot = '',
    [string] $Report = '',
    [string] $SyntheticUsername = 'Candidate8Gate',
    [string] $SyntheticUuid = '00000000-0000-0000-0000-000000000801'
)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedSource = Join-Path $workspace 'outputs\tmp\client-gate-candidate5\.minecraft'
$expectedMods = Join-Path $workspace 'outputs\tmp\final-client-mods-candidate6'
$expectedManifest = Join-Path $workspace 'outputs\final-client-mods-candidate6-manifest-20260810.json'
$expectedOutput = Join-Path $workspace 'outputs\tmp\client-gate-candidate8\.minecraft'
$expectedReport = Join-Path $workspace 'outputs\candidate8-client-root-prepare-20260811.json'

if ([string]::IsNullOrWhiteSpace($SourceMinecraftRoot)) { $SourceMinecraftRoot = $expectedSource }
if ([string]::IsNullOrWhiteSpace($ClientMods)) { $ClientMods = $expectedMods }
if ([string]::IsNullOrWhiteSpace($BundleManifest)) { $BundleManifest = $expectedManifest }
if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = $expectedOutput }
if ([string]::IsNullOrWhiteSpace($Report)) { $Report = $expectedReport }

function Full-Path([string] $Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Same-Path([string] $Left, [string] $Right) {
    return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase)
}

function Path-IsWithin([string] $Path, [string] $Parent) {
    $fullPath = (Full-Path $Path) + '\'
    $fullParent = (Full-Path $Parent) + '\'
    return $fullPath.StartsWith($fullParent, [StringComparison]::OrdinalIgnoreCase)
}

function File-Sha256([string] $Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

function Bytes-Sha256([byte[]] $Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '')
    } finally {
        $sha.Dispose()
    }
}

function Record-Sha256([string[]] $Records) {
    $payload = [Text.Encoding]::UTF8.GetBytes(($Records -join "`n") + "`n")
    return Bytes-Sha256 $payload
}

function Relative-Path([string] $Base, [string] $Path) {
    $prefix = (Full-Path $Base) + '\'
    $full = Full-Path $Path
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside base: $full"
    }
    return $full.Substring($prefix.Length).Replace('\', '/')
}

function Tree-Fingerprint([string] $Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return [ordered]@{ files = 0; bytes = 0; sha256 = Record-Sha256 @() }
    }
    $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File | Sort-Object FullName)
    $records = [Collections.Generic.List[string]]::new()
    [long]$totalBytes = 0
    foreach ($file in $files) {
        $relative = Relative-Path $Root $file.FullName
        $hash = File-Sha256 $file.FullName
        $totalBytes += $file.Length
        $records.Add($relative + [char]0 + [string]$file.Length + [char]0 + $hash)
    }
    return [ordered]@{
        files = $files.Count
        bytes = $totalBytes
        sha256 = Record-Sha256 $records.ToArray()
    }
}

function Top-Level-Fingerprint([string] $Root) {
    $records = [Collections.Generic.List[string]]::new()
    foreach ($item in @(Get-ChildItem -LiteralPath $Root -Force | Sort-Object Name)) {
        $target = @($item.Target) -join ';'
        $length = if ($item.PSIsContainer) { '-' } else { [string]$item.Length }
        $records.Add(
            $item.Name + [char]0 + [string]$item.Attributes + [char]0 +
            $length + [char]0 + $item.LastWriteTimeUtc.ToString('o') + [char]0 + $target
        )
    }
    return Record-Sha256 $records.ToArray()
}

function Bundle-Digest([object[]] $Rows, [hashtable] $FilesByName) {
    $stream = [IO.MemoryStream]::new()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        foreach ($row in $Rows) {
            $name = [string]$row.file
            if (-not $FilesByName.ContainsKey($name)) { throw "Missing client JAR: $name" }
            $file = $FilesByName[$name]
            $hash = File-Sha256 $file.FullName
            $record = [Text.Encoding]::UTF8.GetBytes($name + [char]0 + $hash + "`n")
            $stream.Write($record, 0, $record.Length)
        }
        $stream.Position = 0
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

$source = Full-Path $SourceMinecraftRoot
$mods = Full-Path $ClientMods
$manifestPath = Full-Path $BundleManifest
$output = Full-Path $OutputRoot
$reportPath = Full-Path $Report

foreach ($binding in @(
    @($source, $expectedSource, 'SourceMinecraftRoot'),
    @($mods, $expectedMods, 'ClientMods'),
    @($manifestPath, $expectedManifest, 'BundleManifest'),
    @($output, $expectedOutput, 'OutputRoot'),
    @($reportPath, $expectedReport, 'Report')
)) {
    if (-not (Same-Path $binding[0] $binding[1])) {
        throw "$($binding[2]) is not the locked Candidate8 path: $($binding[0])"
    }
}
if ($SyntheticUsername -notmatch '^[A-Za-z0-9_]{1,16}$') {
    throw 'SyntheticUsername is not a safe offline test name'
}
$parsedUuid = [Guid]::Empty
if (-not [Guid]::TryParseExact($SyntheticUuid, 'D', [ref]$parsedUuid)) {
    throw 'SyntheticUuid must be a canonical UUID'
}
if ($parsedUuid -eq [Guid]::Empty) { throw 'SyntheticUuid cannot be the nil UUID' }

foreach ($path in @($source, $mods)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Directory missing: $path" }
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Bundle manifest missing: $manifestPath"
}
if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite client gate root: $output" }
if (Test-Path -LiteralPath $reportPath) { throw "Refusing to overwrite client gate report: $reportPath" }
if (-not (Path-IsWithin $output $workspace) -or -not (Path-IsWithin $reportPath $workspace)) {
    throw 'Candidate8 output and report must remain inside the workspace'
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([int]$manifest.schema -ne 1 -or [string]$manifest.side -ne 'client' -or [string]$manifest.status -ne 'PASS') {
    throw 'Candidate6 client manifest is not a passing schema-1 client manifest'
}
if ([int]$manifest.file_count -ne 50 -or @($manifest.files).Count -ne 50) {
    throw 'Candidate6 client manifest must contain exactly 50 JARs'
}
if (-not (Same-Path ([string]$manifest.bundle_dir) $mods)) {
    throw 'Candidate6 client manifest is not bound to the requested mod directory'
}

$manifestNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    if ([IO.Path]::GetFileName($name) -ne $name -or -not $name.EndsWith('.jar', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe manifest JAR name: $name"
    }
    if (-not $manifestNames.Add($name)) { throw "Duplicate manifest JAR name: $name" }
}

$allSourceFiles = @(Get-ChildItem -LiteralPath $mods -File | Sort-Object Name)
$sourceDirs = @(Get-ChildItem -LiteralPath $mods -Directory)
$sourceJars = @($allSourceFiles | Where-Object { $_.Extension -ieq '.jar' })
if ($sourceDirs.Count -ne 0 -or $allSourceFiles.Count -ne 50 -or $sourceJars.Count -ne 50) {
    throw 'Candidate6 mod directory must be flat and contain only the exact 50 JARs'
}
$sourceByName = @{}
foreach ($jar in $sourceJars) { $sourceByName[$jar.Name] = $jar }
[long]$sourceBytes = 0
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    if (-not $sourceByName.ContainsKey($name)) { throw "Missing source client JAR: $name" }
    $jar = $sourceByName[$name]
    $hash = File-Sha256 $jar.FullName
    if ($jar.Length -ne [long]$row.bytes -or $hash -ne ([string]$row.sha256).ToUpperInvariant()) {
        throw "Source client JAR hash/size mismatch: $name"
    }
    $sourceBytes += $jar.Length
}
if ($sourceBytes -ne [long]$manifest.bytes) { throw 'Source client bundle byte total mismatch' }
$sourceBundleDigest = Bundle-Digest @($manifest.files) $sourceByName
if ($sourceBundleDigest -ne ([string]$manifest.bundle_sha256).ToUpperInvariant()) {
    throw 'Source client bundle digest mismatch'
}

$sourceBefore = Top-Level-Fingerprint $source
$copiedDirectoryNames = @('config', 'defaultconfigs', 'resourcepacks', 'data')
$copiedFileNames = @('options.txt')
$excludedNames = @(
    '.cache', 'downloads', 'journeymap', 'logs', 'saves', 'schematics', 'screenshots',
    'launcher_profiles.json', 'usercache.json', 'usernamecache.json'
)
$junctionNames = @('assets', 'libraries', 'versions')
$junctionEvidence = [Collections.Generic.List[object]]::new()

New-Item -ItemType Directory -Path $output | Out-Null
foreach ($name in $junctionNames) {
    $sourceLink = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $sourceLink -PathType Container)) {
        throw "Shared client input missing: $sourceLink"
    }
    $sourceItem = Get-Item -LiteralPath $sourceLink -Force
    $sourceTargets = @($sourceItem.Target)
    if ($sourceItem.LinkType -eq 'Junction') {
        if ($sourceTargets.Count -ne 1) { throw "Unexpected junction target count: $sourceLink" }
        $directTarget = Full-Path ([string]$sourceTargets[0])
    } else {
        $directTarget = Full-Path $sourceItem.FullName
    }
    if (-not (Test-Path -LiteralPath $directTarget -PathType Container)) {
        throw "Resolved shared client input missing: $directTarget"
    }
    if (Path-IsWithin $directTarget '<TRANS_ROOT>\20260807') {
        throw "Shared client input unexpectedly resolves into the historical backup: $directTarget"
    }
    $destination = Join-Path $output $name
    New-Item -ItemType Junction -Path $destination -Target $directTarget | Out-Null
    $destinationItem = Get-Item -LiteralPath $destination -Force
    $destinationTargets = @($destinationItem.Target)
    if ($destinationItem.LinkType -ne 'Junction' -or $destinationTargets.Count -ne 1 -or
        -not (Same-Path ([string]$destinationTargets[0]) $directTarget)) {
        throw "Candidate8 shared directory junction validation failed: $destination"
    }
    $junctionEvidence.Add([ordered]@{
        name = $name
        source_path = $sourceLink
        source_link_type = [string]$sourceItem.LinkType
        resolved_target = $directTarget
        output_path = $destination
        output_link_type = [string]$destinationItem.LinkType
    })
}

foreach ($name in $copiedDirectoryNames) {
    $from = Join-Path $source $name
    if (Test-Path -LiteralPath $from -PathType Container) {
        Copy-Item -LiteralPath $from -Destination (Join-Path $output $name) -Recurse
    } else {
        New-Item -ItemType Directory -Path (Join-Path $output $name) | Out-Null
    }
}
foreach ($name in $copiedFileNames) {
    $from = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "Required client config missing: $from" }
    Copy-Item -LiteralPath $from -Destination (Join-Path $output $name)
}

# Identity and runtime caches are intentionally not inherited by the synthetic account.
foreach ($relative in @(
    'config\voicechat\username-cache.json',
    'config\voicechat\player-volumes.properties',
    'config\spark\tmp',
    'config\spark\tmp-client'
)) {
    $cachePath = Join-Path $output $relative
    if (Test-Path -LiteralPath $cachePath) { Remove-Item -LiteralPath $cachePath -Recurse -Force }
}

$outputMods = Join-Path $output 'mods'
New-Item -ItemType Directory -Path $outputMods | Out-Null
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    Copy-Item -LiteralPath $sourceByName[$name].FullName -Destination (Join-Path $outputMods $name)
}
New-Item -ItemType Directory -Path (Join-Path $output 'natives') | Out-Null

$outputFiles = @(Get-ChildItem -LiteralPath $outputMods -File | Sort-Object Name)
$outputDirs = @(Get-ChildItem -LiteralPath $outputMods -Directory)
$outputByName = @{}
foreach ($file in $outputFiles) { $outputByName[$file.Name] = $file }
if ($outputDirs.Count -ne 0 -or $outputFiles.Count -ne 50) {
    throw 'Prepared Candidate8 mod directory is not the exact flat 50-JAR set'
}
[long]$outputBytes = 0
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    if (-not $outputByName.ContainsKey($name)) { throw "Prepared Candidate8 JAR missing: $name" }
    $jar = $outputByName[$name]
    $hash = File-Sha256 $jar.FullName
    if ($jar.Length -ne [long]$row.bytes -or $hash -ne ([string]$row.sha256).ToUpperInvariant()) {
        throw "Prepared Candidate8 JAR hash/size mismatch: $name"
    }
    $outputBytes += $jar.Length
}
$outputBundleDigest = Bundle-Digest @($manifest.files) $outputByName
if ($outputBytes -ne [long]$manifest.bytes -or $outputBundleDigest -ne $sourceBundleDigest) {
    throw 'Prepared Candidate8 bundle aggregate mismatch'
}

foreach ($name in $excludedNames) {
    if (Test-Path -LiteralPath (Join-Path $output $name)) {
        throw "Excluded Candidate5 state leaked into Candidate8: $name"
    }
}
$allowedTopLevel = @(
    'assets', 'config', 'data', 'defaultconfigs', 'libraries', 'mods', 'natives',
    'options.txt', 'resourcepacks', 'versions'
)
$unexpectedTopLevel = @(
    Get-ChildItem -LiteralPath $output -Force |
        Where-Object { $allowedTopLevel -notcontains $_.Name } |
        ForEach-Object { $_.Name }
)
if ($unexpectedTopLevel.Count -ne 0) {
    throw "Unexpected Candidate8 top-level state: $($unexpectedTopLevel -join ', ')"
}
$lastServer = @(
    Get-Content -LiteralPath (Join-Path $output 'options.txt') |
        Where-Object { $_ -like 'lastServer:*' }
)
if ($lastServer.Count -ne 1 -or $lastServer[0] -ne 'lastServer:') {
    throw 'Candidate8 options.txt inherits a non-empty multiplayer endpoint'
}

$sourceAfter = Top-Level-Fingerprint $source
if ($sourceBefore -ne $sourceAfter) {
    throw 'Candidate5 source root changed while Candidate8 was being prepared'
}

$copiedTreeEvidence = [ordered]@{}
foreach ($name in $copiedDirectoryNames) {
    $copiedTreeEvidence[$name] = Tree-Fingerprint (Join-Path $output $name)
}
$copiedTreeEvidence['options.txt'] = [ordered]@{
    files = 1
    bytes = (Get-Item -LiteralPath (Join-Path $output 'options.txt')).Length
    sha256 = File-Sha256 (Join-Path $output 'options.txt')
}

$value = [ordered]@{
    schema = 1
    status = 'PREPARED'
    purpose = 'Candidate8 hidden localhost join client root'
    source_minecraft_root = $source
    source_top_level_sha256_before = $sourceBefore
    source_top_level_sha256_after = $sourceAfter
    source_unchanged = $true
    output_root = $output
    junctions = $junctionEvidence.ToArray()
    copied_non_world_client_state = $copiedTreeEvidence
    excluded_source_state = $excludedNames
    excluded_state_absent = $true
    offline_identity = [ordered]@{
        username = $SyntheticUsername
        uuid = $parsedUuid.ToString('D')
        user_type = 'legacy'
        access_token = '0 (launcher argument, no account credential copied)'
        inherited_account_cache = $false
    }
    client_bundle = [ordered]@{
        source = $mods
        destination = $outputMods
        manifest = $manifestPath
        manifest_sha256 = File-Sha256 $manifestPath
        file_count = $outputFiles.Count
        bytes = $outputBytes
        bundle_sha256 = $outputBundleDigest
        expected_bundle_sha256 = ([string]$manifest.bundle_sha256).ToUpperInvariant()
        exact_manifest_match = $true
        stale_files = @()
    }
    java_started = $false
    historical_backup_accessed = $false
}
New-Item -ItemType Directory -Path (Split-Path -Parent $reportPath) -Force | Out-Null
[IO.File]::WriteAllText(
    $reportPath,
    ($value | ConvertTo-Json -Depth 10) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$value
