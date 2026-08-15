[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ServerRoot,

    [ValidateRange(1, 86400)]
    [int]$DurationSeconds = 86400,

    [switch]$CheckLatestLog
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$deployScript = Join-Path $PSScriptRoot 'deploy_xiyuslogin_auto_session.ps1'
if (-not (Test-Path -LiteralPath $deployScript -PathType Leaf)) {
    throw "Missing verifier dependency: $deployScript"
}

& $deployScript -ServerRoot $ServerRoot -DurationSeconds $DurationSeconds -RequireDesiredState

if ($CheckLatestLog) {
    $canonicalServerRoot = (Get-Item -LiteralPath $ServerRoot -ErrorAction Stop).FullName
    $latestLog = Join-Path $canonicalServerRoot 'logs\latest.log'
    if (-not (Test-Path -LiteralPath $latestLog -PathType Leaf)) {
        throw "Missing latest log: $latestLog"
    }

    $premiumEvidence = Select-String -LiteralPath $latestLog -Encoding UTF8 `
        -Pattern 'TrueUUID login_complete outcome=premium ' -Quiet
    $sessionEvidence = Select-String -LiteralPath $latestLog -Encoding UTF8 `
        -Pattern 'Restored IP session for player ' -Quiet

    $logResult = [pscustomobject]@{
        schema = 'xiyuslogin-auto-session-log-check/v1'
        premiumVerificationObserved = [bool]$premiumEvidence
        ipSessionRestoreObserved = [bool]$sessionEvidence
        note = if ($sessionEvidence) {
            'Runtime IP-session restore evidence is present.'
        } else {
            'No restore evidence yet. After restart, log in once manually, disconnect, and reconnect within the configured duration.'
        }
    }
    Write-Output ($logResult | ConvertTo-Json -Depth 4)
}
