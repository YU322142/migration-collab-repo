param(
    [Parameter(Mandatory = $true)] [string] $MinecraftRoot,
    [string] $ServerAddress = '',
    [string] $SingleplayerWorld = '',
    [Parameter(Mandatory = $true)] [string] $Username,
    [Parameter(Mandatory = $true)] [string] $Uuid,
    [string] $Java = 'C:\Program Files\Java\jdk-21.0.10\bin\java.exe',
    [int] $MaximumMemoryMb = 4096,
    [string] $ResultPath = '',
    [string] $ExitPath = '',
    [switch] $BackgroundWindow
)

$ErrorActionPreference = 'Stop'
$root = [System.IO.Path]::GetFullPath($MinecraftRoot)
$javaPath = [System.IO.Path]::GetFullPath($Java)
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw "MinecraftRoot is missing: $root" }
if (-not (Test-Path -LiteralPath $javaPath -PathType Leaf)) { throw "Java is missing: $javaPath" }
if ($Username -notmatch '^[A-Za-z0-9_]{1,16}$') { throw 'Username must be a safe offline test name' }
if ($Uuid -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Uuid must be a canonical UUID' }
if (-not [string]::IsNullOrWhiteSpace($ServerAddress) -and -not [string]::IsNullOrWhiteSpace($SingleplayerWorld)) {
    throw 'ServerAddress and SingleplayerWorld are mutually exclusive'
}
if (-not [string]::IsNullOrWhiteSpace($SingleplayerWorld)) {
    if ($SingleplayerWorld -notmatch '^[A-Za-z0-9_. -]{1,128}$' -or
        [System.IO.Path]::GetFileName($SingleplayerWorld) -ne $SingleplayerWorld) {
        throw 'SingleplayerWorld must be a safe saves folder name'
    }
    $singleplayerPath = Join-Path (Join-Path $root 'saves') $SingleplayerWorld
    if (-not (Test-Path -LiteralPath $singleplayerPath -PathType Container)) {
        throw "Singleplayer world is missing: $singleplayerPath"
    }
}

function Write-AtomicJson([string] $Path, [object] $Value) {
    $destination = [IO.Path]::GetFullPath($Path)
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    $temporary = $destination + '.tmp'
    [IO.File]::WriteAllText(
        $temporary,
        ($Value | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $destination -Force
}

$versions = Join-Path $root 'versions'
$neoJsonPath = Join-Path $versions 'neoforge-21.1.241\neoforge-21.1.241.json'
$mcJsonPath = Join-Path $versions '1.21.1\1.21.1.json'
foreach ($path in @($neoJsonPath, $mcJsonPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Version metadata is missing: $path" }
}
$neo = Get-Content -LiteralPath $neoJsonPath -Raw | ConvertFrom-Json
$mc = Get-Content -LiteralPath $mcJsonPath -Raw | ConvertFrom-Json
$libraries = Join-Path $root 'libraries'
$separator = [IO.Path]::PathSeparator

function Artifact-Path([object] $library) {
    $artifact = $library.downloads.artifact
    if ($null -eq $artifact -or [string]::IsNullOrWhiteSpace([string]$artifact.path)) { return $null }
    return Join-Path $libraries ([string]$artifact.path)
}

function Allowed-OnWindows([object] $library) {
    $rules = @()
    if ($null -ne $library.PSObject.Properties['rules'] -and $null -ne $library.rules) {
        $rules = @($library.rules)
    }
    if ($rules.Count -eq 0) { return $true }
    $allowed = $false
    foreach ($rule in $rules) {
        $osName = if ($null -ne $rule.os) { [string]$rule.os.name } else { $null }
        $matches = ($null -eq $osName -or $osName -eq 'windows')
        if ($matches) { $allowed = ([string]$rule.action -eq 'allow') }
    }
    return $allowed
}

$libraryPaths = [System.Collections.Generic.List[string]]::new()
$nativeJars = [System.Collections.Generic.List[string]]::new()
$missingNativeArtifacts = [System.Collections.Generic.List[string]]::new()
foreach ($library in @($mc.libraries) + @($neo.libraries)) {
    if (-not (Allowed-OnWindows $library)) { continue }
    $path = Artifact-Path $library
    if ($null -eq $path) { continue }
    if ([string]$library.name -match ':natives-windows(?:-|$)') {
        if (Test-Path -LiteralPath $path -PathType Leaf) { $nativeJars.Add($path) }
        else { $missingNativeArtifacts.Add($path) }
        continue
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Library is missing: $path" }
    $libraryPaths.Add($path)
}
$vanillaClientJar = Join-Path $versions '1.21.1\1.21.1.jar'
$forgeWrapperJar = Join-Path $libraries 'io\github\zekerzhayard\ForgeWrapper\prism-2025-12-07\ForgeWrapper-prism-2025-12-07.jar'
$neoInstallerJar = Join-Path $libraries 'net\neoforged\neoforge\21.1.241\neoforge-21.1.241-installer.jar'
foreach ($path in @($vanillaClientJar, $forgeWrapperJar, $neoInstallerJar)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Launcher input is missing: $path" }
}
$libraryPaths.Add($forgeWrapperJar)
$libraryPaths.Add($vanillaClientJar)

$nativeDir = Join-Path $root 'natives'
$nativeSource = 'metadata_artifacts'
if ($missingNativeArtifacts.Count -gt 0) {
    if ($nativeJars.Count -gt 0) {
        throw "Native library set is partial ($($nativeJars.Count) present, $($missingNativeArtifacts.Count) missing)"
    }
    $versionsItem = Get-Item -LiteralPath $versions -Force
    $versionTargets = @($versionsItem.Target)
    if (-not ($versionsItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        $versionTargets.Count -ne 1) {
        throw "Native libraries are missing and versions is not a single-target reparse point: $versions"
    }
    $resolvedVersions = [IO.Path]::GetFullPath([string]$versionTargets[0])
    if ([IO.Path]::GetFileName($resolvedVersions.TrimEnd('\')) -ne 'versions') {
        throw "Resolved versions target has an unexpected name: $resolvedVersions"
    }
    $nativeDir = Join-Path (Split-Path -Parent $resolvedVersions) 'natives'
    $requiredNativeFiles = @(
        'windows\x64\org\lwjgl\lwjgl.dll',
        'windows\x64\org\lwjgl\freetype\freetype.dll',
        'windows\x64\org\lwjgl\glfw\glfw.dll',
        'windows\x64\org\lwjgl\jemalloc\jemalloc.dll',
        'windows\x64\org\lwjgl\openal\OpenAL.dll',
        'windows\x64\org\lwjgl\opengl\lwjgl_opengl.dll',
        'windows\x64\org\lwjgl\stb\lwjgl_stb.dll',
        'windows\x64\org\lwjgl\tinyfd\lwjgl_tinyfd.dll'
    )
    $missingReusableNativeFiles = @(
        $requiredNativeFiles | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $nativeDir $_) -PathType Leaf)
        }
    )
    if ($missingReusableNativeFiles.Count -gt 0) {
        throw "Reusable native directory is incomplete: $nativeDir [$($missingReusableNativeFiles -join ', ')]"
    }
    $nativeSource = 'versions_sibling'
} else {
    New-Item -ItemType Directory -Path $nativeDir -Force | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $nativeIndex = 0
    foreach ($jar in $nativeJars) {
        $nativeIndex++
        $temporary = Join-Path $root (".native-extract-" + $nativeIndex)
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
        New-Item -ItemType Directory -Path $temporary -Force | Out-Null
        try {
            [IO.Compression.ZipFile]::ExtractToDirectory($jar, $temporary)
            Get-ChildItem -LiteralPath $temporary -Recurse -File | ForEach-Object {
                $relative = $_.FullName.Substring($temporary.Length).TrimStart([char[]]@([char]92, [char]47))
                $destination = Join-Path $nativeDir $relative
                New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
            }
        } catch { throw "Unable to extract native jar $jar`: $($_.Exception.Message)" }
        finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force } }
    }
}

$jvmArgs = [System.Collections.Generic.List[string]]::new()
$jvmArgs.Add("-Xms512m")
$jvmArgs.Add("-Xmx${MaximumMemoryMb}m")
$jvmArgs.Add("-Djava.library.path=$nativeDir")
$jvmArgs.Add("-Duser.home=$root")
$jvmArgs.Add("-Dforgewrapper.librariesDir=$libraries")
$jvmArgs.Add("-Dforgewrapper.installer=$neoInstallerJar")
$jvmArgs.Add("-Dforgewrapper.minecraft=$vanillaClientJar")
$jvmArgs.Add('-cp')
$jvmArgs.Add(($libraryPaths | Select-Object -Unique) -join $separator)

$gameArgs = @(
    '--username', $Username,
    '--version', 'neoforge-21.1.241',
    '--gameDir', $root,
    '--assetsDir', (Join-Path $root 'assets'),
    '--assetIndex', [string]$mc.assetIndex.id,
    '--uuid', $Uuid,
    '--accessToken', '0',
    '--clientId', '0',
    '--xuid', '0',
    '--userType', 'legacy',
    '--versionType', 'release',
    '--width', '1280',
    '--height', '720'
)
if (-not [string]::IsNullOrWhiteSpace($ServerAddress)) {
    $gameArgs += @('--quickPlayMultiplayer', $ServerAddress)
}
if (-not [string]::IsNullOrWhiteSpace($SingleplayerWorld)) {
    $gameArgs += @('--quickPlaySingleplayer', $SingleplayerWorld)
}
$allArgs = @($jvmArgs) + @('io.github.zekerzhayard.forgewrapper.installer.Main') + @($neo.arguments.game | ForEach-Object { if ($_ -is [string]) { $_ } }) + $gameArgs
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$stdout = Join-Path $root "client-$stamp.stdout.log"
$stderr = Join-Path $root "client-$stamp.stderr.log"
$startOptions = @{
    FilePath = $javaPath
    ArgumentList = $allArgs
    WorkingDirectory = $root
    RedirectStandardOutput = $stdout
    RedirectStandardError = $stderr
    PassThru = $true
}
if ($BackgroundWindow) { $startOptions.WindowStyle = 'Hidden' }
$process = Start-Process @startOptions
$result = [pscustomobject]@{
    pid = $process.Id
    root = $root
    server = $ServerAddress
    singleplayerWorld = $SingleplayerWorld
    username = $Username
    stdout = $stdout
    stderr = $stderr
    native_source = $nativeSource
    native_directory = $nativeDir
    launched_at_utc = [DateTime]::UtcNow.ToString('o')
    exit_state = if ([string]::IsNullOrWhiteSpace($ExitPath)) { '' } else { [IO.Path]::GetFullPath($ExitPath) }
}
if (-not [string]::IsNullOrWhiteSpace($ResultPath)) {
    Write-AtomicJson $ResultPath $result
}
if ([string]::IsNullOrWhiteSpace($ExitPath)) {
    $result
} else {
    $process.WaitForExit()
    # A second wait guarantees redirected stdout/stderr have drained before the
    # exit record is published to the supervising private-desktop helper.
    $process.WaitForExit()
    $exitResult = [pscustomobject]@{
        pid = $process.Id
        exit_code = $process.ExitCode
        stdout = $stdout
        stderr = $stderr
        exited_at_utc = [DateTime]::UtcNow.ToString('o')
    }
    Write-AtomicJson $ExitPath $exitResult
}
