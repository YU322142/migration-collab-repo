#!/usr/bin/env python3
"""Fail-closed static validator for the Overworld 544-height overlay.

This tool does not start Minecraft and never writes into a server or world.
It validates only the supplied overlay directory. With --require-production-ready
it intentionally fails while the same-Overworld transition contract remains
BLOCKED.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ACTIVE_REL = Path("kubejs/data/minecraft/dimension_type/overworld.json")
STALE_REL = Path("kubejs/data/minecraft/worldgen/dimension_type/overworld.json")
DIMENSION_REL = Path("kubejs/data/minecraft/dimension/overworld.json")
NOISE_REL = Path("kubejs/data/minecraft/worldgen/noise_settings/overworld.json")
CONTRACT_REL = Path("OVERLAY-CONTRACT.json")
DELETE_LIST_REL = Path(".ota-delete-list.json")

EXPECTED_DIMENSION_TYPE = {
    "min_y": -64,
    "height": 544,
    "logical_height": 544,
    "natural": True,
    "has_skylight": True,
    "has_ceiling": False,
    "effects": "minecraft:overworld",
}

EXPECTED_STATUS = "HEIGHT_OVERLAY_STATIC_PASS__SAME_WORLD_TRANSITION_BLOCKED"
EXPECTED_STALE_SHA256 = (
    "F037D47507D099F2BC74D1D6093E3D580EE8E62312AD15F41B46DF4EA801A817"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def add_check(checks: list[dict[str, Any]], check_id: str, ok: bool, detail: str) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "PASS" if ok else "FAIL",
            "detail": detail,
        }
    )


def validate_overlay(overlay: Path, require_production_ready: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    overlay = overlay.resolve()
    active = overlay / ACTIVE_REL
    stale = overlay / STALE_REL
    dimension = overlay / DIMENSION_REL
    noise = overlay / NOISE_REL
    contract_path = overlay / CONTRACT_REL
    delete_list_path = overlay / DELETE_LIST_REL

    add_check(
        checks,
        "overlay_directory_exists",
        overlay.is_dir(),
        str(overlay),
    )

    dimension_type: dict[str, Any] | None = None
    if active.is_file():
        try:
            loaded = load_json(active)
            if isinstance(loaded, dict):
                dimension_type = loaded
                add_check(checks, "effective_path_json", True, str(ACTIVE_REL))
            else:
                add_check(checks, "effective_path_json", False, "JSON root is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            add_check(checks, "effective_path_json", False, f"parse error: {exc}")
    else:
        add_check(checks, "effective_path_json", False, f"missing {ACTIVE_REL}")

    if dimension_type is not None:
        for key, expected in EXPECTED_DIMENSION_TYPE.items():
            actual = dimension_type.get(key)
            add_check(
                checks,
                f"dimension_type_{key}",
                actual == expected,
                f"expected={expected!r}, actual={actual!r}",
            )
        min_y = dimension_type.get("min_y")
        height = dimension_type.get("height")
        logical_height = dimension_type.get("logical_height")
        aligned = (
            isinstance(min_y, int)
            and isinstance(height, int)
            and min_y % 16 == 0
            and height > 0
            and height % 16 == 0
        )
        add_check(checks, "dimension_bounds_16_aligned", aligned, f"min_y={min_y}, height={height}")
        logical_valid = (
            isinstance(logical_height, int)
            and isinstance(height, int)
            and 0 < logical_height <= height
        )
        add_check(
            checks,
            "logical_height_within_dimension",
            logical_valid,
            f"logical_height={logical_height}, height={height}",
        )
        max_y = min_y + height - 1 if isinstance(min_y, int) and isinstance(height, int) else None
        add_check(checks, "max_build_y_479", max_y == 479, f"computed max_y={max_y}")

    add_check(
        checks,
        "no_invalid_stale_path_in_overlay",
        not stale.exists(),
        str(STALE_REL),
    )
    add_check(
        checks,
        "no_overworld_generator_mutation",
        not dimension.exists(),
        str(DIMENSION_REL),
    )
    add_check(
        checks,
        "no_overworld_noise_mutation",
        not noise.exists(),
        str(NOISE_REL),
    )

    contract: dict[str, Any] | None = None
    if contract_path.is_file():
        try:
            loaded = load_json(contract_path)
            if isinstance(loaded, dict):
                contract = loaded
                add_check(checks, "contract_json", True, str(CONTRACT_REL))
            else:
                add_check(checks, "contract_json", False, "JSON root is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            add_check(checks, "contract_json", False, f"parse error: {exc}")
    else:
        add_check(checks, "contract_json", False, f"missing {CONTRACT_REL}")

    if contract is not None:
        status = contract.get("status")
        add_check(
            checks,
            "contract_static_status",
            status == EXPECTED_STATUS,
            f"status={status!r}",
        )
        scope = contract.get("scope", {})
        add_check(
            checks,
            "contract_no_world_writes",
            scope.get("changes_world_files") is False,
            f"changes_world_files={scope.get('changes_world_files')!r}",
        )
        transition = contract.get("same_overworld_transition", {})
        transition_blocked = (
            transition.get("activation") == "BLOCKED"
            and transition.get("requires_both_side_neoforge_mod") is True
            and transition.get("not_implemented_by_this_overlay") is True
        )
        add_check(
            checks,
            "transition_fail_closed",
            transition_blocked,
            (
                f"activation={transition.get('activation')!r}, "
                f"requires_mod={transition.get('requires_both_side_neoforge_mod')!r}, "
                f"not_implemented={transition.get('not_implemented_by_this_overlay')!r}"
            ),
        )

    delete_list: dict[str, Any] | None = None
    if delete_list_path.is_file():
        try:
            loaded = load_json(delete_list_path)
            if isinstance(loaded, dict):
                delete_list = loaded
                add_check(checks, "delete_list_json", True, str(DELETE_LIST_REL))
            else:
                add_check(checks, "delete_list_json", False, "JSON root is not an object")
        except (OSError, json.JSONDecodeError) as exc:
            add_check(checks, "delete_list_json", False, f"parse error: {exc}")
    else:
        add_check(checks, "delete_list_json", False, f"missing {DELETE_LIST_REL}")

    if delete_list is not None:
        entries = delete_list.get("delete_only_after_preimage_sha256_match", [])
        matching = [entry for entry in entries if entry.get("path") == STALE_REL.as_posix()]
        guarded = (
            len(matching) == 1
            and str(matching[0].get("preimage_sha256", "")).upper() == EXPECTED_STALE_SHA256
        )
        add_check(
            checks,
            "stale_path_delete_hash_guard",
            guarded,
            f"matching_entries={len(matching)}",
        )

    deployable_files: list[str] = []
    kubejs_root = overlay / "kubejs"
    if kubejs_root.is_dir():
        deployable_files = sorted(
            path.relative_to(overlay).as_posix()
            for path in kubejs_root.rglob("*")
            if path.is_file()
        )
    add_check(
        checks,
        "exactly_one_deployable_file",
        deployable_files == [ACTIVE_REL.as_posix()],
        f"deployable_files={deployable_files}",
    )

    world_like = [
        path.relative_to(overlay).as_posix()
        for path in overlay.rglob("*")
        if path.is_file()
        and (
            path.name == "level.dat"
            or path.suffix.lower() in {".mca", ".mcc"}
            or "server.properties" == path.name
        )
    ]
    add_check(checks, "no_world_or_server_files", not world_like, f"matches={world_like}")

    production_ready = False
    if require_production_ready:
        add_check(
            checks,
            "same_overworld_transition_production_ready",
            production_ready,
            "The contract intentionally remains BLOCKED until the custom transition module and all runtime gates pass.",
        )

    failed = [check for check in checks if check["status"] == "FAIL"]
    result = {
        "schema_version": 1,
        "operation": "validate-worldgen-height-overlay",
        "overlay": str(overlay),
        "static_status": "PASS" if not failed else "FAIL",
        "production_release_status": "BLOCKED" if not production_ready else "PASS",
        "require_production_ready": require_production_ready,
        "active_file_sha256": sha256_file(active) if active.is_file() else None,
        "checks": checks,
        "failed_check_ids": [check["id"] for check in failed],
    }
    return result


def validate_assembled_server(server_root: Path) -> dict[str, Any]:
    """Validate the post-merge KubeJS registry state without starting Minecraft."""

    checks: list[dict[str, Any]] = []
    server_root = server_root.resolve()

    def read_object(relative: Path, check_id: str) -> dict[str, Any] | None:
        path = server_root / relative
        if not path.is_file():
            add_check(checks, check_id, False, f"missing {relative}")
            return None
        try:
            value = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            add_check(checks, check_id, False, f"parse error: {exc}")
            return None
        if not isinstance(value, dict):
            add_check(checks, check_id, False, "JSON root is not an object")
            return None
        add_check(checks, check_id, True, str(relative))
        return value

    active = read_object(ACTIVE_REL, "assembled_effective_dimension_type_json")
    if active is not None:
        for key, expected in EXPECTED_DIMENSION_TYPE.items():
            actual = active.get(key)
            add_check(
                checks,
                f"assembled_dimension_type_{key}",
                actual == expected,
                f"expected={expected!r}, actual={actual!r}",
            )

    add_check(
        checks,
        "assembled_stale_path_absent",
        not (server_root / STALE_REL).exists(),
        str(STALE_REL),
    )

    overworld_dimension = read_object(DIMENSION_REL, "assembled_overworld_dimension_json")
    if overworld_dimension is not None:
        generator = overworld_dimension.get("generator", {})
        biome_source = generator.get("biome_source", {}) if isinstance(generator, dict) else {}
        semantics = {
            "type": overworld_dimension.get("type"),
            "generator_type": generator.get("type") if isinstance(generator, dict) else None,
            "biome_source_type": biome_source.get("type") if isinstance(biome_source, dict) else None,
            "biome_preset": biome_source.get("preset") if isinstance(biome_source, dict) else None,
            "settings": generator.get("settings") if isinstance(generator, dict) else None,
        }
        expected = {
            "type": "minecraft:overworld",
            "generator_type": "minecraft:noise",
            "biome_source_type": "minecraft:multi_noise",
            "biome_preset": "minecraft:overworld",
            "settings": "minecraft:overworld",
        }
        add_check(
            checks,
            "assembled_overworld_generator_unchanged",
            semantics == expected,
            f"actual={semantics}",
        )

    overworld_noise = read_object(NOISE_REL, "assembled_overworld_noise_json")
    if overworld_noise is not None:
        noise = overworld_noise.get("noise", {})
        semantics = {
            "min_y": noise.get("min_y") if isinstance(noise, dict) else None,
            "height": noise.get("height") if isinstance(noise, dict) else None,
            "sea_level": overworld_noise.get("sea_level"),
        }
        expected = {"min_y": -64, "height": 384, "sea_level": 63}
        add_check(
            checks,
            "assembled_overworld_noise_remains_384",
            semantics == expected,
            f"actual={semantics}",
        )

    frontier_type_rel = Path(
        "kubejs/data/mechanomania_frontier/dimension_type/frontier.json"
    )
    frontier_dimension_rel = Path(
        "kubejs/data/mechanomania_frontier/dimension/frontier.json"
    )
    frontier_noise_rel = Path(
        "kubejs/data/mechanomania_frontier/worldgen/noise_settings/tectonic.json"
    )

    frontier_type = read_object(frontier_type_rel, "assembled_frontier_dimension_type_json")
    if frontier_type is not None:
        semantics = {
            "min_y": frontier_type.get("min_y"),
            "height": frontier_type.get("height"),
            "logical_height": frontier_type.get("logical_height"),
        }
        expected = {"min_y": -64, "height": 544, "logical_height": 544}
        add_check(
            checks,
            "assembled_frontier_dimension_type_544",
            semantics == expected,
            f"actual={semantics}",
        )

    frontier_dimension = read_object(
        frontier_dimension_rel, "assembled_frontier_dimension_json"
    )
    if frontier_dimension is not None:
        generator = frontier_dimension.get("generator", {})
        semantics = {
            "type": frontier_dimension.get("type"),
            "generator_type": generator.get("type") if isinstance(generator, dict) else None,
            "settings": generator.get("settings") if isinstance(generator, dict) else None,
        }
        expected = {
            "type": "mechanomania_frontier:frontier",
            "generator_type": "minecraft:noise",
            "settings": "mechanomania_frontier:tectonic",
        }
        add_check(
            checks,
            "assembled_frontier_generator_intact",
            semantics == expected,
            f"actual={semantics}",
        )

    frontier_noise = read_object(frontier_noise_rel, "assembled_frontier_noise_json")
    if frontier_noise is not None:
        noise = frontier_noise.get("noise", {})
        semantics = {
            "min_y": noise.get("min_y") if isinstance(noise, dict) else None,
            "height": noise.get("height") if isinstance(noise, dict) else None,
            "sea_level": frontier_noise.get("sea_level"),
        }
        expected = {"min_y": -64, "height": 544, "sea_level": 63}
        add_check(
            checks,
            "assembled_frontier_noise_544",
            semantics == expected,
            f"actual={semantics}",
        )

    failed = [check for check in checks if check["status"] == "FAIL"]
    return {
        "server_root": str(server_root),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_check_ids": [check["id"] for check in failed],
        "same_overworld_transition_status": "BLOCKED",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--assembled-server-root", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--require-production-ready", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_overlay(args.overlay, args.require_production_ready)
    if args.assembled_server_root:
        assembled = validate_assembled_server(args.assembled_server_root)
        result["assembled_server"] = assembled
        if assembled["status"] != "PASS":
            result["static_status"] = "FAIL"
            result["failed_check_ids"].extend(
                f"assembled::{check_id}" for check_id in assembled["failed_check_ids"]
            )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result["static_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
