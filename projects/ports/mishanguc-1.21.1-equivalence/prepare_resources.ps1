param(
    [Parameter(Mandatory = $true)]
    [string]$SourceUnpacked,
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'

function Write-JsonFile {
    param([string]$Path, [object]$Value)
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $json = $Value | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($Path, $json + "`n", [System.Text.UTF8Encoding]::new($false))
}

function Copy-MatchingFiles {
    param([string]$SourceDir, [string]$DestinationDir, [string]$Filter)
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    Get-ChildItem -LiteralPath $SourceDir -File -Filter $Filter | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $DestinationDir $_.Name) -Force
    }
}

$resourceRoot = Join-Path $ProjectRoot 'src\main\resources'
$sourceAssets = Join-Path $SourceUnpacked 'assets\mishanguc'
$sourceData = Join-Path $SourceUnpacked 'data'

Copy-MatchingFiles -SourceDir (Join-Path $sourceAssets 'blockstates') -DestinationDir (Join-Path $resourceRoot 'assets\mishanguc\blockstates') -Filter '*pale_oak*.json'
Copy-MatchingFiles -SourceDir (Join-Path $sourceAssets 'models\block') -DestinationDir (Join-Path $resourceRoot 'assets\mishanguc\models\block') -Filter '*pale_oak*.json'
Copy-MatchingFiles -SourceDir (Join-Path $sourceAssets 'models\item') -DestinationDir (Join-Path $resourceRoot 'assets\mishanguc\models\item') -Filter '*pale_oak*.json'

$itemDefinitions = Get-ChildItem -LiteralPath (Join-Path $sourceAssets 'items') -File -Filter '*pale_oak*.json'
foreach ($definitionFile in $itemDefinitions) {
    $target = Join-Path $resourceRoot ('assets\mishanguc\models\item\' + $definitionFile.Name)
    if (Test-Path -LiteralPath $target) {
        continue
    }
    $definition = Get-Content -LiteralPath $definitionFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-JsonFile $target ([ordered]@{ parent = [string]$definition.model.model })
}

Copy-MatchingFiles -SourceDir (Join-Path $SourceUnpacked 'data\mishanguc\loot_table\blocks') -DestinationDir (Join-Path $resourceRoot 'data\mishanguc\loot_table\blocks') -Filter '*pale_oak*.json'

Get-ChildItem -LiteralPath (Join-Path $SourceUnpacked 'data\mishanguc\advancement\recipes') -Recurse -File -Filter '*pale_oak*.json' | ForEach-Object {
        $relative = $_.FullName.Substring((Join-Path $SourceUnpacked 'data\mishanguc\advancement\recipes').Length + 1)
        $target = Join-Path $resourceRoot (Join-Path 'data\mishanguc\advancement\recipes' $relative)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }

$recipeSource = Join-Path $SourceUnpacked 'data\mishanguc\recipe'
$recipeTarget = Join-Path $resourceRoot 'data\mishanguc\recipe'
New-Item -ItemType Directory -Force -Path $recipeTarget | Out-Null
Get-ChildItem -LiteralPath $recipeSource -File -Filter '*pale_oak*.json' | ForEach-Object {
    $recipe = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($recipe.ingredient -is [string]) {
        $recipe.ingredient = [ordered]@{ item = [string]$recipe.ingredient }
    }
    if ($null -ne $recipe.key) {
        foreach ($property in @($recipe.key.PSObject.Properties)) {
            if ($property.Value -is [string]) {
                $property.Value = [ordered]@{ item = [string]$property.Value }
            }
        }
    }
    Write-JsonFile (Join-Path $recipeTarget $_.Name) $recipe
}

Get-ChildItem -LiteralPath $sourceData -Recurse -File -Filter '*.json' | ForEach-Object {
    if ($_.FullName -notmatch '\\tags\\') {
        return
    }
    $document = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -eq $document.values) {
        return
    }
    $values = @($document.values | Where-Object {
        if ($_ -is [string]) {
            return $_ -match 'pale_oak'
        }
        return ([string]$_.id) -match 'pale_oak'
    })
    if ($values.Count -eq 0) {
        return
    }
    $relative = $_.FullName.Substring($sourceData.Length + 1)
    Write-JsonFile (Join-Path $resourceRoot (Join-Path 'data' $relative)) ([ordered]@{
        replace = $false
        values = $values
    })
}

Get-ChildItem -LiteralPath (Join-Path $sourceAssets 'lang') -File -Filter '*.json' | ForEach-Object {
    $sourceLanguage = Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    $backportLanguage = [ordered]@{}
    foreach ($entry in $sourceLanguage.PSObject.Properties) {
        if ($entry.Name -match 'pale_oak') {
            $backportLanguage[$entry.Name] = $entry.Value
        }
    }
    Write-JsonFile (Join-Path $resourceRoot ('assets\mishanguc\lang\' + $_.Name)) $backportLanguage
}

$blockStateCount = (Get-ChildItem -LiteralPath (Join-Path $resourceRoot 'assets\mishanguc\blockstates') -File).Count
$itemModelCount = (Get-ChildItem -LiteralPath (Join-Path $resourceRoot 'assets\mishanguc\models\item') -File).Count
$recipeCount = (Get-ChildItem -LiteralPath $recipeTarget -File).Count
$lootCount = (Get-ChildItem -LiteralPath (Join-Path $resourceRoot 'data\mishanguc\loot_table\blocks') -File).Count
$advancementCount = (Get-ChildItem -LiteralPath (Join-Path $resourceRoot 'data\mishanguc\advancement\recipes') -Recurse -File).Count

if ($blockStateCount -ne 37 -or $itemModelCount -ne 17 -or $recipeCount -ne 16 -or
        $lootCount -ne 37 -or $advancementCount -ne 16) {
    throw "Unexpected resource counts: blockstates=$blockStateCount itemModels=$itemModelCount recipes=$recipeCount loot=$lootCount advancements=$advancementCount"
}

Write-Output "Prepared Mishang pale oak resources: 37 blockstates, 17 item models, 16 recipes, 37 loot tables, 16 advancements"
