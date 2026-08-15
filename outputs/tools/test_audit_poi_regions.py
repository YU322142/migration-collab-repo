import unittest

import audit_poi_regions as poi


class PoiAuditHelpersTest(unittest.TestCase):
    def test_region_name_and_slot_coordinates(self):
        self.assertEqual((-1, 12), poi.parse_region_coords("r.-1.12.mca"))
        self.assertIsNone(poi.parse_region_coords("r.-1.12.mcr"))
        self.assertEqual((-29, 389), poi.chunk_coords(-1, 12, 163))

    def test_valid_record(self):
        record = {"type": "minecraft:fisherman", "pos": [-283, 63, -450], "free_tickets": 1}
        self.assertEqual([], poi.validate_plain_record(record, (-18, -29), 3))

    def test_record_rejects_schema_and_coordinate_drift(self):
        record = {"type": "fisherman", "pos": [-283, 64, -450], "free_tickets": -1, "extra": 1}
        errors = poi.validate_plain_record(record, (-17, -29), 3)
        self.assertEqual(5, len(errors))
        self.assertTrue(any("record keys" in error for error in errors))
        self.assertTrue(any("namespaced" in error for error in errors))
        self.assertTrue(any("chunk" in error for error in errors))
        self.assertTrue(any("section" in error for error in errors))
        self.assertTrue(any("negative" in error for error in errors))

    def test_slot_bounds_are_fail_closed(self):
        with self.assertRaises(ValueError):
            poi.chunk_coords(0, 0, -1)
        with self.assertRaises(ValueError):
            poi.chunk_coords(0, 0, 1024)

    def test_mixed_data_version_allowlist_is_normalized(self):
        self.assertEqual(
            poi._data_version_policy(None, [4671, 3839, 4671, 3955]),
            frozenset({3839, 3955, 4671}),
        )

    def test_data_version_policies_are_mutually_exclusive(self):
        with self.assertRaises(ValueError):
            poi._data_version_policy(3955, [3955])
        with self.assertRaises(ValueError):
            poi._data_version_policy(None, [])

    def test_data_version_allowlist_preserves_strict_mode(self):
        mixed = poi._data_version_policy(None, [3839, 3955, 4556, 4671])
        self.assertTrue(poi._data_version_is_allowed(4671, None, mixed))
        self.assertFalse(poi._data_version_is_allowed(5000, None, mixed))
        self.assertTrue(poi._data_version_is_allowed(3955, 3955, None))
        self.assertFalse(poi._data_version_is_allowed(4671, 3955, None))


if __name__ == "__main__":
    unittest.main()
