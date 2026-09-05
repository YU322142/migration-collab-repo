# Hot Bath 3.0.0 advancement trigger registry fix

Status: **static build and compatibility contracts passed; disposable Minecraft startup gate still required**.

## Root cause

`ExtraEventsRegister.registerAdvancementTrigger(RegisterEvent)` was subscribed without checking which registry was being processed. It therefore called `CriteriaTriggers.register(...)` on every `RegisterEvent`.

Attempt4 recorded 156 duplicate failures after the first successful call. The first ID is always `hotbath:foot_health`, so each later invocation failed there before reaching the other three IDs. The crash occurred before server/world preparation.

This is a deterministic Hot Bath 3.0.0 bug. It is not caused by CEI, Connector, another copy of Hot Bath, or world data.

## Fix

The 3.0.0 method now exits unless the current registry is `Registries.TRIGGER_TYPE`:

```java
if (!event.getRegistryKey().equals(Registries.TRIGGER_TYPE)) {
    return;
}
```

The four original registrations remain unchanged:

- `hotbath:foot_health`
- `hotbath:milk_skin`
- `hotbath:chronic_invalid`
- `hotbath:rose_body_fragrance`

The compatibility version is `1.21.1-3.0.0-registry-fix.1`, with the original `hotbath` mod ID and BOTH-side behavior retained.

## Fail-closed packaging decision

A conventional full source rebuild was rejected because it changed the released resource `assets/hotbath/particles/steam_particle.json` from 492 to 507 bytes. The resource-equivalence assertion was not relaxed.

The final artifact is instead a deterministic overlay on the exact released JAR. Of 337 file entries, exactly three differ:

1. `com/crabmod/hotbath/registers/ExtraEventsRegister.class`
2. `META-INF/MANIFEST.MF` — compatibility version only
3. `META-INF/neoforge.mods.toml` — compatibility version only

All other 334 file entries are byte-identical to the release, including the other 73 classes and every gameplay/data/resource entry. Both JARs contain 383 ZIP entries, 337 files, and 74 classes.

## Verification

Two independent project-clean builds ran:

```text
gradlew.bat clean check --no-daemon --no-build-cache
```

Both completed successfully and produced byte-identical JARs:

```text
712,893 bytes
SHA256 1B53A2B7B2C6476BBAD3ACE344316DA7ABE62854967DE322E9A25CA1D5C7681A
```

Each build passed 5 tests with 0 failures and 0 errors. The checks cover:

- ASM verification of `getRegistryKey()` and `Registries.TRIGGER_TYPE` before any trigger registration;
- control-flow verification that the conditional branch enters at `hotbath:foot_health` and dominates all four registrations;
- exactly four preserved `CriteriaTriggers.register` calls and four original IDs;
- exact advancement JSON `id` and `trigger` mappings;
- exact JAR file-entry set, all other classes/resources byte-identical;
- complete ZIP reads, CRC validation, and no duplicate entries;
- BOTH-side metadata.

Final bytecode begins:

```text
0:  aload_0
1:  invokevirtual RegisterEvent.getRegistryKey
4:  getstatic Registries.TRIGGER_TYPE
7:  invokevirtual Object.equals
10: ifne 14
13: return
14: ldc "hotbath:foot_health"
```

## Frozen artifact

```text
<AUDIT_ROOT>\hotbath-300-trigger-fix-artifacts-20260814\hotbath-1.21.1-3.0.0-registry-fix.1.jar
```

- Size: `712,893` bytes
- SHA-256: `1B53A2B7B2C6476BBAD3ACE344316DA7ABE62854967DE322E9A25CA1D5C7681A`

Reproducible build evidence is retained under `build-a` and `build-b` in the same artifact directory.

Source repository:

```text
<AUDIT_ROOT>\hotbath-300-trigger-fix-source-20260814
```

- Official 3.0.0 base: `5e382931c20744b2ffe43abc26b917e59f7a21cd`
- Frozen compatibility commit: `bdc4d7cafb1de80650fedf1e62ded60c0dce06ff`
- Branch: `codex/hotbath-3.0.0-trigger-fix`
- Working tree: clean

## Deployment rule

Install this exact JAR on both server and client. Each side must contain exactly one Hot Bath JAR; the original and fixed JAR must never coexist.

No Minecraft process was started, and attempt4, staging, client/runtime load paths, production configuration, ports, and world data were not modified. Runtime approval remains gated on a fresh disposable startup/join test.
