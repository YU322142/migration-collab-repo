param(
    [string]$SourceJar = 'D:\Trans\20260807\mods\kaleidoscope_end-1.0.11-fabric+mc1.21.11.jar',
    [string]$DestinationRoot = 'D:\Trans\migration-audit-work\KaleidoscopeEnd-1.21.1-equivalence\src\main\resources'
)

$expectedSourceSha256 = 'CE9CC96296DA26EF2D604246D3FD7BFA618EA83145B81D1FB4E420B18D6DD619'
$sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SourceJar).Hash
if ($sourceHash -ne $expectedSourceSha256) {
    throw "Unexpected source JAR SHA256: $sourceHash"
}

$entries = @(
    'assets/kaleidoscope_end/textures/item/endermite_egg.png',
    'assets/kaleidoscope_end/textures/gui/sprites/container/enchanting_table/level_1.png',
    'assets/kaleidoscope_end/textures/gui/sprites/container/enchanting_table/level_1_disabled.png',
    'assets/kaleidoscope_end/textures/gui/sprites/container/enchanting_table/level_2.png',
    'assets/kaleidoscope_end/textures/gui/sprites/container/enchanting_table/level_2_disabled.png',
    'assets/kaleidoscope_end/textures/gui/sprites/container/enchanting_table/level_3.png',
    'assets/kaleidoscope_end/textures/gui/sprites/container/enchanting_table/level_3_disabled.png'
)

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $SourceJar))
try {
    foreach ($entryName in $entries) {
        $entry = $archive.GetEntry($entryName)
        if ($null -eq $entry) {
            throw "Missing source entry: $entryName"
        }
        $destination = Join-Path $DestinationRoot ($entryName -replace '/', '\\')
        $destinationDirectory = Split-Path -Parent $destination
        New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null
        $input = $entry.Open()
        $output = [System.IO.File]::Open($destination, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        try {
            $input.CopyTo($output)
        } finally {
            $output.Dispose()
            $input.Dispose()
        }
        $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
        if ([string]::IsNullOrWhiteSpace($actual)) {
            throw "Could not hash restored asset: $destination"
        }
        Write-Output "$entryName -> $destination`t$actual"
    }
} finally {
    $archive.Dispose()
}
