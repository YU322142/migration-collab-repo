param(
    [Parameter(Mandatory = $true)]
    [string]$RecipeRoot
)

$ErrorActionPreference = 'Stop'

function Convert-ItemIngredient($ingredient) {
    if ($ingredient -is [string]) {
        return [ordered]@{ item = $ingredient }
    }
    return $ingredient
}

$files = Get-ChildItem -LiteralPath $RecipeRoot -Recurse -File -Filter '*.json'
foreach ($file in $files) {
    $recipe = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json

    if ($recipe.PSObject.Properties.Name -contains 'ingredients') {
        $converted = @($recipe.ingredients | ForEach-Object { Convert-ItemIngredient $_ })
        $recipe.ingredients = [object[]]$converted
    }

    if ($recipe.PSObject.Properties.Name -contains 'ingredient') {
        $converted = Convert-ItemIngredient $recipe.ingredient
        if ($recipe.type -eq 'minecraft:smoking') {
            $recipe.ingredient = $converted
        } else {
            $recipe.PSObject.Properties.Remove('ingredient')
            $recipe | Add-Member -NotePropertyName ingredients -NotePropertyValue ([object[]]@($converted))
        }
    }

    if ($recipe.PSObject.Properties.Name -contains 'fluid_ingredients') {
        $ingredients = @($recipe.ingredients)
        foreach ($fluid in $recipe.fluid_ingredients) {
            $sourceAmount = [long]$fluid.amount
            if ($sourceAmount % 81 -ne 0) {
                throw "Fluid amount is not exactly convertible to mB: $($file.FullName): $sourceAmount"
            }
            $ingredients += [ordered]@{
                type   = 'neoforge:single'
                amount = [long]($sourceAmount / 81)
                fluid  = [string]$fluid.fluid
            }
        }
        $recipe.ingredients = [object[]]$ingredients
        $recipe.PSObject.Properties.Remove('fluid_ingredients')
    }

    $json = $recipe | ConvertTo-Json -Depth 32
    Set-Content -LiteralPath $file.FullName -Value $json -Encoding UTF8
}

Write-Output "Converted $($files.Count) NERFAD recipes."
