#!/usr/bin/env python3
"""Fail-closed slot-level protected-zone terrain/biome OTA builder.

The protected selection is fixed to the exact discrete-block intersection of
the circle centred at (10192, -1574) with radius 1536.  It contains 29,305
chunks in 40 region files.

Read-only commands are ``inspect``, ``plan``, ``verify-bundle`` and
``verify-target``.  ``build`` writes only a detached OTA bundle.  The only
commands that may mutate a world are ``apply`` and ``rollback``; both require
``--allow-world-write`` and the literal stopped-server acknowledgement.

Terrain ``region`` files are reconstructed by chunk slot.  Selected slots
come from the vanilla donor V, while every outside slot (including its MCA
timestamp and raw compressed record) comes from current C.  POI is a separate,
explicit policy.  Entity MCA files are never emitted or written and are guarded
by byte hashes before and after every transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


CENTER_X = 10_192
CENTER_Z = -1_574
FREEZE_RADIUS = 1_536
EXPECTED_CHUNKS = 29_305
EXPECTED_REGIONS = 40
SECTOR_BYTES = 4096
HEADER_BYTES = 8192
STOPPED_ACK = "SERVER_IS_STOPPED"
DEFAULT_CURRENT_ZIP = Path(r"<DOWNLOAD_ROOT>\mechanomania-matched-runtime-attempt13-2.zip")
REGION_NAME_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
SAFE_REL_RE = re.compile(r"^(region|poi|entities)/r\.-?\d+\.-?\d+\.mca$")
SCHEMA_PLAN = "protected-zone-terrain-ota-plan/v1"
SCHEMA_BUNDLE = "protected-zone-terrain-ota-bundle/v1"
SCHEMA_RECEIPT = "protected-zone-terrain-ota-apply-receipt/v1"


class OtaError(RuntimeError):
    """A fail-closed validation or transaction error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(path, canonical_json_bytes(value))


def selected_chunks(
    center_x: int = CENTER_X,
    center_z: int = CENTER_Z,
    radius: int = FREEZE_RADIUS,
) -> list[tuple[int, int]]:
    """Return chunks containing at least one integer block inside the circle."""

    result: list[tuple[int, int]] = []
    minimum_x = (center_x - radius) // 16 - 1
    maximum_x = (center_x + radius) // 16 + 1
    minimum_z = (center_z - radius) // 16 - 1
    maximum_z = (center_z + radius) // 16 + 1
    radius_squared = radius * radius
    for chunk_x in range(minimum_x, maximum_x + 1):
        block_min_x = chunk_x * 16
        block_max_x = block_min_x + 15
        delta_x = 0 if block_min_x <= center_x <= block_max_x else min(
            abs(center_x - block_min_x), abs(center_x - block_max_x)
        )
        for chunk_z in range(minimum_z, maximum_z + 1):
            block_min_z = chunk_z * 16
            block_max_z = block_min_z + 15
            delta_z = 0 if block_min_z <= center_z <= block_max_z else min(
                abs(center_z - block_min_z), abs(center_z - block_max_z)
            )
            if delta_x * delta_x + delta_z * delta_z <= radius_squared:
                result.append((chunk_x, chunk_z))
    return result


def slot_for_chunk(chunk_x: int, chunk_z: int) -> int:
    return (chunk_x & 31) + (chunk_z & 31) * 32


def selection_by_region() -> dict[tuple[int, int], frozenset[int]]:
    grouped: dict[tuple[int, int], set[int]] = {}
    chunks = selected_chunks()
    for chunk_x, chunk_z in chunks:
        region = (chunk_x // 32, chunk_z // 32)
        grouped.setdefault(region, set()).add(slot_for_chunk(chunk_x, chunk_z))
    if len(chunks) != EXPECTED_CHUNKS:
        raise OtaError(f"geometry drift: {len(chunks)} chunks, expected {EXPECTED_CHUNKS}")
    if len(grouped) != EXPECTED_REGIONS:
        raise OtaError(f"geometry drift: {len(grouped)} regions, expected {EXPECTED_REGIONS}")
    if sum(len(slots) for slots in grouped.values()) != EXPECTED_CHUNKS:
        raise OtaError("geometry drift: duplicate or missing selected chunk slots")
    return {region: frozenset(slots) for region, slots in sorted(grouped.items())}


@dataclass(frozen=True)
class ChunkRecord:
    timestamp: int
    raw: bytes


class RegionImage:
    """Parsed MCA data preserving raw compressed records and every timestamp."""

    def __init__(self, records: Mapping[int, ChunkRecord] | None = None, timestamps: Iterable[int] | None = None):
        self.records = dict(records or {})
        self.timestamps = list(timestamps or [0] * 1024)
        if len(self.timestamps) != 1024:
            raise OtaError("MCA timestamp table must contain exactly 1024 entries")

    @classmethod
    def parse(cls, data: bytes | None, label: str) -> "RegionImage":
        if data is None or len(data) == 0:
            return cls()
        if len(data) < HEADER_BYTES:
            raise OtaError(f"{label}: non-empty MCA is shorter than the 8192-byte header")
        locations = data[:SECTOR_BYTES]
        timestamps_raw = data[SECTOR_BYTES:HEADER_BYTES]
        timestamps = [struct.unpack_from(">I", timestamps_raw, slot * 4)[0] for slot in range(1024)]
        allocations: set[int] = set()
        records: dict[int, ChunkRecord] = {}
        sector_count = math.ceil(len(data) / SECTOR_BYTES)
        for slot in range(1024):
            entry = locations[slot * 4 : slot * 4 + 4]
            offset = int.from_bytes(entry[:3], "big")
            sectors = entry[3]
            if offset == 0:
                if sectors != 0:
                    raise OtaError(f"{label}: slot {slot} has zero offset but {sectors} sectors")
                continue
            if offset < 2 or sectors < 1:
                raise OtaError(f"{label}: slot {slot} has invalid offset={offset}, sectors={sectors}")
            if offset + sectors > sector_count or (offset + sectors) * SECTOR_BYTES > len(data):
                raise OtaError(f"{label}: slot {slot} allocation exceeds file length")
            occupied = set(range(offset, offset + sectors))
            overlap = occupied & allocations
            if overlap:
                raise OtaError(f"{label}: slot {slot} overlaps allocated sector {min(overlap)}")
            allocations.update(occupied)
            position = offset * SECTOR_BYTES
            length = struct.unpack_from(">I", data, position)[0]
            if length < 1 or length + 4 > sectors * SECTOR_BYTES:
                raise OtaError(f"{label}: slot {slot} has invalid record length {length}")
            raw = data[position : position + 4 + length]
            if len(raw) != 4 + length:
                raise OtaError(f"{label}: slot {slot} record is truncated")
            compression = raw[4]
            if compression & 0x80:
                raise OtaError(f"{label}: slot {slot} uses refused external .mcc storage")
            if compression not in (1, 2, 3):
                raise OtaError(f"{label}: slot {slot} uses unsupported compression {compression}")
            records[slot] = ChunkRecord(timestamp=timestamps[slot], raw=raw)
        return cls(records, timestamps)

    def encode(self) -> bytes:
        location_table = bytearray(SECTOR_BYTES)
        timestamp_table = bytearray(SECTOR_BYTES)
        body = bytearray()
        next_sector = 2
        for slot, timestamp in enumerate(self.timestamps):
            struct.pack_into(">I", timestamp_table, slot * 4, timestamp & 0xFFFFFFFF)
        for slot in sorted(self.records):
            record = self.records[slot]
            required = max(1, math.ceil(len(record.raw) / SECTOR_BYTES))
            if required > 255:
                raise OtaError(f"slot {slot} needs {required} sectors; external .mcc is refused")
            if next_sector > 0xFFFFFF:
                raise OtaError("MCA sector offset exceeds 24-bit location-table capacity")
            entry = next_sector.to_bytes(3, "big") + bytes([required])
            location_table[slot * 4 : slot * 4 + 4] = entry
            body.extend(record.raw)
            body.extend(b"\0" * (required * SECTOR_BYTES - len(record.raw)))
            next_sector += required
        return bytes(location_table + timestamp_table + body)

    def signature(self, slots: Iterable[int]) -> str:
        digest = hashlib.sha256()
        for slot in sorted(slots):
            record = self.records.get(slot)
            digest.update(struct.pack(">H", slot))
            digest.update(struct.pack(">I", self.timestamps[slot] & 0xFFFFFFFF))
            if record is None:
                digest.update(b"MISSING\0")
            else:
                digest.update(b"PRESENT\0")
                digest.update(hashlib.sha256(record.raw).digest())
        return digest.hexdigest().upper()

    def semantically_equal(self, other: "RegionImage") -> bool:
        if self.timestamps != other.timestamps or self.records.keys() != other.records.keys():
            return False
        return all(self.records[slot].raw == other.records[slot].raw for slot in self.records)


def file_identity_bytes(data: bytes | None) -> dict[str, Any]:
    return {
        "exists": data is not None,
        "bytes": len(data) if data is not None else 0,
        "sha256": sha256_bytes(data) if data is not None else None,
    }


def file_identity_path(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "bytes": 0, "sha256": None}
    return {"exists": True, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def identity_equal(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return (
        bool(actual.get("exists")) == bool(expected.get("exists"))
        and int(actual.get("bytes", 0)) == int(expected.get("bytes", 0))
        and actual.get("sha256") == expected.get("sha256")
    )


def merge_region_bytes(
    current_data: bytes | None,
    donor_data: bytes | None,
    selected_slots: frozenset[int],
    *,
    kind: str,
    require_every_donor_slot: bool,
    current_label: str,
    donor_label: str,
) -> dict[str, Any]:
    if kind not in ("region", "poi"):
        raise OtaError(f"unsupported merge kind {kind}")
    current = RegionImage.parse(current_data, current_label)
    donor = RegionImage.parse(donor_data, donor_label)
    if require_every_donor_slot:
        missing = sorted(selected_slots - donor.records.keys())
        if missing:
            raise OtaError(
                f"{donor_label}: donor is missing {len(missing)} required selected terrain slots; "
                f"first={missing[:8]}"
            )
    desired_records = dict(current.records)
    desired_timestamps = list(current.timestamps)
    for slot in selected_slots:
        donor_record = donor.records.get(slot)
        if donor_record is None:
            desired_records.pop(slot, None)
            desired_timestamps[slot] = 0
        else:
            desired_records[slot] = donor_record
            desired_timestamps[slot] = donor_record.timestamp
    desired = RegionImage(desired_records, desired_timestamps)
    changed = not current.semantically_equal(desired)
    if not changed:
        post_data = current_data
    elif not desired.records:
        post_data = None
    else:
        post_data = desired.encode()
    reparsed = RegionImage.parse(post_data, f"rebuilt {kind}")
    outside_slots = frozenset(set(range(1024)) - set(selected_slots))
    if reparsed.signature(outside_slots) != current.signature(outside_slots):
        raise OtaError(f"{kind}: rebuilt MCA changed one or more outside slots")
    if reparsed.signature(selected_slots) != desired.signature(selected_slots):
        raise OtaError(f"{kind}: rebuilt MCA does not match desired selected slots")
    return {
        "changed": changed,
        "post_data": post_data,
        "pre": file_identity_bytes(current_data),
        "donor": file_identity_bytes(donor_data),
        "post": file_identity_bytes(post_data),
        "selected_pre_signature": current.signature(selected_slots),
        "selected_donor_signature": donor.signature(selected_slots),
        "selected_post_signature": reparsed.signature(selected_slots),
        "outside_pre_signature": current.signature(outside_slots),
        "outside_post_signature": reparsed.signature(outside_slots),
        "selected_pre_occupied": len(current.records.keys() & selected_slots),
        "selected_donor_occupied": len(donor.records.keys() & selected_slots),
        "selected_post_occupied": len(reparsed.records.keys() & selected_slots),
        "outside_occupied": len(current.records.keys() & outside_slots),
    }


class WorldSource:
    source_type: str

    def read(self, relative: str) -> bytes | None:
        raise NotImplementedError

    def descriptor(self) -> dict[str, Any]:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self) -> "WorldSource":
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self.close()


class DirectoryWorldSource(WorldSource):
    source_type = "directory"

    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise OtaError(f"world directory is missing: {self.root}")

    def read(self, relative: str) -> bytes | None:
        validate_relative_path(relative)
        path = self.root / Path(relative)
        if path.is_symlink():
            raise OtaError(f"linked world file is refused: {path}")
        return path.read_bytes() if path.is_file() else None

    def descriptor(self) -> dict[str, Any]:
        return {"type": self.source_type, "path": str(self.root)}


class ZipWorldSource(WorldSource):
    source_type = "zip"

    def __init__(self, path: Path, world_prefix: str | None = None, compute_archive_hash: bool = True):
        self.path = path.resolve()
        if not self.path.is_file():
            raise OtaError(f"ZIP source is missing: {self.path}")
        self.zip = zipfile.ZipFile(self.path, "r")
        self.names = set(self.zip.namelist())
        self.world_prefix = (world_prefix or self._detect_world_prefix()).strip("/")
        self.archive_identity = {
            "bytes": self.path.stat().st_size,
            "sha256": sha256_file(self.path) if compute_archive_hash else None,
        }

    def _detect_world_prefix(self) -> str:
        counts: dict[str, int] = {}
        for name in self.names:
            pure = PurePosixPath(name)
            if len(pure.parts) < 3 or pure.parts[-2] != "region":
                continue
            if not REGION_NAME_RE.fullmatch(pure.name):
                continue
            root = str(pure.parent.parent)
            if f"{root}/level.dat" in self.names:
                counts[root] = counts.get(root, 0) + 1
        if not counts:
            raise OtaError(f"could not detect an Overworld root in {self.path}")
        highest = max(counts.values())
        winners = sorted(root for root, count in counts.items() if count == highest)
        if len(winners) != 1:
            raise OtaError(f"ambiguous Overworld roots in {self.path}: {winners}")
        return winners[0]

    def read(self, relative: str) -> bytes | None:
        validate_relative_path(relative)
        member = f"{self.world_prefix}/{relative}"
        if member not in self.names:
            return None
        info = self.zip.getinfo(member)
        if info.is_dir():
            return None
        return self.zip.read(info)

    def descriptor(self) -> dict[str, Any]:
        return {
            "type": self.source_type,
            "path": str(self.path),
            "world_prefix": self.world_prefix,
            "archive": self.archive_identity,
        }

    def close(self) -> None:
        self.zip.close()


def open_source(path: Path, world_prefix: str | None = None, compute_archive_hash: bool = True) -> WorldSource:
    if path.is_dir():
        if world_prefix:
            raise OtaError("--world-prefix is only valid for ZIP sources")
        return DirectoryWorldSource(path)
    if path.suffix.lower() == ".zip":
        return ZipWorldSource(path, world_prefix, compute_archive_hash=compute_archive_hash)
    raise OtaError(f"source must be a world directory or ZIP: {path}")


def source_from_descriptor(descriptor: Mapping[str, Any], compute_archive_hash: bool = True) -> WorldSource:
    source = open_source(
        Path(str(descriptor["path"])),
        str(descriptor.get("world_prefix")) if descriptor.get("world_prefix") else None,
        compute_archive_hash=compute_archive_hash,
    )
    actual = source.descriptor()
    if descriptor.get("type") != actual.get("type"):
        source.close()
        raise OtaError("source type changed since the plan was created")
    if descriptor.get("type") == "zip":
        if descriptor.get("world_prefix") != actual.get("world_prefix"):
            source.close()
            raise OtaError("ZIP world prefix changed since the plan was created")
        expected_archive = descriptor.get("archive", {})
        actual_archive = actual.get("archive", {})
        if expected_archive.get("sha256") and expected_archive != actual_archive:
            source.close()
            raise OtaError("ZIP archive CAS mismatch")
    return source


def validate_relative_path(relative: str) -> None:
    if not SAFE_REL_RE.fullmatch(relative) or ".." in PurePosixPath(relative).parts:
        raise OtaError(f"path is outside the OTA allowlist: {relative!r}")


def region_relative(kind: str, region_x: int, region_z: int) -> str:
    relative = f"{kind}/r.{region_x}.{region_z}.mca"
    validate_relative_path(relative)
    return relative


def selection_json(grouped: Mapping[tuple[int, int], frozenset[int]]) -> dict[str, Any]:
    return {
        "rule": "chunk selected iff at least one discrete integer block in its closed 16x16 square is inside/on circle",
        "center": {"x": CENTER_X, "z": CENTER_Z},
        "radius_blocks": FREEZE_RADIUS,
        "chunk_count": sum(len(slots) for slots in grouped.values()),
        "region_count": len(grouped),
        "regions": [
            {"region": [region_x, region_z], "slots": sorted(slots), "slot_count": len(slots)}
            for (region_x, region_z), slots in grouped.items()
        ],
    }


def source_file_row(source: WorldSource, relative: str) -> dict[str, Any]:
    data = source.read(relative)
    identity = file_identity_bytes(data)
    if data is not None:
        image = RegionImage.parse(data, f"{source.descriptor().get('path')}::{relative}")
        occupied = len(image.records)
    else:
        occupied = 0
    return {"relative_path": relative, "identity": identity, "occupied_slots": occupied}


def inspect_current(source: WorldSource) -> dict[str, Any]:
    grouped = selection_by_region()
    totals = {kind: 0 for kind in ("region", "poi", "entities")}
    files: list[dict[str, Any]] = []
    selected_total = {kind: 0 for kind in totals}
    for (region_x, region_z), slots in grouped.items():
        for kind in ("region", "poi", "entities"):
            relative = region_relative(kind, region_x, region_z)
            data = source.read(relative)
            image = RegionImage.parse(data, f"current::{relative}")
            row = {
                "relative_path": relative,
                "identity": file_identity_bytes(data),
                "occupied_slots": len(image.records),
                "selected_occupied_slots": len(image.records.keys() & slots),
            }
            files.append(row)
            if data is not None:
                totals[kind] += 1
            selected_total[kind] += row["selected_occupied_slots"]
    return {
        "schema": "protected-zone-terrain-ota-current-inspection/v1",
        "generated_at_utc": utc_now(),
        "status": "PASS_READ_ONLY",
        "source": source.descriptor(),
        "selection": selection_json(grouped),
        "present_candidate_files": totals,
        "selected_occupied_slots": selected_total,
        "files": files,
        "non_actions": {"world_modified": False, "java_started": False},
    }


def create_plan(current: WorldSource, donor: WorldSource, poi_policy: str) -> dict[str, Any]:
    if poi_policy not in ("preserve-current", "donor-selected"):
        raise OtaError("POI policy must be explicitly preserve-current or donor-selected")
    grouped = selection_by_region()
    region_rows: list[dict[str, Any]] = []
    guard_rows: list[dict[str, Any]] = []
    terrain_donor_slots = 0
    for (region_x, region_z), slots in grouped.items():
        for kind in ("region", "poi", "entities"):
            relative = region_relative(kind, region_x, region_z)
            current_data = current.read(relative)
            current_image = RegionImage.parse(current_data, f"current::{relative}")
            guard_rows.append(
                {
                    "relative_path": relative,
                    "kind": kind,
                    "pre": file_identity_bytes(current_data),
                    "selected_signature": current_image.signature(slots),
                }
            )

        terrain_relative = region_relative("region", region_x, region_z)
        terrain_current = current.read(terrain_relative)
        terrain_donor = donor.read(terrain_relative)
        terrain_merge = merge_region_bytes(
            terrain_current,
            terrain_donor,
            slots,
            kind="region",
            require_every_donor_slot=True,
            current_label=f"current::{terrain_relative}",
            donor_label=f"donor::{terrain_relative}",
        )
        terrain_donor_slots += terrain_merge["selected_donor_occupied"]
        region_rows.append(
            {
                "relative_path": terrain_relative,
                "kind": "region",
                "region": [region_x, region_z],
                "selected_slots": len(slots),
                **{key: value for key, value in terrain_merge.items() if key != "post_data"},
            }
        )

        poi_relative = region_relative("poi", region_x, region_z)
        if poi_policy == "preserve-current":
            poi_current = current.read(poi_relative)
            poi_image = RegionImage.parse(poi_current, f"current::{poi_relative}")
            outside = frozenset(set(range(1024)) - set(slots))
            poi_row = {
                "relative_path": poi_relative,
                "kind": "poi",
                "region": [region_x, region_z],
                "selected_slots": len(slots),
                "changed": False,
                "pre": file_identity_bytes(poi_current),
                "donor": None,
                "post": file_identity_bytes(poi_current),
                "selected_pre_signature": poi_image.signature(slots),
                "selected_donor_signature": None,
                "selected_post_signature": poi_image.signature(slots),
                "outside_pre_signature": poi_image.signature(outside),
                "outside_post_signature": poi_image.signature(outside),
                "selected_pre_occupied": len(poi_image.records.keys() & slots),
                "selected_donor_occupied": None,
                "selected_post_occupied": len(poi_image.records.keys() & slots),
                "outside_occupied": len(poi_image.records.keys() & outside),
                "policy_action": "PRESERVE_CURRENT_POI_BYTE_IDENTICALLY",
            }
        else:
            poi_current = current.read(poi_relative)
            poi_donor = donor.read(poi_relative)
            poi_merge = merge_region_bytes(
                poi_current,
                poi_donor,
                slots,
                kind="poi",
                require_every_donor_slot=False,
                current_label=f"current::{poi_relative}",
                donor_label=f"donor::{poi_relative}",
            )
            poi_row = {
                "relative_path": poi_relative,
                "kind": "poi",
                "region": [region_x, region_z],
                "selected_slots": len(slots),
                **{key: value for key, value in poi_merge.items() if key != "post_data"},
                "policy_action": "REPLACE_SELECTED_POI_SLOTS_FROM_DONOR_AND_PRESERVE_OUTSIDE",
            }
        region_rows.append(poi_row)
    if terrain_donor_slots != EXPECTED_CHUNKS:
        raise OtaError(
            f"donor terrain coverage drift: {terrain_donor_slots}, expected {EXPECTED_CHUNKS}"
        )
    return {
        "schema": SCHEMA_PLAN,
        "generated_at_utc": utc_now(),
        "status": "READY_FOR_DETACHED_BUNDLE_BUILD",
        "selection": selection_json(grouped),
        "poi_policy": poi_policy,
        "current": current.descriptor(),
        "donor": donor.descriptor(),
        "rules": {
            "selected_region_slots": "donor V raw record and timestamp",
            "outside_region_slots": "current C raw record and timestamp",
            "entities": "guard byte-identically; never write or include in payload",
            "whole_region_copy": False,
            "default_world_write": False,
        },
        "guard_files": guard_rows,
        "file_plans": region_rows,
        "terrain_donor_selected_slots": terrain_donor_slots,
        "non_actions": {"world_modified": False, "java_started": False},
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OtaError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OtaError(f"JSON root must be an object: {path}")
    return value


def plan_slot_map(plan: Mapping[str, Any]) -> dict[tuple[int, int], frozenset[int]]:
    grouped: dict[tuple[int, int], frozenset[int]] = {}
    selection = plan.get("selection", {})
    if selection.get("chunk_count") != EXPECTED_CHUNKS or selection.get("region_count") != EXPECTED_REGIONS:
        raise OtaError("plan selection count does not match the locked geometry")
    for row in selection.get("regions", []):
        region = tuple(int(value) for value in row["region"])
        if len(region) != 2:
            raise OtaError("invalid region coordinate in plan")
        slots = frozenset(int(value) for value in row["slots"])
        if any(slot < 0 or slot >= 1024 for slot in slots):
            raise OtaError(f"invalid slot in plan region {region}")
        grouped[(region[0], region[1])] = slots
    if grouped != selection_by_region():
        raise OtaError("plan geometry does not equal the locked protected selection")
    return grouped


def verify_plan_source_file(source: WorldSource, row: Mapping[str, Any], side: str) -> bytes | None:
    relative = str(row["relative_path"])
    data = source.read(relative)
    expected = row.get(side)
    if not isinstance(expected, Mapping) or not identity_equal(file_identity_bytes(data), expected):
        raise OtaError(f"{side} CAS mismatch for {relative}")
    return data


def build_bundle(plan_path: Path, bundle_root: Path) -> dict[str, Any]:
    plan_path = plan_path.resolve()
    plan = load_json(plan_path)
    if plan.get("schema") != SCHEMA_PLAN or plan.get("status") != "READY_FOR_DETACHED_BUNDLE_BUILD":
        raise OtaError("plan is not a build-ready protected-zone OTA plan")
    grouped = plan_slot_map(plan)
    bundle_root = bundle_root.resolve()
    if bundle_root.exists():
        raise OtaError(f"bundle output already exists: {bundle_root}")
    temporary = bundle_root.with_name(f".{bundle_root.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir(parents=True)
    try:
        plan_copy = temporary / "plan.json"
        shutil.copy2(plan_path, plan_copy)
        changes: list[dict[str, Any]] = []
        with source_from_descriptor(plan["current"]) as current, source_from_descriptor(plan["donor"]) as donor:
            for row in plan["file_plans"]:
                relative = str(row["relative_path"])
                validate_relative_path(relative)
                kind = str(row["kind"])
                region_x, region_z = (int(value) for value in row["region"])
                slots = grouped[(region_x, region_z)]
                current_data = verify_plan_source_file(current, row, "pre")
                if kind == "poi" and plan["poi_policy"] == "preserve-current":
                    if row.get("changed"):
                        raise OtaError("preserve-current POI row unexpectedly requests a change")
                    continue
                donor_data = verify_plan_source_file(donor, row, "donor")
                merged = merge_region_bytes(
                    current_data,
                    donor_data,
                    slots,
                    kind=kind,
                    require_every_donor_slot=(kind == "region"),
                    current_label=f"current::{relative}",
                    donor_label=f"donor::{relative}",
                )
                for key in (
                    "changed",
                    "post",
                    "selected_post_signature",
                    "outside_post_signature",
                ):
                    if merged[key] != row[key]:
                        raise OtaError(f"plan drift for {relative}: {key}")
                if not merged["changed"]:
                    continue
                post_data = merged["post_data"]
                payload_relative = f"payload/{relative}" if post_data is not None else None
                if payload_relative:
                    payload_path = temporary / Path(payload_relative)
                    atomic_write_bytes(payload_path, post_data)
                changes.append(
                    {
                        "relative_path": relative,
                        "kind": kind,
                        "region": [region_x, region_z],
                        "pre": merged["pre"],
                        "post": merged["post"],
                        "payload_relative_path": payload_relative,
                        "selected_post_signature": merged["selected_post_signature"],
                        "outside_post_signature": merged["outside_post_signature"],
                    }
                )
        manifest = {
            "schema": SCHEMA_BUNDLE,
            "generated_at_utc": utc_now(),
            "status": "READY_FOR_STOPPED_SERVER_APPLY",
            "plan_sha256": sha256_file(plan_copy),
            "selection": plan["selection"],
            "poi_policy": plan["poi_policy"],
            "guard_files": plan["guard_files"],
            "changes": changes,
            "rules": plan["rules"],
            "payload_file_count": sum(1 for row in changes if row["payload_relative_path"]),
            "world_files_changed_during_build": 0,
        }
        atomic_write_json(temporary / "bundle.json", manifest)
        os.replace(temporary, bundle_root)
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def read_bundle(bundle_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle_root = bundle_root.resolve()
    manifest_path = bundle_root / "bundle.json"
    plan_path = bundle_root / "plan.json"
    manifest = load_json(manifest_path)
    plan = load_json(plan_path)
    if manifest.get("schema") != SCHEMA_BUNDLE or plan.get("schema") != SCHEMA_PLAN:
        raise OtaError("bundle or embedded plan schema mismatch")
    if manifest.get("plan_sha256") != sha256_file(plan_path):
        raise OtaError("embedded plan hash mismatch")
    if manifest.get("selection") != plan.get("selection"):
        raise OtaError("bundle selection differs from embedded plan")
    plan_slot_map(plan)
    change_paths: set[str] = set()
    for row in manifest.get("changes", []):
        relative = str(row["relative_path"])
        validate_relative_path(relative)
        if relative.startswith("entities/"):
            raise OtaError("entities MCA is forbidden in OTA changes")
        if relative in change_paths:
            raise OtaError(f"duplicate change path in bundle: {relative}")
        change_paths.add(relative)
        payload_relative = row.get("payload_relative_path")
        post = row.get("post", {})
        if post.get("exists"):
            expected_payload = f"payload/{relative}"
            if payload_relative != expected_payload:
                raise OtaError(f"payload path mismatch for {relative}")
            payload_path = bundle_root / Path(expected_payload)
            actual = file_identity_path(payload_path)
            if not identity_equal(actual, post):
                raise OtaError(f"payload hash mismatch for {relative}")
        elif payload_relative is not None:
            raise OtaError(f"deleted postimage must not have payload: {relative}")
    for path in (bundle_root / "payload").rglob("*") if (bundle_root / "payload").exists() else []:
        if not path.is_file():
            continue
        relative_payload = path.relative_to(bundle_root).as_posix()
        if relative_payload not in {
            str(row["payload_relative_path"])
            for row in manifest.get("changes", [])
            if row.get("payload_relative_path")
        }:
            raise OtaError(f"unmanifested payload file: {relative_payload}")
    return manifest, plan


def target_path(world_root: Path, relative: str) -> Path:
    validate_relative_path(relative)
    path = world_root / Path(relative)
    if path.is_symlink():
        raise OtaError(f"linked target file is refused: {path}")
    resolved_root = world_root.resolve()
    resolved_parent = path.parent.resolve()
    try:
        resolved_parent.relative_to(resolved_root)
    except ValueError as exc:
        raise OtaError(f"target path escapes the world root: {path}") from exc
    return path


def expected_target_rows(manifest: Mapping[str, Any], state: str) -> list[dict[str, Any]]:
    guards = {str(row["relative_path"]): dict(row) for row in manifest["guard_files"]}
    if state == "pre":
        return [
            {"relative_path": relative, "expected": row["pre"], "kind": row["kind"]}
            for relative, row in sorted(guards.items())
        ]
    if state != "post":
        raise OtaError(f"unsupported target state {state}")
    for change in manifest["changes"]:
        relative = str(change["relative_path"])
        if relative not in guards:
            raise OtaError(f"change is not covered by a preimage guard: {relative}")
        guards[relative]["expected_post"] = change["post"]
    return [
        {
            "relative_path": relative,
            "expected": row.get("expected_post", row["pre"]),
            "kind": row["kind"],
        }
        for relative, row in sorted(guards.items())
    ]


def verify_target(bundle_root: Path, world_root: Path, state: str) -> dict[str, Any]:
    manifest, plan = read_bundle(bundle_root)
    world_root = world_root.resolve()
    if not world_root.is_dir():
        raise OtaError(f"target world root is missing: {world_root}")
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for row in expected_target_rows(manifest, state):
        path = target_path(world_root, row["relative_path"])
        actual = file_identity_path(path)
        checked += 1
        if not identity_equal(actual, row["expected"]):
            mismatches.append(
                {"relative_path": row["relative_path"], "expected": row["expected"], "actual": actual}
            )
    if state == "post" and not mismatches:
        grouped = plan_slot_map(plan)
        changes = {str(row["relative_path"]): row for row in manifest["changes"]}
        for relative, row in changes.items():
            if not row["post"]["exists"]:
                continue
            region_x, region_z = (int(value) for value in row["region"])
            slots = grouped[(region_x, region_z)]
            data = target_path(world_root, relative).read_bytes()
            image = RegionImage.parse(data, f"target::{relative}")
            outside = frozenset(set(range(1024)) - set(slots))
            if image.signature(slots) != row["selected_post_signature"]:
                mismatches.append({"relative_path": relative, "reason": "selected-slot signature mismatch"})
            if image.signature(outside) != row["outside_post_signature"]:
                mismatches.append({"relative_path": relative, "reason": "outside-slot signature mismatch"})
    entity_checked = sum(1 for row in manifest["guard_files"] if row["kind"] == "entities")
    return {
        "schema": "protected-zone-terrain-ota-target-verification/v1",
        "generated_at_utc": utc_now(),
        "status": "PASS" if not mismatches else "BLOCKED",
        "state": state,
        "world_root": str(world_root),
        "checked_files": checked,
        "entities_byte_guard_files": entity_checked,
        "mismatches": mismatches,
        "world_modified": False,
    }


def require_world_write(allow: bool, stopped_ack: str | None) -> None:
    if not allow:
        raise OtaError("world mutation refused: pass --allow-world-write explicitly")
    if stopped_ack != STOPPED_ACK:
        raise OtaError(f"world mutation refused: --stopped-server-ack must equal {STOPPED_ACK}")


def paths_disjoint(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    try:
        left.relative_to(right)
        return False
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return False
    except ValueError:
        return True


def apply_bundle(
    bundle_root: Path,
    world_root: Path,
    backup_root: Path,
    *,
    allow_world_write: bool,
    stopped_ack: str | None,
) -> dict[str, Any]:
    require_world_write(allow_world_write, stopped_ack)
    bundle_root = bundle_root.resolve()
    world_root = world_root.resolve()
    backup_root = backup_root.resolve()
    if not world_root.is_dir():
        raise OtaError(f"target world root is missing: {world_root}")
    if backup_root.exists():
        raise OtaError(f"backup root already exists: {backup_root}")
    if not paths_disjoint(world_root, backup_root) or not paths_disjoint(bundle_root, backup_root):
        raise OtaError("backup root must be disjoint from world and bundle roots")
    manifest, _plan = read_bundle(bundle_root)
    preflight = verify_target(bundle_root, world_root, "pre")
    if preflight["status"] != "PASS":
        raise OtaError(f"preimage CAS mismatch; no files written: {preflight['mismatches'][:3]}")
    backup_root.mkdir(parents=True)
    journal_path = backup_root / "apply-receipt.json"
    entries: list[dict[str, Any]] = []
    for change in manifest["changes"]:
        relative = str(change["relative_path"])
        target = target_path(world_root, relative)
        backup_relative = f"preimage/{relative}" if change["pre"]["exists"] else None
        if backup_relative:
            backup = backup_root / Path(backup_relative)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            if not identity_equal(file_identity_path(backup), change["pre"]):
                raise OtaError(f"preimage backup verification failed: {relative}")
        entries.append(
            {
                "relative_path": relative,
                "pre": change["pre"],
                "post": change["post"],
                "backup_relative_path": backup_relative,
            }
        )
    receipt: dict[str, Any] = {
        "schema": SCHEMA_RECEIPT,
        "created_at_utc": utc_now(),
        "status": "PREPARED",
        "bundle_root": str(bundle_root),
        "bundle_manifest_sha256": sha256_file(bundle_root / "bundle.json"),
        "world_root": str(world_root),
        "backup_root": str(backup_root),
        "entries": entries,
        "applied_paths": [],
        "entity_guards": [row for row in manifest["guard_files"] if row["kind"] == "entities"],
    }
    atomic_write_json(journal_path, receipt)
    try:
        for change in manifest["changes"]:
            relative = str(change["relative_path"])
            target = target_path(world_root, relative)
            # Journal intent before the atomic replacement.  Recovery accepts
            # either the exact preimage (replacement never happened) or the
            # exact postimage (replacement completed); any third state is a
            # fail-closed external-tamper/storage-error condition.
            receipt["applied_paths"].append(relative)
            atomic_write_json(journal_path, receipt)
            if change["post"]["exists"]:
                payload = bundle_root / Path(str(change["payload_relative_path"]))
                data = payload.read_bytes()
                atomic_write_bytes(target, data)
            elif target.exists():
                target.unlink()
            actual = file_identity_path(target)
            if not identity_equal(actual, change["post"]):
                raise OtaError(f"postimage verification failed immediately after write: {relative}")
        postverify = verify_target(bundle_root, world_root, "post")
        if postverify["status"] != "PASS":
            raise OtaError(f"post-apply verification failed: {postverify['mismatches'][:3]}")
        receipt["status"] = "APPLIED_VERIFIED"
        receipt["completed_at_utc"] = utc_now()
        receipt["postverify"] = postverify
        atomic_write_json(journal_path, receipt)
        return receipt
    except Exception as original:
        rollback_errors: list[str] = []
        for relative in reversed(receipt["applied_paths"]):
            entry = next(row for row in entries if row["relative_path"] == relative)
            target = target_path(world_root, relative)
            try:
                actual = file_identity_path(target)
                if identity_equal(actual, entry["pre"]):
                    continue
                if not identity_equal(actual, entry["post"]):
                    raise OtaError("automatic rollback CAS mismatch")
                if entry["pre"]["exists"]:
                    backup = backup_root / Path(str(entry["backup_relative_path"]))
                    atomic_write_bytes(target, backup.read_bytes())
                elif target.exists():
                    target.unlink()
            except Exception as rollback_exc:  # pragma: no cover - catastrophic I/O branch
                rollback_errors.append(f"{relative}: {rollback_exc}")
        receipt["status"] = "AUTO_ROLLED_BACK" if not rollback_errors else "AUTO_ROLLBACK_FAILED"
        receipt["failure"] = f"{type(original).__name__}: {original}"
        receipt["rollback_errors"] = rollback_errors
        atomic_write_json(journal_path, receipt)
        if rollback_errors:
            raise OtaError(f"apply failed and automatic rollback was incomplete: {rollback_errors}") from original
        raise


def rollback_apply(
    apply_receipt_path: Path,
    *,
    allow_world_write: bool,
    stopped_ack: str | None,
) -> dict[str, Any]:
    require_world_write(allow_world_write, stopped_ack)
    receipt = load_json(apply_receipt_path.resolve())
    if receipt.get("schema") != SCHEMA_RECEIPT or receipt.get("status") != "APPLIED_VERIFIED":
        raise OtaError("receipt is not an applied, verified transaction")
    world_root = Path(str(receipt["world_root"])).resolve()
    backup_root = Path(str(receipt["backup_root"])).resolve()
    bundle_root = Path(str(receipt["bundle_root"])).resolve()
    if sha256_file(bundle_root / "bundle.json") != receipt.get("bundle_manifest_sha256"):
        raise OtaError("bundle manifest changed after apply")
    manifest, _plan = read_bundle(bundle_root)
    postverify = verify_target(bundle_root, world_root, "post")
    if postverify["status"] != "PASS":
        raise OtaError(f"rollback refused because postimage was tampered: {postverify['mismatches'][:3]}")
    for entry in receipt["entries"]:
        relative = str(entry["relative_path"])
        validate_relative_path(relative)
        if entry["pre"]["exists"]:
            backup = backup_root / Path(str(entry["backup_relative_path"]))
            if not identity_equal(file_identity_path(backup), entry["pre"]):
                raise OtaError(f"rollback preimage backup is missing or tampered: {relative}")
    for entry in receipt["entries"]:
        relative = str(entry["relative_path"])
        target = target_path(world_root, relative)
        if entry["pre"]["exists"]:
            backup = backup_root / Path(str(entry["backup_relative_path"]))
            atomic_write_bytes(target, backup.read_bytes())
        elif target.exists():
            target.unlink()
    preverify = verify_target(bundle_root, world_root, "pre")
    if preverify["status"] != "PASS":  # pragma: no cover - catastrophic storage failure
        raise OtaError(f"rollback completed writes but preimage verification failed: {preverify['mismatches'][:3]}")
    result = {
        "schema": "protected-zone-terrain-ota-rollback-receipt/v1",
        "generated_at_utc": utc_now(),
        "status": "ROLLED_BACK_VERIFIED",
        "apply_receipt": str(apply_receipt_path.resolve()),
        "world_root": str(world_root),
        "restored_entries": len(receipt["entries"]),
        "entities_byte_guard_files": sum(1 for row in manifest["guard_files"] if row["kind"] == "entities"),
        "preverify": preverify,
    }
    atomic_write_json(backup_root / "rollback-receipt.json", result)
    return result


def print_result(result: Mapping[str, Any], output: Path | None = None) -> None:
    if output is not None:
        atomic_write_json(output.resolve(), result)
    summary = {
        key: result.get(key)
        for key in ("schema", "status", "state", "checked_files", "restored_entries")
        if key in result
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="read-only current-ZIP inventory")
    inspect_parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT_ZIP)
    inspect_parser.add_argument("--current-world-prefix")
    inspect_parser.add_argument("--output", type=Path, required=True)
    inspect_parser.add_argument("--skip-archive-sha", action="store_true")

    plan_parser = subparsers.add_parser("plan", help="read-only plan against current C and donor V")
    plan_parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT_ZIP)
    plan_parser.add_argument("--current-world-prefix")
    plan_parser.add_argument("--donor", type=Path, required=True)
    plan_parser.add_argument("--donor-world-prefix")
    plan_parser.add_argument(
        "--poi-policy", choices=("preserve-current", "donor-selected"), required=True
    )
    plan_parser.add_argument("--output", type=Path, required=True)

    build = subparsers.add_parser("build", help="build a detached bundle; never edits a world")
    build.add_argument("--plan", type=Path, required=True)
    build.add_argument("--bundle-root", type=Path, required=True)
    build.add_argument("--output", type=Path)

    verify_bundle_parser = subparsers.add_parser("verify-bundle", help="verify detached bundle hashes")
    verify_bundle_parser.add_argument("--bundle-root", type=Path, required=True)
    verify_bundle_parser.add_argument("--output", type=Path)

    verify_target_parser = subparsers.add_parser("verify-target", help="read-only target CAS verification")
    verify_target_parser.add_argument("--bundle-root", type=Path, required=True)
    verify_target_parser.add_argument("--world", type=Path, required=True)
    verify_target_parser.add_argument("--state", choices=("pre", "post"), default="post")
    verify_target_parser.add_argument("--output", type=Path)

    apply_parser = subparsers.add_parser("apply", help="CAS apply to a stopped extracted world")
    apply_parser.add_argument("--bundle-root", type=Path, required=True)
    apply_parser.add_argument("--world", type=Path, required=True)
    apply_parser.add_argument("--backup-root", type=Path, required=True)
    apply_parser.add_argument("--allow-world-write", action="store_true")
    apply_parser.add_argument("--stopped-server-ack")

    rollback_parser = subparsers.add_parser("rollback", help="CAS rollback an applied transaction")
    rollback_parser.add_argument("--apply-receipt", type=Path, required=True)
    rollback_parser.add_argument("--allow-world-write", action="store_true")
    rollback_parser.add_argument("--stopped-server-ack")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            with open_source(
                args.current,
                args.current_world_prefix,
                compute_archive_hash=not args.skip_archive_sha,
            ) as current:
                print_result(inspect_current(current), args.output)
        elif args.command == "plan":
            with open_source(args.current, args.current_world_prefix) as current, open_source(
                args.donor, args.donor_world_prefix
            ) as donor:
                print_result(create_plan(current, donor, args.poi_policy), args.output)
        elif args.command == "build":
            result = build_bundle(args.plan, args.bundle_root)
            print_result(result, args.output)
        elif args.command == "verify-bundle":
            manifest, _plan = read_bundle(args.bundle_root)
            result = {
                "schema": "protected-zone-terrain-ota-bundle-verification/v1",
                "generated_at_utc": utc_now(),
                "status": "PASS",
                "bundle_root": str(args.bundle_root.resolve()),
                "changes": len(manifest["changes"]),
                "entities_in_payload": 0,
                "world_modified": False,
            }
            print_result(result, args.output)
        elif args.command == "verify-target":
            print_result(verify_target(args.bundle_root, args.world, args.state), args.output)
        elif args.command == "apply":
            print_result(
                apply_bundle(
                    args.bundle_root,
                    args.world,
                    args.backup_root,
                    allow_world_write=args.allow_world_write,
                    stopped_ack=args.stopped_server_ack,
                )
            )
        elif args.command == "rollback":
            print_result(
                rollback_apply(
                    args.apply_receipt,
                    allow_world_write=args.allow_world_write,
                    stopped_ack=args.stopped_server_ack,
                )
            )
        else:  # pragma: no cover
            raise OtaError(f"unsupported command {args.command}")
        return 0
    except (OtaError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "BLOCKED", "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
