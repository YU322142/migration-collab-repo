#!/usr/bin/env python3
"""Read-only empty-slot audit for the target 1.21.1 protected Overworld zone.

Unlike the historical source-world audit, this verifier expects DataVersion
3955 and uses the exact discrete-block intersection rule: a chunk is selected
when at least one integer block coordinate in its 16x16 square lies inside or
on the requested circle.  It never writes to the audited world.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nbtlib

from audit_terrain_biome_ota_inputs import RegionView, selected_chunks


EXPECTED_SEED = -794_095_451_117_350_581
EXPECTED_DATA_VERSION = 3_955
MCA_KINDS = ("region", "entities", "poi")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    if hasattr(value, "tolist"):
        return [plain(child) for child in value.tolist()]
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    return value


def read_level(world: Path) -> dict[str, Any]:
    path = world / "level.dat"
    if not path.is_file():
        return {"path": str(path), "exists": False}
    with gzip.open(path, "rb") as stream:
        root = nbtlib.File.parse(stream, byteorder="big")
    data = plain(root.get("Data", root))
    settings = data.get("WorldGenSettings", {})
    dimensions = settings.get("dimensions", {})
    overworld = dimensions.get("minecraft:overworld", {})
    return {
        "path": str(path),
        "exists": True,
        "data_version": data.get("DataVersion"),
        "version_name": data.get("Version", {}).get("Name"),
        "seed": settings.get("seed"),
        "generate_features": settings.get("generate_features"),
        "overworld_generator": overworld.get("generator"),
    }


def audit(
    world: Path,
    center_x: int,
    center_z: int,
    core_radius: int,
    freeze_radius: int,
) -> dict[str, Any]:
    core = set(selected_chunks(center_x, center_z, core_radius))
    freeze = set(selected_chunks(center_x, center_z, freeze_radius))
    regions = sorted({(x // 32, z // 32) for x, z in freeze})
    target_slots = {
        (x // 32, z // 32, (x & 31) + (z & 31) * 32): (x, z)
        for x, z in freeze
    }
    blockers: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    per_kind: dict[str, Any] = {}
    manifests: list[dict[str, Any]] = []

    if len(core) != 12_500:
        blockers.append({"reason": "unexpected core chunk count", "actual": len(core), "expected": 12_500})
    if len(freeze) != 29_305:
        blockers.append(
            {"reason": "unexpected freeze chunk count", "actual": len(freeze), "expected": 29_305}
        )
    if len(regions) != 40:
        blockers.append({"reason": "unexpected region count", "actual": len(regions), "expected": 40})
    if not core <= freeze:
        blockers.append({"reason": "freeze selection does not fully cover the core selection"})

    for kind in MCA_KINDS:
        occupied: list[dict[str, Any]] = []
        present = 0
        for region_x, region_z in regions:
            path = world / kind / f"r.{region_x}.{region_z}.mca"
            try:
                view = RegionView(path)
            except Exception as exc:
                parse_errors.append(
                    {
                        "kind": kind,
                        "region": [region_x, region_z],
                        "path": str(path),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            if view.exists:
                present += 1
                manifests.append(
                    {
                        "kind": kind,
                        "region": [region_x, region_z],
                        "path": str(path),
                        "bytes": view.file_size,
                        "sha256": view.file_sha256,
                        "occupied_slots": len(view.locations),
                    }
                )
            for slot in sorted(view.locations):
                key = (region_x, region_z, slot)
                if key in target_slots:
                    occupied.append(
                        {
                            "chunk": list(target_slots[key]),
                            "region": [region_x, region_z],
                            "slot": slot,
                        }
                    )
        per_kind[kind] = {
            "candidate_region_files_present": present,
            "occupied_target_slots": len(occupied),
            "occupied_rows": occupied[:200],
        }
        if occupied:
            blockers.append(
                {"reason": f"{kind} target slots are occupied", "count": len(occupied)}
            )

    level = read_level(world)
    if not level.get("exists"):
        blockers.append({"reason": "level.dat is missing"})
    if level.get("data_version") != EXPECTED_DATA_VERSION:
        blockers.append(
            {
                "reason": "target DataVersion mismatch",
                "actual": level.get("data_version"),
                "expected": EXPECTED_DATA_VERSION,
            }
        )
    if level.get("seed") != EXPECTED_SEED:
        blockers.append(
            {"reason": "seed mismatch", "actual": level.get("seed"), "expected": EXPECTED_SEED}
        )
    generator = level.get("overworld_generator") or {}
    if generator.get("type") != "minecraft:noise":
        blockers.append({"reason": "Overworld generator is not minecraft:noise", "actual": generator})
    if generator.get("settings") != "minecraft:overworld":
        blockers.append(
            {"reason": "Overworld noise settings are not minecraft:overworld", "actual": generator}
        )
    biome_source = generator.get("biome_source") or {}
    if biome_source.get("type") != "minecraft:multi_noise" or biome_source.get("preset") != "minecraft:overworld":
        blockers.append(
            {"reason": "Overworld biome source is not the vanilla overworld preset", "actual": biome_source}
        )
    if parse_errors:
        blockers.append({"reason": "MCA parse errors", "count": len(parse_errors)})

    return {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not blockers else "BLOCKED",
        "operation": "audit-protected-zone-target-1.21.1-readonly",
        "world": str(world),
        "selection": {
            "rule": (
                "Select a chunk when at least one integer block coordinate in its closed 16x16 "
                "square lies inside or on the circle."
            ),
            "center": {"x": center_x, "z": center_z},
            "core_radius_blocks": core_radius,
            "core_intersecting_chunks": len(core),
            "freeze_radius_blocks": freeze_radius,
            "selected_chunks": len(freeze),
            "selected_regions": len(regions),
            "core_fully_covered": core <= freeze,
        },
        "expected": {
            "minecraft": "1.21.1",
            "data_version": EXPECTED_DATA_VERSION,
            "seed": EXPECTED_SEED,
        },
        "level": level,
        "per_kind": per_kind,
        "existing_selected_region_manifest": manifests,
        "parse_errors": parse_errors,
        "blockers": blockers,
        "non_actions": {"world_modified": False, "java_started": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--center-x", type=int, default=10_192)
    parser.add_argument("--center-z", type=int, default=-1_574)
    parser.add_argument("--core-radius", type=int, default=1_000)
    parser.add_argument("--freeze-radius", type=int, default=1_536)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(
        args.world.resolve(),
        args.center_x,
        args.center_z,
        args.core_radius,
        args.freeze_radius,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "selection": report["selection"],
                "per_kind": report["per_kind"],
                "blockers": report["blockers"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
