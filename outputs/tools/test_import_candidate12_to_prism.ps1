$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'import_candidate12_to_prism.ps1'
$tokens = $null
$errors = $null
[Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors) | Out-Null
if (@($errors).Count -ne 0) { throw "Parser errors: $(@($errors).Message -join '; ')" }

$text = Get-Content -LiteralPath $scriptPath -Raw
$required = @(
    'final-mod-bundles-candidate12-20260811',
    'Candidate12-NeoForge-1.21.1-20260811',
    'Candidate11-NeoForge-1.21.1-20260811',
    'ExpectedReleaseSha256',
    'ExpectedWaypointSha256',
    '613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E',
    '1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D',
    'CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B',
    '5572EE1F196038071FB5D7B9D7FF271CCB0E19BA722B83BCC1A2B8C0C844F8EB',
    'Refusing to overwrite existing Candidate12 Prism instance',
    'source_instance_unchanged',
    'java_started_by_importer = $false',
    'prism_started_by_importer = $false',
    'Write-Utf8NoBomCreateNew'
)
foreach ($needle in $required) {
    if (-not $text.Contains($needle)) { throw "Missing strict Candidate12 binding: $needle" }
}

$forbidden = @(
    'final-mod-bundles-candidate10-20260811',
    'Remove-Item -LiteralPath $sourceInstance',
    'Start-Process',
    'java.exe',
    'javaw.exe'
)
foreach ($needle in $forbidden) {
    if ($text.Contains($needle)) { throw "Forbidden Candidate12 importer binding: $needle" }
}

[ordered]@{
    status = 'PASS'
    parser_errors = 0
    strict_bindings = $required.Count
    forbidden_bindings_absent = $forbidden.Count
    source_instance_overwrite = $false
    java_started = $false
    prism_started = $false
} | ConvertTo-Json
