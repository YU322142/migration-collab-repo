param(
    [string] $SourceMinecraftRoot = '',
    [string] $ClientMods = '',
    [string] $BundleManifest = '',
    [string] $ReleaseReady = '',
    [string] $ReleaseLock = '',
    [string] $OutputRoot = '',
    [string] $Report = '',
    [string] $SyntheticUsername = 'Candidate11Gate',
    [string] $SyntheticUuid = '00000000-0000-0000-0000-000000001101',
    [switch] $PreflightOnly
)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$bundleRoot = '<AUDIT_ROOT>\final-mod-bundles-candidate11-20260811'
$expectedSource = Join-Path $workspace 'outputs\tmp\client-gate-candidate5\.minecraft'
$expectedMods = Join-Path $bundleRoot 'client-mods'
$expectedManifest = Join-Path $bundleRoot 'manifests\client.json'
$expectedReady = Join-Path $bundleRoot 'READY.json'
$expectedLock = Join-Path $bundleRoot 'release-lock.json'
$expectedOutput = Join-Path $workspace 'outputs\tmp\client-gate-candidate11\.minecraft'
$expectedReport = Join-Path $workspace 'outputs\candidate11-client-root-prepare-20260811.json'
$expectedReadySha256 = '613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E'
$expectedManifestSha256 = '1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D'
$expectedBundleSha256 = 'CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B'
$expectedBundlePairSha256 = 'FC008BD9ED9ABF5FF23B61E40ADDCAC46986E22147EB2437324C48E2E9242E56'
$expectedHappyGhastFile = 'happyghast-equivalence-1.0.0-equivalence.2+mc1.21.1.jar'
$expectedHappyGhastSha256 = '36C1CE14EE18B81C04654F1A6956F2257B7DEAC07746E960475AAF5C6F25A579'
$expectedCcGuardFile = 'cctweaked-startup-shutdown-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar'
$expectedCcGuardSha256 = '6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7'
$expectedCreateGuardFile = 'create-chute-unload-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar'
$expectedCreateGuardSha256 = 'AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A'
$staleCandidate10Ready = '<AUDIT_ROOT>\final-mod-bundles-candidate10-20260811\READY.json'
$expectedStaleCandidate10ReadySha256 = '71D13227E80AB70B04CDD800D6E786821ABA759F99397B52960974715DFF5108'
$expectedStaleCandidate10ManifestSha256 = '79677A95935DD67E4196C8CCC99F92D9D817087C1DC7402DCE3A614B44C89553'
$expectedStaleCandidate10BundleSha256 = 'CEC51F141A226E53E5CB0F64851E6EA37DE6FFC7BFD307863FE2563AA606737F'

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
        throw "$($binding[2]) is not the locked Candidate11 path: $($binding[0])"
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
if ($SyntheticUsername -cne 'Candidate11Gate' -or
    $parsedUuid.ToString('D') -cne '00000000-0000-0000-0000-000000001101') {
    throw 'Candidate11 offline identity is immutable'
}

foreach ($path in @($source, $mods)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Directory missing: $path" }
}
foreach ($path in @($manifestPath, $readyPath, $lockPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Locked release input missing: $path" }
}
if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite client gate root: $output" }
if (Test-Path -LiteralPath $reportPath) { throw "Refusing to overwrite client gate report: $reportPath" }
if (-not (Path-IsWithin $output $workspace) -or -not (Path-IsWithin $reportPath $workspace)) {
    throw 'Candidate11 output and report must remain inside the workspace'
}

$readyHash = File-Sha256 $readyPath
$lockHash = File-Sha256 $lockPath
$manifestHash = File-Sha256 $manifestPath
if ($readyHash -ne $expectedReadySha256 -or $lockHash -ne $expectedReadySha256) {
    throw 'Candidate11 READY/release-lock hash does not match the frozen release'
}
if ($manifestHash -ne $expectedManifestSha256) {
    throw 'Candidate11 client manifest hash does not match the frozen release'
}
if (-not [Linq.Enumerable]::SequenceEqual([byte[]][IO.File]::ReadAllBytes($readyPath), [byte[]][IO.File]::ReadAllBytes($lockPath))) {
    throw 'Candidate11 READY.json and release-lock.json are not byte-identical'
}

$ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ([int]$ready.schema -ne 1 -or [int]$ready.candidate -ne 11 -or
    [string]$ready.status -ne 'PASS' -or -not [bool]$ready.source_unchanged) {
    throw 'Candidate11 READY.json is not a passing immutable schema-1 release'
}
if (-not (Same-Path ([string]$ready.output_root) $bundleRoot) -or
    -not (Same-Path ([string]$ready.client.mods_dir) $mods) -or
    -not (Same-Path ([string]$ready.client.manifest) $manifestPath)) {
    throw 'Candidate11 READY.json path binding mismatch'
}
if ([int]$ready.client.file_count -ne 52 -or
    ([string]$ready.client.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha256 -or
    ([string]$ready.client.manifest_sha256).ToUpperInvariant() -ne $expectedManifestSha256) {
    throw 'Candidate11 READY.json client identity mismatch'
}
if (([string]$ready.bundle_pair_sha256).ToUpperInvariant() -ne $expectedBundlePairSha256 -or
    [int]$ready.candidate10_invariance.baseline_rows_per_side -ne 50 -or
    [int]$ready.candidate10_invariance.unchanged_rows_per_side -ne 50 -or
    [int]$ready.candidate10_invariance.replaced_rows_per_side -ne 0 -or
    [int]$ready.candidate10_invariance.added_rows_per_side -ne 2) {
    throw 'Candidate11 READY.json Candidate10 invariance or pair binding mismatch'
}
if (([string]$ready.baseline.release_lock_sha256).ToUpperInvariant() -ne $expectedStaleCandidate10ReadySha256 -or
    ([string]$ready.baseline.client_manifest_sha256).ToUpperInvariant() -ne $expectedStaleCandidate10ManifestSha256 -or
    ([string]$ready.baseline.client_bundle_sha256).ToUpperInvariant() -ne $expectedStaleCandidate10BundleSha256) {
    throw 'Candidate11 READY.json baseline binding mismatch'
}
if ([string]$ready.patches.cc_stop_worker_compat.file -cne $expectedCcGuardFile -or
    ([string]$ready.patches.cc_stop_worker_compat.sha256).ToUpperInvariant() -ne $expectedCcGuardSha256 -or
    [string]$ready.patches.create_chute_guard.file -cne $expectedCreateGuardFile -or
    ([string]$ready.patches.create_chute_guard.sha256).ToUpperInvariant() -ne $expectedCreateGuardSha256 -or
    [bool]$ready.runtime_sanitization_policy.client_runtime_jar_transforms_allowed) {
    throw 'Candidate11 READY.json compatibility-guard policy mismatch'
}
if ([int]$manifest.schema -ne 1 -or [int]$manifest.candidate -ne 11 -or
    [string]$manifest.side -ne 'client' -or [string]$manifest.status -ne 'PASS') {
    throw 'Candidate11 client manifest is not a passing schema-1 client manifest'
}
if ([int]$manifest.file_count -ne 52 -or @($manifest.files).Count -ne 52) {
    throw 'Candidate11 client manifest must contain exactly 52 JARs'
}
if (-not (Same-Path ([string]$manifest.bundle_dir) $mods) -or
    ([string]$manifest.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha256) {
    throw 'Candidate11 client manifest path or bundle digest mismatch'
}
if ([int]$manifest.candidate10_invariance.baseline_rows -ne 50 -or
    [int]$manifest.candidate10_invariance.unchanged_rows -ne 50 -or
    [int]$manifest.candidate10_invariance.replaced_rows -ne 0 -or
    [int]$manifest.candidate10_invariance.added_rows -ne 2 -or
    [string]$manifest.cc_compat_addition.file -cne $expectedCcGuardFile -or
    ([string]$manifest.cc_compat_addition.sha256).ToUpperInvariant() -ne $expectedCcGuardSha256 -or
    [string]$manifest.guard_addition.file -cne $expectedCreateGuardFile -or
    ([string]$manifest.guard_addition.sha256).ToUpperInvariant() -ne $expectedCreateGuardSha256) {
    throw 'Candidate11 client manifest compatibility-guard binding mismatch'
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
if ($sourceDirs.Count -ne 0 -or $allSourceFiles.Count -ne 52 -or $sourceJars.Count -ne 52) {
    throw 'Candidate11 mod directory must be flat and contain only the exact 52 JARs'
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
    throw 'Superseded Happy Ghast JAR leaked into Candidate11'
}
foreach ($guard in @(
    @($expectedCcGuardFile, $expectedCcGuardSha256),
    @($expectedCreateGuardFile, $expectedCreateGuardSha256)
)) {
    if (-not $sourceByName.ContainsKey($guard[0]) -or
        (File-Sha256 $sourceByName[$guard[0]].FullName) -ne $guard[1]) {
        throw "Candidate11 compatibility guard is absent or changed: $($guard[0])"
    }
}

$sevenZipCommand = Get-Command '7z.exe' -ErrorAction Stop
$sevenZip = $sevenZipCommand.Source
$sourceCrcRows = [Collections.Generic.List[object]]::new()
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    Test-ZipCrc $sourceByName[$name].FullName $sevenZip
    $sourceCrcRows.Add([ordered]@{ file = $name; source_crc = 'PASS' })
}

$candidate10Evidence = [ordered]@{
    status = 'REJECTED_STALE'
    reason = 'Candidate10 lacks the frozen CC and Create guards; never eligible as Candidate11 input'
    ready = $staleCandidate10Ready
    documented = (Test-Path -LiteralPath $staleCandidate10Ready -PathType Leaf)
}
if ($candidate10Evidence.documented) {
    $candidate10Hash = File-Sha256 $staleCandidate10Ready
    $candidate10 = Get-Content -LiteralPath $staleCandidate10Ready -Raw | ConvertFrom-Json
    if ($candidate10Hash -ne $expectedStaleCandidate10ReadySha256 -or
        ([string]$candidate10.client.manifest_sha256).ToUpperInvariant() -ne $expectedStaleCandidate10ManifestSha256 -or
        ([string]$candidate10.client.bundle_sha256).ToUpperInvariant() -ne $expectedStaleCandidate10BundleSha256) {
        throw 'Documented Candidate10 evidence changed; stale-input rejection cannot be proven'
    }
    $candidate10Evidence['ready_sha256'] = $candidate10Hash
    $candidate10Evidence['client_manifest_sha256'] = ([string]$candidate10.client.manifest_sha256).ToUpperInvariant()
    $candidate10Evidence['client_bundle_sha256'] = ([string]$candidate10.client.bundle_sha256).ToUpperInvariant()
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
        stale_candidate10 = $candidate10Evidence
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
        throw "Candidate11 shared directory junction validation failed: $destination"
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
if ($outputDirs.Count -ne 0 -or $outputFiles.Count -ne 52) {
    throw 'Prepared Candidate11 mod directory is not the exact flat 52-JAR set'
}
[long]$outputBytes = 0
$outputCrcRows = [Collections.Generic.List[object]]::new()
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    if (-not $outputByName.ContainsKey($name)) { throw "Prepared Candidate11 JAR missing: $name" }
    $jar = $outputByName[$name]
    $hash = File-Sha256 $jar.FullName
    if ($jar.Length -ne [long]$row.bytes -or $hash -ne ([string]$row.sha256).ToUpperInvariant()) {
        throw "Prepared Candidate11 JAR hash/size mismatch: $name"
    }
    Test-ZipCrc $jar.FullName $sevenZip
    $outputCrcRows.Add([ordered]@{ file = $name; output_crc = 'PASS' })
    $outputBytes += $jar.Length
}
$outputBundleDigest = Bundle-Digest @($manifest.files) $outputByName
if ($outputBytes -ne [long]$manifest.bytes -or $outputBundleDigest -ne $sourceBundleDigest) {
    throw 'Prepared Candidate11 bundle aggregate mismatch'
}

foreach ($name in $excludedNames) {
    if (Test-Path -LiteralPath (Join-Path $output $name)) {
        throw "Runtime state leaked into Candidate11: $name"
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
    throw "Cache/log/save state leaked into Candidate11 copied trees: $($forbiddenCopiedState -join ', ')"
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
    throw "Unexpected Candidate11 top-level state: $($unexpectedTopLevel -join ', ')"
}
$lastServer = @(Get-Content -LiteralPath (Join-Path $output 'options.txt') | Where-Object { $_ -like 'lastServer:*' })
if ($lastServer.Count -ne 1 -or $lastServer[0] -ne 'lastServer:') {
    throw 'Candidate11 options.txt inherits a non-empty multiplayer endpoint'
}

$sourceAfter = Top-Level-Fingerprint $source
if ($sourceBefore -ne $sourceAfter) {
    throw 'Candidate5 source root changed while Candidate11 was being prepared'
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
    purpose = 'Candidate11 isolated localhost join client root'
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
        cc_guard_file = $expectedCcGuardFile
        cc_guard_sha256 = $expectedCcGuardSha256
        create_guard_file = $expectedCreateGuardFile
        create_guard_sha256 = $expectedCreateGuardSha256
        stale_files = @()
    }
    zip_crc = [ordered]@{
        verifier = $sevenZip
        source_archives_tested = $sourceCrcRows.Count
        output_archives_tested = $outputCrcRows.Count
        all_source_entries_passed = $true
        all_output_entries_passed = $true
    }
    stale_candidate10 = $candidate10Evidence
    candidate8_root_read_or_written = $false
    candidate10_root_read_or_written = $false
    prior_gate_root_read_or_written = $false
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
