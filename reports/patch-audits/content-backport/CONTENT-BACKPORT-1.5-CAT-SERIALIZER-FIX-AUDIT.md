# Content Backport 1.5 entity-data serializer startup fix audit

Date: 2026-08-14 (Asia/Shanghai)

Status: **STATIC FIX READY FOR A DISPOSABLE STARTUP GATE; NOT YET RUNTIME-PROVEN**

## Scope and constraints

- Diagnosed the attempt3 crash without launching Minecraft.
- Built on `D:` in an isolated source/patch project.
- Did not modify the attempt3 runtime, matched client, source staging, world, configs, or ports.
- The replacement remains a BOTH-side mod and must be identical on server and client.

## Root cause

The observed crash is not a missing registry declaration. `ContentBackport` does attach
`BackportedEntityDataSerializers.SERIALIZERS` to the mod event bus. The defect is an
illegal early value read:

1. NeoForge is applying/reverting registry snapshots in `GameData.postRegisterEvents`.
2. Vanilla `DefaultAttributes.<clinit>` initializes `Cat` before the custom entity-data
   serializer registry is bound.
3. `CatSoundVariantBackport$CatMixin.<clinit>` calls
   `BackportedEntityDataSerializers.CAT_SOUND_VARIANT.get()`.
4. `DeferredHolder.get()` throws because `backport:cat_sound_variant` is temporarily
   unbound.

The same static pattern existed for all eight Content Backport animal serializers:

- cow variant
- pig variant
- chicken variant
- wolf sound variant
- cow sound variant
- chicken sound variant
- pig sound variant
- cat sound variant

Only fixing the cat field would leave chicken/cow/pig/wolf able to fail later in the same
vanilla `DefaultAttributes` initialization path.

## Fix design

The patch creates each of the eight serializer objects eagerly without reading a
registry value. The existing DeferredRegister suppliers then register those exact same
objects under the original names. The five affected mixin static initializers use the
eager objects when calling `SynchedEntityData.defineId`.

This preserves:

- registry ids such as `backport:cat_sound_variant`;
- all DeferredHolder fields and normal registration wiring;
- serializer codecs and registry-key types;
- entity/NBT persistence keys;
- mod id `backport`, metadata version `1.5`, and BOTH-side metadata;
- two cat sound-variant JSON files and all 21 backported cat OGG files;
- every unrelated class and resource byte-for-byte.

Exactly six JAR entries changed:

1. `com/juanmuscaria/backport/world/entity/animal/BackportedEntityDataSerializers.class`
2. `com/juanmuscaria/backport/mixin/common/CatSoundVariantBackport$CatMixin.class`
3. `com/juanmuscaria/backport/mixin/common/ChickenVariantBackport$ChickenMixin.class`
4. `com/juanmuscaria/backport/mixin/common/CowVariantBackport$CowMixin.class`
5. `com/juanmuscaria/backport/mixin/common/PigVariantBackport$PigMixin.class`
6. `com/juanmuscaria/backport/mixin/common/WolfSoundVariantBackport$WolfMixin.class`

No entry was added or removed.

## Artifact identity

Original audited input:

- File: `backport-1.5.jar`
- Bytes: `15,301,451`
- SHA-256: `167534C66D5E6C09DCB01152EBD37D18CED5CF6278A9228C094F937886133AF5`

Fixed replacement:

- File: `backport-1.5-cat-serializer-fix.1.jar`
- Bytes: `15,336,561`
- SHA-256: `34291AF9D81B6AEE0780F5F511B2A9594664F36906AED40687DF1C7009E68B1D`

## Verification results

Two separate `--no-daemon clean check` builds completed successfully. Both generated
the exact fixed SHA-256 above.

Each clean check ran:

- 2/2 JUnit contract tests;
- exact-input SHA fail-closed guard;
- deterministic duplicate-build byte comparison;
- ZIP entry and CRC validation;
- unchanged-entry byte comparison;
- ASM stack/local bytecode analysis on all six modified classes;
- registry name and original DeferredHolder preservation checks;
- serializer-supplier identity checks;
- BOTH-side metadata checks;
- cat gameplay resource preservation checks.

Measured lifecycle-risk result:

- original animal serializer `DeferredHolder.get()` sites in mixin static initializers: `8`
- fixed JAR sites: `0`
- eager serializer use sites: `8`

Independent `javap` inspection confirms the cat mixin now calls
`SynchedEntityData.defineId(Cat.class, CODEX_EAGER_CAT_SOUND_VARIANT)` directly, while
the `cat_sound_variant` DeferredRegister supplier returns the same eager object.

## Wider static audit

A JAR-wide scan of static initializers found two unrelated classes that still use
registered holders during their own initialization:

- `EyeblossomBlock$Type`: four sound-event holder reads.
- `HappyGhast`: one sensor-type holder read.

They are not part of the vanilla `DefaultAttributes` pre-registration trigger that
caused attempt3, and their referenced registries are expected to be available before
their backported block/entity suppliers execute. They were intentionally left unchanged
to keep this repair minimal. The next disposable startup gate remains the authority for
whether either requires a separate patch.

## Installation contract for the parent task

1. Back up the active original JAR outside all load paths.
2. Replace `backport-1.5.jar` with the fixed JAR on both server and client.
3. Never load the original and fixed JAR together; both retain mod id `backport`.
4. Gate the exact filename, byte size, and SHA-256 shown above on both sides.
5. Run only a disposable fresh runtime startup gate first.
6. If that gate passes, exercise cat/chicken/cow/pig/wolf spawning, save/reload, and
   client synchronization before promoting the release.

No production configuration or port change is required.
