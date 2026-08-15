from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile


MODULE_PATH = Path(__file__).with_name("build_candidate14_bundle.py")
SPEC = importlib.util.spec_from_file_location("candidate14_bundle_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class Candidate14BuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "candidate13"
        self._make_baseline()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _jar(path: Path, mod_id: str, marker: str, side: str | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schemaVersion": 1,
            "id": mod_id,
            "version": "test",
        }
        if side:
            metadata["environment"] = side
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("fabric.mod.json", json.dumps(metadata))
            archive.writestr("marker.txt", marker)

    def _make_baseline(self) -> None:
        manifests = self.baseline / "manifests"
        manifests.mkdir(parents=True)
        side_only = {
            "server": ("grieflogger-1.2.10-1.21.1-neoforge.jar", "grieflogger"),
            "client": ("chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar", "colorizer"),
        }
        rows_by_side: dict[str, list[dict[str, object]]] = {}
        for side in ("server", "client"):
            mods = self.baseline / f"{side}-mods"
            mods.mkdir()
            rows: list[dict[str, object]] = []
            for index in range(51):
                filename = f"shared-{index:02d}.jar"
                source = self.baseline / "server-mods" / filename
                if side == "server":
                    self._jar(source, f"shared_{index:02d}", filename)
                destination = mods / filename
                if destination != source:
                    shutil.copy2(source, destination)
                rows.append({"file": filename, "bytes": destination.stat().st_size, "sha256": builder.sha256(destination), "mod_ids": [f"shared_{index:02d}"], "role": "baseline"})
            filename, mod_id = side_only[side]
            destination = mods / filename
            self._jar(destination, mod_id, side)
            rows.append({"file": filename, "bytes": destination.stat().st_size, "sha256": builder.sha256(destination), "mod_ids": [mod_id], "role": "side_only"})
            rows.sort(key=lambda row: str(row["file"]).casefold())
            rows_by_side[side] = rows
            manifest = {"schema": 1, "candidate": 13, "status": "PASS", "side": side, "file_count": 52, "bytes": sum(int(r["bytes"]) for r in rows), "bundle_sha256": builder.bundle_digest(rows), "files": rows}
            (manifests / f"{side}.json").write_bytes(builder.stable_json(manifest))
        server_manifest = manifests / "server.json"
        client_manifest = manifests / "client.json"
        server_bundle = builder.bundle_digest(rows_by_side["server"])
        client_bundle = builder.bundle_digest(rows_by_side["client"])
        release = {"schema": 1, "candidate": 13, "status": "PASS", "source_unchanged": True, "output_root": str(self.baseline), "server": {"file_count": 52, "bundle_sha256": server_bundle, "manifest_sha256": builder.sha256(server_manifest)}, "client": {"file_count": 52, "bundle_sha256": client_bundle, "manifest_sha256": builder.sha256(client_manifest)}, "bundle_pair_sha256": builder.pair_digest(server_bundle, client_bundle), "side_specific_policy": {"server_only_file": side_only["server"][0], "client_only_file": side_only["client"][0]}}
        payload = builder.stable_json(release)
        (self.baseline / "READY.json").write_bytes(payload)
        (self.baseline / "release-lock.json").write_bytes(payload)
        self.lock = builder.BaselineLock(ready_sha256=builder.sha256(self.baseline / "READY.json"), server_manifest_sha256=builder.sha256(server_manifest), client_manifest_sha256=builder.sha256(client_manifest), server_bundle_sha256=server_bundle, client_bundle_sha256=client_bundle, bundle_pair_sha256=builder.pair_digest(server_bundle, client_bundle))
        artifacts = self.root / "artifacts"
        self.scarecrow = artifacts / builder.SCARECROW_FILE
        self.protection = artifacts / builder.PROTECTION_FILE
        self.mcsync = artifacts / builder.MCSYNC_FILE
        self._jar(self.scarecrow, builder.SCARECROW_MOD_ID, "scarecrow", "*")
        self._jar(self.protection, builder.PROTECTION_MOD_ID, "protection", "*")
        self._jar(self.mcsync, builder.MCSYNC_MOD_ID, "mcsync", "client")
        self.scarecrow_sha = builder.sha256(self.scarecrow)
        self.protection_sha = builder.sha256(self.protection)
        self.mcsync_sha = builder.sha256(self.mcsync)

    def _build(self, name: str = "candidate14") -> dict:
        return builder.build_candidate14(
            self.root / name,
            baseline_root=self.baseline,
            report_path=self.root / f"{name}.json",
            markdown_path=self.root / f"{name}.md",
            lock=self.lock,
            scarecrow_source=self.scarecrow,
            scarecrow_sha256=self.scarecrow_sha,
            protection_source=self.protection,
            protection_sha256=self.protection_sha,
            mcsync_source=self.mcsync,
            mcsync_sha256=self.mcsync_sha,
            runtime_sanitized_root=self.root / "missing-runtime",
        )

    def test_adds_two_both_and_audits_but_does_not_install_mcmodsync(self) -> None:
        before = builder._snapshot(self.baseline)
        result = self._build()
        output = Path(result["output_root"])
        self.assertEqual(before, builder._snapshot(self.baseline))
        self.assertEqual((output / "READY.json").read_bytes(), (output / "release-lock.json").read_bytes())
        server = builder.read_json(output / "manifests/server.json")
        client = builder.read_json(output / "manifests/client.json")
        self.assertEqual(54, server["file_count"])
        self.assertEqual(54, client["file_count"])
        self.assertNotIn(builder.MCSYNC_FILE, {r["file"] for r in server["files"]})
        self.assertNotIn(builder.MCSYNC_FILE, {r["file"] for r in client["files"]})
        ready = builder.read_json(output / "READY.json")
        self.assertEqual("NOT_INSTALLED", ready["ota_preparation"]["runtime_install_status"])
        self.assertEqual(self.mcsync_sha, ready["ota_preparation"]["audited_artifact"]["sha256"])
        extension = ready["extension_policy"]
        self.assertEqual("acceptance_snapshot_not_permanent_allowlist", extension["release_lock_semantics"])
        self.assertTrue(extension["additive_server_mods_allowed"])
        self.assertTrue(extension["additive_client_mods_allowed"])
        self.assertTrue(extension["ota_additions_allowed"])
        self.assertFalse(extension["runtime_global_mod_denylist"])
        self.assertFalse(extension["permanent_exact_mod_count_enforcement"])
        for side, manifest in (("server", server), ("client", client)):
            old = builder.read_json(self.baseline / f"manifests/{side}.json")["files"]
            now = {r["file"].casefold(): r for r in manifest["files"]}
            for row in old:
                self.assertEqual(row, now[row["file"].casefold()])

    def test_existing_output_is_never_reused(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaises(FileExistsError):
            self._build("existing")

    def test_existing_report_fails_before_publication(self) -> None:
        report = self.root / "report-exists.json"
        report.write_text("owned", encoding="utf-8")
        output = self.root / "report-output"
        with self.assertRaisesRegex(FileExistsError, "build report"):
            builder.build_candidate14(
                output,
                baseline_root=self.baseline,
                report_path=report,
                markdown_path=self.root / "report-output.md",
                lock=self.lock,
                scarecrow_source=self.scarecrow,
                scarecrow_sha256=self.scarecrow_sha,
                protection_source=self.protection,
                protection_sha256=self.protection_sha,
                mcsync_source=self.mcsync,
                mcsync_sha256=self.mcsync_sha,
                runtime_sanitized_root=self.root / "missing-runtime",
            )
        self.assertFalse(output.exists())

    def test_wrong_new_hash_fails_before_publication(self) -> None:
        self.protection_sha = "0" * 64
        with self.assertRaisesRegex(ValueError, "new artifact hash mismatch"):
            self._build("bad-hash")
        self.assertFalse((self.root / "bad-hash").exists())

    def test_candidate13_tamper_fails_before_publication(self) -> None:
        tampered = self.baseline / "server-mods/shared-00.jar"
        tampered.write_bytes(tampered.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "byte/hash mismatch"):
            self._build("tampered")
        self.assertFalse((self.root / "tampered").exists())


if __name__ == "__main__":
    unittest.main()
