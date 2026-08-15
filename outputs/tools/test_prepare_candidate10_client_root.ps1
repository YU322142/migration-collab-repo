$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'prepare_candidate10_client_root.ps1'

$tokens = $null
$errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$errors)
if (@($errors).Count -ne 0) {
    throw "Parser errors: $(@($errors).Message -join '; ')"
}

$text = Get-Content -LiteralPath $scriptPath -Raw
$required = @(
    'final-mod-bundles-candidate10-20260811',
    'CEC51F141A226E53E5CB0F64851E6EA37DE6FFC7BFD307863FE2563AA606737F',
    '36C1CE14EE18B81C04654F1A6956F2257B7DEAC07746E960475AAF5C6F25A579',
    '79677A95935DD67E4196C8CCC99F92D9D817087C1DC7402DCE3A614B44C89553',
    '71D13227E80AB70B04CDD800D6E786821ABA759F99397B52960974715DFF5108',
    'REJECTED_STALE',
    'Test-ZipCrc',
    'Refusing to overwrite client gate root',
    'candidate8_root_read_or_written = $false',
    'java_started = $false'
)
foreach ($needle in $required) {
    if (-not $text.Contains($needle)) { throw "Missing strict binding: $needle" }
}

$forbidden = @(
    'client-gate-candidate8\.minecraft',
    'final-mod-bundles-candidate9-20260811\client-mods',
    'Start-Process java',
    'java.exe',
    'javaw.exe'
)
foreach ($needle in $forbidden) {
    if ($text.Contains($needle)) { throw "Forbidden runtime/input binding: $needle" }
}

[ordered]@{
    status = 'PASS'
    parser_errors = 0
    strict_bindings = $required.Count
    forbidden_bindings_absent = $forbidden.Count
    java_started = $false
} | ConvertTo-Json
