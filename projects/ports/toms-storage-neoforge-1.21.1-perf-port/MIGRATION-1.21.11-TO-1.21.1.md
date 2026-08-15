# Tom's Storage world migration gate

This branch must not be pointed at the production world. Run the conversion on
an independently backed-up D-drive copy before the first NeoForge save.

## Block-filter attachment conversion

`BlockFilterAttachmentMigration` converts one copied block-entity tag from:

```text
fabric:attachments/toms_storage:block_filter
```

to:

```text
neoforge:attachments/toms_storage:block_filter
```

The converter is fail-closed. It validates the legacy `pos`, converts absolute
`connected` positions to relative compounds, maps priorities to `0..4`, renames
`keep_last` to `keepLast`, retains non-empty filter NBT, and never mutates its
input tag. If both namespaces exist, NeoForge wins and a conflict is reported;
the target is never silently overwritten. A second pass performs no writes.

The filter ItemStack payload is copied exactly. The global Minecraft/mod
1.21.11-to-1.21.1 component converter must run before this attachment step. Any
unknown or failed ItemStack/component conversion aborts the world conversion;
it must never be replaced with an empty stack.

## Controlled execution order

1. Freeze and hash the source world. Work only on a D-drive copy.
2. Run the global block/item/component downgrade on that copy.
3. For every block entity, call
   `BlockFilterAttachmentMigration.migrateBlockEntity(tag, blockEntityPos)` and
   write only `Result.changed()` values to a new region file.
4. Require exactly `7` converted attachments, `0` position/format errors and
   `0` target conflicts for the audited source world.
5. Re-run the same pass and require `0` writes (`ALREADY_NEOFORGE` for all 7).
6. Re-scan semantics: `7` attachments, priority distribution
   `lowest=1, normal=3, highest=3`, `3` non-empty filters, and every connected
   absolute position equal to its pre-conversion value.
7. Only after those checks may an isolated NeoForge server load the copy.

Run the deterministic fixture with D-drive Gradle state:

```powershell
.\gradlew.bat -g D:\Trans\migration-audit-work\gradle-cache-toms-neoforge blockFilterAttachmentMigrationRegression --no-daemon
```

The fixture covers all seven audited coordinates, all priority values,
coordinate conversion, filter preservation, target-wins conflict behavior,
position mismatch failure, and a no-write second pass.

## MCA pipeline entry and evidence

The audit workspace did not contain a general 1.21.11 -> 1.21.1 MCA writer or
ItemStack/component downgrade entry. The independently reproducible entry is:

  migration-tools/toms_global_mca_downgrade.py

Its order is fixed and recorded in every JSON report:

1. itemstack_components_1.21.11_to_1.21.1
2. toms_storage_block_filter_attachment
3. anvil_region_rebuild

The converter is scoped to the audited Tom's filter component schemas and
fails closed for unknown ItemStack fields/components. It copies only the two
source regions named by the manifest into a new D-drive fixture; the
production source is never opened for write.

Reproducible command (all temporary state on D):

  $env:TEMP='D:\Trans\migration-audit-work\tmp-toms-mca'; $env:TMP=$env:TEMP; python -B migration-tools\toms_global_mca_downgrade.py fixture --source-world D:\Trans\20260807\world --fixture-root D:\Trans\migration-audit-work\toms-mca-fixture-20260808-6 --manifest D:\Trans\migration-audit-work\toms-storage-2.9.2-vs-2.4.1-audit\source-world-toms-attachments.csv --report D:\Trans\migration-audit-work\toms-mca-fixture-20260808-6\fixture-report.json

Evidence: first pass 7/7 converted in four chunks; second pass 7/7
ALREADY_NEOFORGE, zero converted chunks and zero writes; target-wins fixture
returned NEOFORGE_WINS_CONFLICT while retaining the target payload.
Semantic audit reports priority lowest=1, normal=3, highest=3, three
non-empty filters, seven self-connected positions, and source/target semantic
equality. Region audit preserves both timestamp tables and every untouched
compressed chunk record byte-for-byte (1021 + 1023 records).

Converter SHA-256:

  FF0D5DBD39ED6389EF0F1187B15E84FE71CD9D89EA34A0035643393680FD42A2

Fixture report SHA-256:

  0DEBB39FFF53570F4E4DA19ED9AF1F14B76878C2AB515F4F5990E27B2249252E

## Dedicated-server smoke

The perf5.2 candidate was loaded with NeoForge 21.1.241 and Create 6.0.10 in:

  D:\Trans\migration-audit-work\toms-storage-create-6.0.10-smoke4

The RCON-gated smoke reached Done, returned a valid list response, saved all
dimensions, and stopped. NeoForge 21.1.241, Create 6.0.10, and both Tom's
Storage config loads were present; hard-fatal patterns were zero.

This is a GO for the Tom/Create empty-server compatibility gate only. The full
stack still logs 18 pre-existing data/resource errors (the template baseline
logs 19), including missing Kaleidoscope Nether doll items, Cookery food tags,
three recipe parse failures, and two Create Dragons Plus loot-table items.
Therefore it remains a NO-GO for production migration or player-visible
equivalence until those unrelated full-stack errors and the general world
downgrade are closed.
