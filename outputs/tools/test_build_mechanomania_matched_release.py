from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


MODULE_PATH = Path(__file__).with_name("build_mechanomania_matched_release.py")
SPEC = importlib.util.spec_from_file_location("mechanomania_builder", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def make_jar(path: Path, mod_id: str, *, dependency: str | None = None) -> None:
    dep = ""
    if dependency:
        dep = f'''\n[[dependencies.{mod_id}]]\nmodId="{dependency}"\ntype="required"\nversionRange="*"\nside="BOTH"\n'''
    metadata = f'''modLoader="javafml"\nloaderVersion="[4,)"\nlicense="MIT"\n[[mods]]\nmodId="{mod_id}"\nversion="1.0.0"\n{dep}'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/neoforge.mods.toml", metadata)
        archive.writestr(f"{mod_id}/Marker.class", b"synthetic")


class BuilderUnitTests(unittest.TestCase):
    def test_version_ranges(self) -> None:
        self.assertTrue(builder._version_matches("1.6.0", "(1.6.0,)" ) is False)
        self.assertTrue(builder._version_matches("1.6.1", "(1.6.0,)"))
        self.assertTrue(builder._version_matches("4.9.1", "4.7.5.1"))
        self.assertTrue(builder._version_matches("2.3.0", "[0.0.1,)"))

    def test_side_only_mapping(self) -> None:
        base = {"file": "gui.jar", "path": "x", "sha256": "A" * 64, "bytes": 1, "source": "TEST"}
        selections = {"server": {"gui.jar": dict(base)}, "client": {"gui.jar": dict(base)}}
        builder._apply_locked_side_overrides(
            selections,
            [{"file": "gui.jar", "sha256": "A" * 64, "classification": "CLIENT_ONLY"}],
        )
        self.assertNotIn("gui.jar", selections["server"])
        self.assertIn("gui.jar", selections["client"])

    def test_duplicate_mod_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.jar"
            second = root / "second.jar"
            make_jar(first, "duplicate")
            make_jar(second, "duplicate")
            rows = [builder.inspect_jar(first), builder.inspect_jar(second)]
            with self.assertRaisesRegex(builder.ReleaseError, "duplicate top-level mod IDs"):
                builder._validate_dependency_closure("server", rows, {})

    def test_missing_dependency_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dependent.jar"
            make_jar(path, "dependent", dependency="absent")
            with self.assertRaisesRegex(builder.ReleaseError, "missing required dependencies"):
                builder._validate_dependency_closure("server", [builder.inspect_jar(path)], {})

    def test_virtual_connector_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            connector = root / "connector.jar"
            dependent = root / "dependent.jar"
            make_jar(connector, "connector")
            make_jar(dependent, "dependent", dependency="fabricloader")
            result = builder._validate_dependency_closure(
                "server",
                [builder.inspect_jar(connector), builder.inspect_jar(dependent)],
                {"connector": ["fabricloader"]},
            )
            self.assertEqual("PASS", result["status"])

    def test_path_traversal_rejected(self) -> None:
        with self.assertRaises(builder.ReleaseError):
            builder._safe_rel("../world/level.dat", "test")

    def test_pair_digest_is_side_sensitive(self) -> None:
        first = builder._pair_digest("A" * 64, "B" * 64, "C" * 64, "D" * 64)
        second = builder._pair_digest("B" * 64, "A" * 64, "C" * 64, "D" * 64)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
