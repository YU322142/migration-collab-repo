param(
    [string] $Launcher = (Join-Path $PSScriptRoot 'launch_neoforge_client_isolated.ps1')
)

$ErrorActionPreference = 'Stop'

function Assert-True([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw $Message }
}

function Write-Utf8NoBom([string] $Path, [string] $Value) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    [IO.File]::WriteAllText($Path, $Value, [Text.UTF8Encoding]::new($false))
}

$launcherPath = [IO.Path]::GetFullPath($Launcher)
$launcherText = [IO.File]::ReadAllText($launcherPath)
$parseErrors = $null
[void][Management.Automation.Language.Parser]::ParseFile(
    $launcherPath, [ref]$null, [ref]$parseErrors
)
Assert-True ($parseErrors.Count -eq 0) 'launcher PowerShell syntax must parse'
foreach ($requiredText in @(
    'Native library set is partial',
    'versions_sibling',
    'Reusable native directory is incomplete',
    'native_source = $nativeSource'
)) {
    Assert-True ($launcherText.Contains($requiredText)) "missing launcher contract: $requiredText"
}

$testBase = '<AUDIT_ROOT>\private-launcher-native-fallback-tests'
$caseRoot = Join-Path $testBase ('case-' + [Guid]::NewGuid().ToString('N'))
$sourceRoot = Join-Path $caseRoot 'source'
$clientRoot = Join-Path $caseRoot 'client'
$sourceVersions = Join-Path $sourceRoot 'versions'
$clientVersions = Join-Path $clientRoot 'versions'
$libraries = Join-Path $clientRoot 'libraries'
$resultPath = Join-Path $caseRoot 'launch-result.json'
$global:PrivateLauncherStubCalls = 0

try {
    New-Item -ItemType Directory -Path $sourceVersions, $clientRoot, $libraries -Force | Out-Null
    New-Item -ItemType Junction -Path $clientVersions -Target $sourceVersions | Out-Null

    $minecraftMetadata = [ordered]@{
        arguments = [ordered]@{ game = @() }
        assetIndex = [ordered]@{ id = '17' }
        libraries = @(
            [ordered]@{
                name = 'example:ordinary:1.0'
                downloads = [ordered]@{
                    artifact = [ordered]@{ path = 'example/ordinary/1.0/ordinary-1.0.jar' }
                }
            },
            [ordered]@{
                name = 'org.lwjgl:lwjgl:3.3.3:natives-windows'
                downloads = [ordered]@{
                    artifact = [ordered]@{ path = 'org/lwjgl/lwjgl/3.3.3/lwjgl-3.3.3-natives-windows.jar' }
                }
                rules = @([ordered]@{ action = 'allow'; os = [ordered]@{ name = 'windows' } })
            },
            [ordered]@{
                name = 'org.lwjgl:lwjgl-glfw:3.3.3:natives-windows'
                downloads = [ordered]@{
                    artifact = [ordered]@{ path = 'org/lwjgl/lwjgl-glfw/3.3.3/lwjgl-glfw-3.3.3-natives-windows.jar' }
                }
                rules = @([ordered]@{ action = 'allow'; os = [ordered]@{ name = 'windows' } })
            }
        )
    }
    $neoMetadata = [ordered]@{
        arguments = [ordered]@{ game = @() }
        libraries = @()
    }
    Write-Utf8NoBom (Join-Path $sourceVersions '1.21.1\1.21.1.json') `
        (($minecraftMetadata | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
    Write-Utf8NoBom (Join-Path $sourceVersions 'neoforge-21.1.241\neoforge-21.1.241.json') `
        (($neoMetadata | ConvertTo-Json -Depth 10) + [Environment]::NewLine)

    foreach ($path in @(
        (Join-Path $libraries 'example\ordinary\1.0\ordinary-1.0.jar'),
        (Join-Path $sourceVersions '1.21.1\1.21.1.jar'),
        (Join-Path $libraries 'io\github\zekerzhayard\ForgeWrapper\prism-2025-12-07\ForgeWrapper-prism-2025-12-07.jar'),
        (Join-Path $libraries 'net\neoforged\neoforge\21.1.241\neoforge-21.1.241-installer.jar')
    )) {
        Write-Utf8NoBom $path 'fixture'
    }

    $nativeRoot = Join-Path $sourceRoot 'natives'
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
    foreach ($relative in $requiredNativeFiles) {
        Write-Utf8NoBom (Join-Path $nativeRoot $relative) 'fixture'
    }

    function global:Start-Process {
        [CmdletBinding()]
        param(
            [string] $FilePath,
            [object[]] $ArgumentList,
            [string] $WorkingDirectory,
            [string] $RedirectStandardOutput,
            [string] $RedirectStandardError,
            [switch] $PassThru,
            [string] $WindowStyle
        )
        $global:PrivateLauncherStubCalls++
        return [pscustomobject]@{ Id = 424242 }
    }

    $result = & $launcherPath `
        -MinecraftRoot $clientRoot `
        -ServerAddress '127.0.0.1:12341' `
        -Username 'NativeProbe' `
        -Uuid '00000000-0000-0000-0000-000000009999' `
        -Java "$env:SystemRoot\System32\where.exe" `
        -MaximumMemoryMb 4096 `
        -ResultPath $resultPath

    Assert-True ($result.pid -eq 424242) 'stubbed process id was not returned'
    Assert-True ($result.native_source -eq 'versions_sibling') 'fallback source was not selected'
    Assert-True (
        [IO.Path]::GetFullPath([string]$result.native_directory) -eq [IO.Path]::GetFullPath($nativeRoot)
    ) 'fallback resolved outside the versions sibling native directory'
    Assert-True ($global:PrivateLauncherStubCalls -eq 1) 'the process stub must be called exactly once'
    Assert-True (Test-Path -LiteralPath $resultPath -PathType Leaf) 'launch result was not written'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $clientRoot 'natives'))) `
        'fallback must not mutate the client native directory'

    Remove-Item -LiteralPath (Join-Path $nativeRoot $requiredNativeFiles[0]) -Force
    $incompleteFailure = ''
    try {
        & $launcherPath `
            -MinecraftRoot $clientRoot `
            -ServerAddress '127.0.0.1:12341' `
            -Username 'NativeProbe' `
            -Uuid '00000000-0000-0000-0000-000000009999' `
            -Java "$env:SystemRoot\System32\where.exe" | Out-Null
    } catch { $incompleteFailure = $_.Exception.Message }
    Assert-True ($incompleteFailure.Contains('Reusable native directory is incomplete')) `
        'incomplete reusable natives must fail closed'
    Assert-True ($global:PrivateLauncherStubCalls -eq 1) 'incomplete natives must fail before process creation'

    Write-Utf8NoBom (Join-Path $nativeRoot $requiredNativeFiles[0]) 'fixture'
    Write-Utf8NoBom `
        (Join-Path $libraries 'org\lwjgl\lwjgl\3.3.3\lwjgl-3.3.3-natives-windows.jar') `
        'fixture'
    $partialFailure = ''
    try {
        & $launcherPath `
            -MinecraftRoot $clientRoot `
            -ServerAddress '127.0.0.1:12341' `
            -Username 'NativeProbe' `
            -Uuid '00000000-0000-0000-0000-000000009999' `
            -Java "$env:SystemRoot\System32\where.exe" | Out-Null
    } catch { $partialFailure = $_.Exception.Message }
    Assert-True ($partialFailure.Contains('Native library set is partial')) `
        'partial native artifacts must fail closed instead of mixing sources'
    Assert-True ($global:PrivateLauncherStubCalls -eq 1) 'partial native artifacts must fail before process creation'

    [pscustomobject]@{
        status = 'PASS'
        syntax = 'PASS'
        fallback = 'PASS'
        incomplete_rejected = 'PASS'
        partial_rejected = 'PASS'
        java_or_minecraft_started = $false
    } | ConvertTo-Json -Depth 4
} finally {
    Remove-Item -LiteralPath Function:\Start-Process -ErrorAction SilentlyContinue
    Remove-Variable -Name PrivateLauncherStubCalls -Scope Global -ErrorAction SilentlyContinue
    $resolvedCase = [IO.Path]::GetFullPath($caseRoot)
    $resolvedBase = [IO.Path]::GetFullPath($testBase).TrimEnd('\') + '\'
    if ($resolvedCase.StartsWith($resolvedBase, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedCase)) {
        Remove-Item -LiteralPath $resolvedCase -Recurse -Force
    }
}
