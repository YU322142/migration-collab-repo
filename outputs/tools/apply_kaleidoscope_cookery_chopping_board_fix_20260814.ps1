param(
    [string]$Artifact = '<AUDIT_ROOT>\kaleidoscope-cookery-chopping-board-fix-20260814\final-build2-kaleidoscopecookery-1.4.1.7-migration.4-neoforge+mc1.21.1.jar',
    [string]$ServerRoot = '<AUDIT_ROOT>\mechanomania-matched-runtime-attempt13-20260814',
    [string]$ClientRoot = '<AUDIT_ROOT>\mechanomania-matched-client-attempt13-20260814',
    [string]$PrismRoot = '',
    [string]$AuditRoot = '<AUDIT_ROOT>\kaleidoscope-cookery-chopping-board-fix-20260814'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$OldName = 'kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar'
$NewName = 'kaleidoscopecookery-1.4.1.7-migration.4-neoforge+mc1.21.1.jar'
$OldSha = 'A061FB1E953AD815144304F7567B30876DBBC07B8565069871771F0AAEB63D3F'
$NewSha = '9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17'
$BackupRoot = Join-Path $AuditRoot 'installed-backup-20260814'
$ReportPath = Join-Path $AuditRoot 'kaleidoscope-cookery-chopping-board-fix-apply.json'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

if ([string]::IsNullOrWhiteSpace($PrismRoot)) {
    $instancesRoot = '<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\instances'
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
Assert-True ((Get-Sha256 $Artifact) -eq $NewSha) 'artifact SHA-256 mismatch'
Assert-True (-not (Test-Path -LiteralPath $ReportPath)) "apply report already exists: $ReportPath"
Assert-True (-not (Test-Path -LiteralPath $BackupRoot)) "backup root already exists: $BackupRoot"

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

$preflight = @()
foreach ($target in $targets) {
    Assert-True (Test-Path -LiteralPath $target.Mods -PathType Container) "mods directory missing: $($target.Mods)"
    $modsItem = Get-Item -LiteralPath $target.Mods
    Assert-True (-not (($modsItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) "mods directory is a reparse point: $($target.Mods)"
    $cookery = @(Get-ChildItem -LiteralPath $target.Mods -File -Filter 'kaleidoscopecookery*.jar')
    Assert-True ($cookery.Count -eq 1) "$($target.Name) must contain exactly one Cookery JAR"
    Assert-True ($cookery[0].Name -eq $OldName) "$($target.Name) Cookery filename drift"
    Assert-True ((Get-Sha256 $cookery[0].FullName) -eq $OldSha) "$($target.Name) Cookery SHA drift"
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $target.Mods $NewName))) "$($target.Name) already has new Cookery JAR"
    $mcModSyncHits = @(Get-ChildItem -LiteralPath $target.Root -Recurse -Force -ErrorAction Stop | Where-Object {
        $_.Name -match '(?i)mcmodsync|modsync\.properties'
    })
    Assert-True ($mcModSyncHits.Count -eq 0) "$($target.Name) contains active MCModSync material"
    $preflight += [pscustomobject]@{
        name = $target.Name
        root = $target.Root
        old_path = $cookery[0].FullName
        old_bytes = $cookery[0].Length
        old_sha256 = $OldSha
    }
}

New-Item -ItemType Directory -Path $BackupRoot | Out-Null
$staged = @()
$removed = @()
try {
    foreach ($target in $targets) {
        $oldPath = Join-Path $target.Mods $OldName
        $backupPath = Join-Path $BackupRoot ($target.Name + '-' + $OldName)
        Copy-Item -LiteralPath $oldPath -Destination $backupPath
        Assert-True ((Get-Sha256 $backupPath) -eq $OldSha) "$($target.Name) backup verification failed"

        $temporaryPath = Join-Path $target.Mods ($NewName + '.incoming')
        $newPath = Join-Path $target.Mods $NewName
        Copy-Item -LiteralPath $Artifact -Destination $temporaryPath
        Assert-True ((Get-Sha256 $temporaryPath) -eq $NewSha) "$($target.Name) staged new JAR verification failed"
        Move-Item -LiteralPath $temporaryPath -Destination $newPath
        $staged += [pscustomobject]@{ target = $target; old = $oldPath; new = $newPath; backup = $backupPath }
    }

    foreach ($row in $staged) {
        Remove-Item -LiteralPath $row.old
        $removed += $row
    }

    $installed = @()
    foreach ($row in $staged) {
        $cookery = @(Get-ChildItem -LiteralPath $row.target.Mods -File -Filter 'kaleidoscopecookery*.jar')
        Assert-True ($cookery.Count -eq 1) "$($row.target.Name) post-install duplicate Cookery JAR"
        Assert-True ($cookery[0].Name -eq $NewName) "$($row.target.Name) post-install filename mismatch"
        Assert-True ((Get-Sha256 $cookery[0].FullName) -eq $NewSha) "$($row.target.Name) post-install SHA mismatch"
        $installed += [pscustomobject]@{
            name = $row.target.Name
            path = $cookery[0].FullName
            bytes = $cookery[0].Length
            sha256 = $NewSha
            backup = $row.backup
        }
    }

    $report = [ordered]@{
        schema = 1
        status = 'PASS_COMMITTED'
        old_filename = $OldName
        old_sha256 = $OldSha
        new_filename = $NewName
        new_sha256 = $NewSha
        artifact = (Resolve-Path -LiteralPath $Artifact).Path
        backup_root = $BackupRoot
        preflight = $preflight
        installed = $installed
        mcmodsync_active_hits = 0
    }
    [IO.File]::WriteAllText($ReportPath, (($report | ConvertTo-Json -Depth 8) + "`n"), [Text.UTF8Encoding]::new($false))
    [pscustomobject]@{ Status = 'PASS_COMMITTED'; Report = $ReportPath; ReportSha256 = (Get-Sha256 $ReportPath); NewSha256 = $NewSha } | ConvertTo-Json
}
catch {
    foreach ($row in $staged) {
        if (Test-Path -LiteralPath $row.new) { Remove-Item -LiteralPath $row.new -Force }
        if (-not (Test-Path -LiteralPath $row.old) -and (Test-Path -LiteralPath $row.backup)) {
            Copy-Item -LiteralPath $row.backup -Destination $row.old
        }
        $temporaryPath = $row.new + '.incoming'
        if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath -Force }
    }
    throw
}
