param(
    [Parameter(Mandatory = $true)]
    [string]$SourceMain,
    [Parameter(Mandatory = $true)]
    [string]$OfficialData,
    [Parameter(Mandatory = $true)]
    [string]$ProjectResources
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Ensure-Parent([string]$Path) {
    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

function Write-Json([string]$RelativePath, $Value) {
    $path = Join-Path $ProjectResources $RelativePath
    Ensure-Parent $path
    $json = ConvertTo-Json -InputObject $Value -Depth 100
    [System.IO.File]::WriteAllText($path, $json + "`n", $utf8NoBom)
}

function Copy-Resource([string]$SourceRelativePath, [string]$TargetRelativePath) {
    $source = Join-Path $SourceMain $SourceRelativePath
    $target = Join-Path $ProjectResources $TargetRelativePath
    Ensure-Parent $target
    Copy-Item -LiteralPath $source -Destination $target -Force
}

function Copy-ResourceTree([string]$SourceRelativePath, [string]$TargetRelativePath) {
    $source = Join-Path $SourceMain $SourceRelativePath
    $target = Join-Path $ProjectResources $TargetRelativePath
    if (-not (Test-Path -LiteralPath $target)) {
        New-Item -ItemType Directory -Path $target -Force | Out-Null
    }
    Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
}

# Client assets: only paths referenced by the Nautilus implementation.
Copy-ResourceTree 'resources\assets\minecraft\textures\entity\nautilus' 'assets\minecraft\textures\entity\nautilus'
Copy-Resource 'resources\assets\minecraft\textures\gui\container\nautilus.png' 'assets\minecraft\textures\gui\container\nautilus.png'
Copy-Resource 'resources\assets\minecraft\textures\mob_effect\breath_of_the_nautilus.png' 'assets\minecraft\textures\mob_effect\breath_of_the_nautilus.png'

$itemNames = @(
    'copper_nautilus_armor',
    'iron_nautilus_armor',
    'golden_nautilus_armor',
    'diamond_nautilus_armor',
    'netherite_nautilus_armor',
    'nautilus_spawn_egg',
    'zombie_nautilus_spawn_egg'
)
foreach ($name in $itemNames) {
    Copy-Resource ("resources\assets\minecraft\textures\item\$name.png") ("assets\minecraft\textures\item\$name.png")
    Copy-Resource ("generated\assets\minecraft\models\item\$name.json") ("assets\minecraft\models\item\$name.json")
}

foreach ($soundDir in @('baby_nautilus', 'nautilus', 'zombie_nautilus')) {
    Copy-ResourceTree ("resources\assets\minecraft\sounds\mob\$soundDir") ("assets\minecraft\sounds\mob\$soundDir")
}

$allSounds = Get-Content -LiteralPath (Join-Path $SourceMain 'resources\assets\minecraft\sounds.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$sounds = [ordered]@{}
foreach ($property in $allSounds.PSObject.Properties) {
    if ($property.Name -match 'nautilus') {
        $sounds[$property.Name] = $property.Value
    }
}
Write-Json 'assets\minecraft\sounds.json' $sounds

$language = [ordered]@{}
foreach ($languagePath in @(
    'resources\assets\minecraft\lang\en_us.json',
    'generated\assets\vanillabackport\lang\en_us.json'
)) {
    $sourceLanguage = Get-Content -LiteralPath (Join-Path $SourceMain $languagePath) -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($property in $sourceLanguage.PSObject.Properties) {
        if ($property.Name -match 'nautilus') {
            $language[$property.Name] = $property.Value
        }
    }
}
Write-Json 'assets\nautilus_equivalence\lang\en_us.json' $language

# Entity loot and the namespace-owned tags used directly by code.
foreach ($entity in @('nautilus', 'zombie_nautilus')) {
    Copy-Resource ("generated\data\minecraft\loot_table\entities\$entity.json") ("data\minecraft\loot_table\entities\$entity.json")
}
foreach ($tag in @('nautilus_bucket_food', 'nautilus_food', 'nautilus_taming_items')) {
    Copy-Resource ("generated\data\minecraft\tags\item\$tag.json") ("data\minecraft\tags\item\$tag.json")
}
Copy-Resource 'generated\data\minecraft\tags\entity_type\nautilus_hostiles.json' 'data\minecraft\tags\entity_type\nautilus_hostiles.json'
foreach ($tag in @('spawns_coral_variant_zombie_nautilus', 'spawns_nautilus', 'spawns_nautilus_frequently')) {
    Copy-Resource ("generated\data\minecraft\tags\worldgen\biome\$tag.json") ("data\minecraft\tags\worldgen\biome\$tag.json")
}

# Append only the newly introduced IDs; tag files default to replace=false.
$entityTagAdditions = [ordered]@{
    'aquatic' = @('minecraft:nautilus', 'minecraft:zombie_nautilus')
    'not_scary_for_pufferfish' = @('minecraft:nautilus', 'minecraft:zombie_nautilus')
    'zombies' = @('minecraft:zombie_nautilus')
    'can_wear_nautilus_armor' = @('minecraft:nautilus', 'minecraft:zombie_nautilus')
    'can_equip_saddle' = @('minecraft:nautilus', 'minecraft:zombie_nautilus')
    'can_breathe_under_water' = @('minecraft:nautilus')
    'cannot_be_pushed_onto_boats' = @('minecraft:nautilus', 'minecraft:zombie_nautilus')
    'burn_in_daylight' = @('minecraft:zombie_nautilus')
}
foreach ($entry in $entityTagAdditions.GetEnumerator()) {
    Write-Json ("data\minecraft\tags\entity_type\$($entry.Key).json") ([ordered]@{ values = $entry.Value })
}
Write-Json 'data\minecraft\tags\item\piglin_loved.json' ([ordered]@{ values = @('minecraft:golden_nautilus_armor') })

# Match the official cold/frequent ocean weights. Spawn placement bounds live in Java.
Write-Json 'data\nautilus_equivalence\neoforge\biome_modifier\add_nautilus.json' ([ordered]@{
    type = 'neoforge:add_spawns'
    biomes = '#minecraft:spawns_nautilus'
    spawners = [ordered]@{
        type = 'minecraft:nautilus'
        weight = 2
        minCount = 1
        maxCount = 1
    }
})
Write-Json 'data\nautilus_equivalence\neoforge\biome_modifier\add_nautilus_frequently.json' ([ordered]@{
    type = 'neoforge:add_spawns'
    biomes = '#minecraft:spawns_nautilus_frequently'
    spawners = [ordered]@{
        type = 'minecraft:nautilus'
        weight = 5
        minCount = 1
        maxCount = 1
    }
})

# Recipes compatible with 1.21.1. Copper recycling cannot be represented because
# minecraft:copper_nugget does not exist in this target registry.
Copy-Resource 'generated\data\minecraft\recipe\netherite_nautilus_armor_smithing.json' 'data\minecraft\recipe\netherite_nautilus_armor_smithing.json'
Copy-Resource 'generated\data\minecraft\advancement\recipes\combat\netherite_nautilus_armor_smithing.json' 'data\minecraft\advancement\recipes\combat\netherite_nautilus_armor_smithing.json'

foreach ($recipeName in @(
    'iron_nugget_from_smelting',
    'iron_nugget_from_blasting',
    'gold_nugget_from_smelting',
    'gold_nugget_from_blasting'
)) {
    $recipe = Get-Content -LiteralPath (Join-Path $OfficialData "recipe\$recipeName.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $recipe.ingredient = @($recipe.ingredient | Where-Object { $_ -notmatch '_spear$' } | ForEach-Object { [ordered]@{ item = $_ } })
    Write-Json ("data\minecraft\recipe\$recipeName.json") $recipe

    $advancement = Get-Content -LiteralPath (Join-Path $OfficialData "advancement\recipes\misc\$recipeName.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $spearCriteria = @($advancement.criteria.PSObject.Properties | Where-Object { $_.Name -match '_spear$' } | ForEach-Object Name)
    foreach ($criterion in $spearCriteria) {
        $advancement.criteria.PSObject.Properties.Remove($criterion)
    }
    $requirementGroup = [object[]]@($advancement.requirements[0] | Where-Object { $_ -notmatch '_spear$' })
    $requirementGroups = [object[]]::new(1)
    $requirementGroups[0] = $requirementGroup
    $advancement.requirements = $requirementGroups
    Write-Json ("data\minecraft\advancement\recipes\misc\$recipeName.json") $advancement
}

# 1.21.1 and 1.21.11 definitions differ only by this Nautilus criterion/requirement.
$bredAllAnimalsTarget = Join-Path $ProjectResources 'data\minecraft\advancement\husbandry\bred_all_animals.json'
Ensure-Parent $bredAllAnimalsTarget
Copy-Item -LiteralPath (Join-Path $OfficialData 'advancement\husbandry\bred_all_animals.json') `
    -Destination $bredAllAnimalsTarget -Force

Write-Output "Nautilus resources assembled at $ProjectResources"
