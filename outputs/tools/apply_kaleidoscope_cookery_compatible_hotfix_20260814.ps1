param(
    [string]$Artifact = 'D:\Trans\migration-audit-work\kaleidoscope-cookery-chopping-board-fix-20260814\compatible-build2-kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar',
    [string]$ServerRoot = 'D:\Trans\migration-audit-work\mechanomania-matched-runtime-attempt13-20260814',
    [string]$ClientRoot = 'D:\Trans\migration-audit-work\mechanomania-matched-client-attempt13-20260814',
    [string]$PrismRoot = '',
    [string]$AuditRoot = 'D:\Trans\migration-audit-work\kaleidoscope-cookery-chopping-board-fix-20260814'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$CurrentName = 'kaleidoscopecookery-1.4.1.7-migration.4-neoforge+mc1.21.1.jar'
$CurrentSha = '9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17'
$CompatibleName = 'kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar'
$CompatibleSha = 'AC0D269F395A5D8CBCFEDC747898D1A16171AB0C0C0E94681605F682FEEDAEF0'
$BackupRoot = Join-Path $AuditRoot 'migration4-superseded-backup-20260814'
$ReportPath = Join-Path $AuditRoot 'kaleidoscope-cookery-compatible-hotfix-apply.json'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

if ([string]::IsNullOrWhiteSpace($PrismRoot)) {
    $instancesRoot = 'D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\instances'
    $prismCandidates = @(Get-ChildItem -LiteralPath $instancesRoot -Directory | Where-Object {
        $_.Name -like '*Mechanomania-Matched-Attempt13-NeoForge-1.21.1-20260814'
    } | ForEach-Object { Join-Path $_.FullName 'minecraft' })
    Assert-True ($prismCandidates.Count -eq 1) 'unable to resolve exactly one Attempt13 Prism minecraft root'
    $PrismRoot = $prismCandidates[0]
}

$targets = @(
    [pscustomobject]@{ Name = 'server'; Root = $ServerRoot; Mods = (Join-Path $ServerRoot 'mods') },
    [pscustomobject]@{ Name = 'client'; Root = $ClientRoot; Mods = (Join-Path $ClientRoot 'mods') },
    [pscustomobject]@{ Name = 'prism'; Root = $PrismRoot; Mods = (Join-Path $PrismRoot 'mods') }
)

Assert-True (Test-Path -LiteralPath $Artifact -PathType Leaf) "artifact missing: $Artifact"
Assert-True ((Get-Sha256 $Artifact) -eq $CompatibleSha) 'compatible artifact SHA mismatch'
Assert-True (-not (Test-Path -LiteralPath $BackupRoot)) "backup already exists: $BackupRoot"
Assert-True (-not (Test-Path -LiteralPath $ReportPath)) "report already exists: $ReportPath"

$activeJava = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('java.exe', 'javaw.exe') -and $_.CommandLine
})
foreach ($process in $activeJava) {
    foreach ($target in $targets) {
        if ($process.CommandLine.IndexOf($target.Root, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            throw "Java PID $($process.ProcessId) is still using $($target.Name) root"
        }
    }
}

foreach ($target in $targets) {
    $jars = @(Get-ChildItem -LiteralPath $target.Mods -File -Filter 'kaleidoscopecookery*.jar')
    Assert-True ($jars.Count -eq 1) "$($target.Name) must contain exactly one Cookery JAR"
    Assert-True ($jars[0].Name -eq $CurrentName) "$($target.Name) current filename mismatch"
    Assert-True ((Get-Sha256 $jars[0].FullName) -eq $CurrentSha) "$($target.Name) current SHA mismatch"
}

New-Item -ItemType Directory -Path $BackupRoot | Out-Null
$staged = @()
try {
    foreach ($target in $targets) {
        $currentPath = Join-Path $target.Mods $CurrentName
        $compatiblePath = Join-Path $target.Mods $CompatibleName
        $temporaryPath = $compatiblePath + '.incoming'
        $backupPath = Join-Path $BackupRoot ($target.Name + '-' + $CurrentName)

        Copy-Item -LiteralPath $currentPath -Destination $backupPath
        Assert-True ((Get-Sha256 $backupPath) -eq $CurrentSha) "$($target.Name) migration.4 backup failed"
        Copy-Item -LiteralPath $Artifact -Destination $temporaryPath
        Assert-True ((Get-Sha256 $temporaryPath) -eq $CompatibleSha) "$($target.Name) compatible staging failed"
        Move-Item -LiteralPath $temporaryPath -Destination $compatiblePath
        $staged += [pscustomobject]@{ Target = $target; Current = $currentPath; Compatible = $compatiblePath; Backup = $backupPath }
    }

    foreach ($row in $staged) {
        Remove-Item -LiteralPath $row.Current
    }

    $installed = @()
    foreach ($row in $staged) {
        $jars = @(Get-ChildItem -LiteralPath $row.Target.Mods -File -Filter 'kaleidoscopecookery*.jar')
        Assert-True ($jars.Count -eq 1) "$($row.Target.Name) post-install duplicate"
        Assert-True ($jars[0].Name -eq $CompatibleName) "$($row.Target.Name) post-install filename mismatch"
        Assert-True ((Get-Sha256 $jars[0].FullName) -eq $CompatibleSha) "$($row.Target.Name) post-install SHA mismatch"
        $installed += [pscustomobject]@{ name = $row.Target.Name; path = $jars[0].FullName; bytes = $jars[0].Length; sha256 = $CompatibleSha; backup = $row.Backup }
    }

    $report = [ordered]@{
        schema = 1
        status = 'PASS_COMMITTED'
        reason = 'preserve exact migration.3 metadata required by kaleidoscope_end and kaleidoscope_nether_equivalence'
        superseded_filename = $CurrentName
        superseded_sha256 = $CurrentSha
        installed_filename = $CompatibleName
        installed_sha256 = $CompatibleSha
        artifact = (Resolve-Path -LiteralPath $Artifact).Path
        installed = $installed
        backup_root = $BackupRoot
    }
    [IO.File]::WriteAllText($ReportPath, (($report | ConvertTo-Json -Depth 8) + "`n"), [Text.UTF8Encoding]::new($false))
    [pscustomobject]@{ Status = 'PASS_COMMITTED'; Report = $ReportPath; ReportSha256 = (Get-Sha256 $ReportPath); InstalledSha256 = $CompatibleSha } | ConvertTo-Json
}
catch {
    foreach ($row in $staged) {
        if (Test-Path -LiteralPath $row.Compatible) { Remove-Item -LiteralPath $row.Compatible -Force }
        if (-not (Test-Path -LiteralPath $row.Current) -and (Test-Path -LiteralPath $row.Backup)) {
            Copy-Item -LiteralPath $row.Backup -Destination $row.Current
        }
        $temporaryPath = $row.Compatible + '.incoming'
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
    throw
}
