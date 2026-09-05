param(
    [string] $ClientRoot = '',
    [string] $PrismRoot = '<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3',
    [string] $InstanceName = '',
    [string] $ServerAddress = 'play.example.invalid:12341'
)

# Read-only Candidate13 client + Prism audit.  This is intentionally separate
# from the writer so an existing instance can be rechecked without mutation.
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedClientRoot = Join-Path $workspace 'outputs\tmp\client-gate-candidate13\.minecraft'
$expectedRelease = '<AUDIT_ROOT>\final-mod-bundles-candidate13-20260812'
$expectedReadySha = 'FA992151079AEE46DCDAEB49D23487F0F4642099E86F0962469E2257E830BA3F'
$expectedManifestSha = '261ADB612DB2A2D992F8A8CAC0FC8C753D6620B98B8CB79E693CC434E57216BE'
$expectedBundleSha = 'AC9887DB6F12E0A9E9F8B77030C3F904276DB8BFD4BDF9D01C4B9DAF9EEA4495'
$expectedPackSha = '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364'
$expectedPackBytes = 110377999
$packStem = ([char]0x4E16)+([char]0x754C)+([char]0x6307)+([char]0x5B9A)+([char]0x8D44)+([char]0x6E90)+([char]0x5305)+([char]0x55B5)
$packName = $packStem + '-mc1.21.1-candidate13.zip'
$instanceStem = ([char]0x52A8)+([char]0x9759)+([char]0x4EA4)+([char]0x6620)
if([string]::IsNullOrWhiteSpace($ClientRoot)){$ClientRoot=$expectedClientRoot}
if([string]::IsNullOrWhiteSpace($InstanceName)){$InstanceName=$instanceStem+'-Candidate13-NeoForge-1.21.1-20260812'}

function Full([string]$Path){return [IO.Path]::GetFullPath($Path).TrimEnd('\')}
function Same([string]$A,[string]$B){return [string]::Equals((Full $A),(Full $B),[StringComparison]::OrdinalIgnoreCase)}
function Sha([string]$Path){return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()}
function Bytes-Sha([byte[]]$Value){$h=[Security.Cryptography.SHA256]::Create();try{return([BitConverter]::ToString($h.ComputeHash($Value))).Replace('-','')}finally{$h.Dispose()}}
function Bundle([object[]]$Rows,[hashtable]$Files){$values=[Collections.Generic.List[string]]::new();foreach($row in $Rows){$name=[string]$row.file;$values.Add($name+[char]0+(Sha $Files[$name].FullName))};return Bytes-Sha ([Text.Encoding]::UTF8.GetBytes(($values -join "`n")+"`n"))}
function U16([int]$v){return [byte[]]@([byte](($v-shr 8)-band 255),[byte]($v-band 255))}
function I32([int]$v){return [byte[]]@([byte](($v-shr 24)-band 255),[byte](($v-shr 16)-band 255),[byte](($v-shr 8)-band 255),[byte]($v-band 255))}
function Str([string]$v){$b=[Text.Encoding]::UTF8.GetBytes($v);return [byte[]](@(U16 $b.Length)+$b)}
function Tag([int]$id,[string]$name,[byte[]]$payload){return [byte[]](@([byte]$id)+(Str $name)+$payload)}
function Servers([string]$address){$e=[byte[]](@(Tag 8 'name' (Str 'Minecraft Server'))+(Tag 8 'ip' (Str $address))+(Tag 1 'acceptTextures' ([byte[]]@(0)))+(Tag 1 'hidden' ([byte[]]@(1)))+[byte]0);$l=[byte[]](@([byte]10)+(I32 1)+$e);return [byte[]](@([byte]10,[byte]0,[byte]0)+(Tag 9 'servers' $l)+[byte]0)}
function Equal-Bytes([byte[]]$a,[byte[]]$b){if($a.Length -ne $b.Length){return $false};for($i=0;$i -lt $a.Length;$i++){if($a[$i] -ne $b[$i]){return $false}};return $true}
function Allowed-Servers([string]$address){return @((Servers $address),(Servers '127.0.0.1:12341'))}
function Pack-Ids([string]$line){$values=[Collections.Generic.List[string]]::new();foreach($match in [regex]::Matches($line,'"((?:\\.|[^"])*)"')){$values.Add([regex]::Unescape($match.Groups[1].Value))};return $values.ToArray()}
function Audit-Root([string]$Root,[object]$Manifest,[byte[]]$ServersPayload){
    $files=@(Get-ChildItem -LiteralPath (Join-Path $Root 'mods') -File|Sort-Object Name);if($files.Count-ne52){throw "Exact 52-JAR set missing: $Root"};$by=@{};foreach($f in $files){$by[$f.Name]=$f};foreach($row in @($Manifest.files)){$name=[string]$row.file;if(-not$by.ContainsKey($name)-or$by[$name].Length-ne[long]$row.bytes-or(Sha $by[$name].FullName)-ne([string]$row.sha256).ToUpperInvariant()){throw "JAR mismatch: $Root :: $name"}};if((Bundle @($Manifest.files)$by)-ne$expectedBundleSha){throw "Bundle digest mismatch: $Root"}
    $pack=Join-Path $Root ('resourcepacks\'+$packName);if(@(Get-ChildItem -LiteralPath (Join-Path $Root 'resourcepacks') -Force).Count-ne1-or(Get-Item $pack).Length-ne$expectedPackBytes-or(Sha $pack)-ne$expectedPackSha){throw "Local resource pack mismatch: $Root"}
    $lines=[IO.File]::ReadAllLines((Join-Path $Root 'options.txt'),[Text.Encoding]::UTF8);$rp=@($lines|Where-Object{$_.StartsWith('resourcePacks:')});$ls=@($lines|Where-Object{$_.StartsWith('lastServer:')});$selected=if($rp.Count -eq 1){@(Pack-Ids $rp[0])}else{@()};if($rp.Count -ne 1 -or @($selected|Where-Object{$_ -ceq ('file/'+$packName)}).Count -ne 1 -or @($selected|Where-Object{$_ -ceq ('file/'+$packStem+'.zip')}).Count -ne 0 -or $ls.Count -ne 1 -or $ls[0] -cne ('lastServer:'+$ServerAddress)){throw "Client options mismatch: $Root"};$actualServers=[IO.File]::ReadAllBytes((Join-Path $Root 'servers.dat'));if(@(Allowed-Servers $ServerAddress|Where-Object{Equal-Bytes $actualServers $_}).Count -eq 0){throw "servers.dat does not prove acceptTextures=false or port 12341: $Root"}
    $usernameCache=Join-Path $Root 'config\voicechat\username-cache.json';if(Test-Path -LiteralPath $usernameCache){$raw=[IO.File]::ReadAllText($usernameCache,[Text.Encoding]::UTF8).Trim();if($raw -notin @('{}','')){throw "Voice-chat username identity cache leaked into fresh client: $Root"}}
    foreach($relative in @('config\spark\tmp','config\spark\tmp-client')){
        $tmp=Join-Path $Root $relative
        if(Test-Path -LiteralPath $tmp){
            $files=@(Get-ChildItem -LiteralPath $tmp -Recurse -File -Force)
            $unexpected=@($files|Where-Object{$_.Name -cne 'about.txt' -or $_.DirectoryName -cne (Full $tmp)})
            if($unexpected.Count -ne 0){throw "Spark runtime temp data leaked into fresh client: $($unexpected.FullName -join ', ')"}
        }
    }
    return [ordered]@{root=(Full $Root);jars=52;bundle_sha256=$expectedBundleSha;resource_pack_sha256=$expectedPackSha;resource_pack_enabled_exactly_once=$true;options_unicode_escape_normalization_accepted=$true;server_address=$ServerAddress;acceptTextures=$false;voicechat_username_cache_empty=$true;spark_temp_runtime_references_absent=$true}
}

$client=Full $ClientRoot;$prism=Full $PrismRoot;$instance=Join-Path (Join-Path $prism 'instances') $InstanceName
if(-not(Same $client $expectedClientRoot)){throw 'ClientRoot is not the locked Candidate13 path'}
foreach($path in @($client,$instance)){if(-not(Test-Path -LiteralPath $path -PathType Container)){throw "Candidate13 path missing: $path"}}
$ready=Join-Path $expectedRelease 'READY.json';$manifestPath=Join-Path $expectedRelease 'manifests\client.json';if((Sha $ready)-ne$expectedReadySha-or(Sha $manifestPath)-ne$expectedManifestSha){throw 'Candidate13 release identity mismatch'};$manifest=Get-Content -Raw $manifestPath|ConvertFrom-Json
$servers=Servers $ServerAddress;$clientState=Audit-Root $client $manifest $servers;$instanceMc=Join-Path $instance 'minecraft';$instanceState=Audit-Root $instanceMc $manifest $servers
$mmc=Get-Content -Raw (Join-Path $instance 'mmc-pack.json')|ConvertFrom-Json;$mc=@($mmc.components|Where-Object{$_.uid-ceq'net.minecraft'});$neo=@($mmc.components|Where-Object{$_.uid-ceq'net.neoforged'});if($mc.Count-ne1-or$mc[0].version-cne'1.21.1'-or$neo.Count-ne1-or$neo[0].version-cne'21.1.241'){throw 'Prism component binding mismatch'}
$forbidden=@('logs','saves','downloads','screenshots','journeymap','schematics','server-resource-packs','crash-reports','.cache');$leaked=@($forbidden|Where-Object{Test-Path -LiteralPath (Join-Path $instanceMc $_)});if($leaked.Count-ne0){throw "Runtime state leaked into Candidate13 Prism instance: $($leaked -join ', ')"}
[ordered]@{schema=1;status='PASS';category='candidate13_client_prism_read_only_audit';candidate=13;release_ready_sha256=$expectedReadySha;manifest_sha256=$expectedManifestSha;client_root=$clientState;prism_instance=$instanceState;minecraft='1.21.1';neoforge='21.1.241';forbidden_runtime_state_found=@();remote_resource_pack='REJECT';local_derived_resource_pack='ENABLED';server_port=12341;writes_performed=0;java_started=$false;prism_started=$false}|ConvertTo-Json -Depth 10
