#!/usr/bin/env python3
"""Read-only audit of every generated Overworld chunk and its frontier.

The audit is deliberately independent of Minecraft/Java.  It reads only MCA
location tables, records the complete existing terrain footprint, identifies
every cardinal edge where an existing chunk touches an ungenerated chunk, and
writes a fail-closed JSON snapshot plus an SHA-256 file manifest.  The snapshot
is used as the immutable baseline before any Mechanomania world-generation
stack is allowed to create new chunks.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import struct
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import nbtlib
except ImportError:  # Optional for the fast footprint scan; required by blend-audit.
    nbtlib = None


REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
MCA_KINDS = ("region", "entities", "poi")
CARDINAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_locations(path: Path) -> dict[int, tuple[int, int]]:
    with path.open("rb") as stream:
        table = stream.read(4096)
    if len(table) != 4096:
        raise ValueError("truncated MCA location table")
    occupied: dict[int, tuple[int, int]] = {}
    for slot in range(1024):
        entry = table[slot * 4 : slot * 4 + 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if not offset:
            continue
        if offset < 2 or sectors < 1:
            raise ValueError(f"invalid slot {slot}: offset={offset}, sectors={sectors}")
        occupied[slot] = (offset, sectors)
    return occupied


def validate_allocations(path: Path, occupied: dict[int, tuple[int, int]]) -> None:
    sectors_total = (path.stat().st_size + 4095) // 4096
    used: set[int] = {0, 1}
    with path.open("rb") as stream:
        for slot, (offset, sectors) in occupied.items():
            allocation = set(range(offset, offset + sectors))
            if offset + sectors > sectors_total:
                raise ValueError(f"slot {slot}: allocation exceeds file length")
            overlap = allocation & used
            if overlap:
                raise ValueError(f"slot {slot}: overlapping sectors {sorted(overlap)[:8]}")
            used.update(allocation)
            stream.seek(offset * 4096)
            length_raw = stream.read(4)
            compression_raw = stream.read(1)
            if len(length_raw) != 4 or len(compression_raw) != 1:
                raise ValueError(f"slot {slot}: truncated chunk header")
            length = struct.unpack(">I", length_raw)[0]
            compression = compression_raw[0]
            if length < 1 or length + 4 > sectors * 4096:
                raise ValueError(f"slot {slot}: invalid chunk length {length}")
            if compression & 0x80:
                raise ValueError(f"slot {slot}: external .mcc payload is refused")
            if compression not in (1, 2, 3):
                raise ValueError(f"slot {slot}: unsupported compression {compression}")


def chunks_from_region(path: Path, region_x: int, region_z: int) -> set[tuple[int, int]]:
    occupied = read_locations(path)
    validate_allocations(path, occupied)
    return {
        (region_x * 32 + (slot & 31), region_z * 32 + (slot >> 5))
        for slot in occupied
    }


def read_chunk_nbt(path: Path, location: tuple[int, int]) -> Any:
    if nbtlib is None:
        raise RuntimeError("nbtlib is required for blend-audit")
    offset, sectors = location
    with path.open("rb") as stream:
        stream.seek(offset * 4096)
        length_raw = stream.read(4)
        compression_raw = stream.read(1)
        if len(length_raw) != 4 or len(compression_raw) != 1:
            raise ValueError("truncated chunk header")
        length = struct.unpack(">I", length_raw)[0]
        compression = compression_raw[0]
        if compression & 0x80:
            raise ValueError("external .mcc payload is refused")
        if length < 1 or length + 4 > sectors * 4096:
            raise ValueError(f"invalid chunk length {length}")
        payload = stream.read(length - 1)
    if len(payload) != length - 1:
        raise ValueError("truncated chunk payload")
    if compression == 1:
        raw = gzip.decompress(payload)
    elif compression == 2:
        raw = zlib.decompress(payload)
    elif compression == 3:
        raw = payload
    else:
        raise ValueError(f"unsupported compression {compression}")
    return nbtlib.File.parse(io.BytesIO(raw), byteorder="big")


def range_row(values: list[int]) -> dict[str, int] | None:
    if not values:
        return None
    return {"min": min(values), "max": max(values)}


def audit(world: Path, output: Path) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    terrain: set[tuple[int, int]] = set()
    files: list[dict[str, Any]] = []
    per_kind: dict[str, Any] = {}

    for kind in MCA_KINDS:
        root = world / kind
        kind_chunks: set[tuple[int, int]] = set()
        parse_errors = 0
        for path in sorted(root.glob("r.*.*.mca")) if root.is_dir() else []:
            # Empty MCA placeholders are produced by vanilla for regions with
            # no saved chunks.  They are not corruption and must not be fed to
            # the 8 KiB header parser; retain them in the file manifest so
            # later drift checks still protect the source tree.
            if path.stat().st_size == 0:
                files.append(
                    {
                        "kind": kind,
                        "relative_path": str(path.relative_to(world)).replace("\\", "/"),
                        "size": 0,
                        "sha256": sha256(path),
                        "region": list(map(int, REGION_RE.fullmatch(path.name).groups())),
                        "occupied_chunks": 0,
                        "empty_placeholder": True,
                    }
                )
                continue
            match = REGION_RE.fullmatch(path.name)
            if not match:
                continue
            region_x, region_z = map(int, match.groups())
            row: dict[str, Any] = {
                "kind": kind,
                "relative_path": str(path.relative_to(world)).replace("\\", "/"),
                "size": path.stat().st_size,
                "sha256": sha256(path),
                "region": [region_x, region_z],
            }
            try:
                chunks = chunks_from_region(path, region_x, region_z)
                kind_chunks.update(chunks)
                row["occupied_chunks"] = len(chunks)
            except Exception as exc:
                parse_errors += 1
                row["error"] = f"{type(exc).__name__}: {exc}"
                blockers.append({"path": str(path), "reason": row["error"]})
            files.append(row)
        if kind == "region":
            terrain = kind_chunks
        per_kind[kind] = {
            "file_count": sum(1 for row in files if row["kind"] == kind),
            "occupied_chunk_count": len(kind_chunks),
            "parse_errors": parse_errors,
        }

    frontier_edges: list[tuple[int, int, int, int]] = []
    frontier_existing: set[tuple[int, int]] = set()
    frontier_missing: set[tuple[int, int]] = set()
    missing_degree: Counter[tuple[int, int]] = Counter()
    for chunk_x, chunk_z in terrain:
        for delta_x, delta_z in CARDINAL:
            adjacent = (chunk_x + delta_x, chunk_z + delta_z)
            if adjacent in terrain:
                continue
            frontier_edges.append((chunk_x, chunk_z, adjacent[0], adjacent[1]))
            frontier_existing.add((chunk_x, chunk_z))
            frontier_missing.add(adjacent)
            missing_degree[adjacent] += 1

    protected_center = (10_192, -1_574)
    protected_radius = 1_536
    protected_chunks = {
        (x, z)
        for x in range((protected_center[0] - protected_radius) // 16 - 1,
                       (protected_center[0] + protected_radius) // 16 + 2)
        for z in range((protected_center[1] - protected_radius) // 16 - 1,
                       (protected_center[1] + protected_radius) // 16 + 2)
        if ((x * 16 + 8 - protected_center[0]) ** 2
            + (z * 16 + 8 - protected_center[1]) ** 2)
        <= protected_radius ** 2
    }
    protected_overlap = terrain & protected_chunks

    if not terrain:
        blockers.append({"reason": "no Overworld terrain chunks were found"})

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "audit-existing-terrain-frontier",
        "world": str(world),
        "policy": {
            "existing_chunk_rule": "Every occupied Overworld terrain chunk is immutable retained content.",
            "frontier_rule": "Every cardinal edge from an occupied chunk to an ungenerated chunk must be included in the final real-world continuity gate.",
            "release_rule": "Do not enable public generation with a changed noise router until the immutable manifest and complete-frontier gate both PASS.",
            "production_configuration_unchanged": True,
        },
        "per_kind": per_kind,
        "terrain": {
            "occupied_chunk_count": len(terrain),
            "chunk_x_range": range_row([x for x, _ in terrain]),
            "chunk_z_range": range_row([z for _, z in terrain]),
            "region_file_count": per_kind["region"]["file_count"],
        },
        "frontier": {
            "edge_count": len(frontier_edges),
            "existing_boundary_chunk_count": len(frontier_existing),
            "adjacent_ungenerated_chunk_count": len(frontier_missing),
            "edge_samples": [
                {"existing": [a, b], "ungenerated": [c, d]}
                for a, b, c, d in sorted(frontier_edges)[:100]
            ],
            "highest_missing_adjacency_samples": [
                {"ungenerated": [x, z], "existing_neighbors": count}
                for (x, z), count in sorted(
                    missing_degree.items(), key=lambda item: (-item[1], item[0])
                )[:100]
            ],
        },
        "requested_protected_zone": {
            "center_blocks": list(protected_center),
            "freeze_radius_blocks": protected_radius,
            "planned_chunk_count": len(protected_chunks),
            "already_generated_chunk_count": len(protected_overlap),
            "currently_ungenerated_chunk_count": len(protected_chunks - terrain),
            "note": "This zone is additional protected content; it does not replace the full existing-world frontier audit.",
        },
        "files": files,
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def verify(world: Path, baseline: Path, output: Path) -> dict[str, Any]:
    base = json.loads(baseline.read_text(encoding="utf-8"))
    blockers: list[dict[str, Any]] = []
    if base.get("status") != "PASS":
        blockers.append({"reason": "baseline audit is not PASS", "status": base.get("status")})
    for row in base.get("files", []):
        path = world / row["relative_path"]
        if not path.is_file():
            blockers.append({"reason": "retained MCA file is missing", "path": str(path)})
            continue
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        if actual_size != row["size"] or actual_hash != row["sha256"]:
            blockers.append({
                "reason": "retained MCA file changed",
                "path": str(path),
                "expected_size": row["size"],
                "actual_size": actual_size,
                "expected_sha256": row["sha256"],
                "actual_sha256": actual_hash,
            })
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "verify-existing-terrain-frontier",
        "world": str(world),
        "baseline": str(baseline),
        "baseline_sha256": sha256(baseline),
        "verified_file_count": len(base.get("files", [])),
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def audit_blending(world: Path, frontier_path: Path, output: Path) -> dict[str, Any]:
    """Require every old frontier chunk to advertise vanilla blending data.

    Minecraft 1.21.1 treats DataVersion >= 3441 chunks as "old generation"
    only when the root ``blending_data`` compound is present.  The converted
    1.21.11 chunks therefore cannot be assumed blendable based on version
    alone.  This reads only the 18,120 boundary chunks from the frontier audit.
    """

    frontier = json.loads(frontier_path.read_text(encoding="utf-8"))
    blockers: list[dict[str, Any]] = []
    if nbtlib is None:
        blockers.append({"reason": "nbtlib is unavailable"})
    if frontier.get("status") != "PASS":
        blockers.append({"reason": "frontier audit is not PASS", "status": frontier.get("status")})

    coordinates = {
        tuple(row["existing"])
        for row in frontier.get("frontier", {}).get("edge_samples", [])
    }
    # The compact frontier JSON intentionally stores only edge samples, while
    # the exact set is cheap and safer to derive again from MCA headers.
    terrain: set[tuple[int, int]] = set()
    locations_by_region: dict[tuple[int, int], tuple[Path, dict[int, tuple[int, int]]]] = {}
    region_root = world / "region"
    for path in sorted(region_root.glob("r.*.*.mca")):
        if path.stat().st_size == 0:
            continue
        match = REGION_RE.fullmatch(path.name)
        if not match:
            continue
        region_x, region_z = map(int, match.groups())
        try:
            occupied = read_locations(path)
            validate_allocations(path, occupied)
        except Exception as exc:
            blockers.append({"path": str(path), "reason": f"{type(exc).__name__}: {exc}"})
            continue
        locations_by_region[(region_x, region_z)] = (path, occupied)
        for slot in occupied:
            terrain.add((region_x * 32 + (slot & 31), region_z * 32 + (slot >> 5)))

    coordinates = {
        (chunk_x, chunk_z)
        for chunk_x, chunk_z in terrain
        if any((chunk_x + dx, chunk_z + dz) not in terrain for dx, dz in CARDINAL)
    }
    variants: Counter[tuple[int, bool, int | None, int | None]] = Counter()
    checked = 0
    missing: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for chunk_x, chunk_z in sorted(coordinates):
        region = (chunk_x // 32, chunk_z // 32)
        row = locations_by_region.get(region)
        if row is None:
            parse_errors.append({"chunk": [chunk_x, chunk_z], "reason": "region lookup missing"})
            continue
        path, occupied = row
        slot = (chunk_x & 31) + (chunk_z & 31) * 32
        location = occupied.get(slot)
        if location is None:
            parse_errors.append({"chunk": [chunk_x, chunk_z], "reason": "slot lookup missing"})
            continue
        try:
            root = read_chunk_nbt(path, location)
            version = int(root.get("DataVersion", -1))
            blend = root.get("blending_data")
            min_section = int(blend.get("min_section")) if blend is not None and "min_section" in blend else None
            max_section = int(blend.get("max_section")) if blend is not None and "max_section" in blend else None
            variants[(version, blend is not None, min_section, max_section)] += 1
            checked += 1
            # -64..320 is the vanilla 1.18+ old-generation area.  Tectonic may
            # generate through y=479, but blending must be anchored to the old
            # chunk's actual section range, not falsely extended upward.
            if blend is None or min_section != -4 or max_section != 20:
                missing.append({
                    "chunk": [chunk_x, chunk_z],
                    "data_version": version,
                    "has_blending_data": blend is not None,
                    "min_section": min_section,
                    "max_section": max_section,
                })
        except Exception as exc:
            parse_errors.append({"chunk": [chunk_x, chunk_z], "path": str(path), "reason": f"{type(exc).__name__}: {exc}"})

    if missing:
        blockers.append({
            "reason": "frontier chunks lack the exact vanilla old-generation blending marker",
            "count": len(missing),
            "samples": missing[:100],
        })
    if parse_errors:
        blockers.append({"reason": "frontier chunk NBT could not be verified", "count": len(parse_errors), "samples": parse_errors[:100]})
    if checked != len(coordinates):
        blockers.append({"reason": "not every frontier chunk was checked", "expected": len(coordinates), "checked": checked})

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "audit-frontier-blending-data",
        "world": str(world),
        "frontier_audit": str(frontier_path),
        "frontier_audit_sha256": sha256(frontier_path),
        "frontier_chunk_count": len(coordinates),
        "checked_chunk_count": checked,
        "variants": [
            {
                "data_version": version,
                "has_blending_data": present,
                "min_section": min_section,
                "max_section": max_section,
                "count": count,
            }
            for (version, present, min_section, max_section), count in sorted(variants.items())
        ],
        "required_marker": {"min_section": -4, "max_section": 20},
        "mechanism": "Minecraft 1.21.1 IOWorker marks DataVersion >=3441 chunks old only when blending_data exists; Tectonic's final density uses minecraft:blend_density and its blend-alpha data function.",
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def scan_blending_markers(world: Path, output: Path) -> dict[str, Any]:
    """Inventory blending markers for every terrain chunk in one dimension."""

    blockers: list[dict[str, Any]] = []
    variants: Counter[tuple[int, bool, int | None, int | None]] = Counter()
    examples: dict[tuple[int, bool, int | None, int | None], list[int]] = {}
    checked = 0
    terrain_root = world / "region"
    for path in sorted(terrain_root.glob("r.*.*.mca")) if terrain_root.is_dir() else []:
        if path.stat().st_size == 0:
            continue
        match = REGION_RE.fullmatch(path.name)
        if not match:
            continue
        region_x, region_z = map(int, match.groups())
        try:
            occupied = read_locations(path)
            validate_allocations(path, occupied)
        except Exception as exc:
            blockers.append({"path": str(path), "reason": f"{type(exc).__name__}: {exc}"})
            continue
        for slot, location in occupied.items():
            chunk_x = region_x * 32 + (slot & 31)
            chunk_z = region_z * 32 + (slot >> 5)
            try:
                root = read_chunk_nbt(path, location)
                version = int(root.get("DataVersion", -1))
                blend = root.get("blending_data")
                min_section = int(blend.get("min_section")) if blend is not None and "min_section" in blend else None
                max_section = int(blend.get("max_section")) if blend is not None and "max_section" in blend else None
                key = (version, blend is not None, min_section, max_section)
                variants[key] += 1
                examples.setdefault(key, [chunk_x, chunk_z])
                checked += 1
            except Exception as exc:
                blockers.append({"chunk": [chunk_x, chunk_z], "path": str(path), "reason": f"{type(exc).__name__}: {exc}"})

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "scan-blending-markers",
        "world": str(world),
        "checked_chunk_count": checked,
        "variants": [
            {
                "data_version": version,
                "has_blending_data": present,
                "min_section": min_section,
                "max_section": max_section,
                "count": count,
                "example_chunk": examples[(version, present, min_section, max_section)],
            }
            for (version, present, min_section, max_section), count in sorted(variants.items())
        ],
        "blockers": blockers,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--world", type=Path, required=True)
    scan.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--world", type=Path, required=True)
    check.add_argument("--baseline", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    blend = sub.add_parser("blend-audit")
    blend.add_argument("--world", type=Path, required=True)
    blend.add_argument("--frontier", type=Path, required=True)
    blend.add_argument("--output", type=Path, required=True)
    markers = sub.add_parser("marker-scan")
    markers.add_argument("--world", type=Path, required=True)
    markers.add_argument("--output", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "scan":
        result = audit(args.world, args.output)
    elif args.command == "verify":
        result = verify(args.world, args.baseline, args.output)
    elif args.command == "blend-audit":
        result = audit_blending(args.world, args.frontier, args.output)
    else:
        result = scan_blending_markers(args.world, args.output)
    print(json.dumps({"status": result["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
