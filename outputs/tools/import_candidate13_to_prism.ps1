param(
    [string] $ClientRoot = '',
    [string] $PrismRoot = '<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3',
    [string] $ReleaseRoot = '<AUDIT_ROOT>\final-mod-bundles-candidate13-20260812',
    [string] $TemplateInstanceName = '',
    [string] $InstanceName = '',
    [string] $Report = '',
    [string] $ServerAddress = 'play.example.invalid:12341',
    [switch] $PreflightOnly
)

# Candidate13 Prism importer.  This is deliberately a fresh-instance writer:
# it never edits or reuses an existing Candidate11/12 instance, never starts
# Java/Prism, and carries only the audited client state into the new instance.
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedClientRoot = Join-Path $workspace 'outputs\tmp\client-gate-candidate13\.minecraft'
$expectedReport = Join-Path $workspace 'outputs\candidate13-prism-import-20260812.json'
$expectedRelease = '<AUDIT_ROOT>\final-mod-bundles-candidate13-20260812'
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
$packStem = ([char]0x4e16) + ([char]0x754c) + ([char]0x6307) + ([char]0x5b9a) + ([char]0x8d44) + ([char]0x6e90) + ([char]0x5305) + ([char]0x55b5)
$packFileName = $packStem + '-mc1.21.1-candidate13.zip'
$candidate11Stem = ([char]0x52A8) + ([char]0x9759) + ([char]0x4EA4) + ([char]0x6620)
$defaultTemplateName = $candidate11Stem + '-Candidate11-NeoForge-1.21.1-20260811'
$defaultInstanceName = $candidate11Stem + '-Candidate13-NeoForge-1.21.1-20260812'

if ([string]::IsNullOrWhiteSpace($ClientRoot)) { $ClientRoot = $expectedClientRoot }
if ([string]::IsNullOrWhiteSpace($TemplateInstanceName)) { $TemplateInstanceName = $defaultTemplateName }
if ([string]::IsNullOrWhiteSpace($InstanceName)) { $InstanceName = $defaultInstanceName }
if ([string]::IsNullOrWhiteSpace($Report)) { $Report = $expectedReport }

function Full-Path([string] $Path) { return [IO.Path]::GetFullPath($Path).TrimEnd('\') }
function Same-Path([string] $Left, [string] $Right) { return [string]::Equals((Full-Path $Left), (Full-Path $Right), [StringComparison]::OrdinalIgnoreCase) }
function Path-IsWithin([string] $Path, [string] $Parent) { return ((Full-Path $Path) + '\').StartsWith(((Full-Path $Parent) + '\'), [StringComparison]::OrdinalIgnoreCase) }
function Sha256([string] $Path) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant() }
function Bytes-Sha256([byte[]] $Bytes) { $sha=[Security.Cryptography.SHA256]::Create(); try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '') } finally { $sha.Dispose() } }
function Bytes-Equal([byte[]] $Left, [byte[]] $Right) {
    if ($null -eq $Left -or $null -eq $Right) { return $false }
    if ($Left.Length -ne $Right.Length) { return $false }
    for ($i = 0; $i -lt $Left.Length; $i++) { if ($Left[$i] -ne $Right[$i]) { return $false } }
    return $true
}
function Bundle-Digest([object[]] $Rows, [hashtable] $ByName) {
    $records=[Collections.Generic.List[string]]::new(); foreach($row in $Rows){$name=[string]$row.file; $records.Add($name+[char]0+(Sha256 $ByName[$name].FullName))}; return Bytes-Sha256 ([Text.Encoding]::UTF8.GetBytes(($records -join "`n")+"`n"))
}
function Relative([string] $Base, [string] $Path) { $prefix=(Full-Path $Base)+'\'; $full=Full-Path $Path; if(-not $full.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw "Path outside base: $full"}; return $full.Substring($prefix.Length).Replace('\','/') }
function Copy-Tree([string] $Source, [string] $Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Source tree missing: $Source" }
    New-Item -ItemType Directory -Path $Destination | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $Source -Force)) {
        if ([int]$item.Attributes -band 0x400) { throw "Unexpected reparse point in copied tree: $($item.FullName)" }
        $target=Join-Path $Destination $item.Name
        if ($item.PSIsContainer) { Copy-Tree $item.FullName $target } else { Copy-Item -LiteralPath $item.FullName -Destination $target }
    }
}
function U16BE([int] $Value) { return [byte[]]@([byte](($Value -shr 8) -band 255), [byte]($Value -band 255)) }
function I32BE([int] $Value) { return [byte[]]@([byte](($Value -shr 24) -band 255), [byte](($Value -shr 16) -band 255), [byte](($Value -shr 8) -band 255), [byte]($Value -band 255)) }
function Nbt-String([string] $Value) { $b=[Text.Encoding]::UTF8.GetBytes($Value); return [byte[]](@(U16BE $b.Length)+$b) }
function Nbt-Tag([int] $Id, [string] $Name, [byte[]] $Payload) { return [byte[]](@([byte]$Id)+(Nbt-String $Name)+$Payload) }
function New-ServersDat([string] $Address) {
    $entry=[byte[]](@(Nbt-Tag 8 'name' (Nbt-String 'Minecraft Server'))+(Nbt-Tag 8 'ip' (Nbt-String $Address))+(Nbt-Tag 1 'acceptTextures' ([byte[]]@(0)))+(Nbt-Tag 1 'hidden' ([byte[]]@(1)))+[byte]0)
    $list=[byte[]](@([byte]10)+(I32BE 1)+$entry); return [byte[]](@([byte]10,[byte]0,[byte]0)+(Nbt-Tag 9 'servers' $list)+[byte]0)
}
function New-AllowedServersDat([string] $Address) {
    return @((New-ServersDat $Address),(New-ServersDat '127.0.0.1:12341'))
}
function Read-PackFormat([string] $Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip=[IO.Compression.ZipFile]::OpenRead($Path); try {$entry=$zip.GetEntry('pack.mcmeta'); if($null -eq $entry){throw 'pack.mcmeta missing'}; $reader=[IO.StreamReader]::new($entry.Open(),[Text.Encoding]::UTF8,$true); try{$json=$reader.ReadToEnd()|ConvertFrom-Json}finally{$reader.Dispose()}; return [int]$json.pack.pack_format} finally {$zip.Dispose()}
}
function Option-ResourcePackIds([string] $Line) {
    $values = [Collections.Generic.List[string]]::new()
    foreach ($match in [Text.RegularExpressions.Regex]::Matches($Line, '"((?:\\.|[^"])*)"')) {
        $values.Add([Text.RegularExpressions.Regex]::Unescape($match.Groups[1].Value))
    }
    return $values.ToArray()
}
function Validate-Mods([string] $Root, [object] $Manifest) {
    $mods=Join-Path $Root 'mods'; if(-not (Test-Path -LiteralPath $mods -PathType Container)){throw 'Client root mods directory missing'}
    $files=@(Get-ChildItem -LiteralPath $mods -File|Sort-Object Name); if($files.Count -ne $expectedJarCount -or @($files|Where-Object{$_.Extension -ine '.jar'}).Count -ne 0){throw 'Client root must contain exact 52 JARs'}
    $by=@{}; foreach($f in $files){$by[$f.Name]=$f}
    foreach($row in @($Manifest.files)){ $name=[string]$row.file; if(-not $by.ContainsKey($name)){throw "Client root JAR missing: $name"}; if($by[$name].Length -ne [long]$row.bytes -or (Sha256 $by[$name].FullName) -ne ([string]$row.sha256).ToUpperInvariant()){throw "Client root JAR mismatch: $name"} }
    if((Bundle-Digest @($Manifest.files) $by) -ne $expectedBundleSha){throw 'Client root bundle digest mismatch'}
    return [ordered]@{files=$files.Count;bytes=(($files|Measure-Object Length -Sum).Sum);bundle_sha256=$expectedBundleSha}
}
function Validate-Options([string] $Path, [string] $Address) {
    $lines=[IO.File]::ReadAllLines($Path,[Text.Encoding]::UTF8); $packLine=@($lines|Where-Object{$_.StartsWith('resourcePacks:',[StringComparison]::Ordinal)}); $last=@($lines|Where-Object{$_.StartsWith('lastServer:',[StringComparison]::Ordinal)})
    $selected = if ($packLine.Count -eq 1) { @(Option-ResourcePackIds $packLine[0]) } else { @() }
    if($packLine.Count -ne 1 -or @($selected | Where-Object { $_ -ceq ('file/'+$packFileName) }).Count -ne 1 -or @($selected | Where-Object { $_ -ceq ('file/'+$packStem+'.zip') }).Count -ne 0) { throw 'Candidate13 options.txt local/remote resource-pack policy mismatch' }
    if($last.Count -ne 1 -or $last[0] -cne ('lastServer:'+ $Address)) { throw 'Candidate13 options.txt server endpoint mismatch' }
    return [ordered]@{sha256=(Sha256 $Path);local_pack_selected_once=@($selected | Where-Object { $_ -ceq ('file/'+$packFileName) }).Count;last_server=$Address;unicode_escape_normalization_accepted=$true}
}

$client=Full-Path $ClientRoot; $prism=Full-Path $PrismRoot; $release=Full-Path $ReleaseRoot; $report=Full-Path $Report
if(-not (Same-Path $client $expectedClientRoot)){throw "Candidate13 client root is not the locked fresh root: $client"}
if(-not (Same-Path $release $expectedRelease)){throw "Candidate13 release path is not locked: $release"}
if(-not (Path-IsWithin $report $workspace)){throw 'Prism import report must remain under workspace outputs'}
if($ServerAddress -notmatch '^(\[[^\]]+\]|[^:]+):12341$'){throw 'Candidate13 importer must retain port 12341'}
$instances=Join-Path $prism 'instances'; $template=Join-Path $instances $TemplateInstanceName; $target=Join-Path $instances $InstanceName
if(-not (Test-Path -LiteralPath (Join-Path $prism 'portable.txt') -PathType Leaf)){throw "Not a Prism portable root: $prism"}
if(-not (Test-Path -LiteralPath $instances -PathType Container)){throw "Prism instances directory missing: $instances"}
if(-not (Test-Path -LiteralPath $template -PathType Container)){throw "Candidate11 template instance missing: $template"}
if(-not (Path-IsWithin $template $instances) -or -not (Path-IsWithin $target $instances)){throw 'Prism instance path isolation failed'}
if(Same-Path $template $target){throw 'Candidate13 target must differ from Candidate11 template'}
if(-not $PreflightOnly.IsPresent -and (Test-Path -LiteralPath $target)){throw "Refusing to overwrite existing Candidate13 Prism instance: $target"}
if(-not $PreflightOnly.IsPresent -and (Test-Path -LiteralPath $report)){throw 'Refusing to overwrite existing Candidate13 Prism import report'}
$ready=Join-Path $release 'READY.json'; $lock=Join-Path $release 'release-lock.json'; $manifestPath=Join-Path $release 'manifests\client.json'; $manifest=Get-Content -Raw $manifestPath|ConvertFrom-Json
if((Sha256 $ready)-ne $expectedReadySha -or (Sha256 $lock)-ne $expectedReadySha -or (Sha256 $manifestPath)-ne $expectedManifestSha){throw 'Candidate13 release fingerprint mismatch'}
if(-not (Bytes-Equal ([IO.File]::ReadAllBytes($ready)) ([IO.File]::ReadAllBytes($lock)))){throw 'Candidate13 READY/release-lock bytes differ'}
$readyJson=Get-Content -Raw $ready|ConvertFrom-Json; if([int]$readyJson.candidate -ne 13 -or [string]$readyJson.status -cne 'PASS' -or [int]$manifest.file_count -ne $expectedJarCount -or ([string]$manifest.bundle_sha256).ToUpperInvariant() -ne $expectedBundleSha){throw 'Candidate13 release content binding mismatch'}
$pack=Join-Path $client ('resourcepacks\'+$packFileName); if(-not (Test-Path -LiteralPath $pack -PathType Leaf)){throw 'Fresh Candidate13 client root lacks the derived local pack'}; if((Get-Item $pack).Length -ne $expectedPackBytes -or (Sha256 $pack)-ne $expectedPackSha -or (Read-PackFormat $pack)-ne $expectedPackFormat){throw 'Fresh Candidate13 local pack fingerprint mismatch'}
$clientState=Validate-Mods $client $manifest; $optionsState=Validate-Options (Join-Path $client 'options.txt') $ServerAddress; $serversPath=Join-Path $client 'servers.dat'; $expectedServers=New-ServersDat $ServerAddress; $actualServers=if(Test-Path -LiteralPath $serversPath -PathType Leaf){[IO.File]::ReadAllBytes($serversPath)}else{@()}; if(@(New-AllowedServersDat $ServerAddress|Where-Object{Bytes-Equal $actualServers $_}).Count -eq 0){throw 'Fresh Candidate13 servers.dat does not reject remote packs or retain port 12341'}
$mmcPath=Join-Path $template 'mmc-pack.json'; $cfgPath=Join-Path $template 'instance.cfg'; if(-not (Test-Path -LiteralPath $mmcPath -PathType Leaf)-or -not(Test-Path -LiteralPath $cfgPath -PathType Leaf)){throw 'Candidate11 template metadata missing'}; $mmc=Get-Content -Raw $mmcPath|ConvertFrom-Json; $mc=@($mmc.components|Where-Object{[string]$_.uid -ceq 'net.minecraft'}); $neo=@($mmc.components|Where-Object{[string]$_.uid -ceq 'net.neoforged'}); if($mc.Count -ne 1 -or [string]$mc[0].version -cne '1.21.1' -or $neo.Count -ne 1 -or [string]$neo[0].version -cne '21.1.241'){throw 'Candidate11 template is not NeoForge 1.21.1/21.1.241'}
if($PreflightOnly){[ordered]@{schema=1;status='PREFLIGHT_PASS';candidate=13;client_root=$client;template_instance=$template;target_instance=$target;release_ready_sha256=$expectedReadySha;client_manifest_sha256=$expectedManifestSha;client_bundle_sha256=$expectedBundleSha;client_bundle=$clientState;local_resource_pack=[ordered]@{path=$pack;sha256=$expectedPackSha;bytes=$expectedPackBytes;pack_format=$expectedPackFormat;enabled_exactly_once=$true};resource_pack_policy=[ordered]@{remote_server_pack='REJECT';acceptTextures=$false;server_address=$ServerAddress};minecraft='1.21.1';neoforge='21.1.241';java_started=$false;prism_started=$false;writes_performed=0}|ConvertTo-Json -Depth 10; exit 0}

$temp=Join-Path $instances ('.candidate13-import-'+[Guid]::NewGuid().ToString('N')); $tempMc=Join-Path $temp 'minecraft'; $published=$false
try {
    New-Item -ItemType Directory -Path $tempMc | Out-Null
    foreach($name in @('assets','libraries','versions')){$src=Get-Item -LiteralPath (Join-Path $client $name) -Force; if($src.LinkType -ne 'Junction'){throw "Fresh shared directory is not a junction: $name"}; $resolved=Full-Path ([string]$src.Target); if(Path-IsWithin $resolved '<TRANS_ROOT>\20260807'){throw "Shared directory resolves into historical backup: $resolved"}; New-Item -ItemType Junction -Path (Join-Path $tempMc $name) -Target $resolved|Out-Null}
    foreach($name in @('config','defaultconfigs','data')){Copy-Tree (Join-Path $client $name) (Join-Path $tempMc $name)}
    foreach($name in @('options.txt','servers.dat')){Copy-Item -LiteralPath (Join-Path $client $name) -Destination (Join-Path $tempMc $name)}
    foreach($name in @('mods','resourcepacks')){New-Item -ItemType Directory -Path (Join-Path $tempMc $name)|Out-Null}
    foreach($row in @($manifest.files)){ $name=[string]$row.file; Copy-Item -LiteralPath (Join-Path $client "mods\$name") -Destination (Join-Path $tempMc "mods\$name") }
    Copy-Item -LiteralPath $pack -Destination (Join-Path $tempMc "resourcepacks\$packFileName")
    New-Item -ItemType Directory -Path (Join-Path $tempMc 'natives')|Out-Null
    Copy-Item -LiteralPath $mmcPath -Destination (Join-Path $temp 'mmc-pack.json')
    $cfg=[IO.File]::ReadAllText($cfgPath,[Text.Encoding]::UTF8); if($cfg -notmatch '(?m)^name='){throw 'Template instance.cfg has no name field'}; $cfg=[Regex]::Replace($cfg,'(?m)^name=.*$','name='+$InstanceName,1); [IO.File]::WriteAllText((Join-Path $temp 'instance.cfg'),$cfg,[Text.UTF8Encoding]::new($false))
    $icon=Join-Path $template 'icon.png'; if(Test-Path -LiteralPath $icon -PathType Leaf){Copy-Item -LiteralPath $icon -Destination (Join-Path $temp 'icon.png')}
    $allowed=@('assets','config','data','defaultconfigs','libraries','mods','natives','options.txt','resourcepacks','servers.dat','versions'); $actual=@(Get-ChildItem -LiteralPath $tempMc -Force|ForEach-Object{$_.Name}); if(@($actual|Where-Object{$allowed -notcontains $_}).Count -ne 0){throw 'Unexpected runtime state leaked into Candidate13 Prism minecraft root'}
    if(@(Get-ChildItem -LiteralPath (Join-Path $tempMc 'resourcepacks') -Force).Count -ne 1){throw 'Candidate13 Prism root has extra resource packs'}
    if(-not (Bytes-Equal ([IO.File]::ReadAllBytes((Join-Path $tempMc 'servers.dat'))) $expectedServers)){throw 'Published Candidate13 servers.dat policy mismatch'}
    Validate-Options (Join-Path $tempMc 'options.txt') $ServerAddress | Out-Null
    Move-Item -LiteralPath $temp -Destination $target; $published=$true; $temp=$null
    $reportValue=[ordered]@{schema=1;status='IMPORTED_PRISM_INSTANCE';candidate=13;ready_for_manual_launch=$true;source_client_root=$client;source_template_instance=$template;source_template_unchanged=$true;instance_name=$InstanceName;instance_path=$target;minecraft_path=(Join-Path $target 'minecraft');minecraft='1.21.1';neoforge='21.1.241';release=[ordered]@{root=$release;ready_sha256=$expectedReadySha;client_manifest_sha256=$expectedManifestSha;client_bundle_sha256=$expectedBundleSha;file_count=$expectedJarCount};local_resource_pack=[ordered]@{file=$packFileName;sha256=$expectedPackSha;bytes=$expectedPackBytes;pack_format=$expectedPackFormat;enabled_exactly_once=$true};resource_pack_policy=[ordered]@{remote_server_pack='REJECT';acceptTextures=$false;server_address=$ServerAddress};excluded_runtime_state=@('logs','saves','downloads','screenshots','journeymap','schematics','server-resource-packs','server-resource-packs-cache','cache');java_started_by_importer=$false;prism_started_by_importer=$false;manual_action='Refresh Prism and launch the new Candidate13 instance manually for the runtime join gate.'}
    New-Item -ItemType Directory -Path (Split-Path -Parent $report) -Force|Out-Null; $json=($reportValue|ConvertTo-Json -Depth 10)+[Environment]::NewLine; $stream=[IO.File]::Open($report,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None); try{$b=[Text.UTF8Encoding]::new($false).GetBytes($json);$stream.Write($b,0,$b.Length);$stream.Flush($true)}finally{$stream.Dispose()}; $reportValue
} catch {if($null -ne $temp -and(Test-Path -LiteralPath $temp)){Remove-Item -LiteralPath $temp -Recurse -Force};if($published -and(Test-Path -LiteralPath $target)){Remove-Item -LiteralPath $target -Recurse -Force};throw}
