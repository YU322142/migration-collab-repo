#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


BUILD_PATH = Path(__file__).with_name("build_terrain_preservation_final.py")
VALIDATE_PATH = Path(__file__).with_name("validate_terrain_preservation_final.py")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build = load_module("build_terrain_preservation_final", BUILD_PATH)
validate = load_module("validate_terrain_preservation_final", VALIDATE_PATH)


class TerrainPreservationTests(unittest.TestCase):
    def test_rewrite_strings_is_exact_and_recursive(self) -> None:
        value = {"a": "minecraft:x", "b": ["minecraft:x/y", {"c": "no"}]}
        mapping = {"minecraft:x": "frontier:x", "minecraft:x/y": "frontier:x/y"}
        self.assertEqual(
            build.rewrite_strings(value, mapping),
            {"a": "frontier:x", "b": ["frontier:x/y", {"c": "no"}]},
        )

    def test_dependency_closure_walks_transitive_resources(self) -> None:
        resources = [
            build.RegistryResource(
                "worldgen/density_function", "minecraft:a", "a", b'{"argument":"tectonic:b"}'
            ),
            build.RegistryResource(
                "worldgen/density_function", "tectonic:b", "b", b'{"argument":"minecraft:c"}'
            ),
            build.RegistryResource(
                "worldgen/noise", "minecraft:c", "c", b'{"firstOctave":-1,"amplitudes":[1.0]}'
            ),
            build.RegistryResource(
                "worldgen/noise", "minecraft:unused", "unused", b'{}'
            ),
        ]
        closure = build.dependency_closure([{"root": "minecraft:a"}], resources)
        self.assertEqual({row.key for row in closure}, {"minecraft:a", "tectonic:b", "minecraft:c"})

    def test_same_key_in_two_registries_is_preserved(self) -> None:
        resources = [
            build.RegistryResource("worldgen/density_function", "minecraft:x", "d", b'{}'),
            build.RegistryResource("worldgen/noise", "minecraft:x", "n", b'{}'),
        ]
        closure = build.dependency_closure([{"root": "minecraft:x"}], resources)
        self.assertEqual(len(closure), 2)

    def test_frontier_resource_id_retains_source_namespace(self) -> None:
        self.assertEqual(
            build.frontier_resource_id("tectonic:region/heart"),
            "mechanomania_frontier:tectonic/region/heart",
        )

    def test_tree_manifest_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "a").write_text("x", encoding="utf-8")
            rows_a, sha_a = build.tree_manifest(root)
            rows_b, sha_b = validate.tree_manifest(root, set())
            self.assertEqual(rows_a, rows_b)
            self.assertEqual(sha_a, sha_b)
            (root / "a").write_text("y", encoding="utf-8")
            _, sha_c = build.tree_manifest(root)
            self.assertNotEqual(sha_a, sha_c)

    def test_validate_evidence_fails_on_count_drift(self) -> None:
        frontier = {
            "status": "PASS",
            "terrain": {"occupied_chunk_count": 1},
            "frontier": {"edge_count": 21018, "existing_boundary_chunk_count": 18120},
            "requested_protected_zone": {"already_generated_chunk_count": 0},
        }
        blend = {"status": "BLOCKED", "checked_chunk_count": 18120, "variants": [{"has_blending_data": False}]}
        plan = {"geometry": {"freeze": {"chunk_count": 28950}}}
        with self.assertRaises(ValueError):
            build.validate_evidence(frontier, blend, plan)


if __name__ == "__main__":
    unittest.main()
