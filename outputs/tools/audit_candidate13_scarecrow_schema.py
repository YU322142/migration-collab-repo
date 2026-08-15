#!/usr/bin/env python3
"""Audit every Candidate13 scarecrow entity and its cross-version slot schema."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from candidate13_nbt_audit_common import (
    bounded,
    iter_region,
    path_text,
    plain,
    sha256,
    tag_type,
)


SCARECROW_ID = "kaleidoscope_cookery:scarecrow"
LOGICAL_SIZES = {"HandItems": 2, "ArmorItems": 4}


def _uuid_text(entity: dict[str, Any]) -> str | None:
    value = plain(entity.get("UUID"))
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 4:
        number = 0
        for part in value:
            number = (number << 32) | (int(part) & 0xFFFFFFFF)
        raw = f"{number:032x}"
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return None


def _slot_summary(entity: dict[str, Any], key: str) -> dict[str, Any]:
    logical_size = LOGICAL_SIZES[key]
    if key not in entity:
        return {
            "present": False,
            "tag_type": None,
            "logical_size": logical_size,
            "source_list_valid": True,
            "target_handler_compound_valid": True,
            "target_runtime_result": "key absent; target loader skips this container",
        }
    value = entity[key]
    result: dict[str, Any] = {
        "present": True,
        "tag_type": tag_type(value),
        "logical_size": logical_size,
        "value": bounded(value),
    }
    if isinstance(value, (list, tuple)):
        slots = []
        malformed = []
        for index, entry in enumerate(value):
            if not isinstance(entry, dict):
                malformed.append({"index": index, "reason": "entry is not a compound"})
                continue
            raw_slot = plain(entry.get("Slot"))
            if not isinstance(raw_slot, int):
                malformed.append({"index": index, "reason": "missing/non-integer Slot"})
                continue
            slots.append(int(raw_slot))
            if not 0 <= int(raw_slot) < logical_size:
                malformed.append({"index": index, "reason": "Slot outside logical size", "slot": int(raw_slot)})
        result.update(
            {
                "list_length": len(value),
                "slots": slots,
                "source_list_valid": not malformed,
                "source_list_issues": malformed,
                "target_handler_compound_valid": False,
                "target_runtime_result": (
                    "target getCompound() receives a list, yielding an empty/default handler; "
                    "target then reads fixed logical slots and throws from slot 1"
                ),
            }
        )
    elif isinstance(value, dict):
        size = plain(value.get("Size"))
        items = value.get("Items")
        item_list = items if isinstance(items, (list, tuple)) else []
        slots = [plain(entry.get("Slot")) for entry in item_list if isinstance(entry, dict)]
        valid = isinstance(size, int) and int(size) == logical_size and isinstance(items, (list, tuple))
        result.update(
            {
                "handler_size": size,
                "handler_items_length": len(item_list),
                "slots": slots,
                "source_list_valid": False,
                "target_handler_compound_valid": valid,
                "target_runtime_result": "loads with target ItemStackHandler" if valid else "malformed target handler compound",
            }
        )
    else:
        result.update(
            {
                "source_list_valid": False,
                "target_handler_compound_valid": False,
                "target_runtime_result": "unsupported tag type",
            }
        )
    return result


def _visit_entities(
    value: Any,
    parts: list[str | int],
    records: list[dict[str, Any]],
) -> None:
    if isinstance(value, dict):
        if plain(value.get("id")) == SCARECROW_ID:
            records.append(
                {
                    "nbt_path": path_text(parts),
                    "uuid": _uuid_text(value),
                    "pos": plain(value.get("Pos")),
                    "hand_items": _slot_summary(value, "HandItems"),
                    "armor_items": _slot_summary(value, "ArmorItems"),
                    "entity": bounded(value),
                }
            )
        passengers = value.get("Passengers")
        if isinstance(passengers, (list, tuple)):
            for index, child in enumerate(passengers):
                _visit_entities(child, parts + ["Passengers", index], records)


def scan_entity_region(task: tuple[str, str, str]) -> dict[str, Any]:
    label, root_text, path_text_value = task
    root = Path(root_text)
    path = Path(path_text_value)
    relative = str(path.relative_to(root)).replace("\\", "/")
    result: dict[str, Any] = {"label": label, "path": relative, "bytes": path.stat().st_size, "chunks": 0, "records": [], "errors": []}
    try:
        for slot, compression, chunk in iter_region(path):
            result["chunks"] += 1
            entities = chunk.get("Entities", chunk.get("entities"))
            if entities is None and isinstance(chunk.get("Level"), dict):
                level = chunk["Level"]
                entities = level.get("Entities", level.get("entities"))
            if not isinstance(entities, (list, tuple)):
                continue
            for index, entity in enumerate(entities):
                records: list[dict[str, Any]] = []
                _visit_entities(entity, ["Entities", index], records)
                for record in records:
                    record.update({"mca_slot": slot, "compression": compression})
                    result["records"].append(record)
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    return result


def entity_regions(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.mca") if path.parent.name == "entities")


def source_semantics(source_code: Path, target_code: Path) -> dict[str, Any]:
    source = source_code.read_text(encoding="utf-8", errors="replace")
    target = target_code.read_text(encoding="utf-8", errors="replace")
    required_source = [
        "valueOutput.method_71467(HAND_ITEMS_TAG",
        "valueOutput.method_71467(ARMOR_ITEMS_TAG",
        "itemStackWithSlot.method_71368(this.handItems.size())",
        "itemStackWithSlot.method_71368(this.armorItems.size())",
    ]
    required_target = [
        "new ItemStackHandler(this.handItems).serializeNBT",
        "new ItemStackHandler(this.armorItems).serializeNBT",
        "handler = new ItemStackHandler();",
        "tag.getCompound(HAND_ITEMS_TAG)",
        "tag.getCompound(ARMOR_ITEMS_TAG)",
        "handler.getStackInSlot(i)",
    ]
    return {
        "source_1_21_11": {
            "path": str(source_code.resolve()),
            "bytes": source_code.stat().st_size,
            "sha256": sha256(source_code),
            "required_fragments_present": {fragment: fragment in source for fragment in required_source},
            "writer_shape": "list of ItemStackWithSlot entries; absent when empty",
            "reader_semantics": "validates each entry Slot against logical list size (2 hands, 4 armor)",
        },
        "target_1_21_1": {
            "path": str(target_code.resolve()),
            "bytes": target_code.stat().st_size,
            "sha256": sha256(target_code),
            "required_fragments_present": {fragment: fragment in target for fragment in required_target},
            "writer_shape": "NeoForge ItemStackHandler compound with Size and Items",
            "reader_semantics": (
                "uses getCompound + default ItemStackHandler, then reads all 2/4 logical slots; "
                "a source list is therefore not a compatible target payload"
            ),
        },
        "logical_sizes": LOGICAL_SIZES,
    }


def write_markdown(report: dict[str, Any], output: Path) -> None:
    lines = [
        "# Candidate13 scarecrow slot-schema audit",
        "",
        f"- Status: `{report['status']}`",
        f"- Workers: `{report['workers']}`",
        f"- Entity regions: `{report['totals']['region_files']}`",
        f"- Entity chunks: `{report['totals']['chunks']}`",
        f"- Scarecrows: `{report['totals']['scarecrows']}`",
        f"- Source-list containers incompatible with target loader: `{report['totals']['source_list_containers_requiring_conversion']}`",
        f"- Parse errors: `{report['totals']['errors']}`",
        "",
        "## Exact entities",
        "",
    ]
    for index, row in enumerate(report["scarecrows"], 1):
        lines.extend(
            [
                f"{index}. `{row['root_label']}:{row['file']}` slot `{row['mca_slot']}`, "
                f"UUID `{row['uuid']}`, position `{row['pos']}`.",
                f"   - HandItems: `{row['hand_items']['tag_type']}`; target-compatible "
                f"`{row['hand_items']['target_handler_compound_valid']}`.",
                f"   - ArmorItems: `{row['armor_items']['tag_type']}`; target-compatible "
                f"`{row['armor_items']['target_handler_compound_valid']}`; slots "
                f"`{row['armor_items'].get('slots', [])}`.",
            ]
        )
    lines.extend(
        [
            "",
            "## Proven cross-version semantic mismatch",
            "",
            "The 1.21.11 writer stores each non-empty hand/armor item as a slotted entry in an NBT list. "
            "The 1.21.1 target writer and reader use a NeoForge ItemStackHandler compound (`Size` + `Items`). "
            "The target constructs a default one-slot handler and then iterates two hand or four armor slots, "
            "so feeding it a source list produces the observed slot-1 out-of-range exception.",
            "",
            "The JSON report binds this conclusion to hashes and required fragments from both decompiled class sources.",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--source-code", type=Path, required=True)
    parser.add_argument("--target-code", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.workers <= 20:
        parser.error("--workers must be in [1,20]")
    roots = {"source": args.source.resolve(), "staging": args.staging.resolve()}
    for path in (*roots.values(), args.source_code, args.target_code):
        if not path.exists():
            raise FileNotFoundError(path)
    tasks = [(label, str(root), str(path)) for label, root in roots.items() for path in entity_regions(root)]
    per_root = {
        label: {"root": str(root), "region_files": 0, "bytes": 0, "chunks": 0, "scarecrows": 0, "errors": 0}
        for label, root in roots.items()
    }
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(scan_entity_region, task): task for task in tasks}
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            summary = per_root[result["label"]]
            summary["region_files"] += 1
            summary["bytes"] += result["bytes"]
            summary["chunks"] += result["chunks"]
            summary["scarecrows"] += len(result["records"])
            summary["errors"] += len(result["errors"])
            records.extend({"root_label": result["label"], "file": result["path"], **record} for record in result["records"])
            errors.extend({"root_label": result["label"], "file": result["path"], "error": error} for error in result["errors"])
            if completed % 100 == 0 or completed == len(tasks):
                print(json.dumps({"completed": completed, "total": len(tasks), "scarecrows": len(records), "errors": len(errors)}), flush=True)

    records.sort(key=lambda row: (row["root_label"], row["file"], row["mca_slot"], row["nbt_path"]))
    incompatible = sum(
        1
        for row in records
        for key in ("hand_items", "armor_items")
        if row[key]["present"] and row[key]["tag_type"] == "List" and not row[key]["target_handler_compound_valid"]
    )
    semantics = source_semantics(args.source_code, args.target_code)
    fragment_ok = all(
        all(section["required_fragments_present"].values())
        for section in (semantics["source_1_21_11"], semantics["target_1_21_1"])
    )
    status = "PASS" if not errors and fragment_ok else "BLOCKED"
    report: dict[str, Any] = {
        "schema": 1,
        "status": status,
        "category": "candidate13_scarecrow_cross_version_schema_audit",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "entity_id": SCARECROW_ID,
        "workers": args.workers,
        "process_pid": os.getpid(),
        "roots": per_root,
        "totals": {
            "region_files": sum(value["region_files"] for value in per_root.values()),
            "bytes": sum(value["bytes"] for value in per_root.values()),
            "chunks": sum(value["chunks"] for value in per_root.values()),
            "scarecrows": len(records),
            "source_list_containers_requiring_conversion": incompatible,
            "errors": len(errors),
        },
        "semantics": semantics,
        "scarecrows": records,
        "errors": errors,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.output_md)
    print(json.dumps({"status": status, "scarecrows": len(records), "incompatible_containers": incompatible, "errors": len(errors), "json_sha256": sha256(args.output_json), "md_sha256": sha256(args.output_md)}), flush=True)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

