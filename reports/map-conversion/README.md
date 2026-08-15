# JourneyMap → Xaero handoff

Status: `STATIC_VALIDATION_PASSED`. Minecraft was not launched.

Primary install candidate: copy the contents of `staging/` into a stopped client's `.minecraft/` only after backing up that client's existing `xaero/` directory. Do not copy `alternatives/legacy-waypoint-import/` at the same time.

Cache identity was audited with disposable `play.example.invalid:12341`. Production remains `play.example.invalid:25566`. Xaero's cache directory is `Multiplayer_play.example.invalid` because its current path algorithm removes the port before sanitizing the address.

Port boundary: `12341` is disposable/audit-only; `25566` is production and was not changed. No production `server.properties`, proxy routing, firewall rule, or live server was touched.

The native map and waypoint world node is `mw$default`. The staged per-server Xaero cache configs explicitly select it and ignore an unknown server levelId so the imported data is visible on first connection. This does not change the server or any global mod setting.

`manifests/source-inventory.json` and `manifests/reference-layers.json` point to every preserved source layer. The complete source is intentionally not duplicated here; use the original ZIP or the extracted D: audit root recorded in `conversion-report.json`.

JourneyMap is not part of this staging output. The Mechanomania pack manifest already selects Xaero Minimap and World Map, but its stale `overrides/config/journeymap-server.toml` should be omitted when the final client is assembled.
