$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'prepare_candidate11_client_root.ps1'
$releaseRoot = '<AUDIT_ROOT>\final-mod-bundles-candidate11-20260811'
$readyPath = Join-Path $releaseRoot 'READY.json'
$manifestPath = Join-Path $releaseRoot 'manifests\client.json'

$tokens = $null
$errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if (@($errors).Count -ne 0) {
    throw "Parser errors: $(@($errors).Message -join '; ')"
}

$text = Get-Content -LiteralPath $scriptPath -Raw
$required = @(
    'final-mod-bundles-candidate11-20260811',
    'outputs\tmp\client-gate-candidate11\.minecraft',
    'Candidate11Gate',
    '00000000-0000-0000-0000-000000001101',
    '613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E',
    '1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D',
    'CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B',
    'FC008BD9ED9ABF5FF23B61E40ADDCAC46986E22147EB2437324C48E2E9242E56',
    '6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7',
    'AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A',
    'Candidate11 offline identity is immutable',
    'candidate10_root_read_or_written = $false',
    'prior_gate_root_read_or_written = $false',
    'java_started = $false'
)
foreach ($needle in $required) {
    if (-not $text.Contains($needle)) { throw "Missing strict Candidate11 binding: $needle" }
}

$forbidden = @(
    'outputs\tmp\client-gate-candidate10\.minecraft',
    'final-mod-bundles-candidate10-20260811\client-mods',
    'Start-Process java',
    'java.exe',
    'javaw.exe'
)
foreach ($needle in $forbidden) {
    if ($text.Contains($needle)) { throw "Forbidden runtime/input binding: $needle" }
}

$readyHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $readyPath).Hash
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash
$ready = Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$jars = @(Get-ChildItem -LiteralPath (Join-Path $releaseRoot 'client-mods') -File)
if ($readyHash -cne '613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E' -or
    $manifestHash -cne '1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D' -or
    [int]$ready.candidate -ne 11 -or [string]$ready.status -cne 'PASS' -or
    [int]$ready.client.file_count -ne 52 -or [int]$manifest.file_count -ne 52 -or
    $jars.Count -ne 52) {
    throw 'Frozen Candidate11 release does not match the preparation test contract'
}

foreach ($guard in @(
    @('cctweaked-startup-shutdown-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar', '6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7'),
    @('create-chute-unload-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar', 'AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A')
)) {
    $path = Join-Path $releaseRoot ('client-mods\' + $guard[0])
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash -cne $guard[1]) {
        throw "Candidate11 guard hash mismatch: $($guard[0])"
    }
}

[ordered]@{
    status = 'PASS'
    parser_errors = 0
    strict_bindings = $required.Count
    forbidden_bindings_absent = $forbidden.Count
    frozen_client_jars = $jars.Count
    java_started = $false
} | ConvertTo-Json
