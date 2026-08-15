param(
    [string] $ClientRoot = '',
    [string] $BasePrepareReport = '',
    [string] $GuardJar = '',
    [string] $Manifest = '',
    [string] $Report = ''
)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$expectedClientRoot = Join-Path $workspace 'outputs\tmp\client-gate-candidate10\.minecraft'
$expectedBaseReport = Join-Path $workspace 'outputs\candidate10-client-root-prepare-20260811.json'
$expectedGuardJar = Join-Path $workspace 'outputs\artifacts\create-chute-unload-guard-20260811\create-chute-unload-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar'
$expectedManifest = Join-Path $workspace 'outputs\candidate11-chute-stress-client-manifest-20260811.json'
$expectedReport = Join-Path $workspace 'outputs\candidate11-chute-stress-client-prepare-20260811.json'
$expectedGuardSha256 = 'AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A'

if ([string]::IsNullOrWhiteSpace($ClientRoot)) { $ClientRoot = $expectedClientRoot }
if ([string]::IsNullOrWhiteSpace($BasePrepareReport)) { $BasePrepareReport = $expectedBaseReport }
if ([string]::IsNullOrWhiteSpace($GuardJar)) { $GuardJar = $expectedGuardJar }
if ([string]::IsNullOrWhiteSpace($Manifest)) { $Manifest = $expectedManifest }
if ([string]::IsNullOrWhiteSpace($Report)) { $Report = $expectedReport }

function Full-Path([string] $Path) {
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Require-ExactPath([string] $Actual, [string] $Expected, [string] $Label) {
    if (-not [string]::Equals((Full-Path $Actual), (Full-Path $Expected), [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label is not the locked stress-fixture path: $Actual"
    }
}

function File-Sha256([string] $Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

function Bundle-Digest([object[]] $Rows) {
    $stream = [IO.MemoryStream]::new()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        foreach ($row in $Rows) {
            $record = [Text.Encoding]::UTF8.GetBytes(
                [string]$row.file + [char]0 + ([string]$row.sha256).ToUpperInvariant() + "`n"
            )
            $stream.Write($record, 0, $record.Length)
        }
        $stream.Position = 0
        return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '')
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

Require-ExactPath $ClientRoot $expectedClientRoot 'ClientRoot'
Require-ExactPath $BasePrepareReport $expectedBaseReport 'BasePrepareReport'
Require-ExactPath $GuardJar $expectedGuardJar 'GuardJar'
Require-ExactPath $Manifest $expectedManifest 'Manifest'
Require-ExactPath $Report $expectedReport 'Report'

foreach ($path in @($BasePrepareReport, $GuardJar)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}
if (-not (Test-Path -LiteralPath $ClientRoot -PathType Container)) {
    throw "Client root missing: $ClientRoot"
}
if (Test-Path -LiteralPath $Manifest) { throw "Refusing to overwrite manifest: $Manifest" }
if (Test-Path -LiteralPath $Report) { throw "Refusing to overwrite report: $Report" }
if ((File-Sha256 $GuardJar) -ne $expectedGuardSha256) {
    throw 'Guard JAR SHA-256 mismatch'
}

$base = Get-Content -LiteralPath $BasePrepareReport -Raw | ConvertFrom-Json
if ([string]$base.status -ne 'PREPARED' -or
    -not [bool]$base.saves_logs_caches_absent -or
    @($base.forbidden_runtime_state_found).Count -ne 0 -or
    [bool]$base.java_started) {
    throw 'Base client preparation report is not a pristine PREPARED fixture'
}

$mods = Join-Path $ClientRoot 'mods'
$destinationGuard = Join-Path $mods ([IO.Path]::GetFileName($GuardJar))
Copy-Item -LiteralPath $GuardJar -Destination $destinationGuard
if ((File-Sha256 $destinationGuard) -ne $expectedGuardSha256) {
    throw 'Copied guard JAR SHA-256 mismatch'
}

$filesByName = @{}
foreach ($file in @(Get-ChildItem -LiteralPath $mods -File)) {
    $filesByName[$file.Name] = $file
}
$nameByLower = @{}
foreach ($name in $filesByName.Keys) {
    $nameByLower[$name.ToLowerInvariant()] = $name
}
[string[]]$sortedLowerNames = @($nameByLower.Keys)
[Array]::Sort($sortedLowerNames, [StringComparer]::Ordinal)
$files = @($sortedLowerNames | ForEach-Object { $filesByName[$nameByLower[$_]] })
$directories = @(Get-ChildItem -LiteralPath $mods -Directory)
if ($directories.Count -ne 0 -or $files.Count -ne 51 -or @($files | Where-Object Extension -ine '.jar').Count -ne 0) {
    throw 'Stress client mods must be a flat exact 51-JAR set'
}
$rows = @(
    foreach ($file in $files) {
        [pscustomobject][ordered]@{
            file = $file.Name
            bytes = [long]$file.Length
            sha256 = File-Sha256 $file.FullName
        }
    }
)
[long]$totalBytes = ($rows | Measure-Object -Property bytes -Sum).Sum
$bundleSha256 = Bundle-Digest $rows

$manifestValue = [ordered]@{
    schema = 1
    status = 'PASS'
    purpose = 'Candidate11 Create chute unload guard private stress fixture'
    side = 'client'
    bundle_dir = Full-Path $mods
    file_count = $rows.Count
    bytes = $totalBytes
    bundle_sha256 = $bundleSha256
    overlay = [ordered]@{
        file = [IO.Path]::GetFileName($destinationGuard)
        bytes = (Get-Item -LiteralPath $destinationGuard).Length
        sha256 = $expectedGuardSha256
    }
    files = $rows
}
[IO.File]::WriteAllText(
    $Manifest,
    ($manifestValue | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)
$manifestSha256 = File-Sha256 $Manifest

$base.purpose = 'Candidate11 Create chute unload guard private stress fixture'
$base.client_bundle.source = 'Candidate10 frozen client bundle plus pinned chute guard overlay'
$base.client_bundle.manifest = Full-Path $Manifest
$base.client_bundle.manifest_sha256 = $manifestSha256
$base.client_bundle.file_count = $rows.Count
$base.client_bundle.bytes = $totalBytes
$base.client_bundle.bundle_sha256 = $bundleSha256
$base.client_bundle.expected_bundle_sha256 = $bundleSha256
$base.client_bundle.exact_manifest_match = $true
$base.client_bundle.stale_files = @()
$base.client_bundle | Add-Member -NotePropertyName compatibility_overlay -NotePropertyValue ([pscustomobject]@{
    file = [IO.Path]::GetFileName($destinationGuard)
    bytes = (Get-Item -LiteralPath $destinationGuard).Length
    sha256 = $expectedGuardSha256
}) -Force
[IO.File]::WriteAllText(
    $Report,
    ($base | ConvertTo-Json -Depth 12) + [Environment]::NewLine,
    [Text.UTF8Encoding]::new($false)
)

[ordered]@{
    status = 'PREPARED'
    client_root = Full-Path $ClientRoot
    files = $rows.Count
    bytes = $totalBytes
    bundle_sha256 = $bundleSha256
    manifest = Full-Path $Manifest
    manifest_sha256 = $manifestSha256
    report = Full-Path $Report
    report_sha256 = File-Sha256 $Report
    guard_sha256 = $expectedGuardSha256
} | ConvertTo-Json
