param(
    [string]$Destination = '<HANDOFF_ROOT>.building'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$originalZip = '<DOWNLOAD_ROOT>\20260811.zip'
$staging = '<AUDIT_ROOT>\cutover-staging-incoming-20260811-candidate13-20260812'
$release = '<AUDIT_ROOT>\final-mod-bundles-candidate14-r3-20260812'
$paintingCache = '<AUDIT_ROOT>\incoming-20260811-raw\20260811\immersive_paintings_cache'
$fixedTracks = '<AUDIT_ROOT>\tmp-handoff-create-tracks-fixed-20260812.dat'
$tracksReport = '<AUDIT_ROOT>\tmp-handoff-create-tracks-audit-20260812.json'

foreach ($required in @($originalZip, $staging, $release, $paintingCache, $fixedTracks, $tracksReport)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required handoff input is missing: $required"
    }
}

$destinationItem = Get-Item -LiteralPath (Split-Path -Parent $Destination)
if ($destinationItem.FullName -notlike '<TRANS_ROOT>*') {
    throw "Handoff destination must remain under <TRANS_ROOT>: $Destination"
}
if (Test-Path -LiteralPath $Destination) {
    throw "Refusing to overwrite an existing handoff build: $Destination"
}

$statusPath = "$Destination.status.json"
$logPath = "$Destination.copy.log"

function Write-Status([string]$phase, [string]$status, [string]$detail = '') {
    $value = [ordered]@{
        schema = 1
        status = $status
        phase = $phase
        detail = $detail
        destination = $Destination
        pid = $PID
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $temporary = "$statusPath.tmp"
    $value | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $statusPath -Force
}

function Invoke-Robocopy([string]$source, [string]$target, [string[]]$extra = @()) {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $arguments = @(
        $source,
        $target,
        '/E',
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/R:2',
        '/W:2',
        '/J',
        '/MT:12',
        '/NP',
        '/TEE',
        "/LOG+:$logPath"
    ) + $extra
    & robocopy.exe @arguments
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        throw "robocopy failed with exit code ${code}: $source -> $target"
    }
}

try {
    Write-Status 'initialize' 'RUNNING'
    New-Item -ItemType Directory -Path $Destination | Out-Null
    foreach ($relative in @(
        '01-original',
        '02-latest',
        '03-tools-and-source',
        '04-reports-and-docs',
        '05-superseded-index'
    )) {
        New-Item -ItemType Directory -Path (Join-Path $Destination $relative) | Out-Null
    }

    Write-Status 'copy-original-zip' 'RUNNING'
    Copy-Item -LiteralPath $originalZip -Destination (Join-Path $Destination '01-original\20260811.zip')

    Write-Status 'copy-converted-staging' 'RUNNING'
    Invoke-Robocopy $staging (Join-Path $Destination '02-latest\converted-staging')

    Write-Status 'apply-create-tracks-fix' 'RUNNING'
    Copy-Item -LiteralPath $fixedTracks -Destination (Join-Path $Destination '02-latest\converted-staging\world\data\create_tracks.dat') -Force
    Copy-Item -LiteralPath $tracksReport -Destination (Join-Path $Destination '02-latest\converted-staging\migration-reports\handoff-create-tracks-initial-orientation-fix.json')

    Write-Status 'restore-immersive-paintings-cache' 'RUNNING'
    Invoke-Robocopy $paintingCache (Join-Path $Destination '02-latest\converted-staging\immersive_paintings_cache')

    Write-Status 'copy-release-bundle' 'RUNNING'
    Invoke-Robocopy $release (Join-Path $Destination '02-latest\release-bundle-candidate14-r3')

    Write-Status 'BASE_COPY_COMPLETE' 'PASS' 'Stable large inputs copied; small sources/reports and final manifests are appended by the foreground packager.'
}
catch {
    Write-Status 'FAILED' 'NO_GO' $_.Exception.Message
    throw
}
