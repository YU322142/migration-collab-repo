# Mechanomania frontier terrain isolation datapack

This directory is generated, not runtime-validated.

- `minecraft:overworld` is pinned to the Minecraft 1.21.1 384-block
  dimension type, noise settings, and reachable vanilla noise/density closure.
- `mechanomania_frontier:frontier` uses the Mechanomania/Tectonic 544-block generator.
- Existing world chunks are not included and must never be copied into this
  directory.
- Preferred integration: merge `data/**` last into the final KubeJS data tree.
- Alternative integration: install as the highest-priority world datapack and
  prove priority plus resolved registry values in an isolated server.
- Bootstrap test access: `/execute in mechanomania_frontier:frontier run tp @s 0 160 0`.

Do not publish until the runtime gates in
`outputs/terrain-preservation-final-20260813.md` pass.
