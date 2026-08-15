"""Read-only full-world audit of block-entity ids against block states.

The audit decodes every occupied chunk in the three vanilla Anvil region
trees.  For every block entity it resolves the section palette at the stored
``x/y/z`` coordinate, then compares an immutable source world with a fresh
pre-Java conversion target.  It deliberately reports the raw evidence and
uses only a small, explicit registry map for Create; air/void-air is always a
definite mismatch because no block entity type can be valid on an air block.

This is an audit tool, not a repair tool.  It never writes either world.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import io
import json
import math
import re
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import nbtlib


DIMENSIONS = {
    "minecraft:overworld": Path("."),
    "minecraft:the_nether": Path("DIM-1"),
    "minecraft:the_end": Path("DIM1"),
}
REGION_NAME = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
AIR_IDS = {
    "minecraft:air",
    "minecraft:cave_air",
    "minecraft:void_air",
    "minecraft:structure_void",
}
DYE_COLORS = (
    "white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
    "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black",
)


def value(tag: Any) -> Any:
    """Unwrap nbtlib scalar/array tags without changing the source file."""
    if tag is None:
        return None
    if hasattr(tag, "unpack"):
        try:
            return tag.unpack()
        except Exception:
            pass
    if hasattr(tag, "tolist"):
        try:
            return tag.tolist()
        except Exception:
            pass
    if hasattr(tag, "value"):
        try:
            return tag.value
        except Exception:
            pass
    return tag


def plain(tag: Any) -> Any:
    tag = value(tag)
    if isinstance(tag, dict):
        return {str(k): plain(v) for k, v in tag.items()}
    if isinstance(tag, (list, tuple)):
        return [plain(v) for v in tag]
    if isinstance(tag, (str, int, float, bool)) or tag is None:
        return tag
    return str(tag)


def sequence(tag: Any) -> list[Any]:
    """Return an NBT list/array as ordinary Python values.

    ``LongArray`` is not necessarily a ``list`` in every nbtlib release, so
    checking the wrapper type before unwrapping silently loses packed block
    state data.  Always unwrap first, then copy the sequence.
    """
    unwrapped = value(tag)
    if hasattr(unwrapped, "tolist"):
        try:
            unwrapped = unwrapped.tolist()
        except Exception:
            pass
    if isinstance(unwrapped, (list, tuple)):
        return list(unwrapped)
    return []


def decompress(payload: bytes, compression: int) -> bytes:
    compression &= 0x7F
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported compression type {compression}")


def root_value(root: Any, *names: str) -> Any:
    for name in names:
        if name in root:
            return root[name]
    level = root.get("Level") if isinstance(root, dict) else None
    if isinstance(level, dict):
        for name in names:
            if name in level:
                return level[name]
    return None


def region_coords(name: str) -> tuple[int, int] | None:
    match = REGION_NAME.fullmatch(name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def slot_chunk(coords: tuple[int, int], slot: int) -> tuple[int, int]:
    return coords[0] * 32 + (slot & 31), coords[1] * 32 + (slot >> 5)


def state_name(entry: Any) -> str:
    if not isinstance(entry, dict):
        return "<invalid-palette-entry>"
    raw = entry.get("Name", entry.get("name", "minecraft:air"))
    return str(value(raw))


def state_properties(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    raw = entry.get("Properties", entry.get("properties", {}))
    data = plain(raw)
    return data if isinstance(data, dict) else {}


def block_at(section: Any, local_x: int, local_y: int, local_z: int) -> dict[str, Any]:
    if not isinstance(section, dict):
        return {"name": "minecraft:air", "properties": {}, "decode": "missing_section"}
    container = section.get("block_states", section.get("BlockStates"))
    if not isinstance(container, dict):
        return {"name": "minecraft:air", "properties": {}, "decode": "missing_container"}
    palette = sequence(container.get("palette", container.get("Palette", [])))
    if not palette:
        return {"name": "<missing-palette>", "properties": {}, "decode": "missing_palette"}
    data = sequence(container.get("data", container.get("Data")))
    index = (local_y * 16 + local_z) * 16 + local_x
    palette_index = 0
    if len(palette) > 1:
        if not data:
            return {"name": "<missing-packed-data>", "properties": {}, "decode": "missing_data"}
        bits = max(4, (len(palette) - 1).bit_length())
        values_per_long = 64 // bits
        long_index = index // values_per_long
        if long_index >= len(data):
            return {"name": "<packed-data-overrun>", "properties": {}, "decode": "data_overrun"}
        raw = int(value(data[long_index])) & 0xFFFFFFFFFFFFFFFF
        palette_index = (raw >> ((index % values_per_long) * bits)) & ((1 << bits) - 1)
    if palette_index >= len(palette):
        return {"name": "<invalid-palette-index>", "properties": {}, "decode": "invalid_index"}
    return {
        "name": state_name(palette[palette_index]),
        "properties": state_properties(palette[palette_index]),
        "decode": "ok",
    }


def parse_chunk(root: Any, region: str, slot: int, coords: tuple[int, int]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sections_raw = root_value(root, "sections", "Sections")
    sections: dict[int, Any] = {}
    for section in sequence(sections_raw):
            if not isinstance(section, dict):
                continue
            raw_y = value(section.get("Y", section.get("y")))
            try:
                sections[int(raw_y)] = section
            except (TypeError, ValueError):
                continue
    entities = root_value(root, "block_entities", "BlockEntities", "blockEntities")
    errors: list[dict[str, Any]] = []
    if entities is None:
        return [], errors
    entities = sequence(entities)
    if not entities:
        # An absent list and an empty list are both valid and have no records;
        # preserve malformed non-list values as an explicit error below.
        raw_entities = root_value(root, "block_entities", "BlockEntities", "blockEntities")
        if raw_entities is None:
            return [], errors
        if not isinstance(value(raw_entities), (list, tuple)):
            return [], [{"region": region, "slot": slot, "reason": "block_entities_not_list"}]
    chunk_x, chunk_z = slot_chunk(coords, slot)
    records: list[dict[str, Any]] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            errors.append({"region": region, "slot": slot, "index": index, "reason": "block_entity_not_compound"})
            continue
        identifier = value(entity.get("id"))
        identifier = str(identifier) if identifier is not None else "<missing-id>"
        raw_pos = [value(entity.get(axis)) for axis in ("x", "y", "z")]
        if not all(type(axis) is int for axis in raw_pos):
            records.append({
                "region": region, "slot": slot, "index": index,
                "chunk": [chunk_x, chunk_z], "pos": raw_pos,
                "id": identifier,
                "block": {"name": "<unknown-position>", "properties": {}, "decode": "invalid_position"},
            })
            continue
        x, y, z = raw_pos
        section_y = math.floor(y / 16)
        state = block_at(sections.get(section_y), x & 15, y & 15, z & 15)
        records.append({
            "region": region,
            "slot": slot,
            "index": index,
            "chunk": [chunk_x, chunk_z],
            "pos": [x, y, z],
            "id": identifier,
            "block": state,
        })
    return records, errors


def read_region(path: Path, dimension: str) -> dict[str, Any]:
    data = path.read_bytes()
    relative = path.relative_to(path.parents[1]).as_posix()
    result: dict[str, Any] = {
        "dimension": dimension,
        "region": relative,
        "files": 1,
        "occupied_slots": 0,
        "records": [],
        "errors": [],
    }
    coords = region_coords(path.name)
    if coords is None:
        result["errors"].append({"reason": "invalid_region_name"})
        return result
    if len(data) < 8192:
        if data:
            result["errors"].append({"reason": "short_header", "bytes": len(data)})
        return result
    sector_count = (len(data) + 4095) // 4096
    for slot in range(1024):
        entry = data[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if not offset:
            continue
        result["occupied_slots"] += 1
        if offset < 2 or sectors < 1 or offset + sectors > sector_count:
            result["errors"].append({"slot": slot, "reason": "invalid_chunk_extent", "offset": offset, "sectors": sectors})
            continue
        start = offset * 4096
        length = int.from_bytes(data[start : start + 4], "big")
        compression = data[start + 4]
        if compression & 0x80:
            result["errors"].append({"slot": slot, "reason": "external_chunk_payload"})
            continue
        if length < 1 or length > sectors * 4096 - 4:
            result["errors"].append({"slot": slot, "reason": "invalid_chunk_length", "length": length})
            continue
        payload = data[start + 5 : start + 4 + length]
        try:
            root = nbtlib.File.parse(io.BytesIO(decompress(payload, compression)), byteorder="big")
            records, errors = parse_chunk(root, path.name, slot, coords)
            for record in records:
                record["dimension"] = dimension
            result["records"].extend(records)
            result["errors"].extend(errors)
        except Exception as exc:
            result["errors"].append({"slot": slot, "reason": "nbt_decode_error", "error": f"{type(exc).__name__}: {exc}"})
    return result


def discover_regions(root: Path) -> list[tuple[str, Path]]:
    jobs: list[tuple[str, Path]] = []
    for dimension, relative in DIMENSIONS.items():
        directory = root / relative / "region"
        if not directory.is_dir():
            continue
        jobs.extend((dimension, path) for path in sorted(directory.glob("r.*.*.mca")))
    return jobs


def parse_world(root: Path, workers: int) -> dict[str, Any]:
    jobs = discover_regions(root)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    occupied_slots = 0
    completed = 0
    print(json.dumps({"phase": "discover", "root": str(root), "regions": len(jobs)}), flush=True)
    # NBT decoding is CPU-bound and nbtlib holds the GIL.  Processes are
    # required here so ``--workers 20`` actually uses the available cores.
    with ProcessPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(read_region, path, dimension): (dimension, path) for dimension, path in jobs}
        for future in as_completed(futures):
            result = future.result()
            records.extend(result["records"])
            errors.extend({"region": result["region"], **error} for error in result["errors"])
            occupied_slots += result["occupied_slots"]
            completed += 1
            if completed == len(jobs) or completed % 100 == 0:
                print(json.dumps({"phase": "parse", "completed": completed, "total": len(jobs), "block_entities": len(records)}), flush=True)
    records.sort(key=lambda item: (item.get("dimension", ""), tuple(item.get("pos") or (10**30, 10**30, 10**30)), item.get("id", ""), item.get("region", ""), item.get("slot", -1), item.get("index", -1)))
    return {
        "root": str(root.resolve()),
        "region_files": len(jobs),
        "occupied_chunk_slots": occupied_slots,
        "records": records,
        "errors": errors,
    }


def parse_registry_map(path: Path | None) -> dict[str, set[str]]:
    """Extract Create's valid block names from its decompiled registration.

    The extraction is intentionally conservative: a missing/unparsed entry is
    treated as unknown, never as invalid.  This keeps the audit from inventing
    false positives for third-party mods.
    """
    if path is None or not path.is_dir():
        return {}
    blocks_file = next(path.rglob("AllBlocks.java"), None)
    entities_file = next(path.rglob("AllBlockEntityTypes.java"), None)
    if blocks_file is None or entities_file is None:
        return {}
    blocks_text = blocks_file.read_text(encoding="utf-8", errors="replace")
    entities_text = entities_file.read_text(encoding="utf-8", errors="replace")
    field_to_name: dict[str, str] = {}
    # CFR leaves one declaration per line in this source.  The fallback regex
    # also handles declarations split across a line by a formatter.
    block_pattern = re.compile(r"REGISTRATE\.block\(\s*\"([^\"]+)\"", re.S)
    for line in blocks_text.splitlines():
        fields = re.findall(r"\b([A-Z][A-Z0-9_]*)\b\s*=\s*", line)
        match = block_pattern.search(line)
        if not match or not fields:
            continue
        field_to_name[fields[-1]] = "create:" + match.group(1)
    result: dict[str, set[str]] = {}
    for line in entities_text.splitlines():
        match = re.search(r"blockEntity\(\s*\"([^\"]+)\"", line)
        if not match:
            continue
        identifier = "create:" + match.group(1)
        names = {
            field_to_name[field]
            for field in re.findall(r"AllBlocks\.([A-Z][A-Z0-9_]*)", line)
            if field in field_to_name
        }
        if names:
            result[identifier] = names
    # These registrations use DyedBlockList/TrackMaterial collections, which
    # cannot be expanded from the literal AllBlocks field references above.
    result.setdefault("create:table_cloth", set()).update(
        {f"create:{colour}_table_cloth" for colour in DYE_COLORS}
    )
    result.setdefault("create:toolbox", set()).update(
        {f"create:{colour}_toolbox" for colour in DYE_COLORS}
    )
    result.setdefault("create:package_postbox", set()).update(
        {f"create:{colour}_postbox" for colour in DYE_COLORS}
    )
    return result


def pair(record: dict[str, Any]) -> tuple[str, str]:
    block = record.get("block") or {}
    return str(record.get("id", "<missing-id>")), str(block.get("name", "<unknown>"))


def compatibility(record: dict[str, Any], registry: dict[str, set[str]]) -> tuple[bool | None, str]:
    identifier = str(record.get("id", ""))
    state = str((record.get("block") or {}).get("name", "<unknown>"))
    if state in AIR_IDS:
        return False, "air_state"
    if state.startswith("<"):
        return False, "decode_error"
    if state == identifier:
        return True, "exact_id_state"
    allowed = registry.get(identifier)
    if allowed is not None:
        return state in allowed, "create_registry" if state in allowed else "create_registry_mismatch"
    # No static registry is available for the third-party type.  Preserve it
    # as unknown rather than claiming that a naming alias is invalid.
    return None, "unmapped_registry"


def classify_world(world: dict[str, Any], registry: dict[str, set[str]]) -> dict[str, Any]:
    pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    id_counts: collections.Counter[str] = collections.Counter()
    state_counts: collections.Counter[str] = collections.Counter()
    strict: list[dict[str, Any]] = []
    unknown = 0
    for record in world["records"]:
        identifier, state = pair(record)
        pair_counts[(identifier, state)] += 1
        id_counts[identifier] += 1
        state_counts[state] += 1
        ok, reason = compatibility(record, registry)
        record["compatibility"] = ok
        record["compatibility_reason"] = reason
        if ok is None:
            unknown += 1
        elif not ok:
            strict.append(record)
    world["summary"] = {
        "block_entities": len(world["records"]),
        "unique_ids": len(id_counts),
        "unique_pairs": len(pair_counts),
        "id_counts": dict(sorted(id_counts.items())),
        "state_counts": dict(sorted(state_counts.items())),
        "pair_counts": {f"{identifier}|{state}": count for (identifier, state), count in sorted(pair_counts.items())},
        "strict_mismatch_count": len(strict),
        "strict_mismatch_by_reason": dict(collections.Counter(item["compatibility_reason"] for item in strict)),
        "unmapped_registry_count": unknown,
        "parse_error_count": len(world["errors"]),
    }
    world["strict_mismatches"] = strict
    return world


def coord_key(record: dict[str, Any]) -> tuple[Any, ...] | None:
    pos = record.get("pos")
    if not (isinstance(pos, list) and len(pos) == 3 and all(type(v) is int for v in pos)):
        return None
    return (record.get("dimension"), *pos)


def compare_worlds(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_by_coord: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    target_by_coord: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(list)
    for record in source["records"]:
        key = coord_key(record)
        if key is not None:
            source_by_coord[key].append(record)
    for record in target["records"]:
        key = coord_key(record)
        if key is not None:
            target_by_coord[key].append(record)
    for values in source_by_coord.values():
        values.sort(key=lambda item: (item.get("id", ""), item.get("region", ""), item.get("slot", -1), item.get("index", -1)))
    for values in target_by_coord.values():
        values.sort(key=lambda item: (item.get("id", ""), item.get("region", ""), item.get("slot", -1), item.get("index", -1)))

    def evidence(record: dict[str, Any], side: str) -> dict[str, Any]:
        return {
            "side": side,
            "dimension": record.get("dimension"),
            "pos": record.get("pos"),
            "id": record.get("id"),
            "block": record.get("block"),
            "compatibility": record.get("compatibility"),
            "compatibility_reason": record.get("compatibility_reason"),
            "region": record.get("region"),
            "slot": record.get("slot"),
            "index": record.get("index"),
        }

    source_inherited: list[dict[str, Any]] = []
    conversion_created: list[dict[str, Any]] = []
    conversion_resolved: list[dict[str, Any]] = []
    source_only: list[dict[str, Any]] = []
    target_only: list[dict[str, Any]] = []
    changed_pairs: list[dict[str, Any]] = []
    for key in sorted(set(source_by_coord) | set(target_by_coord), key=str):
        left = source_by_coord.get(key, [])
        right = target_by_coord.get(key, [])
        if not left:
            target_only.extend(evidence(item, "target") for item in right)
            continue
        if not right:
            source_only.extend(evidence(item, "source") for item in left)
            continue
        max_len = max(len(left), len(right))
        for index in range(max_len):
            source_item = left[index] if index < len(left) else None
            target_item = right[index] if index < len(right) else None
            if source_item is None:
                target_only.append(evidence(target_item, "target"))
                continue
            if target_item is None:
                source_only.append(evidence(source_item, "source"))
                continue
            if pair(source_item) != pair(target_item):
                changed_pairs.append({"source": evidence(source_item, "source"), "target": evidence(target_item, "target")})
            source_bad = source_item.get("compatibility") is False
            target_bad = target_item.get("compatibility") is False
            if target_bad and source_bad:
                source_inherited.append({"source": evidence(source_item, "source"), "target": evidence(target_item, "target")})
            elif target_bad and not source_bad:
                conversion_created.append({"source": evidence(source_item, "source"), "target": evidence(target_item, "target")})
            elif source_bad and not target_bad:
                conversion_resolved.append({"source": evidence(source_item, "source"), "target": evidence(target_item, "target")})
    return {
        "source_records": len(source["records"]),
        "target_records": len(target["records"]),
        "source_strict_mismatch_count": source["summary"]["strict_mismatch_count"],
        "target_strict_mismatch_count": target["summary"]["strict_mismatch_count"],
        "source_inherited_count": len(source_inherited),
        "conversion_created_count": len(conversion_created),
        "conversion_resolved_count": len(conversion_resolved),
        "source_only_count": len(source_only),
        "target_only_count": len(target_only),
        "changed_pair_count": len(changed_pairs),
        "source_inherited": source_inherited,
        "conversion_created": conversion_created,
        "conversion_resolved": conversion_resolved,
        "source_only": source_only,
        "target_only": target_only,
        "changed_pairs": changed_pairs,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    source = report["source"]["summary"]
    target = report["target"]["summary"]
    compare = report["comparison"]
    lines = [
        "# Block Entity / Block State Consistency Audit",
        "",
        "Read-only audit. Source is immutable; target was inspected before any Java launch.",
        "",
        "## Totals",
        "",
        f"- Source: `{report['source']['root']}`; regions `{report['source']['region_files']}`, occupied chunks `{report['source']['occupied_chunk_slots']}`, block entities `{source['block_entities']}`.",
        f"- Target: `{report['target']['root']}`; regions `{report['target']['region_files']}`, occupied chunks `{report['target']['occupied_chunk_slots']}`, block entities `{target['block_entities']}`.",
        f"- Strict mismatches (source/target): `{source['strict_mismatch_count']}` / `{target['strict_mismatch_count']}`.",
        f"- Conversion-created: `{compare['conversion_created_count']}`; source-inherited: `{compare['source_inherited_count']}`; resolved: `{compare['conversion_resolved_count']}`.",
        f"- Coordinate-only changes: source-only `{compare['source_only_count']}`, target-only `{compare['target_only_count']}`, changed pairs `{compare['changed_pair_count']}`.",
        "",
        "Strict mismatch means air/void-air, a palette decode error, or a Create id whose state is outside the decompiled target registry valid-block set. Third-party ids without a static map are retained as `unmapped_registry`, never treated as invalid.",
        "",
        "## Definite Mismatches",
        "",
        "| Classification | Count |",
        "|---|---:|",
        f"| Source-inherited | {compare['source_inherited_count']} |",
        f"| Conversion-created | {compare['conversion_created_count']} |",
        f"| Conversion-resolved | {compare['conversion_resolved_count']} |",
        "",
    ]
    for title, rows in (
        ("Source-inherited", compare["source_inherited"]),
        ("Conversion-created", compare["conversion_created"]),
        ("Conversion-resolved", compare["conversion_resolved"]),
    ):
        lines += [f"### {title}", ""]
        if not rows:
            lines.append("None.")
        else:
            lines += ["| Dimension | Position | ID | Block state | Reason |", "|---|---|---|---|---|"]
            for row in rows:
                item = row["target"] if title != "Conversion-resolved" else row["source"]
                state = item.get("block", {}).get("name", "<unknown>")
                lines.append(f"| `{item.get('dimension')}` | `{item.get('pos')}` | `{item.get('id')}` | `{state}` | `{item.get('compatibility_reason')}` |")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--create-decompile", type=Path, default=Path("D:/Trans/migration-audit-work/fluid-target-review-20260811"))
    parser.add_argument("--workers", type=int, default=20)
    args = parser.parse_args()
    registry = parse_registry_map(args.create_decompile)
    print(json.dumps({"phase": "registry", "create_entries": len(registry)}), flush=True)
    source = classify_world(parse_world(args.source, args.workers), registry)
    target = classify_world(parse_world(args.target, args.workers), registry)
    report = {
        "schema": 1,
        "read_only": True,
        "source": {key: value for key, value in source.items() if key != "records"},
        "target": {key: value for key, value in target.items() if key != "records"},
        "comparison": compare_worlds(source, target),
        "registry": {identifier: sorted(states) for identifier, states in sorted(registry.items())},
    }
    # Keep only exact anomaly records plus compact summaries in the persisted
    # report.  Full raw records are not needed to verify the listed findings.
    report["source"]["strict_mismatches"] = source["strict_mismatches"]
    report["target"]["strict_mismatches"] = target["strict_mismatches"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(report, args.markdown)
    print(json.dumps({
        "status": "PASS" if not report["comparison"]["conversion_created"] else "FAIL",
        "source_block_entities": source["summary"]["block_entities"],
        "target_block_entities": target["summary"]["block_entities"],
        "source_strict_mismatches": source["summary"]["strict_mismatch_count"],
        "target_strict_mismatches": target["summary"]["strict_mismatch_count"],
        "conversion_created": report["comparison"]["conversion_created_count"],
        "source_inherited": report["comparison"]["source_inherited_count"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
