from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_candidate9_happyghast_bundles.py")
SPEC = importlib.util.spec_from_file_location("candidate9_bundle_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class Candidate9BundleBuilderTest(unittest.TestCase):
    def d_temp(self):
        root = Path(os.environ.get("MIGRATION_TEST_TMP", r"<AUDIT_ROOT>\tmp"))
        root.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    @staticmethod
    def make_fabric_jar(path: Path, mod_id: str, payload: bytes = b"payload") -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "fabric.mod.json",
                json.dumps({"schemaVersion": 1, "id": mod_id, "version": "1"}),
            )
            archive.writestr("payload.bin", payload)
        return builder.sha256(path)

    def make_pair(self, root: Path):
        server_dir = root / "candidate6-server"
        client_dir = root / "candidate6-client"
        server_dir.mkdir(parents=True)
        client_dir.mkdir(parents=True)
        shared = []
        for index in range(48):
            name = f"shared-{index:02d}.jar"
            source = root / "source" / name
            digest = self.make_fabric_jar(source, f"shared_{index:02d}", bytes([index]))
            for destination_dir in (server_dir, client_dir):
                shutil.copy2(source, destination_dir / name)
            shared.append((name, digest))
        happy_source = root / "source" / "happy-old.jar"
        old_happy_hash = self.make_fabric_jar(happy_source, builder.HAPPY_MOD_ID, b"old")
        shutil.copy2(happy_source, server_dir / builder.CANDIDATE6_LOCK.old_happy_file)
        shutil.copy2(happy_source, client_dir / builder.CANDIDATE6_LOCK.old_happy_file)
        server_sentinel = root / "source" / builder.CANDIDATE6_LOCK.server_only_file
        server_sentinel_hash = self.make_fabric_jar(
            server_sentinel, builder.CANDIDATE6_LOCK.server_only_mod_id, b"server"
        )
        shutil.copy2(server_sentinel, server_dir / server_sentinel.name)
        client_sentinel = root / "source" / builder.CANDIDATE6_LOCK.client_only_file
        client_sentinel_hash = self.make_fabric_jar(
            client_sentinel, builder.CANDIDATE6_LOCK.client_only_mod_id, b"client"
        )
        shutil.copy2(client_sentinel, client_dir / client_sentinel.name)

        def rows(directory: Path):
            result = []
            for path in sorted(directory.glob("*.jar"), key=lambda item: item.name.casefold()):
                result.append(
                    {
                        "file": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": builder.sha256(path),
                        "mod_ids": sorted(builder.jar_mod_ids(path)),
                        "role": "candidate",
                        "component": path.stem,
                    }
                )
            return result

        def write_manifest(side: str, directory: Path, name: str):
            manifest_rows = rows(directory)
            value = {
                "schema": 1,
                "side": side,
                "status": "PASS",
                "bundle_dir": str(directory.resolve()),
                "file_count": len(manifest_rows),
                "bytes": sum(row["bytes"] for row in manifest_rows),
                "bundle_sha256": builder.bundle_digest(manifest_rows),
                "files": manifest_rows,
            }
            path = root / name
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            return path, builder.sha256(path), value

        server_manifest, server_manifest_hash, server_value = write_manifest(
            "server", server_dir, "server-manifest.json"
        )
        client_manifest, client_manifest_hash, client_value = write_manifest(
            "client", client_dir, "client-manifest.json"
        )
        lock = builder.Candidate6Lock(
            server_manifest_sha256=server_manifest_hash,
            client_manifest_sha256=client_manifest_hash,
            server_bundle_sha256=server_value["bundle_sha256"],
            client_bundle_sha256=client_value["bundle_sha256"],
            old_happy_sha256=old_happy_hash,
            old_happy_file=builder.CANDIDATE6_LOCK.old_happy_file,
            server_only_file=builder.CANDIDATE6_LOCK.server_only_file,
            server_only_sha256=server_sentinel_hash,
            server_only_mod_id=builder.CANDIDATE6_LOCK.server_only_mod_id,
            client_only_file=builder.CANDIDATE6_LOCK.client_only_file,
            client_only_sha256=client_sentinel_hash,
            client_only_mod_id=builder.CANDIDATE6_LOCK.client_only_mod_id,
        )
        return server_manifest, client_manifest, lock, server_dir, client_dir

    def make_replacement(self, root: Path, payload: bytes = b"new") -> Path:
        return_path = root / "happyghast-equivalence-1.0.0-equivalence.2+mc1.21.1.jar"
        self.make_fabric_jar(return_path, builder.HAPPY_MOD_ID, payload)
        return return_path

    def test_success_is_new_root_with_50_jars_and_side_preservation(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            server_manifest, client_manifest, lock, server_dir, client_dir = self.make_pair(root)
            replacement = self.make_replacement(root)
            before = {
                path: builder.sha256(path)
                for path in (*server_dir.glob("*.jar"), *client_dir.glob("*.jar"))
            }
            output = root / "candidate9-bundles"
            result = builder.build_bundles(
                server_manifest,
                client_manifest,
                replacement,
                builder.sha256(replacement),
                output,
                lock=lock,
            )
            self.assertEqual(result["status"], "PASS")
            self.assertTrue((output / "READY.json").is_file())
            self.assertEqual(len(list((output / "server-mods").glob("*.jar"))), 50)
            self.assertEqual(len(list((output / "client-mods").glob("*.jar"))), 50)
            self.assertTrue(
                (output / "server-mods" / lock.server_only_file).is_file()
            )
            self.assertTrue(
                (output / "client-mods" / lock.client_only_file).is_file()
            )
            self.assertFalse(
                (output / "client-mods" / lock.server_only_file).exists()
            )
            self.assertFalse(
                (output / "server-mods" / lock.client_only_file).exists()
            )
            for path, digest in before.items():
                self.assertEqual(builder.sha256(path), digest)
            for side in ("server-mods", "client-mods"):
                names = {path.name for path in (output / side).glob("*.jar")}
                self.assertNotIn(lock.old_happy_file, names)
                self.assertIn(replacement.name, names)
            release = json.loads((output / "READY.json").read_text(encoding="utf-8"))
            self.assertEqual(release["server"]["file_count"], 50)
            self.assertEqual(release["client"]["file_count"], 50)
            self.assertEqual(
                release["replacement"]["replaces_sha256"], lock.old_happy_sha256
            )

    def test_wrong_hash_and_non_happy_replacement_fail_without_output(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            server_manifest, client_manifest, lock, *_ = self.make_pair(root)
            replacement = self.make_replacement(root)
            output = root / "must-not-exist"
            with self.assertRaisesRegex(ValueError, "replacement hash mismatch"):
                builder.build_bundles(
                    server_manifest,
                    client_manifest,
                    replacement,
                    "0" * 64,
                    output,
                    lock=lock,
                )
            self.assertFalse(output.exists())

            bad = root / "not-happy.jar"
            self.make_fabric_jar(bad, "grieflogger")
            with self.assertRaisesRegex(ValueError, "must expose only mod ID"):
                builder.build_bundles(
                    server_manifest,
                    client_manifest,
                    bad,
                    builder.sha256(bad),
                    output,
                    lock=lock,
                )
            self.assertFalse(output.exists())

    def test_source_extra_file_and_existing_output_are_fail_closed(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            server_manifest, client_manifest, lock, server_dir, _ = self.make_pair(root)
            replacement = self.make_replacement(root)
            (server_dir / "unexpected.jar").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "flat exact 50-JAR"):
                builder.build_bundles(
                    server_manifest,
                    client_manifest,
                    replacement,
                    builder.sha256(replacement),
                    root / "no-output",
                    lock=lock,
                )

            # Restore the fixture and prove an existing destination is never overwritten.
            (server_dir / "unexpected.jar").unlink()
            output = root / "existing"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                builder.build_bundles(
                    server_manifest,
                    client_manifest,
                    replacement,
                    builder.sha256(replacement),
                    output,
                    lock=lock,
                )

    def test_replacement_identical_to_old_is_rejected(self):
        with self.d_temp() as temporary:
            root = Path(temporary)
            server_manifest, client_manifest, lock, server_dir, _ = self.make_pair(root)
            old = server_dir / lock.old_happy_file
            with self.assertRaisesRegex(ValueError, "byte-identical"):
                builder.build_bundles(
                    server_manifest,
                    client_manifest,
                    old,
                    builder.sha256(old),
                    root / "no-output",
                    lock=lock,
                )


if __name__ == "__main__":
    unittest.main()
