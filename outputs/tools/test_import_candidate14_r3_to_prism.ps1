$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'import_candidate14_r3_to_prism.ps1'
$tokens = $null; $errors = $null
[Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if (@($errors).Count -ne 0) { throw "Parser errors: $(@($errors).Message -join '; ')" }
$text = [IO.File]::ReadAllText($scriptPath, [Text.Encoding]::UTF8)
foreach ($needle in @(
    'Candidate14-r3-NeoForge-1.21.1-20260812',
    '66778B3F91842D0AB6CC291D03AD9538AB12447F63340E6144747C4DAE819C24',
    '020352BA39C8FAAF511AFF02FD0F9A92451697F51A1C8E4D1E0B9BEFE0398AAC',
    '4658F5B6B75CEBC0E89C549427FBA10B87E9A05D6C934B408DEF85923493EF81',
    'FCBEFE432E802CA8834ADFEA8D360764F33697D84B690C53D085CBD3DCDE0E76',
    'release_scoped_exactness = $true',
    'permanent_mod_count_cap = $false',
    'remote_server_pack = ''REJECT''',
    'acceptTextures = $false',
    'runtime_install = ''NOT_INSTALLED''',
    'java_started_by_importer = $false',
    'prism_started_by_importer = $false',
    'Refusing to overwrite existing Candidate14-r3 Prism instance',
    '[IO.FileMode]::CreateNew'
)) { if (-not $text.Contains($needle)) { throw "Missing Candidate14-r3 Prism importer binding: $needle" } }
foreach ($needle in @('Start-Process', 'prismlauncher.exe', 'java.exe', 'javaw.exe', 'Remove-Item -LiteralPath $template')) { if ($text.Contains($needle)) { throw "Forbidden Candidate14-r3 Prism importer action: $needle" } }
$preflight = & $scriptPath -PreflightOnly | ConvertFrom-Json
if ($preflight.status -cne 'PREFLIGHT_PASS' -or [int]$preflight.client_bundle.files -ne 54 -or [long]$preflight.client_bundle.bytes -ne 145905880 -or [string]$preflight.release.client_bundle_sha256 -cne 'FCBEFE432E802CA8834ADFEA8D360764F33697D84B690C53D085CBD3DCDE0E76' -or $preflight.release.release_scoped_exactness -ne $true -or $preflight.release.permanent_mod_count_cap -ne $false -or $preflight.resource_pack_policy.remote_server_pack -cne 'REJECT' -or $preflight.resource_pack_policy.acceptTextures -ne $false -or $preflight.resource_pack_policy.manual_test_address -cne '127.0.0.1:12341' -or $preflight.mcmodsync.runtime_install -cne 'NOT_INSTALLED' -or [int]$preflight.writes_performed -ne 0 -or $preflight.java_started -ne $false -or $preflight.prism_started -ne $false) { throw 'Candidate14-r3 Prism preflight contract failed' }
[ordered]@{status = 'PASS'; parser_errors = 0; client_jars = 54; client_bytes = 145905880; minecraft = '1.21.1'; neoforge = '21.1.241'; manual_test_address = '127.0.0.1:12341'; remote_resource_pack = 'REJECT'; mcmodsync = 'NOT_INSTALLED'; writes = 0; java_started = $false; prism_started = $false} | ConvertTo-Json
