param(
    [string] $ClientRoot = 'D:\Trans\migration-audit-work\mechanomania-matched-client-attempt9-20260814',
    [string] $ClientPrepareReport = 'D:\Trans\migration-audit-work\mechanomania-matched-client-attempt9-prepare-20260814.json',
    [string] $GateReport = 'D:\Trans\migration-audit-work\mechanomania-cei-backport-startup-gate-attempt9-20260814.json',
    [string] $PrismRoot = 'D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3',
    [string] $TemplateInstanceName = '',
    [string] $InstanceName = '',
    [string] $Report = '',
    [string] $ServerAddress = '127.0.0.1:12341',
    [int] $MinMemoryMb = 2048,
    [int] $MaxMemoryMb = 4096,
    [switch] $PreflightOnly
)

# Mechanomania Attempt9 -> Prism 11.0.3 importer.
#
# Safety contract:
# - Preflight is read-only for the source client and Prism instances. It writes
#   only a new evidence report under workspace outputs.
# - A real import requires the matching Attempt9 startup gate to be PASS.
# - Existing instances/reports are never overwritten.
# - Mutable gameplay/client directories are copied as ordinary directories.
# - assets/libraries/versions reuse only the already-audited source junctions.
# - Prism and Java are never launched by this script.
# - MCModSync is globally inactive: neither mods nor config may contain it.

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedClientRoot = 'D:\Trans\migration-audit-work\mechanomania-matched-client-attempt9-20260814'
$expectedPrepareReport = 'D:\Trans\migration-audit-work\mechanomania-matched-client-attempt9-prepare-20260814.json'
$expectedPrepareReportSha256 = 'B63ACEE97ED3C0EF53378A9BA4B5FE04C36EE98CA1B1B02E7ABF1A98086F7D65'
$expectedPrismRoot = 'D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3'
$expectedLocalPack = 'migration-local-resources-mc1.21.1.zip'
$expectedLocalPackBytes = 110377999
$expectedLocalPackSha256 = '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364'
$instanceStem = ([char]0x52A8) + ([char]0x9759) + ([char]0x4EA4) + ([char]0x6620)
$defaultTemplateName = $instanceStem + '-Candidate14-r3-NeoForge-1.21.1-20260812'
$defaultInstanceName = $instanceStem + '-Mechanomania-Matched-Attempt9-NeoForge-1.21.1-20260814'

if ([string]::IsNullOrWhiteSpace($TemplateInstanceName)) { $TemplateInstanceName = $defaultTemplateName }
if ([string]::IsNullOrWhiteSpace($InstanceName)) { $InstanceName = $defaultInstanceName }
if ([string]::IsNullOrWhiteSpace($Report)) {
    $leaf = if ($PreflightOnly.IsPresent) { 'mechanomania-attempt9-prism-import-preflight-20260814.json' } else { 'mechanomania-attempt9-prism-import-20260814.json' }
    $Report = Join-Path $workspace ('outputs\' + $leaf)
}

$requiredModLocks = [ordered]@{
    'mineastr-neoforge-1.21.1-0.6.26.jar' = [ordered]@{ bytes = 257982; sha256 = '0264D729A3343BE1645B5AFE16C15A7A57C7E89A9405FA67EC80EE06D4A148D8' }
    'yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar' = [ordered]@{ bytes = 1111051; sha256 = '673FECBFFAD26BB6D025FB5F60560CF6340E542BDF091D8D66074490515292F3' }
    'backport-1.5-cat-serializer-fix.1.jar' = [ordered]@{ bytes = 15336561; sha256 = '34291AF9D81B6AEE0780F5F511B2A9594664F36906AED40687DF1C7009E68B1D' }
    'hotbath-1.21.1-3.0.0-registry-fix.1.jar' = [ordered]@{ bytes = 712893; sha256 = '1B53A2B7B2C6476BBAD3ACE344316DA7ABE62854967DE322E9A25CA1D5C7681A' }
    'worldedit-mod-7.3.8-direction-property-fix.1.jar' = [ordered]@{ bytes = 6264309; sha256 = '8EB5E39AA914EB1B09307B6C004478BD1263655FCCA880580673481EBFEF9283' }
    'create-enchantment-industry-2.4.2-cei251-backport.1.jar' = [ordered]@{ bytes = 1575446; sha256 = '5B2C3BE95385DBF93000759DB604AB4C71224D7455C437C1B4650D91FAC669EB' }
}

$sharedDirectoryNames = @('assets', 'libraries', 'versions')
$requiredMutableDirectoryNames = @('config', 'data', 'defaultconfigs', 'mods', 'resourcepacks', 'xaero')
$excludedRuntimeDirectoryNames = @(
    '.cache', '.sable', 'cache', 'crash-reports', 'downloads', 'journeymap', 'logs',
    'natives', 'saves', 'screenshots', 'server-resource-packs',
    'server-resource-packs-cache'
)

function Full-Path([string] $Path) { return [IO.Path]::GetFullPath($Path).TrimEnd('\') }
function Same-Path([string] $Left, [string] $Right) { return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase) }
function Path-IsWithin([string] $Path, [string] $Parent) { return ((Full-Path $Path) + '\').StartsWith(((Full-Path $Parent) + '\'), [StringComparison]::OrdinalIgnoreCase) }
function Paths-Overlap([string] $Left, [string] $Right) { return (Path-IsWithin $Left $Right) -or (Path-IsWithin $Right $Left) }
function Sha256([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant() }
function Bytes-Sha256([byte[]] $Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '') } finally { $sha.Dispose() }
}
function Bytes-Equal([byte[]] $Left, [byte[]] $Right) {
    if ($null -eq $Left -or $null -eq $Right -or $Left.Length -ne $Right.Length) { return $false }
    for ($i = 0; $i -lt $Left.Length; $i++) { if ($Left[$i] -ne $Right[$i]) { return $false } }
    return $true
}
function Read-Json([string] $Path) { return ([IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json) }
function Is-Reparse([IO.FileSystemInfo] $Item) { return (([int]$Item.Attributes -band 0x400) -ne 0) }
function Write-NewUtf8([string] $Path, [string] $Value) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}
function Add-TreeRows([string] $Base, [string] $Current, [string] $Prefix, [Collections.Generic.List[string]] $Rows, [ref] $FileCount, [ref] $DirectoryCount, [ref] $ByteCount) {
    foreach ($item in @(Get-ChildItem -LiteralPath $Current -Force | Sort-Object Name)) {
        if (Is-Reparse $item) { throw "Unexpected reparse point in mutable tree: $($item.FullName)" }
        $relative = if ([string]::IsNullOrEmpty($Prefix)) { $item.Name } else { $Prefix + '/' + $item.Name }
        if ($item.PSIsContainer) {
            $DirectoryCount.Value++
            $Rows.Add('D' + [char]0 + $relative)
            Add-TreeRows $Base $item.FullName $relative $Rows $FileCount $DirectoryCount $ByteCount
        } else {
            $FileCount.Value++
            $ByteCount.Value += [long]$item.Length
            $Rows.Add('F' + [char]0 + $relative + [char]0 + [string]$item.Length + [char]0 + (Sha256 $item.FullName))
        }
    }
}
function Snapshot-CopySet([string] $Root, [string[]] $DirectoryNames) {
    $rows = [Collections.Generic.List[string]]::new()
    $files = 0; $directories = 0; $bytes = [long]0
    foreach ($name in @($DirectoryNames | Sort-Object)) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Mutable source directory missing: $path" }
        $item = Get-Item -LiteralPath $path -Force
        if (Is-Reparse $item) { throw "Mutable source directory may not be linked: $path" }
        $directories++
        $rows.Add('D' + [char]0 + $name)
        Add-TreeRows $Root $path $name $rows ([ref]$files) ([ref]$directories) ([ref]$bytes)
    }
    $payload = [Text.Encoding]::UTF8.GetBytes(($rows.ToArray() -join "`n") + "`n")
    return [ordered]@{ directories = $directories; files = $files; bytes = $bytes; tree_sha256 = (Bytes-Sha256 $payload) }
}
function Same-Snapshot([object] $Left, [object] $Right) {
    return [int]$Left.directories -eq [int]$Right.directories -and [int]$Left.files -eq [int]$Right.files -and [long]$Left.bytes -eq [long]$Right.bytes -and [string]$Left.tree_sha256 -ceq [string]$Right.tree_sha256
}
function Get-CopySetLatestWriteUtc([string] $Root, [string[]] $DirectoryNames) {
    $latest = [DateTime]::MinValue
    foreach ($name in $DirectoryNames) {
        $path = Join-Path $Root $name
        foreach ($item in @((Get-Item -LiteralPath $path -Force)) + @(Get-ChildItem -LiteralPath $path -Recurse -Force)) {
            if ($item.LastWriteTimeUtc -gt $latest) { $latest = $item.LastWriteTimeUtc }
        }
    }
    foreach ($name in @('options.txt', 'servers.dat')) {
        $item = Get-Item -LiteralPath (Join-Path $Root $name) -Force
        if ($item.LastWriteTimeUtc -gt $latest) { $latest = $item.LastWriteTimeUtc }
    }
    return $latest
}
function Copy-Tree([string] $Source, [string] $Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Source tree missing: $Source" }
    New-Item -ItemType Directory -Path $Destination | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $Source -Force | Sort-Object Name)) {
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
    $entry = [byte[]](@(Nbt-Tag 8 'name' (Nbt-String 'Mechanomania Local Test')) + (Nbt-Tag 8 'ip' (Nbt-String $Address)) + (Nbt-Tag 1 'acceptTextures' ([byte[]]@(0))) + (Nbt-Tag 1 'hidden' ([byte[]]@(0))) + [byte]0)
    $list = [byte[]](@([byte]10) + (I32BE 1) + $entry)
    return [byte[]](@([byte]10, [byte]0, [byte]0) + (Nbt-Tag 9 'servers' $list) + [byte]0)
}
function Option-ResourcePackIds([string] $Line) {
    $values = [Collections.Generic.List[string]]::new()
    foreach ($match in [Text.RegularExpressions.Regex]::Matches($Line, '"((?:\\.|[^"])*)"')) {
        $values.Add([Text.RegularExpressions.Regex]::Unescape($match.Groups[1].Value))
    }
    return $values.ToArray()
}
function Validate-Options([string] $Path, [string] $Address) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf) -or (Is-Reparse (Get-Item -LiteralPath $Path -Force))) { throw "options.txt missing or linked: $Path" }
    $lines = [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)
    $packLine = @($lines | Where-Object { $_.StartsWith('resourcePacks:', [StringComparison]::Ordinal) })
    $serverLine = @($lines | Where-Object { $_.StartsWith('lastServer:', [StringComparison]::Ordinal) })
    $selected = if ($packLine.Count -eq 1) { @(Option-ResourcePackIds $packLine[0]) } else { @() }
    $packId = 'file/' + $expectedLocalPack
    if ($packLine.Count -ne 1 -or @($selected | Where-Object { $_ -ceq $packId }).Count -ne 1) { throw 'Mechanomania local resource pack must be selected exactly once' }
    if ($serverLine.Count -ne 1 -or $serverLine[0] -cne ('lastServer:' + $Address)) { throw "options.txt lastServer mismatch: $Address" }
    return [ordered]@{ sha256 = (Sha256 $Path); local_pack_selected_once = $true; last_server = $Address }
}
function Set-Options([string] $Path, [string] $Address) {
    $lines = [IO.File]::ReadAllLines($Path, [Text.Encoding]::UTF8)
    $output = [Collections.Generic.List[string]]::new(); $foundServer = $false
    foreach ($line in $lines) {
        if ($line.StartsWith('lastServer:', [StringComparison]::Ordinal)) {
            if (-not $foundServer) { $output.Add('lastServer:' + $Address); $foundServer = $true }
        } else { $output.Add($line) }
    }
    if (-not $foundServer) { $output.Add('lastServer:' + $Address) }
    [IO.File]::WriteAllText($Path, (($output.ToArray() -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
}
function Validate-Instance-Metadata([string] $Instance) {
    $mmcPath = Join-Path $Instance 'mmc-pack.json'; $cfgPath = Join-Path $Instance 'instance.cfg'
    if (-not (Test-Path -LiteralPath $mmcPath -PathType Leaf) -or -not (Test-Path -LiteralPath $cfgPath -PathType Leaf)) { throw "Prism instance metadata missing: $Instance" }
    $mmc = Read-Json $mmcPath
    $minecraft = @($mmc.components | Where-Object { [string]$_.uid -ceq 'net.minecraft' })
    $neoforge = @($mmc.components | Where-Object { [string]$_.uid -ceq 'net.neoforged' })
    if ($minecraft.Count -ne 1 -or [string]$minecraft[0].version -cne '1.21.1' -or $neoforge.Count -ne 1 -or [string]$neoforge[0].version -cne '21.1.241') { throw 'Prism metadata must be Minecraft 1.21.1 / NeoForge 21.1.241' }
    return [ordered]@{ mmc_path = $mmcPath; cfg_path = $cfgPath; mmc_sha256 = (Sha256 $mmcPath); cfg_sha256 = (Sha256 $cfgPath); minecraft = '1.21.1'; neoforge = '21.1.241' }
}
function Set-Cfg([string] $Path, [string] $Name) {
    $cfg = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    foreach ($required in @('name=', 'MinMemAlloc=', 'MaxMemAlloc=', 'OverrideMemory=', 'JoinServerOnLaunch=', 'lastLaunchTime=', 'lastTimePlayed=', 'totalTimePlayed=')) {
        if ($cfg -notmatch ('(?m)^' + [Regex]::Escape($required))) { throw "Template instance.cfg lacks $required" }
    }
    $replacements = [ordered]@{
        name = $Name; OverrideMemory = 'true'; MinMemAlloc = [string]$MinMemoryMb; MaxMemAlloc = [string]$MaxMemoryMb
        JoinServerOnLaunch = 'false'; lastLaunchTime = '0'; lastTimePlayed = '0'; totalTimePlayed = '0'
    }
    foreach ($key in $replacements.Keys) { $cfg = [Regex]::Replace($cfg, '(?m)^' + [Regex]::Escape($key) + '=.*$', $key + '=' + $replacements[$key], 1) }
    [IO.File]::WriteAllText($Path, $cfg, [Text.UTF8Encoding]::new($false))
}
function Validate-Cfg([string] $Path, [string] $Name) {
    $cfg = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    foreach ($line in @(
        ('name=' + $Name), 'OverrideMemory=true', ('MinMemAlloc=' + $MinMemoryMb), ('MaxMemAlloc=' + $MaxMemoryMb),
        'JoinServerOnLaunch=false', 'lastLaunchTime=0', 'lastTimePlayed=0', 'totalTimePlayed=0'
    )) {
        if ($cfg -notmatch ('(?m)^' + [Regex]::Escape([string]$line) + '$')) { throw "Published Mechanomania instance.cfg mismatch: $line" }
    }
    return [ordered]@{ sha256 = (Sha256 $Path); minimum_mb = $MinMemoryMb; maximum_mb = $MaxMemoryMb; join_server_on_launch = $false }
}
function Validate-MCModSync-Zero([string] $Root) {
    $matches = [Collections.Generic.List[string]]::new()
    foreach ($scope in @('mods', 'config')) {
        $path = Join-Path $Root $scope
        if (Test-Path -LiteralPath $path -PathType Container) {
            foreach ($item in @(Get-ChildItem -LiteralPath $path -Recurse -Force -ErrorAction Stop)) {
                if ($item.Name -match '(?i)mcmodsync|modsync') { $matches.Add($item.FullName) }
            }
        }
    }
    foreach ($name in @('MCModSync-Config.jar', 'modsync.properties', 'mcmodsync.properties')) {
        $path = Join-Path $Root $name
        if (Test-Path -LiteralPath $path) { $matches.Add($path) }
    }
    if ($matches.Count -ne 0) { throw ('MCModSync must be globally inactive; found: ' + ($matches.ToArray() -join '; ')) }
    return [ordered]@{ active_mods = 0; active_config = 0; policy = 'GLOBALLY_DISABLED' }
}
function Validate-Mods([string] $Root) {
    $modsPath = Join-Path $Root 'mods'
    if (-not (Test-Path -LiteralPath $modsPath -PathType Container)) { throw "mods directory missing: $modsPath" }
    $entries = @(Get-ChildItem -LiteralPath $modsPath -Force)
    $files = @($entries | Where-Object { -not $_.PSIsContainer } | Sort-Object Name)
    if ($entries.Count -ne $files.Count -or @($files | Where-Object { $_.Extension -ine '.jar' -or (Is-Reparse $_) }).Count -ne 0) { throw 'Attempt9 mods must contain only ordinary active JAR files' }
    foreach ($name in $requiredModLocks.Keys) {
        $matches = @($files | Where-Object { $_.Name -ceq $name })
        $lock = $requiredModLocks[$name]
        if ($matches.Count -ne 1 -or [long]$matches[0].Length -ne [long]$lock.bytes -or (Sha256 $matches[0].FullName) -ne [string]$lock.sha256) { throw "Required fixed client mod mismatch: $name" }
    }
    $bytes = [long](($files | Measure-Object Length -Sum).Sum)
    return [ordered]@{ active_jar_count = $files.Count; bytes = $bytes; required_fix_locks = $requiredModLocks.Count; permanent_mod_count_cap = $false }
}
function Get-MutableDirectoryNames([string] $Root) {
    $names = [Collections.Generic.List[string]]::new()
    foreach ($item in @(Get-ChildItem -LiteralPath $Root -Directory -Force | Sort-Object Name)) {
        if ($sharedDirectoryNames -contains $item.Name) {
            if (-not (Is-Reparse $item)) { throw "Shared path must remain a junction: $($item.FullName)" }
            continue
        }
        if (Is-Reparse $item) { throw "Unexpected top-level client reparse point: $($item.FullName)" }
        if ($excludedRuntimeDirectoryNames -contains $item.Name) { continue }
        $names.Add($item.Name)
    }
    foreach ($required in $requiredMutableDirectoryNames) {
        if ($names -notcontains $required) { throw "Required mutable client directory missing: $required" }
    }
    if (Test-Path -LiteralPath (Join-Path $Root 'journeymap')) { throw 'JourneyMap runtime data must not coexist with the selected Xaero map data' }
    return @($names.ToArray() | Sort-Object)
}
function Validate-Shared-Junctions([string] $Root, [string] $Prism, [string] $Client, [string] $Target) {
    $result = [ordered]@{}
    foreach ($name in $sharedDirectoryNames) {
        $path = Join-Path $Root $name
        if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Shared client path missing: $path" }
        $item = Get-Item -LiteralPath $path -Force
        if (-not (Is-Reparse $item) -or [string]$item.LinkType -cne 'Junction') { throw "Shared client path must be an audited junction: $name" }
        $targetValue = [string](@($item.Target)[0])
        if ([string]::IsNullOrWhiteSpace($targetValue)) { throw "Junction target missing: $path" }
        $resolved = Full-Path $targetValue
        if (-not (Test-Path -LiteralPath $resolved -PathType Container) -or -not (Path-IsWithin $resolved $Prism) -or (Paths-Overlap $resolved $Client) -or (Paths-Overlap $resolved $Target)) { throw "Unsafe shared junction target for ${name}: $resolved" }
        $result[$name] = $resolved
    }
    return $result
}
function Validate-Local-Pack([string] $Root) {
    $path = Join-Path $Root ('resourcepacks\' + $expectedLocalPack)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required local resource pack missing: $path" }
    $item = Get-Item -LiteralPath $path -Force
    if (Is-Reparse $item -or [long]$item.Length -ne $expectedLocalPackBytes -or (Sha256 $path) -ne $expectedLocalPackSha256) { throw 'Mechanomania local resource pack fingerprint mismatch' }
    return [ordered]@{ file = $expectedLocalPack; bytes = [long]$item.Length; sha256 = $expectedLocalPackSha256; copied_with_all_resourcepacks = $true }
}
function Inspect-Gate([string] $Path, [string] $Client, [int] $CurrentJarCount, [DateTime] $SourceLatestWriteUtc, [bool] $RequirePass) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        if ($RequirePass) { throw "Attempt9 PASS gate report required before Prism import: $Path" }
        return [ordered]@{ status = 'PENDING'; path = $Path; import_allowed = $false }
    }
    $gateItem = Get-Item -LiteralPath $Path -Force
    $hash = Sha256 $Path; $gate = Read-Json $Path
    if ([string]$gate.status -cne 'PASS') {
        if ($RequirePass) { throw "Attempt9 gate is not PASS: $($gate.status)" }
        return [ordered]@{ status = [string]$gate.status; path = $Path; sha256 = $hash; import_allowed = $false }
    }
    if (-not (Same-Path ([string]$gate.client) $Client) -or [int]$gate.ports.server -ne 12341 -or [int]$gate.ports.rcon -ne 12342 -or [int]$gate.ports.voice -ne 26341) { throw 'Attempt9 PASS gate identity/ports do not match this client' }
    if ($gate.client_mods.mcmodsync_active -ne $false -or $gate.server_mods.mcmodsync_active -ne $false -or [int]$gate.client_mods.active_jar_count -ne $CurrentJarCount) { throw 'Attempt9 PASS gate mod/MCModSync evidence mismatch' }
    if ($gate.cleanup.all_closed -ne $true -or @($gate.blockers).Count -ne 0 -or [string]::IsNullOrWhiteSpace([string]$gate.completed_at_utc)) { throw 'Attempt9 PASS gate cleanup/completion evidence is incomplete' }
    if ($SourceLatestWriteUtc -gt $gateItem.LastWriteTimeUtc) { throw 'Attempt9 client contains files newer than its PASS gate report' }
    return [ordered]@{ status = 'PASS'; path = $Path; sha256 = $hash; import_allowed = $true; completed_at_utc = [string]$gate.completed_at_utc; report_last_write_utc = $gateItem.LastWriteTimeUtc.ToString('o'); source_latest_write_utc = $SourceLatestWriteUtc.ToString('o'); client_active_jars = [int]$gate.client_mods.active_jar_count; ports_closed = $true }
}

$client = Full-Path $ClientRoot
$preparePath = Full-Path $ClientPrepareReport
$gatePath = Full-Path $GateReport
$prism = Full-Path $PrismRoot
$reportPath = Full-Path $Report
$reportSidecar = $reportPath + '.sha256'

if (-not (Same-Path $client $expectedClientRoot)) { throw "Attempt9 client root is not the locked D-drive root: $client" }
if (-not (Same-Path $preparePath $expectedPrepareReport)) { throw "Attempt9 prepare report path is not locked: $preparePath" }
if (-not (Same-Path $prism $expectedPrismRoot)) { throw "Prism root is not the locked portable 11.0.3 root: $prism" }
if (-not (Path-IsWithin $reportPath (Join-Path $workspace 'outputs'))) { throw 'Prism import evidence must remain under workspace outputs' }
if ($ServerAddress -cne '127.0.0.1:12341') { throw 'Attempt9 Prism endpoint must be exactly 127.0.0.1:12341' }
if ($MinMemoryMb -lt 2048 -or $MaxMemoryMb -gt 4096 -or $MaxMemoryMb -lt $MinMemoryMb) { throw 'Attempt9 Prism memory must stay within 2-4 GiB' }
if ([string]::IsNullOrWhiteSpace($InstanceName) -or $InstanceName -in @('.', '..') -or $InstanceName.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) { throw 'Unsafe Prism instance name' }
foreach ($path in @($client, $prism)) { if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Required directory missing: $path" } }
if (Is-Reparse (Get-Item -LiteralPath $client -Force)) { throw 'Attempt9 client root may not be a reparse point' }
if (-not (Test-Path -LiteralPath (Join-Path $prism 'portable.txt') -PathType Leaf)) { throw "Not a Prism portable root: $prism" }
if (-not (Test-Path -LiteralPath $preparePath -PathType Leaf) -or (Sha256 $preparePath) -ne $expectedPrepareReportSha256) { throw 'Attempt9 client prepare report fingerprint mismatch' }

$instances = Join-Path $prism 'instances'
$template = Join-Path $instances $TemplateInstanceName
$target = Join-Path $instances $InstanceName
if (-not (Test-Path -LiteralPath $instances -PathType Container) -or -not (Test-Path -LiteralPath $template -PathType Container)) { throw 'Prism instances/template directory missing' }
if (-not (Path-IsWithin $template $instances) -or -not (Path-IsWithin $target $instances) -or (Same-Path $template $target)) { throw 'Prism instance isolation failed' }
if (Test-Path -LiteralPath $target) { throw "Refusing to overwrite existing Mechanomania Attempt9 Prism instance: $target" }
if ((Test-Path -LiteralPath $reportPath) -or (Test-Path -LiteralPath $reportSidecar)) { throw 'Refusing to overwrite existing Mechanomania Attempt9 Prism import evidence' }

$prepare = Read-Json $preparePath
if ([string]$prepare.status -cne 'PREPARED' -or -not (Same-Path ([string]$prepare.output_root) $client) -or [string]$prepare.server.address -cne $ServerAddress -or $prepare.server.acceptTextures -ne $false -or [string]$prepare.server.remote_pack -cne 'REJECT' -or [string]$prepare.heap.xms -cne '2G' -or [string]$prepare.heap.xmx -cne '4G' -or $prepare.release.permanent_mod_count_cap -ne $false -or $prepare.safety.java_started -ne $false -or $prepare.safety.prism_started -ne $false) { throw 'Attempt9 client prepare report binding/policy mismatch' }

$templateState = Validate-Instance-Metadata $template
$mutableNames = @(Get-MutableDirectoryNames $client)
$sharedTargets = Validate-Shared-Junctions $client $prism $client $target
$modState = Validate-Mods $client
$mcmodsyncState = Validate-MCModSync-Zero $client
$packState = Validate-Local-Pack $client
$sourceOptions = Validate-Options (Join-Path $client 'options.txt') $ServerAddress
$sourceServers = Join-Path $client 'servers.dat'
if (-not (Test-Path -LiteralPath $sourceServers -PathType Leaf) -or (Is-Reparse (Get-Item -LiteralPath $sourceServers -Force))) { throw 'Attempt9 servers.dat missing or linked' }
$sourceSnapshot = Snapshot-CopySet $client $mutableNames
$sourceLatestWriteUtc = Get-CopySetLatestWriteUtc $client $mutableNames
$gateState = Inspect-Gate $gatePath $client ([int]$modState.active_jar_count) $sourceLatestWriteUtc (-not $PreflightOnly.IsPresent)

if ($PreflightOnly.IsPresent) {
    $value = [ordered]@{
        schema = 1; status = 'PREFLIGHT_PASS'; attempt = 9; generated_at_utc = [DateTime]::UtcNow.ToString('o')
        source_client_root = $client; source_prepare_report = $preparePath; source_prepare_report_sha256 = $expectedPrepareReportSha256
        target_instance = $target; target_already_exists = $false; template_instance = $template
        gate = $gateState; import_blocked_until_matching_gate_pass = (-not $gateState.import_allowed)
        copied_mutable_directories = $mutableNames; excluded_runtime_directories = $excludedRuntimeDirectoryNames
        source_copy_snapshot = $sourceSnapshot; mods = $modState; mcmodsync = $mcmodsyncState; local_resource_pack = $packState
        shared_junction_targets = $sharedTargets; options = $sourceOptions
        server = [ordered]@{ address = $ServerAddress; acceptTextures = $false; auto_join = $false; source_servers_dat_sha256 = (Sha256 $sourceServers) }
        memory = [ordered]@{ minimum_mb = $MinMemoryMb; maximum_mb = $MaxMemoryMb }
        minecraft = '1.21.1'; neoforge = '21.1.241'; permanent_mod_count_cap = $false
        source_or_prism_instance_writes = 0; evidence_files_written = 2; java_started = $false; prism_started = $false
    }
    $json = ($value | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    try {
        Write-NewUtf8 $reportPath $json
        $hash = Sha256 $reportPath
        Write-NewUtf8 $reportSidecar ($hash + '  ' + [IO.Path]::GetFileName($reportPath) + [Environment]::NewLine)
    } catch {
        if (Test-Path -LiteralPath $reportSidecar -PathType Leaf) { Remove-Item -LiteralPath $reportSidecar -Force }
        if (Test-Path -LiteralPath $reportPath -PathType Leaf) { Remove-Item -LiteralPath $reportPath -Force }
        throw
    }
    [ordered]@{ status = 'PREFLIGHT_PASS'; report = $reportPath; report_sha256 = $hash; gate_status = $gateState.status; import_allowed = $gateState.import_allowed; source_tree_sha256 = $sourceSnapshot.tree_sha256; java_started = $false; prism_started = $false } | ConvertTo-Json -Depth 6
    exit 0
}

$temp = Join-Path $instances ('.mechanomania-attempt9-import-' + [Guid]::NewGuid().ToString('N'))
$tempMc = Join-Path $temp 'minecraft'
$published = $false; $reportWritten = $false; $sidecarWritten = $false
try {
    New-Item -ItemType Directory -Path $tempMc | Out-Null
    foreach ($name in $sharedDirectoryNames) { New-Item -ItemType Junction -Path (Join-Path $tempMc $name) -Target ([string]$sharedTargets[$name]) | Out-Null }
    foreach ($name in $mutableNames) { Copy-Tree (Join-Path $client $name) (Join-Path $tempMc $name) }
    New-Item -ItemType Directory -Path (Join-Path $tempMc 'natives') | Out-Null
    Copy-Item -LiteralPath (Join-Path $client 'options.txt') -Destination (Join-Path $tempMc 'options.txt')
    Set-Options (Join-Path $tempMc 'options.txt') $ServerAddress
    [IO.File]::WriteAllBytes((Join-Path $tempMc 'servers.dat'), (New-ServersDat $ServerAddress))
    Copy-Item -LiteralPath $templateState.mmc_path -Destination (Join-Path $temp 'mmc-pack.json')
    Copy-Item -LiteralPath $templateState.cfg_path -Destination (Join-Path $temp 'instance.cfg')
    Set-Cfg (Join-Path $temp 'instance.cfg') $InstanceName
    $icon = Join-Path $template 'icon.png'
    $iconHash = if (Test-Path -LiteralPath $icon -PathType Leaf) { $h = Sha256 $icon; Copy-Item -LiteralPath $icon -Destination (Join-Path $temp 'icon.png'); $h } else { $null }

    $targetSnapshot = Snapshot-CopySet $tempMc $mutableNames
    $sourceAfterCopy = Snapshot-CopySet $client $mutableNames
    if (-not (Same-Snapshot $sourceSnapshot $targetSnapshot) -or -not (Same-Snapshot $sourceSnapshot $sourceAfterCopy)) { throw 'Attempt9 source changed during import or copied snapshot differs' }
    $sourceLatestAfterCopyUtc = Get-CopySetLatestWriteUtc $client $mutableNames
    $gateLastWriteUtc = [DateTime]::Parse([string]$gateState.report_last_write_utc, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
    if ($sourceLatestAfterCopyUtc -gt $gateLastWriteUtc) { throw 'Attempt9 client changed after its PASS gate report' }
    $targetModState = Validate-Mods $tempMc
    $targetMCModSync = Validate-MCModSync-Zero $tempMc
    $targetPack = Validate-Local-Pack $tempMc
    $targetOptions = Validate-Options (Join-Path $tempMc 'options.txt') $ServerAddress
    $expectedServers = New-ServersDat $ServerAddress
    if (-not (Bytes-Equal ([IO.File]::ReadAllBytes((Join-Path $tempMc 'servers.dat'))) $expectedServers)) { throw 'Published servers.dat is not the exact local acceptTextures=false payload' }
    $targetCfg = Validate-Cfg (Join-Path $temp 'instance.cfg') $InstanceName
    $targetMetadata = Validate-Instance-Metadata $temp
    $targetShared = Validate-Shared-Junctions $tempMc $prism $client $target
    foreach ($name in $sharedDirectoryNames) { if ([string]$targetShared[$name] -cne [string]$sharedTargets[$name]) { throw "Published shared junction changed: $name" } }
    if ((Sha256 $templateState.mmc_path) -ne $templateState.mmc_sha256 -or (Sha256 $templateState.cfg_path) -ne $templateState.cfg_sha256 -or ($null -ne $iconHash -and (Sha256 $icon) -ne $iconHash)) { throw 'Prism template changed during import' }

    Move-Item -LiteralPath $temp -Destination $target
    $published = $true; $temp = $null
    $value = [ordered]@{
        schema = 1; status = 'IMPORTED_PRISM_INSTANCE'; attempt = 9; imported_at_utc = [DateTime]::UtcNow.ToString('o'); ready_for_manual_launch = $true
        source_client_root = $client; source_prepare_report = $preparePath; source_prepare_report_sha256 = $expectedPrepareReportSha256; source_unchanged_during_copy = $true
        gate = $gateState; source_template_instance = $template; source_template_unchanged = $true
        instance_name = $InstanceName; instance_path = $target; minecraft_path = (Join-Path $target 'minecraft')
        copied_mutable_directories = $mutableNames; excluded_runtime_directories = $excludedRuntimeDirectoryNames
        copy_snapshot = $targetSnapshot; mods = $targetModState; mcmodsync = $targetMCModSync; local_resource_pack = $targetPack
        shared_junction_targets = $targetShared
        server = [ordered]@{ address = $ServerAddress; acceptTextures = $false; auto_join = $false; servers_dat_sha256 = (Sha256 (Join-Path $target 'minecraft\servers.dat')); options_sha256 = $targetOptions.sha256; production_server_configuration_modified = $false }
        memory = [ordered]@{ minimum_mb = $MinMemoryMb; maximum_mb = $MaxMemoryMb }; instance_cfg_sha256 = $targetCfg.sha256; mmc_pack_sha256 = $targetMetadata.mmc_sha256
        minecraft = '1.21.1'; neoforge = '21.1.241'; permanent_mod_count_cap = $false
        java_started_by_importer = $false; prism_started_by_importer = $false; automatic_server_join = $false
        manual_action = 'Refresh Prism if it is already open, then manually launch this new instance when the server test is ready.'
    }
    $json = ($value | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    Write-NewUtf8 $reportPath $json; $reportWritten = $true
    $hash = Sha256 $reportPath
    Write-NewUtf8 $reportSidecar ($hash + '  ' + [IO.Path]::GetFileName($reportPath) + [Environment]::NewLine); $sidecarWritten = $true
    [ordered]@{ status = 'IMPORTED_PRISM_INSTANCE'; instance_path = $target; report = $reportPath; report_sha256 = $hash; source_tree_sha256 = $targetSnapshot.tree_sha256; mcmodsync_active = 0; java_started = $false; prism_started = $false } | ConvertTo-Json -Depth 6
} catch {
    if (Test-Path -LiteralPath $reportSidecar -PathType Leaf) { Remove-Item -LiteralPath $reportSidecar -Force }
    if (Test-Path -LiteralPath $reportPath -PathType Leaf) { Remove-Item -LiteralPath $reportPath -Force }
    if ($published -and (Test-Path -LiteralPath $target -PathType Container) -and (Path-IsWithin $target $instances) -and -not (Same-Path $target $instances)) { Remove-Item -LiteralPath $target -Recurse -Force }
    if ($null -ne $temp -and (Test-Path -LiteralPath $temp -PathType Container) -and (Path-IsWithin $temp $instances) -and ([IO.Path]::GetFileName($temp)).StartsWith('.mechanomania-attempt9-import-', [StringComparison]::Ordinal)) { Remove-Item -LiteralPath $temp -Recurse -Force }
    throw
}
