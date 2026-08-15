#!/usr/bin/env python3

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import validate_worldgen_height_overlay as validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_OVERLAY = REPOSITORY_ROOT / "pack/worldgen-height-544-overlay"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_overlay(destination: Path) -> None:
    for source in REFERENCE_OVERLAY.rglob("*"):
        if source.is_file():
            target = destination / source.relative_to(REFERENCE_OVERLAY)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())


def write_minimal_assembled_server(root: Path) -> None:
    active = json.loads(
        (REFERENCE_OVERLAY / validator.ACTIVE_REL).read_text(encoding="utf-8")
    )
    write_json(root / validator.ACTIVE_REL, active)
    write_json(
        root / validator.DIMENSION_REL,
        {
            "type": "minecraft:overworld",
            "generator": {
                "type": "minecraft:noise",
                "biome_source": {
                    "type": "minecraft:multi_noise",
                    "preset": "minecraft:overworld",
                },
                "settings": "minecraft:overworld",
            },
        },
    )
    write_json(
        root / validator.NOISE_REL,
        {"noise": {"min_y": -64, "height": 384}, "sea_level": 63},
    )
    write_json(
        root / "kubejs/data/mechanomania_frontier/dimension_type/frontier.json",
        {"min_y": -64, "height": 544, "logical_height": 544},
    )
    write_json(
        root / "kubejs/data/mechanomania_frontier/dimension/frontier.json",
        {
            "type": "mechanomania_frontier:frontier",
            "generator": {
                "type": "minecraft:noise",
                "settings": "mechanomania_frontier:tectonic",
            },
        },
    )
    write_json(
        root
        / "kubejs/data/mechanomania_frontier/worldgen/noise_settings/tectonic.json",
        {"noise": {"min_y": -64, "height": 544}, "sea_level": 63},
    )


class HeightOverlayValidatorTests(unittest.TestCase):
    def test_reference_overlay_passes_static_validation(self) -> None:
        result = validator.validate_overlay(REFERENCE_OVERLAY, False)
        self.assertEqual(result["static_status"], "PASS", result["failed_check_ids"])
        self.assertEqual(result["production_release_status"], "BLOCKED")

    def test_missing_effective_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp)
            copy_overlay(overlay)
            (overlay / validator.ACTIVE_REL).unlink()
            result = validator.validate_overlay(overlay, False)
            self.assertIn("effective_path_json", result["failed_check_ids"])

    def test_wrong_registry_path_inside_overlay_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp)
            copy_overlay(overlay)
            write_json(overlay / validator.STALE_REL, {"height": 544})
            result = validator.validate_overlay(overlay, False)
            self.assertIn("no_invalid_stale_path_in_overlay", result["failed_check_ids"])
            self.assertIn("exactly_one_deployable_file", result["failed_check_ids"])

    def test_noise_settings_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp)
            copy_overlay(overlay)
            write_json(overlay / validator.NOISE_REL, {"noise": {"height": 544}})
            result = validator.validate_overlay(overlay, False)
            self.assertIn("no_overworld_noise_mutation", result["failed_check_ids"])

    def test_bad_height_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp)
            copy_overlay(overlay)
            path = overlay / validator.ACTIVE_REL
            value = json.loads(path.read_text(encoding="utf-8"))
            value["height"] = 384
            write_json(path, value)
            result = validator.validate_overlay(overlay, False)
            self.assertIn("dimension_type_height", result["failed_check_ids"])
            self.assertIn("max_build_y_479", result["failed_check_ids"])

    def test_transition_cannot_be_marked_ready_without_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp)
            copy_overlay(overlay)
            path = overlay / validator.CONTRACT_REL
            value = json.loads(path.read_text(encoding="utf-8"))
            value["same_overworld_transition"] = copy.deepcopy(
                value["same_overworld_transition"]
            )
            value["same_overworld_transition"]["activation"] = "READY"
            write_json(path, value)
            result = validator.validate_overlay(overlay, False)
            self.assertIn("transition_fail_closed", result["failed_check_ids"])

    def test_delete_list_requires_exact_preimage_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            overlay = Path(temp)
            copy_overlay(overlay)
            path = overlay / validator.DELETE_LIST_REL
            value = json.loads(path.read_text(encoding="utf-8"))
            value["delete_only_after_preimage_sha256_match"][0]["preimage_sha256"] = "00"
            write_json(path, value)
            result = validator.validate_overlay(overlay, False)
            self.assertIn("stale_path_delete_hash_guard", result["failed_check_ids"])

    def test_production_ready_request_fails_closed(self) -> None:
        result = validator.validate_overlay(REFERENCE_OVERLAY, True)
        self.assertEqual(result["static_status"], "FAIL")
        self.assertIn(
            "same_overworld_transition_production_ready",
            result["failed_check_ids"],
        )

    def test_minimal_post_merge_server_passes_assembled_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = Path(temp)
            write_minimal_assembled_server(server)
            result = validator.validate_assembled_server(server)
            self.assertEqual(result["status"], "PASS", result["failed_check_ids"])
            self.assertEqual(result["same_overworld_transition_status"], "BLOCKED")

    def test_assembled_server_rejects_stale_registry_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            server = Path(temp)
            write_minimal_assembled_server(server)
            write_json(server / validator.STALE_REL, {"height": 544})
            result = validator.validate_assembled_server(server)
            self.assertIn("assembled_stale_path_absent", result["failed_check_ids"])


if __name__ == "__main__":
    unittest.main()
