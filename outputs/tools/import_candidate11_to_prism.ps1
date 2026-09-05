param(
    [string] $PrismRoot = '<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3',
    [string] $SourceMinecraftRoot = '',
    [string] $ReleaseRoot = '<AUDIT_ROOT>\final-mod-bundles-candidate11-20260811',
    [string] $InstanceName = '',
    [string] $Report = ''
)

$ErrorActionPreference = 'Stop'

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$packFileName = ([char]0x4e16) + ([char]0x754c) + ([char]0x6307) + ([char]0x5b9a) + ([char]0x8d44) + ([char]0x6e90) + ([char]0x5305) + ([char]0x55b5) + '.zip'
$defaultInstanceName = ([char]0x52a8) + ([char]0x9759) + ([char]0x4ea4) + ([char]0x6620) + '-Candidate11-NeoForge-1.21.1-20260811'
if ([string]::IsNullOrWhiteSpace($InstanceName)) { $InstanceName = $defaultInstanceName }
if ([string]::IsNullOrWhiteSpace($SourceMinecraftRoot)) {
    $SourceMinecraftRoot = Join-Path $workspace 'outputs\tmp\client-gate-candidate11\.minecraft'
}
if ([string]::IsNullOrWhiteSpace($Report)) {
    $Report = Join-Path $workspace 'outputs\candidate11-prism-import-20260811.json'
}

$expectedClientBundle = 'CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B'
$expectedClientManifest = '1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D'
$expectedReleaseLock = '613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E'
$expectedPackSha = 'C8E9113D9E0773234A0CA1A77572548A968C5E5970856970FAAB8FC431E1BCD6'
$expectedPackBytes = 111537147L
$expectedServersSha = '383C90619FD783D6CFB045A3B98D49CE01E885CD4EEC3536BDD4C07A62AFCB41'
$expectedJava = '<INSTANCE_ROOT>/PrismLauncher-Windows-MinGW-w64-Portable-11.0.3/java/java-runtime-delta/bin/javaw.exe'

function Full-Path([string] $Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Same-Path([string] $Left, [string] $Right) {
    return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase)
}

function Path-Is-Within([string] $Path, [string] $Parent) {
    $p = (Full-Path $Path) + '\'
    $q = (Full-Path $Parent) + '\'
    return $p.StartsWith($q, [StringComparison]::OrdinalIgnoreCase)
}

function File-Sha256([string] $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Bytes-Sha256([byte[]] $Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '') }
    finally { $sha.Dispose() }
}

function Record-Sha256([string[]] $Records) {
    return Bytes-Sha256 ([Text.Encoding]::UTF8.GetBytes(($Records -join "`n") + "`n"))
}

function Relative-Path([string] $Base, [string] $Path) {
    $prefix = (Full-Path $Base) + '\'
    $full = Full-Path $Path
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside base: $full" }
    return $full.Substring($prefix.Length).Replace('\', '/')
}

function Tree-Fingerprint([string] $Root) {
    $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File | Sort-Object FullName)
    $records = [Collections.Generic.List[string]]::new()
    [long]$bytes = 0
    foreach ($file in $files) {
        $bytes += $file.Length
        $records.Add((Relative-Path $Root $file.FullName) + [char]0 + [string]$file.Length + [char]0 + (File-Sha256 $file.FullName))
    }
    return [ordered]@{ files = $files.Count; bytes = $bytes; sha256 = Record-Sha256 $records.ToArray() }
}

function Bundle-Digest([object[]] $Rows, [hashtable] $FilesByName) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.MemoryStream]::new()
    try {
        foreach ($row in $Rows) {
            $name = [string]$row.file
            if (-not $FilesByName.ContainsKey($name)) { throw "Missing JAR: $name" }
            $record = [Text.Encoding]::UTF8.GetBytes($name + [char]0 + (File-Sha256 $FilesByName[$name].FullName) + "`n")
            $stream.Write($record, 0, $record.Length)
        }
        $stream.Position = 0
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
    } finally { $stream.Dispose(); $sha.Dispose() }
}

function Write-Utf8NoBom([string] $Path, [string] $Text) {
    [IO.File]::WriteAllText($Path, $Text, [Text.UTF8Encoding]::new($false))
}

function Copy-Tree([string] $Source, [string] $Destination) {
    if (Test-Path -LiteralPath $Source -PathType Container) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
        Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
            $target = Join-Path $Destination $_.Name
            if ($_.PSIsContainer) { Copy-Tree $_.FullName $target }
            else { Copy-Item -LiteralPath $_.FullName -Destination $target -Force }
        }
    } else {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }
}

$prism = Full-Path $PrismRoot
$source = Full-Path $SourceMinecraftRoot
$release = Full-Path $ReleaseRoot
$instances = Join-Path $prism 'instances'
$target = Join-Path $instances $InstanceName
$manifestPath = Join-Path $release 'manifests\client.json'
$lockPath = Join-Path $release 'release-lock.json'
$reportPath = Full-Path $Report
$packPath = Join-Path $source ('resourcepacks\' + $packFileName)
$serversPath = Join-Path $source 'servers.dat'

if (-not (Test-Path -LiteralPath (Join-Path $prism 'portable.txt') -PathType Leaf)) { throw "Not a Prism portable root: $prism" }
if (-not (Test-Path -LiteralPath $instances -PathType Container)) { throw "Prism instances directory missing: $instances" }
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Candidate11 client root missing: $source" }
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Client manifest missing: $manifestPath" }
if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) { throw "Candidate11 lock missing: $lockPath" }
if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite existing Prism instance: $target" }
if (Test-Path -LiteralPath $reportPath) { throw "Refusing to overwrite existing import report: $reportPath" }
if (-not (Path-Is-Within $target $instances) -or -not (Path-Is-Within $reportPath $workspace)) { throw 'Target/report path isolation failed' }

$manifestSha = File-Sha256 $manifestPath
$lockSha = File-Sha256 $lockPath
if ($manifestSha -ne $expectedClientManifest -or $lockSha -ne $expectedReleaseLock) { throw 'Candidate11 release fingerprint mismatch' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$lock = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
if ([int]$manifest.candidate -ne 11 -or [string]$manifest.side -ne 'client' -or [string]$manifest.status -ne 'PASS') { throw 'Client manifest is not Candidate11 PASS' }
if ([int]$manifest.file_count -ne 52 -or ([string]$manifest.bundle_sha256).ToUpperInvariant() -ne $expectedClientBundle) { throw 'Client manifest bundle binding mismatch' }
if ([string]$lock.client.bundle_sha256 -ne $expectedClientBundle -or [string]$lock.client.manifest_sha256 -ne $expectedClientManifest) { throw 'Release lock client binding mismatch' }

$sourceMods = Join-Path $source 'mods'
$sourceJars = @(Get-ChildItem -LiteralPath $sourceMods -File -Filter '*.jar' | Sort-Object Name)
if ($sourceJars.Count -ne 52) { throw "Candidate11 source must contain 52 JARs, got $($sourceJars.Count)" }
$sourceByName = @{}
foreach ($jar in $sourceJars) { $sourceByName[$jar.Name] = $jar }
[long]$sourceBytes = 0
foreach ($row in @($manifest.files)) {
    $name = [string]$row.file
    if (-not $sourceByName.ContainsKey($name)) { throw "Source JAR missing: $name" }
    $jar = $sourceByName[$name]
    $hash = File-Sha256 $jar.FullName
    if ($jar.Length -ne [long]$row.bytes -or $hash -ne ([string]$row.sha256).ToUpperInvariant()) { throw "Source JAR mismatch: $name" }
    $sourceBytes += $jar.Length
}
$sourceBundle = Bundle-Digest @($manifest.files) $sourceByName
if ($sourceBytes -ne [long]$manifest.bytes -or $sourceBundle -ne $expectedClientBundle) { throw 'Source Candidate11 bundle aggregate mismatch' }

if (-not (Test-Path -LiteralPath $packPath -PathType Leaf)) { throw "Local resource pack missing: $packPath" }
$packItem = Get-Item -LiteralPath $packPath
$packSha = File-Sha256 $packPath
if ($packItem.Length -ne $expectedPackBytes -or $packSha -ne $expectedPackSha) { throw 'Local resource pack fingerprint mismatch' }
if (-not (Test-Path -LiteralPath $serversPath -PathType Leaf) -or (File-Sha256 $serversPath) -ne $expectedServersSha) { throw 'servers.dat is not the tested remote-pack-decline profile' }
$optionsPath = Join-Path $source 'options.txt'
if (-not (Test-Path -LiteralPath $optionsPath -PathType Leaf)) { throw 'options.txt missing' }
$optionsBytes = [IO.File]::ReadAllBytes($optionsPath)
$optionsText = [Text.Encoding]::UTF8.GetString($optionsBytes)
if (-not $optionsText.Contains('resourcePacks:["fabric","file/' + $packFileName + '"]')) { throw 'options.txt does not select the local resource pack exactly once' }
if ($optionsText -notmatch '(?m)^lastServer:\s*$') { throw 'options.txt contains a non-empty lastServer' }

$sourceGuard = [ordered]@{
    mods = Tree-Fingerprint $sourceMods
    config = Tree-Fingerprint (Join-Path $source 'config')
    defaultconfigs = Tree-Fingerprint (Join-Path $source 'defaultconfigs')
    data = Tree-Fingerprint (Join-Path $source 'data')
    resourcepacks = Tree-Fingerprint (Join-Path $source 'resourcepacks')
    options_sha256 = File-Sha256 $optionsPath
    servers_sha256 = File-Sha256 $serversPath
}

$guid = [Guid]::NewGuid().ToString('N')
$temp = Join-Path $instances ('.candidate11-import-' + $guid)
$minecraft = Join-Path $temp 'minecraft'
$javaPath = Full-Path $expectedJava
if (-not (Test-Path -LiteralPath $javaPath -PathType Leaf)) { throw "Prism bundled Java missing: $javaPath" }

try {
    New-Item -ItemType Directory -Path $minecraft -Force | Out-Null
    foreach ($name in @('config','defaultconfigs','data','resourcepacks')) {
        Copy-Tree (Join-Path $source $name) (Join-Path $minecraft $name)
    }
    New-Item -ItemType Directory -Path (Join-Path $minecraft 'mods') -Force | Out-Null
    foreach ($row in @($manifest.files)) {
        $name = [string]$row.file
        Copy-Item -LiteralPath $sourceByName[$name].FullName -Destination (Join-Path $minecraft "mods\$name")
    }
    Copy-Item -LiteralPath $optionsPath -Destination (Join-Path $minecraft 'options.txt')
    Copy-Item -LiteralPath $serversPath -Destination (Join-Path $minecraft 'servers.dat')
    # Prism/Minecraft will create runtime folders. Do not import logs, saves, caches, junctions, or the 1.59GB archive.

    $mmc = [ordered]@{
        components = @(
            [ordered]@{ cachedName='LWJGL 3'; cachedVersion='3.3.3'; dependencyOnly=$true; uid='org.lwjgl3'; version='3.3.3' },
            [ordered]@{ cachedName='Minecraft'; cachedRequires=@([ordered]@{ suggests='3.3.3'; uid='org.lwjgl3' }); cachedVersion='1.21.1'; important=$true; uid='net.minecraft'; version='1.21.1' },
            [ordered]@{ cachedName='NeoForge'; cachedRequires=@([ordered]@{ equals='1.21.1'; uid='net.minecraft' }); cachedVersion='21.1.241'; uid='net.neoforged'; version='21.1.241' }
        )
        formatVersion = 1
    }
    Write-Utf8NoBom (Join-Path $temp 'mmc-pack.json') (($mmc | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
    $cfg = @"
[General]
InstanceType=OneSix
name=$InstanceName
ConfigVersion=1.3
ManagedPack=false
ManagedPackType=
ManagedPackName=
ManagedPackID=
ManagedPackVersionID=
ManagedPackVersionName=
ManagedPackURL=
JavaArchitecture=64
JavaRealArchitecture=amd64
JavaPath=$expectedJava
JavaVersion=21.0.7
JavaVendor=Microsoft
AutomaticJava=false
OverrideJavaLocation=true
OverrideMemory=true
MinMemAlloc=2048
MaxMemAlloc=8192
JvmArgs=
OverrideConsole=true
ShowConsole=true
ShowConsoleOnError=true
CloseAfterLaunch=false
UseAccountForInstance=false
JoinServerOnLaunch=false
OverrideWindow=true
MinecraftWinWidth=1280
MinecraftWinHeight=720
RecordGameTime=true
QuitAfterGameStop=false
AutoCloseConsole=false
"@
    Write-Utf8NoBom (Join-Path $temp 'instance.cfg') $cfg

    $tempMods = Join-Path $minecraft 'mods'
    $tempJars = @(Get-ChildItem -LiteralPath $tempMods -File -Filter '*.jar' | Sort-Object Name)
    $tempByName = @{}
    foreach ($jar in $tempJars) { $tempByName[$jar.Name] = $jar }
    if ($tempJars.Count -ne 52 -or (Bundle-Digest @($manifest.files) $tempByName) -ne $expectedClientBundle) { throw 'Temporary Prism mod bundle validation failed' }
    if ((File-Sha256 (Join-Path $minecraft ('resourcepacks\' + $packFileName))) -ne $expectedPackSha) { throw 'Temporary Prism resource pack validation failed' }
    if ((File-Sha256 (Join-Path $minecraft 'servers.dat')) -ne $expectedServersSha) { throw 'Temporary Prism servers.dat validation failed' }
    $tempOptionsText = [IO.File]::ReadAllText((Join-Path $minecraft 'options.txt'), [Text.Encoding]::UTF8)
    if (-not $tempOptionsText.Contains('resourcePacks:["fabric","file/' + $packFileName + '"]')) { throw 'Temporary Prism options validation failed' }

    # No symlinks/reparse points are permitted in the newly imported instance.
    $reparse = @(Get-ChildItem -LiteralPath $temp -Recurse -Force | Where-Object { [int]$_.Attributes -band 0x400 })
    if ($reparse.Count -ne 0) { throw "Unexpected reparse points in imported Prism instance: $($reparse.FullName -join ', ')" }

    Move-Item -LiteralPath $temp -Destination $target
    $temp = $null

    $targetMinecraft = Join-Path $target 'minecraft'
    $targetMods = Join-Path $targetMinecraft 'mods'
    $targetJars = @(Get-ChildItem -LiteralPath $targetMods -File -Filter '*.jar' | Sort-Object Name)
    $targetByName = @{}
    foreach ($jar in $targetJars) { $targetByName[$jar.Name] = $jar }
    $targetBundle = Bundle-Digest @($manifest.files) $targetByName
    if ($targetJars.Count -ne 52 -or $targetBundle -ne $expectedClientBundle) { throw 'Published Prism mod bundle validation failed' }
    if ((File-Sha256 (Join-Path $targetMinecraft ('resourcepacks\' + $packFileName))) -ne $expectedPackSha) { throw 'Published Prism resource pack validation failed' }
    if ((File-Sha256 (Join-Path $targetMinecraft 'servers.dat')) -ne $expectedServersSha) { throw 'Published Prism servers.dat validation failed' }

    $reportValue = [ordered]@{
        schema = 1
        status = 'IMPORTED_PRISM_INSTANCE'
        ready_for_manual_launch = $true
        prism_root = $prism
        prism_pid_observed = 25880
        instances_root = $instances
        instance_name = $InstanceName
        instance_path = $target
        minecraft_path = $targetMinecraft
        mmc_pack = [ordered]@{ minecraft='1.21.1'; neoforge='21.1.241'; lwjgl='3.3.3'; path=(Join-Path $target 'mmc-pack.json') }
        java = [ordered]@{ path=$javaPath; version='21.0.7'; override=$true }
        client_bundle = [ordered]@{ file_count=52; bytes=$sourceBytes; bundle_sha256=$expectedClientBundle; manifest_sha256=$expectedClientManifest; release_lock_sha256=$expectedReleaseLock }
        resource_pack = [ordered]@{ source=$packPath; source_sha256=$expectedPackSha; imported_path=(Join-Path $targetMinecraft ('resourcepacks\' + $packFileName)); imported_sha256=(File-Sha256 (Join-Path $targetMinecraft ('resourcepacks\' + $packFileName))); bytes=$expectedPackBytes; local_selected=$true; derived_pack_format=34 }
        remote_resource_pack = [ordered]@{ servers_dat_sha256=$expectedServersSha; acceptTextures=$false; policy='decline optional server pack; keep local pack selected' }
        imported_trees = [ordered]@{ config=(Tree-Fingerprint (Join-Path $targetMinecraft 'config')); defaultconfigs=(Tree-Fingerprint (Join-Path $targetMinecraft 'defaultconfigs')); data=(Tree-Fingerprint (Join-Path $targetMinecraft 'data')); resourcepacks=(Tree-Fingerprint (Join-Path $targetMinecraft 'resourcepacks')) }
        excluded = @('.cache','downloads','journeymap','logs','saves','schematics','screenshots','natives','assets','libraries','versions','.minecraft.zip','stdout/stderr logs')
        source_read_only = $true
        java_started_by_importer = $false
        manual_action = 'Refresh Prism instance list, select this instance, and launch manually. Do not enable JoinServerOnLaunch; server is not started by this import.'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $reportPath) -Force | Out-Null
    Write-Utf8NoBom $reportPath (($reportValue | ConvertTo-Json -Depth 12) + [Environment]::NewLine)
    $reportValue
} catch {
    if ($null -ne $temp -and (Test-Path -LiteralPath $temp)) { Remove-Item -LiteralPath $temp -Recurse -Force }
    throw
}
