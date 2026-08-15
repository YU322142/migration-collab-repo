[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputJar,

    [string]$OriginalJar = 'D:\Trans\migration-audit-work\mechanomania-matched-client-attempt9-20260814\mods\yuushya-1.21.0-neoforge-2.3.0.jar',

    [string]$JarTool = 'D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\java\java-runtime-delta\bin\jar.exe'
)

$ErrorActionPreference = 'Stop'

$expectedOriginalSha256 = 'C410C51E1ECDD9D3FF55EB34B84D71DA761A8990EC0993A766C9BA40E8C360E8'
$expectedPatchedSha256 = '31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D'
$expectedPatchedBytes = 28197402
$patchRoot = Join-Path $PSScriptRoot 'patch-root'

$patchedEntries = @(
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/categories/mod_functions.json',
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_basic.json',
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_basic_adjust.json',
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_block_layer.json',
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_special.json',
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/building_techniques/bt_survival_gameplay.json',
    'assets/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/building_techniques/bt_survival_building_material.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/categories/mod_functions.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_basic.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_basic_adjust.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_block_layer.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/mod_functions/mf_block_modeling_special.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/building_techniques/bt_survival_gameplay.json',
    'data/yuushya/patchouli_books/yuushya_guidebook/en_us/entries/building_techniques/bt_survival_building_material.json'
)

if (-not (Test-Path -LiteralPath $OriginalJar -PathType Leaf)) {
    throw "Original JAR not found: $OriginalJar"
}
if (-not (Test-Path -LiteralPath $JarTool -PathType Leaf)) {
    throw "jar.exe not found: $JarTool"
}
if (Test-Path -LiteralPath $OutputJar) {
    throw "Refusing to overwrite existing output: $OutputJar"
}

$originalSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $OriginalJar).Hash
if ($originalSha256 -ne $expectedOriginalSha256) {
    throw "Original JAR SHA-256 mismatch: $originalSha256"
}

foreach ($entry in $patchedEntries) {
    $source = Join-Path $patchRoot $entry
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Patch source missing: $source"
    }
}

$outputParent = Split-Path -Parent ([System.IO.Path]::GetFullPath($OutputJar))
New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
Copy-Item -LiteralPath $OriginalJar -Destination $OutputJar

$arguments = @('--update', "--file=$OutputJar")
foreach ($entry in $patchedEntries) {
    $arguments += @('-C', $patchRoot, $entry)
}

& $JarTool @arguments
if ($LASTEXITCODE -ne 0) {
    throw "jar.exe update failed with exit code $LASTEXITCODE"
}

$outputInfo = Get-Item -LiteralPath $OutputJar
$patchedSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $OutputJar).Hash
if ($outputInfo.Length -ne $expectedPatchedBytes) {
    throw "Patched JAR size mismatch: $($outputInfo.Length)"
}
if ($patchedSha256 -ne $expectedPatchedSha256) {
    throw "Patched JAR SHA-256 mismatch: $patchedSha256"
}

[ordered]@{
    status = 'PASS'
    output = $outputInfo.FullName
    bytes = $outputInfo.Length
    sha256 = $patchedSha256
    patched_entries = $patchedEntries.Count
} | ConvertTo-Json -Depth 3
