# Deferred Content Protection

First-release, fail-closed carrier for `minecraft:netherite_horse_armor`.

It intentionally does not implement the deferred gameplay. It keeps the exact
registry ID loadable and uses a minimal equestrian `AnimalArmorItem` only so armor
already stored in a horse BODY slot still renders safely. New equip, use, drop,
crafting/processing, dispenser and nested-container paths fail closed. The existing
horse inventory remains open for its other slots, while BODY slot 1 is immutable.
Ordinary inventory, chest, shulker, barrel, hopper and dispenser storage transfer remains
available; the dispenser may store it but its activation is a no-op. Ground/death-drop
carriers are persistent and damage-immune. A later OTA must replace this carrier
with the full implementation; the two must never coexist.
