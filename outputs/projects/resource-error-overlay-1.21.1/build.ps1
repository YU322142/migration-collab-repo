$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$resourceRoot = Join-Path $projectRoot "src\main\resources"
$outputDir = Join-Path $projectRoot "build\libs"
$outputJar = Join-Path $outputDir "migration-resource-overlay-1.1.0+mc1.21.1.jar"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
if (Test-Path -LiteralPath $outputJar) {
    Remove-Item -LiteralPath $outputJar -Force
}

& jar --create --date=2020-01-01T00:00:00Z --file $outputJar -C $resourceRoot .
if ($LASTEXITCODE -ne 0) {
    throw "jar failed with exit code $LASTEXITCODE"
}

Get-FileHash -Algorithm SHA256 -LiteralPath $outputJar
