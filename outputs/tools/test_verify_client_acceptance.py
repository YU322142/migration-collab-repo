from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile


MODULE_PATH = Path(__file__).with_name("verify_client_acceptance.py")
SPEC = importlib.util.spec_from_file_location("verify_client_acceptance", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class VerifyClientAcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.mods = self.root / "client-mods"
        self.evidence_root = self.root / "evidence"
        self.manifest = self.root / "client-manifest.json"
        self.evidence = self.evidence_root / "client-evidence.json"
        self.report = self.root / "reports" / "client-gate.json"
        self.server_digest = "A" * 64
        self.mods.mkdir()
        self.evidence_root.mkdir()
        self._write_bundle()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_jar(self, name: str, mod_id: str) -> dict:
        path = self.mods / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/neoforge.mods.toml",
                "modLoader='javafml'\nloaderVersion='[4,)'\n"
                "[[mods]]\nmodId='" + mod_id + "'\nversion='1'\n",
            )
            archive.writestr("payload.txt", mod_id)
            marker_names = {
                "colorizer": gate.REQUIRED_BUNDLE_MARKERS["colorizer"],
                "mineastr": gate.REQUIRED_BUNDLE_MARKERS["mineastr"],
                "xiyuslogin": gate.REQUIRED_BUNDLE_MARKERS["xiyuslogin"],
            }.get(mod_id, ())
            for marker in marker_names:
                if marker == "META-INF/neoforge.mods.toml":
                    continue
                archive.writestr(marker, b"fixture")
        return {
            "file": name,
            "bytes": path.stat().st_size,
            "sha256": digest(path),
            "mod_ids": [mod_id],
        }

    def _write_bundle(self) -> None:
        rows = [
            self._write_jar("colorizer.jar", "colorizer"),
            self._write_jar("mineastr.jar", "mineastr"),
            self._write_jar("xiyuslogin.jar", "xiyuslogin"),
        ]
        value = {
            "schema": 1,
            "side": "client",
            "file_count": len(rows),
            "bundle_sha256": gate.bundle_digest(rows),
            "files": rows,
        }
        self.manifest.write_text(json.dumps(value), encoding="utf-8")
        self.client_digest = value["bundle_sha256"]

    def _write_evidence(self, *, status: str = "PASS", bad_artifact: bool = False) -> None:
        suites = {}
        for suite, scenarios in gate.REQUIRED_SCENARIOS.items():
            artifacts = []
            for index, kind in enumerate(sorted(gate.REQUIRED_ARTIFACT_KINDS[suite])):
                artifact = self.evidence_root / f"{suite}-{kind}.txt"
                artifact.write_text(f"redacted {suite} {kind} evidence\n", encoding="utf-8")
                artifacts.append(
                    {
                        "path": artifact.name,
                        "sha256": (
                            "0" * 64
                            if bad_artifact and suite == "java_client" and index == 0
                            else digest(artifact)
                        ),
                        "kind": kind,
                        "contains_secrets": False,
                    }
                )
            scenario_rows = {}
            for scenario in scenarios:
                if suite == "xiyuslogin":
                    scenario_artifact = self.evidence_root / f"{suite}-{scenario}.txt"
                    scenario_artifact.write_text(
                        f"redacted {suite} {scenario} evidence\n", encoding="utf-8"
                    )
                    scenario_rows[scenario] = {
                        "status": "PASS",
                        "artifacts": [
                            {
                                "path": scenario_artifact.name,
                                "sha256": digest(scenario_artifact),
                                "kind": "redacted-login-transcript",
                                "contains_secrets": False,
                            }
                        ],
                    }
                else:
                    scenario_rows[scenario] = "PASS"
            suites[suite] = {
                "status": "PASS",
                "client_bundle_sha256": self.client_digest,
                "server_bundle_sha256": self.server_digest,
                "tested_with_secrets": False,
                "scenarios": scenario_rows,
                "artifacts": artifacts,
            }
        value = {
            "schema": 1,
            "status": status,
            "tested_at_utc": "2026-08-09T12:00:00Z",
            "operator": "fixture",
            "contains_secrets": False,
            "environment": {
                "minecraft_version": "1.21.1",
                "loader": "NeoForge",
                "java_major": 21,
                "address_redacted": True,
            },
            "client_bundle_sha256": self.client_digest,
            "server_bundle_sha256": self.server_digest,
            "suites": suites,
        }
        self.evidence.write_text(json.dumps(value), encoding="utf-8")

    def _argv(self) -> list[str]:
        return [
            "--client-mods",
            str(self.mods),
            "--bundle-manifest",
            str(self.manifest),
            "--evidence",
            str(self.evidence),
            "--evidence-root",
            str(self.evidence_root),
            "--expected-server-bundle-sha256",
            self.server_digest,
            "--report",
            str(self.report),
        ]

    def _result(self) -> dict:
        return json.loads(self.report.read_text(encoding="utf-8"))

    def test_all_pass_closes_real_client_gate(self) -> None:
        self._write_evidence()
        self.assertEqual(gate.main(self._argv()), 0)
        result = self._result()
        self.assertEqual(result["status"], "PRODUCTION_CLIENT_GO")
        self.assertEqual(result["bundle"]["file_count"], 3)
        self.assertEqual(set(result["evidence"]["suites"]), set(gate.REQUIRED_SCENARIOS))
        self.assertEqual(
            set(result["evidence"]["suites"]["xiyuslogin"]["scenario_artifacts"]),
            set(gate.REQUIRED_SCENARIOS["xiyuslogin"]),
        )

    def test_auth_scenario_without_own_artifact_is_no_go(self) -> None:
        self._write_evidence()
        value = json.loads(self.evidence.read_text(encoding="utf-8"))
        value["suites"]["xiyuslogin"]["scenarios"][
            "java_existing_bcrypt_correct"
        ]["artifacts"] = []
        self.evidence.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(gate.main(self._argv()), 2)
        self.assertEqual(
            self._result()["error_code"],
            "CLIENT_SCENARIO_ARTIFACTS_MISSING:xiyuslogin:java_existing_bcrypt_correct",
        )

    def test_template_or_incomplete_evidence_is_no_go(self) -> None:
        self._write_evidence(status="NOT_RUN")
        self.assertEqual(gate.main(self._argv()), 2)
        result = self._result()
        self.assertEqual(result["status"], "NO_GO")
        self.assertEqual(result["error_code"], "CLIENT_EVIDENCE_NOT_PASS")

    def test_artifact_hash_mismatch_is_no_go(self) -> None:
        self._write_evidence(bad_artifact=True)
        self.assertEqual(gate.main(self._argv()), 2)
        self.assertEqual(
            self._result()["error_code"], "CLIENT_ARTIFACT_HASH_MISMATCH:java_client"
        )

    def test_extra_jar_fails_bundle_integrity(self) -> None:
        self._write_evidence()
        self._write_jar("extra.jar", "extra")
        self.assertEqual(gate.main(self._argv()), 1)
        self.assertTrue(self._result()["error_code"].startswith("CLIENT_BUNDLE_EXTRA:"))

    def test_required_client_asset_marker_is_fail_closed(self) -> None:
        self._write_evidence()
        path = self.mods / "colorizer.jar"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/neoforge.mods.toml",
                "modLoader='javafml'\nloaderVersion='[4,)'\n"
                "[[mods]]\nmodId='colorizer'\nversion='1'\n",
            )
            archive.writestr("colorizer.mixins.json", "{}")
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        row = next(item for item in manifest["files"] if item["file"] == path.name)
        row["bytes"] = path.stat().st_size
        row["sha256"] = digest(path)
        manifest["bundle_sha256"] = gate.bundle_digest(manifest["files"])
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(gate.main(self._argv()), 1)
        self.assertTrue(
            self._result()["error_code"].startswith("CLIENT_REQUIRED_ASSET_MISSING:colorizer:")
        )

    def test_suite_must_bind_server_bundle(self) -> None:
        self._write_evidence()
        value = json.loads(self.evidence.read_text(encoding="utf-8"))
        value["suites"]["mineastr_astrbot"]["server_bundle_sha256"] = "B" * 64
        self.evidence.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(gate.main(self._argv()), 2)
        self.assertEqual(
            self._result()["error_code"],
            "CLIENT_SUITE_SERVER_BINDING_MISMATCH:mineastr_astrbot",
        )


if __name__ == "__main__":
    unittest.main()
