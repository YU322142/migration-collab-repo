## Create: Enchantment Industry 2.5.0-preview-alpha1

PLEASE NOTICE: **DO NOT** ADD IT TO YOUR NORMAL SAVE OR MODPACK! IT IS ALPHA VERSION FOR CONTENT PREVIEW! BREAKING CHANGE MAY(CERTAINLY WILL) OCCUR IN FUTURE PREVIEW AND RELEASE VERSIONS!

THIS IS **NOT** A RELEASE FOR PLAYING IN YOUR MODPACK OR SERVER! THIS IS **JUST A PREVIEW** FOR TESTING AND HAVING FUN! OCCURRING ISSUE IS **NORMAL**.

### Update
* Add Blaze Composer & Affix Templates for handling apotheosis affixes.
* Apotheotic Content now has an independent CreativeTab.
* Added more customizable options of Blaze Forger & Enchanter.
* Improved Arm Interaction for Blaze Enchanter and Blaze Forger.
* Improved goggle tooltips of Blaze Forger & Enchanter.
* Added Goggle tooltip for Gem Cutter & Affix Augmentor.

If you are **modpack developer**:

#### Migration From Older Version

The old server config option `enchantmentMaxLevelExtension` is no longer used. There is no automatic fallback from that old config value. Modpacks that previously changed it must set both new options explicitly.

Some old datapack datamaps are still supported through a compatibility layer (might be removed in the future), but they are deprecated and will print a server log warning when used.

Migration table:

| Old entry | New entry | Compatibility fallback |
| --- | --- | --- |
| `enchantmentMaxLevelExtension` config | `blazeEnchanterMaxLevelExtension` and `blazeForgerMaxLevelExtension` config | No |
| `super_enchanting/custom_level_extension` datamap | `enchantment_processing/rules.level_extension.blaze_enchanter` and `level_extension.blaze_forger` | Yes |
| `forging/cost_multiplier` datamap | `enchantment_processing/rules.cost_multiplier.blaze_forger.merge` and `cost_multiplier.blaze_forger.apply` | Yes |
| `forging/split_enchantment_cost_multiplier` datamap | `enchantment_processing/rules.cost_multiplier.blaze_forger.split` | Yes |

If you need any help on customization, please read https://github.com/DragonsPlusMinecraft/CreateEnchantmentIndustry/blob/1.21.1/6.0.0-dev/MODPACK-README.md

### Change
* Affix Augmentor now has configurable maximum level and global cost multiplier, and affix composing rules can deny or reprice augmenting separately.
* Blaze Forger now needs to select mode manually via side panel for better automation setup.

### Fixed
* Fixed optional integration block loot tables losing their `neoforge:conditions` during data generation.
* Fixed Affix Augmentor idle processing state so belt-held items can start processing reliably.
* Fixed how `curse` in Blaze Forger work.
* Fixed Gem Cutter doesn't process flawless gem on depot.
