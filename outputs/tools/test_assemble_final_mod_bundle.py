from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("assemble_final_mod_bundle.py")
SPEC = importlib.util.spec_from_file_location("assemble_final_mod_bundle", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class AssembleBundleTest(unittest.TestCase):
    def d_temp(self):
        root = Path(os.environ.get("MIGRATION_TEST_TMP", r"D:\Trans\migration-audit-work\tmp"))
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def make_jar(self, path: Path, mod_id: str, payload: bytes = b"x") -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "fabric.mod.json",
                json.dumps({"schemaVersion": 1, "id": mod_id, "version": "1"}),
            )
            archive.writestr("payload.bin", payload)
        return bundle.sha256(path)

    def inventory_row(self, component: str, path: Path, digest: str, mod_id: str, sides: str):
        return {
            "component": component,
            "install_sides": sides,
            "role": "candidate",
            "canonical": {
                "path": str(path),
                "sha256": digest,
                "mods": [{"id": mod_id}],
            },
        }

    def test_server_replaces_stale_and_excludes_client_only(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            baseline = root / "baseline"
            old = baseline / "old.jar"
            extra = baseline / "extra.jar"
            old_hash = self.make_jar(old, "same_mod", b"old")
            self.make_jar(extra, "extra_mod")
            canonical = root / "canonical.jar"
            canonical_hash = self.make_jar(canonical, "same_mod", b"new")
            client = root / "client.jar"
            client_hash = self.make_jar(client, "client_mod")
            inventory = {
                "release_candidates": [
                    self.inventory_row("Same", canonical, canonical_hash, "same_mod", "server+client"),
                    self.inventory_row("Client", client, client_hash, "client_mod", "client-only"),
                ],
                "support_and_replacements": [],
                "stale_or_rejected": [{"metadata": {"sha256": old_hash}}],
            }
            inventory_path = root / "inventory.json"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            result = bundle.assemble(inventory_path, baseline, root / "output", "server")
            self.assertEqual(set(result["mod_ids"]), {"same_mod", "extra_mod"})
            self.assertNotIn("client_mod", result["mod_ids"])
            self.assertEqual(result["file_count"], 2)

    def test_duplicate_selected_ids_fail(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            baseline = root / "baseline"
            baseline.mkdir()
            first = root / "first.jar"
            second = root / "second.jar"
            first_hash = self.make_jar(first, "duplicate")
            second_hash = self.make_jar(second, "duplicate", b"other")
            inventory = {
                "release_candidates": [
                    self.inventory_row("First", first, first_hash, "duplicate", "server+client"),
                    self.inventory_row("Second", second, second_hash, "duplicate", "server+client"),
                ],
                "support_and_replacements": [],
                "stale_or_rejected": [],
            }
            path = root / "inventory.json"
            path.write_text(json.dumps(inventory), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate selected"):
                bundle.assemble(path, baseline, root / "output", "server")


if __name__ == "__main__":
    unittest.main()
