#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import verify_attempt10_content_repairs_installed as validator  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_jar(path: Path, metadata: str = "modId=fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("META-INF/neoforge.mods.toml", metadata)
        archive.writestr("fixture.txt", "fixture")


class InstalledStateValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.server = base / "server"
        self.client = base / "client"
        self.server.mkdir()
        self.client.mkdir()

        yuushya_name = "yuushya-patched.jar"
        tlm_name = "touhoulittlemaid.jar"
        for root in (self.server, self.client):
            write_jar(root / "mods" / yuushya_name)
            write_jar(root / "mods" / tlm_name)

        maid_relative = "kubejs/server_scripts/maid.js"
        maid_path = self.server / maid_relative
        maid_path.parent.mkdir(parents=True)
        maid_path.write_text(
            'ServerEvents.recipes((event) => {\n  event.remove({\n'
            '    id: "touhou_little_maid:altar_recipe/spawn_box",\n  });\n});\n',
            encoding="utf-8",
        )

        self.overlay_payloads = {
            (
                "kubejs/assets/touhou_little_maid/patchouli_books/"
                "memorizable_gensokyo/en_us/entries/maid/spawn_maid.json"
            ): {"name": "spawn", "pages": [{"type": "text", "text": "safe"}]},
            (
                "kubejs/assets/touhou_little_maid/patchouli_books/"
                "memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json"
            ): {
                "name": "altar",
                "pages": [
                    {
                        "type": "altar_recipe",
                        "recipe_id": "touhou_little_maid:altar_recipe/reborn_maid",
                    }
                ],
            },
        }
        for relative, payload in self.overlay_payloads.items():
            target = self.client / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        yuushya_path = self.server / "mods" / yuushya_name
        tlm_path = self.server / "mods" / tlm_name
        self.spec = {
            "yuushya": {
                "name": yuushya_name,
                "original_name": "yuushya-original.jar",
                "bytes": yuushya_path.stat().st_size,
                "sha256": digest(yuushya_path),
            },
            "tlm": {
                "name": tlm_name,
                "bytes": tlm_path.stat().st_size,
                "sha256": digest(tlm_path),
            },
            "maid_js": {
                "relative": maid_relative,
                "bytes": maid_path.stat().st_size,
                "sha256": digest(maid_path),
            },
            "overlays": {
                relative: {
                    "bytes": (self.client / relative).stat().st_size,
                    "sha256": digest(self.client / relative),
                }
                for relative in self.overlay_payloads
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self) -> dict:
        return validator.validate_installed(self.server, self.client, self.spec)

    def failed(self, report: dict) -> set[str]:
        return {check["name"] for check in report["checks"] if not check["passed"]}

    def test_valid_installed_state_passes(self) -> None:
        report = self.validate()
        self.assertEqual(self.failed(report), set())

    def test_yuushya_mutation_fails_closed(self) -> None:
        target = self.client / "mods" / self.spec["yuushya"]["name"]
        with target.open("ab") as stream:
            stream.write(b"mutation")
        self.assertIn("client:yuushya_patched:exact_artifact", self.failed(self.validate()))

    def test_duplicate_original_yuushya_fails_selection(self) -> None:
        write_jar(self.server / "mods" / "yuushya-original.jar")
        self.assertIn("server:yuushya_selection_exact", self.failed(self.validate()))

    def test_tlm_mutation_fails_closed(self) -> None:
        target = self.server / "mods" / self.spec["tlm"]["name"]
        with target.open("ab") as stream:
            stream.write(b"mutation")
        self.assertIn("server:tlm_unchanged:exact_artifact", self.failed(self.validate()))

    def test_maid_js_mutation_fails_closed(self) -> None:
        target = self.server / self.spec["maid_js"]["relative"]
        target.write_text("recipe restored", encoding="utf-8")
        failed = self.failed(self.validate())
        self.assertIn("server:maid_js_unchanged:exact_artifact", failed)
        self.assertIn("server:maid_js_remove_rule", failed)

    def test_extra_patchouli_entry_fails_exact_two_scope(self) -> None:
        root = self.client / (
            "kubejs/assets/touhou_little_maid/patchouli_books/"
            "memorizable_gensokyo/en_us/entries"
        )
        (root / "extra.json").write_text("{}\n", encoding="utf-8")
        self.assertIn(
            "client:tlm_patchouli_overlay_scope_exactly_two_jsons",
            self.failed(self.validate()),
        )

    def test_renamed_mcmodsync_jar_is_detected_by_metadata(self) -> None:
        write_jar(
            self.client / "mods" / "innocent-name.jar",
            'modId="mcmodsync"',
        )
        report = self.validate()
        self.assertIn("client:mcmodsync_absent", self.failed(report))
        self.assertEqual(len(report["mcmodsync"]["client"]["metadata_matches"]), 1)

    def test_application_report_hash_and_projection_are_bound(self) -> None:
        report_path = Path(self.temporary.name) / "apply.json"
        payload = {
            "status": "PASS_APPLIED",
            "policy": {
                "spawn_box_recipe_removed": True,
                "maid_js_unchanged": True,
                "tlm_patch_side": "CLIENT",
                "yuushya_patch_side": "BOTH",
                "mcmodsync_globally_disabled": True,
            },
            "after": {"server": str(self.server), "client": str(self.client)},
            "application": {
                "changed": [
                    {
                        "side": "server",
                        "kind": "jar",
                        "target": str(self.server / "mods" / validator.repair_spec.YUUSHYA_PATCHED_NAME),
                    },
                    {
                        "side": "client",
                        "kind": "jar",
                        "target": str(self.client / "mods" / validator.repair_spec.YUUSHYA_PATCHED_NAME),
                    },
                    {
                        "side": "client",
                        "kind": "overlay",
                        "target": str(self.client / "spawn_maid.json"),
                    },
                    {
                        "side": "client",
                        "kind": "overlay",
                        "target": str(self.client / "multiblocks_altar.json"),
                    },
                ]
            },
        }
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        evidence, checks = validator.inspect_application_report(
            report_path,
            digest(report_path),
            self.server,
            self.client,
        )
        self.assertTrue(all(check["passed"] for check in checks), checks)
        self.assertEqual(evidence["status"], "PASS_APPLIED")

        _, mutated_checks = validator.inspect_application_report(
            report_path,
            "0" * 64,
            self.server,
            self.client,
        )
        failed = {check["name"] for check in mutated_checks if not check["passed"]}
        self.assertIn("application_report:locked_sha256", failed)

    def test_prior_static_report_is_explicitly_non_authoritative(self) -> None:
        report_path = Path(self.temporary.name) / "prior.json"
        report_path.write_text(
            json.dumps(
                {
                    "verdict": "FAIL",
                    "checks": [
                        {"name": "content", "passed": True},
                        {"name": "attempt9_client_not_modified", "passed": False},
                        {"name": "attempt9_client_log_exists", "passed": False},
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = validator.classify_prior_static_report(report_path)
        self.assertFalse(result["authoritative_for_installed_state"])
        self.assertEqual(result["classification"], "NON_AUTHORITATIVE_FOR_INSTALLED_STATE")
        self.assertTrue(result["expected_scope_mismatch_confirmed"])


if __name__ == "__main__":
    unittest.main()
