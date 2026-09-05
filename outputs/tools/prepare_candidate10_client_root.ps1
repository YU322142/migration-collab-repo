param(
    [string] $SourceMinecraftRoot = '',
    [string] $ClientMods = '',
    [string] $BundleManifest = '',
    [string] $ReleaseReady = '',
    [string] $ReleaseLock = '',
    [string] $OutputRoot = '',
    [string] $Report = '',
    [string] $SyntheticUsername = 'Candidate10Gate',
    [string] $SyntheticUuid = '00000000-0000-0000-0000-000000001001',
    [switch] $PreflightOnly
)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$bundleRoot = '<AUDIT_ROOT>\final-mod-bundles-candidate10-20260811'
$expectedSource = Join-Path $workspace 'outputs\tmp\client-gate-candidate5\.minecraft'
$expectedMods = Join-Path $bundleRoot 'client-mods'
$expectedManifest = Join-Path $bundleRoot 'manifests\client.json'
$expectedReady = Join-Path $bundleRoot 'READY.json'
$expectedLock = Join-Path $bundleRoot 'release-lock.json'
$expectedOutput = Join-Path $workspace 'outputs\tmp\client-gate-candidate10\.minecraft'
$expectedReport = Join-Path $workspace 'outputs\candidate10-client-root-prepare-20260811.json'
$expectedReadySha256 = '71D13227E80AB70B04CDD800D6E786821ABA759F99397B52960974715DFF5108'
$expectedManifestSha256 = '79677A95935DD67E4196C8CCC99F92D9D817087C1DC7402DCE3A614B44C89553'
$expectedBundleSha256 = 'CEC51F141A226E53E5CB0F64851E6EA37DE6FFC7BFD307863FE2563AA606737F'
$expectedHappyGhastFile = 'happyghast-equivalence-1.0.0-equivalence.2+mc1.21.1.jar'
$expectedHappyGhastSha256 = '36C1CE14EE18B81C04654F1A6956F2257B7DEAC07746E960475AAF5C6F25A579'
$staleCandidate9Ready = '<AUDIT_ROOT>\final-mod-bundles-candidate9-20260811\READY.json'
$expectedStaleCandidate9ReadySha256 = '2B650E1D5DDB0798B98F2A23BEC5636A629CFFFBB2B206D0A5685D654EDA0F0D'
$expectedStaleCandidate9BundleSha256 = 'C87B3398E7B38907E8E4EE21ED6F3A4A748F5756E6E1612FB730132FD36E14D4'
$expectedStaleCandidate9HappyGhastSha256 = 'F715D0065BEEC583B5EDEEFF3DCD28D4E9DFCC3D5E9B5FE55E9DF26C945D82E8'

if ([string]::IsNullOrWhiteSpace($SourceMinecraftRoot)) { $SourceMinecraftRoot = $expectedSource }
if ([string]::IsNullOrWhiteSpace($ClientMods)) { $ClientMods = $expectedMods }
if ([string]::IsNullOrWhiteSpace($BundleManifest)) { $BundleManifest = $expectedManifest }
if ([string]::IsNullOrWhiteSpace($ReleaseReady)) { $ReleaseReady = $expectedReady }
if ([string]::IsNullOrWhiteSpace($ReleaseLock)) { $ReleaseLock = $expectedLock }
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
            $hash = File-Sha256 $FilesByName[$name].FullName
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

function Test-ZipCrc([string] $Path, [string] $SevenZip) {
    & $SevenZip t -bso0 -bsp0 -bse0 -- $Path | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ZIP CRC validation failed (7z exit $LASTEXITCODE): $Path"
    }
}

$source = Full-Path $SourceMinecraftRoot
$mods = Full-Path $ClientMods
$manifestPath = Full-Path $BundleManifest
$readyPath = Full-Path $ReleaseReady
$lockPath = Full-Path $ReleaseLock
$output = Full-Path $OutputRoot
$reportPath = Full-Path $Report

foreach ($binding in @(
    @($source, $expectedSource, 'SourceMinecraftRoot'),
    @($mods, $expectedMods, 'ClientMods'),
    @($manifestPath, $expectedManifest, 'BundleManifest'),
    @($readyPath, $expectedReady, 'ReleaseReady'),
    @($lockPath, $expectedLock, 'ReleaseLock'),
    @($output, $expectedOutput, 'OutputRoot'),
    @($reportPath, $expectedReport, 'Report')
)) {
    if (-not (Same-Path $binding[0] $binding[1])) {
        throw "$($binding[2]) is not the locked Candidate10 path: $($binding[0])"
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
foreach ($path in @($manifestPath, $readyPath, $lockPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Locked release input missing: $path" }
}
if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite client gate root: $output" }
if (Test-Path -LiteralPath $reportPath) { throw "Refusing to overwrite client gate report: $reportPath" }
if (-not (Path-IsWithin $output $workspace) -or -not (Path-IsWithin $reportPath $workspace)) {
    throw 'Candidate10 output and report must remain inside the workspace'
}

$readyHash = File-Sha256 $readyPath
$lockHash = File-Sha256 $lockPath
$manifestHash = File-Sha256 $manifestPath
if ($readyHash -ne $expectedReadySha256 -or $lockHash -ne $expectedReadySha256) {
    throw 'Candidate10 READY/release-lock hash does not match the frozen release'
}
if ($manifestHash -ne $expectedManifestSha256) {
    throw 'Candidate10 client manifest hash does not match the frozen release'
}
if (-not [Linq.Enumerable]::SequenceEqual([byte[]][IO.File]::ReadAllBytes($readyPath), [byte[]][IO.File]::ReadAllBytes($lockPath))) {
    throw 'Candidate10 READY.json and release-lock.json are not byte-identical'
}

$ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([int]$ready.schema -ne 1 -or [string]$ready.status -ne 'PASS' -or -not [bool]$ready.source_unchanged) {
    throw 'Candidate10 READY.json is not a passing immutable schema-1 release'
}
if (-not (Same-Path ([string]$ready.output_root) $bundleRoot) -or
    -not (Same-Path ([string]$ready.client.mods_dir) $mods) -or
    -not (Same-Path ([string]$ready.client.manifest) $manifestPath)) {
    throw 'Candidate10 READY.json path binding mismatch'
}
if ([int]$ready.client.file_count -ne 50 -or
    ([string]$ready.client.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha256 -or
    ([string]$ready.client.manifest_sha256).ToUpperInvariant() -ne $expectedManifestSha256) {
    throw 'Candidate10 READY.json client identity mismatch'
}
if ([string]$ready.replacement.file -ne $expectedHappyGhastFile -or
    ([string]$ready.replacement.sha256).ToUpperInvariant() -ne $expectedHappyGhastSha256) {
    throw 'Candidate10 READY.json does not bind the final Happy Ghast replacement'
}
if ([int]$manifest.schema -ne 1 -or [string]$manifest.side -ne 'client' -or [string]$manifest.status -ne 'PASS') {
    throw 'Candidate10 client manifest is not a passing schema-1 client manifest'
}
if ([int]$manifest.file_count -ne 50 -or @($manifest.files).Count -ne 50) {
    throw 'Candidate10 client manifest must contain exactly 50 JARs'
}
if (-not (Same-Path ([string]$manifest.bundle_dir) $mods) -or
    ([string]$manifest.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha256) {
    throw 'Candidate10 client manifest path or bundle digest mismatch'
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
    throw 'Candidate10 mod directory must be flat and contain only the exact 50 JARs'
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
if ($sourceBytes -ne [long]$manifest.bytes -or $sourceBytes -ne [long]$ready.client.bytes) {
    throw 'Source client bundle byte total mismatch'
}
$sourceBundleDigest = Bundle-Digest @($manifest.files) $sourceByName
if ($sourceBundleDigest -ne $expectedBundleSha256) { throw 'Source client bundle aggregate mismatch' }
if (-not $sourceByName.ContainsKey($expectedHappyGhastFile) -or
    (File-Sha256 $sourceByName[$expectedHappyGhastFile].FullName) -ne $expectedHappyGhastSha256) {
    throw 'Final Happy Ghast JAR is absent or changed'
}
if ($sourceByName.ContainsKey('happyghast-equivalence-1.0.0-equivalence.1+mc1.21.1.jar')) {
    throw 'Superseded Happy Ghast JAR leaked into Candidate10'
}

$sevenZipCommand = Get-Command '7z.exe' -ErrorAction Stop
$sevenZip = $sevenZipCommand.Source
$sourceCrcRows = [Collections.Generic.List[object]]::new()
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    Test-ZipCrc $sourceByName[$name].FullName $sevenZip
    $sourceCrcRows.Add([ordered]@{ file = $name; source_crc = 'PASS' })
}

$candidate9Evidence = [ordered]@{
    status = 'REJECTED_STALE'
    reason = 'Superseded Happy Ghast replacement and client bundle; never eligible as Candidate10 input'
    ready = $staleCandidate9Ready
    documented = (Test-Path -LiteralPath $staleCandidate9Ready -PathType Leaf)
}
if ($candidate9Evidence.documented) {
    $candidate9Hash = File-Sha256 $staleCandidate9Ready
    $candidate9 = Get-Content -LiteralPath $staleCandidate9Ready -Raw | ConvertFrom-Json
    if ($candidate9Hash -ne $expectedStaleCandidate9ReadySha256 -or
        ([string]$candidate9.client.bundle_sha256).ToUpperInvariant() -ne $expectedStaleCandidate9BundleSha256 -or
        ([string]$candidate9.replacement.sha256).ToUpperInvariant() -ne $expectedStaleCandidate9HappyGhastSha256) {
        throw 'Documented Candidate9 evidence changed; stale-input rejection cannot be proven'
    }
    $candidate9Evidence['ready_sha256'] = $candidate9Hash
    $candidate9Evidence['client_bundle_sha256'] = ([string]$candidate9.client.bundle_sha256).ToUpperInvariant()
    $candidate9Evidence['happyghast_sha256'] = ([string]$candidate9.replacement.sha256).ToUpperInvariant()
}

$sourceBefore = Top-Level-Fingerprint $source
if ($PreflightOnly) {
    [ordered]@{
        schema = 1
        status = 'PREFLIGHT_PASS'
        source_minecraft_root = $source
        output_root = $output
        release_ready_sha256 = $readyHash
        manifest_sha256 = $manifestHash
        file_count = $sourceJars.Count
        bytes = $sourceBytes
        bundle_sha256 = $sourceBundleDigest
        source_zip_crc_archives_tested = $sourceCrcRows.Count
        stale_candidate9 = $candidate9Evidence
        java_started = $false
    }
    exit 0
}

$copiedDirectoryNames = @('config', 'defaultconfigs', 'resourcepacks', 'data')
$copiedFileNames = @('options.txt')
$excludedNames = @(
    '.cache', 'downloads', 'journeymap', 'logs', 'saves', 'schematics', 'screenshots',
    'launcher_profiles.json', 'servers.dat', 'servers.dat_old', 'usercache.json',
    'usernamecache.json'
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
        throw "Candidate10 shared directory junction validation failed: $destination"
    }
    $junctionEvidence.Add([ordered]@{
        name = $name
        source_path = $sourceLink
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
    throw 'Prepared Candidate10 mod directory is not the exact flat 50-JAR set'
}
[long]$outputBytes = 0
$outputCrcRows = [Collections.Generic.List[object]]::new()
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    if (-not $outputByName.ContainsKey($name)) { throw "Prepared Candidate10 JAR missing: $name" }
    $jar = $outputByName[$name]
    $hash = File-Sha256 $jar.FullName
    if ($jar.Length -ne [long]$row.bytes -or $hash -ne ([string]$row.sha256).ToUpperInvariant()) {
        throw "Prepared Candidate10 JAR hash/size mismatch: $name"
    }
    Test-ZipCrc $jar.FullName $sevenZip
    $outputCrcRows.Add([ordered]@{ file = $name; output_crc = 'PASS' })
    $outputBytes += $jar.Length
}
$outputBundleDigest = Bundle-Digest @($manifest.files) $outputByName
if ($outputBytes -ne [long]$manifest.bytes -or $outputBundleDigest -ne $sourceBundleDigest) {
    throw 'Prepared Candidate10 bundle aggregate mismatch'
}

foreach ($name in $excludedNames) {
    if (Test-Path -LiteralPath (Join-Path $output $name)) {
        throw "Runtime state leaked into Candidate10: $name"
    }
}
$forbiddenCopiedState = @(
    foreach ($name in $copiedDirectoryNames) {
        $root = Join-Path $output $name
        Get-ChildItem -LiteralPath $root -Recurse -Force | Where-Object {
            $_.Name -match '(^|[-_.])(cache|logs?|saves?)([-_.]|$)' -or $_.Extension -ieq '.log'
        } | ForEach-Object { Relative-Path $output $_.FullName }
    }
)
if ($forbiddenCopiedState.Count -ne 0) {
    throw "Cache/log/save state leaked into Candidate10 copied trees: $($forbiddenCopiedState -join ', ')"
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
    throw "Unexpected Candidate10 top-level state: $($unexpectedTopLevel -join ', ')"
}
$lastServer = @(Get-Content -LiteralPath (Join-Path $output 'options.txt') | Where-Object { $_ -like 'lastServer:*' })
if ($lastServer.Count -ne 1 -or $lastServer[0] -ne 'lastServer:') {
    throw 'Candidate10 options.txt inherits a non-empty multiplayer endpoint'
}

$sourceAfter = Top-Level-Fingerprint $source
if ($sourceBefore -ne $sourceAfter) {
    throw 'Candidate5 source root changed while Candidate10 was being prepared'
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
    purpose = 'Candidate10 isolated localhost join client root'
    source_minecraft_root = $source
    source_top_level_sha256_before = $sourceBefore
    source_top_level_sha256_after = $sourceAfter
    source_unchanged = $true
    output_root = $output
    release = [ordered]@{
        root = $bundleRoot
        ready = $readyPath
        ready_sha256 = $readyHash
        release_lock = $lockPath
        release_lock_sha256 = $lockHash
        ready_lock_byte_identical = $true
    }
    junctions = $junctionEvidence.ToArray()
    copied_non_world_client_state = $copiedTreeEvidence
    excluded_source_state = $excludedNames
    forbidden_runtime_state_found = @()
    saves_logs_caches_absent = $true
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
        manifest_sha256 = $manifestHash
        file_count = $outputFiles.Count
        bytes = $outputBytes
        bundle_sha256 = $outputBundleDigest
        expected_bundle_sha256 = $expectedBundleSha256
        exact_manifest_match = $true
        happyghast_file = $expectedHappyGhastFile
        happyghast_sha256 = $expectedHappyGhastSha256
        stale_files = @()
    }
    zip_crc = [ordered]@{
        verifier = $sevenZip
        source_archives_tested = $sourceCrcRows.Count
        output_archives_tested = $outputCrcRows.Count
        all_source_entries_passed = $true
        all_output_entries_passed = $true
    }
    stale_candidate9 = $candidate9Evidence
    candidate8_root_read_or_written = $false
    java_started = $false
    historical_backup_accessed = $false
}
New-Item -ItemType Directory -Path (Split-Path -Parent $reportPath) -Force | Out-Null
[IO.File]::WriteAllText(
    $reportPath,
    ($value | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$value

