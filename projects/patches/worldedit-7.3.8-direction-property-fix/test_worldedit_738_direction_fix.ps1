[CmdletBinding()]
param(
    [string]$OriginalJar = 'D:\Trans\migration-audit-work\mechanomania-matched-runtime-attempt6-20260814\mods\worldedit-mod-7.3.8.jar',
    [string]$FixedJar = '',
    [string]$RuntimeRoot = 'D:\Trans\migration-audit-work\mechanomania-matched-runtime-attempt6-20260814'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([String]::IsNullOrWhiteSpace($FixedJar)) {
    $FixedJar = Join-Path $PSScriptRoot 'worldedit-mod-7.3.8-direction-property-fix.1.jar'
}

function Assert-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label not found: $Path" }
}

Assert-File $OriginalJar 'Original WorldEdit JAR'
Assert-File $FixedJar 'Fixed WorldEdit JAR'

$testSource = Join-Path $PSScriptRoot 'test\DirectionPropertyCacheProbe.java'
Assert-File $testSource 'Regression probe source'
$server = Join-Path $RuntimeRoot 'libraries\net\minecraft\server\1.21.1-20240808.144430\server-1.21.1-20240808.144430-srg.jar'
$guava = Join-Path $RuntimeRoot 'libraries\com\google\guava\guava\32.1.2-jre\guava-32.1.2-jre.jar'
$failure = Join-Path $RuntimeRoot 'libraries\com\google\guava\failureaccess\1.0.1\failureaccess-1.0.1.jar'
$dataFixer = Join-Path $RuntimeRoot 'libraries\com\mojang\datafixerupper\8.0.16\datafixerupper-8.0.16.jar'
$fastUtil = Join-Path $RuntimeRoot 'libraries\it\unimi\dsi\fastutil\8.5.12\fastutil-8.5.12.jar'
foreach ($p in @($server, $guava, $failure, $dataFixer, $fastUtil)) { Assert-File $p "Runtime dependency" }

$testRoot = Join-Path $PSScriptRoot 'probe-run'
if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
$classes = Join-Path $testRoot 'classes'
New-Item -ItemType Directory -Path $classes | Out-Null
$compileCp = @($OriginalJar, $server, $guava, $failure, $dataFixer, $fastUtil) -join [IO.Path]::PathSeparator
$runCp = @($classes, $OriginalJar, $server, $guava, $failure, $dataFixer, $fastUtil) -join [IO.Path]::PathSeparator

& (Get-Command javac -ErrorAction Stop).Source -J-Xmx256m --release 21 -g -encoding UTF-8 -cp $compileCp -d $classes $testSource
if ($LASTEXITCODE -ne 0) { throw "Regression probe compilation failed ($LASTEXITCODE)" }

function Invoke-JavaProbe([string]$ClassPath, [string]$Mode) {
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = (Get-Command java -ErrorAction Stop).Source
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = "-Xms32m -Xmx256m -cp `"$ClassPath`" DirectionPropertyCacheProbe $Mode"
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    [pscustomobject]@{ ExitCode = $process.ExitCode; Stdout = $stdout; Stderr = $stderr }
}

$originalProbe = Invoke-JavaProbe $runCp 'broken'
$originalOutput = $originalProbe.Stdout
if ($originalProbe.ExitCode -ne 0 -or $originalOutput -notmatch 'fixed=false' -or $originalOutput -notmatch 'first_worldedit_property=com\.sk89q\.worldedit\.registry\.state\.EnumProperty') {
    throw "Original regression probe did not reproduce the known bug:`n$($originalOutput)`n$($originalProbe.Stderr)"
}

$fixedRunCp = @($classes, $FixedJar, $server, $guava, $failure, $dataFixer, $fastUtil) -join [IO.Path]::PathSeparator
$fixedProbe = Invoke-JavaProbe $fixedRunCp 'fixed'
$fixedOutput = $fixedProbe.Stdout
if ($fixedProbe.ExitCode -ne 0 -or $fixedOutput -notmatch 'fixed=true' -or $fixedOutput -notmatch 'first_worldedit_property=com\.sk89q\.worldedit\.registry\.state\.DirectionalProperty' -or $fixedOutput -notmatch 'second_worldedit_property=com\.sk89q\.worldedit\.registry\.state\.DirectionalProperty') {
    throw "Fixed regression probe failed:`n$($fixedOutput)`n$($fixedProbe.Stderr)"
}

[pscustomobject]@{
    Status = 'PASS'
    OriginalReproduced = $true
    FixedPassed = $true
    MinecraftLaunched = $false
    OriginalOutput = $originalOutput.Trim()
    FixedOutput = $fixedOutput.Trim()
} | ConvertTo-Json -Depth 5
