#!/usr/bin/env python3
"""Regression tests for the protected-zone object-level entity OTA."""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import nbtlib

import protected_zone_entity_ota as ota


BUNDLE_ROOT = Path(r"D:\Trans\migration-audit-work\protected-entity-ota-20260815\bundle")
GATE_PATH = Path(__file__).resolve().parent.parent / "protected-zone-entity-collision-poi-gate-20260815.json"
V_WORLD = Path(
    r"D:\Trans\migration-audit-work\vanilla-reference-v-20260815"
    r"\strict-reference-world\vanilla-reference-v"
)
TEST_TEMP_PARENT = Path(r"D:\Trans\migration-audit-work\protected-entity-ota-tests-20260815")


class FlatIndex:
    """Tiny deterministic block index: stone at/below zero and air above."""

    def state(self, _x: int, y: int, _z: int) -> dict[str, object]:
        if y <= 0:
            return {"name": "minecraft:stone", "properties": {}}
        return {"name": "minecraft:air", "properties": {}}


class WaterIndex:
    """Stone floor at zero, water at y=1..4, air above."""

    def state(self, _x: int, y: int, _z: int) -> dict[str, object]:
        if y <= 0:
            return {"name": "minecraft:stone", "properties": {}}
        if y <= 4:
            return {"name": "minecraft:water", "properties": {"level": "0"}}
        return {"name": "minecraft:air", "properties": {}}


class SolidIndex:
    def state(self, _x: int, _y: int, _z: int) -> dict[str, object]:
        return {"name": "minecraft:stone", "properties": {}}


def bundle_file_maps(
    bundle_root: Path, manifest: dict[str, object]
) -> tuple[dict[str, bytes | None], dict[str, bytes | None]]:
    pre: dict[str, bytes | None] = {}
    post: dict[str, bytes | None] = {}
    changes = {str(row["relative_path"]): row for row in manifest["changes"]}  # type: ignore[index]
    for guard in manifest["guard_files"]:  # type: ignore[index]
        relative = str(guard["relative_path"])
        preimage_relative = guard.get("preimage_relative_path")
        value = (bundle_root / Path(str(preimage_relative))).read_bytes() if preimage_relative else None
        pre[relative] = value
        if relative in changes:
            change = changes[relative]
            payload_relative = change.get("payload_relative_path")
            post[relative] = (
                (bundle_root / Path(str(payload_relative))).read_bytes() if payload_relative else None
            )
        else:
            post[relative] = value
    return pre, post


class EntityOtaUnitTests(unittest.TestCase):
    def test_geometry_is_fixed(self) -> None:
        grouped = ota.terrain_ota.selection_by_region()
        self.assertEqual(len(grouped), ota.EXPECTED_REGIONS)
        self.assertEqual(sum(len(slots) for slots in grouped.values()), ota.EXPECTED_CHUNKS)

    def test_payload_hash_ignores_only_position(self) -> None:
        entity = nbtlib.Compound(
            {
                "id": nbtlib.String("minecraft:item"),
                "UUID": nbtlib.IntArray([1, 2, 3, 4]),
                "Pos": nbtlib.List[nbtlib.Double]([1.0, 2.0, 3.0]),
                "Item": nbtlib.Compound(
                    {"id": nbtlib.String("minecraft:diamond"), "count": nbtlib.Int(7)}
                ),
            }
        )
        original = ota.entity_payload_sha256(entity)
        moved = copy.deepcopy(entity)
        ota.set_entity_position(moved, [9.0, 10.0, 11.0])
        self.assertEqual(original, ota.entity_payload_sha256(moved))
        moved["Item"]["count"] = nbtlib.Int(6)
        self.assertNotEqual(original, ota.entity_payload_sha256(moved))

    def test_ground_support_and_collision(self) -> None:
        selected = {(0, 0)}
        self.assertTrue(
            ota.position_is_safe(
                FlatIndex(), [0.5, 1.0, 0.5], "minecraft:pig", "ground", selected
            )[0]
        )
        self.assertFalse(
            ota.position_is_safe(
                FlatIndex(), [0.5, 0.0, 0.5], "minecraft:pig", "ground", selected
            )[0]
        )
        self.assertFalse(
            ota.position_is_safe(
                WaterIndex(), [0.5, 2.0, 0.5], "minecraft:item", "item", selected
            )[0],
            "water must not be accepted as an item air/support destination",
        )

    def test_aquatic_requires_full_water_body(self) -> None:
        selected = {(0, 0)}
        self.assertTrue(
            ota.position_is_safe(
                WaterIndex(), [0.5, 1.0, 0.5], "minecraft:drowned", "aquatic", selected
            )[0]
        )
        self.assertFalse(
            ota.position_is_safe(
                FlatIndex(), [0.5, 1.0, 0.5], "minecraft:drowned", "aquatic", selected
            )[0]
        )

    def test_falling_block_has_clear_fall_path(self) -> None:
        selected = {(0, 0)}
        self.assertTrue(
            ota.position_is_safe(
                FlatIndex(), [0.5, 2.0, 0.5], "minecraft:falling_block", "falling_block", selected
            )[0]
        )
        self.assertFalse(
            ota.position_is_safe(
                FlatIndex(), [0.5, 1.0, 0.5], "minecraft:falling_block", "falling_block", selected
            )[0]
        )

    def test_deterministic_choice(self) -> None:
        selected = {(0, 0)}
        old_radius = ota.CATEGORY_RADIUS["ground"]
        ota.CATEGORY_RADIUS["ground"] = 2
        try:
            first = ota.relocate_entity(
                FlatIndex(),
                "minecraft:pig",
                "00000000-0000-0000-0000-000000000001",
                [1.5, 1.0, 1.5],
                "ground",
                selected,
                [],
            )
            second = ota.relocate_entity(
                FlatIndex(),
                "minecraft:pig",
                "00000000-0000-0000-0000-000000000001",
                [1.5, 1.0, 1.5],
                "ground",
                selected,
                [],
            )
        finally:
            ota.CATEGORY_RADIUS["ground"] = old_radius
        self.assertEqual(first["new_pos"], second["new_pos"])
        self.assertTrue(first["assignment_is_unique"])

    def test_no_safe_point_blocks(self) -> None:
        selected = {(0, 0)}
        old_radius = ota.CATEGORY_RADIUS["ground"]
        ota.CATEGORY_RADIUS["ground"] = 1
        try:
            with self.assertRaises(ota.EntityOtaError):
                ota.relocate_entity(
                    SolidIndex(),
                    "minecraft:pig",
                    "00000000-0000-0000-0000-000000000002",
                    [1.5, 1.0, 1.5],
                    "ground",
                    selected,
                    [],
                )
        finally:
            ota.CATEGORY_RADIUS["ground"] = old_radius


@unittest.skipUnless(BUNDLE_ROOT.is_dir() and V_WORLD.is_dir() and GATE_PATH.is_file(), "real bundle inputs missing")
class EntityOtaRealBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.plan = ota.read_bundle(BUNDLE_ROOT)
        cls.pre_files, cls.post_files = bundle_file_maps(BUNDLE_ROOT, cls.manifest)
        cls.pre_dataset = ota.load_current_dataset(ota.ByteMapWorldSource(cls.pre_files))
        cls.post_dataset = ota.load_current_dataset(ota.ByteMapWorldSource(cls.post_files))

    def test_real_bundle_reparses_all_entities_and_payloads(self) -> None:
        self.assertEqual(len(self.pre_dataset.entities), ota.EXPECTED_ENTITIES)
        self.assertEqual(len(self.post_dataset.entities), ota.EXPECTED_ENTITIES)
        self.assertEqual(set(self.pre_dataset.entities), set(self.post_dataset.entities))
        for entity_uuid in self.pre_dataset.entities:
            self.assertEqual(
                self.pre_dataset.entities[entity_uuid].payload_sha256,
                self.post_dataset.entities[entity_uuid].payload_sha256,
            )

    def test_real_item_payloads_are_exact(self) -> None:
        item_uuids = [
            entity_uuid
            for entity_uuid, record in self.pre_dataset.entities.items()
            if record.identifier == "minecraft:item"
        ]
        self.assertEqual(len(item_uuids), 65)
        for entity_uuid in item_uuids:
            before = self.pre_dataset.entities[entity_uuid].entity
            after = self.post_dataset.entities[entity_uuid].entity
            self.assertEqual(ota.typed_plain(before.get("Item")), ota.typed_plain(after.get("Item")))

    def test_real_assignments_are_safe_and_bound(self) -> None:
        gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
        rows = ota.validate_gate_against_dataset(gate, self.pre_dataset)
        ota.validate_assignments(self.pre_dataset, rows, self.plan["assignments"], V_WORLD)
        self.assertEqual(self.plan["summary"]["moved"], 72)
        self.assertEqual(self.plan["summary"]["cross_chunk_moves"], 11)

    def test_real_outside_slots_and_timestamps_are_identical(self) -> None:
        for guard in self.manifest["guard_files"]:
            self.assertEqual(guard["outside_pre_signature"], guard["outside_post_signature"])
            region = tuple(int(value) for value in guard["region"])
            selected = ota.terrain_ota.selection_by_region()[region]
            outside = frozenset(set(range(1024)) - set(selected))
            pre = ota.terrain_ota.RegionImage.parse(
                self.pre_files[guard["relative_path"]], f"test-pre::{guard['relative_path']}"
            )
            post = ota.terrain_ota.RegionImage.parse(
                self.post_files[guard["relative_path"]], f"test-post::{guard['relative_path']}"
            )
            self.assertEqual(pre.signature(outside), post.signature(outside))

    def test_real_apply_idempotence_tamper_refusal_and_rollback(self) -> None:
        TEST_TEMP_PARENT.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix="transaction-", dir=TEST_TEMP_PARENT))
        world = temporary / "world"
        world.mkdir()
        for guard in self.manifest["guard_files"]:
            if not guard["pre"]["exists"]:
                continue
            relative = str(guard["relative_path"])
            target = world / Path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.pre_files[relative])
        backup = temporary / "backup"
        try:
            self.assertEqual(ota.verify_target(BUNDLE_ROOT, world, "pre")["status"], "PASS")
            receipt = ota.apply_bundle(
                BUNDLE_ROOT,
                world,
                backup,
                allow_world_write=True,
                stopped_ack=ota.STOPPED_ACK,
            )
            self.assertEqual(receipt["status"], "APPLIED_VERIFIED")
            self.assertEqual(ota.verify_target(BUNDLE_ROOT, world, "post")["status"], "PASS")
            idempotent = ota.apply_bundle(
                BUNDLE_ROOT,
                world,
                temporary / "unused-idempotent-backup",
                allow_world_write=True,
                stopped_ack=ota.STOPPED_ACK,
            )
            self.assertEqual(idempotent["status"], "ALREADY_APPLIED_VERIFIED")

            change = self.manifest["changes"][0]
            tampered = world / Path(str(change["relative_path"]))
            tampered.write_bytes(tampered.read_bytes() + b"tamper")
            with self.assertRaises(ota.EntityOtaError):
                ota.apply_bundle(
                    BUNDLE_ROOT,
                    world,
                    temporary / "tamper-backup",
                    allow_world_write=True,
                    stopped_ack=ota.STOPPED_ACK,
                )
            payload = BUNDLE_ROOT / Path(str(change["payload_relative_path"]))
            tampered.write_bytes(payload.read_bytes())

            rolled_back = ota.rollback_apply(
                backup / "apply-receipt.json",
                allow_world_write=True,
                stopped_ack=ota.STOPPED_ACK,
            )
            self.assertEqual(rolled_back["status"], "ROLLED_BACK_VERIFIED")
            self.assertEqual(ota.verify_target(BUNDLE_ROOT, world, "pre")["status"], "PASS")
            again = ota.rollback_apply(
                backup / "apply-receipt.json",
                allow_world_write=True,
                stopped_ack=ota.STOPPED_ACK,
            )
            self.assertEqual(again["status"], "ALREADY_ROLLED_BACK_VERIFIED")
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    def test_write_guard_requires_both_flags(self) -> None:
        with self.assertRaises(ota.EntityOtaError):
            ota.require_world_write(False, ota.STOPPED_ACK)
        with self.assertRaises(ota.EntityOtaError):
            ota.require_world_write(True, "wrong")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    unittest.main(verbosity=2)
