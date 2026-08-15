# Migration Resource Error Overlay

Version 1.1.0 also closes the verified 1.21.1 client resource gaps for all 144 Ender Dragon Tea block states and the three blowgun pulling models. Five- and six-cup tea states retain their gameplay state and use the existing four-cup geometry as a documented visual fallback.

NeoForge 1.21.1 resource-only compatibility overlay for the fixed migration pack.

It does not add replacement gameplay. It makes existing optional resources conditional:

- Create Dragons Plus fragile tank loot tables load only with `simulated`, matching the recipes and registration gate.
- Nether doll loot tables load only with `kaleidoscope_nether_equivalence`, which owns the missing registrations.
- Nether recipes load only when the backported item/fluid owner is present.
- Yuushya painter gift box loads only when its missing encyclopedia input is registered.
- Optional tag members use `required: false`, preserving them whenever their provider is installed.

Build with `powershell -ExecutionPolicy Bypass -File .\build.ps1`.
