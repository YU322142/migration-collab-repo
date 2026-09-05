# Create 6.0.10 carriage orientation crash closure

Date: 2026-08-13

## Outcome

The crash at the carriage contraption near `(-98.5, 63, -97.7625)` is caused by
Create 6.0.10 reading the 1.21.11 lowercase `InitialOrientation` with a
case-sensitive enum helper.  The failed read leaves `Direction.DOWN`; four
Create paths then call `getCounterClockWise()` on that vertical direction.

The closure is deliberately two-layered:

1. The conversion code normalizes every source carriage `InitialOrientation`
   to its uppercase 1.21.1 enum name and records every change.
2. The BOTH-side compatibility mod intercepts `getInitialOrientation()` for
   carriage entities.  It preserves every valid horizontal result, derives a
   bad/missing result from the horizontal `AssemblyDirection`, and uses SOUTH
   only if both values are unusable.  It does not write entity or world data.

## Authority and staging audit

- Authority: `<AUDIT_ROOT>\incoming-20260811-raw\20260811\world`
- Frozen staging: `<AUDIT_ROOT>\cutover-staging-incoming-20260811-candidate13-20260812\world`
- Four saved carriages were found in each `create_tracks.dat`.
- Source and staging both still contain four lowercase `InitialOrientation`
  values: `south`, `west`, `east`, and `north`.
- Every value is semantically equal to clockwise(`AssemblyDirection`).
- Sixteen train-control block instances were checked across source and staging.
  Every controls facing is horizontal and aligned with the carriage axis.
- The crashing carriage is source train 2, carriage 0, at
  `[-98.5, 63.0, -97.76249980926514]`: initial `east`, assembly `north`, two
  controls facing `north` and `south`.

Full entity-region audit, read-only:

- 3,002 entity region files
- 146,456 chunks
- 292,556 entities
- 18 ordinary Create contraptions (nine per root)
- zero parse errors
- zero actor/block-state issues
- zero additional carriage contraptions outside `create_tracks.dat`

Ordinary stationary, elevator, bearing, and gantry contraptions legitimately do
not use the carriage-only `InitialOrientation` rule; their actor positions all
resolved to valid block palette entries.

## Build and bytecode contract

Target Create JAR:

- SHA-256 `EF87FE5709F1BA1F5B8BB20A2925B5AFB4669E178FD6D8BF10C167759EEFE37A`

Source reference Create JAR:

- SHA-256 `38B61FFE06124A33336AC5C73BA26BDF5A53916FE83B08B33CED4BBAC92F24B0`

The contract test verifies:

- target Create uses a case-sensitive `NBTHelper.readEnum`;
- source Create uses a codec read path;
- the four target consumers expose the vertical `getCounterClockWise()` edge;
- the mixin is a cancellable RETURN injection on `getInitialOrientation`;
- valid orientations are returned unchanged;
- fallback output is always horizontal;
- the guard contains no save/write calls and no client-only references.

Two independent clean/offline builds passed (`clean check jar` and
`--rerun-tasks clean check jar`).  Both produced the same 6,288-byte JAR:

- SHA-256 `805D6841BD30B514A059B21BEE4B6C70E183CB379CA286032975DCB961D6D74E`

No Minecraft process was launched, no complete world copy was made, and neither
the authority nor frozen staging was modified.

## Deliverables

- `outputs/artifacts/create-carriage-orientation-guard-p02/build2-create-carriage-orientation-guard-1.0.0+neoforge.1.21.1-p0.2.jar`
- `outputs/create-carriage-controls-audit-20260813.json`
- `outputs/create-contraption-region-audit-20260813.json`
- `outputs/projects/create-carriage-orientation-guard-neoforge`
- `outputs/tools/audit_create_contraption_regions_readonly.py`

Deploy the JAR to both server and client mod sets.  The persisted data fix is
applied by the current conversion code on the next conversion from authority;
the guard remains useful as OTA-safe protection against old or partially
converted worlds.
