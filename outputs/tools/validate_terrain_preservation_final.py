#!/usr/bin/env python3
"""Validate the static terrain split decision and generated datapack."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FRONTIER = "mechanomania_frontier:frontier"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def tree_manifest(root: Path, exclude: set[str]) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in exclude:
            continue
        row = {"path": relative, "size": path.stat().st_size, "sha256": sha256(path)}
        rows.append(row)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return rows, digest.hexdigest().upper()


def validate(report_path: Path, datapack: Path, output: Path) -> dict[str, Any]:
    report = load(report_path)
    manifest_path = datapack / "FRONTIER-MANIFEST.json"
    manifest = load(manifest_path)
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    evidence = report.get("evidence", {})
    expect(report.get("status") == "READY_FOR_ISOLATED_RUNTIME_VALIDATION", "unexpected report status")
    expect(report.get("production_release_status") == "BLOCKED_FAIL_CLOSED", "production must remain fail-closed")
    expect(evidence.get("existing_terrain_chunks") == 927_157, "terrain count drift")
    expect(evidence.get("frontier_edges") == 21_018, "frontier count drift")
    expect(evidence.get("existing_boundary_chunks") == 18_120, "boundary count drift")
    expect(evidence.get("blending_missing_chunks") == 18_120, "blending evidence drift")
    expect(evidence.get("vanilla_height") == 384, "vanilla height drift")
    expect(evidence.get("tectonic_height") == 544, "Tectonic height drift")
    expect(evidence.get("height_delta") == 160, "height delta drift")
    expect(evidence.get("protected_existing_chunks") == 0, "protected area is no longer empty")
    expect(report.get("non_actions") == {
        "java_started": False,
        "world_modified": False,
        "level_dat_modified": False,
        "production_configuration_modified": False,
    }, "non-action safety declaration drift")

    for lock_name, lock in report.get("source_locks", {}).items():
        path = Path(lock["path"])
        expect(path.is_file(), f"missing locked source: {lock_name}")
        if path.is_file():
            expect(sha256(path) == lock["sha256"], f"source hash drift: {lock_name}")

    rows, tree_sha = tree_manifest(datapack, {"FRONTIER-MANIFEST.json"})
    expect(rows == manifest.get("files"), "datapack file manifest drift")
    expect(tree_sha == manifest.get("tree_sha256"), "datapack tree hash drift")
    expect(tree_sha == report.get("frontier_datapack", {}).get("tree_sha256"), "report/datapack tree mismatch")
    expect(manifest.get("frontier_dimension") == FRONTIER, "frontier dimension ID drift")

    required = {
        "pack.mcmeta",
        "README.md",
        "data/minecraft/dimension/overworld.json",
        "data/minecraft/dimension_type/overworld.json",
        "data/minecraft/worldgen/noise_settings/overworld.json",
        "data/mechanomania_frontier/dimension/frontier.json",
        "data/mechanomania_frontier/dimension_type/frontier.json",
        "data/mechanomania_frontier/worldgen/noise_settings/tectonic.json",
    }
    paths = {row["path"] for row in rows}
    expect(required <= paths, f"missing required files: {sorted(required - paths)}")

    if required <= paths:
        overworld_dimension = load(datapack / "data/minecraft/dimension/overworld.json")
        overworld_type = load(datapack / "data/minecraft/dimension_type/overworld.json")
        overworld_noise = load(datapack / "data/minecraft/worldgen/noise_settings/overworld.json")
        frontier_dimension = load(datapack / "data/mechanomania_frontier/dimension/frontier.json")
        frontier_type = load(datapack / "data/mechanomania_frontier/dimension_type/frontier.json")
        frontier_noise = load(datapack / "data/mechanomania_frontier/worldgen/noise_settings/tectonic.json")
        expect(overworld_dimension["generator"]["settings"] == "minecraft:overworld", "Overworld settings drift")
        expect(overworld_dimension["generator"]["biome_source"].get("preset") == "minecraft:overworld", "Overworld biome preset drift")
        expect(overworld_type.get("height") == 384 and overworld_type.get("logical_height") == 384, "Overworld type not 384")
        expect(overworld_noise.get("noise", {}).get("height") == 384, "Overworld noise not 384")
        expect(frontier_dimension.get("type") == "mechanomania_frontier:frontier", "frontier type reference drift")
        expect(frontier_dimension["generator"]["settings"] == "mechanomania_frontier:tectonic", "frontier noise reference drift")
        expect(frontier_type.get("height") == 544 and frontier_type.get("logical_height") == 544, "frontier type not 544")
        expect(frontier_noise.get("noise", {}).get("height") == 544, "frontier noise not 544")

    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if not failures else "BLOCKED",
        "operation": "validate-terrain-preservation-final",
        "report": str(report_path),
        "datapack": str(datapack),
        "checked_file_count": len(rows),
        "tree_sha256": tree_sha,
        "production_release_status": "BLOCKED_PENDING_RUNTIME",
        "failures": failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("outputs/terrain-preservation-final-20260813.json"))
    parser.add_argument("--datapack", type=Path, default=Path("outputs/terrain-preservation-frontier-datapack-20260813"))
    parser.add_argument("--output", type=Path, default=Path("outputs/terrain-preservation-final-validation-20260813.json"))
    args = parser.parse_args()
    result = validate(args.report, args.datapack, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
