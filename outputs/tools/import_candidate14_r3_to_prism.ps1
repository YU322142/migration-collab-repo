param(
    [string] $ClientRoot = '<AUDIT_ROOT>\client-gate-candidate14-r3-attempt3\.minecraft',
    [string] $ClientPrepareReport = '',
    [string] $PrismRoot = '<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3',
    [string] $ReleaseRoot = '<AUDIT_ROOT>\final-mod-bundles-candidate14-r3-20260812',
    [string] $BuildReport = '',
    [string] $TemplateInstanceName = '',
    [string] $InstanceName = '',
    [string] $Report = '',
    [string] $ServerAddress = '127.0.0.1:12341',
    [int] $MinMemoryMb = 2048,
    [int] $MaxMemoryMb = 4096,
    [switch] $PreflightOnly
)

# Candidate14-r3 Prism importer.
#
# This is deliberately a fresh-instance publisher. It dynamically validates the
# immutable Candidate14-r3 READY, release-lock, build report and client manifest,
# copies only that release's client JAR snapshot, and never launches Prism/Java.
# The exact 54-JAR check is release-scoped and is not a permanent mod-count cap.
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedClientRoot = '<AUDIT_ROOT>\client-gate-candidate14-r3-attempt3\.minecraft'
$expectedRelease = '<AUDIT_ROOT>\final-mod-bundles-candidate14-r3-20260812'
$expectedReadySha = '66778B3F91842D0AB6CC291D03AD9538AB12447F63340E6144747C4DAE819C24'
$expectedManifestSha = '020352BA39C8FAAF511AFF02FD0F9A92451697F51A1C8E4D1E0B9BEFE0398AAC'
$expectedBuildReportSha = '4658F5B6B75CEBC0E89C549427FBA10B87E9A05D6C934B408DEF85923493EF81'
$expectedPrepareReportSha = 'FDBB2341A82EA63C90DC280D26CD02EF60901F0A1B8CB743128673E236BC3576'
$expectedBundleSha = 'FCBEFE432E802CA8834ADFEA8D360764F33697D84B690C53D085CBD3DCDE0E76'
$expectedPairSha = 'D1B98FA225DD9DBE27499C36A8761A72449C50A43A250DBDCA32A348C21959C7'
$expectedPackSha = '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364'
$expectedPackBytes = 110377999
$expectedPackFormat = 34
$expectedJarCount = 54
$expectedJarBytes = 145905880
$packStem = ([char]0x4e16) + ([char]0x754c) + ([char]0x6307) + ([char]0x5b9a) + ([char]0x8d44) + ([char]0x6e90) + ([char]0x5305) + ([char]0x55b5)
$packFileName = $packStem + '-mc1.21.1-candidate13.zip'
$instanceStem = ([char]0x52A8) + ([char]0x9759) + ([char]0x4EA4) + ([char]0x6620)
$defaultTemplateName = $instanceStem + '-Candidate13-NeoForge-1.21.1-20260812'
$defaultInstanceName = $instanceStem + '-Candidate14-r3-NeoForge-1.21.1-20260812'

if ([string]::IsNullOrWhiteSpace($ClientPrepareReport)) { $ClientPrepareReport = Join-Path $workspace 'outputs\candidate14-r3-client-attempt3-prepare-20260812.json' }
if ([string]::IsNullOrWhiteSpace($BuildReport)) { $BuildReport = Join-Path $workspace 'outputs\candidate14-r3-bundle-build-20260812.json' }
if ([string]::IsNullOrWhiteSpace($TemplateInstanceName)) { $TemplateInstanceName = $defaultTemplateName }
if ([string]::IsNullOrWhiteSpace($InstanceName)) { $InstanceName = $defaultInstanceName }
if ([string]::IsNullOrWhiteSpace($Report)) { $Report = Join-Path $workspace 'outputs\candidate14-r3-prism-import-20260812.json' }

function Full-Path([string] $Path) { return [IO.Path]::GetFullPath($Path).TrimEnd('\') }
function Same-Path([string] $Left, [string] $Right) { return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase) }
function Path-IsWithin([string] $Path, [string] $Parent) { return ((Full-Path $Path) + '\').StartsWith(((Full-Path $Parent) + '\'), [StringComparison]::OrdinalIgnoreCase) }
function Paths-Overlap([string] $Left, [string] $Right) { return (Path-IsWithin $Left $Right) -or (Path-IsWithin $Right $Left) }
function Sha256([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant() }
function Bytes-Sha256([byte[]] $Bytes) { $sha = [Security.Cryptography.SHA256]::Create(); try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '') } finally { $sha.Dispose() } }
function Bytes-Equal([byte[]] $Left, [byte[]] $Right) {
    if ($null -eq $Left -or $null -eq $Right -or $Left.Length -ne $Right.Length) { return $false }
    for ($i = 0; $i -lt $Left.Length; $i++) { if ($Left[$i] -ne $Right[$i]) { return $false } }
    return $true
}
function Read-Json([string] $Path) { return ([IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json) }
function Bundle-Digest([object[]] $Rows, [hashtable] $ByName) {
    $records = [Collections.Generic.List[string]]::new()
    foreach ($row in $Rows) {
        $name = [string]$row.file
        $records.Add($name + [char]0 + (Sha256 $ByName[$name].FullName))
    }
    return Bytes-Sha256 ([Text.Encoding]::UTF8.GetBytes(($records -join "`n") + "`n"))
}
function Is-Reparse([IO.FileSystemInfo] $Item) { return (([int]$Item.Attributes -band 0x400) -ne 0) }
function Copy-Tree([string] $Source, [string] $Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Source tree missing: $Source" }
    New-Item -ItemType Directory -Path $Destination | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $Source -Force)) {
        if (Is-Reparse $item) { throw "Unexpected reparse point in copied tree: $($item.FullName)" }
        $target = Join-Path $Destination $item.Name
        if ($item.PSIsContainer) { Copy-Tree $item.FullName $target } else { Copy-Item -LiteralPath $item.FullName -Destination $target }
    }
}
function U16BE([int] $Value) { return [byte[]]@([byte](($Value -shr 8) -band 255), [byte]($Value -band 255)) }
function I32BE([int] $Value) { return [byte[]]@([byte](($Value -shr 24) -band 255), [byte](($Value -shr 16) -band 255), [byte](($Value -shr 8) -band 255), [byte]($Value -band 255)) }
function Nbt-String([string] $Value) { $bytes = [Text.Encoding]::UTF8.GetBytes($Value); return [byte[]](@(U16BE $bytes.Length) + $bytes) }
function Nbt-Tag([int] $Id, [string] $Name, [byte[]] $Payload) { return [byte[]](@([byte]$Id) + (Nbt-String $Name) + $Payload) }
function New-ServersDat([string] $Address) {
    $entry = [byte[]](@(Nbt-Tag 8 'name' (Nbt-String 'Candidate14-r3 Local Test')) + (Nbt-Tag 8 'ip' (Nbt-String $Address)) + (Nbt-Tag 1 'acceptTextures' ([byte[]]@(0))) + (Nbt-Tag 1 'hidden' ([byte[]]@(1))) + [byte]0)
    $list = [byte[]](@([byte]10) + (I32BE 1) + $entry)
    return [byte[]](@([byte]10, [byte]0, [byte]0) + (Nbt-Tag 9 'servers' $list) + [byte]0)
}
function New-PreparedServersDat([string] $Address) {
    $entry = [byte[]](@(Nbt-Tag 8 'name' (Nbt-String 'Minecraft Server')) + (Nbt-Tag 8 'ip' (Nbt-String $Address)) + (Nbt-Tag 1 'acceptTextures' ([byte[]]@(0))) + (Nbt-Tag 1 'hidden' ([byte[]]@(1))) + [byte]0)
    $list = [byte[]](@([byte]10) + (I32BE 1) + $entry)
    return [byte[]](@([byte]10, [byte]0, [byte]0) + (Nbt-Tag 9 'servers' $list) + [byte]0)
}
function Read-PackFormat([string] $Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry = $zip.GetEntry('pack.mcmeta'); if ($null -eq $entry) { throw 'pack.mcmeta missing' }
        $reader = [IO.StreamReader]::new($entry.Open(), [Text.Encoding]::UTF8, $true)
        try { $metadata = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        return [int]$metadata.pack.pack_format
    } finally { $zip.Dispose() }
}
function Option-ResourcePackIds([string] $Line) {
    $values = [Collections.Generic.List[string]]::new()
    foreach ($match in [Text.RegularExpressions.Regex]::Matches($Line, '"((?:\\.|[^"])*)"')) {
        $values.Add([Text.RegularExpressions.Regex]::Unescape($match.Groups[1].Value))
    }
    return $values.ToArray()
}
function Validate-Options([string] $Path, [string] $Address) {
    $lines = [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)
    $packLine = @($lines | Where-Object { $_.StartsWith('resourcePacks:', [StringComparison]::Ordinal) })
    $serverLine = @($lines | Where-Object { $_.StartsWith('lastServer:', [StringComparison]::Ordinal) })
    $selected = if ($packLine.Count -eq 1) { @(Option-ResourcePackIds $packLine[0]) } else { @() }
    $packId = 'file/' + $packFileName
    if ($packLine.Count -ne 1 -or @($selected | Where-Object { $_ -ceq $packId }).Count -ne 1 -or @($selected | Where-Object { $_ -ceq ('file/' + $packStem + '.zip') }).Count -ne 0) { throw 'Candidate14 options.txt local resource-pack selection mismatch' }
    if ($serverLine.Count -ne 1 -or $serverLine[0] -cne ('lastServer:' + $Address)) { throw 'Candidate14 options.txt server endpoint mismatch' }
    return [ordered]@{sha256 = (Sha256 $Path); local_pack_selected_once = $true; last_server = $Address}
}
function Set-Options([string] $Path, [string] $Address) {
    $lines = [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)
    $output = [Collections.Generic.List[string]]::new()
    $foundServer = $false
    foreach ($line in $lines) {
        if ($line.StartsWith('lastServer:', [StringComparison]::Ordinal)) {
            if (-not $foundServer) { $output.Add('lastServer:' + $Address); $foundServer = $true }
        } else { $output.Add($line) }
    }
    if (-not $foundServer) { $output.Add('lastServer:' + $Address) }
    [IO.File]::WriteAllText($Path, (($output.ToArray() -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
}
function Validate-Mods([string] $Root, [object[]] $Rows, [string] $ExpectedDigest, [string] $DirectoryName = 'mods') {
    $mods = Join-Path $Root $DirectoryName
    if (-not (Test-Path -LiteralPath $mods -PathType Container) -or (Is-Reparse (Get-Item -LiteralPath $mods -Force))) { throw 'Client mods directory is missing or linked' }
    $entries = @(Get-ChildItem -LiteralPath $mods -Force)
    $files = @($entries | Where-Object { -not $_.PSIsContainer } | Sort-Object Name)
    if ($entries.Count -ne $expectedJarCount -or $files.Count -ne $expectedJarCount -or @($files | Where-Object { $_.Extension -ine '.jar' -or (Is-Reparse $_) }).Count -ne 0) { throw 'Client root must contain the exact Candidate14-r3 54-JAR release snapshot' }
    $byName = @{}; foreach ($file in $files) { if ($byName.ContainsKey($file.Name)) { throw "Duplicate client JAR filename: $($file.Name)" }; $byName[$file.Name] = $file }
    foreach ($row in $Rows) {
        $name = [string]$row.file
        if (-not $byName.ContainsKey($name)) { throw "Client JAR missing: $name" }
        if ($byName[$name].Length -ne [long]$row.bytes -or (Sha256 $byName[$name].FullName) -ne ([string]$row.sha256).ToUpperInvariant()) { throw "Client JAR mismatch: $name" }
    }
    $digest = Bundle-Digest $Rows $byName
    $bytes = [long](($files | Measure-Object Length -Sum).Sum)
    if ($digest -ne $ExpectedDigest -or $bytes -ne $expectedJarBytes) { throw 'Client bundle aggregate differs from Candidate14-r3 manifest' }
    return [ordered]@{files = $files.Count; bytes = $bytes; bundle_sha256 = $digest}
}
function Validate-Release([string] $Root, [string] $BuildPath) {
    $readyPath = Join-Path $Root 'READY.json'; $lockPath = Join-Path $Root 'release-lock.json'; $manifestPath = Join-Path $Root 'manifests\client.json'; $publishedMods = Join-Path $Root 'client-mods'
    foreach ($path in @($readyPath, $lockPath, $manifestPath, $BuildPath)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Candidate14 release binding file missing: $path" } }
    if ((Sha256 $readyPath) -ne $expectedReadySha -or (Sha256 $lockPath) -ne $expectedReadySha -or (Sha256 $manifestPath) -ne $expectedManifestSha -or (Sha256 $BuildPath) -ne $expectedBuildReportSha) { throw 'Candidate14-r3 release/build fingerprint mismatch' }
    if (-not (Bytes-Equal ([IO.File]::ReadAllBytes($readyPath)) ([IO.File]::ReadAllBytes($lockPath)))) { throw 'Candidate14 READY and release-lock are not byte-identical' }
    $ready = Read-Json $readyPath; $manifest = Read-Json $manifestPath; $build = Read-Json $BuildPath
    if ([int]$ready.candidate -ne 14 -or [string]$ready.status -cne 'PASS' -or -not (Same-Path ([string]$ready.output_root) $Root)) { throw 'Candidate14 READY identity mismatch' }
    if ([string]$ready.extension_policy.release_lock_semantics -cne 'acceptance_snapshot_not_permanent_allowlist' -or $ready.extension_policy.current_file_counts_are_not_production_caps -ne $true -or $ready.extension_policy.additive_client_mods_allowed -ne $true -or $ready.extension_policy.permanent_exact_mod_count_enforcement -ne $false) { throw 'Candidate14 extension policy would lock future client mods' }
    if ([int]$manifest.candidate -ne 14 -or [string]$manifest.status -cne 'PASS' -or [string]$manifest.side -cne 'client' -or [int]$manifest.file_count -ne $expectedJarCount -or [long]$manifest.bytes -ne $expectedJarBytes -or ([string]$manifest.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha -or -not (Same-Path ([string]$manifest.bundle_dir) $publishedMods)) { throw 'Candidate14 client manifest header/aggregate mismatch' }
    if ([int]$ready.client.file_count -ne $expectedJarCount -or [long]$ready.client.bytes -ne $expectedJarBytes -or ([string]$ready.client.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha -or ([string]$ready.client.manifest_sha256).ToUpperInvariant() -ne $expectedManifestSha -or ([string]$ready.bundle_pair_sha256).ToUpperInvariant() -ne $expectedPairSha) { throw 'Candidate14 READY client binding mismatch' }
    if ([string]$build.status -cne 'PASS' -or -not (Same-Path ([string]$build.output_root) $Root) -or ([string]$build.ready_sha256).ToUpperInvariant() -ne $expectedReadySha -or ([string]$build.client_manifest_sha256).ToUpperInvariant() -ne $expectedManifestSha -or ([string]$build.client_bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha -or ([string]$build.bundle_pair_sha256).ToUpperInvariant() -ne $expectedPairSha) { throw 'Candidate14 build report is not bound to this release' }
    $rows = @($manifest.files)
    if ($rows.Count -ne $expectedJarCount) { throw 'Candidate14 client manifest row count mismatch' }
    $idIndex = @{}
    foreach ($row in $rows) {
        $name = [string]$row.file
        if ([IO.Path]::GetFileName($name) -cne $name -or -not $name.EndsWith('.jar', [StringComparison]::OrdinalIgnoreCase) -or [long]$row.bytes -le 0 -or ([string]$row.sha256).ToUpperInvariant() -notmatch '^[0-9A-F]{64}$') { throw "Invalid Candidate14 client manifest row: $name" }
        foreach ($modId in @($row.mod_ids)) { if ($idIndex.ContainsKey([string]$modId)) { throw "Duplicate Candidate14 client mod ID: $modId" }; $idIndex[[string]$modId] = $name }
    }
    foreach ($required in @('cctweaked_startup_guard', 'create_chute_unload_guard', 'deferred_content_protection', 'kaleidoscope_cookery_scarecrow_compat')) { if (-not $idIndex.ContainsKey($required)) { throw "Candidate14 safety mod absent: $required" } }
    if ($idIndex.ContainsKey('mcmodsync') -or @($rows | Where-Object { ([string]$_.file) -match '(?i)mcmodsync' }).Count -ne 0) { throw 'MCModSync must remain uninstalled until its locked HTTPS configuration exists' }
    $published = Validate-Mods $Root $rows $expectedBundleSha 'client-mods'
    return [ordered]@{ready = $ready; manifest = $manifest; rows = $rows; published_bundle = $published; ready_sha256 = $expectedReadySha; manifest_sha256 = $expectedManifestSha; build_report_sha256 = $expectedBuildReportSha; bundle_sha256 = $expectedBundleSha; pair_sha256 = $expectedPairSha}
}
function Validate-Shared-Roots([string] $Root, [string] $Release) {
    foreach ($name in @('assets', 'libraries', 'versions')) {
        $item = Get-Item -LiteralPath (Join-Path $Root $name) -Force
        if (-not $item.PSIsContainer -or -not (Is-Reparse $item) -or [string]$item.LinkType -cne 'Junction') { throw "Candidate14 shared client path must be a junction: $name" }
        $resolved = Full-Path ([string]$item.Target)
        if (Path-IsWithin $resolved '<TRANS_ROOT>\20260807' -or (Paths-Overlap $resolved $Release)) { throw "Candidate14 shared client path resolves into protected data: $resolved" }
    }
    foreach ($name in @('config', 'data', 'defaultconfigs', 'mods', 'resourcepacks')) {
        $item = Get-Item -LiteralPath (Join-Path $Root $name) -Force
        if (-not $item.PSIsContainer -or (Is-Reparse $item)) { throw "Candidate14 mutable client path must be an ordinary directory: $name" }
    }
}
function Validate-Instance-Metadata([string] $Instance) {
    $mmcPath = Join-Path $Instance 'mmc-pack.json'; $cfgPath = Join-Path $Instance 'instance.cfg'
    if (-not (Test-Path -LiteralPath $mmcPath -PathType Leaf) -or -not (Test-Path -LiteralPath $cfgPath -PathType Leaf)) { throw "Prism instance metadata missing: $Instance" }
    $mmc = Read-Json $mmcPath
    $minecraft = @($mmc.components | Where-Object { [string]$_.uid -ceq 'net.minecraft' })
    $neoforge = @($mmc.components | Where-Object { [string]$_.uid -ceq 'net.neoforged' })
    if ($minecraft.Count -ne 1 -or [string]$minecraft[0].version -cne '1.21.1' -or $neoforge.Count -ne 1 -or [string]$neoforge[0].version -cne '21.1.241') { throw 'Prism template is not Minecraft 1.21.1 / NeoForge 21.1.241' }
    return [ordered]@{mmc_path = $mmcPath; cfg_path = $cfgPath; mmc_sha256 = (Sha256 $mmcPath); cfg_sha256 = (Sha256 $cfgPath); minecraft = '1.21.1'; neoforge = '21.1.241'}
}
function Set-Cfg([string] $Path, [string] $Name) {
    $cfg = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    foreach ($required in @('name=', 'MinMemAlloc=', 'MaxMemAlloc=', 'OverrideMemory=', 'JoinServerOnLaunch=', 'lastLaunchTime=', 'lastTimePlayed=', 'totalTimePlayed=')) { if ($cfg -notmatch ('(?m)^' + [Regex]::Escape($required))) { throw "Template instance.cfg lacks $required" } }
    $replacements = [ordered]@{
        'name' = $Name; 'OverrideMemory' = 'true'; 'MinMemAlloc' = [string]$MinMemoryMb; 'MaxMemAlloc' = [string]$MaxMemoryMb; 'JoinServerOnLaunch' = 'false'; 'lastLaunchTime' = '0'; 'lastTimePlayed' = '0'; 'totalTimePlayed' = '0'
    }
    foreach ($key in $replacements.Keys) { $cfg = [Regex]::Replace($cfg, '(?m)^' + [Regex]::Escape($key) + '=.*$', $key + '=' + $replacements[$key], 1) }
    [IO.File]::WriteAllText($Path, $cfg, [Text.UTF8Encoding]::new($false))
}
function Validate-Cfg([string] $Path, [string] $Name) {
    $cfg = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    foreach ($line in @(
        ('name=' + $Name),
        'OverrideMemory=true',
        ('MinMemAlloc=' + $MinMemoryMb),
        ('MaxMemAlloc=' + $MaxMemoryMb),
        'JoinServerOnLaunch=false',
        'lastLaunchTime=0',
        'lastTimePlayed=0',
        'totalTimePlayed=0'
    )) { if ($cfg -notmatch ('(?m)^' + [Regex]::Escape([string]$line) + '$')) { throw "Published Candidate14 instance.cfg mismatch: $line" } }
    return [ordered]@{sha256 = (Sha256 $Path); minimum_mb = $MinMemoryMb; maximum_mb = $MaxMemoryMb; join_server_on_launch = $false}
}
function Write-NewUtf8([string] $Path, [string] $Value) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value); $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
}

$client = Full-Path $ClientRoot; $prism = Full-Path $PrismRoot; $release = Full-Path $ReleaseRoot; $buildPath = Full-Path $BuildReport; $preparePath = Full-Path $ClientPrepareReport; $report = Full-Path $Report
$reportSidecar = $report + '.sha256'
if (-not (Same-Path $client $expectedClientRoot)) { throw "Candidate14 client root is not the locked audited D-drive root: $client" }
if (-not (Same-Path $release $expectedRelease)) { throw "Candidate14 release path is not locked: $release" }
if (-not (Path-IsWithin $report (Join-Path $workspace 'outputs'))) { throw 'Prism import report must remain under workspace outputs' }
if ($ServerAddress -notmatch '^(\[[^\]]+\]|[^:]+):12341$') { throw 'Candidate14 manual-test endpoint must retain port 12341' }
if ($MinMemoryMb -lt 1024 -or $MaxMemoryMb -lt $MinMemoryMb -or $MaxMemoryMb -gt 6144) { throw 'Candidate14 manual-test memory must stay between 1 GiB and 6 GiB' }
foreach ($path in @($client, $release, $prism)) { if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Required directory missing: $path" } }
if ((Is-Reparse (Get-Item -LiteralPath $client -Force)) -or (Is-Reparse (Get-Item -LiteralPath $release -Force))) { throw 'Candidate14 client/release root may not be a reparse point' }
if (-not (Test-Path -LiteralPath (Join-Path $prism 'portable.txt') -PathType Leaf)) { throw "Not a Prism portable root: $prism" }
$instances = Join-Path $prism 'instances'; $template = Join-Path $instances $TemplateInstanceName; $target = Join-Path $instances $InstanceName
if (-not (Test-Path -LiteralPath $instances -PathType Container) -or -not (Test-Path -LiteralPath $template -PathType Container)) { throw 'Prism instances/template directory missing' }
if (-not (Path-IsWithin $template $instances) -or -not (Path-IsWithin $target $instances) -or (Same-Path $template $target)) { throw 'Prism instance isolation failed' }
if (-not $PreflightOnly.IsPresent -and (Test-Path -LiteralPath $target)) { throw "Refusing to overwrite existing Candidate14-r3 Prism instance: $target" }
if (-not $PreflightOnly.IsPresent -and ((Test-Path -LiteralPath $report) -or (Test-Path -LiteralPath $reportSidecar))) { throw 'Refusing to overwrite existing Candidate14-r3 Prism import evidence' }
if ((Sha256 $preparePath) -ne $expectedPrepareReportSha) { throw 'Candidate14 client prepare report fingerprint mismatch' }
$prepare = Read-Json $preparePath
if ([string]$prepare.status -cne 'PREPARED' -or [int]$prepare.candidate -ne 14 -or -not (Same-Path ([string]$prepare.output_root) $client) -or -not (Same-Path ([string]$prepare.release.root) $release) -or ([string]$prepare.release.ready_sha256).ToUpperInvariant() -ne $expectedReadySha -or ([string]$prepare.release.client_manifest_sha256).ToUpperInvariant() -ne $expectedManifestSha -or ([string]$prepare.release.client_bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha -or [int]$prepare.release.file_count -ne $expectedJarCount -or $prepare.release.permanent_mod_count_cap -ne $false -or [string]$prepare.mcmodsync.runtime_install -cne 'NOT_INSTALLED') { throw 'Candidate14 client prepare report binding mismatch' }
$sourceAddress = [string]$prepare.server.address
if ($sourceAddress -notmatch '^(\[[^\]]+\]|[^:]+):12341$' -or $prepare.server.accept_remote_resource_pack -ne $false -or $prepare.server.servers_dat_acceptTextures -ne $false) { throw 'Candidate14 source client server/resource-pack policy mismatch' }
$releaseState = Validate-Release $release $buildPath
Validate-Shared-Roots $client $release
$sourceBundle = Validate-Mods $client $releaseState.rows $expectedBundleSha
$sourceOptions = Validate-Options (Join-Path $client 'options.txt') $sourceAddress
$sourceServers = Join-Path $client 'servers.dat'
if (-not (Test-Path -LiteralPath $sourceServers -PathType Leaf)) { throw 'Candidate14 source servers.dat is missing' }
$sourceServersBytes = [IO.File]::ReadAllBytes($sourceServers)
$sourceServersAllowed = (Bytes-Equal $sourceServersBytes (New-PreparedServersDat $sourceAddress)) -or (Bytes-Equal $sourceServersBytes (New-PreparedServersDat '127.0.0.1:12341'))
if (-not $sourceServersAllowed) { throw 'Candidate14 source servers.dat is not an audited port-12341 remote-pack rejection payload' }
$pack = Join-Path $client ('resourcepacks\' + $packFileName)
$packEntries = @(Get-ChildItem -LiteralPath (Join-Path $client 'resourcepacks') -Force)
if ($packEntries.Count -ne 1 -or -not (Test-Path -LiteralPath $pack -PathType Leaf) -or (Is-Reparse (Get-Item -LiteralPath $pack -Force)) -or (Get-Item -LiteralPath $pack).Length -ne $expectedPackBytes -or (Sha256 $pack) -ne $expectedPackSha -or (Read-PackFormat $pack) -ne $expectedPackFormat) { throw 'Candidate14 source local resource pack fingerprint/policy mismatch' }
$templateState = Validate-Instance-Metadata $template

if ($PreflightOnly.IsPresent) {
    [ordered]@{
        schema = 1; status = 'PREFLIGHT_PASS'; candidate = 14; release_revision = 'r3'; client_root = $client; client_prepare_report = $preparePath; target_instance = $target; target_already_exists = (Test-Path -LiteralPath $target); template_instance = $template
        release = [ordered]@{ready_sha256 = $expectedReadySha; client_manifest_sha256 = $expectedManifestSha; build_report_sha256 = $expectedBuildReportSha; client_bundle_sha256 = $expectedBundleSha; bundle_pair_sha256 = $expectedPairSha; files = $expectedJarCount; bytes = $expectedJarBytes; release_scoped_exactness = $true; permanent_mod_count_cap = $false}
        client_bundle = $sourceBundle; local_resource_pack = [ordered]@{path = $pack; sha256 = $expectedPackSha; bytes = $expectedPackBytes; pack_format = $expectedPackFormat; enabled_exactly_once = $true}
        resource_pack_policy = [ordered]@{remote_server_pack = 'REJECT'; acceptTextures = $false; source_address = $sourceAddress; manual_test_address = $ServerAddress}
        mcmodsync = [ordered]@{runtime_install = 'NOT_INSTALLED'; future_install_requires_locked_config_and_https_manifest = $true}
        memory = [ordered]@{minimum_mb = $MinMemoryMb; maximum_mb = $MaxMemoryMb}; minecraft = '1.21.1'; neoforge = '21.1.241'; writes_performed = 0; java_started = $false; prism_started = $false
    } | ConvertTo-Json -Depth 12
    exit 0
}

$temp = Join-Path $instances ('.candidate14-r3-import-' + [Guid]::NewGuid().ToString('N')); $tempMc = Join-Path $temp 'minecraft'; $published = $false; $reportWritten = $false; $sidecarWritten = $false
try {
    New-Item -ItemType Directory -Path $tempMc | Out-Null
    foreach ($name in @('assets', 'libraries', 'versions')) {
        $source = Get-Item -LiteralPath (Join-Path $client $name) -Force
        $resolved = Full-Path ([string]$source.Target)
        New-Item -ItemType Junction -Path (Join-Path $tempMc $name) -Target $resolved | Out-Null
    }
    foreach ($name in @('config', 'data', 'defaultconfigs')) { Copy-Tree (Join-Path $client $name) (Join-Path $tempMc $name) }
    New-Item -ItemType Directory -Path (Join-Path $tempMc 'mods') | Out-Null
    foreach ($row in $releaseState.rows) { Copy-Item -LiteralPath (Join-Path $client ('mods\' + [string]$row.file)) -Destination (Join-Path $tempMc ('mods\' + [string]$row.file)) }
    New-Item -ItemType Directory -Path (Join-Path $tempMc 'resourcepacks') | Out-Null
    Copy-Item -LiteralPath $pack -Destination (Join-Path $tempMc ('resourcepacks\' + $packFileName))
    New-Item -ItemType Directory -Path (Join-Path $tempMc 'natives') | Out-Null
    Copy-Item -LiteralPath (Join-Path $client 'options.txt') -Destination (Join-Path $tempMc 'options.txt')
    Set-Options (Join-Path $tempMc 'options.txt') $ServerAddress
    [IO.File]::WriteAllBytes((Join-Path $tempMc 'servers.dat'), (New-ServersDat $ServerAddress))
    Copy-Item -LiteralPath $templateState.mmc_path -Destination (Join-Path $temp 'mmc-pack.json')
    Copy-Item -LiteralPath $templateState.cfg_path -Destination (Join-Path $temp 'instance.cfg')
    Set-Cfg (Join-Path $temp 'instance.cfg') $InstanceName
    $icon = Join-Path $template 'icon.png'; if (Test-Path -LiteralPath $icon -PathType Leaf) { Copy-Item -LiteralPath $icon -Destination (Join-Path $temp 'icon.png') }

    $allowed = @('assets', 'config', 'data', 'defaultconfigs', 'libraries', 'mods', 'natives', 'options.txt', 'resourcepacks', 'servers.dat', 'versions')
    $actual = @(Get-ChildItem -LiteralPath $tempMc -Force | ForEach-Object { $_.Name })
    if (@($actual | Where-Object { $allowed -notcontains $_ }).Count -ne 0) { throw 'Unexpected runtime state leaked into Candidate14-r3 Prism minecraft root' }
    Validate-Shared-Roots $tempMc $release
    $targetBundle = Validate-Mods $tempMc $releaseState.rows $expectedBundleSha
    $targetOptions = Validate-Options (Join-Path $tempMc 'options.txt') $ServerAddress
    $targetServers = New-ServersDat $ServerAddress
    if (-not (Bytes-Equal ([IO.File]::ReadAllBytes((Join-Path $tempMc 'servers.dat'))) $targetServers) -or @(Get-ChildItem -LiteralPath (Join-Path $tempMc 'resourcepacks') -Force).Count -ne 1 -or (Sha256 (Join-Path $tempMc ('resourcepacks\' + $packFileName))) -ne $expectedPackSha) { throw 'Published Candidate14-r3 resource/server policy mismatch' }
    $targetCfg = Validate-Cfg (Join-Path $temp 'instance.cfg') $InstanceName
    $targetMetadata = Validate-Instance-Metadata $temp
    if ((Sha256 $templateState.mmc_path) -ne $templateState.mmc_sha256 -or (Sha256 $templateState.cfg_path) -ne $templateState.cfg_sha256) { throw 'Candidate13 template changed during Candidate14 import' }

    Move-Item -LiteralPath $temp -Destination $target; $published = $true; $temp = $null
    $reportValue = [ordered]@{
        schema = 1; status = 'IMPORTED_PRISM_INSTANCE'; candidate = 14; release_revision = 'r3'; ready_for_manual_launch = $true; imported_at_utc = [DateTime]::UtcNow.ToString('o')
        source_client_root = $client; source_client_prepare_report = $preparePath; source_client_prepare_report_sha256 = $expectedPrepareReportSha; source_client_unchanged = $true
        source_template_instance = $template; source_template_unchanged = $true; template_mmc_sha256 = $templateState.mmc_sha256; template_instance_cfg_sha256 = $templateState.cfg_sha256
        instance_name = $InstanceName; instance_path = $target; minecraft_path = (Join-Path $target 'minecraft'); minecraft = '1.21.1'; neoforge = '21.1.241'
        release = [ordered]@{root = $release; ready_sha256 = $expectedReadySha; client_manifest_sha256 = $expectedManifestSha; build_report = $buildPath; build_report_sha256 = $expectedBuildReportSha; client_bundle_sha256 = $expectedBundleSha; bundle_pair_sha256 = $expectedPairSha; file_count = $targetBundle.files; bytes = $targetBundle.bytes; release_scoped_exactness = $true; permanent_mod_count_cap = $false}
        local_resource_pack = [ordered]@{file = $packFileName; sha256 = $expectedPackSha; bytes = $expectedPackBytes; pack_format = $expectedPackFormat; enabled_exactly_once = $true}
        resource_pack_policy = [ordered]@{remote_server_pack = 'REJECT'; acceptTextures = $false; source_address = $sourceAddress; manual_test_address = $ServerAddress; production_server_configuration_modified = $false; servers_dat_sha256 = (Sha256 (Join-Path $target 'minecraft\servers.dat')); options_sha256 = $targetOptions.sha256}
        mcmodsync = [ordered]@{runtime_install = 'NOT_INSTALLED'; audited_for_future_ota = $true; installation_deferred_until_locked_config_and_https_manifest = $true}
        memory = [ordered]@{minimum_mb = $MinMemoryMb; maximum_mb = $MaxMemoryMb}; instance_cfg_sha256 = $targetCfg.sha256; mmc_pack_sha256 = $targetMetadata.mmc_sha256
        excluded_runtime_state = @('logs', 'saves', 'downloads', 'screenshots', 'journeymap', 'schematics', 'server-resource-packs', 'server-resource-packs-cache', 'cache')
        java_started_by_importer = $false; prism_started_by_importer = $false; manual_action = 'Refresh the already-open Prism window if needed, then launch this new Candidate14-r3 instance for manual testing.'
    }
    $json = ($reportValue | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    Write-NewUtf8 $report $json; $reportWritten = $true
    $reportHash = Sha256 $report
    Write-NewUtf8 $reportSidecar ($reportHash + '  ' + [IO.Path]::GetFileName($report) + [Environment]::NewLine); $sidecarWritten = $true
    [ordered]@{status = 'IMPORTED_PRISM_INSTANCE'; instance_path = $target; report = $report; report_sha256 = $reportHash; report_sha256_sidecar = $reportSidecar; client_bundle_sha256 = $expectedBundleSha; local_resource_pack_sha256 = $expectedPackSha; java_started = $false; prism_started = $false} | ConvertTo-Json -Depth 6
} catch {
    if ($sidecarWritten -and (Test-Path -LiteralPath $reportSidecar)) { Remove-Item -LiteralPath $reportSidecar -Force }
    if ($reportWritten -and (Test-Path -LiteralPath $report)) { Remove-Item -LiteralPath $report -Force }
    if ($published -and (Test-Path -LiteralPath $target)) { Remove-Item -LiteralPath $target -Recurse -Force }
    if ($null -ne $temp -and (Test-Path -LiteralPath $temp)) { Remove-Item -LiteralPath $temp -Recurse -Force }
    throw
}
