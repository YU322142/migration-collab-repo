from __future__ import annotations

import argparse
import gzip
import io
import json
import sys
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from nbt import nbt

import convert_create_fluid_nbt as fluid_converter


def _scalar(value):
    return getattr(value, "value", None)


def _decode(payload, kind):
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def _read_slots(path):
    data = path.read_bytes()
    if len(data) < 8192:
        if data:
            raise ValueError("non-empty region is shorter than its header")
        return
    locations = data[:4096]
    for slot in range(1024):
        entry = locations[slot * 4:(slot + 1) * 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if not offset:
            continue
        start = offset * 4096
        allocation_end = start + sectors * 4096
        if not sectors or offset < 2 or start + 5 > len(data):
            raise ValueError(f"invalid slot allocation at {slot}")
        length = int.from_bytes(data[start:start + 4], "big")
        if length < 1 or start + 4 + length > min(len(data), allocation_end):
            raise ValueError(f"invalid payload length at slot {slot}")
        yield slot, data[start + 4], data[start + 5:start + 4 + length]


def _owner_metadata(owner):
    result = {"owner_id": _scalar(owner.get("id"))}
    coords = [_scalar(owner.get(key)) for key in ("x", "y", "z")]
    if all(isinstance(value, int) for value in coords):
        result["owner_pos"] = coords
    else:
        pos = owner.get("Pos")
        if isinstance(pos, nbt.TAG_List) and len(pos) >= 3:
            result["owner_pos"] = [_scalar(pos[index]) for index in range(3)]
    return result


def _collect_tree(owner, base_path, metadata):
    records = []
    for record in fluid_converter.audit_source_fluid_tree(owner, base_path):
        records.append({"kind": "fluid_stack", **metadata, **record})
    for record in fluid_converter.audit_source_mounted_storages(owner, base_path):
        records.append({"kind": "mounted_storage", **metadata, **record})
    return records


def scan_region(path, world):
    relative = path.relative_to(world).as_posix()
    entity_file = path.parent.name == "entities"
    records = []
    chunks = 0
    for slot, compression, payload in _read_slots(path):
        chunk = nbt.NBTFile(buffer=io.BytesIO(_decode(payload, compression)))
        chunks += 1
        if entity_file:
            key = "Entities"
            owners = chunk.get(key, [])
        else:
            key = None
            owners = []
            for candidate in ("block_entities", "BlockEntities", "blockEntities", "TileEntities"):
                if candidate in chunk:
                    key = candidate
                    owners = chunk[candidate]
                    break
        for index, owner in enumerate(owners):
            if not isinstance(owner, nbt.TAG_Compound):
                continue
            metadata = {
                "file": relative,
                "slot": slot,
                "owner_index": index,
                **_owner_metadata(owner),
            }
            records.extend(_collect_tree(owner, f"{key}[{index}]", metadata))
    return {"file": relative, "chunks": chunks, "records": records}


def scan_dat(path, world):
    relative = path.relative_to(world).as_posix()
    root = nbt.NBTFile(filename=str(path))
    metadata = {"file": relative, "slot": None, "owner_index": None, "owner_id": None}
    return {"file": relative, "chunks": 1, "records": _collect_tree(root, "", metadata)}


def summarize(records):
    stacks = [record for record in records if record["kind"] == "fluid_stack"]
    mounted = [record for record in records if record["kind"] == "mounted_storage"]
    return {
        "fluid_stacks": len(stacks),
        "mounted_storages": len(mounted),
        "inexact_records": sum(not record["exact"] for record in records),
        "semantic_floor_allowed_records": sum(
            record.get("semantic_floor_allowed", False) and not record["exact"]
            for record in stacks
        ),
        "nearest_millibucket_volume_records": sum(
            record.get("nearest_millibucket_volume_allowed", False)
            and not record["exact"]
            for record in stacks
        ),
        "nearest_potion_bottle_scale_records": sum(
            record.get("nearest_potion_bottle_scale_allowed", False)
            and not record["exact"]
            for record in stacks
        ),
        "fluid_ids": dict(sorted(Counter(record["id"] for record in stacks).items())),
        "target_fluid_ids": dict(sorted(Counter(record["target_id"] for record in stacks).items())),
        "amounts": {str(key): value for key, value in sorted(Counter(record["amount"] for record in stacks).items())},
        "max_capacities": {
            str(key): value for key, value in sorted(Counter(record["max_capacity"] for record in stacks).items())
        },
        "component_sets": dict(
            sorted(Counter("|".join(record["components"]) for record in stacks).items())
        ),
        "owner_ids": dict(sorted(Counter(record.get("owner_id") for record in stacks).items(), key=lambda item: str(item[0]))),
        "files_with_records": len({record["file"] for record in records}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    world = args.world.resolve()
    region_files = []
    for directory in world.rglob("*.mca"):
        if directory.parent.name in {"region", "entities"}:
            region_files.append(directory)
    dat_files = sorted(
        path
        for path in world.rglob("*.dat")
        if path.name not in {"session.lock", "uid.dat"}
    )
    all_records = []
    malformed = []
    scanned_chunks = 0
    region_files = sorted(region_files)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(scan_region, path, world): path for path in region_files}
        for completed, future in enumerate(as_completed(futures), 1):
            path = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                malformed.append({"file": path.relative_to(world).as_posix(), "error": f"{type(exc).__name__}: {exc}"})
                continue
            scanned_chunks += result["chunks"]
            all_records.extend(result["records"])
            if completed % 100 == 0:
                print(
                    f"regions={completed}/{len(region_files)} chunks={scanned_chunks} records={len(all_records)}",
                    file=sys.stderr,
                    flush=True,
                )
    for path in dat_files:
        try:
            result = scan_dat(path, world)
        except Exception as exc:
            malformed.append({"file": path.relative_to(world).as_posix(), "error": f"{type(exc).__name__}: {exc}"})
            continue
        all_records.extend(result["records"])
    all_records.sort(key=lambda record: (record["file"], record.get("slot") or -1, record["path"], record["kind"]))
    report = {
        "world": str(world),
        "source_bucket_units": fluid_converter.FABRIC_BUCKET,
        "target_bucket_units": fluid_converter.NEOFORGE_BUCKET,
        "unit_divisor": fluid_converter.FLUID_UNIT_DIVISOR,
        "region_files_scanned": len(region_files),
        "dat_files_scanned": len(dat_files),
        "chunks_scanned": scanned_chunks,
        "summary": summarize(all_records),
        "malformed": malformed,
        "records": all_records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report["summary"], "malformed": len(malformed)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
