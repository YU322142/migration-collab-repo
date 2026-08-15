## Tags

### Enchantment

* `create_enchantment_industry:blaze_enchanter/enchanting` for enchantments available to regular Blaze Enchanter enchanting. It includes `minecraft:in_enchanting_table`.
* `create_enchantment_industry:blaze_enchanter/enchanting_exclusive` for enchantments that should only appear in regular Blaze Enchanter enchanting.
* `create_enchantment_industry:blaze_enchanter/super_enchanting` for enchantments available to Super Enchanting. It includes `create_enchantment_industry:blaze_enchanter/super_enchanting_exclusive` and `minecraft:in_enchanting_table`, and excludes `create_enchantment_industry:blaze_enchanter/enchanting_exclusive`.
* `create_enchantment_industry:blaze_enchanter/super_enchanting_exclusive` for enchantments that should only appear in Super Enchanting. The generated tag includes `minecraft:treasure` and excludes `minecraft:curse`.
* `create_enchantment_industry:printer/deny` for enchantments that the Printer should not copy onto Enchanted Books.

### Fluid

* `create_enchantment_industry:infusing/ingredients` for fluids that can power Infuser processing when Apothic Enchanting integration is active. The generated tag contains Liquid Experience.
* `create_enchantment_industry:fan_processing_catalysts/salvaging` for fluid Bulk Salvaging catalysts when Apotheosis integration is active. The generated tag optionally includes Infused Dragon's Breath.
* `c:dragon_breath` includes Infused Dragon's Breath when Apothic Enchanting integration is active.
* `create:bottomless/deny` includes Liquid Experience and optional Apotheosis integration essence fluids.

### Item

* `c:buckets` includes Bucket o' Enchanting.
* `c:nuggets` includes Nugget of Super Experience.
* `c:storage_blocks` includes Block of Super Experience.
* `create:upright_on_belt` includes Cake Base o' Enchanting, Cake o' Enchanting, and optional Apothic Enchanting Infused Breath.
* `create_enchantment_industry:blaze_composer/super_activators` for items that unlock Blaze Composer Super charging. The generated tag optionally includes `apotheosis:mythic_material`.

### Block

* `create:fan_transparent` includes Blaze Enchanter, Blaze Forger, and Classic Blaze Enchanter.
* `create:fan_processing_catalysts/smoking` includes Blaze Enchanter, Blaze Forger, and Classic Blaze Enchanter.
* `create_enchantment_industry:fan_processing_catalysts/salvaging` for block Bulk Salvaging catalysts when Apotheosis integration is active.
* `minecraft:mineable/pickaxe` includes Create: Enchantment Industry machinery and optional integration machinery.
* `minecraft:beacon_base_blocks` includes Block of Super Experience.
* `c:lightning_rods` can be used by datapacks and integrations that need to treat compatible blocks as lightning rods.

### Sable Block (normally you won't need these)

When the Sable integration source set is active, the mod provides Sable physics grouping tags:

* `create_enchantment_industry:sable/light_machines`
* `create_enchantment_industry:sable/medium_machines`
* `create_enchantment_industry:sable/heavy_machines`
* `create_enchantment_industry:sable/super_heavy_machines`

## Data Maps

### Experience Fuel

`create_enchantment_industry:experience_fuel` is an item data map used by the Blaze Experience Workstation and related experience conversion logic.

Entries can be written as a positive integer for normal experience fuel:

```json
{
  "values": {
    "examplemod:experience_shard": 3
  }
}
```

Entries can also use the full object form:

```json
{
  "values": {
    "examplemod:condensed_experience": {
      "experience": 27,
      "special": true,
      "using_convert_to": {
        "id": "minecraft:glass_bottle"
      }
    }
  }
}
```

Fields:

* `experience` is the amount of Liquid Experience represented by one item.
* `special` marks the fuel as Super Experience.
* `using_convert_to` is optional and defines the item returned after the fuel item is consumed.

The generated data map includes Create Experience Nuggets/Blocks, Super Experience items, the experience bucket, experience cake items, and optional entries for Create Stuff & Additions, Ars Nouveau, and Mystical Agriculture.

### Fluid Experience Units

`create_enchantment_industry:unit/experience` is a fluid data map that configures how much experience one mB of another mod's experience fluid represents.

Example:

```json
{
  "values": {
    "examplemod:liquid_xp": 20
  }
}
```

The generated data map includes optional entries for CoFH Core, Cyclic, Ender IO, Industrial Foregoing, Just Dire Things, Mob Grinding Utils, PneumaticCraft, Reliquary, and Sophisticated Core.

### Printing Ingredients

The Printer uses fluid data maps to decide which fluids can power built-in printing behaviours and how much fluid each operation consumes:

* `create_enchantment_industry:printing/address/ingredient`
* `create_enchantment_industry:printing/pattern/ingredient`
* `create_enchantment_industry:printing/copy/ingredient`
* `create_enchantment_industry:printing/custom_name/ingredient`
* `create_enchantment_industry:printing/written_book/ingredient`
* `create_enchantment_industry:printing/banner_pattern/ingredient`

Each entry maps a fluid or fluid tag to a positive integer mB cost:

```json
{
  "values": {
    "#c:dyes/black": 10,
    "create_enchantment_industry:experience": 25
  }
}
```

### Custom Name Styles

`create_enchantment_industry:printing/custom_name/style` is a fluid data map that controls the text style applied by custom-name printing.

Example:

```json
{
  "values": {
    "#c:dyes/red": {
      "color": "#FF0000"
    },
    "examplemod:royal_ink": {
      "color": "#663399",
      "bold": true
    }
  }
}
```

The value uses Minecraft's `Style` codec. The generated entries provide text colors for common dye fluid tags.

### Enchanted Book Printing Costs

`create_enchantment_industry:printing/enchanted_book/custom_cost` is an enchantment data map that overrides Printer costs for specific enchantments and levels.

Example:

```json
{
  "values": {
    "minecraft:mending": [
      {
        "level": 1,
        "value": 100
      }
    ]
  }
}
```

If no custom entry exists, the Printer falls back to its normal cost formula and server config multiplier.

### Enchantment Processing Rules

`create_enchantment_industry:enchantment_processing/rules` is an enchantment data map that tunes Blaze Enchanter and Blaze Forger behaviour per enchantment.

It controls two groups of values:

* `level_extension` sets the extra level cap used by Super Enchanting and Super Forging.
* `cost_multiplier` sets per-enchantment cost multipliers for Blaze Enchanter and Blaze Forger operations.

Example:

```json
{
  "values": {
    "minecraft:sharpness": {
      "level_extension": {
        "blaze_enchanter": 2,
        "blaze_forger": 4
      },
      "cost_multiplier": {
        "blaze_enchanter": {
          "normal": 1.0,
          "super": 1.5,
          "direct": 1.0,
          "template": 1.2
        },
        "blaze_forger": {
          "normal": 1.0,
          "super": 2.0,
          "merge": 1.0,
          "apply": 1.25,
          "extract": 0.75
        }
      }
    },
    "minecraft:mending": {
      "level_extension": {
        "blaze_enchanter": 0,
        "blaze_forger": 0
      }
    }
  }
}
```

All fields are optional. Missing level extension values use the matching server config:

* `blazeEnchanterMaxLevelExtension`
* `blazeForgerMaxLevelExtension`

Missing cost multipliers use `1.0`. Cost multipliers may be `0.0`, but any otherwise valid operation still costs at least one unit.

Blaze Enchanter cost is based on its selected enchanting level, then multiplied by:

* regular or Super Blaze Enchanter global cost multiplier
* direct or template Blaze Enchanter global cost multiplier
* the weighted average of selected enchantment rule multipliers

Blaze Forger cost is based on each affected enchantment's anvil cost and level, then multiplied by:

* regular or Super Blaze Forger global cost multiplier
* merge, apply, or extract Blaze Forger global cost multiplier
* the matching per-enchantment rule multipliers

The generated rule data map sets Mending and Infinity level extension to `0` for both Blaze Enchanter and Blaze Forger.

## Recipes

### Printing

`Printing` is the Printer recipe type `create_enchantment_industry:printing`.

It follows Create processing recipe conventions, with one extra `sound` field for the sound played when printing completes. The first item ingredient is the base item. The second item ingredient is the template or printing material. The recipe may also require one fluid ingredient.

Example:

```json
{
  "type": "create_enchantment_industry:printing",
  "ingredients": [
    {
      "item": "minecraft:wheat"
    },
    {
      "item": "minecraft:cookie"
    },
    {
      "type": "neoforge:single",
      "amount": 250,
      "fluid": "create_enchantment_industry:experience"
    }
  ],
  "results": [
    {
      "id": "minecraft:cookie"
    }
  ],
  "sound": "entity.generic.eat"
}
```

Printing recipes can also be used as Sequenced Assembly steps.

### Grinding

`Grinding` is the Mechanical Grindstone recipe type `create_enchantment_industry:grinding`.

It follows Create standard processing recipe conventions:

* It accepts one item ingredient.
* It can output up to four item results.
* It can have either one fluid input or one fluid output.
* It supports `processing_time`.
* It can be used as a Sequenced Assembly step.

Example with a fluid output:

```json
{
  "type": "create_enchantment_industry:grinding",
  "ingredients": [
    {
      "item": "create:experience_nugget"
    }
  ],
  "results": [
    {
      "amount": 3,
      "id": "create_enchantment_industry:experience"
    }
  ]
}
```

Example with a fluid input:

```json
{
  "type": "create_enchantment_industry:grinding",
  "ingredients": [
    {
      "item": "examplemod:rough_gem"
    },
    {
      "type": "neoforge:single",
      "amount": 100,
      "fluid": "create_enchantment_industry:experience"
    }
  ],
  "results": [
    {
      "id": "examplemod:polished_gem"
    }
  ],
  "processing_time": 100
}
```

Grinding also automatically supports automatable Sandpaper Polishing recipes.

### Infusing

When Apothic Enchanting integration is enabled and Apothic Enchanting is loaded, Create: Enchantment Industry adds the Infuser recipe type `create_enchantment_industry:infusing`.

Infusing recipes run through the Infuser and Basin. They follow Create processing recipe conventions and add a required `stats` object:

```json
{
  "type": "create_enchantment_industry:infusing",
  "ingredients": [
    {
      "type": "neoforge:single",
      "amount": 250,
      "fluid": "create_dragons_plus:dragon_breath"
    }
  ],
  "results": [
    {
      "amount": 750,
      "id": "create_enchantment_industry:infused_dragon_breath"
    }
  ],
  "stats": {
    "eterna": 80.0,
    "quanta": 15.0,
    "arcana": 60.0
  }
}
```

`stats` defines the minimum Apothic Enchanting table stats required from the Infuser setup. The Infuser consumes a reagent fluid from `create_enchantment_industry:infusing/ingredients`.

Apothic Enchanting `apothic_enchanting:infusion` recipes are also converted into Infusing recipes.

### Bulk Salvaging

When Apotheosis integration is enabled and Apotheosis is loaded, Create: Enchantment Industry adds a fan processing type for Salvaging Table logic.

* JEI name: `Bulk Salvaging`
* Fan processing id: `create_enchantment_industry:salvaging`
* Recipe type: `create_enchantment_industry:salvaging`
* Catalysts: blocks in `create_enchantment_industry:fan_processing_catalysts/salvaging` and fluids in `create_enchantment_industry:fan_processing_catalysts/salvaging`

When Sable, Apothic Enchanting, and Apotheosis are all loaded, Fragile Fluid Tanks filled with Infused Dragon's Breath release a Bulk Salvaging burst on impact. This burst can salvage nearby dropped items and may salvage equipped items from nearby living entities. Equipped-item salvaging uses the Apotheosis integration server config and scales with tank fullness.

Custom salvaging recipes follow Create standard processing recipe conventions:

```json
{
  "type": "create_enchantment_industry:salvaging",
  "ingredients": [
    {
      "item": "examplemod:salvageable_item"
    }
  ],
  "results": [
    {
      "id": "examplemod:salvaged_material"
    }
  ]
}
```

### Blaze Composer, Affix Templates, and Affix Augmentor Costs

From this section you'll learn how we designed the default cost calculation. If you're a modpack developer this might help you understand how things work (that's why I added this section here).

When Apotheosis integration is active, Blaze Composer and Affix Augmentor use the current Apotheosis Augmenting Table upgrade cost as their shared reference point.

Reference cost:

```text
apotheosis_upgrade_reference =
  scaled_experience_essence
  + AdventureConfig.upgradeSigilCost * affixAugmentorCostSigilToApotheoticEssenceRatio
```

`scaled_experience_essence` starts from `affixAugmentorCostExperienceToApotheoticEssenceTotal`, then scales it by actual total XP:

```text
scaled_experience_essence =
  affixAugmentorCostExperienceToApotheoticEssenceTotal
  * total_xp_for(Apotheosis upgradeLevelCost)
  / total_xp_for(225)
```

With default Apotheosis and CEI configs this is `19347 + 2 * 81 = 19509 mB` of Apotheotic Essence for one standard 0.25 affix upgrade.

Affix Templates store one rarity and one or more affix entries. Each entry stores an affix id, level, source loot categories, and whether the entry has gone beyond Apotheosis' native level range. The template rarity is shared by all entries because Apotheosis equipment has one rarity component for all affixes.

Affix Templates do not have a gameplay affix-count cap, matching Enchanting Templates and their stored enchantments. Template capacity is controlled by per-entry level limits:

* Brass Affix Template: `brassAffixTemplateMaxLevel`
* Crystal Affix Template: `crystalAffixTemplateMaxLevel`
* Apotheotic Affix Template: `apotheoticAffixTemplateMaxLevel`

More entries naturally cost more because Blaze Composer prices every entry that is extracted, newly applied, upgraded, or merged. The internal network codec still has a defensive decode limit for corrupted or malicious data; that guard is not a configurable gameplay limit.

Blaze Composer mode behaviour:

* Extract still extracts exactly one affix from equipment into one blank template. If an item has multiple affixes, the first valid affix by id is selected for deterministic automation.
* Merge takes two filled templates and produces exactly one filled template. The operation must fully merge all entries or it fails without consuming inputs. Different rarities fail. Exceeding the resulting template's level limits fails. Exclusive-set conflicts fail in Normal Mode; in Super Mode they can be allowed by `allowExclusiveSetBypassInSuperMerging` and are charged extra.
* Apply consumes the filled template if at least one entry can be added or upgraded on the target equipment. Entries that cannot apply are not returned; the Composer goggle tooltip lists each lost affix and why it was lost. If no entry can be applied or upgraded, the operation fails and consumes nothing. This intentionally matches Blaze Forger's "apply everything that can apply" behaviour.

Blaze Composer does not charge for the full result every time. It charges by operation and by the actual affix value being created, moved, or folded into the result:

* Extract charges from `0 -> extracted level` with `blazeComposerExtractSnapshotMultiplier` because it snapshots an existing affix into a blank template.
* Applying a template entry to equipment with no matching affix charges from `0 -> template level` with `blazeComposerApplyNewTemplateMultiplier` because the filled template is consumed.
* Applying a template entry to equipment with a matching affix charges only `current level -> result level` with `blazeComposerApplyUpgradeDeltaMultiplier`.
* Merging a new affix entry into the result charges from `0 -> entry level` with `blazeComposerMergeUpgradeDeltaMultiplier`.
* Merging two entries with the same affix charges from the lower input level to the resulting level with `blazeComposerMergeUpgradeDeltaMultiplier`. Equal levels can upgrade by `affixTemplateMergeStep`; different levels fold the weaker entry into the stronger result.

Level value is weighted before cost is calculated:

```text
value(level) =
  standard_segment_0_to_1
  + crystal_segment_1_to_2 * blazeComposerCrystalLevelMultiplier
  + pow(super_segment_above_2, blazeComposerSuperLevelExponent) * blazeComposerSuperLevelMultiplier
```

The standard non-Super level contribution is capped by `blazeComposerStandardOperationCostCap` before template tier, affix type, and datapack rule multipliers are applied. Super value above level `2.0` is intentionally uncapped by that setting and grows with the Super exponent. Final Composer cost is:

```text
cost =
  mode_base_cost
  + sum(
      operation_level_cost(entry)
      * template_tier_multiplier
      * affix_type_multiplier(entry)
      * affix_composing_rule_cost_multiplier(entry, rarity)
    )
  + exclusive_set_bypass_extra_cost
```

Template tier multipliers are `brassAffixTemplateCostMultiplier`, `crystalAffixTemplateCostMultiplier`, and `apotheoticAffixTemplateCostMultiplier`. Affix type multipliers are `statAffixTypeCostMultiplier`, `basicEffectAffixTypeCostMultiplier`, and `abilityAffixTypeCostMultiplier`. Exclusive-set bypass extra costs are configured separately for applying and merging through `superExclusiveSetApplyExtraCostMultiplier` and `superExclusiveSetMergeExtraCostMultiplier`; each bypassed conflict adds the configured multiplier of the current Apotheosis upgrade reference cost.

Blaze Composer Super charging is explicit. Fill the normal Apotheotic Essence tank, use an item from `create_enchantment_industry:blaze_composer/super_activators`, then continue supplying Apotheotic Essence to fill the Super tank. Normal Mode processes Brass and Crystal Affix Templates; Super Mode processes Apotheotic Affix Templates. Super fuel draining to empty returns the machine to normal processing, but the Super charging activation remains on that Composer.

Config note: `allowExclusiveSetBypassInSuperApplying` and `allowExclusiveSetBypassInSuperMerging` control whether Super Mode may bypass Apotheosis exclusive sets. Set both explicitly if your pack wants this behavior.

Affix Augmentor is the automated standard upgrade path. By default, it upgrades only up to level `1.0`, matching Apotheosis' normal Augmenting Table. It chooses the lowest-level valid affix on the item; ties are resolved by affix id for deterministic automation. It skips level-independent affixes and affixes denied by affix composing rules.

Affix Augmentor result level:

```text
result_level = min(current_level + affixTemplateMergeStep, affixAugmentorMaxLevel)
```

Affix Augmentor cost:

```text
cost =
  apotheosis_upgrade_reference
  * weighted_delta(current_level, result_level) / weighted_delta(0, 0.25)
  * affixAugmentorCostMultiplier
  * affix_composing_rule_cost_multiplier
  * affix_composing_rule_augmenting_cost_multiplier
```

With default configs and no datapack rule multiplier, a normal 0.25 upgrade costs the same as the current Apotheosis Augmenting Table reference cost.
Partial upgrades, such as the final step into the configured cap, are charged proportionally by their weighted level delta. They are not forced up to a full 0.25-step cost.

### Affix Composing Rules

Apotheosis affixes and rarities are Placebo dynamic registry entries rather than NeoForge registry entries, so they cannot host native NeoForge data maps. Affix composing rules use the same target-file model: the resource id of each JSON file is the exact affix or rarity id receiving the rule.

Affix rules are loaded from:

```text
data/<affix_namespace>/create_enchantment_industry/affix_composing/affix/<affix_path>.json
```

Rarity rules are loaded from:

```text
data/<rarity_namespace>/create_enchantment_industry/affix_composing/rarity/<rarity_path>.json
```

For example, the rule for `apotheosis:example_affix` is:

```text
data/apotheosis/create_enchantment_industry/affix_composing/affix/example_affix.json
```

Its contents are the rule directly:

```json
{
  "cost_multiplier": 1.5,
  "augmenting_cost_multiplier": 0.75,
  "max_level": 3.0,
  "deny_extraction": false,
  "deny_applying": false,
  "deny_merge": false,
  "deny_augmenting": false,
  "deny_super": false
}
```

Rules target exact ids only; dynamic registry tags are not supported. A higher-priority datapack replaces a lower-priority rule at the same resource path, matching normal datapack resource override behavior. Rules are evaluated per affix entry on a template. An affix rule and its rarity rule both apply to that entry: cost multipliers multiply, deny flags use logical OR, and the lowest configured `max_level` wins.

Fields:

* `cost_multiplier` affects Blaze Composer and also acts as the shared base multiplier for Affix Augmentor.
* `augmenting_cost_multiplier` affects Affix Augmentor only.
* `max_level` caps template operations for matching affixes or rarities.
* `deny_extraction`, `deny_applying`, and `deny_merge` disable specific Blaze Composer modes.
* `deny_augmenting` prevents Affix Augmentor from selecting matching affixes.
* `deny_super` prevents matching affixes from being processed in Blaze Composer Super Mode.
* Numeric fields must be finite and non-negative. Omitted fields use neutral defaults.

## Config

### Feature Flags

Feature flags are in the common config and require restart when changed.

Notable feature flags:

* `processing/classic_blaze_enchanter`
* `classic_blaze_enchanter` as an alias for the same feature

Mods depending on certain features may forcibly enable or disable them. In that case, the corresponding config value is ignored.

### Apothic Enchanting Integration Server Config

When the Apothic Enchanting integration is active, its server config provides:

* Brass Bookshelf Eterna, Quanta, Arcana, and treasure settings
* Multiple Brass Bookshelf max Eterna
* Creative Bookshelf treasure setting
* Infuser fluid capacity
* Affix Enhancer fluid capacity placeholder used by integration machinery
* Ender Woven Bag capacity, pull behaviour, boss pull toggle, pull radius, pull force, and contraption release cooldown
* Integration stress values

### Apotheosis Integration Server Config

When the Apotheosis integration is active, its server config provides:

* Gem Cutter per-purity Crystal Essence costs for Cracked -> Chipped, Chipped -> Flawed, Flawed -> Normal, Normal -> Flawless, and Flawless -> Perfect upgrades
* Gem Cutter global Crystal Essence cost multiplier
* Apotheosis Augmenting Table cost conversion ratios used by Affix Augmentor and Blaze Composer
* Blaze Composer template level limits, template level limits, Super fuel capacity, operation multipliers, level segment weights, template/type cost multipliers, and Super exclusive-set bypass controls
* Affix Augmentor max level and global cost multiplier
* Bulk Salvaging equipped-item destruction probability
* Infused Dragon's Breath Fragile Fluid Tank impact settings for salvaging dropped items and equipped items

### Touhou Little Maid Integration Server Config

When the Touhou Little Maid integration is active, its server config provides:

* Whether Experience Lanterns drain experience from nearby maids
* The maximum experience drained from each maid per operation
