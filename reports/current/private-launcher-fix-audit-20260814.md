# Attempt5 private desktop launcher audit and fix

Date: 2026-08-14 (Asia/Shanghai)

## Outcome

The Attempt5 client did not reach Java. The private-desktop PowerShell child
exited during launcher preflight because the matched client's Prism-backed
`libraries` tree contains none of the 24 Windows native classifier JARs named
by the 1.21.1 metadata. The first rejected path was:

`<AUDIT_ROOT>\mechanomania-matched-client-20260813\libraries\org\lwjgl\lwjgl-freetype\3.3.3\lwjgl-freetype-3.3.3-natives-windows.jar`

All 93 selected non-native libraries were present. The Java executable was
also present. This explains the evidence shape exactly: launcher PID 21984,
null Java PID, no client stdout/stderr path, and no launch-result JSON.

The launcher itself was not a new regression: its pre-fix SHA-256 was
`A7996B3B8E7AB5F71AB1AF7DB373465EBEA96203FF67FAE5BCD0070CC27F5F89`,
identical to the launcher recorded by the successful Candidate11 gate. The
input topology changed: the matched client links `versions`, `libraries`, and
`assets` to the portable Prism installation, whose global `libraries` cache
does not retain these classifier JARs.

## Safe native source

The client's `versions` junction has one resolved target:

`<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\instances\1.21.11\minecraft\versions`

Its sibling `natives` directory is the extracted tree associated with that
same version source. It contains 66 files / 16,505,767 bytes. A deterministic
relative-path, length, and file-hash manifest has SHA-256
`55559F16F0C2A8D199C1F736500BCFEEB067667CAA59D8A6A379DE20597B1BAF`.
All eight required x64 LWJGL DLLs are present.

## Patch

Only
`outputs/tools/launch_neoforge_client_isolated.ps1` was changed. The private
desktop helper was not changed.

The launcher now:

1. Continues to reject any missing ordinary library immediately.
2. Uses metadata native JAR extraction unchanged when every native artifact is
   present.
3. Rejects a partially present native artifact set instead of mixing sources.
4. When all native classifier JARs are absent, accepts only a single-target
   `versions` reparse point whose resolved directory is named `versions`.
5. Uses only that resolved target's sibling `natives` directory and validates
   all eight required x64 LWJGL DLLs before process creation.
6. Records `native_source` and `native_directory` in the launch result.

Current launcher: 10,613 bytes, SHA-256
`CD8BAEC99762F6260B43CA1E7C92E47AE19BC2583FAA7BE9865D2CEA06154914`.

Unchanged private helper: 14,764 bytes, SHA-256
`FB819479F7143C53B2E690568CE85CC5E31F47F5EE9C3C6ACB561C111AF195F9`.

Added regression test:
`outputs/tools/test_launch_neoforge_client_isolated_native_fallback.ps1`,
8,197 bytes, SHA-256
`8EE4AE85D04E6FAB9C2314D599C2F7B5A493E41EABC873EC3E6CB7619277C303`.

## Verification without Java or Minecraft

- PowerShell AST parse: PASS for the launcher and test.
- Synthetic native fallback test: PASS.
- Missing required DLL rejection: PASS before process creation.
- Partial native artifact rejection: PASS before process creation.
- Actual matched-client read-only probe with an in-memory `Start-Process`
  stub: returned fake PID 424242, selected `versions_sibling`, wrote the
  expected result, and created no process.
- Actual matched-client top-level metadata was unchanged by the probe.
- Actual matched-client `natives` file count stayed 0 -> 0.
- Existing static suites: 32/32 Candidate8 join tests, 18/18 Candidate14
  release tests, and 14/14 Mechanomania startup-gate tests passed (64/64).
- Final process inventory contained no `java.exe` or `javaw.exe`.

The matched-client stub result is retained at
`<AUDIT_ROOT>\private-launcher-fix-audit-20260814\matched-client-stub-launch-result.json`
(723 bytes, SHA-256
`330A075D2E0ED96EC0AFAC9B30CF1F32202A6110702C8659100CB30D8A017297`).
It is simulation evidence only; PID 424242 is synthetic.

## Source evidence

- Attempt5 report: 7,319 bytes, SHA-256
  `C6DBAE8BE745874C70E87113F45D0D6C21F3ED52EE537BB7016D5635152E0333`.
- Attempt5 client state: 400 bytes, SHA-256
  `24CE1026F1112D6F49CA3DB269D28EE916FF82FCC0ABB5FB76B02D929DDFA8F9`.
- Attempt5 state records `launcher_pid=21984`, `java_pid=null`, empty client
  stdout/stderr, and `Private launcher exited before producing a launch result`.

No Minecraft/Java process was started, and no runtime, matched client, Prism
instance, production configuration, or production port was modified by this
fix task.
