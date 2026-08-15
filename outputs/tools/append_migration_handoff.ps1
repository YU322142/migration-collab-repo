param(
    [string]$Destination = 'D:\Trans\migration-handoff-20260812.building'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$statusPath = "$Destination.status.json"
$logPath = "$Destination.append.log"

function Write-Status([string]$phase, [string]$status, [string]$detail = '') {
    $value = [ordered]@{
        schema = 2
        status = $status
        phase = $phase
        detail = $detail
        destination = $Destination
        pid = $PID
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    $temporary = "$statusPath.tmp"
    $value | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding utf8
    Move-Item -LiteralPath $temporary -Destination $statusPath -Force
}

function Copy-Tree([string]$Source, [string]$Target, [string[]]$Extra = @()) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Missing source tree: $Source" }
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
    $args = @($Source, $Target, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:2', '/J', '/MT:12', '/NP', '/TEE', "/LOG+:$logPath") + $Extra
    & robocopy.exe @args
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed (${LASTEXITCODE}): $Source -> $Target" }
}

function Copy-FileSafe([string]$Source, [string]$Target) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Missing source file: $Source" }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Target -Force
}

function Resolve-ResourcePack([string]$Root, [int64]$ExpectedBytes, [string]$ExpectedSha256) {
    $matches = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.zip' -ErrorAction Stop |
        Where-Object { $_.Length -eq $ExpectedBytes }
    foreach ($candidate in $matches) {
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $candidate.FullName).Hash -eq $ExpectedSha256) {
            return $candidate.FullName
        }
    }
    throw "Could not locate resource pack by locked size/hash under $Root"
}

function Resolve-FileByName([string]$Root, [string]$Name) {
    $candidate = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $candidate) { throw "Could not locate evidence file $Name under $Root" }
    return $candidate.FullName
}

try {
    if (-not (Test-Path -LiteralPath $Destination -PathType Container)) { throw "Handoff base directory missing: $Destination" }
    Write-Status 'copy-tools' 'RUNNING'
    Copy-Tree (Join-Path $workspace 'outputs\tools') (Join-Path $Destination '03-tools-and-source\tools') @('/XD', '__pycache__')

    Write-Status 'copy-workspace-projects' 'RUNNING'
    Copy-Tree (Join-Path $workspace 'outputs\projects') (Join-Path $Destination '03-tools-and-source\projects') @('/XD', 'build', '.gradle', '.git', 'out', 'bin', 'classes', 'reports', 'tmp')

    Write-Status 'copy-d-source-projects' 'RUNNING'
    $dSourceNames = @(
        'HappyGhast-1.21.1-equivalence',
        'KaleidoscopeEnd-1.21.1-equivalence',
        'KaleidoscopeNether-1.21.1-equivalence',
        'KaleidoscopeCookery-source',
        'KaleidoscopeTavern-source',
        'MishangUC-1.21.1-equivalence',
        'Potted-Farms-1.21.1-equivalence',
        'respawn-pitch-compat',
        'XiyusLogin-migration',
        'FroglightPatch-1.21.1-equivalence',
        'Resource-Error-Overlay-1.21.1',
        'CreateNerfad-1.21.1-neoforge',
        'create-dynamic-blocking-neoforge',
        'KaleidoscopeCookery-1.21.1-neoforge'
    )
    foreach ($name in $dSourceNames) {
        Copy-Tree (Join-Path 'D:\Trans\migration-audit-work' $name) (Join-Path $Destination "03-tools-and-source\d-projects\$name") @('/XD', 'build', '.gradle', '.git', 'out', 'bin', 'classes', 'reports', 'tmp')
    }

    Write-Status 'copy-reports' 'RUNNING'
    $reportTarget = Join-Path $Destination '04-reports-and-docs\outputs-root'
    New-Item -ItemType Directory -Path $reportTarget -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $workspace 'outputs') -File -Force |
        Where-Object { $_.Extension -in @('.json','.md','.txt','.sha256','.properties','.dat') } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $reportTarget $_.Name) -Force }
    $explicit = @(
        'D:\Trans\migration-audit-work\handoff-immersive-paintings-manifest-20260812.json',
        'D:\Trans\migration-audit-work\tmp-handoff-create-tracks-audit-20260812.json',
        'D:\Trans\migration-audit-work\tmp-handoff-create-tracks-fixed-20260812.dat',
        'D:\Trans\migration-audit-work\handoff-create-carriage-orientation-guard-20260812\build1-create-carriage-orientation-guard.jar',
        'D:\Trans\migration-audit-work\carriage-guard-build-20260812.log'
    )
    foreach ($file in $explicit) { if (Test-Path -LiteralPath $file -PathType Leaf) { Copy-FileSafe $file (Join-Path $Destination "04-reports-and-docs\evidence\$(Split-Path $file -Leaf)") } }

    Write-Status 'copy-special-inputs' 'RUNNING'
    $originalPack = Resolve-ResourcePack 'D:\D\Tools' 110867309 'BF88450FF0EED414657DC75CC1F0FD6689109A654DEEC8CF5306A13C3900CCCC'
    Copy-FileSafe $originalPack (Join-Path $Destination '01-original\resource-pack-original.zip')
    $adaptedPack = Get-ChildItem -LiteralPath (Join-Path $workspace 'outputs\candidate13-resource-closure-20260812') -File -Filter '*.zip' |
        Where-Object { $_.Length -eq 110377999 } | Select-Object -First 1
    if ($null -eq $adaptedPack -or (Get-FileHash -Algorithm SHA256 -LiteralPath $adaptedPack.FullName).Hash -ne '614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364') { throw 'Adapted resource pack size/hash mismatch' }
    Copy-FileSafe $adaptedPack.FullName (Join-Path $Destination '02-latest\resource-pack-mc1.21.1-candidate13.zip')
    $crash = Resolve-FileByName 'D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3' 'crash-2026-08-12_23.38.16-client.txt'
    Copy-FileSafe $crash (Join-Path $Destination '04-reports-and-docs\evidence\candidate14-manual-client-crash.txt')

    Write-Status 'copy-handoff-docs' 'RUNNING'
    $handoffDocs = Join-Path $workspace 'outputs\handoff-20260812'
    Copy-Tree $handoffDocs (Join-Path $Destination '04-reports-and-docs\handoff-docs') @('/XD', '__pycache__')
    $readme = Get-ChildItem -LiteralPath $handoffDocs -File | Where-Object { $_.Name -like 'README-*' } | Select-Object -First 1
    if ($null -eq $readme) { throw 'README handoff document is missing' }
    Copy-Item -LiteralPath $readme.FullName -Destination (Join-Path $Destination 'README-handoff.md') -Force
    foreach ($asciiDoc in @('TODO.md','AUTHORITATIVE-INPUTS.json','P0-STATUS.md','HISTORY-POLICY.md')) {
        Copy-FileSafe (Join-Path $handoffDocs $asciiDoc) (Join-Path $Destination $asciiDoc)
    }

    Write-Status 'APPEND_COMPLETE' 'PASS' 'Tools, source, reports, resource packs, crash evidence and handoff docs appended.'
}
catch {
    Write-Status 'FAILED' 'NO_GO' $_.Exception.Message
    throw
}
