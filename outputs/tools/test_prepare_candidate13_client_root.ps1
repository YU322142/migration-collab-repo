$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'prepare_candidate13_client_root.ps1'
$tokens = $null; $errors = $null
[Management.Automation.Language.Parser]::ParseFile($scriptPath,[ref]$tokens,[ref]$errors) | Out-Null
if(@($errors).Count -ne 0){throw "Parser errors: $(@($errors).Message -join '; ')"}
$text=Get-Content -Raw -LiteralPath $scriptPath
foreach($needle in @(
    'final-mod-bundles-candidate13-20260812',
    'client-gate-candidate13\.minecraft',
    'FA992151079AEE46DCDAEB49D23487F0F4642099E86F0962469E2257E830BA3F',
    '261ADB612DB2A2D992F8A8CAC0FC8C753D6620B98B8CB79E693CC434E57216BE',
    'AC9887DB6F12E0A9E9F8B77030C3F904276DB8BFD4BDF9D01C4B9DAF9EEA4495',
    '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364',
    'acceptTextures',
    'server_properties_modified=$false',
    'java_started=$false',
    'prism_started=$false',
    'Refusing to overwrite Candidate13 client root'
)){if(-not $text.Contains($needle)){throw "Missing Candidate13 preparation binding: $needle"}}
foreach($needle in @('Start-Process','java.exe','javaw.exe','prismlauncher.exe')){if($text.Contains($needle)){throw "Forbidden Candidate13 preparation action: $needle"}}
$preflight=& $scriptPath -PreflightOnly | ConvertFrom-Json
if($preflight.status -cne 'PREFLIGHT_PASS' -or [int]$preflight.client_file_count -ne 52 -or [int]$preflight.server.port -ne 12341 -or $preflight.server.accept_remote_resource_pack -ne $false -or $preflight.writes_performed -ne 0){throw 'Candidate13 preparation preflight contract failed'}
[ordered]@{status='PASS';parser_errors=0;client_jars=52;server_port=12341;remote_resource_pack='REJECT';writes=0;java_started=$false;prism_started=$false}|ConvertTo-Json
