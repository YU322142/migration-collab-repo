# CC:Tweaked 1.120.0 startup/shutdown guard

This NeoForge 1.21.1 compatibility mod addresses the exact failure observed in
Candidate8m without modifying world data or the migration converter.

## Root cause

- `ComputerId=11` at overworld `(1403, 67, -5088)` is `On=1` in both the
  immutable source and the fresh e4 conversion.
- Its first 1.21.1 startup spent more than CC:Tweaked's fixed 30-second
  long-task deadline generating Java method handles. CC hard-aborted it and the
  failed test copy consequently saved it as `On=0`.
- After a worker exceeds the hard-abort grace period, CC deliberately keeps an
  additional `workerCount` sentinel for the abandoned physical thread. That
  makes `ComputerContext.close` fail closed instead of claiming a clean stop
  while an unresponsive worker may still exist. This guard preserves that
  safety signal.
- The smoke report's count of two is one event duplicated across `latest.log`
  and redirected server stdout, not two independent shutdown failures.

## Guard

- Extend the long-task startup/shutdown budget from 30 to 120 seconds.
- Extend the final context-close wait from 1 to 30 seconds.
- Require the exact CC:Tweaked 1.120.0 version and fail mixin application if
  any bytecode target is missing.

The timeout extension affects CC's long startup/shutdown tasks. Normal Lua
execution still uses CC's separate seven-second execution limit.

## Build

```powershell
& 'D:\Trans\migration-audit-work\gradle-cache-chest-colorizer\wrapper\dists\gradle-8.8-bin\dl7vupf4psengwqhwktix4v1\gradle-8.8\bin\gradle.bat' clean check jar --offline --no-daemon --max-workers=20
```

`verifyInputs` pins the CC:Tweaked input JAR SHA-256. `bytecodeContractTest`
pins both modified bytecode shapes, proves the normal Lua 7-second timeout and
1.5-second abort grace remain separate, and requires CC's abandoned-worker
fail-closed sentinel to remain intact.

## Acceptance gate

Use only a fresh copy assembled from the untouched e4 staging world. Before
round 1, verify `ComputerId=11` is `On=1`. After two join/teleport/restart
rounds, require:

- no `Terminating computer #11 due to timeout`;
- no `Failed to stop computers under deadline`;
- clean server exit in both rounds;
- `ComputerId=11` remains `On=1` after each clean stop;
- the `world/computercraft` payload remains content-preserved except for
  intentional gameplay writes.

Never reuse Candidate8m for acceptance: its failed run already persisted
`ComputerId=11` as `On=0`.
