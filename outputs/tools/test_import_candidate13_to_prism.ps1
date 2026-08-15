$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'import_candidate13_to_prism.ps1'
$tokens = $null; $errors = $null
[Management.Automation.Language.Parser]::ParseFile($scriptPath,[ref]$tokens,[ref]$errors) | Out-Null
if(@($errors).Count -ne 0){throw "Parser errors: $(@($errors).Message -join '; ')"}
$text=Get-Content -Raw -LiteralPath $scriptPath
foreach($needle in @(
    'Candidate13-NeoForge-1.21.1-20260812',
    '21.1.241',
    'Refusing to overwrite existing Candidate13 Prism instance',
    'remote_server_pack=''REJECT''',
    'acceptTextures=$false',
    'java_started_by_importer=$false',
    'prism_started_by_importer=$false',
    'CreateNew'
)){if(-not $text.Contains($needle)){throw "Missing Candidate13 Prism importer binding: $needle"}}
foreach($needle in @('Start-Process','java.exe','javaw.exe','Remove-Item -LiteralPath $template')){if($text.Contains($needle)){throw "Forbidden Candidate13 Prism action: $needle"}}
$preflight=& $scriptPath -PreflightOnly | ConvertFrom-Json
if($preflight.status -cne 'PREFLIGHT_PASS' -or [int]$preflight.client_bundle.files -ne 52 -or $preflight.minecraft -cne '1.21.1' -or $preflight.neoforge -cne '21.1.241' -or $preflight.resource_pack_policy.remote_server_pack -cne 'REJECT' -or $preflight.resource_pack_policy.acceptTextures -ne $false -or $preflight.writes_performed -ne 0){throw 'Candidate13 Prism preflight contract failed'}
[ordered]@{status='PASS';parser_errors=0;client_jars=52;minecraft='1.21.1';neoforge='21.1.241';remote_resource_pack='REJECT';writes=0;java_started=$false;prism_started=$false}|ConvertTo-Json
