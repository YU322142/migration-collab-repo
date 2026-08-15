# Overworld 544-height fail-closed overlay

Date: 2026-08-15  
Static overlay status: `PASS`  
Same-Overworld transition status: `BLOCKED`

This overlay fixes the effective Minecraft 1.21.1 registry path for the
Overworld build height. It contains exactly one deployable KubeJS data file:

```text
kubejs/data/minecraft/dimension_type/overworld.json
```

Its dimension bounds are `min_y=-64`, `height=544`, and
`logical_height=544`. The highest placeable block is therefore Y=479. The
existing `minecraft:overworld` noise settings remain `min_y=-64,height=384`,
so natural terrain remains Y=-64..319 and Y=320..479 is an upper build/air
layer. This overlay does not contain chunks and does not rewrite a world.

The current final server also contains this stale, ineffective path:

```text
kubejs/data/minecraft/worldgen/dimension_type/overworld.json
```

It must be removed only after its preimage SHA-256 matches the entry in
`.ota-delete-list.json`. Leaving it in place does not raise the build limit,
but it makes future audits dangerously ambiguous.

Deployment rules:

1. Stop the server and pass the normal OTA preimage/CAS gate.
2. Merge only `kubejs/**` from this directory.
3. Apply `.ota-delete-list.json` with its SHA-256 guard.
4. Do not copy or edit `world`, `level.dat`, region, entities, POI, or
   `server.properties` files.
5. Put the same effective KubeJS file in the final client for integrated
   singleplayer parity. Keep MCModSync disabled while testing; restore it only
   for the final client and prevent it from downgrading this file.
6. Run `outputs/tools/validate_worldgen_height_overlay.py` before packaging.

This is deliberately not a same-Overworld Tectonic transition implementation.
The latter needs a BOTH-side NeoForge module plus a final-C frozen mask and
boundary-condition atlas. Until every transition gate in
`OVERLAY-CONTRACT.json` passes, production must remain fail-closed. The
existing namespace-isolated `mechanomania_frontier:frontier` dimension remains
the safe complete-Tectonic fallback, but it is not a substitute for the
requested far field in the main Overworld.
