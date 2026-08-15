$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$projectVersion = '1.9.2'
$jarFileName = "MCModSync-$projectVersion.jar"
$sourceZipFileName = "MCModSync-$projectVersion-source.zip"
$fabricMinecraftTargets = @('1.21.1', '1.21.11')
$neoForgeMinecraftRange = '[1.21.1]'
$neoForgeVersionRange = '[21.1.0,)'
$buildDirectory = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
$expectedBuildDirectory = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
if ($buildDirectory -ne $expectedBuildDirectory -or -not $buildDirectory.StartsWith($projectRoot + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to clean unexpected build directory: $buildDirectory"
}
if (Test-Path -LiteralPath $buildDirectory) {
    Remove-Item -LiteralPath $buildDirectory -Recurse -Force
}

$mainClasses = Join-Path $buildDirectory 'classes-main'
$testClasses = Join-Path $buildDirectory 'classes-test'
$distDirectory = Join-Path $buildDirectory 'dist'
New-Item -ItemType Directory -Path $mainClasses, $testClasses, $distDirectory -Force | Out-Null

$mainSources = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src\main\java') -Recurse -File -Filter '*.java' |
    Sort-Object FullName |
    ForEach-Object FullName
$testSources = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src\test\java') -Recurse -File -Filter '*.java' |
    Sort-Object FullName |
    ForEach-Object FullName
$compileOnlySources = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src\compileOnly\java') -Recurse -File -Filter '*.java' |
    Sort-Object FullName |
    ForEach-Object FullName

if (-not $mainSources) {
    throw 'No main Java sources found.'
}

Write-Output '[1/8] Compiling Java 21-compatible main classes with Fabric and NeoForge compile-only API shapes...'
$mainArguments = @('--release', '21', '-encoding', 'UTF-8', '-d', $mainClasses) + $compileOnlySources + $mainSources
& javac @mainArguments
if ($LASTEXITCODE -ne 0) {
    throw "javac main failed with exit code $LASTEXITCODE"
}

Write-Output '[2/8] Compiling tests...'
$testArguments = @('--release', '21', '--add-modules', 'jdk.httpserver', '-encoding', 'UTF-8', '-d', $testClasses) + $compileOnlySources + $mainSources + $testSources
& javac @testArguments
if ($LASTEXITCODE -ne 0) {
    throw "javac tests failed with exit code $LASTEXITCODE"
}

Write-Output '[3/8] Running tests...'
& java --add-modules jdk.httpserver -cp "$mainClasses;$testClasses" io.github.mcmodsync.AllTests
if ($LASTEXITCODE -ne 0) {
    throw "tests failed with exit code $LASTEXITCODE"
}

$jarPath = Join-Path $distDirectory $jarFileName
$compileOnlyStubClass = Join-Path $mainClasses 'net\fabricmc\loader\api\entrypoint\PreLaunchEntrypoint.class'
if (-not (Test-Path -LiteralPath $compileOnlyStubClass -PathType Leaf)) {
    throw "Expected compile-only Fabric API class not found: $compileOnlyStubClass"
}
$neoForgeDistStubClass = Join-Path $mainClasses 'net\neoforged\api\distmarker\Dist.class'
$neoForgeModStubClass = Join-Path $mainClasses 'net\neoforged\fml\common\Mod.class'
$neoForgeStubsPresent = (Test-Path -LiteralPath $neoForgeDistStubClass -PathType Leaf) -and
        (Test-Path -LiteralPath $neoForgeModStubClass -PathType Leaf)
if (-not $neoForgeStubsPresent) {
    throw "Expected compile-only NeoForge API classes were not found under $mainClasses"
}
$fabricStubRoot = Join-Path $mainClasses 'net\fabricmc'
if (Test-Path -LiteralPath $fabricStubRoot) {
    Remove-Item -LiteralPath $fabricStubRoot -Recurse -Force
}
$neoForgeStubRoot = Join-Path $mainClasses 'net\neoforged'
if (Test-Path -LiteralPath $neoForgeStubRoot) {
    Remove-Item -LiteralPath $neoForgeStubRoot -Recurse -Force
}

Write-Output '[4/8] Building Fabric/NeoForge/executable/agent JAR...'
& jar --create --file $jarPath --manifest (Join-Path $projectRoot 'manifest.mf') `
    -C $mainClasses . `
    -C (Join-Path $projectRoot 'src\main\resources') .
if ($LASTEXITCODE -ne 0) {
    throw "jar failed with exit code $LASTEXITCODE"
}
$loaderApiLeak = & jar tf $jarPath | Select-String -Pattern '^net/(fabricmc|neoforged)/'
if ($loaderApiLeak) {
    throw "Refusing to ship Fabric/NeoForge Loader API classes inside MCModSync jar: $loaderApiLeak"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead($jarPath)
try {
    $metadataEntry = $archive.GetEntry('fabric.mod.json')
    if ($null -eq $metadataEntry) {
        throw 'Packaged JAR is missing fabric.mod.json.'
    }
    $metadataStream = $metadataEntry.Open()
    try {
        $metadataReader = [System.IO.StreamReader]::new(
            $metadataStream,
            [System.Text.UTF8Encoding]::new($false, $true))
        try {
            $fabricMetadata = $metadataReader.ReadToEnd() | ConvertFrom-Json
        } finally {
            $metadataReader.Dispose()
        }
    } finally {
        $metadataStream.Dispose()
    }
} finally {
    $archive.Dispose()
}
    $minecraftTargets = @($fabricMetadata.depends.minecraft)
    $metadataInvalid = ($fabricMetadata.version -ne $projectVersion) -or
            ($fabricMetadata.depends.fabricloader -ne '>=0.15.11') -or
            (($minecraftTargets -join ',') -ne ($fabricMinecraftTargets -join ',')) -or
            ($fabricMetadata.depends.java -ne '>=21')
if ($metadataInvalid) {
    throw "Unexpected packaged Fabric compatibility metadata: version=$($fabricMetadata.version), " +
            "loader=$($fabricMetadata.depends.fabricloader), minecraft=$($minecraftTargets -join ','), " +
            "java=$($fabricMetadata.depends.java)"
}
$neoArchive = [System.IO.Compression.ZipFile]::OpenRead($jarPath)
try {
    $neoEntry = $neoArchive.GetEntry('META-INF/neoforge.mods.toml')
    if ($null -eq $neoEntry) {
        throw 'Packaged JAR is missing META-INF/neoforge.mods.toml.'
    }
    $neoStream = $neoEntry.Open()
    try {
        $neoReader = [System.IO.StreamReader]::new(
            $neoStream,
            [System.Text.UTF8Encoding]::new($false, $true))
        try {
            $neoText = $neoReader.ReadToEnd()
        } finally {
            $neoReader.Dispose()
        }
    } finally {
        $neoStream.Dispose()
    }
    if ($neoText -match '\$\{') {
        throw 'Packaged NeoForge metadata contains an unresolved ${...} placeholder.'
    }
    $loaderMetadataValid = ($neoText -match '(?m)^modLoader\s*=\s*"javafml"\s*$') -and
            ($neoText -match '(?m)^loaderVersion\s*=\s*"\[1,\)"\s*$') -and
            ($neoText -match '(?m)^license\s*=\s*"[^"]+"\s*$')
    if (-not $loaderMetadataValid) {
        throw 'Packaged NeoForge metadata has invalid loaderVersion/modLoader/license.'
    }
    $modsBlock = [regex]::Match($neoText, '(?ms)^\[\[mods\]\](.*?)(?=^\[\[|\z)').Value
    $neoVersionPattern = '(?m)^version\s*=\s*"' + [regex]::Escape($projectVersion) + '"\s*$'
    $neoMinecraftRangePattern = '(?m)^versionRange\s*=\s*"' + [regex]::Escape($neoForgeMinecraftRange) + '"\s*$'
    $neoForgeRangePattern = '(?m)^versionRange\s*=\s*"' + [regex]::Escape($neoForgeVersionRange) + '"\s*$'
    $modsMetadataValid = ($modsBlock -match '(?m)^modId\s*=\s*"mcmodsync"\s*$') -and
            ($modsBlock -match $neoVersionPattern) -and
            ($modsBlock -match '(?m)^description\s*=')
    if (-not $modsMetadataValid) {
        throw 'Packaged NeoForge [[mods]] metadata is invalid.'
    }
    $dependencyBlocks = [regex]::Matches($neoText, '(?ms)^\[\[dependencies\.mcmodsync\]\](.*?)(?=^\[\[|\z)')
    $hasMinecraftDependency = $false
    $hasNeoForgeDependency = $false
    foreach ($dependency in $dependencyBlocks) {
        $block = $dependency.Value
        $minecraftDependencyValid = ($block -match '(?m)^modId\s*=\s*"minecraft"\s*$') -and
                ($block -match $neoMinecraftRangePattern) -and
                ($block -match '(?m)^type\s*=\s*"required"\s*$') -and
                ($block -match '(?m)^side\s*=\s*"CLIENT"\s*$')
        if ($minecraftDependencyValid) {
            $hasMinecraftDependency = $true
        }
        $neoForgeDependencyValid = ($block -match '(?m)^modId\s*=\s*"neoforge"\s*$') -and
                ($block -match $neoForgeRangePattern) -and
                ($block -match '(?m)^type\s*=\s*"required"\s*$') -and
                ($block -match '(?m)^side\s*=\s*"CLIENT"\s*$')
        if ($neoForgeDependencyValid) {
            $hasNeoForgeDependency = $true
        }
    }
    if (-not $hasMinecraftDependency -or -not $hasNeoForgeDependency) {
        throw 'Packaged NeoForge dependencies do not require NeoForge and Minecraft 1.21.1 on CLIENT.'
    }
    $entryClass = $neoArchive.GetEntry('io/github/mcmodsync/NeoForgeModEntrypoint.class')
    if ($null -eq $entryClass) {
        throw 'Packaged JAR is missing NeoForgeModEntrypoint.class.'
    }
    $manifestEntry = $neoArchive.GetEntry('META-INF/MANIFEST.MF')
    if ($null -eq $manifestEntry) {
        throw 'Packaged JAR is missing META-INF/MANIFEST.MF.'
    }
    $manifestStream = $manifestEntry.Open()
    try {
        $manifestReader = [System.IO.StreamReader]::new($manifestStream, [System.Text.Encoding]::ASCII)
        try {
            $jarManifest = $manifestReader.ReadToEnd()
        } finally {
            $manifestReader.Dispose()
        }
    } finally {
        $manifestStream.Dispose()
    }
    $implementationVersionPattern = '(?m)^Implementation-Version:\s*' + [regex]::Escape($projectVersion) + '\s*$'
    if ($jarManifest -notmatch $implementationVersionPattern) {
        throw 'Packaged MANIFEST.MF has an unexpected Implementation-Version.'
    }
} finally {
    $neoArchive.Dispose()
}
$reportedVersion = (& java -jar $jarPath --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $reportedVersion -ne "MCModSync $projectVersion") {
    throw "Packaged CLI reported an unexpected version: $reportedVersion"
}
Write-Output 'Packaged Fabric/NeoForge metadata and CLI version passed.'

$legacyJarForSmoke = $env:MCMODSYNC_LEGACY_JAR
if ($legacyJarForSmoke) {
    $legacyJarForSmoke = [System.IO.Path]::GetFullPath($legacyJarForSmoke)
    if (-not (Test-Path -LiteralPath $legacyJarForSmoke -PathType Leaf)) {
        throw "MCMODSYNC_LEGACY_JAR does not exist: $legacyJarForSmoke"
    }
    $legacyEntrypoint = $env:MCMODSYNC_LEGACY_ENTRYPOINT
    if (-not $legacyEntrypoint) {
        throw 'MCMODSYNC_LEGACY_ENTRYPOINT must be set when running a historical-JAR transition smoke.'
    }
    Write-Output "Running real historical-JAR transition smoke: $legacyJarForSmoke"
    & java --add-modules jdk.httpserver -cp "$mainClasses;$testClasses" `
        io.github.mcmodsync.LegacyUpgradeIntegrationSmoke `
        $legacyJarForSmoke $jarPath $testClasses $legacyEntrypoint
    if ($LASTEXITCODE -ne 0) {
        throw "real historical-JAR transition smoke failed with exit code $LASTEXITCODE"
    }
}


Write-Output '[5/8] Verifying the real portable helper exits cleanly and installs the update...'
& java --add-modules jdk.httpserver -cp "$jarPath;$testClasses" `
    io.github.mcmodsync.PostBuildPortableSmoke $jarPath $testClasses
if ($LASTEXITCODE -ne 0) {
    throw "post-build portable helper smoke test failed with exit code $LASTEXITCODE"
}

Write-Output '[6/8] Verifying legacy fail-open configuration can no longer bypass blocking...'
$smokeDirectory = Join-Path $buildDirectory 'agent-smoke-game'
New-Item -ItemType Directory -Path (Join-Path $smokeDirectory 'mods') -Force | Out-Null
$agentArgument = "-javaagent:$jarPath=gameDir=$smokeDirectory;manifest=http://127.0.0.1:1/mods.txt;requireManifest=false;connectTimeoutSeconds=1"
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$smokeOutput = & java '-Dmodsync.disableDialogs=true' '-Dmodsync.syncResourcePacks=false' '-Dmodsync.syncServerList=false' $agentArgument -cp "$mainClasses;$testClasses" io.github.mcmodsync.DummyMain 2>&1
$smokeExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorAction
$smokeText = $smokeOutput | Out-String
if ($smokeExitCode -ne 0) {
    throw 'legacy fail-open rejection did not exit normally'
}
if ($smokeText -notmatch 'STARTUP_BLOCKED') {
    throw 'legacy fail-open rejection did not emit STARTUP_BLOCKED'
}
if ($smokeText -match 'Dummy main reached') {
    throw 'legacy requireManifest=false unexpectedly reached the game main class'
}
Write-Output 'Legacy fail-open bypass rejection and normal exit passed.'

Write-Output '[7/8] Verifying fatal errors really block startup...'
$fatalDirectory = Join-Path $buildDirectory 'agent-fatal-game'
New-Item -ItemType Directory -Path (Join-Path $fatalDirectory 'mods') -Force | Out-Null
$fatalAgentArgument = "-javaagent:$jarPath=gameDir=$fatalDirectory;manifest=http://127.0.0.1:1/mods.txt;requireManifest=true;connectTimeoutSeconds=1"
$previousErrorAction = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$fatalOutput = & java '-Dmodsync.disableDialogs=true' '-Dmodsync.syncResourcePacks=false' '-Dmodsync.syncServerList=false' $fatalAgentArgument -cp "$mainClasses;$testClasses" io.github.mcmodsync.DummyMain 2>&1
$fatalExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorAction
$fatalText = $fatalOutput | Out-String
if ($fatalExitCode -ne 0) {
    throw 'fatal javaagent test did not exit normally'
}
if ($fatalText -notmatch 'STARTUP_BLOCKED') {
    throw 'fatal javaagent test did not emit STARTUP_BLOCKED'
}
if ($fatalText -match 'Dummy main reached') {
    throw 'fatal javaagent test unexpectedly reached the game main class'
}
Write-Output 'Fatal startup-block normal-exit test passed.'

Write-Output '[8/8] Copying deliverables...'
$workspaceRoot = [System.IO.Directory]::GetParent([System.IO.Directory]::GetParent($projectRoot).FullName).FullName
$outputsDirectory = Join-Path $workspaceRoot 'outputs'
New-Item -ItemType Directory -Path $outputsDirectory -Force | Out-Null
$jarOutputName = $jarFileName
Get-ChildItem -LiteralPath $outputsDirectory -File -Filter 'MCModSync-*.jar' -ErrorAction SilentlyContinue |
    Where-Object Name -ne $jarOutputName |
    ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Force
        } catch {
            Write-Warning "Keeping locked old JAR: $($_.FullName)"
        }
    }
Copy-Item -LiteralPath $jarPath -Destination (Join-Path $outputsDirectory $jarOutputName) -Force
$readmeDestinationName = 'MCModSync-README-zh-CN.md'
Get-ChildItem -LiteralPath $outputsDirectory -File -Filter 'MCModSync-*.md' -ErrorAction SilentlyContinue |
    Where-Object Name -ne $readmeDestinationName |
    ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Force
        } catch {
            Write-Warning "Keeping locked old documentation: $($_.FullName)"
        }
    }
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $outputsDirectory $readmeDestinationName) -Force
Copy-Item -LiteralPath (Join-Path $projectRoot 'modsync.properties.example') -Destination (Join-Path $outputsDirectory 'modsync.properties.example') -Force

$sourceZip = Join-Path $outputsDirectory $sourceZipFileName
Get-ChildItem -LiteralPath $outputsDirectory -File -Filter 'MCModSync-*-source.zip' -ErrorAction SilentlyContinue |
    Where-Object FullName -ne $sourceZip |
    ForEach-Object {
        try {
            Remove-Item -LiteralPath $_.FullName -Force
        } catch {
            Write-Warning "Keeping locked old source archive: $($_.FullName)"
        }
    }
if (Test-Path -LiteralPath $sourceZip) {
    Remove-Item -LiteralPath $sourceZip -Force
}
Compress-Archive -Path @(
    (Join-Path $projectRoot 'src'),
    (Join-Path $projectRoot 'build.ps1'),
    (Join-Path $projectRoot 'manifest.mf'),
    (Join-Path $projectRoot 'README.md'),
    (Join-Path $projectRoot 'modsync.properties.example'),
    (Join-Path $projectRoot 'LICENSE'),
    (Join-Path $projectRoot 'docs')
) -DestinationPath $sourceZip -CompressionLevel Optimal

Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $outputsDirectory $jarOutputName) |
    Select-Object Algorithm, Hash, Path
Write-Output "Build complete: $outputsDirectory"
