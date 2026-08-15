param(
    [Parameter(Mandatory = $true)][string]$NeoRepo,
    [Parameter(Mandatory = $true)][string]$Fabric1211Repo,
    [Parameter(Mandatory = $true)][string]$Actual12111Root
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)

function Resolve-Directory([string]$Path, [string]$Label) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-Path -LiteralPath $resolved -PathType Container)) {
        throw "$Label is not a directory: $resolved"
    }
    return $resolved.TrimEnd('\')
}

function Copy-FileChecked([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required source file is missing: $Source"
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-Tree([string]$Source, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Required source directory is missing: $Source"
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($Source.Length).TrimStart('\')
        Copy-FileChecked $_.FullName (Join-Path $Destination $relative)
    }
}

function Sync-MainAssetTree([string]$Source, [string]$MainDestination, [string]$GeneratedAssets) {
    New-Item -ItemType Directory -Path $MainDestination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Recurse -File | ForEach-Object {
        $relative = $_.FullName.Substring($Source.Length).TrimStart('\')
        $mainFile = Join-Path $MainDestination $relative
        $generatedFile = Join-Path $GeneratedAssets $relative
        if (Test-Path -LiteralPath $generatedFile -PathType Leaf) {
            # The baseline build has no cross-source duplicates. A main copy at this
            # path was introduced by an earlier sync and must not shadow generated data.
            if (Test-Path -LiteralPath $mainFile -PathType Leaf) {
                Remove-Item -LiteralPath $mainFile -Force
            }
        } else {
            Copy-FileChecked $_.FullName $mainFile
        }
    }
}

function Read-Json([string]$Path) {
    return ([IO.File]::ReadAllText($Path, $utf8) | ConvertFrom-Json)
}

function Write-Json([string]$Path, $Value) {
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $json = $Value | ConvertTo-Json -Depth 100
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, $utf8)
}

function Merge-Properties([System.Collections.Specialized.OrderedDictionary]$Target, $Source) {
    if ($null -eq $Source) {
        return
    }
    foreach ($property in $Source.PSObject.Properties) {
        $Target[$property.Name] = $property.Value
    }
}

function Convert-Ingredient($Value) {
    if ($Value -is [string]) {
        if ($Value.StartsWith('#')) {
            return [pscustomobject][ordered]@{ tag = $Value.Substring(1) }
        }
        return [pscustomobject][ordered]@{ item = $Value }
    }
    return $Value
}

function Convert-Recipe($Recipe) {
    foreach ($name in @('ingredient', 'carrier', 'template', 'base', 'addition')) {
        $property = $Recipe.PSObject.Properties[$name]
        if ($null -ne $property) {
            $property.Value = Convert-Ingredient $property.Value
        }
    }

    $ingredients = $Recipe.PSObject.Properties['ingredients']
    if ($null -ne $ingredients) {
        $ingredients.Value = @($ingredients.Value | ForEach-Object { Convert-Ingredient $_ })
    }

    $key = $Recipe.PSObject.Properties['key']
    if ($null -ne $key) {
        foreach ($entry in $key.Value.PSObject.Properties) {
            $entry.Value = Convert-Ingredient $entry.Value
        }
    }

    if ([string]$Recipe.type -eq 'create:cutting') {
        $singleIngredient = $Recipe.PSObject.Properties['ingredient']
        if ($null -eq $singleIngredient -or $null -ne $Recipe.PSObject.Properties['ingredients']) {
            throw 'Expected a singular ingredient in a 1.21.11 Create cutting recipe'
        }
        $convertedIngredient = $singleIngredient.Value
        $Recipe.PSObject.Properties.Remove('ingredient')
        $Recipe | Add-Member -NotePropertyName 'ingredients' -NotePropertyValue @($convertedIngredient)
    }

    $fabricConditions = $Recipe.PSObject.Properties['fabric:load_conditions']
    if ($null -ne $fabricConditions) {
        $neoConditions = @()
        foreach ($condition in @($fabricConditions.Value)) {
            $values = @($condition.values)
            if ($values.Count -ne 1 -or
                    $condition.condition -notin @('fabric:any_mods_loaded', 'fabric:all_mods_loaded')) {
                throw "Unsupported Fabric recipe condition: $($condition | ConvertTo-Json -Compress)"
            }
            $neoConditions += [pscustomobject][ordered]@{
                type = 'neoforge:mod_loaded'
                modid = [string]$values[0]
            }
        }
        $Recipe.PSObject.Properties.Remove('fabric:load_conditions')
        $Recipe | Add-Member -NotePropertyName 'neoforge:conditions' -NotePropertyValue $neoConditions
    }
    return $Recipe
}

$neo = Resolve-Directory $NeoRepo 'NeoForge repository'
$fabric = Resolve-Directory $Fabric1211Repo 'Fabric 1.21.1 repository'
$actual = Resolve-Directory $Actual12111Root 'Extracted 1.21.11 JAR'
if ((Split-Path -Leaf $neo) -ne 'KaleidoscopeCookery-1.21.1-neoforge') {
    throw "Refusing unexpected NeoForge repository: $neo"
}

$mainResources = Join-Path $neo 'src\main\resources'
$generatedResources = Join-Path $neo 'src\generated\resources'
$targetAssets = Join-Path $mainResources 'assets\kaleidoscope_cookery'
$generatedAssets = Join-Path $generatedResources 'assets\kaleidoscope_cookery'
$fabricAssets = Join-Path $fabric 'src\main\resources\assets\kaleidoscope_cookery'
$actualAssets = Join-Path $actual 'assets\kaleidoscope_cookery'
$actualData = Join-Path $actual 'data'

# Preserve loader-side translations before refreshing loader-neutral 1.21.1 assets.
$originalLanguages = @{}
$originalLangDir = Join-Path $targetAssets 'lang'
if (Test-Path -LiteralPath $originalLangDir) {
    Get-ChildItem -LiteralPath $originalLangDir -File -Filter '*.json' | ForEach-Object {
        $originalLanguages[$_.Name] = Read-Json $_.FullName
    }
}

Sync-MainAssetTree $fabricAssets $targetAssets $generatedAssets

# These assets were introduced after the 1.21.1 Fabric bridge, but their block/model
# schema is unchanged. Copy only the explicitly audited portable files.
$portableFiles = @(
    'blockstates\chair_pale_oak.json',
    'blockstates\cook_stool_pale_oak.json',
    'blockstates\table_pale_oak.json',
    'models\block\chair\pale_oak.json',
    'models\block\cook_stool\pale_oak.json',
    'models\block\table\pale_oak_left.json',
    'models\block\table\pale_oak_left_rot.json',
    'models\block\table\pale_oak_middle.json',
    'models\block\table\pale_oak_middle_rot.json',
    'models\block\table\pale_oak_right.json',
    'models\block\table\pale_oak_right_rot.json',
    'models\block\table\pale_oak_single.json',
    'models\item\chair_pale_oak.json',
    'models\item\cook_stool_pale_oak.json',
    'models\item\table_pale_oak.json',
    'models\item\copper_kitchen_knife.json',
    'textures\block\chair\pale_oak.png',
    'textures\block\cook_stool\pale_oak.png',
    'textures\block\table\pale_oak.png',
    'textures\item\copper_kitchen_knife.png'
)
foreach ($relative in $portableFiles) {
    Copy-FileChecked (Join-Path $actualAssets $relative) (Join-Path $targetAssets $relative)
}

# Merge flat language maps. Actual 1.21.11 wording wins, while NeoForge-only keys survive.
$languageNames = @($originalLanguages.Keys)
$languageNames += @(Get-ChildItem -LiteralPath (Join-Path $fabricAssets 'lang') -File -Filter '*.json' | ForEach-Object Name)
$languageNames += @(Get-ChildItem -LiteralPath (Join-Path $actualAssets 'lang') -File -Filter '*.json' | ForEach-Object Name)
$languageNames = @($languageNames | Sort-Object -Unique)
foreach ($name in $languageNames) {
    $merged = New-Object System.Collections.Specialized.OrderedDictionary
    if ($originalLanguages.ContainsKey($name)) {
        Merge-Properties $merged $originalLanguages[$name]
    }
    $fabricLanguage = Join-Path (Join-Path $fabricAssets 'lang') $name
    if (Test-Path -LiteralPath $fabricLanguage) {
        Merge-Properties $merged (Read-Json $fabricLanguage)
    }
    $actualLanguage = Join-Path (Join-Path $actualAssets 'lang') $name
    if (Test-Path -LiteralPath $actualLanguage) {
        Merge-Properties $merged (Read-Json $actualLanguage)
    }
    Write-Json (Join-Path (Join-Path $targetAssets 'lang') $name) $merged
}

# Tag JSON is compatible across these versions. Copy the actual tag trees so new
# and legacy Common Tags aliases coexist, including the copper knife membership.
Get-ChildItem -LiteralPath $actualData -Directory | ForEach-Object {
    $tagRoot = Join-Path $_.FullName 'tags'
    if (Test-Path -LiteralPath $tagRoot -PathType Container) {
        Copy-Tree $tagRoot (Join-Path $generatedResources ("data\{0}\tags" -f $_.Name))
    }
}

# Cookery loot tables use the same schema; NeoForge's existing global loot modifiers
# continue to attach entity tables, avoiding replacement of vanilla entity tables.
Copy-Tree (Join-Path $actualData 'kaleidoscope_cookery\loot_table') `
        (Join-Path $generatedResources 'data\kaleidoscope_cookery\loot_table')

# Recipe-book advancements are schema-identical. Copy every namespace that supplies them.
Get-ChildItem -LiteralPath $actualData -Directory | ForEach-Object {
    $advancementRoot = Join-Path $_.FullName 'advancement'
    if (Test-Path -LiteralPath $advancementRoot -PathType Container) {
        Copy-Tree $advancementRoot (Join-Path $generatedResources ("data\{0}\advancement" -f $_.Name))
    }
}

$recipeFiles = @(Get-ChildItem -LiteralPath $actualData -Recurse -File -Filter '*.json' |
        Where-Object { $_.FullName -match '\\recipe\\' })
if ($recipeFiles.Count -ne 699) {
    throw "Expected 699 source recipes, found $($recipeFiles.Count)"
}

$writtenRecipes = 0
$skippedMainRecipes = 0
foreach ($source in $recipeFiles) {
    $relative = $source.FullName.Substring($actualData.Length).TrimStart('\')
    $mainDestination = Join-Path (Join-Path $mainResources 'data') $relative
    if (Test-Path -LiteralPath $mainDestination -PathType Leaf) {
        $skippedMainRecipes++
        continue
    }
    $destination = Join-Path (Join-Path $generatedResources 'data') $relative
    $recipe = Convert-Recipe (Read-Json $source.FullName)
    Write-Json $destination $recipe
    $null = Read-Json $destination
    $writtenRecipes++
}

if ($writtenRecipes -ne 697 -or $skippedMainRecipes -ne 2) {
    throw "Unexpected recipe output: written=$writtenRecipes skipped-main=$skippedMainRecipes"
}

Write-Output "Assets refreshed from 1.21.1 bridge: $targetAssets"
Write-Output "Portable 1.21.11 assets copied: $($portableFiles.Count)"
Write-Output "Languages merged: $($languageNames.Count)"
Write-Output "Recipes converted: $writtenRecipes; preserved main recipes: $skippedMainRecipes"
