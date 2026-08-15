# Deferred Content Protection — frozen build audit

- Date: 2026-08-12
- Status: `BUILD_REPRODUCIBLE_STATIC_PASS`
- Frozen: yes
- Final JAR: `outputs/projects/deferred-content-protection-neoforge/build/libs/deferred-content-protection-1.0.0+neoforge.1.21.1-first-release.1.jar`
- Bytes: `23338`
- SHA-256: `1C7C4B2A76978C563C18EE05ABA9292099E6B15BA920CF2699904068F0B1104B`

## Reproducible build

The identical command was run twice from a clean project state:

`gradle.bat --no-daemon --max-workers=20 clean check jar`

Both builds passed `compileJava`, `compileTestJava`, `protectionContractTest`, `test`, `check` and `jar`. Both artifacts were 23,338 bytes with the same SHA-256 above and were byte-for-byte identical.

## Locked safety boundary

- Exact carrier ID remains `minecraft:netherite_horse_armor`.
- The carrier is an equestrian `AnimalArmorItem`, because vanilla `HorseArmorLayer` only renders that type. An ordinary `Item` would be skipped safely rather than cast, but would make already-equipped migrated armor invisible.
- Existing horse BODY carriers stay renderable. New equip is blocked through item callbacks, interaction events, horse BODY menu clicks and `AbstractHorse.equipBodyArmor` interception.
- Safe storage moves remain available in ordinary chests, barrels, shulker boxes, hoppers and dispenser containers.
- Q/throw/outside-click, clone, swap edge cases, quick move, drag and double-click collection are guarded where they could discard, equip or feed processing slots.
- Crafting, crafter, furnace, brewing, anvil, grindstone, smithing, stonecutter, cartography, loom, beacon and merchant processing paths reject the protected carrier.
- Recipe lookup returns no match for protected input; server startup fails closed if a loaded recipe names it as input or output.
- Dispenser activation uses NOOP and keeps the stack in the dispenser.
- Death snapshots restore a protected carrier missing from the drop collection. Ground carriers have unlimited lifetime, are invulnerable, and are rescued from below-world deletion to shared spawn.

## Scope

This is a compile/contract/reproducibility audit. Minecraft was not started. No `source`, `staging`, or Candidate13 content was modified.
