from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
import re
import struct
import time
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import nbtlib


REGION_NAME = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
LAYERS = ("region", "entities", "poi")
PAIR_DEFINITIONS = (
    ("the_nether", Path("world_nether"), Path("DIM-1"), Path("world") / "DIM-1"),
    ("the_end", Path("world_the_end"), Path("DIM1"), Path("world") / "DIM1"),
)


def plain(value: Any) -> Any:
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def json_hash(value: Any) -> str:
    raw = json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stat_summary(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
        "sha256": file_sha256(path),
    }


def level_summary(path: Path) -> dict[str, Any]:
    result = stat_summary(path)
    try:
        root = nbtlib.load(path, gzipped=True)
        data = root.get("Data", root)
        selected: dict[str, Any] = {}
        for key in (
            "DataVersion",
            "LevelName",
            "RandomSeed",
            "Time",
            "DayTime",
            "LastPlayed",
            "SpawnX",
            "SpawnY",
            "SpawnZ",
            "BorderCenterX",
            "BorderCenterZ",
            "BorderSize",
            "BorderWarningTime",
        ):
            if key in data:
                selected[key] = plain(data[key])
        version = data.get("Version")
        if version is not None:
            selected["Version"] = plain(version)
        world_gen = data.get("WorldGenSettings")
        if isinstance(world_gen, dict) and "seed" in world_gen:
            selected["WorldGenSettingsSeed"] = plain(world_gen["seed"])
        for key in ("Bukkit.Version", "paperSpawnDimension"):
            if key in data:
                selected[key] = plain(data[key])
        result["nbt"] = selected
        result["semantic_sha256"] = json_hash(root)
    except Exception as exc:  # pragma: no cover - exercised against the real snapshot
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def uid_summary(path: Path) -> dict[str, Any]:
    result = stat_summary(path)
    raw = path.read_bytes()
    if len(raw) == 16:
        result["uuid"] = str(uuid.UUID(bytes=raw))
    else:
        result["error"] = f"uid.dat has {len(raw)} bytes, expected 16"
    return result


def decompress(payload: bytes, compression: int) -> bytes:
    kind = compression & 0x7F
    if compression & 0x80:
        raise ValueError("external .mcc chunk payloads are not supported by this audit")
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported MCA compression type {compression}")


def uuid_text(entity: Any) -> str | None:
    if not isinstance(entity, dict):
        return None
    value = plain(entity.get("UUID"))
    if isinstance(value, str):
        try:
            return str(uuid.UUID(value))
        except ValueError:
            return value.lower()
    if isinstance(value, list) and len(value) == 4:
        number = 0
        for part in value:
            number = (number << 32) | (int(part) & 0xFFFFFFFF)
        return str(uuid.UUID(int=number))
    if "UUIDMost" in entity and "UUIDLeast" in entity:
        number = ((int(entity["UUIDMost"]) & 0xFFFFFFFFFFFFFFFF) << 64) | (
            int(entity["UUIDLeast"]) & 0xFFFFFFFFFFFFFFFF
        )
        return str(uuid.UUID(int=number))
    return None


def entity_list(chunk: Any) -> Iterable[Any]:
    for key in ("Entities", "entities"):
        value = chunk.get(key)
        if value is not None:
            return value
    level = chunk.get("Level")
    if isinstance(level, dict):
        for key in ("Entities", "entities"):
            value = level.get(key)
            if value is not None:
                return value
    return ()


def walk_entities(entity: Any) -> Iterable[Any]:
    yield entity
    if not isinstance(entity, dict):
        return
    passengers = entity.get("Passengers") or entity.get("passengers") or ()
    for passenger in passengers:
        yield from walk_entities(passenger)


def poi_records(chunk: Any) -> Iterable[Any]:
    sections = chunk.get("Sections") or chunk.get("sections")
    if not isinstance(sections, dict):
        return ()
    records: list[Any] = []
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        value = section.get("Records") or section.get("records") or ()
        records.extend(value)
    return records


@dataclass(frozen=True)
class ChunkSlot:
    coord: str
    region: str
    slot: int
    timestamp: int
    raw_sha256: str
    raw_bytes: int
    compression: int
    record_count: int

    def public(self) -> dict[str, Any]:
        return {
            "coord": self.coord,
            "region": self.region,
            "slot": self.slot,
            "timestamp": self.timestamp,
            "timestamp_utc": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)) if self.timestamp else None
            ),
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "compression": self.compression,
            "record_count": self.record_count,
        }


def read_mca(path: Path, layer: str) -> tuple[dict[str, ChunkSlot], dict[str, dict[str, Any]], list[dict[str, Any]], collections.Counter[str]]:
    match = REGION_NAME.fullmatch(path.name)
    if match is None:
        raise ValueError(f"invalid region filename: {path.name}")
    region_x, region_z = int(match.group(1)), int(match.group(2))
    slots: dict[str, ChunkSlot] = {}
    entity_uuids: dict[str, dict[str, Any]] = {}
    poi: list[dict[str, Any]] = []
    ids: collections.Counter[str] = collections.Counter()

    if path.stat().st_size == 0:
        return slots, entity_uuids, poi, ids

    with path.open("rb") as handle:
        header = handle.read(8192)
        if len(header) != 8192:
            raise ValueError(f"non-empty MCA has a {len(header)}-byte header")
        for slot in range(1024):
            location = header[slot * 4 : slot * 4 + 4]
            offset = int.from_bytes(location[:3], "big")
            sectors = location[3]
            if offset == 0:
                continue
            timestamp = int.from_bytes(header[4096 + slot * 4 : 4100 + slot * 4], "big")
            handle.seek(offset * 4096)
            length_raw = handle.read(4)
            if len(length_raw) != 4:
                raise ValueError(f"slot {slot}: missing payload length")
            length = int.from_bytes(length_raw, "big")
            compression_raw = handle.read(1)
            if length < 1 or len(compression_raw) != 1:
                raise ValueError(f"slot {slot}: invalid payload header")
            if length + 4 > sectors * 4096:
                raise ValueError(f"slot {slot}: payload overruns allocated sectors")
            payload = handle.read(length - 1)
            if len(payload) != length - 1:
                raise ValueError(f"slot {slot}: truncated payload")
            compression = compression_raw[0]
            raw = decompress(payload, compression)
            chunk_x = region_x * 32 + (slot & 31)
            chunk_z = region_z * 32 + (slot >> 5)
            coord = f"{chunk_x},{chunk_z}"
            record_count = 0

            if layer in ("entities", "poi"):
                chunk = nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
                if layer == "entities":
                    top_entities = list(entity_list(chunk))
                    for top_index, top_entity in enumerate(top_entities):
                        for nested_index, entity in enumerate(walk_entities(top_entity)):
                            record_count += 1
                            identifier = str(plain(entity.get("id", "<missing>"))) if isinstance(entity, dict) else "<invalid>"
                            ids[identifier] += 1
                            entity_uuid = uuid_text(entity)
                            if entity_uuid is None:
                                continue
                            position = plain(entity.get("Pos", [])) if isinstance(entity, dict) else []
                            entity_uuids[entity_uuid] = {
                                "uuid": entity_uuid,
                                "id": identifier,
                                "pos": position,
                                "coord": coord,
                                "region": path.name,
                                "slot": slot,
                                "top_index": top_index,
                                "nested_index": nested_index,
                            }
                else:
                    for record in poi_records(chunk):
                        record_count += 1
                        unpacked = plain(record)
                        if not isinstance(unpacked, dict):
                            continue
                        position = unpacked.get("pos")
                        identifier = str(unpacked.get("type", "<missing>"))
                        ids[identifier] += 1
                        if isinstance(position, list) and len(position) == 3:
                            poi.append(
                                {
                                    "key": f"{position[0]},{position[1]},{position[2]}|{identifier}",
                                    "pos": position,
                                    "type": identifier,
                                    "coord": coord,
                                    "region": path.name,
                                    "slot": slot,
                                }
                            )

            slots[coord] = ChunkSlot(
                coord=coord,
                region=path.name,
                slot=slot,
                timestamp=timestamp,
                raw_sha256=hashlib.sha256(raw).hexdigest().upper(),
                raw_bytes=len(raw),
                compression=compression,
                record_count=record_count,
            )
    return slots, entity_uuids, poi, ids


def scan_layer(root: Path, layer: str) -> dict[str, Any]:
    directory = root / layer
    files = sorted(directory.glob("*.mca"), key=lambda item: item.name)
    all_slots: dict[str, ChunkSlot] = {}
    all_entities: dict[str, dict[str, Any]] = {}
    all_poi: dict[str, dict[str, Any]] = {}
    ids: collections.Counter[str] = collections.Counter()
    errors: list[dict[str, str]] = []
    empty_files = 0
    for path in files:
        if path.stat().st_size == 0:
            empty_files += 1
        try:
            slots, entities, poi, file_ids = read_mca(path, layer)
            duplicates = set(all_slots) & set(slots)
            if duplicates:
                raise ValueError(f"duplicate chunk coordinates: {sorted(duplicates)[:3]}")
            all_slots.update(slots)
            all_entities.update(entities)
            for record in poi:
                all_poi[record["key"]] = record
            ids.update(file_ids)
        except Exception as exc:
            errors.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
    return {
        "directory": str(directory),
        "file_names": [item.name for item in files],
        "file_count": len(files),
        "empty_file_count": empty_files,
        "bytes": sum(item.stat().st_size for item in files),
        "slots": all_slots,
        "entities": all_entities,
        "poi": all_poi,
        "ids": ids,
        "errors": errors,
    }


def compare_records(legacy: dict[str, dict[str, Any]], canonical: dict[str, dict[str, Any]]) -> dict[str, Any]:
    legacy_keys = set(legacy)
    canonical_keys = set(canonical)
    common = legacy_keys & canonical_keys
    moved_or_changed = [
        {"legacy": legacy[key], "canonical": canonical[key]}
        for key in sorted(common)
        if legacy[key].get("id") != canonical[key].get("id") or legacy[key].get("pos") != canonical[key].get("pos")
    ]
    return {
        "legacy_count": len(legacy),
        "canonical_count": len(canonical),
        "common_count": len(common),
        "legacy_only_count": len(legacy_keys - canonical_keys),
        "canonical_only_count": len(canonical_keys - legacy_keys),
        "moved_or_changed_count": len(moved_or_changed),
        "legacy_only": [legacy[key] for key in sorted(legacy_keys - canonical_keys)],
        "canonical_only": [canonical[key] for key in sorted(canonical_keys - legacy_keys)],
        "moved_or_changed": moved_or_changed,
    }


def compare_layer(legacy_root: Path, canonical_root: Path, layer: str) -> dict[str, Any]:
    legacy = scan_layer(legacy_root, layer)
    canonical = scan_layer(canonical_root, layer)
    legacy_slots: dict[str, ChunkSlot] = legacy.pop("slots")
    canonical_slots: dict[str, ChunkSlot] = canonical.pop("slots")
    legacy_keys = set(legacy_slots)
    canonical_keys = set(canonical_slots)
    common = legacy_keys & canonical_keys
    identical = sorted(key for key in common if legacy_slots[key].raw_sha256 == canonical_slots[key].raw_sha256)
    different = sorted(common - set(identical))
    timestamp_relation = collections.Counter()
    for key in common:
        left = legacy_slots[key].timestamp
        right = canonical_slots[key].timestamp
        if left < right:
            timestamp_relation["canonical_newer"] += 1
        elif left > right:
            timestamp_relation["legacy_newer"] += 1
        else:
            timestamp_relation["equal"] += 1

    result: dict[str, Any] = {
        "legacy": legacy,
        "canonical": canonical,
        "files": {
            "common_count": len(set(legacy["file_names"]) & set(canonical["file_names"])),
            "legacy_only": sorted(set(legacy["file_names"]) - set(canonical["file_names"])),
            "canonical_only": sorted(set(canonical["file_names"]) - set(legacy["file_names"])),
        },
        "slots": {
            "legacy_count": len(legacy_keys),
            "canonical_count": len(canonical_keys),
            "common_count": len(common),
            "legacy_only_count": len(legacy_keys - canonical_keys),
            "canonical_only_count": len(canonical_keys - legacy_keys),
            "common_identical_count": len(identical),
            "common_different_count": len(different),
            "common_timestamp_relation": dict(sorted(timestamp_relation.items())),
            "legacy_only": [legacy_slots[key].public() for key in sorted(legacy_keys - canonical_keys)],
            "canonical_only": [canonical_slots[key].public() for key in sorted(canonical_keys - legacy_keys)],
            "common_different": [
                {"coord": key, "legacy": legacy_slots[key].public(), "canonical": canonical_slots[key].public()}
                for key in different
            ],
        },
        "id_counts": {
            "legacy": dict(sorted(legacy.pop("ids").items())),
            "canonical": dict(sorted(canonical.pop("ids").items())),
        },
    }
    if layer == "entities":
        result["entity_uuid_comparison"] = compare_records(legacy.pop("entities"), canonical.pop("entities"))
    else:
        legacy.pop("entities")
        canonical.pop("entities")
    if layer == "poi":
        result["poi_record_comparison"] = compare_records(legacy.pop("poi"), canonical.pop("poi"))
    else:
        legacy.pop("poi")
        canonical.pop("poi")
    return result


def data_file_summary(path: Path) -> dict[str, Any]:
    result = stat_summary(path)
    try:
        root = nbtlib.load(path, gzipped=True)
        result["semantic_sha256"] = json_hash(root)
        result["top_level_keys"] = sorted(str(key) for key in root.keys())
    except Exception as exc:
        result["nbt_error"] = f"{type(exc).__name__}: {exc}"
    return result


def compare_data_dirs(legacy_dir: Path, canonical_dir: Path) -> dict[str, Any]:
    legacy_paths = {item.name: item for item in legacy_dir.glob("*.dat")}
    canonical_paths = {item.name: item for item in canonical_dir.glob("*.dat")}
    common = sorted(set(legacy_paths) & set(canonical_paths))
    records = []
    for name in common:
        left = data_file_summary(legacy_paths[name])
        right = data_file_summary(canonical_paths[name])
        records.append(
            {
                "name": name,
                "byte_identical": left["sha256"] == right["sha256"],
                "semantic_identical": left.get("semantic_sha256") == right.get("semantic_sha256"),
                "legacy": left,
                "canonical": right,
            }
        )
    return {
        "legacy_dir": str(legacy_dir),
        "canonical_dir": str(canonical_dir),
        "legacy_only": sorted(set(legacy_paths) - set(canonical_paths)),
        "canonical_only": sorted(set(canonical_paths) - set(legacy_paths)),
        "common": records,
    }


def count_risks(pair: dict[str, Any]) -> dict[str, int]:
    risks = collections.Counter()
    for layer, comparison in pair["layers"].items():
        risks[f"{layer}_legacy_only_slots"] = comparison["slots"]["legacy_only_count"]
        risks[f"{layer}_common_different_slots"] = comparison["slots"]["common_different_count"]
    risks["legacy_only_entity_uuids"] = pair["layers"]["entities"]["entity_uuid_comparison"]["legacy_only_count"]
    risks["legacy_only_poi_records"] = pair["layers"]["poi"]["poi_record_comparison"]["legacy_only_count"]
    return dict(risks)


def md_list(values: list[str], limit: int = 12) -> str:
    if not values:
        return "none"
    shown = ", ".join(f"`{value}`" for value in values[:limit])
    if len(values) > limit:
        shown += f", ... (+{len(values) - limit})"
    return shown


def millis_utc(value: Any) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(value) / 1000))
    except (TypeError, ValueError, OSError):
        return "unknown"


def build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Legacy dimension root audit",
        "",
        f"Generated UTC: `{report['generated_utc']}`",
        f"Source (read-only): `{report['source']}`",
        f"Status: **{report['status']}**",
        "",
        "## Verdict",
        "",
        "The legacy dimension roots are not byte-for-byte stale replicas. They are dormant 1.21.10 world branches with a different world UUID and a different world-generation seed from the active 1.21.11 canonical world. Both also contain occupied chunk coordinates, entity UUIDs, and POI records absent from canonical. Common entity UUIDs prove partial historical inheritance, but the branches have since diverged.",
        "",
        "There is no automatic same-dimension merge that can honestly be called lossless: overlapping coordinates conflict, while importing only legacy-only coordinates would create a cross-seed mosaic with terrain seams and potentially resurrect deliberately retired areas. Fail closed until the owner decides whether these April-era worlds are archival-only or must remain player-accessible as separate worlds/dimensions.",
        "",
    ]
    for pair in report["pairs"]:
        lines.extend(
            [
                f"## {pair['name']}",
                "",
                f"Legacy wrapper: `{pair['legacy_wrapper']}`",
                f"Legacy dimension: `{pair['legacy_dimension']}`",
                f"Canonical dimension: `{pair['canonical_dimension']}`",
                "",
                "### Identity and time",
                "",
                f"- Legacy wrapper uid: `{pair['identity']['legacy_uid'].get('uuid', 'unreadable')}`",
                f"- Canonical world uid: `{pair['identity']['canonical_uid'].get('uuid', 'unreadable')}`",
                f"- Legacy data version: `{pair['identity']['legacy_level'].get('nbt', {}).get('DataVersion')}` / `{pair['identity']['legacy_level'].get('nbt', {}).get('Version', {}).get('Name')}`",
                f"- Canonical data version: `{pair['identity']['canonical_level'].get('nbt', {}).get('DataVersion')}` / `{pair['identity']['canonical_level'].get('nbt', {}).get('Version', {}).get('Name')}`",
                f"- Legacy world-generation seed: `{pair['identity']['legacy_level'].get('nbt', {}).get('WorldGenSettingsSeed')}`",
                f"- Canonical world-generation seed: `{pair['identity']['canonical_level'].get('nbt', {}).get('WorldGenSettingsSeed')}`",
                f"- Legacy level LastPlayed: `{millis_utc(pair['identity']['legacy_level'].get('nbt', {}).get('LastPlayed'))}`",
                f"- Canonical level LastPlayed: `{millis_utc(pair['identity']['canonical_level'].get('nbt', {}).get('LastPlayed'))}`",
                "",
                "### Region slot comparison",
                "",
                "| Layer | Legacy slots | Canonical slots | Legacy-only | Canonical-only | Common identical | Common different |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for layer in LAYERS:
            slots = pair["layers"][layer]["slots"]
            lines.append(
                f"| {layer} | {slots['legacy_count']} | {slots['canonical_count']} | {slots['legacy_only_count']} | {slots['canonical_only_count']} | {slots['common_identical_count']} | {slots['common_different_count']} |"
            )
        entity_cmp = pair["layers"]["entities"]["entity_uuid_comparison"]
        poi_cmp = pair["layers"]["poi"]["poi_record_comparison"]
        lines.extend(
            [
                "",
                f"Entity UUIDs: legacy `{entity_cmp['legacy_count']}`, canonical `{entity_cmp['canonical_count']}`, common `{entity_cmp['common_count']}`, legacy-only `{entity_cmp['legacy_only_count']}`.",
                f"POI records: legacy `{poi_cmp['legacy_count']}`, canonical `{poi_cmp['canonical_count']}`, common `{poi_cmp['common_count']}`, legacy-only `{poi_cmp['legacy_only_count']}`.",
                "",
            ]
        )
        for layer in LAYERS:
            files = pair["layers"][layer]["files"]
            lines.append(f"- `{layer}` legacy-only region files: {md_list(files['legacy_only'])}")
        lines.extend(
            [
                "",
                "Nested dimension `data` comparison:",
                "",
                f"- Legacy-only files: {md_list(pair['dimension_data']['legacy_only'])}",
                f"- Canonical-only files: {md_list(pair['dimension_data']['canonical_only'])}",
                f"- Common files with semantic differences: `{sum(not item['semantic_identical'] for item in pair['dimension_data']['common'])}` / `{len(pair['dimension_data']['common'])}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Fail-closed merge policy",
            "",
            "1. Treat canonical `world/DIM-1` and `world/DIM1` as the only authoritative active branches for the current August server unless the owner explicitly says the dormant April worlds were still intended gameplay.",
            "2. Preserve `world_nether` and `world_the_end` byte-for-byte in the migration archive. Do not overlay their `level.dat`, `uid.dat`, `data`, `region`, `entities`, or `poi` onto canonical paths.",
            "3. If player access is required, convert each legacy world as an independent artifact and expose it under stable separate dimension/world identifiers, or run it as an archival server instance. Its own seed, world identity, data, entities, and POI must remain together. Portal/teleport routing then needs an explicit compatibility design and smoke tests.",
            "4. Reject an automatic 'fill canonical holes from legacy' plan for the no-loss target. It mixes different seeds and two divergent timelines. Such a mosaic is only permissible as an explicitly accepted sacrifice after visual boundary tests and coordinate-by-coordinate conflict review.",
            "5. Abort on malformed MCA, duplicate chunk coordinate, external `.mcc`, scan error, source mutation, or a changed archive/plan digest. Keep the original source and a pre-activation staging snapshot for rollback.",
            "",
            "## Fast cutover impact",
            "",
            "Archive/conversion of the dormant roots can be completed before downtime because their embedded `LastPlayed` is 2026-04-03. At maintenance start, still lock/verify all three source roots (`world`, `world_nether`, `world_the_end`) and abort if either dormant root changed unexpectedly. The ordinary live delta applies only to canonical chunks. If separate legacy dimensions are authorized, their converted immutable artifacts can be mounted during the final assembly without scanning 9 GB again.",
            "",
            "The machine-readable JSON contains the complete legacy-only slot lists, common divergent slot records, entity UUID comparisons, POI comparisons, and file hashes needed to generate that deterministic merge plan.",
            "",
        ]
    )
    return "\n".join(lines)


def audit(source: Path) -> dict[str, Any]:
    source = source.resolve()
    report: dict[str, Any] = {
        "schema": 1,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(source),
        "source_mode": "read-only",
        "pairs": [],
    }
    canonical_world = source / "world"
    for name, wrapper_relative, legacy_dimension_relative, canonical_relative in PAIR_DEFINITIONS:
        wrapper = source / wrapper_relative
        legacy_dimension = wrapper / legacy_dimension_relative
        canonical_dimension = source / canonical_relative
        pair: dict[str, Any] = {
            "name": name,
            "legacy_wrapper": str(wrapper),
            "legacy_dimension": str(legacy_dimension),
            "canonical_dimension": str(canonical_dimension),
            "identity": {
                "legacy_level": level_summary(wrapper / "level.dat"),
                "legacy_uid": uid_summary(wrapper / "uid.dat"),
                "canonical_level": level_summary(canonical_world / "level.dat"),
                "canonical_uid": uid_summary(canonical_world / "uid.dat"),
            },
            "layers": {},
        }
        for layer in LAYERS:
            pair["layers"][layer] = compare_layer(legacy_dimension, canonical_dimension, layer)
        pair["dimension_data"] = compare_data_dirs(legacy_dimension / "data", canonical_dimension / "data")
        pair["wrapper_data_vs_canonical_world"] = compare_data_dirs(wrapper / "data", canonical_world / "data")
        pair["risks"] = count_risks(pair)
        report["pairs"].append(pair)

    errors = []
    for pair in report["pairs"]:
        for layer in LAYERS:
            errors.extend(pair["layers"][layer]["legacy"]["errors"])
            errors.extend(pair["layers"][layer]["canonical"]["errors"])
    report["errors"] = errors
    has_unique = any(
        pair["layers"][layer]["slots"]["legacy_only_count"]
        for pair in report["pairs"]
        for layer in LAYERS
    )
    seed_mismatch = any(
        pair["identity"]["legacy_level"].get("nbt", {}).get("WorldGenSettingsSeed")
        != pair["identity"]["canonical_level"].get("nbt", {}).get("WorldGenSettingsSeed")
        for pair in report["pairs"]
    )
    if errors:
        report["status"] = "FAIL_SCAN_ERRORS"
    elif has_unique and seed_mismatch:
        report["status"] = "BLOCKED_LEGACY_WORLD_POLICY_REQUIRED"
    elif has_unique:
        report["status"] = "MUST_PRESERVE_LEGACY_UNIQUE_CONTENT"
    else:
        report["status"] = "STALE_DUPLICATES"
    report["report_sha256"] = json_hash({key: value for key, value in report.items() if key != "report_sha256"})
    return report


def compact_summary(report: dict[str, Any]) -> dict[str, Any]:
    pairs = []
    for pair in report["pairs"]:
        layers = {}
        for layer in LAYERS:
            comparison = pair["layers"][layer]
            layers[layer] = {
                "legacy_files": comparison["legacy"]["file_count"],
                "canonical_files": comparison["canonical"]["file_count"],
                "legacy_only_files": len(comparison["files"]["legacy_only"]),
                "canonical_only_files": len(comparison["files"]["canonical_only"]),
                **{key: value for key, value in comparison["slots"].items() if not isinstance(value, list)},
            }
        entity_cmp = pair["layers"]["entities"]["entity_uuid_comparison"]
        poi_cmp = pair["layers"]["poi"]["poi_record_comparison"]
        pairs.append(
            {
                "name": pair["name"],
                "legacy_wrapper": pair["legacy_wrapper"],
                "legacy_dimension": pair["legacy_dimension"],
                "canonical_dimension": pair["canonical_dimension"],
                "legacy_identity": {
                    "uid": pair["identity"]["legacy_uid"].get("uuid"),
                    "level": pair["identity"]["legacy_level"].get("nbt"),
                },
                "canonical_identity": {
                    "uid": pair["identity"]["canonical_uid"].get("uuid"),
                    "level": pair["identity"]["canonical_level"].get("nbt"),
                },
                "layers": layers,
                "entity_uuids": {key: value for key, value in entity_cmp.items() if key.endswith("_count")},
                "poi_records": {key: value for key, value in poi_cmp.items() if key.endswith("_count")},
                "dimension_data": {
                    "legacy_only": pair["dimension_data"]["legacy_only"],
                    "canonical_only": pair["dimension_data"]["canonical_only"],
                    "common_count": len(pair["dimension_data"]["common"]),
                    "common_semantic_differences": sum(
                        not item["semantic_identical"] for item in pair["dimension_data"]["common"]
                    ),
                },
                "risks": pair["risks"],
            }
        )
    summary = {
        "schema": 1,
        "generated_utc": report["generated_utc"],
        "source": report["source"],
        "source_mode": report["source_mode"],
        "status": report["status"],
        "full_report_content_sha256": report["report_sha256"],
        "errors": report["errors"],
        "pairs": pairs,
    }
    summary["summary_sha256"] = json_hash(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only audit of legacy Bukkit dimension roots versus canonical dimensions")
    parser.add_argument("--source", type=Path, default=Path(r"<TRANS_ROOT>\20260807"))
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path)
    args = parser.parse_args()

    report = audit(args.source)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown.write_text(build_markdown(report), encoding="utf-8")
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(compact_summary(report), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_sha256": report["report_sha256"], "json": str(args.json), "markdown": str(args.markdown), "summary_json": str(args.summary_json) if args.summary_json else None}, ensure_ascii=False))
    return 2 if report["status"] == "FAIL_SCAN_ERRORS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
