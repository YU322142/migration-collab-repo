#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).with_name("build_c6c_singleplayer_parity.py")
SPEC = importlib.util.spec_from_file_location("c6c_parity", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class C6CSingleplayerParityTest(unittest.TestCase):
    def make_jar(self, root: Path, class_payload: bytes) -> Path:
        jar = root / "base.jar"
        with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MODULE.TARGET_CLASS, class_payload)
            archive.writestr("data/c6c/example.json", b'{"kept":true}\n')
            archive.writestr("META-INF/neoforge.mods.toml", b'modId="c6c"\n')
        return jar

    def test_exact_overlay_and_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b"prefix" + MODULE.OLD_SEQUENCE + b"suffix"
            source = self.make_jar(root, original)
            output = root / "patched.jar"
            result = MODULE.transform(source, output, expected_sha256=None)
            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["login_systems_modified"])
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
                self.assertEqual(
                    after.read(MODULE.TARGET_CLASS),
                    b"prefix" + MODULE.NEW_SEQUENCE + b"suffix",
                )
                self.assertEqual(
                    before.read("data/c6c/example.json"),
                    after.read("data/c6c/example.json"),
                )
                self.assertEqual(
                    before.read("META-INF/neoforge.mods.toml"),
                    after.read("META-INF/neoforge.mods.toml"),
                )

    def test_rejects_unknown_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_jar(root, b"not-the-audited-class")
            with self.assertRaises(MODULE.PatchError):
                MODULE.transform(source, root / "patched.jar", expected_sha256=None)

    def test_rejects_duplicate_patch_sites(self) -> None:
        with self.assertRaises(MODULE.PatchError):
            MODULE.patch_class(MODULE.OLD_SEQUENCE * 2)

    def test_rejects_wrong_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.make_jar(root, MODULE.OLD_SEQUENCE)
            with self.assertRaises(MODULE.PatchError):
                MODULE.transform(source, root / "patched.jar", expected_sha256="00" * 32)


if __name__ == "__main__":
    unittest.main()
