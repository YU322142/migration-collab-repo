from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import convert_world_nbt as world_nbt


REGION_NAME = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
DIMENSIONS = {
    "minecraft:overworld": Path("."),
    "minecraft:the_nether": Path("DIM-1"),
    "minecraft:the_end": Path("DIM1"),
}
RECORD_KEYS = {"type", "pos", "free_tickets"}


def parse_region_coords(name: str) -> tuple[int, int] | None:
    match = REGION_NAME.fullmatch(name)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def chunk_coords(region_x: int, region_z: int, slot: int) -> tuple[int, int]:
    if not 0 <= slot < 1024:
        raise ValueError(f"region slot is outside 0..1023: {slot}")
    return region_x * 32 + (slot & 31), region_z * 32 + (slot >> 5)


def validate_plain_record(
    record: dict,
    expected_chunk: tuple[int, int],
    expected_section_y: int,
) -> list[str]:
    errors: list[str] = []
    keys = set(record)
    if keys != RECORD_KEYS:
        errors.append(f"record keys are {sorted(keys)}, expected {sorted(RECORD_KEYS)}")

    poi_type = record.get("type")
    if not isinstance(poi_type, str) or ":" not in poi_type:
        errors.append("type is not a namespaced string")

    pos = record.get("pos")
    if not isinstance(pos, list) or len(pos) != 3 or any(type(value) is not int for value in pos):
        errors.append("pos is not a three-integer vector")
    else:
        actual_chunk = (pos[0] // 16, pos[2] // 16)
        if actual_chunk != expected_chunk:
            errors.append(f"pos belongs to chunk {actual_chunk}, expected {expected_chunk}")
        actual_section_y = pos[1] // 16
        if actual_section_y != expected_section_y:
            errors.append(f"pos belongs to section Y {actual_section_y}, expected {expected_section_y}")

    free_tickets = record.get("free_tickets")
    if type(free_tickets) is not int:
        errors.append("free_tickets is not an integer")
    elif free_tickets < 0:
        errors.append("free_tickets is negative")
    return errors


def plain_record(record) -> dict:
    result = {}
    for key, value in record.items():
        if isinstance(value, world_nbt.nbt.TAG_String):
            result[key] = value.value
        elif isinstance(value, world_nbt.nbt.TAG_Int_Array):
            result[key] = [int(entry) for entry in value.value]
        elif isinstance(value, (world_nbt.nbt.TAG_Byte, world_nbt.nbt.TAG_Short, world_nbt.nbt.TAG_Int, world_nbt.nbt.TAG_Long)):
            result[key] = int(value.value)
        else:
            result[key] = {"unsupported_tag": type(value).__name__}
    return result


def error_ref(path: Path, world: Path, slot: int | None, reason: str, **extra) -> dict:
    result = {"path": path.relative_to(world).as_posix(), "reason": reason}
    if slot is not None:
        result["slot"] = slot
    result.update(extra)
    return result


def _data_version_policy(
    expected_data_version: int | None,
    allowed_data_versions: Iterable[int] | None,
) -> frozenset[int] | None:
    """Validate and normalize the mutually-exclusive POI version policy.

    A POI region can legitimately contain several historical DataVersion values:
    the runtime upgrades a section when it is loaded, while untouched sections
    retain their source marker.  The mixed-version policy therefore checks an
    explicit allow-list without rewriting or collapsing the observed values.
    """
    if expected_data_version is not None and allowed_data_versions is not None:
        raise ValueError("expected_data_version and allowed_data_versions are mutually exclusive")
    if allowed_data_versions is None:
        return None
    allowed = frozenset(int(value) for value in allowed_data_versions)
    if not allowed:
        raise ValueError("allowed_data_versions must contain at least one version")
    return allowed


def _data_version_is_allowed(
    version_value: int,
    expected_data_version: int | None,
    allowed_data_versions: frozenset[int] | None,
) -> bool:
    if expected_data_version is not None:
        return version_value == expected_data_version
    return allowed_data_versions is None or version_value in allowed_data_versions


def audit_world(
    world: Path,
    expected_data_version: int | None = None,
    allowed_data_versions: Iterable[int] | None = None,
) -> dict:
    world = world.resolve()
    allowed_versions = _data_version_policy(expected_data_version, allowed_data_versions)
    report = {
        "schema": 1,
        "world": str(world),
        "expected_data_version": expected_data_version,
        "allowed_data_versions": sorted(allowed_versions) if allowed_versions is not None else None,
        "region_files": 0,
        "empty_region_files": 0,
        "region_bytes": 0,
        "chunks": 0,
        "sections": 0,
        "records": 0,
        "valid_sections": Counter(),
        "data_versions": Counter(),
        "poi_types": Counter(),
        "free_tickets": Counter(),
        "dimensions": {},
        "errors": [],
        "duplicates": [],
    }
    manifest = hashlib.sha256()
    positions: dict[tuple[str, int, int, int], dict] = {}

    for dimension, relative in DIMENSIONS.items():
        poi_root = world / relative / "poi"
        dimension_counts = Counter()
        report["dimensions"][dimension] = dimension_counts
        if not poi_root.is_dir():
            report["errors"].append({"path": poi_root.relative_to(world).as_posix(), "reason": "POI directory is missing"})
            continue

        for path in sorted(poi_root.glob("*.mca"), key=lambda item: item.name):
            report["region_files"] += 1
            dimension_counts["region_files"] += 1
            payload = path.read_bytes()
            report["region_bytes"] += len(payload)
            manifest.update(path.relative_to(world).as_posix().encode("utf-8"))
            manifest.update(b"\0")
            manifest.update(str(len(payload)).encode("ascii"))
            manifest.update(b"\0")
            manifest.update(hashlib.sha256(payload).digest())
            if not payload:
                report["empty_region_files"] += 1
                dimension_counts["empty_region_files"] += 1
                continue

            coords = parse_region_coords(path.name)
            if coords is None:
                report["errors"].append(error_ref(path, world, None, "invalid region filename"))
                continue

            try:
                slots = world_nbt.read_slots(path)
                for slot, _offset, _sectors, compression, compressed in slots:
                    report["chunks"] += 1
                    dimension_counts["chunks"] += 1
                    chunk_x, chunk_z = chunk_coords(*coords, slot)
                    try:
                        raw = world_nbt.decode(compressed, compression)
                        chunk = world_nbt.nbt.NBTFile(buffer=io.BytesIO(raw))
                    except Exception as exc:
                        report["errors"].append(error_ref(path, world, slot, "cannot decode POI chunk", error=str(exc)))
                        continue

                    version = chunk.get("DataVersion")
                    if not isinstance(version, (world_nbt.nbt.TAG_Byte, world_nbt.nbt.TAG_Short, world_nbt.nbt.TAG_Int, world_nbt.nbt.TAG_Long)):
                        report["errors"].append(error_ref(path, world, slot, "DataVersion is missing or non-integer"))
                    else:
                        version_value = int(version.value)
                        report["data_versions"][str(version_value)] += 1
                        if not _data_version_is_allowed(version_value, expected_data_version, allowed_versions):
                            expected = (
                                {"expected": expected_data_version}
                                if expected_data_version is not None
                                else {"allowed": sorted(allowed_versions)}
                            )
                            report["errors"].append(
                                error_ref(path, world, slot, "unexpected DataVersion", value=version_value, **expected)
                            )

                    sections = chunk.get("Sections")
                    if not isinstance(sections, world_nbt.nbt.TAG_Compound):
                        report["errors"].append(error_ref(path, world, slot, "Sections is missing or non-compound"))
                        continue

                    for section_name, section in sections.items():
                        report["sections"] += 1
                        dimension_counts["sections"] += 1
                        try:
                            section_y = int(section_name)
                        except ValueError:
                            report["errors"].append(error_ref(path, world, slot, "section key is not an integer", section=section_name))
                            continue
                        if not isinstance(section, world_nbt.nbt.TAG_Compound):
                            report["errors"].append(error_ref(path, world, slot, "section is non-compound", section=section_y))
                            continue
                        if set(section.keys()) != {"Valid", "Records"}:
                            report["errors"].append(
                                error_ref(path, world, slot, "section keys differ", section=section_y, keys=sorted(section.keys()))
                            )
                        valid = section.get("Valid")
                        if not isinstance(valid, world_nbt.nbt.TAG_Byte) or int(valid.value) not in (0, 1):
                            report["errors"].append(error_ref(path, world, slot, "Valid is not a boolean byte", section=section_y))
                        else:
                            report["valid_sections"][str(int(valid.value))] += 1
                        records = section.get("Records")
                        if not isinstance(records, world_nbt.nbt.TAG_List):
                            report["errors"].append(error_ref(path, world, slot, "Records is non-list", section=section_y))
                            continue

                        for index, record in enumerate(records):
                            report["records"] += 1
                            dimension_counts["records"] += 1
                            if not isinstance(record, world_nbt.nbt.TAG_Compound):
                                report["errors"].append(
                                    error_ref(path, world, slot, "record is non-compound", section=section_y, record=index)
                                )
                                continue
                            plain = plain_record(record)
                            problems = validate_plain_record(plain, (chunk_x, chunk_z), section_y)
                            for problem in problems:
                                report["errors"].append(
                                    error_ref(path, world, slot, problem, section=section_y, record=index, value=plain)
                                )
                            if isinstance(plain.get("type"), str):
                                report["poi_types"][plain["type"]] += 1
                            if type(plain.get("free_tickets")) is int:
                                report["free_tickets"][str(plain["free_tickets"])] += 1
                            pos = plain.get("pos")
                            if isinstance(pos, list) and len(pos) == 3 and all(type(value) is int for value in pos):
                                key = (dimension, pos[0], pos[1], pos[2])
                                current = {
                                    "path": path.relative_to(world).as_posix(),
                                    "slot": slot,
                                    "section": section_y,
                                    "record": index,
                                    "type": plain.get("type"),
                                    "free_tickets": plain.get("free_tickets"),
                                }
                                previous = positions.get(key)
                                if previous is not None:
                                    report["duplicates"].append({"dimension": dimension, "pos": pos, "first": previous, "second": current})
                                else:
                                    positions[key] = current
            except Exception as exc:
                report["errors"].append(error_ref(path, world, None, "cannot read region", error=str(exc)))

    report["region_manifest_sha256"] = manifest.hexdigest().upper()
    for key in ("valid_sections", "data_versions", "poi_types", "free_tickets"):
        report[key] = dict(sorted(report[key].items()))
    report["dimensions"] = {key: dict(value) for key, value in report["dimensions"].items()}
    report["status"] = "PASS" if not report["errors"] and not report["duplicates"] else "FAIL"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Minecraft POI region schema/integrity audit")
    parser.add_argument("--world", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    version_group = parser.add_mutually_exclusive_group()
    version_group.add_argument("--expect-data-version", type=int)
    version_group.add_argument(
        "--allow-data-version",
        dest="allowed_data_versions",
        action="append",
        type=int,
        help="allow a mixed historical/runtime DataVersion set; may be repeated",
    )
    args = parser.parse_args()

    report = audit_world(args.world, args.expect_data_version, args.allowed_data_versions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "region_files", "chunks", "sections", "records", "errors", "duplicates")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
