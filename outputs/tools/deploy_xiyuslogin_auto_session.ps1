[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ServerRoot,

    [ValidateRange(1, 86400)]
    [int]$DurationSeconds = 86400,

    [switch]$Apply,
    [switch]$RequireDesiredState,
    [switch]$ConfirmServerStopped,

    [string]$RollbackReceipt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptVersion = '1.0.1'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Get-CanonicalPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$MustExist
    )

    if ($MustExist) {
        return (Get-Item -LiteralPath $Path -ErrorAction Stop).FullName
    }
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-PathUnderRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )

    $canonicalPath = Get-CanonicalPath -Path $Path
    $canonicalRoot = (Get-CanonicalPath -Path $Root).TrimEnd('\', '/')
    $rootPrefix = $canonicalRoot + [System.IO.Path]::DirectorySeparatorChar
    if (-not $canonicalPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing path outside server root: $canonicalPath"
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToUpperInvariant()
}

function Get-SingleTomlSetting {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][ValidateSet('Boolean', 'Integer')][string]$Type
    )

    $escapedName = [regex]::Escape($Name)
    $valuePattern = if ($Type -eq 'Boolean') { 'true|false' } else { '[0-9]+' }
    $pattern = "(?m)^(?<prefix>[ `t]*$escapedName[ `t]*=[ `t]*)(?<value>$valuePattern)(?<suffix>[ `t]*(?:#.*)?)(?<eol>`r?)$"
    $matches = [regex]::Matches($Content, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one '$Name' setting, found $($matches.Count)."
    }

    return [pscustomobject]@{
        Name = $Name
        Type = $Type
        Pattern = $pattern
        Match = $matches[0]
        Value = $matches[0].Groups['value'].Value
    }
}

function Set-SingleTomlSetting {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][psobject]$Setting,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $replacement = '${prefix}' + $Value + '${suffix}${eol}'
    return [regex]::Replace(
        $Content,
        $Setting.Pattern,
        $replacement,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
}

function Get-RunningServerJavaProcess {
    param([Parameter(Mandatory = $true)][string]$CanonicalServerRoot)

    try {
        $javaProcesses = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.Name -in @('java.exe', 'javaw.exe') }
        foreach ($process in $javaProcesses) {
            if ($process.CommandLine -and
                $process.CommandLine.IndexOf($CanonicalServerRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                return $process
            }
        }
    } catch {
        Write-Warning 'Could not inspect Java command lines. -ConfirmServerStopped remains mandatory for writes.'
    }
    return $null
}

function Test-JarContainsEntry {
    param(
        [Parameter(Mandatory = $true)][string]$JarPath,
        [Parameter(Mandatory = $true)][string]$EntryName
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($JarPath)
    try {
        return $null -ne $archive.GetEntry($EntryName)
    } finally {
        $archive.Dispose()
    }
}

function Get-AuthReadiness {
    param(
        [Parameter(Mandatory = $true)][string]$CanonicalServerRoot,
        [Parameter(Mandatory = $true)][int]$ExpectedDuration
    )

    $xiyusConfigPath = Join-Path $CanonicalServerRoot 'config\xiyuslogin-common.toml'
    $trueUuidConfigPath = Join-Path $CanonicalServerRoot 'config\trueuuid-common.toml'
    Assert-PathUnderRoot -Path $xiyusConfigPath -Root $CanonicalServerRoot
    Assert-PathUnderRoot -Path $trueUuidConfigPath -Root $CanonicalServerRoot
    if (-not (Test-Path -LiteralPath $xiyusConfigPath -PathType Leaf)) {
        throw "Missing XiyusLogin config: $xiyusConfigPath"
    }
    if (-not (Test-Path -LiteralPath $trueUuidConfigPath -PathType Leaf)) {
        throw "Missing TrueUUID config: $trueUuidConfigPath"
    }

    $modsPath = Join-Path $CanonicalServerRoot 'mods'
    $xiyusJars = @(Get-ChildItem -LiteralPath $modsPath -Filter 'xiyuslogin-*.jar' -File -ErrorAction Stop)
    $trueUuidJars = @(Get-ChildItem -LiteralPath $modsPath -Filter 'trueuuid-*.jar' -File -ErrorAction Stop)
    if ($xiyusJars.Count -ne 1) {
        throw "Expected exactly one XiyusLogin JAR, found $($xiyusJars.Count)."
    }
    if ($trueUuidJars.Count -ne 1) {
        throw "Expected exactly one TrueUUID JAR, found $($trueUuidJars.Count)."
    }
    $trueUuidApiPresent = Test-JarContainsEntry -JarPath $trueUuidJars[0].FullName `
        -EntryName 'cn/alini/trueuuid/api/TrueuuidApi.class'
    if (-not $trueUuidApiPresent) {
        throw 'Installed TrueUUID JAR does not expose the required addon API.'
    }

    $xiyusContent = [System.IO.File]::ReadAllText($xiyusConfigPath)
    $trueUuidContent = [System.IO.File]::ReadAllText($trueUuidConfigPath)

    $enableIpSession = Get-SingleTomlSetting -Content $xiyusContent -Name 'enableIpSession' -Type Boolean
    $ipSessionDuration = Get-SingleTomlSetting -Content $xiyusContent -Name 'ipSessionDurationSeconds' -Type Integer
    $knownPremiumDenyOffline = Get-SingleTomlSetting -Content $trueUuidContent -Name 'knownPremiumDenyOffline' -Type Boolean
    $allowOfflineForUnknownOnly = Get-SingleTomlSetting -Content $trueUuidContent -Name 'allowOfflineForUnknownOnly' -Type Boolean
    $allowOfflineOnTimeout = Get-SingleTomlSetting -Content $trueUuidContent -Name 'allowOfflineOnTimeout' -Type Boolean

    $guardOk = (
        $knownPremiumDenyOffline.Value.ToLowerInvariant() -eq 'true' -and
        $allowOfflineForUnknownOnly.Value.ToLowerInvariant() -eq 'true' -and
        $allowOfflineOnTimeout.Value.ToLowerInvariant() -eq 'false'
    )
    if (-not $guardOk) {
        throw 'TrueUUID known-premium protection is not in the required safe state; no XiyusLogin change was made.'
    }

    $desiredState = (
        $enableIpSession.Value.ToLowerInvariant() -eq 'true' -and
        [int]$ipSessionDuration.Value -eq $ExpectedDuration
    )

    return [pscustomobject]@{
        XiyusConfigPath = $xiyusConfigPath
        TrueUuidConfigPath = $trueUuidConfigPath
        XiyusJar = $xiyusJars[0].FullName
        TrueUuidJar = $trueUuidJars[0].FullName
        TrueUuidApiPresent = $trueUuidApiPresent
        XiyusContent = $xiyusContent
        EnableIpSessionSetting = $enableIpSession
        IpSessionDurationSetting = $ipSessionDuration
        CurrentEnableIpSession = $enableIpSession.Value.ToLowerInvariant() -eq 'true'
        CurrentDurationSeconds = [int]$ipSessionDuration.Value
        DesiredDurationSeconds = $ExpectedDuration
        DesiredState = $desiredState
        KnownPremiumDenyOffline = $knownPremiumDenyOffline.Value.ToLowerInvariant() -eq 'true'
        AllowOfflineForUnknownOnly = $allowOfflineForUnknownOnly.Value.ToLowerInvariant() -eq 'true'
        AllowOfflineOnTimeout = $allowOfflineOnTimeout.Value.ToLowerInvariant() -eq 'true'
    }
}

function Write-JsonNoBom {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $json = $Value | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, $utf8NoBom)
}

$canonicalServerRoot = Get-CanonicalPath -Path $ServerRoot -MustExist
if (-not (Test-Path -LiteralPath $canonicalServerRoot -PathType Container)) {
    throw "Server root is not a directory: $canonicalServerRoot"
}

if (-not [string]::IsNullOrWhiteSpace($RollbackReceipt)) {
    if (-not $ConfirmServerStopped) {
        throw 'Rollback requires -ConfirmServerStopped.'
    }
    $running = Get-RunningServerJavaProcess -CanonicalServerRoot $canonicalServerRoot
    if ($null -ne $running) {
        throw "Refusing rollback while a matching Java process is running (PID $($running.ProcessId))."
    }

    $receiptPath = Get-CanonicalPath -Path $RollbackReceipt -MustExist
    $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($receipt.schema -ne 'xiyuslogin-auto-session-ota/v1') {
        throw 'Unsupported rollback receipt schema.'
    }

    $targetPath = Get-CanonicalPath -Path ([string]$receipt.targetPath) -MustExist
    $backupPath = Get-CanonicalPath -Path ([string]$receipt.backupPath) -MustExist
    Assert-PathUnderRoot -Path $targetPath -Root $canonicalServerRoot
    Assert-PathUnderRoot -Path $backupPath -Root $canonicalServerRoot
    $expectedTarget = Get-CanonicalPath -Path (Join-Path $canonicalServerRoot 'config\xiyuslogin-common.toml')
    if (-not $targetPath.Equals($expectedTarget, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Receipt target is not this server root''s XiyusLogin config.'
    }

    $currentHash = Get-Sha256 -Path $targetPath
    if ($currentHash -ne ([string]$receipt.afterSha256).ToUpperInvariant()) {
        throw 'CAS rollback refused: current config differs from the receipt post-apply hash.'
    }
    if ((Get-Sha256 -Path $backupPath) -ne ([string]$receipt.beforeSha256).ToUpperInvariant()) {
        throw 'Rollback backup hash mismatch.'
    }

    $rollbackTemp = Join-Path (Split-Path -Parent $targetPath) ('.xiyuslogin-auto-session-rollback-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $rollbackDisplaced = Join-Path (Split-Path -Parent $backupPath) 'xiyuslogin-common.toml.pre-rollback'
    if (Test-Path -LiteralPath $rollbackDisplaced) {
        throw "Refusing to overwrite an existing rollback-displaced copy: $rollbackDisplaced"
    }
    [System.IO.File]::Copy($backupPath, $rollbackTemp, $false)
    try {
        [System.IO.File]::Replace($rollbackTemp, $targetPath, $rollbackDisplaced)
    } finally {
        if (Test-Path -LiteralPath $rollbackTemp) {
            Remove-Item -LiteralPath $rollbackTemp -Force
        }
    }

    $restoredHash = Get-Sha256 -Path $targetPath
    if ($restoredHash -ne ([string]$receipt.beforeSha256).ToUpperInvariant()) {
        throw 'Rollback completed but restored hash verification failed.'
    }

    $rollbackSummary = [pscustomobject]@{
        schema = 'xiyuslogin-auto-session-ota-rollback/v1'
        scriptVersion = $scriptVersion
        status = 'rolled_back'
        rolledBackAtUtc = [DateTime]::UtcNow.ToString('o')
        serverRoot = $canonicalServerRoot
        targetPath = $targetPath
        sourceReceipt = $receiptPath
        restoredSha256 = $restoredHash
    }
    Write-Output ($rollbackSummary | ConvertTo-Json -Depth 5)
    exit 0
}

$readiness = Get-AuthReadiness -CanonicalServerRoot $canonicalServerRoot -ExpectedDuration $DurationSeconds

if ($RequireDesiredState -and -not $readiness.DesiredState) {
    throw "Desired XiyusLogin session state is not active: enableIpSession=$($readiness.CurrentEnableIpSession), duration=$($readiness.CurrentDurationSeconds)."
}

if (-not $Apply) {
    $plan = [pscustomobject]@{
        schema = 'xiyuslogin-auto-session-ota-plan/v1'
        scriptVersion = $scriptVersion
        status = if ($readiness.DesiredState) { 'already_compliant' } else { 'change_required' }
        serverRoot = $canonicalServerRoot
        targetPath = $readiness.XiyusConfigPath
        current = [pscustomobject]@{
            enableIpSession = $readiness.CurrentEnableIpSession
            ipSessionDurationSeconds = $readiness.CurrentDurationSeconds
        }
        desired = [pscustomobject]@{
            enableIpSession = $true
            ipSessionDurationSeconds = $DurationSeconds
        }
        trueUuidGuard = [pscustomobject]@{
            apiPresent = $readiness.TrueUuidApiPresent
            knownPremiumDenyOffline = $readiness.KnownPremiumDenyOffline
            allowOfflineForUnknownOnly = $readiness.AllowOfflineForUnknownOnly
            allowOfflineOnTimeout = $readiness.AllowOfflineOnTimeout
        }
        note = 'IP sessions are in-memory in XiyusLogin 1.4-migration4; one manual /login is still required after each server restart.'
    }
    Write-Output ($plan | ConvertTo-Json -Depth 6)
    exit 0
}

if (-not $ConfirmServerStopped) {
    throw 'Apply requires -ConfirmServerStopped.'
}
$runningProcess = Get-RunningServerJavaProcess -CanonicalServerRoot $canonicalServerRoot
if ($null -ne $runningProcess) {
    throw "Refusing apply while a matching Java process is running (PID $($runningProcess.ProcessId))."
}

if ($readiness.DesiredState) {
    $noChange = [pscustomobject]@{
        schema = 'xiyuslogin-auto-session-ota/v1'
        scriptVersion = $scriptVersion
        status = 'no_change'
        serverRoot = $canonicalServerRoot
        targetPath = $readiness.XiyusConfigPath
        sha256 = Get-Sha256 -Path $readiness.XiyusConfigPath
    }
    Write-Output ($noChange | ConvertTo-Json -Depth 5)
    exit 0
}

$beforeHash = Get-Sha256 -Path $readiness.XiyusConfigPath
$updatedContent = Set-SingleTomlSetting -Content $readiness.XiyusContent `
    -Setting $readiness.EnableIpSessionSetting -Value 'true'
$durationSettingAfterFirstEdit = Get-SingleTomlSetting -Content $updatedContent `
    -Name 'ipSessionDurationSeconds' -Type Integer
$updatedContent = Set-SingleTomlSetting -Content $updatedContent `
    -Setting $durationSettingAfterFirstEdit -Value ([string]$DurationSeconds)

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$backupDirectory = Join-Path $canonicalServerRoot "ota-backups\xiyuslogin-auto-session-$timestamp"
Assert-PathUnderRoot -Path $backupDirectory -Root $canonicalServerRoot
[System.IO.Directory]::CreateDirectory($backupDirectory) | Out-Null
$backupPath = Join-Path $backupDirectory 'xiyuslogin-common.toml.before'
[System.IO.File]::Copy($readiness.XiyusConfigPath, $backupPath, $false)
if ((Get-Sha256 -Path $backupPath) -ne $beforeHash) {
    throw 'Backup verification failed; target was not changed.'
}

$temporaryPath = Join-Path (Split-Path -Parent $readiness.XiyusConfigPath) `
    ('.xiyuslogin-auto-session-' + [guid]::NewGuid().ToString('N') + '.tmp')
$replaceBackupPath = Join-Path $backupDirectory 'xiyuslogin-common.toml.replace-backup'
[System.IO.File]::WriteAllText($temporaryPath, $updatedContent, $utf8NoBom)
$candidateHash = Get-Sha256 -Path $temporaryPath
try {
    [System.IO.File]::Replace($temporaryPath, $readiness.XiyusConfigPath, $replaceBackupPath)
} finally {
    if (Test-Path -LiteralPath $temporaryPath) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }
}

if ((Get-Sha256 -Path $replaceBackupPath) -ne $beforeHash) {
    throw 'Atomic replacement displaced-copy verification failed.'
}

$afterHash = Get-Sha256 -Path $readiness.XiyusConfigPath
if ($afterHash -ne $candidateHash) {
    throw 'Atomic replacement hash verification failed.'
}
$postReadiness = Get-AuthReadiness -CanonicalServerRoot $canonicalServerRoot -ExpectedDuration $DurationSeconds
if (-not $postReadiness.DesiredState) {
    throw 'Post-apply configuration verification failed.'
}

$receiptPath = Join-Path $backupDirectory 'receipt.json'
$receipt = [pscustomobject]@{
    schema = 'xiyuslogin-auto-session-ota/v1'
    scriptVersion = $scriptVersion
    status = 'applied'
    appliedAtUtc = [DateTime]::UtcNow.ToString('o')
    serverRoot = $canonicalServerRoot
    targetPath = $readiness.XiyusConfigPath
    backupPath = $backupPath
    beforeSha256 = $beforeHash
    afterSha256 = $afterHash
    changedKeys = @('enableIpSession', 'ipSessionDurationSeconds')
    desired = [pscustomobject]@{
        enableIpSession = $true
        ipSessionDurationSeconds = $DurationSeconds
    }
    trueUuidGuard = [pscustomobject]@{
        jarSha256 = Get-Sha256 -Path $readiness.TrueUuidJar
        apiPresent = $postReadiness.TrueUuidApiPresent
        knownPremiumDenyOffline = $postReadiness.KnownPremiumDenyOffline
        allowOfflineForUnknownOnly = $postReadiness.AllowOfflineForUnknownOnly
        allowOfflineOnTimeout = $postReadiness.AllowOfflineOnTimeout
    }
    limitation = 'XiyusLogin 1.4-migration4 stores IP sessions only in memory; server restart clears them.'
}
Write-JsonNoBom -Value $receipt -Path $receiptPath

$result = [pscustomobject]@{
    schema = 'xiyuslogin-auto-session-ota-result/v1'
    status = 'applied'
    serverRoot = $canonicalServerRoot
    targetPath = $readiness.XiyusConfigPath
    receiptPath = $receiptPath
    backupPath = $backupPath
    beforeSha256 = $beforeHash
    afterSha256 = $afterHash
}
Write-Output ($result | ConvertTo-Json -Depth 5)
