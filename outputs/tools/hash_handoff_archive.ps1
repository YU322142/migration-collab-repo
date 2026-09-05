param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,

    [Parameter(Mandatory = $true)]
    [string]$PackagePath,

    [Parameter(Mandatory = $true)]
    [string]$ReportPath,

    [Parameter(Mandatory = $true)]
    [string]$Sha256Path
)

$ErrorActionPreference = 'Stop'

function Write-AtomicUtf8Json {
    param([string]$Path, [object]$Value)
    $temporary = "$Path.tmp"
    $json = $Value | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($temporary, $json + "`n", [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

$archive = Get-Item -LiteralPath $ArchivePath
$package = Get-Item -LiteralPath $PackagePath
if (-not $package.PSIsContainer) {
    throw "Package path is not a directory: $PackagePath"
}
if ($archive.DirectoryName -ne '<TRANS_ROOT>' -or $package.Parent.FullName -ne '<TRANS_ROOT>') {
    throw 'Archive and package must both be direct children of <TRANS_ROOT>'
}

$manifestPath = Join-Path $package.FullName 'MANIFEST-SHA256.json'
$packageStatusPath = Join-Path $package.FullName 'PACKAGE-STATUS.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$packageStatus = Get-Content -LiteralPath $packageStatusPath -Raw -Encoding UTF8 | ConvertFrom-Json

$archiveBefore = Get-Item -LiteralPath $archive.FullName
$hash = (Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash.ToUpperInvariant()
$archiveAfter = Get-Item -LiteralPath $archive.FullName
if ($archiveBefore.Length -ne $archiveAfter.Length -or $archiveBefore.LastWriteTimeUtc -ne $archiveAfter.LastWriteTimeUtc) {
    throw "Archive changed while hashing: $ArchivePath"
}

$physical = Get-ChildItem -LiteralPath $package.FullName -Recurse -File -Force | Measure-Object -Property Length -Sum
$testLog = '<HANDOFF_ROOT>.test.log'
$testText = Get-Content -LiteralPath $testLog -Raw -Encoding UTF8
if ($testText -notmatch 'Everything is Ok') {
    throw '7z test log does not contain Everything is Ok'
}
if ($testText -notmatch 'Files:\s+20325') {
    throw '7z test log does not contain the expected physical file count'
}

$report = [ordered]@{
    schema = 1
    status = 'PASS'
    generated_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    archive = [ordered]@{
        path = $archive.FullName
        bytes = $archiveAfter.Length
        sha256 = $hash
        seven_zip_test = 'PASS'
        test_log = $testLog
        test_log_bytes = (Get-Item -LiteralPath $testLog).Length
    }
    package = [ordered]@{
        path = $package.FullName
        physical_file_count = [int]$physical.Count
        physical_bytes = [int64]$physical.Sum
        manifest_file_count = [int]$manifest.file_count
        manifest_bytes = [int64]$manifest.bytes
        manifest_aggregate_sha256 = [string]$manifest.aggregate_sha256
        package_status = [string]$packageStatus.status
    }
    release_status = 'HANDOFF_ONLY_NOT_PRODUCTION_GO'
}

Write-AtomicUtf8Json -Path $ReportPath -Value $report
[System.IO.File]::WriteAllText(
    $Sha256Path,
    "$hash  $($archive.Name)`n",
    [System.Text.UTF8Encoding]::new($false)
)

$report | ConvertTo-Json -Depth 10
