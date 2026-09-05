[CmdletBinding()]
param(
    [string]$SourceServerRoot = '<AUDIT_ROOT>\mechanomania-matched-runtime-attempt13-20260814',
    [string]$TestRoot = '<AUDIT_ROOT>\xiyuslogin-auto-session-script-test-20260815'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$deployScript = Join-Path $PSScriptRoot 'deploy_xiyuslogin_auto_session.ps1'
$verifyScript = Join-Path $PSScriptRoot 'verify_xiyuslogin_auto_session.ps1'
$sourceRoot = (Get-Item -LiteralPath $SourceServerRoot -ErrorAction Stop).FullName
$canonicalTestRoot = [System.IO.Path]::GetFullPath($TestRoot)

if (Test-Path -LiteralPath $canonicalTestRoot) {
    $resolvedExisting = (Get-Item -LiteralPath $canonicalTestRoot).FullName
    $allowedPrefix = '<AUDIT_ROOT>\'
    if (-not $resolvedExisting.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear test directory outside $allowedPrefix"
    }
    Remove-Item -LiteralPath $resolvedExisting -Recurse -Force
}

New-Item -ItemType Directory -Path (Join-Path $canonicalTestRoot 'config') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $canonicalTestRoot 'mods') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot 'config\xiyuslogin-common.toml') `
    -Destination (Join-Path $canonicalTestRoot 'config\xiyuslogin-common.toml')
Copy-Item -LiteralPath (Join-Path $sourceRoot 'config\trueuuid-common.toml') `
    -Destination (Join-Path $canonicalTestRoot 'config\trueuuid-common.toml')
Get-ChildItem -LiteralPath (Join-Path $sourceRoot 'mods') -Filter 'xiyuslogin-*.jar' -File |
    Copy-Item -Destination (Join-Path $canonicalTestRoot 'mods')
Get-ChildItem -LiteralPath (Join-Path $sourceRoot 'mods') -Filter 'trueuuid-*.jar' -File |
    Copy-Item -Destination (Join-Path $canonicalTestRoot 'mods')

$targetConfig = Join-Path $canonicalTestRoot 'config\xiyuslogin-common.toml'
$originalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetConfig).Hash
$originalText = [System.IO.File]::ReadAllText($targetConfig)

$planOutput = & $deployScript -ServerRoot $canonicalTestRoot -DurationSeconds 86400
$plan = $planOutput | ConvertFrom-Json
if ($plan.status -ne 'change_required') {
    throw "Expected change_required plan, got $($plan.status)."
}

$applyOutput = & $deployScript -ServerRoot $canonicalTestRoot -DurationSeconds 86400 `
    -Apply -ConfirmServerStopped
$applyResult = $applyOutput | ConvertFrom-Json
if ($applyResult.status -ne 'applied') {
    throw "Expected applied result, got $($applyResult.status)."
}

& $verifyScript -ServerRoot $canonicalTestRoot -DurationSeconds 86400 | Out-Null

$idempotentOutput = & $deployScript -ServerRoot $canonicalTestRoot -DurationSeconds 86400 `
    -Apply -ConfirmServerStopped
$idempotentResult = $idempotentOutput | ConvertFrom-Json
if ($idempotentResult.status -ne 'no_change') {
    throw "Expected no_change result, got $($idempotentResult.status)."
}

$afterText = [System.IO.File]::ReadAllText($targetConfig)
$normalizedOriginal = [regex]::Replace($originalText, '(?m)^([ \t]*enableIpSession[ \t]*=[ \t]*)(true|false)', '${1}<VALUE>')
$normalizedOriginal = [regex]::Replace($normalizedOriginal, '(?m)^([ \t]*ipSessionDurationSeconds[ \t]*=[ \t]*)[0-9]+', '${1}<VALUE>')
$normalizedAfter = [regex]::Replace($afterText, '(?m)^([ \t]*enableIpSession[ \t]*=[ \t]*)(true|false)', '${1}<VALUE>')
$normalizedAfter = [regex]::Replace($normalizedAfter, '(?m)^([ \t]*ipSessionDurationSeconds[ \t]*=[ \t]*)[0-9]+', '${1}<VALUE>')
if ($normalizedOriginal -cne $normalizedAfter) {
    throw 'Apply changed content outside the two approved TOML values.'
}

& $deployScript -ServerRoot $canonicalTestRoot -RollbackReceipt $applyResult.receiptPath `
    -ConfirmServerStopped | Out-Null
$restoredHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetConfig).Hash
if ($restoredHash -ne $originalHash) {
    throw 'Rollback did not restore the original config byte-for-byte.'
}

$secondApplyOutput = & $deployScript -ServerRoot $canonicalTestRoot -DurationSeconds 86400 `
    -Apply -ConfirmServerStopped
$secondApply = $secondApplyOutput | ConvertFrom-Json
Add-Content -LiteralPath $targetConfig -Value '# intentional CAS tamper probe' -Encoding UTF8
$tamperRefused = $false
try {
    & $deployScript -ServerRoot $canonicalTestRoot -RollbackReceipt $secondApply.receiptPath `
        -ConfirmServerStopped | Out-Null
} catch {
    if ($_.Exception.Message -like 'CAS rollback refused:*') {
        $tamperRefused = $true
    } else {
        throw
    }
}
if (-not $tamperRefused) {
    throw 'CAS rollback did not refuse a tampered target.'
}

[pscustomobject]@{
    schema = 'xiyuslogin-auto-session-script-test/v1'
    status = 'PASS'
    tests = @(
        'plan detects disabled setting',
        'apply changes exactly two values',
        'verify accepts desired state and TrueUUID guards',
        'second apply is idempotent',
        'rollback restores byte-for-byte original',
        'rollback CAS refuses a changed target'
    )
    testRoot = $canonicalTestRoot
} | ConvertTo-Json -Depth 5
