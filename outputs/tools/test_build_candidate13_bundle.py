from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_candidate13_bundle.py")
SPEC = importlib.util.spec_from_file_location("candidate13_bundle_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class Candidate13BundleBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "candidate12"
        self.old_overlay = self.baseline / "server-mods" / "old-overlay.jar"
        self.new_overlay = self.root / builder.NEW_OVERLAY_FILE
        self.lock, self.old_overlay_sha = self._make_candidate12()
        self._make_jar(self.new_overlay, builder.OVERLAY_MOD_ID, b"candidate13")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _make_jar(path: Path, mod_id: str, marker: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(
                "fabric.mod.json",
                json.dumps(
                    {"schemaVersion": 1, "id": mod_id, "version": "test"},
                    separators=(",", ":"),
                ),
            )
            archive.writestr("marker.bin", marker)

    def _make_candidate12(self) -> tuple[builder.BaselineLock, str]:
        server_dir = self.baseline / "server-mods"
        client_dir = self.baseline / "client-mods"
        manifests_dir = self.baseline / "manifests"
        server_dir.mkdir(parents=True)
        client_dir.mkdir()
        manifests_dir.mkdir()
        shared = [("old-overlay.jar", builder.OVERLAY_MOD_ID)] + [
            (f"common-{index:02d}.jar", f"common_{index:02d}") for index in range(50)
        ]
        side_only = {
            "server": ("server-only.jar", "server_only"),
            "client": ("client-only.jar", "client_only"),
        }
        rows: dict[str, list[dict[str, object]]] = {}
        for side in ("server", "client"):
            side_dir = server_dir if side == "server" else client_dir
            values: list[dict[str, object]] = []
            for filename, mod_id in shared:
                canonical = server_dir / filename
                if side == "server":
                    self._make_jar(canonical, mod_id, filename.encode("ascii"))
                destination = side_dir / filename
                if destination != canonical:
                    shutil.copy2(canonical, destination)
                values.append(
                    {
                        "file": filename,
                        "bytes": destination.stat().st_size,
                        "sha256": builder.sha256(destination),
                        "mod_ids": [mod_id],
                        "role": "candidate",
                        "component": mod_id,
                    }
                )
            filename, mod_id = side_only[side]
            destination = side_dir / filename
            self._make_jar(destination, mod_id, side.encode("ascii"))
            values.append(
                {
                    "file": filename,
                    "bytes": destination.stat().st_size,
                    "sha256": builder.sha256(destination),
                    "mod_ids": [mod_id],
                    "role": "side_only",
                    "component": mod_id,
                }
            )
            values.sort(key=lambda row: str(row["file"]).casefold())
            rows[side] = values
            manifest_path = manifests_dir / f"{side}.json"
            manifest = {
                "schema": 1,
                "candidate": 12,
                "status": "PASS",
                "side": side,
                "bundle_dir": str(side_dir),
                "manifest_path": str(manifest_path),
                "file_count": 52,
                "bytes": sum(int(row["bytes"]) for row in values),
                "bundle_sha256": builder.bundle_digest(values),
                "files": values,
            }
            manifest_path.write_bytes(builder.stable_json(manifest))

        server_manifest = manifests_dir / "server.json"
        client_manifest = manifests_dir / "client.json"
        server_bundle = builder.bundle_digest(rows["server"])
        client_bundle = builder.bundle_digest(rows["client"])
        release = {
            "schema": 1,
            "candidate": 12,
            "status": "PASS",
            "source_unchanged": True,
            "output_root": str(self.baseline),
            "server": {
                "file_count": 52,
                "bundle_sha256": server_bundle,
                "manifest_sha256": builder.sha256(server_manifest),
            },
            "client": {
                "file_count": 52,
                "bundle_sha256": client_bundle,
                "manifest_sha256": builder.sha256(client_manifest),
            },
            "bundle_pair_sha256": builder.pair_digest(server_bundle, client_bundle),
            "side_specific_policy": {
                "server_only_file": side_only["server"][0],
                "server_only_mod_id": side_only["server"][1],
                "client_only_file": side_only["client"][0],
                "client_only_mod_id": side_only["client"][1],
            },
            "runtime_sanitization_policy": {"published_bundle_state": "unsanitized"},
        }
        payload = builder.stable_json(release)
        (self.baseline / "READY.json").write_bytes(payload)
        (self.baseline / "release-lock.json").write_bytes(payload)
        return (
            builder.BaselineLock(
                ready_sha256=builder.sha256(self.baseline / "READY.json"),
                server_manifest_sha256=builder.sha256(server_manifest),
                client_manifest_sha256=builder.sha256(client_manifest),
                server_bundle_sha256=server_bundle,
                client_bundle_sha256=client_bundle,
                bundle_pair_sha256=builder.pair_digest(server_bundle, client_bundle),
            ),
            builder.sha256(self.old_overlay),
        )

    def _build(self, name: str = "candidate13") -> dict:
        return builder.build_candidate13(
            self.root / name,
            baseline_root=self.baseline,
            overlay_path=self.new_overlay,
            overlay_sha256=builder.sha256(self.new_overlay),
            resource_report_path=None,
            lock=self.lock,
            old_overlay_file="old-overlay.jar",
            old_overlay_sha256=self.old_overlay_sha,
        )

    def test_replaces_only_overlay_on_both_52_jar_sides(self) -> None:
        before = builder._snapshot(self.baseline)
        result = self._build()
        output = Path(result["output_root"])
        self.assertEqual(before, builder._snapshot(self.baseline))
        self.assertEqual(
            (output / "READY.json").read_bytes(),
            (output / "release-lock.json").read_bytes(),
        )
        for side in ("server", "client"):
            manifest = builder.read_json(output / "manifests" / f"{side}.json")
            self.assertEqual(52, manifest["file_count"])
            self.assertEqual(51, manifest["candidate12_invariance"]["unchanged_rows"])
            self.assertEqual(1, manifest["candidate12_invariance"]["replaced_rows"])
            self.assertNotIn("old-overlay.jar", {row["file"] for row in manifest["files"]})
            new = next(row for row in manifest["files"] if row["file"] == builder.NEW_OVERLAY_FILE)
            self.assertEqual(builder.sha256(self.new_overlay), new["sha256"])

    def test_wrong_overlay_hash_fails_before_publication(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlay hash mismatch"):
            builder.build_candidate13(
                self.root / "bad",
                baseline_root=self.baseline,
                overlay_path=self.new_overlay,
                overlay_sha256="0" * 64,
                resource_report_path=None,
                lock=self.lock,
                old_overlay_file="old-overlay.jar",
                old_overlay_sha256=self.old_overlay_sha,
            )
        self.assertFalse((self.root / "bad").exists())

    def test_candidate12_tamper_fails_before_publication(self) -> None:
        path = self.baseline / "server-mods" / "common-00.jar"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "hash/size mismatch"):
            self._build("tampered")
        self.assertFalse((self.root / "tampered").exists())

    def test_existing_output_is_never_reused(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaises(FileExistsError):
            self._build("existing")


if __name__ == "__main__":
    unittest.main()
