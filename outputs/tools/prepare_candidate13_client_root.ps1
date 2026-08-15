param(
    [string] $SourceMinecraftRoot = '',
    [string] $ReleaseRoot = 'D:\Trans\migration-audit-work\final-mod-bundles-candidate13-20260812',
    [string] $OutputRoot = '',
    [string] $Report = '',
    [string] $LocalResourcePack = '',
    [string] $ServerAddress = 'play.example.invalid:12341',
    [switch] $PreflightOnly
)

# Candidate13-only fresh client-root preparation.  It intentionally does not
# touch Candidate11/12 roots, the original user pack, or server.properties.
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedSource = Join-Path $workspace 'outputs\tmp\client-gate-candidate5\.minecraft'
$expectedOutput = Join-Path $workspace 'outputs\tmp\client-gate-candidate13\.minecraft'
$expectedReport = Join-Path $workspace 'outputs\candidate13-client-root-prepare-20260812.json'
$localPackStem = ([char]0x4E16) + ([char]0x754C) + ([char]0x6307) + ([char]0x5B9A) + ([char]0x8D44) + ([char]0x6E90) + ([char]0x5305) + ([char]0x55B5)
$localPackFileName = $localPackStem + '-mc1.21.1-candidate13.zip'
$expectedPack = Join-Path (Join-Path $workspace 'outputs\candidate13-resource-closure-20260812') $localPackFileName
$expectedRelease = 'D:\Trans\migration-audit-work\final-mod-bundles-candidate13-20260812'
$expectedReadySha = 'FA992151079AEE46DCDAEB49D23487F0F4642099E86F0962469E2257E830BA3F'
$expectedManifestSha = '261ADB612DB2A2D992F8A8CAC0FC8C753D6620B98B8CB79E693CC434E57216BE'
$expectedBundleSha = 'AC9887DB6F12E0A9E9F8B77030C3F904276DB8BFD4BDF9D01C4B9DAF9EEA4495'
$expectedPackSha = '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364'
$expectedPackBytes = 110377999
$expectedPackFormat = 34
$expectedJarCount = 52
$rejectedWaypointSha = '5572EE1F196038071FB5D7B9D7FF271CCB0E19BA722B83BCC1A2B8C0C844F8EB'
$expectedWaypointSha = '86A85C0447315AC17D373E3708425CEB8450D9D0CB1FD9C7ABDC82CE8D8E5B92'
$expectedOverlaySha = 'BCCB7D7CF8019D8895A081D563E578712D7CDF93DA0AD9EAFB31067439C62862'

if ([string]::IsNullOrWhiteSpace($SourceMinecraftRoot)) { $SourceMinecraftRoot = $expectedSource }
if ([string]::IsNullOrWhiteSpace($OutputRoot)) { $OutputRoot = $expectedOutput }
if ([string]::IsNullOrWhiteSpace($Report)) { $Report = $expectedReport }
if ([string]::IsNullOrWhiteSpace($LocalResourcePack)) { $LocalResourcePack = $expectedPack }

function Full-Path([string] $Path) { return [IO.Path]::GetFullPath($Path).TrimEnd('\') }
function Same-Path([string] $Left, [string] $Right) {
    return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase)
}
function Path-IsWithin([string] $Path, [string] $Parent) {
    return ((Full-Path $Path) + '\').StartsWith(((Full-Path $Parent) + '\'), [StringComparison]::OrdinalIgnoreCase)
}
function Sha256([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant() }
function Bytes-Sha256([byte[]] $Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '') }
    finally { $sha.Dispose() }
}
function Record-Sha256([string[]] $Rows) {
    return Bytes-Sha256 ([Text.Encoding]::UTF8.GetBytes(($Rows -join "`n") + "`n"))
}
function Relative([string] $Base, [string] $Path) {
    $prefix = (Full-Path $Base) + '\'; $full = Full-Path $Path
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside base: $full" }
    return $full.Substring($prefix.Length).Replace('\', '/')
}
function Tree-Fingerprint([string] $Root) {
    $rows = [Collections.Generic.List[string]]::new(); [long]$bytes = 0
    if (Test-Path -LiteralPath $Root -PathType Container) {
        $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File | Sort-Object FullName)
        foreach ($file in $files) { $bytes += $file.Length; $rows.Add((Relative $Root $file.FullName) + [char]0 + $file.Length + [char]0 + (Sha256 $file.FullName)) }
    }
    return [ordered]@{ files = $rows.Count; bytes = $bytes; sha256 = Record-Sha256 $rows.ToArray() }
}
function Bundle-Digest([object[]] $Rows, [hashtable] $ByName) {
    $records = [Collections.Generic.List[string]]::new()
    foreach ($row in $Rows) { $name = [string]$row.file; $records.Add($name + [char]0 + (Sha256 $ByName[$name].FullName)) }
    return Bytes-Sha256 ([Text.Encoding]::UTF8.GetBytes(($records -join "`n") + "`n"))
}
function Test-Zip([string] $Path, [string] $SevenZip) {
    & $SevenZip t -bso0 -bsp0 -bse0 -- $Path | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "ZIP CRC validation failed: $Path" }
}
function U16BE([int] $Value) { return [byte[]]@([byte](($Value -shr 8) -band 255), [byte]($Value -band 255)) }
function I32BE([int] $Value) { return [byte[]]@([byte](($Value -shr 24) -band 255), [byte](($Value -shr 16) -band 255), [byte](($Value -shr 8) -band 255), [byte]($Value -band 255)) }
function Nbt-String([string] $Value) { $b = [Text.Encoding]::UTF8.GetBytes($Value); return [byte[]](@(U16BE $b.Length) + $b) }
function Nbt-Tag([int] $Id, [string] $Name, [byte[]] $Payload) { return [byte[]](@([byte]$Id) + (Nbt-String $Name) + $Payload) }
function New-ServersDat([string] $Address) {
    $entry = [byte[]](@(Nbt-Tag 8 'name' (Nbt-String 'Minecraft Server')) + (Nbt-Tag 8 'ip' (Nbt-String $Address)) + (Nbt-Tag 1 'acceptTextures' ([byte[]]@(0))) + (Nbt-Tag 1 'hidden' ([byte[]]@(1))) + [byte]0)
    $list = [byte[]](@([byte]10) + (I32BE 1) + $entry)
    return [byte[]](@([byte]10, [byte]0, [byte]0) + (Nbt-Tag 9 'servers' $list) + [byte]0)
}
function Set-ClientOptions([string] $Path, [string] $PackName, [string] $Address) {
    $lines = [Collections.Generic.List[string]]::new(); $found = $false; $lastServerFound = $false; $packId = 'file/' + $PackName
    foreach ($line in [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)) {
        if ($line.StartsWith('resourcePacks:', [StringComparison]::Ordinal)) {
            if ($found) { continue }
            $found = $true; $tokens = [Collections.Generic.List[string]]::new()
            foreach ($m in [Text.RegularExpressions.Regex]::Matches($line, '"((?:\\.|[^"])*)"')) { if ($m.Groups[1].Value -ne $packId) { $tokens.Add($m.Groups[1].Value) } }
            $tokens.Add($packId); $lines.Add('resourcePacks:[' + (($tokens | ForEach-Object { '"' + $_ + '"' }) -join ',') + ']')
        } elseif ($line.StartsWith('lastServer:', [StringComparison]::Ordinal)) {
            if (-not $lastServerFound) { $lines.Add('lastServer:' + $Address); $lastServerFound = $true }
        } else { $lines.Add($line) }
    }
    if (-not $found) { $lines.Add('resourcePacks:["fabric","' + $packId + '"]') }
    if (-not $lastServerFound) { $lines.Add('lastServer:' + $Address) }
    [IO.File]::WriteAllLines($Path, $lines.ToArray(), [Text.UTF8Encoding]::new($false))
}
function Read-PackFormat([string] $Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry = $zip.GetEntry('pack.mcmeta'); if ($null -eq $entry) { throw 'Derived pack lacks pack.mcmeta' }
        $reader = [IO.StreamReader]::new($entry.Open(), [Text.Encoding]::UTF8, $true)
        try { $json = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        return [int]$json.pack.pack_format
    } finally { $zip.Dispose() }
}

$source = Full-Path $SourceMinecraftRoot; $release = Full-Path $ReleaseRoot; $output = Full-Path $OutputRoot; $report = Full-Path $Report; $pack = Full-Path $LocalResourcePack
if (-not (Same-Path $source $expectedSource)) { throw "Candidate13 source is not the locked Candidate5 template: $source" }
if (-not (Same-Path $release $expectedRelease)) { throw "Candidate13 release path is not locked: $release" }
if (-not (Same-Path $output $expectedOutput) -or -not (Path-IsWithin $output $workspace)) { throw 'Candidate13 output path is not isolated' }
if (-not (Same-Path $report $expectedReport) -or -not (Path-IsWithin $report $workspace)) { throw 'Candidate13 report path is not isolated' }
if ($ServerAddress -notmatch '^(\[[^\]]+\]|[^:]+):12341$') { throw 'Candidate13 server address must retain port 12341' }
if (-not $PreflightOnly.IsPresent -and (Test-Path -LiteralPath $report)) { throw "Refusing to overwrite Candidate13 preparation report: $report" }
foreach ($path in @($source, (Join-Path $source 'config'), (Join-Path $source 'data'), (Join-Path $source 'defaultconfigs'), (Join-Path $source 'options.txt'))) { if (-not (Test-Path -LiteralPath $path)) { throw "Required source path missing: $path" } }
foreach ($name in @('assets','libraries','versions')) { if (-not (Test-Path -LiteralPath (Join-Path $source $name))) { throw "Shared client directory missing: $name" } }

$ready = Join-Path $release 'READY.json'; $lock = Join-Path $release 'release-lock.json'; $manifestPath = Join-Path $release 'manifests\client.json'; $mods = Join-Path $release 'client-mods'
foreach ($path in @($ready,$lock,$manifestPath,$mods,$pack)) { if (-not (Test-Path -LiteralPath $path)) { throw "Candidate13 release input missing: $path" } }
if ((Sha256 $ready) -ne $expectedReadySha -or (Sha256 $lock) -ne $expectedReadySha) { throw 'Candidate13 READY/release-lock hash mismatch' }
if (-not [Linq.Enumerable]::SequenceEqual([IO.File]::ReadAllBytes($ready), [IO.File]::ReadAllBytes($lock))) { throw 'Candidate13 READY/release-lock bytes differ' }
if ((Sha256 $manifestPath) -ne $expectedManifestSha) { throw 'Candidate13 client manifest hash mismatch' }
$readyJson = Get-Content -Raw $ready | ConvertFrom-Json; $manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
if ([int]$readyJson.candidate -ne 13 -or [string]$readyJson.status -cne 'PASS' -or [int]$readyJson.client.file_count -ne $expectedJarCount -or ([string]$readyJson.client.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha) { throw 'Candidate13 READY client binding mismatch' }
if ([int]$manifest.candidate -ne 13 -or [string]$manifest.status -cne 'PASS' -or [string]$manifest.side -cne 'client' -or [int]$manifest.file_count -ne $expectedJarCount -or ([string]$manifest.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha) { throw 'Candidate13 client manifest binding mismatch' }
$jarFiles = @(Get-ChildItem -LiteralPath $mods -File | Sort-Object Name); if ($jarFiles.Count -ne $expectedJarCount -or @($jarFiles | Where-Object {$_.Extension -ine '.jar'}).Count -ne 0) { throw 'Candidate13 client-mods is not an exact flat 52-JAR set' }
$byName = @{}; foreach ($jar in $jarFiles) { $byName[$jar.Name] = $jar }
foreach ($row in @($manifest.files)) { $name=[string]$row.file; if (-not $byName.ContainsKey($name)) { throw "Candidate13 JAR missing: $name" }; if ($byName[$name].Length -ne [long]$row.bytes -or (Sha256 $byName[$name].FullName) -ne ([string]$row.sha256).ToUpperInvariant()) { throw "Candidate13 JAR hash/size mismatch: $name" } }
if ((Bundle-Digest @($manifest.files) $byName) -ne $expectedBundleSha) { throw 'Candidate13 client aggregate digest mismatch' }
if (@($manifest.files | Where-Object { ([string]$_.sha256).ToUpperInvariant() -eq $rejectedWaypointSha }).Count -ne 0) { throw 'Rejected Candidate11 Waypoint bytes leaked into Candidate13' }
if (@($manifest.files | Where-Object { ([string]$_.sha256).ToUpperInvariant() -eq $expectedWaypointSha }).Count -ne 1) { throw 'Candidate13 fixed Waypoint JAR binding missing' }
if (@($manifest.files | Where-Object { ([string]$_.sha256).ToUpperInvariant() -eq $expectedOverlaySha }).Count -ne 1) { throw 'Candidate13 resource overlay binding missing' }
$sevenZip = (Get-Command '7z.exe' -ErrorAction Stop).Source; Test-Zip $pack $sevenZip
if ((Get-Item -LiteralPath $pack).Length -ne $expectedPackBytes -or (Sha256 $pack) -ne $expectedPackSha -or (Read-PackFormat $pack) -ne $expectedPackFormat) { throw 'Candidate13 derived local resource pack binding mismatch' }
$sourceFingerprintBefore = Tree-Fingerprint $source
if ($PreflightOnly) {
    $serversPayload = New-ServersDat $ServerAddress
    [ordered]@{ schema=1; status='PREFLIGHT_PASS'; candidate=13; source_minecraft_root=$source; output_root=$output; release_ready_sha256=$expectedReadySha; client_manifest_sha256=$expectedManifestSha; client_bundle_sha256=$expectedBundleSha; client_file_count=$expectedJarCount; local_resource_pack=[ordered]@{path=$pack;sha256=$expectedPackSha;bytes=$expectedPackBytes;pack_format=$expectedPackFormat}; server=[ordered]@{address=$ServerAddress;port=12341;accept_remote_resource_pack=$false;servers_dat_acceptTextures=$false;servers_dat_bytes=$serversPayload.Length;servers_dat_sha256=(Bytes-Sha256 $serversPayload)}; java_started=$false; prism_started=$false; writes_performed=0; source_tree_sha256=$sourceFingerprintBefore.sha256 } | ConvertTo-Json -Depth 8
    exit 0
}
if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite Candidate13 client root: $output" }
$temporaryOutput = $output + '.candidate13.' + [Guid]::NewGuid().ToString('N') + '.tmp'
$published = $false
try {
    New-Item -ItemType Directory -Path $temporaryOutput | Out-Null
    foreach ($name in @('assets','libraries','versions')) {
        $srcItem = Get-Item -LiteralPath (Join-Path $source $name) -Force; $target = Join-Path $temporaryOutput $name
        $resolved = if ($srcItem.LinkType -eq 'Junction') { Full-Path ([string]$srcItem.Target) } else { Full-Path $srcItem.FullName }
        if (Path-IsWithin $resolved 'D:\Trans\20260807') { throw "Shared client input resolves into historical backup: $resolved" }
        New-Item -ItemType Junction -Path $target -Target $resolved | Out-Null
    }
    foreach ($name in @('config','defaultconfigs','data')) { Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $temporaryOutput $name) -Recurse }
    foreach ($relative in @('config\voicechat\username-cache.json','config\spark\tmp','config\spark\tmp-client')) {
        $cache = Join-Path $temporaryOutput $relative
        if (Test-Path -LiteralPath $cache) { Remove-Item -LiteralPath $cache -Recurse -Force }
    }
    Copy-Item -LiteralPath (Join-Path $source 'options.txt') -Destination (Join-Path $temporaryOutput 'options.txt')
    New-Item -ItemType Directory -Path (Join-Path $temporaryOutput 'mods'),(Join-Path $temporaryOutput 'resourcepacks'),(Join-Path $temporaryOutput 'natives') | Out-Null
    foreach ($row in @($manifest.files)) { $name=[string]$row.file; Copy-Item -LiteralPath $byName[$name].FullName -Destination (Join-Path $temporaryOutput "mods\$name") }
    Copy-Item -LiteralPath $pack -Destination (Join-Path $temporaryOutput "resourcepacks\$([IO.Path]::GetFileName($pack))")
    Set-ClientOptions (Join-Path $temporaryOutput 'options.txt') ([IO.Path]::GetFileName($pack)) $ServerAddress
    $serversPayload = New-ServersDat $ServerAddress
    [IO.File]::WriteAllBytes((Join-Path $temporaryOutput 'servers.dat'), $serversPayload)
    $actualMods = @(Get-ChildItem -LiteralPath (Join-Path $temporaryOutput 'mods') -File | Sort-Object Name)
    if ($actualMods.Count -ne $expectedJarCount) { throw 'Prepared Candidate13 mod count mismatch' }
    $actualByName = @{}; foreach ($jar in $actualMods) { $actualByName[$jar.Name] = $jar }
    if ((Bundle-Digest @($manifest.files) $actualByName) -ne $expectedBundleSha) { throw 'Prepared Candidate13 mod bundle digest mismatch' }
    $actualPack = Join-Path $temporaryOutput "resourcepacks\$([IO.Path]::GetFileName($pack))"
    if (@(Get-ChildItem -LiteralPath (Join-Path $temporaryOutput 'resourcepacks') -Force).Count -ne 1 -or (Sha256 $actualPack) -ne $expectedPackSha) { throw 'Prepared Candidate13 local resource pack mismatch' }
    $optionsLines = [IO.File]::ReadAllLines((Join-Path $temporaryOutput 'options.txt'), [Text.Encoding]::UTF8)
    $packId = 'file/' + [IO.Path]::GetFileName($pack)
    $resourceLine = @($optionsLines | Where-Object { $_.StartsWith('resourcePacks:', [StringComparison]::Ordinal) })
    $lastServerLine = @($optionsLines | Where-Object { $_.StartsWith('lastServer:', [StringComparison]::Ordinal) })
    if ($resourceLine.Count -ne 1 -or ([regex]::Matches($resourceLine[0], [regex]::Escape($packId))).Count -ne 1 -or $lastServerLine.Count -ne 1 -or $lastServerLine[0] -cne ('lastServer:' + $ServerAddress)) { throw 'Prepared Candidate13 options policy mismatch' }
    if (-not [Linq.Enumerable]::SequenceEqual([IO.File]::ReadAllBytes((Join-Path $temporaryOutput 'servers.dat')), $serversPayload)) { throw 'Prepared Candidate13 servers.dat mismatch' }
    $allowed = @('assets','config','data','defaultconfigs','libraries','mods','natives','options.txt','resourcepacks','servers.dat','versions')
    $unexpected = @(Get-ChildItem -LiteralPath $temporaryOutput -Force | Where-Object { $allowed -notcontains $_.Name } | ForEach-Object { $_.Name })
    if ($unexpected.Count -ne 0) { throw "Unexpected Candidate13 top-level state: $($unexpected -join ', ')" }
    Move-Item -LiteralPath $temporaryOutput -Destination $output
    $published = $true
    $temporaryOutput = $null
    $sourceFingerprintAfter = Tree-Fingerprint $source
    if ($sourceFingerprintBefore.sha256 -ne $sourceFingerprintAfter.sha256) { throw 'Candidate5 source changed during Candidate13 preparation' }
    $value = [ordered]@{ schema=1; status='PREPARED'; candidate=13; purpose='Candidate13 fresh client root with local derived resource pack'; source_minecraft_root=$source; output_root=$output; source_unchanged=$true; release=[ordered]@{root=$release;ready_sha256=$expectedReadySha;release_lock_sha256=(Sha256 $lock);client_manifest_sha256=$expectedManifestSha;client_bundle_sha256=$expectedBundleSha;file_count=$expectedJarCount}; local_resource_pack=[ordered]@{path=(Join-Path $output "resourcepacks\$([IO.Path]::GetFileName($pack))");sha256=$expectedPackSha;bytes=$expectedPackBytes;pack_format=$expectedPackFormat;enabled_exactly_once=$true}; server=[ordered]@{address=$ServerAddress;port=12341;accept_remote_resource_pack=$false;servers_dat_acceptTextures=$false;server_properties_modified=$false}; java_started=$false; prism_started=$false }
    New-Item -ItemType Directory -Path (Split-Path -Parent $report) -Force | Out-Null; [IO.File]::WriteAllText($report, (($value | ConvertTo-Json -Depth 10) + [Environment]::NewLine), [Text.UTF8Encoding]::new($false)); $value
} catch { if ($null -ne $temporaryOutput -and (Test-Path -LiteralPath $temporaryOutput)) { Remove-Item -LiteralPath $temporaryOutput -Recurse -Force }; if ($published -and (Test-Path -LiteralPath $output)) { Remove-Item -LiteralPath $output -Recurse -Force }; throw }
