[CmdletBinding()]
param(
    [string]$OriginalJar = '<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814\mods\worldedit-mod-7.3.8.jar',
    [string]$ServerJar = '<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814\libraries\net\minecraft\server\1.21.1-20240808.144430\server-1.21.1-20240808.144430-srg.jar',
    [string]$GuavaJar = '<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814\libraries\com\google\guava\guava\32.1.2-jre\guava-32.1.2-jre.jar',
    [string]$FailureAccessJar = '<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814\libraries\com\google\guava\failureaccess\1.0.1\failureaccess-1.0.1.jar',
    [string]$OutputDirectory = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([String]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = $PSScriptRoot
}

function Assert-File([string]$Path, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
}

Assert-File $OriginalJar 'Original WorldEdit JAR'
Assert-File $ServerJar 'Minecraft server JAR'
Assert-File $GuavaJar 'Guava JAR'
Assert-File $FailureAccessJar 'FailureAccess JAR'

$source = Join-Path $PSScriptRoot 'source\com\sk89q\worldedit\neoforge\internal\NeoForgeTransmogrifier.java'
Assert-File $source 'Patched source'

$workRoot = [IO.Path]::GetFullPath((Join-Path $OutputDirectory 'repro-builds'))
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $workRoot.StartsWith($outputRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a build directory outside the artifact directory: $workRoot"
}

if (Test-Path -LiteralPath $workRoot) {
    Remove-Item -LiteralPath $workRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $workRoot | Out-Null

$javac = (Get-Command javac -ErrorAction Stop).Source
$jar = (Get-Command jar -ErrorAction Stop).Source
$classPath = @($OriginalJar, $ServerJar, $GuavaJar, $FailureAccessJar) -join [IO.Path]::PathSeparator
$entryMain = 'com/sk89q/worldedit/neoforge/internal/NeoForgeTransmogrifier.class'
$entryInner = 'com/sk89q/worldedit/neoforge/internal/NeoForgeTransmogrifier$1.class'
$fixedDate = '2024-10-16T16:53:06Z'
$jarHashes = @()

for ($build = 1; $build -le 2; $build++) {
    $classes = Join-Path $workRoot "build$build\classes"
    New-Item -ItemType Directory -Path $classes | Out-Null

    & $javac -J-Xmx512m --release 21 -g -encoding UTF-8 -cp $classPath -d $classes $source
    if ($LASTEXITCODE -ne 0) { throw "javac failed for build $build ($LASTEXITCODE)" }

    $candidate = Join-Path $OutputDirectory "worldedit-mod-7.3.8-direction-property-fix.build$build.jar"
    Copy-Item -LiteralPath $OriginalJar -Destination $candidate -Force
    & $jar --update --file $candidate --date=$fixedDate -C $classes $entryMain -C $classes $entryInner
    if ($LASTEXITCODE -ne 0) { throw "jar update failed for build $build ($LASTEXITCODE)" }
    & $jar --validate --file $candidate
    if ($LASTEXITCODE -ne 0) { throw "jar validation failed for build $build ($LASTEXITCODE)" }

    $jarHashes += [pscustomobject]@{
        Build = $build
        File = $candidate
        Bytes = (Get-Item -LiteralPath $candidate).Length
        SHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate).Hash
    }
}

if ($jarHashes[0].SHA256 -ne $jarHashes[1].SHA256) {
    throw "Reproducibility failure: build hashes differ ($($jarHashes[0].SHA256) vs $($jarHashes[1].SHA256))"
}

$final = Join-Path $OutputDirectory 'worldedit-mod-7.3.8-direction-property-fix.1.jar'
Copy-Item -LiteralPath $jarHashes[0].File -Destination $final -Force

[pscustomobject]@{
    Status = 'PASS'
    OriginalJar = $OriginalJar
    FinalJar = $final
    FinalBytes = (Get-Item -LiteralPath $final).Length
    FinalSHA256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $final).Hash
    Build1SHA256 = $jarHashes[0].SHA256
    Build2SHA256 = $jarHashes[1].SHA256
    Reproducible = ($jarHashes[0].SHA256 -eq $jarHashes[1].SHA256)
} | ConvertTo-Json -Depth 4
