from __future__ import annotations

"""Read-only three-way audit for Create brass-funnel filter NBT.

The scanner never writes a world.  It compares source, converted staging, and
the current Attempt13 runtime by dimension/absolute block coordinate and
records both the funnel block-state and the ``Filter`` item-stack payload.
"""

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import create_storage_object_ota as ota


def dimension_for_region(root: Path, region: Path) -> str:
    relative = region.parent.parent.relative_to(root).as_posix()
    if relative in {"", "."}:
        return "minecraft:overworld"
    if relative == "DIM-1":
        return "minecraft:the_nether"
    if relative == "DIM1":
        return "minecraft:the_end"
    if relative.startswith("dimensions/"):
        return relative[len("dimensions/") :]
    return relative.replace("/", ":")


def value_hash(value: Any) -> str | None:
    if value is ota.MISSING:
        return None
    try:
        return ota.content_hash(value)
    except Exception:
        return ota.sha256_bytes(ota.canonical_json(ota.plain(value)))


def normalized_filter(block_entity: Any) -> dict[str, Any]:
    value = block_entity.get("Filter", ota.MISSING) if isinstance(block_entity, dict) else ota.MISSING
    if value is ota.MISSING:
        return {"present": False, "empty": True, "sha256": None, "value": None}
    plain = ota.plain(value)
    empty = not bool(plain)
    return {"present": True, "empty": empty, "sha256": value_hash(value), "value": plain}


def scan_world(root: Path) -> tuple[list[dict[str, Any]], Counter[str], list[str]]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    errors: list[str] = []
    for region in sorted(root.rglob("r.*.*.mca"), key=lambda p: p.as_posix().lower()):
        # entities/ and poi/ MCA files are not terrain chunks and do not have
        # block entities.  Restrict the audit to each dimension's region dir.
        if region.parent.name != "region":
            continue
        dimension = dimension_for_region(root, region)
        for slot in range(1024):
            try:
                image = ota.read_chunk_image(region, slot)
                if image is None:
                    continue
                for block_entity in ota.block_entity_list(image.chunk):
                    if not isinstance(block_entity, dict):
                        continue
                    if ota.plain(block_entity.get("id")) != "create:funnel":
                        continue
                    pos = ota.be_position(block_entity)
                    if pos is None:
                        continue
                    try:
                        block_state = ota.block_state_at(image.chunk, pos)
                    except ota.OtaError as exc:
                        errors.append(f"{region}:{slot}:{pos}: block-state decode failed: {exc}")
                        continue
                    if block_state.get("Name") != "create:brass_funnel":
                        continue
                    filter_value = normalized_filter(block_entity)
                    classification = "filtered" if filter_value["present"] and not filter_value["empty"] else "unfiltered"
                    counts[classification] += 1
                    counts["brass_funnel"] += 1
                    records.append(
                        {
                            "dimension": dimension,
                            "pos": list(pos),
                            "chunk": [ota.chunk_coordinates(image.chunk)[0], ota.chunk_coordinates(image.chunk)[1]],
                            "region_path": region.relative_to(root).as_posix(),
                            "mca_slot": slot,
                            "block_entity_id": ota.plain(block_entity.get("id")),
                            "block_state": block_state,
                            "filter": filter_value,
                            "block_entity_sha256": value_hash(block_entity),
                        }
                    )
            except Exception as exc:
                errors.append(f"{region}:{slot}: {exc}")
    return records, counts, errors


def index(records: list[dict[str, Any]]) -> dict[tuple[str, tuple[int, int, int]], dict[str, Any]]:
    return {(item["dimension"], tuple(item["pos"])): item for item in records}


def compare_three_way(
    source: list[dict[str, Any]], staging: list[dict[str, Any]], live: list[dict[str, Any]]
) -> dict[str, Any]:
    indexed = {name: index(items) for name, items in (("source", source), ("staging", staging), ("live", live))}
    keys = sorted(set().union(*[set(value) for value in indexed.values()]), key=lambda item: (item[0], item[1]))
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for key in keys:
        values = {name: indexed[name].get(key) for name in indexed}
        src, stg, run = (values["source"], values["staging"], values["live"])
        src_filter = src.get("filter") if src else None
        stg_filter = stg.get("filter") if stg else None
        live_filter = run.get("filter") if run else None
        source_filtered = bool(src_filter and src_filter.get("present") and not src_filter.get("empty"))
        staging_filtered = bool(stg_filter and stg_filter.get("present") and not stg_filter.get("empty"))
        live_filtered = bool(live_filter and live_filter.get("present") and not live_filter.get("empty"))
        if src is None:
            classification = "live_or_staging_only"
        elif not source_filtered:
            classification = "source_unfiltered"
        elif stg is None:
            classification = "source_filtered_staging_missing"
        elif not staging_filtered:
            classification = "source_filter_lost_in_staging"
        elif run is None:
            classification = "runtime_missing"
        elif live_filtered and live_filter.get("sha256") == stg_filter.get("sha256"):
            classification = "preserved"
        elif live_filtered:
            classification = "runtime_filter_changed"
        else:
            classification = "runtime_filter_missing"
        counts[classification] += 1
        rows.append(
            {
                "dimension": key[0],
                "pos": list(key[1]),
                "classification": classification,
                "source": src,
                "staging": stg,
                "live": run,
            }
        )
    return {"counts": dict(sorted(counts.items())), "records": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    scans: dict[str, Any] = {}
    for name, root in (("source", args.source), ("staging", args.staging), ("live", args.live)):
        records, counts, errors = scan_world(root)
        scans[name] = {"root": str(root), "counts": dict(sorted(counts.items())), "records": records, "errors": errors}
    comparison = compare_three_way(scans["source"]["records"], scans["staging"]["records"], scans["live"]["records"])
    result = {
        "schema": 1,
        "read_only": True,
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "worlds": {name: value["root"] for name, value in scans.items()},
        "scan_counts": {name: value["counts"] for name, value in scans.items()},
        "scan_error_counts": {name: len(value["errors"]) for name, value in scans.items()},
        "comparison": comparison,
        "scan_errors": {name: value["errors"] for name, value in scans.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "scan_counts": result["scan_counts"], "comparison": comparison["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
