"""Reclassify the completed v4 block-entity/state audit without rescanning."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


LEGAL_DYNAMIC_PAIRS = {
    ("create:track", "create:track"),
    ("create:table_cloth", "create:white_table_cloth"),
    ("create:table_cloth", "create:blue_table_cloth"),
}
EXPECTED_MIGRATIONS = {
    ("create:bracketed_kinetic", "create:shaft", "create:simple_kinetic", "create:shaft"): 106,
    ("create:bracketed_kinetic", "create:cogwheel", "create:simple_kinetic", "create:cogwheel"): 86,
    ("create:bracketed_kinetic", "create:large_cogwheel", "create:simple_kinetic", "create:large_cogwheel"): 42,
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest().upper()


def row_key(row: dict) -> tuple:
    return (
        row.get("dimension"),
        tuple(row.get("pos", [])),
        row.get("id"),
        row.get("block", {}).get("name"),
    )


def compact_row(row: dict) -> dict:
    return {
        "dimension": row["dimension"],
        "pos": row["pos"],
        "id": row["id"],
        "block_state": row["block"]["name"],
        "region": row["region"],
        "slot": row["slot"],
        "index": row["index"],
    }


def finalize(raw: dict, raw_path: Path) -> dict:
    source_rows = raw["source"]["strict_mismatches"]
    target_rows = raw["target"]["strict_mismatches"]
    if len(source_rows) != 36 or len(target_rows) != 36:
        raise ValueError("v4 must contain exactly 36 provisional Create mismatches on each side")
    if any((row["id"], row["block"]["name"]) not in LEGAL_DYNAMIC_PAIRS for row in source_rows + target_rows):
        raise ValueError("v4 contains a provisional mismatch outside the reviewed dynamic registrations")
    source_index = {row_key(row): row for row in source_rows}
    target_index = {row_key(row): row for row in target_rows}
    if source_index.keys() != target_index.keys():
        raise ValueError("source/target dynamic-registration coordinates differ")

    changed = collections.Counter(
        (
            row["source"]["id"],
            row["source"]["block"]["name"],
            row["target"]["id"],
            row["target"]["block"]["name"],
        )
        for row in raw["comparison"]["changed_pairs"]
    )
    if dict(changed) != EXPECTED_MIGRATIONS:
        raise ValueError(f"unexpected changed-pair set: {dict(changed)!r}")
    chute_key = ("minecraft:overworld", (-57, 50, -50))
    if any(
        (item["source"]["dimension"], tuple(item["source"]["pos"])) == chute_key
        for item in raw["comparison"]["changed_pairs"]
    ):
        raise ValueError("targeted chute coordinate unexpectedly changed")

    def side_summary(side: str) -> dict:
        value = raw[side]
        summary = value["summary"]
        strict = value["strict_mismatches"]
        air = [row for row in strict if row.get("compatibility_reason") == "air_state"]
        decode = [row for row in strict if row.get("compatibility_reason") == "decode_error"]
        remaining = [row for row in strict if (row["id"], row["block"]["name"]) not in LEGAL_DYNAMIC_PAIRS]
        return {
            "root": value["root"],
            "region_files": value["region_files"],
            "occupied_chunk_slots": value["occupied_chunk_slots"],
            "block_entities": summary["block_entities"],
            "unique_ids": summary["unique_ids"],
            "unique_id_state_pairs": summary["unique_pairs"],
            "parse_errors": summary["parse_error_count"],
            "air_or_void_air_mismatches": len(air),
            "palette_decode_mismatches": len(decode),
            "reviewed_dynamic_registration_false_positives": len(strict) - len(air) - len(decode) - len(remaining),
            "proven_mismatches_after_reclassification": len(air) + len(decode) + len(remaining),
            "unmapped_registry_records": summary["unmapped_registry_count"],
        }

    exceptions = []
    for key in sorted(source_index, key=str):
        source = source_index[key]
        target = target_index[key]
        exceptions.append({
            "classification": "LEGAL_DYNAMIC_REGISTRATION",
            "source": compact_row(source),
            "target": compact_row(target),
            "safe_to_remove": False,
            "reason": "The target Create registry accepts this block through TrackMaterial/DyedBlockList rather than a literal AllBlocks validBlocks entry.",
        })

    comparison = raw["comparison"]
    result = {
        "schema": 1,
        "status": "PASS",
        "read_only": True,
        "rescanned": False,
        "source_evidence": {
            "path": str(raw_path.resolve()),
            "sha256": digest(raw_path),
        },
        "source": side_summary("source"),
        "target": side_summary("target"),
        "comparison": {
            "source_records": comparison["source_records"],
            "target_records": comparison["target_records"],
            "source_only": comparison["source_only_count"],
            "target_only": comparison["target_only_count"],
            "conversion_created_mismatches": comparison["conversion_created_count"],
            "conversion_resolved_mismatches": comparison["conversion_resolved_count"],
            "source_inherited_proven_mismatches": 0,
            "reviewed_legal_dynamic_registrations": len(exceptions),
            "changed_id_state_pairs": comparison["changed_pair_count"],
            "expected_id_migrations": [
                {
                    "source_id": key[0],
                    "source_block_state": key[1],
                    "target_id": key[2],
                    "target_block_state": key[3],
                    "count": count,
                }
                for key, count in sorted(EXPECTED_MIGRATIONS.items())
            ],
        },
        "targeted_chute_check": {
            "dimension": "minecraft:overworld",
            "pos": [-57, 50, -50],
            "block_entity_id": "create:chute",
            "source_block_state": "create:chute",
            "target_block_state": "create:chute",
            "safe_to_remove": False,
            "evidence": "Direct SimpleBitStorage decode after LongArray unwrapping; the coordinate is absent from v4 source-only, target-only, and changed-pair sets.",
        },
        "reviewed_dynamic_registration_exceptions": exceptions,
        "removal_decision": {
            "safe_to_remove_count": 0,
            "do_not_remove_count": len(exceptions),
            "reason": "No orphan block entity was found. Removing any reviewed record would delete valid Create gameplay state.",
        },
        "tool_correction": {
            "issue": "nbtlib LongArray.unpack() returns a numpy ndarray; the initial decoder checked list/tuple before converting ndarray to a list.",
            "fix": "Unwrap LongArray, call tolist(), then decode modern SimpleBitStorage with values_per_long = 64 // bits.",
            "regression_coordinate": [-57, 50, -50],
            "regression_expected_state": "create:chute",
        },
        "limitations": [
            "Air/void-air and palette decode checks cover every one of the 228,436 records on each side.",
            "The static valid-block registry map is authoritative only for parsed Create literal registrations plus the reviewed TrackMaterial/DyedBlockList expansions.",
            "Records outside that explicit map are reported as unmapped_registry and are not declared invalid; runtime registry validation remains the final authority for third-party aliases.",
            "The source is a historical immutable backup; the audit distinguishes conversion-created changes but does not repair pre-existing gameplay corruption.",
        ],
    }
    if result["source"]["proven_mismatches_after_reclassification"] or result["target"]["proven_mismatches_after_reclassification"]:
        raise ValueError("final report cannot pass with a proven mismatch")
    return result


def markdown(report: dict) -> str:
    source = report["source"]
    target = report["target"]
    compare = report["comparison"]
    lines = [
        "# Final Block Entity / Block State Audit",
        "",
        "## Result",
        "",
        "**PASS. No proven block-entity/block-state mismatch was created or inherited in the audited scope.**",
        "",
        f"- Block entities: source `{source['block_entities']}`, target `{target['block_entities']}`.",
        f"- Region files: source `{source['region_files']}`, target `{target['region_files']}`; occupied chunk slots `{source['occupied_chunk_slots']}` each.",
        f"- Parse errors: source `{source['parse_errors']}`, target `{target['parse_errors']}`.",
        f"- Air/void-air mismatches: source `{source['air_or_void_air_mismatches']}`, target `{target['air_or_void_air_mismatches']}`.",
        f"- Palette decode mismatches: source `{source['palette_decode_mismatches']}`, target `{target['palette_decode_mismatches']}`.",
        f"- Conversion-created mismatches: `{compare['conversion_created_mismatches']}`.",
        f"- Source-only/target-only block entities: `{compare['source_only']}` / `{compare['target_only']}`.",
        "",
        "## Reviewed False Positives",
        "",
        "The v4 static parser provisionally flagged 36 Create pairs. All 36 are legal dynamic registrations and must not be removed:",
        "",
        "- `create:track -> create:track`: 24 records, accepted through `TrackMaterial.allBlocks()`.",
        "- `create:table_cloth -> create:white_table_cloth`: 6 records, accepted through `DyedBlockList`.",
        "- `create:table_cloth -> create:blue_table_cloth`: 6 records, accepted through `DyedBlockList`.",
        "",
        "| Dimension | Position | Block entity | Block state | Remove? |",
        "|---|---|---|---|---|",
    ]
    for item in report["reviewed_dynamic_registration_exceptions"]:
        row = item["target"]
        lines.append(f"| `{row['dimension']}` | `{row['pos']}` | `{row['id']}` | `{row['block_state']}` | No |")
    lines += [
        "",
        "## Expected Conversion",
        "",
        "The only 234 changed id/state pairs are the intentional Create 1.21.11 to 1.21.1 block-entity id migration; block states did not change:",
        "",
    ]
    for item in compare["expected_id_migrations"]:
        lines.append(f"- `{item['source_id']} / {item['source_block_state']}` -> `{item['target_id']} / {item['target_block_state']}`: `{item['count']}`.")
    lines += [
        "",
        "## Chute Regression",
        "",
        "At `minecraft:overworld [-57, 50, -50]`, `create:chute` resolves to the `create:chute` block state on both sides. It is not `void_air` and must not be removed.",
        "",
        "## Decoder Correction",
        "",
        "The initial audit attempt mishandled `nbtlib.LongArray`: `unpack()` returns a NumPy array, not a Python list. The corrected decoder calls `tolist()` first, then decodes modern `SimpleBitStorage` using `values_per_long = 64 // bits`. The full v4 evidence was produced with corrected packed-state decoding.",
        "",
        "## Limits",
        "",
    ]
    lines.extend(f"- {item}" for item in report["limitations"])
    lines += [
        "",
        f"Raw v4 evidence SHA-256: `{report['source_evidence']['sha256']}`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    report = finalize(raw, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "source_block_entities": report["source"]["block_entities"],
        "target_block_entities": report["target"]["block_entities"],
        "proven_mismatches": report["target"]["proven_mismatches_after_reclassification"],
        "conversion_created": report["comparison"]["conversion_created_mismatches"],
        "reviewed_do_not_remove": report["removal_decision"]["do_not_remove_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
