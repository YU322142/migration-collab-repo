from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from nbt.region import RegionFile


def canonical_tag(tag, *, omit_root_data_version: bool = False):
    if hasattr(tag, "tags"):
        if getattr(tag, "id", None) == 10:
            values = {
                child.name: canonical_tag(child)
                for child in tag.tags
                if not (omit_root_data_version and child.name == "DataVersion")
            }
            return {"type": 10, "value": dict(sorted(values.items()))}
        return {
            "type": getattr(tag, "id", None),
            "element_type": getattr(tag, "tagID", None),
            "value": [canonical_tag(child) for child in tag.tags],
        }

    value = getattr(tag, "value", tag)
    if isinstance(value, (bytes, bytearray)):
        value = list(value)
    elif not isinstance(value, (str, int, float, bool, type(None))):
        try:
            value = list(value)
        except TypeError:
            value = str(value)
    return {"type": getattr(tag, "id", None), "value": value}


def stable_hash(tag, *, omit_root_data_version: bool = False) -> str:
    payload = json.dumps(
        canonical_tag(tag, omit_root_data_version=omit_root_data_version),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_slots(raw: str) -> set[int]:
    slots = {int(value) for value in raw.split(",") if value.strip()}
    if not slots or any(slot < 0 or slot >= 1024 for slot in slots):
        raise ValueError("--slots must contain unique integers from 0 through 1023")
    return slots


def read_manifest(path: Path) -> dict[int, dict[str, object]]:
    region = RegionFile(filename=str(path))
    try:
        manifest = {}
        for metadata in region.get_chunk_coords():
            x = metadata["x"]
            z = metadata["z"]
            slot = x + 32 * z
            chunk = region.get_chunk(x, z)
            manifest[slot] = {
                "data_version": int(chunk["DataVersion"].value),
                "full_hash": stable_hash(chunk),
                "payload_hash": stable_hash(chunk, omit_root_data_version=True),
                "keys": sorted(chunk.keys()),
            }
        return manifest
    finally:
        region.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy a region and rewrite only explicit chunk DataVersion tags."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slots", required=True)
    parser.add_argument("--source-version", type=int, required=True)
    parser.add_argument("--target-version", type=int, required=True)
    parser.add_argument("--require-key", action="append", default=[])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source = args.input.resolve()
    output = args.output.resolve()
    slots = parse_slots(args.slots)
    if source == output:
        raise ValueError("in-place rewriting is forbidden")
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    if args.source_version == args.target_version:
        raise ValueError("source and target DataVersion must differ")

    before = read_manifest(source)
    missing = sorted(slots - before.keys())
    if missing:
        raise ValueError(f"selected slots are absent: {missing}")
    for slot in sorted(slots):
        version = before[slot]["data_version"]
        if version not in (args.source_version, args.target_version):
            raise ValueError(
                f"slot {slot} has DataVersion {version}, expected "
                f"{args.source_version} or already-normalized {args.target_version}"
            )
        missing_keys = sorted(set(args.require_key) - set(before[slot]["keys"]))
        if missing_keys:
            raise ValueError(f"slot {slot} is missing required keys: {missing_keys}")

    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    changed_slots = []
    region = RegionFile(filename=str(output))
    try:
        for slot in sorted(slots):
            x = slot % 32
            z = slot // 32
            chunk = region.get_chunk(x, z)
            if int(chunk["DataVersion"].value) == args.target_version:
                continue
            chunk["DataVersion"].value = args.target_version
            region.write_chunk(x, z, chunk)
            changed_slots.append(slot)
    finally:
        region.close()

    after = read_manifest(output)
    if before.keys() != after.keys():
        raise RuntimeError("chunk slot set changed")
    for slot in sorted(before):
        if before[slot]["payload_hash"] != after[slot]["payload_hash"]:
            raise RuntimeError(f"slot {slot} payload changed beyond DataVersion")
        if slot not in slots and before[slot]["full_hash"] != after[slot]["full_hash"]:
            raise RuntimeError(f"unselected slot {slot} changed")
    for slot in sorted(slots):
        if after[slot]["data_version"] != args.target_version:
            raise RuntimeError(f"slot {slot} did not reach target DataVersion")

    result = {
        "status": "PASS",
        "input": str(source),
        "output": str(output),
        "input_sha256": file_sha256(source),
        "output_sha256": file_sha256(output),
        "selected_slots": sorted(slots),
        "changed_slots": changed_slots,
        "source_version": args.source_version,
        "target_version": args.target_version,
        "chunk_count": len(before),
        "payload_hashes_preserved": True,
        "unselected_chunks_preserved": True,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    print(encoded)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
