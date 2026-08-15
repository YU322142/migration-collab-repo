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


MODULE_PATH = Path(__file__).with_name("build_candidate11_guard_cc_bundles.py")
SPEC = importlib.util.spec_from_file_location("candidate11_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class Candidate11BuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "candidate10"
        self.cc_path = self.root / "cctweaked-startup-guard-test.jar"
        self.guard_path = self.root / "create-chute-unload-guard-test.jar"
        self.lock, self.guard_lock, self.compat_lock = self._make_baseline()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _jar(self, path: Path, mod_id: str, marker: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(
                "fabric.mod.json",
                json.dumps(
                    {"schemaVersion": 1, "id": mod_id, "version": "test"},
                    separators=(",", ":"),
                ),
            )
            archive.writestr("marker.txt", marker.encode("ascii"))

    def _make_baseline(self):
        server_dir = self.baseline / "server-mods"
        client_dir = self.baseline / "client-mods"
        manifests_dir = self.baseline / "manifests"
        server_dir.mkdir(parents=True)
        client_dir.mkdir()
        manifests_dir.mkdir()

        common_names: list[tuple[str, str]] = [
            (f"common-{index:02d}.jar", f"common_{index:02d}")
            for index in range(48)
        ]
        common_names.append(("cc-tweaked-test.jar", builder.CC_BASE_MOD_ID))
        server_only = ("grieflogger-test.jar", "grieflogger")
        client_only = ("chest-colorizer-test.jar", "colorizer")

        rows_by_side: dict[str, list[dict]] = {}
        for side, side_only in (("server", server_only), ("client", client_only)):
            side_dir = server_dir if side == "server" else client_dir
            rows: list[dict] = []
            for filename, mod_id in [*common_names, side_only]:
                path = side_dir / filename
                self._jar(path, mod_id, f"{side}:{filename}")
                rows.append(
                    {
                        "file": filename,
                        "bytes": path.stat().st_size,
                        "sha256": builder.sha256(path),
                        "mod_ids": [mod_id],
                        "role": "baseline",
                    }
                )
            rows.sort(key=lambda row: row["file"].casefold())
            rows_by_side[side] = rows

        # Make the 49 shared baseline bytes truly identical across sides.
        for row in rows_by_side["server"]:
            if row["file"] not in {server_only[0]}:
                source = server_dir / row["file"]
                destination = client_dir / row["file"]
                shutil.copy2(source, destination)
                client_row = next(item for item in rows_by_side["client"] if item["file"] == row["file"])
                client_row["bytes"] = destination.stat().st_size
                client_row["sha256"] = builder.sha256(destination)
                client_row["mod_ids"] = list(row["mod_ids"])
                row["sha256"] = builder.sha256(source)

        # Rewrite rows from disk so their hashes/bytes exactly match the shared copies.
        for side, side_dir in (("server", server_dir), ("client", client_dir)):
            for row in rows_by_side[side]:
                path = side_dir / row["file"]
                row["bytes"] = path.stat().st_size
                row["sha256"] = builder.sha256(path)

        manifests: dict[str, dict] = {}
        for side, rows in rows_by_side.items():
            manifest_path = manifests_dir / f"{side}.json"
            bundle_dir = self.baseline / f"{side}-mods"
            manifest = {
                "schema": 1,
                "status": "PASS",
                "side": side,
                "baseline_manifest": "synthetic-candidate6.json",
                "baseline_manifest_sha256": "0" * 64,
                "baseline_bundle_sha256": builder.bundle_digest(rows),
                "bundle_dir": str(bundle_dir),
                "file_count": 50,
                "bytes": sum(row["bytes"] for row in rows),
                "bundle_sha256": builder.bundle_digest(rows),
                "manifest_path": str(manifest_path),
                "files": rows,
            }
            manifest_path.write_bytes(builder.stable_json(manifest))
            manifests[side] = manifest

        server_manifest_sha = builder.sha256(manifests_dir / "server.json")
        client_manifest_sha = builder.sha256(manifests_dir / "client.json")
        server_bundle_sha = manifests["server"]["bundle_sha256"]
        client_bundle_sha = manifests["client"]["bundle_sha256"]
        pair_sha = builder.pair_digest(server_bundle_sha, client_bundle_sha)
        release = {
            "schema": 1,
            "status": "PASS",
            "purpose": "synthetic Candidate10",
            "output_root": str(self.baseline),
            "source_unchanged": True,
            "server": {
                "file_count": 50,
                "bytes": manifests["server"]["bytes"],
                "bundle_sha256": server_bundle_sha,
                "manifest_sha256": server_manifest_sha,
            },
            "client": {
                "file_count": 50,
                "bytes": manifests["client"]["bytes"],
                "bundle_sha256": client_bundle_sha,
                "manifest_sha256": client_manifest_sha,
            },
            "bundle_pair_sha256": pair_sha,
        }
        release_bytes = builder.stable_json(release)
        (self.baseline / "release-lock.json").write_bytes(release_bytes)
        (self.baseline / "READY.json").write_bytes(release_bytes)

        # The synthetic guard and compat artifacts are independently locked.
        self._jar(self.cc_path, builder.CC_COMPAT_MOD_ID, "cc compat")
        self._jar(self.guard_path, builder.GUARD_MOD_ID, "chute guard")
        guard_lock = builder.GuardLock(
            self.guard_path.name,
            self.guard_path.stat().st_size,
            builder.sha256(self.guard_path),
            builder.GUARD_MOD_ID,
        )
        compat_lock = builder.GuardLock(
            self.cc_path.name,
            self.cc_path.stat().st_size,
            builder.sha256(self.cc_path),
            builder.CC_COMPAT_MOD_ID,
        )
        lock = builder.Candidate10Lock(
            builder.sha256(self.baseline / "release-lock.json"),
            server_manifest_sha,
            client_manifest_sha,
            server_bundle_sha,
            client_bundle_sha,
            pair_sha,
            "cc-tweaked-test.jar",
            next(row["sha256"] for row in manifests["server"]["files"] if row["file"] == "cc-tweaked-test.jar"),
            server_only[0],
            next(row["sha256"] for row in manifests["server"]["files"] if row["file"] == server_only[0]),
            server_only[1],
            client_only[0],
            next(row["sha256"] for row in manifests["client"]["files"] if row["file"] == client_only[0]),
            client_only[1],
        )
        return lock, guard_lock, compat_lock

    def _build(self, name: str = "out"):
        return builder.build_candidate11(
            self.cc_path,
            self.compat_lock.sha256,
            self.guard_path,
            self.guard_lock.sha256,
            self.root / name,
            baseline_root=self.baseline,
            lock=self.lock,
            guard_lock=self.guard_lock,
            cc_compat_lock=self.compat_lock,
        )

    def test_success_is_52_jars_and_all_50_baseline_rows_are_identical(self):
        result = self._build()
        self.assertEqual(result["server"]["manifest"]["file_count"], 52)
        self.assertEqual(result["client"]["manifest"]["file_count"], 52)
        self.assertEqual(result["server"]["manifest"]["candidate10_invariance"]["unchanged_rows"], 50)
        self.assertEqual(result["client"]["manifest"]["candidate10_invariance"]["added_rows"], 2)
        self.assertEqual(result["server"]["manifest"]["candidate10_invariance"]["replaced_rows"], 0)
        self.assertEqual(result["server"]["manifest"]["bundle_dir"], str(self.root / "out" / "server-mods"))
        self.assertEqual(result["server"]["manifest"]["files"][-1]["file"], "grieflogger-test.jar")
        self.assertEqual(result["server"]["manifest"]["files"][-2]["file"], self.guard_path.name)
        self.assertEqual(
            result["server"]["manifest"]["runtime_sanitization_policy"]
            if "runtime_sanitization_policy" in result["server"]["manifest"]
            else "absent",
            "absent",
        )
        published = builder.validate_published_candidate11(
            self.root / "out",
            baseline_root=self.baseline,
            lock=self.lock,
            guard_lock=self.guard_lock,
            cc_compat_lock=self.compat_lock,
        )
        self.assertEqual(published["server"]["bundle_sha256"], result["server"]["bundle_sha256"])
        release = json.loads((self.root / "out" / "READY.json").read_text(encoding="utf-8"))
        self.assertEqual(release["runtime_sanitization_policy"]["published_bundle_state"], "unsanitized")
        self.assertEqual(release["runtime_sanitization_policy"]["client_runtime_jar_transforms_allowed"], False)

    def test_missing_final_cc_lock_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "artifact lock"):
            builder.build_candidate11(
                self.cc_path,
                self.compat_lock.sha256,
                self.guard_path,
                self.guard_lock.sha256,
                self.root / "no-lock",
                baseline_root=self.baseline,
                lock=self.lock,
                guard_lock=self.guard_lock,
                cc_compat_lock=None,
            )
        self.assertFalse((self.root / "no-lock").exists())

    def test_wrong_sha_fails_before_output(self):
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self._build_with(cc_sha="0" * 64)

    def test_wrong_mod_id_fails_before_output(self):
        wrong = self.root / "wrong.jar"
        self._jar(wrong, "not_the_guard", "wrong")
        with self.assertRaisesRegex(ValueError, "must expose only mod ID"):
            builder.build_candidate11(
                self.cc_path,
                self.compat_lock.sha256,
                wrong,
                builder.sha256(wrong),
                self.root / "wrong-mod",
                baseline_root=self.baseline,
                lock=self.lock,
                guard_lock=builder.GuardLock(wrong.name, wrong.stat().st_size, builder.sha256(wrong), builder.GUARD_MOD_ID),
                cc_compat_lock=self.compat_lock,
            )
        self.assertFalse((self.root / "wrong-mod").exists())

    def test_baseline_tamper_and_extra_jar_are_rejected(self):
        original = self.baseline / "server-mods" / "common-00.jar"
        original.write_bytes(original.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "Candidate10 server JAR byte/SHA-256 mismatch"):
            self._build("tampered")
        self.assertFalse((self.root / "tampered").exists())

        # Restore the locked byte and then add an unmanifested JAR.
        self._jar(original, "common_00", "server:common-00.jar")
        self._jar(self.baseline / "server-mods" / "extra.jar", "extra", "extra")
        with self.assertRaisesRegex(ValueError, "exactly 50"):
            self._build("extra")
        self.assertFalse((self.root / "extra").exists())

    def test_ready_tamper_is_rejected_by_consumer_gate(self):
        self._build("ready")
        ready = self.root / "ready" / "READY.json"
        ready.write_bytes(ready.read_bytes().replace(b'"status": "PASS"', b'"status": "FAIL"'))
        with self.assertRaisesRegex(ValueError, "bytes differ|not PASS"):
            builder.validate_published_candidate11(
                self.root / "ready",
                baseline_root=self.baseline,
                lock=self.lock,
                guard_lock=self.guard_lock,
                cc_compat_lock=self.compat_lock,
            )

    def test_existing_output_is_never_reused(self):
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaises(FileExistsError):
            self._build("existing")

    def _build_with(self, *, cc_sha: str):
        return builder.build_candidate11(
            self.cc_path,
            cc_sha,
            self.guard_path,
            self.guard_lock.sha256,
            self.root / "bad-sha",
            baseline_root=self.baseline,
            lock=self.lock,
            guard_lock=self.guard_lock,
            cc_compat_lock=self.compat_lock,
        )


if __name__ == "__main__":
    unittest.main()
