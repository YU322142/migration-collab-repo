#!/usr/bin/env python3
"""Unit tests for the Mechanomania UI overlay transforms."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from prepare_mechanomania_ui_overrides import (
    RULES,
    build_overlay,
    transform_json,
    transform_text,
)


class OverlayTransformTests(unittest.TestCase):
    def test_create_only_disables_main_menu_button(self) -> None:
        before = (
            b"mainMenuConfigButtonRow = 2\r\n"
            b"mainMenuConfigButtonOffsetX = -65536\r\n"
            b"ingameMenuConfigButtonRow = 3\r\n"
        )
        after, changes = transform_text("config/create-client.toml", before)
        self.assertIn(b"mainMenuConfigButtonRow = 0", after)
        self.assertIn(b"mainMenuConfigButtonOffsetX = -65536", after)
        self.assertIn(b"ingameMenuConfigButtonRow = 3", after)
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"))
        self.assertEqual(len(after), len(before))
        self.assertEqual(len(changes), 1)

    def test_controller_only_disables_main_menu_button(self) -> None:
        before = (
            b"config_button_main_menu_row = 2\r\n"
            b"config_button_main_menu_offset = 4\r\n"
            b"config_button_ingame_menu_row = 3\r\n"
        )
        after, _ = transform_text(
            "config/createtweakedcontrollers-client.toml", before
        )
        self.assertIn(b"config_button_main_menu_row = 0", after)
        self.assertIn(b"config_button_main_menu_offset = 4", after)
        self.assertIn(b"config_button_ingame_menu_row = 3", after)
        self.assertEqual(after.count(b"\r\n"), before.count(b"\r\n"))
        self.assertEqual(len(after), len(before))

    def test_modernfix_adds_unique_branding_override(self) -> None:
        before = b"# mixin.feature.branding=true # default\nfoo=true\n"
        after, _ = transform_text("config/modernfix-mixins.properties", before)
        self.assertEqual(after.count(b"mixin.feature.branding=false"), 1)
        self.assertIn(before, after)

    def test_modernfix_replaces_existing_branding_override(self) -> None:
        before = b"mixin.feature.branding=true\nfoo=true\n"
        after, _ = transform_text("config/modernfix-mixins.properties", before)
        self.assertEqual(after.count(b"mixin.feature.branding=false"), 1)
        self.assertNotIn(b"mixin.feature.branding=true", after)
        self.assertIn(b"foo=true", after)

    def test_kubejs_clears_only_window_title(self) -> None:
        before_value = {
            "window_title": "Mechanomania 1.1.11.1",
            "show_components": True,
        }
        after, changes = transform_json(
            "kubejs/config/client.json", json.dumps(before_value).encode("utf-8")
        )
        value = json.loads(after)
        self.assertEqual(value["window_title"], "")
        self.assertTrue(value["show_components"])
        self.assertEqual(changes, ["window_title: non-empty -> empty"])

    def test_kubejs_fails_closed_after_source_drift(self) -> None:
        before = json.dumps({"window_title": ""}).encode("utf-8")
        with self.assertRaises(RuntimeError):
            transform_json("kubejs/config/client.json", before)

    def test_builder_refuses_non_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            output.mkdir()
            (output / "stale.txt").write_text("stale", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_overlay(source, output)

    def test_realistic_fixture_emits_exact_file_set(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            output = root / "output"
            fixtures = {
                "config/create-client.toml": (
                    "mainMenuConfigButtonRow = 2\n"
                    "mainMenuConfigButtonOffsetX = -65536\n"
                    "ingameMenuConfigButtonRow = 3\n"
                ),
                "config/createtweakedcontrollers-client.toml": (
                    "config_button_main_menu_row = 2\n"
                    "config_button_ingame_menu_row = 3\n"
                ),
                "config/modernfix-mixins.properties": "foo=true\n",
                "kubejs/config/client.json": json.dumps(
                    {"window_title": "Mechanomania", "show_components": True}
                ),
                "icon.png": "icon",
                "config/create-client-1.toml.bak": "mainMenuConfigButtonRow = 2\n",
            }
            for relative, payload in fixtures.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
            report = build_overlay(source, output)
            actual = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual, set(RULES))
            self.assertEqual(
                [row["path"] for row in report["excluded_not_copied"]],
                ["icon.png", "config/create-client-1.toml.bak"],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
