# Full migrated player-stat audit

The audit input is the read-only staging copy
`D:\Trans\migration-audit-work\cutover-staging-candidate8d-20260811\world\stats`.
It contains 112 JSON files (DataVersion 4671), all 112 parsed successfully.
The deterministic source aggregate hash is
`e5c25837cfd18b307c4d958dd9be22ab6de2a46a7453076d0785ecd36f4cdd20`.

| Source statistic type | Target registry | Unique IDs | References |
| --- | --- | ---: | ---: |
| `minecraft:broken` | `minecraft:item` | 57 | 215 |
| `minecraft:crafted` | `minecraft:item` | 896 | 3,854 |
| `minecraft:custom` | `minecraft:custom_stat` | 76 | 2,789 |
| `minecraft:dropped` | `minecraft:item` | 792 | 3,723 |
| `minecraft:killed` | `minecraft:entity_type` | 76 | 738 |
| `minecraft:killed_by` | `minecraft:entity_type` | 40 | 360 |
| `minecraft:mined` | `minecraft:block` | 947 | 5,285 |
| `minecraft:picked_up` | `minecraft:item` | 1,303 | 8,224 |
| `minecraft:used` | `minecraft:item` | 1,140 | 5,622 |

The complete per-ID inventory, file counts, and source hashes are in
`outputs/happyghast-stat-audit-20260811.json`.

## Modern IDs and static ownership evidence

The source contains two custom IDs that were absent from the earlier target
bundle: `minecraft:happy_ghast_one_cm` occurs in 11 files and
`minecraft:nautilus_one_cm` occurs in 5 files. The new equivalence.2 JAR
registers both IDs and preserves their riding increments.

Other 1.21.11-era IDs in the inventory are covered by these existing target
components:

* Backport 1.5 (`backport-1.5.jar`, SHA-256
  `167534c66d5e6c09dcb01152ebd37d18ced5cf6278a9228c094f937886133af5`):
  Happy Ghast, dried ghast, wildflowers, harnesses, and copper tools/armor.
* Nautilus Equivalence 0.1.0 equivalence.2 (`nautilus-equivalence-0.1.0-
  equivalence.2+mc1.21.1.jar`, SHA-256
  `01ebd831ac5d12d60965168ee10887fb9de81ce660341f420d0c51e9a1e33415`):
  Nautilus/Zombie Nautilus, shell, and Nautilus armor.
* Barched migration.1 ASM (`barched-neoforge-0.0.12-migration.1-asm.jar`,
  SHA-256 `cd93249fa802559886be89f359e69daef1f38919f4b376b88ba1e2ce78f1bd4b`):
  wooden, stone, iron, golden, diamond, and netherite spear IDs.

Resource/model presence is only static evidence. It is deliberately not
treated as proof that the final assembled runtime registry contains every ID.

## Fail-closed result

The generated report is currently **BLOCKED**, because no runtime registry
manifest was supplied. This is intentional: a PASS without an actual target
registry snapshot would recreate the same silent-loss failure mode.

NeoForge provides the required snapshot command (permission level 4) on a
fresh candidate server:

```text
/neoforge dump registry minecraft:item true false
/neoforge dump registry minecraft:block true false
/neoforge dump registry minecraft:entity_type true false
/neoforge dump registry minecraft:custom_stat true false
```

Then run the audit against the server's `dumps/registry` directory:

```text
python tools/audit_player_stats_registry.py \
  --stats-dir D:\Trans\migration-audit-work\cutover-staging-candidate8d-20260811\world\stats \
  --target-dump-dir <fresh-candidate>\dumps\registry \
  --report outputs\happyghast-stat-audit-runtime-20260811.json
```

The command exits `0` only when every source ID is present in the corresponding
runtime registry and all four dump files are non-empty. Missing files, malformed
JSON, unknown statistic types, invalid IDs, missing IDs, or absent runtime
evidence all exit `2` and keep the report `BLOCKED`.

## Integration gate

Install the same new JAR on both sides only through the established candidate
bundle workflow. Do not copy it into a locked candidate or a production/source
backup by hand. The reproducible artifact is:

`D:\Trans\migration-audit-work\HappyGhast-1.21.1-equivalence\build\libs\happyghast-equivalence-1.0.0-equivalence.2+mc1.21.1.jar`

Size: 12,277 bytes. SHA-256 from two independent `clean check jar` runs:
`f715d0065beeec583b5edeef3dcd28d4e9dfcc3d5e9b5fe55e9df26c945d82e8`.
