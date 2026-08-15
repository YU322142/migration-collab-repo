#!/usr/bin/env python3
"""Unit tests for the deterministic C6C UI purifier."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_c6c_purified import PurificationError, sha256_file, transform
from test_build_c6c_purified import verify


MIXINS = {
    "required": True,
    "mixins": ["GameplayMixin", "BrandingControlMixin"],
    "client": [
        "GameplayClientMixin",
        "UI.LogoRendererMixin",
        "UI.TitleScreenMixin",
    ],
}


def make_fixture(path: Path, *, signed: bool = False, missing_ui: bool = False) -> None:
    entries: dict[str, bytes] = {
        "META-INF/neoforge.mods.toml": b'modLoader="javafml"\n',
        "c6c.mixins.json": json.dumps(MIXINS).encode("utf-8"),
        "assets/minecraft/lang/en_us.json": json.dumps(
            {"menu.online": "Acquire a server"}
        ).encode("utf-8"),
        "assets/minecraft/lang/zh_cn.json": json.dumps(
            {"menu.online": "\U0001f30f\u5f00\u670d\U0001f30f"},
            ensure_ascii=False,
        ).encode("utf-8"),
        "assets/minecraft/textures/gui/title/minecraft.png": b"brand",
        "org/huahua/pr/mixin/BrandingControlMixin.class": b"branding",
        "org/huahua/pr/mixin/UI/LogoRendererMixin.class": b"logo",
        "org/huahua/pr/mixin/UI/TitleScreenMixin.class": (
            b"https://www.xyebbs.com/resources/1116/prom\n"
            b"https://www.bisecthosting.com/curseforge?curseforge_project_id=1469136"
        ),
        "org/huahua/pr/Gameplay.class": b"gameplay-bytecode",
        "data/c6c/recipe/example.json": b'{"type":"minecraft:crafting_shapeless"}',
    }
    if missing_ui:
        del entries["org/huahua/pr/mixin/UI/TitleScreenMixin.class"]
    if signed:
        entries["META-INF/SIGNATURE.SF"] = b"signed"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


class PurifierTests(unittest.TestCase):
    def test_removes_only_audited_ui_and_preserves_gameplay(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.jar"
            output = root / "output.jar"
            make_fixture(source)
            result = transform(source, output)
            check = verify(source, output)
            self.assertEqual(check["status"], "PASS", check["failures"])
            self.assertEqual(result["preserved_data_entry_count"], 1)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    archive.read("org/huahua/pr/Gameplay.class"),
                    b"gameplay-bytecode",
                )
                mixins = json.loads(archive.read("c6c.mixins.json"))
                self.assertEqual(mixins["mixins"], ["GameplayMixin"])
                self.assertEqual(mixins["client"], ["GameplayClientMixin"])

    def test_output_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.jar"
            first = root / "first.jar"
            second = root / "second.jar"
            make_fixture(source)
            transform(source, first)
            transform(source, second)
            self.assertEqual(sha256_file(first), sha256_file(second))
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_fails_closed_when_expected_ui_entry_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.jar"
            make_fixture(source, missing_ui=True)
            with self.assertRaises(PurificationError):
                transform(source, root / "output.jar")

    def test_rejects_signed_jar(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.jar"
            make_fixture(source, signed=True)
            with self.assertRaises(PurificationError):
                transform(source, root / "output.jar")


if __name__ == "__main__":
    unittest.main(verbosity=2)
