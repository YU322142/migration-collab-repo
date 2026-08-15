#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("protected_zone_terrain_ota.py")
SPEC = importlib.util.spec_from_file_location("protected_zone_terrain_ota", MODULE_PATH)
assert SPEC and SPEC.loader
ota = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ota
SPEC.loader.exec_module(ota)


def raw_record(payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 1) + b"\x03" + payload


def mca(records: dict[int, tuple[int, bytes]]) -> bytes:
    return ota.RegionImage(
        {
            slot: ota.ChunkRecord(timestamp=timestamp, raw=raw_record(payload))
            for slot, (timestamp, payload) in records.items()
        },
        [records[slot][0] if slot in records else 0 for slot in range(1024)],
    ).encode()


def write_minimal_bundle(
    root: Path,
    pre_region: bytes,
    post_region: bytes,
    entity_data: bytes,
    region: tuple[int, int],
) -> Path:
    bundle = root / "bundle"
    bundle.mkdir()
    grouped = ota.selection_by_region()
    slots = grouped[region]
    outside = frozenset(set(range(1024)) - set(slots))
    relative = ota.region_relative("region", *region)
    entity_relative = ota.region_relative("entities", *region)
    pre_image = ota.RegionImage.parse(pre_region, "pre")
    post_image = ota.RegionImage.parse(post_region, "post")
    plan = {
        "schema": ota.SCHEMA_PLAN,
        "status": "READY_FOR_DETACHED_BUNDLE_BUILD",
        "selection": ota.selection_json(grouped),
        "poi_policy": "preserve-current",
    }
    ota.atomic_write_json(bundle / "plan.json", plan)
    payload = bundle / "payload" / Path(relative)
    ota.atomic_write_bytes(payload, post_region)
    manifest = {
        "schema": ota.SCHEMA_BUNDLE,
        "status": "READY_FOR_STOPPED_SERVER_APPLY",
        "plan_sha256": ota.sha256_file(bundle / "plan.json"),
        "selection": plan["selection"],
        "poi_policy": "preserve-current",
        "guard_files": [
            {
                "relative_path": relative,
                "kind": "region",
                "pre": ota.file_identity_bytes(pre_region),
                "selected_signature": pre_image.signature(slots),
            },
            {
                "relative_path": entity_relative,
                "kind": "entities",
                "pre": ota.file_identity_bytes(entity_data),
                "selected_signature": ota.RegionImage.parse(entity_data, "entity").signature(slots),
            },
        ],
        "changes": [
            {
                "relative_path": relative,
                "kind": "region",
                "region": list(region),
                "pre": ota.file_identity_bytes(pre_region),
                "post": ota.file_identity_bytes(post_region),
                "payload_relative_path": f"payload/{relative}",
                "selected_post_signature": post_image.signature(slots),
                "outside_post_signature": post_image.signature(outside),
            }
        ],
        "rules": {"entities": "never write"},
    }
    ota.atomic_write_json(bundle / "bundle.json", manifest)
    return bundle


class GeometryTests(unittest.TestCase):
    def test_locked_discrete_boundary_geometry(self) -> None:
        chunks = set(ota.selected_chunks())
        grouped = ota.selection_by_region()
        self.assertEqual(len(chunks), 29_305)
        self.assertEqual(len(grouped), 40)
        self.assertEqual(sum(len(slots) for slots in grouped.values()), 29_305)

        center_chunk_z = ota.CENTER_Z // 16
        east_edge = (ota.CENTER_X + ota.FREEZE_RADIUS) // 16
        west_edge = (ota.CENTER_X - ota.FREEZE_RADIUS) // 16
        self.assertIn((east_edge, center_chunk_z), chunks)
        self.assertNotIn((east_edge + 1, center_chunk_z), chunks)
        self.assertIn((west_edge, center_chunk_z), chunks)
        self.assertNotIn((west_edge - 1, center_chunk_z), chunks)

    def test_negative_region_and_slot_math(self) -> None:
        self.assertEqual(-1 // 32, -1)
        self.assertEqual(ota.slot_for_chunk(637, -99), (637 & 31) + (-99 & 31) * 32)


class RegionMergeTests(unittest.TestCase):
    def test_selected_from_donor_outside_byte_semantics_from_current(self) -> None:
        current = mca({0: (111, b"CURRENT_SELECTED"), 1: (222, b"CURRENT_OUTSIDE")})
        donor = mca({0: (333, b"VANILLA_SELECTED"), 1: (444, b"DONOR_OUTSIDE")})
        result = ota.merge_region_bytes(
            current,
            donor,
            frozenset({0}),
            kind="region",
            require_every_donor_slot=True,
            current_label="C",
            donor_label="V",
        )
        output = ota.RegionImage.parse(result["post_data"], "output")
        current_image = ota.RegionImage.parse(current, "current")
        donor_image = ota.RegionImage.parse(donor, "donor")
        self.assertEqual(output.records[0].raw, donor_image.records[0].raw)
        self.assertEqual(output.timestamps[0], 333)
        self.assertEqual(output.records[1].raw, current_image.records[1].raw)
        self.assertEqual(output.timestamps[1], 222)
        self.assertEqual(result["outside_pre_signature"], result["outside_post_signature"])
        self.assertNotEqual(output.records[1].raw, donor_image.records[1].raw)

    def test_zero_byte_current_mca_is_supported(self) -> None:
        donor = mca({0: (9, b"DONOR")})
        result = ota.merge_region_bytes(
            b"",
            donor,
            frozenset({0}),
            kind="region",
            require_every_donor_slot=True,
            current_label="zero-byte C",
            donor_label="V",
        )
        output = ota.RegionImage.parse(result["post_data"], "output")
        self.assertIn(0, output.records)
        self.assertTrue(result["pre"]["exists"])
        self.assertEqual(result["pre"]["bytes"], 0)

    def test_zero_byte_donor_fails_closed_for_terrain(self) -> None:
        with self.assertRaisesRegex(ota.OtaError, "missing 1 required selected terrain slots"):
            ota.merge_region_bytes(
                mca({}),
                b"",
                frozenset({0}),
                kind="region",
                require_every_donor_slot=True,
                current_label="C",
                donor_label="zero-byte V",
            )

    def test_poi_selected_deletion_is_separate_and_preserves_outside(self) -> None:
        current = mca({0: (10, b"SELECTED_POI"), 1: (20, b"OUTSIDE_POI")})
        result = ota.merge_region_bytes(
            current,
            b"",
            frozenset({0}),
            kind="poi",
            require_every_donor_slot=False,
            current_label="C poi",
            donor_label="V poi",
        )
        output = ota.RegionImage.parse(result["post_data"], "output poi")
        self.assertNotIn(0, output.records)
        self.assertEqual(output.records[1].raw, ota.RegionImage.parse(current, "C").records[1].raw)
        self.assertEqual(result["outside_pre_signature"], result["outside_post_signature"])

    def test_external_mcc_is_refused(self) -> None:
        data = bytearray(ota.HEADER_BYTES + ota.SECTOR_BYTES)
        data[:3] = (2).to_bytes(3, "big")
        data[3] = 1
        struct.pack_into(">I", data, ota.HEADER_BYTES, 1)
        data[ota.HEADER_BYTES + 4] = 0x82
        with self.assertRaisesRegex(ota.OtaError, "external .mcc"):
            ota.RegionImage.parse(bytes(data), "external")


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.grouped = ota.selection_by_region()
        self.region = next(iter(self.grouped))
        selected_slot = next(iter(self.grouped[self.region]))
        outside_slot = next(iter(set(range(1024)) - set(self.grouped[self.region])))
        self.pre_region = mca(
            {
                selected_slot: (1, b"C_SELECTED"),
                outside_slot: (2, b"C_OUTSIDE"),
            }
        )
        self.post_region = mca(
            {
                selected_slot: (3, b"V_SELECTED"),
                outside_slot: (2, b"C_OUTSIDE"),
            }
        )
        self.entity_data = b""  # Real worlds may contain zero-byte MCA placeholders.
        self.bundle = write_minimal_bundle(
            self.root,
            self.pre_region,
            self.post_region,
            self.entity_data,
            self.region,
        )
        self.world = self.root / "world"
        region_path = self.world / Path(ota.region_relative("region", *self.region))
        entity_path = self.world / Path(ota.region_relative("entities", *self.region))
        ota.atomic_write_bytes(region_path, self.pre_region)
        ota.atomic_write_bytes(entity_path, self.entity_data)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_write_gate_refuses_without_explicit_flags(self) -> None:
        backup = self.root / "backup-gated"
        with self.assertRaisesRegex(ota.OtaError, "allow-world-write"):
            ota.apply_bundle(
                self.bundle,
                self.world,
                backup,
                allow_world_write=False,
                stopped_ack=ota.STOPPED_ACK,
            )
        self.assertFalse(backup.exists())

    def test_apply_and_rollback_restore_exact_preimage_and_entities(self) -> None:
        backup = self.root / "backup"
        receipt = ota.apply_bundle(
            self.bundle,
            self.world,
            backup,
            allow_world_write=True,
            stopped_ack=ota.STOPPED_ACK,
        )
        self.assertEqual(receipt["status"], "APPLIED_VERIFIED")
        region_path = self.world / Path(ota.region_relative("region", *self.region))
        entity_path = self.world / Path(ota.region_relative("entities", *self.region))
        self.assertEqual(region_path.read_bytes(), self.post_region)
        self.assertEqual(entity_path.read_bytes(), self.entity_data)
        rollback = ota.rollback_apply(
            backup / "apply-receipt.json",
            allow_world_write=True,
            stopped_ack=ota.STOPPED_ACK,
        )
        self.assertEqual(rollback["status"], "ROLLED_BACK_VERIFIED")
        self.assertEqual(region_path.read_bytes(), self.pre_region)
        self.assertEqual(entity_path.read_bytes(), self.entity_data)

    def test_rollback_refuses_tampered_postimage_without_partial_restore(self) -> None:
        backup = self.root / "backup-tamper"
        ota.apply_bundle(
            self.bundle,
            self.world,
            backup,
            allow_world_write=True,
            stopped_ack=ota.STOPPED_ACK,
        )
        region_path = self.world / Path(ota.region_relative("region", *self.region))
        entity_path = self.world / Path(ota.region_relative("entities", *self.region))
        tampered = region_path.read_bytes() + b"TAMPER"
        region_path.write_bytes(tampered)
        with self.assertRaisesRegex(ota.OtaError, "postimage was tampered"):
            ota.rollback_apply(
                backup / "apply-receipt.json",
                allow_world_write=True,
                stopped_ack=ota.STOPPED_ACK,
            )
        self.assertEqual(region_path.read_bytes(), tampered)
        self.assertEqual(entity_path.read_bytes(), self.entity_data)

    def test_apply_refuses_preimage_cas_drift_before_backup_or_write(self) -> None:
        region_path = self.world / Path(ota.region_relative("region", *self.region))
        drifted = region_path.read_bytes() + b"DRIFT"
        region_path.write_bytes(drifted)
        backup = self.root / "backup-pre-cas"
        with self.assertRaisesRegex(ota.OtaError, "preimage CAS mismatch"):
            ota.apply_bundle(
                self.bundle,
                self.world,
                backup,
                allow_world_write=True,
                stopped_ack=ota.STOPPED_ACK,
            )
        self.assertEqual(region_path.read_bytes(), drifted)
        self.assertFalse(backup.exists())

    def test_bundle_rejects_entities_payload(self) -> None:
        manifest_path = self.bundle / "bundle.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        forbidden = dict(manifest["changes"][0])
        forbidden["relative_path"] = ota.region_relative("entities", *self.region)
        manifest["changes"] = [forbidden]
        ota.atomic_write_json(manifest_path, manifest)
        with self.assertRaisesRegex(ota.OtaError, "entities MCA is forbidden"):
            ota.read_bundle(self.bundle)


class PlanBundleTests(unittest.TestCase):
    def test_detached_plan_and_bundle_never_emit_entities(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            current_root = root / "current-world"
            donor_root = root / "donor-world"
            current_region = mca({0: (1, b"C_SELECTED"), 1: (2, b"C_OUTSIDE")})
            donor_region = mca({0: (3, b"V_SELECTED"), 1: (4, b"V_OUTSIDE")})
            ota.atomic_write_bytes(current_root / "region" / "r.0.0.mca", current_region)
            ota.atomic_write_bytes(current_root / "entities" / "r.0.0.mca", b"")
            ota.atomic_write_bytes(donor_root / "region" / "r.0.0.mca", donor_region)
            grouped = {(0, 0): frozenset({0})}
            with (
                mock.patch.object(ota, "selection_by_region", return_value=grouped),
                mock.patch.object(ota, "EXPECTED_CHUNKS", 1),
                mock.patch.object(ota, "EXPECTED_REGIONS", 1),
            ):
                with ota.DirectoryWorldSource(current_root) as current, ota.DirectoryWorldSource(
                    donor_root
                ) as donor:
                    plan = ota.create_plan(current, donor, "donor-selected")
                plan_path = root / "plan.json"
                ota.atomic_write_json(plan_path, plan)
                bundle_root = root / "detached-bundle"
                manifest = ota.build_bundle(plan_path, bundle_root)
                verified, _embedded_plan = ota.read_bundle(bundle_root)
            self.assertEqual(manifest["status"], "READY_FOR_STOPPED_SERVER_APPLY")
            self.assertEqual(len(verified["changes"]), 1)
            self.assertEqual(verified["changes"][0]["kind"], "region")
            self.assertFalse(any((bundle_root / "payload" / "entities").glob("*")))
            output = ota.RegionImage.parse(
                (bundle_root / "payload" / "region" / "r.0.0.mca").read_bytes(), "bundle"
            )
            self.assertEqual(output.records[0].raw, ota.RegionImage.parse(donor_region, "V").records[0].raw)
            self.assertEqual(output.records[1].raw, ota.RegionImage.parse(current_region, "C").records[1].raw)


if __name__ == "__main__":
    unittest.main()
