param(
    [Parameter(Mandatory = $true)][string]$SourceServer,
    [Parameter(Mandatory = $true)][string]$DestinationServer,
    [Parameter(Mandatory = $true)][string]$BarchedJar,
    [Parameter(Mandatory = $true)][string]$CookeryJar,
    [int]$Port = 10691
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$source = (Resolve-Path -LiteralPath $SourceServer).Path.TrimEnd('\')
$barched = (Resolve-Path -LiteralPath $BarchedJar).Path
$cookery = (Resolve-Path -LiteralPath $CookeryJar).Path
$destination = [IO.Path]::GetFullPath($DestinationServer).TrimEnd('\')

if ((Split-Path -Leaf $source) -ne 'fullstack-create-6.0.10-smoke1') {
    throw "Refusing unexpected source server: $source"
}
if ((Split-Path -Leaf $destination) -notmatch '^cookery-fullstack-smoke[0-9]+$') {
    throw "Refusing unexpected destination server: $destination"
}
if (Test-Path -LiteralPath $destination) {
    throw "Destination already exists: $destination"
}

New-Item -ItemType Directory -Path $destination | Out-Null
foreach ($name in @('eula.txt', 'server.properties', 'user_jvm_args.txt', 'run.bat',
        'banned-ips.json', 'banned-players.json', 'ops.json', 'usercache.json', 'whitelist.json')) {
    $sourceFile = Join-Path $source $name
    if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
        Copy-Item -LiteralPath $sourceFile -Destination (Join-Path $destination $name)
    }
}
foreach ($name in @('config', 'defaultconfigs')) {
    $sourceDirectory = Join-Path $source $name
    if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
        Copy-Item -LiteralPath $sourceDirectory -Destination (Join-Path $destination $name) -Recurse
    }
}

$sourceLibraries = Get-Item -LiteralPath (Join-Path $source 'libraries')
if ($sourceLibraries.LinkType -ne 'Junction' -or @($sourceLibraries.Target).Count -ne 1) {
    throw 'Expected the source libraries directory to be a single junction'
}
New-Item -ItemType Junction -Path (Join-Path $destination 'libraries') `
        -Target ([string]@($sourceLibraries.Target)[0]) | Out-Null

$destinationMods = Join-Path $destination 'mods'
New-Item -ItemType Directory -Path $destinationMods | Out-Null
Get-ChildItem -LiteralPath (Join-Path $source 'mods') -File -Filter '*.jar' |
        Where-Object { $_.Name -notmatch '^(barched-|kaleidoscopecookery-)' } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $destinationMods }
Copy-Item -LiteralPath $barched -Destination (Join-Path $destinationMods (Split-Path -Leaf $barched))
Copy-Item -LiteralPath $cookery -Destination (Join-Path $destinationMods (Split-Path -Leaf $cookery))

$propertiesPath = Join-Path $destination 'server.properties'
$properties = [IO.File]::ReadAllText($propertiesPath)
foreach ($entry in ([ordered]@{
        'server-port' = $Port
        'query.port' = $Port
        'rcon.port' = ($Port + 1)
        'enable-rcon' = 'true'
        'rcon.password' = 'cookery-smoke-local-only'
        'level-name' = 'world'
        'motd' = 'Cookery migration full-stack smoke'
    }).GetEnumerator()) {
    $pattern = '(?m)^' + [regex]::Escape([string]$entry.Key) + '=.*$'
    if (-not [regex]::IsMatch($properties, $pattern)) {
        throw "Missing server property: $($entry.Key)"
    }
    $properties = [regex]::Replace($properties, $pattern,
            ([string]$entry.Key) + '=' + ([string]$entry.Value), 1)
}
[IO.File]::WriteAllText($propertiesPath, $properties, $utf8)

Write-Output "Prepared isolated server: $destination"
Write-Output "Port: $Port"
Write-Output "Mods: $((Get-ChildItem -LiteralPath $destinationMods -File -Filter '*.jar').Count)"
