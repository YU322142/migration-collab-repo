from __future__ import annotations

import argparse
import collections
import io
import json
import sys
from pathlib import Path


def load_auditor(path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("audit_poi_regions", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def records(auditor, world: Path) -> dict[tuple[str, int, int, int], dict]:
    world = world.resolve()
    result = {}
    for dimension, relative in auditor.DIMENSIONS.items():
        root = world / relative / "poi"
        for path in sorted(root.glob("*.mca")):
            coords = auditor.parse_region_coords(path.name)
            if coords is None:
                continue
            for slot, _offset, _sectors, compression, compressed in auditor.world_nbt.read_slots(path):
                raw = auditor.world_nbt.decode(compressed, compression)
                chunk = auditor.world_nbt.nbt.NBTFile(buffer=io.BytesIO(raw))
                sections = chunk.get("Sections")
                if not isinstance(sections, auditor.world_nbt.nbt.TAG_Compound):
                    continue
                chunk_x, chunk_z = auditor.chunk_coords(*coords, slot)
                for section_name, section in sections.items():
                    try:
                        section_y = int(section_name)
                    except ValueError:
                        continue
                    if not isinstance(section, auditor.world_nbt.nbt.TAG_Compound):
                        continue
                    raw_records = section.get("Records")
                    if not isinstance(raw_records, auditor.world_nbt.nbt.TAG_List):
                        continue
                    for record in raw_records:
                        if not isinstance(record, auditor.world_nbt.nbt.TAG_Compound):
                            continue
                        plain = auditor.plain_record(record)
                        pos = plain.get("pos")
                        poi_type = plain.get("type")
                        free = plain.get("free_tickets")
                        if isinstance(pos, list) and len(pos) == 3:
                            result[(dimension, *pos)] = {
                                "type": poi_type,
                                "free_tickets": free,
                                "chunk": [chunk_x, chunk_z],
                                "section": section_y,
                            }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--auditor", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    auditor = load_auditor(args.auditor.resolve())
    source = records(auditor, args.source)
    target = records(auditor, args.target)
    missing = sorted(set(source) - set(target))
    extra = sorted(set(target) - set(source))
    changed = []
    for key in sorted(set(source) & set(target)):
        if source[key] != target[key]:
            changed.append({"key": key, "source": source[key], "target": target[key]})
    type_missing = collections.Counter(source[key]["type"] for key in missing)
    type_extra = collections.Counter(target[key]["type"] for key in extra)
    report = {
        "source_records": len(source),
        "target_records": len(target),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": len(changed),
        "missing_by_type": dict(type_missing),
        "extra_by_type": dict(type_extra),
        "missing": [
            {"key": key, **source[key]} for key in missing
        ],
        "extra": [
            {"key": key, **target[key]} for key in extra
        ],
        "changed": changed,
        "status": "PASS" if not missing and not changed else "DIFF",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("source_records", "target_records", "missing_count", "extra_count", "changed_count", "missing_by_type", "extra_by_type", "status")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
