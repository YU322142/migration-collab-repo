from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_candidate12_waypoint_bundles.py")
SPEC = importlib.util.spec_from_file_location("candidate12_builder", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class Candidate12BuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.baseline = self.root / "candidate11"
        self.fixed = self.root / "fixed-waypoint.jar"
        self.old_fixed = self.root / builder.REJECTED_WAYPOINT_FILE
        self.lock = self._make_baseline()
        self._make_fixed_waypoint()

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

    def _make_baseline(self) -> builder.Candidate11Lock:
        server_dir = self.baseline / "server-mods"
        client_dir = self.baseline / "client-mods"
        manifests_dir = self.baseline / "manifests"
        server_dir.mkdir(parents=True)
        client_dir.mkdir()
        manifests_dir.mkdir()

        common = [
            (f"common-{index:02d}.jar", f"common_{index:02d}")
            for index in range(48)
        ]
        common.extend(
            [
                ("cc-tweaked-test.jar", "computercraft"),
                ("shared-support.jar", "shared_support"),
                ("waypoint-fire-old.jar", builder.WAYPOINT_MOD_ID),
            ]
        )
        side_only = {
            "server": ("grieflogger-test.jar", "grieflogger"),
            "client": ("chest-colorizer-test.jar", "colorizer"),
        }
        rows_by_side: dict[str, list[dict[str, object]]] = {}
        for side in ("server", "client"):
            side_dir = server_dir if side == "server" else client_dir
            rows: list[dict[str, object]] = []
            for filename, mod_id in common:
                source = server_dir / filename
                if side == "server":
                    self._jar(source, mod_id, f"shared:{filename}")
                destination = side_dir / filename
                if destination != source:
                    shutil.copy2(source, destination)
                rows.append(
                    {
                        "file": filename,
                        "bytes": destination.stat().st_size,
                        "sha256": builder.sha256(destination),
                        "mod_ids": [mod_id],
                        "role": "candidate",
                    }
                )
            filename, mod_id = side_only[side]
            destination = side_dir / filename
            self._jar(destination, mod_id, f"{side}:{filename}")
            rows.append(
                {
                    "file": filename,
                    "bytes": destination.stat().st_size,
                    "sha256": builder.sha256(destination),
                    "mod_ids": [mod_id],
                    "role": "side_only",
                }
            )
            rows.sort(key=lambda row: str(row["file"]).casefold())
            rows_by_side[side] = rows

        manifests: dict[str, dict[str, object]] = {}
        for side, rows in rows_by_side.items():
            manifest_path = manifests_dir / f"{side}.json"
            bundle_dir = self.baseline / f"{side}-mods"
            manifest = {
                "schema": 1,
                "candidate": 11,
                "status": "PASS",
                "side": side,
                "bundle_dir": str(bundle_dir),
                "file_count": 52,
                "bytes": sum(int(row["bytes"]) for row in rows),
                "bundle_sha256": builder.bundle_digest(rows),
                "manifest_path": str(manifest_path),
                "files": rows,
            }
            manifest_path.write_bytes(builder.stable_json(manifest))
            manifests[side] = manifest

        server_bundle = str(manifests["server"]["bundle_sha256"])
        client_bundle = str(manifests["client"]["bundle_sha256"])
        release = {
            "schema": 1,
            "candidate": 11,
            "status": "PASS",
            "output_root": str(self.baseline),
            "source_unchanged": True,
            "server": {
                "file_count": 52,
                "bundle_sha256": server_bundle,
                "manifest_sha256": builder.sha256(manifests_dir / "server.json"),
            },
            "client": {
                "file_count": 52,
                "bundle_sha256": client_bundle,
                "manifest_sha256": builder.sha256(manifests_dir / "client.json"),
            },
            "bundle_pair_sha256": builder.pair_digest(server_bundle, client_bundle),
        }
        payload = builder.stable_json(release)
        (self.baseline / "release-lock.json").write_bytes(payload)
        (self.baseline / "READY.json").write_bytes(payload)

        waypoint_row = next(
            row
            for row in rows_by_side["server"]
            if builder.WAYPOINT_MOD_ID in row["mod_ids"]
        )
        return builder.Candidate11Lock(
            release_lock_sha256=builder.sha256(self.baseline / "READY.json"),
            server_manifest_sha256=builder.sha256(manifests_dir / "server.json"),
            client_manifest_sha256=builder.sha256(manifests_dir / "client.json"),
            server_bundle_sha256=server_bundle,
            client_bundle_sha256=client_bundle,
            bundle_pair_sha256=builder.pair_digest(server_bundle, client_bundle),
            server_only_file=side_only["server"][0],
            server_only_sha256=next(
                str(row["sha256"])
                for row in rows_by_side["server"]
                if row["file"] == side_only["server"][0]
            ),
            server_only_mod_id=side_only["server"][1],
            client_only_file=side_only["client"][0],
            client_only_sha256=next(
                str(row["sha256"])
                for row in rows_by_side["client"]
                if row["file"] == side_only["client"][0]
            ),
            client_only_mod_id=side_only["client"][1],
            waypoint_file="waypoint-fire-old.jar",
            waypoint_bytes=int(waypoint_row["bytes"]),
            waypoint_sha256=str(waypoint_row["sha256"]),
        )

    def _make_fixed_waypoint(self) -> None:
        old = self.baseline / "server-mods" / "waypoint-fire-old.jar"
        with zipfile.ZipFile(old) as source, zipfile.ZipFile(
            self.fixed, "w", compression=zipfile.ZIP_STORED
        ) as destination:
            for info in source.infolist():
                destination.writestr(info, source.read(info.filename))
            destination.writestr("candidate12-fix-marker.txt", b"registered-argument")

    def _build(self, name: str = "out") -> dict:
        return builder.build_candidate12(
            self.fixed,
            builder.sha256(self.fixed),
            self.root / name,
            baseline_root=self.baseline,
            lock=self.lock,
        )

    def test_synthetic_candidate11_is_validated(self) -> None:
        validated = builder.validate_candidate11(self.baseline, self.lock)
        self.assertEqual(validated["server"]["bundle_sha256"], self.lock.server_bundle_sha256)
        self.assertEqual(validated["client"]["bundle_sha256"], self.lock.client_bundle_sha256)

    def test_replaces_only_waypoint_and_preserves_51_rows(self) -> None:
        result = self._build()
        self.assertEqual(result["server"]["manifest"]["candidate11_invariance"]["unchanged_rows"], 51)
        self.assertEqual(result["client"]["manifest"]["candidate11_invariance"]["replaced_rows"], 1)
        for side in ("server", "client"):
            rows = result[side]["rows"]
            self.assertEqual(len(rows), 52)
            self.assertEqual(sum(row["candidate12_comparison"] == "exact_candidate11" for row in rows), 51)
            replacement = next(row for row in rows if row["mod_ids"] == [builder.WAYPOINT_MOD_ID])
            self.assertEqual(replacement["sha256"], builder.sha256(self.fixed))

        published = builder.validate_published_candidate12(
            self.root / "out",
            self.fixed,
            builder.sha256(self.fixed),
            baseline_root=self.baseline,
            lock=self.lock,
        )
        self.assertEqual(published["ready_sha256"], builder.sha256(self.root / "out" / "READY.json"))
        self.assertEqual((self.root / "out" / "READY.json").read_bytes(), (self.root / "out" / "release-lock.json").read_bytes())

    def test_old_waypoint_is_rejected_before_output(self) -> None:
        old = self.baseline / "server-mods" / "waypoint-fire-old.jar"
        shutil.copy2(old, self.old_fixed)
        with self.assertRaisesRegex(ValueError, "rejected|collides"):
            builder.build_candidate12(
                self.old_fixed,
                builder.sha256(self.old_fixed),
                self.root / "rejected",
                baseline_root=self.baseline,
                lock=self.lock,
            )
        self.assertFalse((self.root / "rejected").exists())

    def test_wrong_sha_is_rejected_before_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            builder.build_candidate12(
                self.fixed,
                "0" * 64,
                self.root / "bad-sha",
                baseline_root=self.baseline,
                lock=self.lock,
            )
        self.assertFalse((self.root / "bad-sha").exists())

    def test_wrong_mod_id_is_rejected_before_output(self) -> None:
        wrong = self.root / "wrong.jar"
        self._jar(wrong, "not_waypoint", "wrong")
        with self.assertRaisesRegex(ValueError, "must expose only mod ID"):
            builder.build_candidate12(
                wrong,
                builder.sha256(wrong),
                self.root / "wrong-mod",
                baseline_root=self.baseline,
                lock=self.lock,
            )
        self.assertFalse((self.root / "wrong-mod").exists())

    def test_existing_output_is_never_reused(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        with self.assertRaises(FileExistsError):
            self._build("existing")

    def test_ready_tamper_is_rejected(self) -> None:
        self._build()
        ready = self.root / "out" / "READY.json"
        ready.write_bytes(ready.read_bytes().replace(b'"status": "PASS"', b'"status": "FAIL"'))
        with self.assertRaisesRegex(ValueError, "bytes differ|not PASS"):
            builder.validate_published_candidate12(
                self.root / "out",
                self.fixed,
                builder.sha256(self.fixed),
                baseline_root=self.baseline,
                lock=self.lock,
            )


if __name__ == "__main__":
    unittest.main()
