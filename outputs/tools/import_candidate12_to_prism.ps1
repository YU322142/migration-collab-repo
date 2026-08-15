param(
    [Parameter(Mandatory = $true)]
    [string] $ExpectedReleaseSha256,

    [Parameter(Mandatory = $true)]
    [string] $ExpectedWaypointSha256,

    [string] $PrismRoot = 'D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3',
    [string] $ReleaseRoot = 'D:\Trans\migration-audit-work\final-mod-bundles-candidate12-20260811',
    [string] $SourceInstanceName = '',
    [string] $InstanceName = '',
    [string] $Report = ''
)

$ErrorActionPreference = 'Stop'

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$defaultSourceName = ([char]0x52a8) + ([char]0x9759) + ([char]0x4ea4) + ([char]0x6620) + '-Candidate11-NeoForge-1.21.1-20260811'
$defaultTargetName = ([char]0x52a8) + ([char]0x9759) + ([char]0x4ea4) + ([char]0x6620) + '-Candidate12-NeoForge-1.21.1-20260811'
if ([string]::IsNullOrWhiteSpace($SourceInstanceName)) { $SourceInstanceName = $defaultSourceName }
if ([string]::IsNullOrWhiteSpace($InstanceName)) { $InstanceName = $defaultTargetName }
if ([string]::IsNullOrWhiteSpace($Report)) {
    $Report = Join-Path $workspace 'outputs\candidate12-prism-import-20260811.json'
}

$candidate11Release = 'D:\Trans\migration-audit-work\final-mod-bundles-candidate11-20260811'
$candidate11ReadySha = '613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E'
$candidate11ClientManifestSha = '1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D'
$candidate11ClientBundleSha = 'CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B'
$rejectedWaypointSha = '5572EE1F196038071FB5D7B9D7FF271CCB0E19BA722B83BCC1A2B8C0C844F8EB'
$waypointModId = 'waypoint_fire_equivalence'

function Full-Path([string] $Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Same-Path([string] $Left, [string] $Right) {
    return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase)
}

function Path-Is-Within([string] $Path, [string] $Parent) {
    $full = (Full-Path $Path) + '\'
    $base = (Full-Path $Parent) + '\'
    return $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)
}

function File-Sha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Normalize-Sha256([string] $Value, [string] $Label) {
    $normalized = $Value.Trim().ToUpperInvariant()
    if ($normalized -notmatch '^[0-9A-F]{64}$') { throw "$Label is not a SHA-256" }
    return $normalized
}

function Bytes-Sha256([byte[]] $Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '') }
    finally { $sha.Dispose() }
}

function Bundle-Digest([object[]] $Rows, [hashtable] $FilesByName) {
    $records = [Collections.Generic.List[string]]::new()
    foreach ($row in $Rows) {
        $name = [string]$row.file
        if (-not $FilesByName.ContainsKey($name)) { throw "Missing JAR: $name" }
        $records.Add($name + [char]0 + (File-Sha256 $FilesByName[$name].FullName))
    }
    return Bytes-Sha256 ([Text.Encoding]::UTF8.GetBytes(($records -join "`n") + "`n"))
}

function Validate-ManifestNamesAndModIds([object[]] $Rows, [string] $Label) {
    $names = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $owners = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($row in $Rows) {
        $name = [string]$row.file
        if ([IO.Path]::GetFileName($name) -cne $name -or -not $name.EndsWith('.jar', [StringComparison]::OrdinalIgnoreCase)) {
            throw "$Label unsafe JAR name: $name"
        }
        if (-not $names.Add($name)) { throw "$Label duplicate filename: $name" }
        foreach ($modId in @($row.mod_ids)) {
            $id = [string]$modId
            if ($owners.ContainsKey($id)) { throw "$Label duplicate mod ID $id in $($owners[$id]) and $name" }
            $owners[$id] = $name
        }
    }
}

function Validate-ModDirectory([string] $Directory, [object] $Manifest, [string] $ExpectedBundle) {
    $jars = @(Get-ChildItem -LiteralPath $Directory -Force -File | Sort-Object Name)
    if ($jars.Count -ne 52 -or @($jars | Where-Object { $_.Extension -ine '.jar' }).Count -ne 0) {
        throw "Mod directory must contain exactly 52 regular JARs: $Directory"
    }
    $byName = @{}
    foreach ($jar in $jars) {
        if ($byName.ContainsKey($jar.Name)) { throw "Duplicate mod filename: $($jar.Name)" }
        $byName[$jar.Name] = $jar
    }
    [long] $totalBytes = 0
    foreach ($row in @($Manifest.files)) {
        $name = [string]$row.file
        if (-not $byName.ContainsKey($name)) { throw "Manifest JAR missing: $name" }
        $jar = $byName[$name]
        $actualHash = File-Sha256 $jar.FullName
        if ($jar.Length -ne [long]$row.bytes -or $actualHash -cne ([string]$row.sha256).ToUpperInvariant()) {
            throw "Manifest JAR mismatch: $name"
        }
        $totalBytes += $jar.Length
    }
    $bundle = Bundle-Digest @($Manifest.files) $byName
    if ($totalBytes -ne [long]$Manifest.bytes -or $bundle -cne $ExpectedBundle) {
        throw "Mod bundle aggregate mismatch: $Directory"
    }
    return [ordered]@{ files = $jars.Count; bytes = $totalBytes; bundle_sha256 = $bundle }
}

function Write-Utf8NoBomCreateNew([string] $Path, [string] $Text) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Text)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}

function Write-Utf8NoBom([string] $Path, [string] $Text) {
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Copy-Tree([string] $Source, [string] $Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
    New-Item -ItemType Directory -Path $Destination | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        $target = Join-Path $Destination $_.Name
        if ($_.PSIsContainer) { Copy-Tree $_.FullName $target }
        else { Copy-Item -LiteralPath $_.FullName -Destination $target }
    }
}

$expectedRelease = Normalize-Sha256 $ExpectedReleaseSha256 'Expected release SHA-256'
$expectedWaypoint = Normalize-Sha256 $ExpectedWaypointSha256 'Expected Waypoint SHA-256'
if ($expectedWaypoint -ceq $rejectedWaypointSha) { throw 'Refusing the rejected Candidate11 Waypoint JAR' }

$prism = Full-Path $PrismRoot
$instances = Join-Path $prism 'instances'
$release = Full-Path $ReleaseRoot
$sourceInstance = Join-Path $instances $SourceInstanceName
$target = Join-Path $instances $InstanceName
$reportPath = Full-Path $Report
$manifestPath = Join-Path $release 'manifests\client.json'
$releaseLockPath = Join-Path $release 'release-lock.json'
$readyPath = Join-Path $release 'READY.json'
$candidate11ManifestPath = Join-Path $candidate11Release 'manifests\client.json'
$candidate11ReadyPath = Join-Path $candidate11Release 'READY.json'

if (-not (Test-Path -LiteralPath (Join-Path $prism 'portable.txt') -PathType Leaf)) { throw "Not a Prism portable root: $prism" }
if (-not (Test-Path -LiteralPath $instances -PathType Container)) { throw "Prism instances directory missing: $instances" }
if (-not (Test-Path -LiteralPath $sourceInstance -PathType Container)) { throw "Candidate11 source instance missing: $sourceInstance" }
if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite existing Candidate12 Prism instance: $target" }
if (Test-Path -LiteralPath $reportPath) { throw "Refusing to overwrite existing Candidate12 import report: $reportPath" }
if (Same-Path $sourceInstance $target) { throw 'Candidate11 source and Candidate12 target instance must differ' }
if (-not (Path-Is-Within $sourceInstance $instances) -or -not (Path-Is-Within $target $instances)) { throw 'Prism instance path isolation failed' }
if (-not (Path-Is-Within $reportPath $workspace)) { throw 'Import report must remain under workspace outputs' }
foreach ($path in @($manifestPath, $releaseLockPath, $readyPath, $candidate11ManifestPath, $candidate11ReadyPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required release file missing: $path" }
}

if ((File-Sha256 $releaseLockPath) -cne $expectedRelease -or (File-Sha256 $readyPath) -cne $expectedRelease) {
    throw 'Candidate12 release fingerprint mismatch'
}
if (-not [Linq.Enumerable]::SequenceEqual([IO.File]::ReadAllBytes($releaseLockPath), [IO.File]::ReadAllBytes($readyPath))) {
    throw 'Candidate12 READY/release-lock bytes differ'
}
if ((File-Sha256 $candidate11ReadyPath) -cne $candidate11ReadySha -or (File-Sha256 $candidate11ManifestPath) -cne $candidate11ClientManifestSha) {
    throw 'Frozen Candidate11 source release fingerprint mismatch'
}

$lock = Get-Content -LiteralPath $releaseLockPath -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$candidate11Manifest = Get-Content -LiteralPath $candidate11ManifestPath -Raw | ConvertFrom-Json
if ([int]$lock.candidate -ne 12 -or [string]$lock.status -cne 'PASS') { throw 'Release lock is not Candidate12 PASS' }
if ([int]$manifest.candidate -ne 12 -or [string]$manifest.status -cne 'PASS' -or [string]$manifest.side -cne 'client') { throw 'Client manifest is not Candidate12 PASS' }
if ([int]$manifest.file_count -ne 52 -or [int]$lock.client.file_count -ne 52) { throw 'Candidate12 client file count mismatch' }
$manifestSha = File-Sha256 $manifestPath
$clientBundle = ([string]$manifest.bundle_sha256).ToUpperInvariant()
if ($manifestSha -cne ([string]$lock.client.manifest_sha256).ToUpperInvariant() -or $clientBundle -cne ([string]$lock.client.bundle_sha256).ToUpperInvariant()) {
    throw 'Candidate12 client manifest/release binding mismatch'
}
if ([string]$lock.replacement.mod_id -cne $waypointModId -or ([string]$lock.replacement.after_sha256).ToUpperInvariant() -cne $expectedWaypoint) {
    throw 'Candidate12 Waypoint release binding mismatch'
}
if ([string]$lock.replacement.before_sha256 -cne $rejectedWaypointSha) { throw 'Candidate12 rejected-byte provenance mismatch' }
Validate-ManifestNamesAndModIds @($manifest.files) 'Candidate12 client'
$waypointRows = @($manifest.files | Where-Object { @($_.mod_ids) -contains $waypointModId })
if ($waypointRows.Count -ne 1 -or ([string]$waypointRows[0].sha256).ToUpperInvariant() -cne $expectedWaypoint) {
    throw 'Candidate12 manifest must contain exactly one fixed Waypoint owner'
}
if (@($manifest.files | Where-Object { ([string]$_.sha256).ToUpperInvariant() -ceq $rejectedWaypointSha }).Count -ne 0) {
    throw 'Candidate12 client still contains the rejected Waypoint bytes'
}

$releaseMods = Join-Path $release 'client-mods'
$releaseState = Validate-ModDirectory $releaseMods $manifest $clientBundle
$sourceMinecraft = Join-Path $sourceInstance 'minecraft'
$sourceMods = Join-Path $sourceMinecraft 'mods'
if (-not (Test-Path -LiteralPath $sourceMinecraft -PathType Container)) { throw "Candidate11 minecraft root missing: $sourceMinecraft" }
if ([int]$candidate11Manifest.candidate -ne 11 -or [int]$candidate11Manifest.file_count -ne 52 -or ([string]$candidate11Manifest.bundle_sha256).ToUpperInvariant() -cne $candidate11ClientBundleSha) {
    throw 'Frozen Candidate11 client manifest content mismatch'
}
$sourceStateBefore = Validate-ModDirectory $sourceMods $candidate11Manifest $candidate11ClientBundleSha
$sourceControlHashes = [ordered]@{}
foreach ($relative in @('instance.cfg', 'mmc-pack.json', 'minecraft\options.txt', 'minecraft\servers.dat')) {
    $path = Join-Path $sourceInstance $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Candidate11 source control file missing: $path" }
    $sourceControlHashes[$relative] = File-Sha256 $path
}

$mmc = Get-Content -LiteralPath (Join-Path $sourceInstance 'mmc-pack.json') -Raw | ConvertFrom-Json
$components = @($mmc.components)
$minecraftComponent = @($components | Where-Object { [string]$_.uid -ceq 'net.minecraft' })
$neoforgeComponent = @($components | Where-Object { [string]$_.uid -ceq 'net.neoforged' })
if ($minecraftComponent.Count -ne 1 -or [string]$minecraftComponent[0].version -cne '1.21.1') { throw 'Candidate11 Prism Minecraft component changed' }
if ($neoforgeComponent.Count -ne 1 -or [string]$neoforgeComponent[0].version -cne '21.1.241') { throw 'Candidate11 Prism NeoForge component changed' }

$temp = Join-Path $instances ('.candidate12-import-' + [Guid]::NewGuid().ToString('N'))
$minecraft = Join-Path $temp 'minecraft'
if (-not (Path-Is-Within $temp $instances)) { throw 'Temporary Prism path isolation failed' }

try {
    New-Item -ItemType Directory -Path $minecraft | Out-Null
    foreach ($name in @('config', 'defaultconfigs', 'data', 'resourcepacks')) {
        Copy-Tree (Join-Path $sourceMinecraft $name) (Join-Path $minecraft $name)
    }
    foreach ($name in @('options.txt', 'servers.dat')) {
        Copy-Item -LiteralPath (Join-Path $sourceMinecraft $name) -Destination (Join-Path $minecraft $name)
    }
    New-Item -ItemType Directory -Path (Join-Path $minecraft 'mods') | Out-Null
    foreach ($row in @($manifest.files)) {
        $name = [string]$row.file
        Copy-Item -LiteralPath (Join-Path $releaseMods $name) -Destination (Join-Path $minecraft "mods\$name")
    }

    Copy-Item -LiteralPath (Join-Path $sourceInstance 'mmc-pack.json') -Destination (Join-Path $temp 'mmc-pack.json')
    $sourceCfg = [IO.File]::ReadAllText((Join-Path $sourceInstance 'instance.cfg'), [Text.Encoding]::UTF8)
    if ($sourceCfg -notmatch '(?m)^name=') { throw 'Candidate11 instance.cfg has no name field' }
    $targetCfg = [Text.RegularExpressions.Regex]::Replace($sourceCfg, '(?m)^name=.*$', 'name=' + $InstanceName, 1)
    Write-Utf8NoBom (Join-Path $temp 'instance.cfg') $targetCfg

    $reparse = @(Get-ChildItem -LiteralPath $temp -Recurse -Force | Where-Object { [int]$_.Attributes -band 0x400 })
    if ($reparse.Count -ne 0) { throw "Unexpected reparse points in Candidate12 instance: $($reparse.FullName -join ', ')" }
    $tempState = Validate-ModDirectory (Join-Path $minecraft 'mods') $manifest $clientBundle
    if ((File-Sha256 (Join-Path $minecraft 'options.txt')) -cne $sourceControlHashes['minecraft\options.txt']) { throw 'Candidate12 options.txt changed during import' }
    if ((File-Sha256 (Join-Path $minecraft 'servers.dat')) -cne $sourceControlHashes['minecraft\servers.dat']) { throw 'Candidate12 servers.dat changed during import' }
    if ((File-Sha256 (Join-Path $temp 'mmc-pack.json')) -cne $sourceControlHashes['mmc-pack.json']) { throw 'Candidate12 mmc-pack.json changed during import' }

    Move-Item -LiteralPath $temp -Destination $target
    $temp = $null
    $targetMinecraft = Join-Path $target 'minecraft'
    $targetState = Validate-ModDirectory (Join-Path $targetMinecraft 'mods') $manifest $clientBundle
    if ((File-Sha256 (Join-Path $targetMinecraft 'options.txt')) -cne $sourceControlHashes['minecraft\options.txt']) { throw 'Published Candidate12 options.txt mismatch' }
    if ((File-Sha256 (Join-Path $targetMinecraft 'servers.dat')) -cne $sourceControlHashes['minecraft\servers.dat']) { throw 'Published Candidate12 servers.dat mismatch' }

    $sourceStateAfter = Validate-ModDirectory $sourceMods $candidate11Manifest $candidate11ClientBundleSha
    foreach ($relative in $sourceControlHashes.Keys) {
        if ((File-Sha256 (Join-Path $sourceInstance $relative)) -cne $sourceControlHashes[$relative]) {
            throw "Candidate11 source was mutated: $relative"
        }
    }
    if ($sourceStateAfter.bundle_sha256 -cne $sourceStateBefore.bundle_sha256) { throw 'Candidate11 source mod bundle was mutated' }

    $reportValue = [ordered]@{
        schema = 1
        status = 'IMPORTED_PRISM_INSTANCE'
        ready_for_manual_launch = $true
        source_instance = $sourceInstance
        source_instance_unchanged = $true
        instance_name = $InstanceName
        instance_path = $target
        minecraft_path = $targetMinecraft
        release = [ordered]@{
            root = $release
            ready_sha256 = $expectedRelease
            client_manifest_sha256 = $manifestSha
            client_bundle_sha256 = $clientBundle
            file_count = 52
            bytes = [long]$targetState.bytes
        }
        waypoint = [ordered]@{
            mod_id = $waypointModId
            file = [string]$waypointRows[0].file
            sha256 = $expectedWaypoint
            rejected_candidate11_sha256_absent = $true
        }
        inherited_without_edit = @('config', 'defaultconfigs', 'data', 'resourcepacks', 'options.txt', 'servers.dat', 'mmc-pack.json')
        intentionally_excluded = @('logs', 'saves', 'cache', 'downloads', 'screenshots', 'crash-reports', 'journeymap', 'schematics')
        source_bundle = $sourceStateBefore
        release_bundle = $releaseState
        staging_bundle = $tempState
        imported_bundle = $targetState
        java_started_by_importer = $false
        prism_started_by_importer = $false
        manual_action = 'Refresh Prism, select the new Candidate12 instance, and launch it manually for the join gate.'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $reportPath) -Force | Out-Null
    Write-Utf8NoBomCreateNew $reportPath (($reportValue | ConvertTo-Json -Depth 12) + [Environment]::NewLine)
    $reportValue
} catch {
    if ($null -ne $temp -and (Test-Path -LiteralPath $temp)) {
        $resolvedTemp = Full-Path $temp
        if (-not (Path-Is-Within $resolvedTemp $instances) -or -not ([IO.Path]::GetFileName($resolvedTemp)).StartsWith('.candidate12-import-', [StringComparison]::Ordinal)) {
            throw "Refusing unsafe temporary cleanup target: $resolvedTemp"
        }
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
    throw
}
