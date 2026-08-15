param(
    [string]$Source = 'D:\Down\20260811.zip',
    [string]$Destination = 'D:\Trans\migration-handoff-20260812.building\01-original\20260811.zip',
    [string]$StatusPath = 'D:\Trans\migration-handoff-20260812.restore-original.status.json'
)

$ErrorActionPreference = 'Stop'
$expectedBytes = 7838147411
$expectedSha256 = '9723FE28BC1B98D6ECE96A4063532BB2A533A038E7B3E457D50CF658E2495021'

function Write-Status([string]$status, [string]$phase, [string]$detail = '') {
    $value = [ordered]@{
        schema = 1
        status = $status
        phase = $phase
        detail = $detail
        source = $Source
        destination = $Destination
        pid = $PID
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $temporary = "$StatusPath.tmp"
    $value | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $StatusPath -Force
}

try {
    $sourceItem = Get-Item -LiteralPath $Source
    if ($sourceItem.Length -ne $expectedBytes) { throw "source byte count mismatch: $($sourceItem.Length)" }
    if (Test-Path -LiteralPath $Destination) { throw "refusing to overwrite destination: $Destination" }
    Write-Status 'RUNNING' 'COPY'
    Copy-Item -LiteralPath $Source -Destination $Destination
    $destinationItem = Get-Item -LiteralPath $Destination
    if ($destinationItem.Length -ne $expectedBytes) { throw "destination byte count mismatch: $($destinationItem.Length)" }
    Write-Status 'RUNNING' 'HASH'
    $actualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash
    if ($actualSha256 -ne $expectedSha256) { throw "destination SHA-256 mismatch: $actualSha256" }
    Write-Status 'PASS' 'COMPLETE' $actualSha256
}
catch {
    Write-Status 'NO_GO' 'FAILED' $_.Exception.Message
    throw
}
