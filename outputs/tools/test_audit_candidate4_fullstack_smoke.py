from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_candidate4_fullstack_smoke.py")
SPEC = importlib.util.spec_from_file_location("candidate4_smoke_audit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class Candidate4SmokeAuditTest(unittest.TestCase):
    def test_log_lifecycle_allows_only_exact_known_diagnostics(self):
        text = "\n".join(
            (
                "[pool/ERROR] [x/RefmapRemapper/]: Error opening jar file java.nio.file.NoSuchFileException: \\~nonexistent",
                "Loaded 11407 recipes",
                "Loaded 4318 advancements",
                "Done (1.0s)!",
                "Loaded 49 player records from data file",
                "[Rcon: Reloading!]",
                "[Rcon: Saved the game]",
                "[Rcon: Stopping the server]",
                "Stopping server",
                "Saving chunks for level x/minecraft:overworld",
                "Saving chunks for level x/minecraft:the_nether",
                "Saving chunks for level x/minecraft:the_end",
                "All dimensions are saved",
                "XiyusLogin data saved and systems shutdown",
                "Thread RCON Listener stopped",
            )
        )
        result = audit.analyze_log(text)
        self.assertEqual(result["connector_refmap_placeholder_error"], 1)
        self.assertEqual(result["unallowlisted_error_level"], 0)
        self.assertEqual(audit.lifecycle_failures(result, 49, require_reload=True), [])

    def test_unknown_error_and_missing_stop_fail(self):
        result = audit.analyze_log("[server/ERROR] [example/]: broken\nDone (1.0s)!")
        failures = audit.lifecycle_failures(result, 49, require_reload=False)
        self.assertIn("LOG_HARD_DIAGNOSTIC_UNALLOWLISTED_ERROR_LEVEL", failures)
        self.assertIn("LOG_MISSING_SERVER_STOPPING", failures)

    def test_rolling_log_connector_exception_may_follow_error_header(self):
        result = audit.analyze_log(
            "[pool/ERROR] [org.sinytra.connector.transformer.transform.RefmapRemapper/]: Error opening jar file\n"
            "java.nio.file.NoSuchFileException: \\~nonexistent\n"
        )
        self.assertEqual(result["error_level"], 1)
        self.assertEqual(result["connector_refmap_placeholder_error"], 1)
        self.assertEqual(result["unallowlisted_error_level"], 0)

    def test_spark_warning_must_be_inside_shutdown_sequence(self):
        valid = audit.analyze_log(
            "Stopping server\nRejectedExecutionException: Server already shutting down\nAll dimensions are saved"
        )
        invalid = audit.analyze_log(
            "RejectedExecutionException: Server already shutting down\nStopping server\nAll dimensions are saved"
        )
        self.assertTrue(valid["spark_warning_order_valid"])
        self.assertFalse(invalid["spark_warning_order_valid"])

    def test_inventory_loss_is_counted_and_legacy_encoding_is_visible(self):
        source = audit.normalize_item_inventory(
            [
                {},
                {"id": "create:empty_schematic", "count": 1},
                {},
                {},
                {"id": "minecraft:gunpowder", "count": 23},
            ]
        )
        target = audit.normalize_item_inventory({"Size": 5, "Items": []})
        lost = audit.item_loss(source, target)
        self.assertEqual(source["encoding"], "legacy_list")
        self.assertEqual(target["encoding"], "neoforge_item_handler_compound")
        self.assertEqual(sum(item["count"] for item in lost), 24)
        self.assertEqual({item["id"] for item in lost}, {"create:empty_schematic", "minecraft:gunpowder"})

    def test_equivalent_compound_inventory_has_no_loss(self):
        source = audit.normalize_item_inventory(
            [{}, {"id": "create:empty_schematic", "count": 1}]
        )
        target = audit.normalize_item_inventory(
            {
                "Size": 2,
                "Items": [
                    {"Slot": 1, "id": "create:empty_schematic", "count": 1}
                ],
            }
        )
        self.assertEqual(audit.item_loss(source, target), [])

    def test_schematicannon_enum_case_is_semantically_canonicalized(self):
        source = audit.summarize_cannon(
            {
                "x": 1,
                "y": 2,
                "z": 3,
                "State": "stopped",
                "Printer": {
                    "PrintStage": "blocks",
                    "EntityProgress": -1,
                    "DeferredBlocks": [],
                },
                "Inventory": [{}, {"id": "minecraft:gunpowder", "count": 2}],
            }
        )
        target = audit.summarize_cannon(
            {
                "x": 1,
                "y": 2,
                "z": 3,
                "State": "STOPPED",
                "Printer": {
                    "PrintStage": "BLOCKS",
                    "EntityProgress": -1,
                    "DeferredBlocks": [],
                },
                "Inventory": {
                    "Size": 2,
                    "Items": [
                        {"Slot": 1, "id": "minecraft:gunpowder", "count": 2}
                    ],
                },
            }
        )
        self.assertEqual(source["state"], target["state"])
        self.assertEqual(source["printer_sha256"], target["printer_sha256"])
        self.assertEqual(audit.item_loss(source["inventory"], target["inventory"]), [])


if __name__ == "__main__":
    unittest.main()
