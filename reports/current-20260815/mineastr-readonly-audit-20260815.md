# MineAstr read-only runtime audit (2026-08-15)

Scope: static inspection only. No Minecraft/Java process was started or stopped, and no world, config, JAR, cache, or MCModSync file was modified.

At inspection time an existing Prism `javaw` client process was present (PID 23992, started 2026-08-15 02:58:39); it was not touched. No dedicated-server Java process was observed.

## First concrete failure

The Attempt13 server loads MineAstr 0.6.26 but disables the bridge before it attempts a WebSocket connection:

- Active server config: `<AUDIT_ROOT>\mechanomania-matched-runtime-attempt13-20260814\config\mineastr-common.toml`
- `enabled = false` (the active NeoForge TOML)
- Startup evidence: `logs\latest.log:1520` and `logs\debug.log:25135` at `2026-08-14 22:30:40.507`: the MineAstr logger emits “disabled by configuration” (the Chinese source text is rendered garbled by the legacy console encoding).
- Source behavior: `MineAstrBridge.start()` checks `MineAstrConfig.ENABLED` and returns before `connectNow()` (`<AUDIT_ROOT>\mineastr-validation\neoforge-1.21.1-current\src\main\java\com\mineastr\MineAstrBridge.java:107-119`). `connectNow()` also refuses when disabled (`:764-767`).

Therefore the first failure is configuration-gated startup, not a DNS/TCP/WebSocket failure. No MineAstr connection error is expected while `enabled=false`.

## Provenance of the disabled setting

The setting appears to be a test-isolation carry-over, not a MineAstr code defect. `outputs/tools/prepare_mechanomania_matched_runtime.py:410` unconditionally calls `smoke.disable_mineastr_network(...)`, and `outputs/tools/prepare_final_fullstack_smoke.py:94-103,192` rewrites the active TOML to `enabled = false`. The Attempt13 runtime was therefore prepared with the bridge disabled by the smoke builder and later launched without a production re-enable step.

## JAR identity comparison

| Location | JAR/version | Bytes | SHA-256 |
|---|---|---:|---|
| Primary Prism client (instance `动静交映客户端`) | `mineastr-0.6.25.jar` / 0.6.25 | 258008 | `0809500F1993861B1F217D6FED89B68E3094396E853B29E9CF9BDD0C9CE0B787` |
| Matched Prism client Attempt13 | `mineastr-neoforge-1.21.1-0.6.26.jar` / 0.6.26 | 257982 | `0264D729A3343BE1645B5AFE16C15A7A57C7E89A9405FA67EC80EE06D4A148D8` |
| Attempt13 runtime/server | `mineastr-neoforge-1.21.1-0.6.26.jar` / 0.6.26 | 257982 | `0264D729A3343BE1645B5AFE16C15A7A57C7E89A9405FA67EC80EE06D4A148D8` |

The matched client and server bytes are identical. The primary client is one version behind. The 0.6.26 release notes state protocol/client behavior is compatible with 0.6.25, but the final deployment should use one pinned 0.6.26 pair.

All inspected manifests identify `modId=mineastr`, Minecraft `[1.21.1]`, and NeoForge `[21.1.219,)`.

## Config comparison (secrets redacted)

| Instance | enabled | WebSocket URL | command tool | binding/login checks |
|---|---:|---|---:|---:|
| Primary Prism client | true | `ws://127.0.0.1:8765/ws` | false | false/false |
| Matched Prism client | true | `ws://127.0.0.1:8765/ws` | false | false/false |
| Attempt13 server TOML | **false** | public host configured, port 8765 | **true** | true/true |
| Attempt13 server JSON (legacy/stale) | true | public host configured, port 8765 | true | true/true |

NeoForge tracks `mineastr-common.toml`; the adjacent `mineastr-common.json` is not read by this build. File times reinforce that distinction: JSON is from 2026-07-29, the active TOML from 2026-08-14 18:28:14, and the TOML backup also records `enabled=false`. Do not edit or delete the JSON in this read-only diagnosis.

The primary and matched clients still contain the template URL `127.0.0.1` and token `change-me`. These common settings are used when a client hosts an integrated/local server; for a dedicated server, the server TOML is the bridge endpoint that matters. If integrated/local hosting is intended, the URL must be reachable and the token must be rotated and matched; the MineAstr README says `change-me` is rejected by the AstrBot plugin.

## Log/cache findings

- Attempt13 server has no MineAstr WebSocket connection/refusal/error lines after startup; this is expected because the bridge exits at the disabled check.
- The server does record client capability/translation preference packets at `debug.log:25702-25703`, `25769-25770`, `25844-25845`, and `25892-25893` (client 0.6.26). These are in-game negotiation packets, not proof of AstrBot bridge connectivity.
- Two unrelated login timeout disconnects appear at `latest.log:1552` (`2026-08-14 22:34:48.695`) and `:1609` (`22:47:40.750`). They should be investigated separately; with MineAstr disabled and `loginCheckFailOpen=true`, they are not evidence of a MineAstr WebSocket failure.
- Attempt13 world cache exists and parses as compressed NBT: `world\data\mineastr_sign_translations.dat`, 13,242 bytes, SHA-256 `0021BC795D9658C4E53174E89D4CA0BA737E75FFC9A6F35EAB000DB78DAC20B5`, `version=2`, 139 entries. Matched client logs show successful sign translation query/results (`latest.log:2279-2287`), so the client-side sign cache/render path is functioning in that run.
- Primary client logs are stale gate artifacts: they reference `outputs\tmp\client-gate-candidate11\.minecraft`, not the current Prism instance root. They prove 0.6.25 loaded in that gate only and must not be used as current runtime evidence.

## Safe repair order (not executed)

1. During a planned restart, choose one canonical 0.6.26 JAR (SHA-256 above) for both Attempt13 server and the actual client used by players.
2. Put the same reachable AstrBot WebSocket endpoint and rotated non-default token in the active client/server TOML files. Keep the token out of reports and chat.
3. Initially leave `enableCommandTool=false`; the current server TOML has it enabled with permission level 4 and an empty static trusted list, so enabling the bridge as-is expands remote command risk.
4. If account-binding login is not part of the intended service, disable `enableBindingSync` and `loginBindingCheckEnabled` together. Otherwise verify AstrBot binding state before enabling the bridge; keep `loginCheckFailOpen=true` during rollout to avoid lockouts.
5. After the user authorizes a controlled restart, verify startup has a MineAstr “connected to AstrBot” line, then test chat, capability negotiation, sign translation, and reconnect. Do not use the legacy JSON as a source of truth.

## Audit integrity

- `java_launched=false`
- `world_mutated=false`
- `runtime_config_mutated=false`
- `mcmodsync_touched=false`
- `mineastr_sign_translations.dat` was read and parsed only.
