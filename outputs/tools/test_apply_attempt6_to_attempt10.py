#!/usr/bin/env python3
"""Tests for the fail-closed Attempt6 -> Attempt10 integration workflow."""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
import zipfile


SCRIPT = Path(__file__).with_name("apply_attempt6_to_attempt10.py")
SPEC = importlib.util.spec_from_file_location("attempt10_apply", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
import sys
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


@contextmanager
def exact_attempt_roots():
    """Create paired direct-child roots satisfying the production name lock."""
    for _ in range(100):
        attempt = str(9_000_000_000_000 + (uuid.uuid4().int % 999_999_999_999))
        server = MODULE.ALLOWED_ROOT / (
            f"mechanomania-matched-runtime-attempt{attempt}-20260814"
        )
        client = MODULE.ALLOWED_ROOT / (
            f"mechanomania-matched-client-attempt{attempt}-20260814"
        )
        if not server.exists() and not client.exists():
            break
    else:
        raise RuntimeError("could not allocate unique exact Attempt fixture roots")
    try:
        (server / "mods").mkdir(parents=True)
        (client / "mods").mkdir(parents=True)
        yield server, client
    finally:
        shutil.rmtree(server, ignore_errors=True)
        shutil.rmtree(client, ignore_errors=True)


class Attempt10IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.release = MODULE.validate_release()
        cls.candidate = MODULE.validate_candidate()
        cls.items = MODULE.build_patch_items(cls.release, cls.candidate)

    def test_locked_inputs_and_side_plan(self) -> None:
        jars = [item for item in self.items if item.kind == "jar"]
        loose = [item for item in self.items if item.kind == "loose"]
        self.assertEqual(len(jars), 11)
        self.assertEqual(len(loose), 7)
        self.assertTrue(all(set(item.sides) == {"server", "client"} for item in jars))
        self.assertTrue(all(item.sides == ("server",) for item in loose))
        self.assertFalse(self.release["mcmodsync_selected"])

    def test_guard_rejects_unapproved_attempt_root(self) -> None:
        with tempfile.TemporaryDirectory(dir=MODULE.ALLOWED_ROOT, prefix="wrong-target-") as raw:
            root = Path(raw)
            (root / "mods").mkdir()
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.guard_target_root(root, "test")

    def test_guard_accepts_attempt11_role_matched_roots(self) -> None:
        with exact_attempt_roots() as (server, client):
            self.assertEqual(MODULE.guard_target_root(server, "server"), server.resolve())
            self.assertEqual(MODULE.guard_target_root(client, "client"), client.resolve())
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.guard_target_root(server, "client")
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.guard_target_root(client, "server")

    def test_preflight_rejects_mismatched_attempt_numbers(self) -> None:
        with exact_attempt_roots() as (server, _client):
            other = MODULE.ALLOWED_ROOT / (
                "mechanomania-matched-client-attempt999999999999999-20260814"
            )
            if other.exists():
                self.skipTest(f"fixture collision: {other}")
            try:
                (other / "mods").mkdir(parents=True)
                with self.assertRaises(MODULE.IntegrationError):
                    MODULE.preflight_targets(self.items, server, other)
            finally:
                shutil.rmtree(other, ignore_errors=True)

    def test_mcmodsync_metadata_is_detected_after_rename(self) -> None:
        with tempfile.TemporaryDirectory(dir=MODULE.ALLOWED_ROOT, prefix="attempt10-mcmodsync-") as raw:
            mods = Path(raw) / "mods"
            mods.mkdir()
            disguised = mods / "harmless-name.jar"
            with zipfile.ZipFile(disguised, "w") as archive:
                archive.writestr(
                    "META-INF/neoforge.mods.toml",
                    'modLoader="javafml"\n[[mods]]\nmodId="mcmodsync"\n',
                )
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.assert_mcmodsync_absent(mods, "fixture")

    def test_full_preflight_apply_and_idempotence_without_world(self) -> None:
        with exact_attempt_roots() as (server, client):
            release_mod_maps = {
                side: {
                    row["file"].casefold(): row
                    for row in self.release[f"{side}_mods"]["rows"]
                }
                for side in ("server", "client")
            }
            for item in self.items:
                for side in item.sides:
                    root = server if side == "server" else client
                    if item.kind == "jar":
                        source = (
                            MODULE.LOCKED_RELEASE_ROOT
                            / side
                            / "mods"
                            / release_mod_maps[side][item.relative.casefold()]["file"]
                        )
                        target = root / "mods" / item.relative
                        os.link(source, target)
                    else:
                        source = (
                            MODULE.LOCKED_RELEASE_ROOT
                            / side
                            / "overlay"
                            / Path(item.relative)
                        )
                        target = root / Path(item.relative)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
            roots, operations = MODULE.preflight_targets(self.items, server, client)
            self.assertEqual(len(operations), 29)
            self.assertTrue(all(operation.state == "SOURCE_EXACT" for operation in operations))
            result = MODULE.apply_operations(operations)
            self.assertEqual(result["changed"], 29)
            self.assertFalse(any((server / "world").exists() for _ in (0,)))
            _, second = MODULE.preflight_targets(self.items, server, client)
            self.assertTrue(
                all(operation.state == "ALREADY_PATCHED_EXACT" for operation in second)
            )
            again = MODULE.apply_operations(second)
            self.assertEqual(again["changed"], 0)
            self.assertEqual(again["already_patched"], 29)
            for side, root in roots.items():
                MODULE.assert_mcmodsync_absent(root / "mods", f"fixture {side}")

    def test_unknown_hash_aborts_before_writing_other_targets(self) -> None:
        with exact_attempt_roots() as (server, client):
            release_mod_maps = {
                side: {
                    row["file"].casefold(): row
                    for row in self.release[f"{side}_mods"]["rows"]
                }
                for side in ("server", "client")
            }
            first_target: Path | None = None
            first_hash: str | None = None
            corrupted = False
            for item in self.items:
                for side in item.sides:
                    root = server if side == "server" else client
                    if item.kind == "jar":
                        source = (
                            MODULE.LOCKED_RELEASE_ROOT
                            / side
                            / "mods"
                            / release_mod_maps[side][item.relative.casefold()]["file"]
                        )
                        target = root / "mods" / item.relative
                        shutil.copy2(source, target)
                    else:
                        source = (
                            MODULE.LOCKED_RELEASE_ROOT
                            / side
                            / "overlay"
                            / Path(item.relative)
                        )
                        target = root / Path(item.relative)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                    if first_target is None:
                        first_target = target
                        first_hash = MODULE.sha256(target)
                    elif not corrupted:
                        target.write_bytes(b"unknown target bytes")
                        corrupted = True
            assert first_target is not None and first_hash is not None
            with self.assertRaises(MODULE.IntegrationError):
                MODULE.preflight_targets(self.items, server, client)
            self.assertEqual(MODULE.sha256(first_target), first_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
