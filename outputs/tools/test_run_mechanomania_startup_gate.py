from __future__ import annotations

import contextlib
import hashlib
import inspect
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import run_mechanomania_startup_gate as gate


CEI_NAME = "create-enchantment-industry-2.5.1.1-legacy-sable.jar"
MINEASTR_CONTENT = b"fake MineAstr 0.6.26 test jar"
YACL_CONTENT = b"fake YACL 3.7.1 test jar"
CONTENT_BACKPORT_CONTENT = b"fake Content Backport cat serializer fix test jar"
HOTBATH_CONTENT = b"fake Hot Bath registry trigger fix test jar"
WORLD_EDIT_CONTENT = b"fake WorldEdit direction property fix test jar"
CEI_CONTENT = b"fake CEI 2.5.1 legacy Sable compatibility test jar"
YACL_SHA256 = hashlib.sha256(YACL_CONTENT).hexdigest().upper()
CONTENT_BACKPORT_SHA256 = hashlib.sha256(CONTENT_BACKPORT_CONTENT).hexdigest().upper()
HOTBATH_SHA256 = hashlib.sha256(HOTBATH_CONTENT).hexdigest().upper()
WORLD_EDIT_SHA256 = hashlib.sha256(WORLD_EDIT_CONTENT).hexdigest().upper()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def prepare_data_repair_fixture(base: Path) -> tuple[Path, Path, Path, dict[str, int]]:
    server = base / "server"
    client = base / "client"
    (server / "mods").mkdir(parents=True)
    (client / "mods").mkdir(parents=True)
    plan: list[dict] = []
    expected_bytes: dict[str, int] = {}
    for index in range(11):
        relative = f"fixture-fix-{index}.jar"
        content = f"patched jar {index}".encode()
        output_sha = hashlib.sha256(content).hexdigest().upper()
        expected_bytes[relative] = len(content)
        for root in (server, client):
            (root / "mods" / relative).write_bytes(content)
        plan.append(
            {
                "kind": "jar",
                "relative": relative,
                "sides": ["server", "client"],
                "source_sha256": hashlib.sha256(f"source {index}".encode()).hexdigest().upper(),
                "output_sha256": output_sha,
            }
        )
    for index in range(7):
        relative = f"kubejs/data/fixture/fix-{index}.json"
        content = (json.dumps({"fixture": index}) + "\n").encode()
        target = server.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        expected_bytes[relative] = len(content)
        plan.append(
            {
                "kind": "loose",
                "relative": relative,
                "sides": ["server"],
                "source_sha256": hashlib.sha256(f"loose source {index}".encode()).hexdigest().upper(),
                "output_sha256": hashlib.sha256(content).hexdigest().upper(),
            }
        )
    payload = {
        "schema": "attempt10-data-resource-integration/v1",
        "status": "PASS_APPLIED",
        "targets": {
            "server": str(server.resolve()),
            "client": str(client.resolve()),
            "source_exact": 29,
            "already_patched_exact": 0,
            "mcmodsync_absent_before": True,
            "mcmodsync_absent_after": True,
        },
        "mcmodsync": {
            "client_install_currently_allowed": False,
            "policy": "globally absent for this Attempt10 integration",
            "release_selected": False,
            "server_install_allowed": False,
        },
        "application": {
            "jar_files_by_side": {"client": 11, "server": 11},
            "loose_files_by_side": {"client": 0, "server": 7},
            "target_operations": 29,
            "plan": plan,
        },
        "application_result": {
            "already_patched": 0,
            "changed": 29,
            "mode": "apply",
            "rolled_back": False,
        },
    }
    report = base / "data-repair-report.json"
    write_json(report, payload)
    return server, client, report, expected_bytes


def prepare_content_repair_fixture(base: Path) -> tuple[Path, Path, Path, dict]:
    server = base / "server"
    client = base / "client"
    for root in (server, client):
        (root / "mods").mkdir(parents=True)
    original_yuushya = b"original Yuushya fixture"
    patched_yuushya = b"patched Yuushya fixture"
    tlm = b"unchanged TLM fixture"
    maid_js = b"remove spawn box fixture"
    for root in (server, client):
        (root / "mods" / gate.YUUSHYA_PATCHED_NAME).write_bytes(patched_yuushya)
        (root / "mods" / gate.TLM_NAME).write_bytes(tlm)
    maid_target = server.joinpath(*PurePosixPath(gate.MAID_JS_RELATIVE).parts)
    maid_target.parent.mkdir(parents=True)
    maid_target.write_bytes(maid_js)
    overlay_contents = {
        relative: f"overlay fixture {index}".encode()
        for index, relative in enumerate(gate.TLM_OVERLAY_ARTIFACTS)
    }
    overlay_locks: dict[str, dict] = {}
    for relative, content in overlay_contents.items():
        target = client.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        overlay_locks[relative] = {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest().upper(),
        }
    original_sha = hashlib.sha256(original_yuushya).hexdigest().upper()
    patched_sha = hashlib.sha256(patched_yuushya).hexdigest().upper()
    tlm_sha = hashlib.sha256(tlm).hexdigest().upper()
    maid_sha = hashlib.sha256(maid_js).hexdigest().upper()
    manifest_sha = "A" * 64

    def artifact_row(path: Path, content: bytes) -> dict:
        return {
            "path": str(path.resolve()),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest().upper(),
        }

    before_yuushya = {
        side: {
            "state": "original",
            "artifact": {
                "path": str((root / "mods" / gate.YUUSHYA_ORIGINAL_NAME).resolve()),
                "bytes": len(original_yuushya),
                "sha256": original_sha,
            },
        }
        for side, root in (("server", server), ("client", client))
    }
    after_yuushya = {
        side: {
            "state": "patched",
            "artifact": artifact_row(root / "mods" / gate.YUUSHYA_PATCHED_NAME, patched_yuushya),
        }
        for side, root in (("server", server), ("client", client))
    }
    tlm_rows = {
        side: artifact_row(root / "mods" / gate.TLM_NAME, tlm)
        for side, root in (("server", server), ("client", client))
    }
    overlay_sources = [
        {
            "relative": relative,
            "path": str((base / "sources" / PurePosixPath(relative).name).resolve()),
            **identity,
        }
        for relative, identity in overlay_locks.items()
    ]
    before_overlay = [{"relative": relative, "state": "absent"} for relative in overlay_locks]
    after_overlay = [
        {
            "relative": relative,
            "state": "patched",
            "artifact": artifact_row(client.joinpath(*PurePosixPath(relative).parts), overlay_contents[relative]),
        }
        for relative in overlay_locks
    ]
    payload = {
        "schema": 1,
        "status": "PASS_APPLIED",
        "policy": {
            "spawn_box_recipe_removed": True,
            "maid_js_unchanged": True,
            "tlm_patch_side": "CLIENT",
            "yuushya_patch_side": "BOTH",
            "mcmodsync_globally_disabled": True,
        },
        "before": {
            "server": str(server.resolve()),
            "client": str(client.resolve()),
            "yuushya": before_yuushya,
            "tlm": tlm_rows,
            "maid_js": artifact_row(maid_target, maid_js),
            "client_overlay": before_overlay,
            "mcmodsync_active": False,
        },
        "after": {
            "server": str(server.resolve()),
            "client": str(client.resolve()),
            "yuushya": after_yuushya,
            "tlm": tlm_rows,
            "maid_js": artifact_row(maid_target, maid_js),
            "tlm_manifest": {"path": str((base / "manifest.json").resolve()), "bytes": 1, "sha256": manifest_sha},
            "tlm_overlay_sources": overlay_sources,
            "client_overlay": after_overlay,
            "mcmodsync_active": False,
        },
        "expected_yuushya_state": "patched",
    }
    report = base / "content-repair-report.json"
    write_json(report, payload)
    locks = {
        "YUUSHYA_ORIGINAL_BYTES": len(original_yuushya),
        "YUUSHYA_ORIGINAL_SHA256": original_sha,
        "YUUSHYA_PATCHED_BYTES": len(patched_yuushya),
        "YUUSHYA_PATCHED_SHA256": patched_sha,
        "TLM_BYTES": len(tlm),
        "TLM_SHA256": tlm_sha,
        "MAID_JS_BYTES": len(maid_js),
        "MAID_JS_SHA256": maid_sha,
        "TLM_MANIFEST_SHA256": manifest_sha,
        "TLM_OVERLAY_ARTIFACTS": overlay_locks,
    }
    return server, client, report, locks


def prepare_side(root: Path) -> tuple[Path, Path]:
    mods = root / "mods"
    mods.mkdir(parents=True)
    mineastr = mods / gate.MINEASTR_NAME
    mineastr.write_bytes(MINEASTR_CONTENT)
    (mods / gate.YACL_NAME).write_bytes(YACL_CONTENT)
    (mods / gate.CONTENT_BACKPORT_NAME).write_bytes(CONTENT_BACKPORT_CONTENT)
    (mods / gate.HOTBATH_NAME).write_bytes(HOTBATH_CONTENT)
    (mods / gate.WORLD_EDIT_NAME).write_bytes(WORLD_EDIT_CONTENT)
    cei = mods / CEI_NAME
    cei.write_bytes(CEI_CONTENT)
    return mineastr, cei


class ValidateSideTests(unittest.TestCase):
    def validate(self, root: Path, cei: Path, side: str = "test") -> dict:
        with mock.patch.multiple(
            gate,
            MINEASTR_BYTES=len(MINEASTR_CONTENT),
            MINEASTR_SHA256=gate.sha256(root / "mods" / gate.MINEASTR_NAME),
            YACL_BYTES=len(YACL_CONTENT),
            YACL_SHA256=YACL_SHA256,
            CONTENT_BACKPORT_BYTES=len(CONTENT_BACKPORT_CONTENT),
            CONTENT_BACKPORT_SHA256=CONTENT_BACKPORT_SHA256,
            HOTBATH_BYTES=len(HOTBATH_CONTENT),
            HOTBATH_SHA256=HOTBATH_SHA256,
            WORLD_EDIT_BYTES=len(WORLD_EDIT_CONTENT),
            WORLD_EDIT_SHA256=WORLD_EDIT_SHA256,
        ):
            return gate.validate_side(
                root,
                side,
                CEI_NAME,
                gate.sha256(cei).lower(),
                cei.stat().st_size,
            )

    def test_accepts_exact_hash_locked_cei_and_keeps_mineastr_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)

            result = self.validate(root, cei)

            self.assertEqual(6, result["active_jar_count"])
            self.assertEqual(gate.MINEASTR_NAME, Path(result["mineastr"]["path"]).name)
            self.assertEqual(gate.YACL_NAME, Path(result["yacl"]["path"]).name)
            self.assertEqual(
                gate.CONTENT_BACKPORT_NAME,
                Path(result["content_backport"]["path"]).name,
            )
            self.assertEqual(
                gate.HOTBATH_NAME,
                Path(result["hotbath_registry_fix"]["path"]).name,
            )
            self.assertEqual(HOTBATH_SHA256, result["hotbath_registry_fix"]["sha256"])
            self.assertEqual(gate.WORLD_EDIT_NAME, Path(result["worldedit_direction_property_fix"]["path"]).name)
            self.assertEqual(CEI_NAME, Path(result["cei_compatibility"]["path"]).name)
            self.assertEqual(gate.sha256(cei), result["cei_compatibility"]["sha256"])
            self.assertFalse(result["mcmodsync_active"])

    def test_accepts_exact_hotbath_lock_on_both_sides(self) -> None:
        for side in ("server", "client"):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, cei = prepare_side(root)

                result = self.validate(root, cei, side)

                self.assertEqual(gate.HOTBATH_NAME, Path(result["hotbath_registry_fix"]["path"]).name)
                self.assertEqual(HOTBATH_SHA256, result["hotbath_registry_fix"]["sha256"])
                self.assertEqual(gate.WORLD_EDIT_NAME, Path(result["worldedit_direction_property_fix"]["path"]).name)

    def test_rejects_an_additional_active_cei_jar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)
            (root / "mods" / "create-enchantment-industry-2.4.2.jar").write_bytes(b"old CEI")

            with self.assertRaisesRegex(gate.GateError, "CEI selection is not exactly"):
                self.validate(root, cei)

    def test_rejects_a_different_active_cei_jar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mineastr, cei = prepare_side(root)
            cei.unlink()
            old = root / "mods" / "create-enchantment-industry-2.4.2.jar"
            old.write_bytes(b"old CEI")

            with mock.patch.multiple(
                gate,
                MINEASTR_BYTES=mineastr.stat().st_size,
                MINEASTR_SHA256=gate.sha256(mineastr),
                YACL_BYTES=len(YACL_CONTENT),
                YACL_SHA256=gate.sha256(root / "mods" / gate.YACL_NAME),
                CONTENT_BACKPORT_BYTES=len(CONTENT_BACKPORT_CONTENT),
                CONTENT_BACKPORT_SHA256=gate.sha256(root / "mods" / gate.CONTENT_BACKPORT_NAME),
                HOTBATH_BYTES=len(HOTBATH_CONTENT),
                HOTBATH_SHA256=gate.sha256(root / "mods" / gate.HOTBATH_NAME),
                WORLD_EDIT_BYTES=len(WORLD_EDIT_CONTENT),
                WORLD_EDIT_SHA256=WORLD_EDIT_SHA256,
            ):
                with self.assertRaisesRegex(gate.GateError, "CEI selection is not exactly"):
                    gate.validate_side(
                        root,
                        "client",
                        CEI_NAME,
                        gate.sha256(old),
                        old.stat().st_size,
                    )

    def test_rejects_cei_hash_or_size_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mineastr, cei = prepare_side(root)
            with mock.patch.multiple(
                gate,
                MINEASTR_BYTES=mineastr.stat().st_size,
                MINEASTR_SHA256=gate.sha256(mineastr),
                YACL_BYTES=len(YACL_CONTENT),
                YACL_SHA256=gate.sha256(root / "mods" / gate.YACL_NAME),
                CONTENT_BACKPORT_BYTES=len(CONTENT_BACKPORT_CONTENT),
                CONTENT_BACKPORT_SHA256=gate.sha256(root / "mods" / gate.CONTENT_BACKPORT_NAME),
                HOTBATH_BYTES=len(HOTBATH_CONTENT),
                HOTBATH_SHA256=gate.sha256(root / "mods" / gate.HOTBATH_NAME),
                WORLD_EDIT_BYTES=len(WORLD_EDIT_CONTENT),
                WORLD_EDIT_SHA256=WORLD_EDIT_SHA256,
            ):
                with self.assertRaisesRegex(gate.GateError, "hash/size mismatch"):
                    gate.validate_side(root, "server", CEI_NAME, "0" * 64, cei.stat().st_size)
                with self.assertRaisesRegex(gate.GateError, "hash/size mismatch"):
                    gate.validate_side(root, "server", CEI_NAME, gate.sha256(cei), cei.stat().st_size + 1)

    def test_rejects_mcmodsync_even_when_cei_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)
            (root / "mods" / "MCModSync-1.0.0.jar").write_bytes(b"disabled in production")

            with self.assertRaisesRegex(gate.GateError, "MCModSync must remain disabled"):
                self.validate(root, cei)

    def test_rejects_missing_server_yacl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)
            (root / "mods" / gate.YACL_NAME).unlink()

            with self.assertRaisesRegex(gate.GateError, "YACL selection is not exactly"):
                self.validate(root, cei)

    def test_rejects_unpatched_content_backport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)
            (root / "mods" / gate.CONTENT_BACKPORT_NAME).unlink()
            (root / "mods" / "backport-1.5.jar").write_bytes(b"unsafe original")

            with self.assertRaisesRegex(gate.GateError, "Content Backport selection is not exactly"):
                self.validate(root, cei)

    def test_rejects_original_hotbath_instead_of_registry_fix(self) -> None:
        for side in ("server", "client"):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, cei = prepare_side(root)
                (root / "mods" / gate.HOTBATH_NAME).unlink()
                (root / "mods" / "hotbath-1.21.1-3.0.0.jar").write_bytes(b"unsafe original")

                with self.assertRaisesRegex(gate.GateError, "Hot Bath selection is not exactly"):
                    self.validate(root, cei, side)

    def test_rejects_original_worldedit_instead_of_direction_property_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)
            (root / "mods" / gate.WORLD_EDIT_NAME).unlink()
            (root / "mods" / "worldedit-mod-7.3.8.jar").write_bytes(b"unsafe original")
            with self.assertRaisesRegex(gate.GateError, "WorldEdit direction-property fix selection"):
                self.validate(root, cei)

    def test_rejects_an_additional_active_hotbath_jar(self) -> None:
        for side in ("server", "client"):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, cei = prepare_side(root)
                (root / "mods" / "hotbath-1.21.1-3.0.0.jar").write_bytes(b"unsafe original")

                with self.assertRaisesRegex(gate.GateError, "Hot Bath selection is not exactly"):
                    self.validate(root, cei, side)

    def test_rejects_hotbath_hash_or_size_mismatch_on_both_sides(self) -> None:
        for side in ("server", "client"):
            with self.subTest(side=side), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, cei = prepare_side(root)
                hotbath = root / "mods" / gate.HOTBATH_NAME
                with mock.patch.multiple(
                    gate,
                    MINEASTR_BYTES=len(MINEASTR_CONTENT),
                    MINEASTR_SHA256=gate.sha256(root / "mods" / gate.MINEASTR_NAME),
                    YACL_BYTES=len(YACL_CONTENT),
                    YACL_SHA256=gate.sha256(root / "mods" / gate.YACL_NAME),
                    CONTENT_BACKPORT_BYTES=len(CONTENT_BACKPORT_CONTENT),
                    CONTENT_BACKPORT_SHA256=gate.sha256(root / "mods" / gate.CONTENT_BACKPORT_NAME),
                    HOTBATH_BYTES=len(HOTBATH_CONTENT),
                    HOTBATH_SHA256="0" * 64,
                    WORLD_EDIT_BYTES=len(WORLD_EDIT_CONTENT),
                    WORLD_EDIT_SHA256=WORLD_EDIT_SHA256,
                ):
                    with self.assertRaisesRegex(gate.GateError, "Hot Bath registry fix hash/size mismatch"):
                        gate.validate_side(root, side, CEI_NAME, gate.sha256(cei), cei.stat().st_size)
                with mock.patch.multiple(
                    gate,
                    MINEASTR_BYTES=len(MINEASTR_CONTENT),
                    MINEASTR_SHA256=gate.sha256(root / "mods" / gate.MINEASTR_NAME),
                    YACL_BYTES=len(YACL_CONTENT),
                    YACL_SHA256=gate.sha256(root / "mods" / gate.YACL_NAME),
                    CONTENT_BACKPORT_BYTES=len(CONTENT_BACKPORT_CONTENT),
                    CONTENT_BACKPORT_SHA256=gate.sha256(root / "mods" / gate.CONTENT_BACKPORT_NAME),
                    HOTBATH_BYTES=hotbath.stat().st_size + 1,
                    HOTBATH_SHA256=gate.sha256(hotbath),
                    WORLD_EDIT_BYTES=len(WORLD_EDIT_CONTENT),
                    WORLD_EDIT_SHA256=WORLD_EDIT_SHA256,
                ):
                    with self.assertRaisesRegex(gate.GateError, "Hot Bath registry fix hash/size mismatch"):
                        gate.validate_side(root, side, CEI_NAME, gate.sha256(cei), cei.stat().st_size)

    def test_rejects_invalid_cei_contract_arguments_before_artifact_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, cei = prepare_side(root)
            with self.assertRaisesRegex(gate.GateError, "invalid CEI compatibility JAR name"):
                gate.validate_side(root, "server", "../" + CEI_NAME, gate.sha256(cei), cei.stat().st_size)
            with self.assertRaisesRegex(gate.GateError, "64 hexadecimal"):
                gate.validate_side(root, "server", CEI_NAME, "not-a-sha256", cei.stat().st_size)
            with self.assertRaisesRegex(gate.GateError, "byte count must be positive"):
                gate.validate_side(root, "server", CEI_NAME, gate.sha256(cei), 0)

    def test_cei_lock_arguments_are_required_by_cli(self) -> None:
        args = [
            "--runtime", "runtime",
            "--client", "client",
            "--report", "report.json",
            "--artifacts", "artifacts",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                gate.parser().parse_args(args)

    def test_command_plan_loads_and_visits_both_existing_blaze_forgers(self) -> None:
        plan = gate.command_plan()
        for site in gate.CEI_FORGER_RISK_SITES:
            self.assertIn(
                {
                    "kind": "forceload",
                    "site": site["name"],
                    "command": f"forceload add {site['x']} {site['z']}",
                },
                plan,
            )
            self.assertIn(
                {
                    "kind": "teleport",
                    "site": site["name"],
                    "command": f"tp {gate.legacy.SYNTHETIC_USERNAME} {site['x']} {site['y']} {site['z']}",
                },
                plan,
            )
        self.assertEqual("save", plan[-1]["kind"])

    def test_pre_client_server_error_check_runs_before_client_allocation(self) -> None:
        source = inspect.getsource(gate.run)
        self.assertLess(
            source.index("assert_server_clean_before_client(before)"),
            source.index("legacy.PrivateClientSession("),
        )

    def test_pre_client_server_error_check_rejects_unallowlisted_server_thread_error(self) -> None:
        line = (
            "[14Aug2026 13:39:30.977] [Server thread/ERROR] "
            "[example/Test]: deterministic pre-client failure"
        )
        with self.assertRaisesRegex(gate.GateError, "Mechanomania server pre-client"):
            gate.assert_server_clean_before_client(line)

    def test_server_error_audit_accepts_only_bounded_known_loader_diagnostics(self) -> None:
        lines = [
            "[14Aug2026 13:39:30.977] [pool-2-thread-2/ERROR] "
            "[org.sinytra.connector.transformer.transform.RefmapRemapper/]: Error opening jar file",
            r"java.nio.file.NoSuchFileException: \~nonexistent",
            "[14Aug2026 13:39:31.000] [main/ERROR] "
            "[net.neoforged.fml.common.asm.RuntimeDistCleaner/DISTXFORM]: "
            "Attempted to load class net/minecraft/client/Options for invalid dist DEDICATED_SERVER",
        ]

        audit = gate.assert_server_clean_before_client("\n".join(lines))

        self.assertEqual(2, audit["error_line_count"])
        self.assertEqual(1, audit["refmap_nonexistent_probe"])
        self.assertEqual(0, audit["unreviewed_error_count"])

    def test_server_error_audit_rejects_refmap_cause_drift(self) -> None:
        text = "\n".join(
            [
                "[14Aug2026 13:39:30.977] [pool-2-thread-2/ERROR] "
                "[org.sinytra.connector.transformer.transform.RefmapRemapper/]: Error opening jar file",
                "java.nio.file.NoSuchFileException: real-mod.jar",
            ]
        )
        with self.assertRaisesRegex(gate.GateError, "RefmapRemapper diagnostic drift"):
            gate.assert_server_clean_before_client(text)

    def test_server_error_audit_rejects_runtime_dist_cleaner_count_growth(self) -> None:
        message = (
            "[14Aug2026 13:39:31.000] [main/ERROR] "
            "[net.neoforged.fml.common.asm.RuntimeDistCleaner/DISTXFORM]: "
            "Attempted to load class net/minecraft/client/Options for invalid dist DEDICATED_SERVER"
        )
        with self.assertRaisesRegex(gate.GateError, "count exceeded audited maximum"):
            gate.assert_server_clean_before_client("\n".join([message, message]))

    def test_controlled_connection_reset_is_allowed_only_in_final_audit(self) -> None:
        text = "\n".join(
            [
                "[14Aug2026 13:39:31.000] [Netty Acceptor IO Thread/ERROR] "
                "[net.minecraft.network.Connection/]: Exception caught in connection",
                "java.net.SocketException: Connection reset",
            ]
        )
        with self.assertRaisesRegex(gate.GateError, "unreviewed server ERROR"):
            gate.audit_server_errors(text, "pre-stop")
        audit = gate.audit_server_errors(text, "final", allow_controlled_disconnect=True)
        self.assertEqual(1, audit["controlled_disconnect"])


class Attempt10RepairLockTests(unittest.TestCase):
    def test_attempt11_followup_report_rehashes_the_installed_state(self) -> None:
        runtime = Path(
            r"<AUDIT_ROOT>\mechanomania-matched-runtime-attempt11-20260814"
        ).resolve()
        client = Path(
            r"<AUDIT_ROOT>\mechanomania-matched-client-attempt11-20260814"
        ).resolve()
        report = Path(
            r"<AUDIT_ROOT>\attempt11-followup-fixes-postverify-20260814.json"
        )
        result = gate.validate_followup_repair_report(
            report,
            gate.FOLLOWUP_REPAIR_REPORT_SHA256,
            runtime,
            client,
        )
        self.assertEqual("PASS_LOCKED_AND_REHASHED", result["status"])
        self.assertEqual(6, result["installed_target_count"])
        self.assertTrue(result["debug_loot_absent"])
        self.assertTrue(result["mcmodsync_globally_disabled"])

    def test_attempt11_followup_rejects_an_unlocked_report_sha(self) -> None:
        with self.assertRaisesRegex(gate.GateError, "not the built-in audited lock"):
            gate.validate_followup_repair_report(
                Path(
                    r"<AUDIT_ROOT>\attempt11-followup-fixes-postverify-20260814.json"
                ),
                "0" * 64,
                Path(
                    r"<AUDIT_ROOT>\mechanomania-matched-runtime-attempt11-20260814"
                ).resolve(),
                Path(
                    r"<AUDIT_ROOT>\mechanomania-matched-client-attempt11-20260814"
                ).resolve(),
            )

    def test_accepts_and_rehashes_all_29_data_resource_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, byte_locks = prepare_data_repair_fixture(Path(temporary))
            report_sha = gate.sha256(report)
            with mock.patch.multiple(
                gate,
                DATA_REPAIR_REPORT_SHA256=report_sha,
                DATA_REPAIR_OUTPUT_BYTES=byte_locks,
            ):
                result = gate.validate_data_resource_repair_report(
                    report,
                    report_sha.lower(),
                    server.resolve(),
                    client.resolve(),
                )
            self.assertEqual("PASS_LOCKED_AND_REHASHED", result["status"])
            self.assertEqual(18, result["source_rows"])
            self.assertEqual(29, result["target_operations"])
            self.assertEqual({"jar": 22, "loose": 7}, result["operations_by_kind"])
            self.assertEqual({"client": 11, "server": 18}, result["operations_by_side"])
            self.assertTrue(all(row["artifact"]["bytes"] > 0 for row in result["installed_targets"]))

    def test_rejects_a_mutated_data_resource_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, byte_locks = prepare_data_repair_fixture(Path(temporary))
            report_sha = gate.sha256(report)
            (client / "mods" / "fixture-fix-0.jar").write_bytes(b"mutated")
            with mock.patch.multiple(
                gate,
                DATA_REPAIR_REPORT_SHA256=report_sha,
                DATA_REPAIR_OUTPUT_BYTES=byte_locks,
            ):
                with self.assertRaisesRegex(gate.GateError, "hash/size mismatch"):
                    gate.validate_data_resource_repair_report(
                        report,
                        report_sha,
                        server.resolve(),
                        client.resolve(),
                    )

    def test_explicit_followup_supersession_is_narrow_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, byte_locks = prepare_data_repair_fixture(Path(temporary))
            report_sha = gate.sha256(report)
            superseded = "fixture-fix-0.jar"
            (server / "mods" / superseded).write_bytes(b"locked followup replacement")
            (client / "mods" / superseded).write_bytes(b"locked followup replacement")
            with mock.patch.multiple(
                gate,
                DATA_REPAIR_REPORT_SHA256=report_sha,
                DATA_REPAIR_OUTPUT_BYTES=byte_locks,
            ):
                result = gate.validate_data_resource_repair_report(
                    report,
                    report_sha,
                    server.resolve(),
                    client.resolve(),
                    superseded_relatives=frozenset({superseded}),
                )
            self.assertEqual("PASS_LOCKED_WITH_EXPLICIT_SUPERSESSION", result["status"])
            self.assertEqual([superseded], result["superseded_relatives"])
            affected = [
                row for row in result["installed_targets"] if row["relative"] == superseded
            ]
            self.assertEqual(2, len(affected))
            self.assertTrue(
                all(row["state"] == "SUPERSEDED_BY_LOCKED_FOLLOWUP" for row in affected)
            )

    def test_rejects_an_unlocked_data_resource_report_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, byte_locks = prepare_data_repair_fixture(Path(temporary))
            report_sha = gate.sha256(report)
            with mock.patch.multiple(
                gate,
                DATA_REPAIR_REPORT_SHA256=report_sha,
                DATA_REPAIR_OUTPUT_BYTES=byte_locks,
            ):
                with self.assertRaisesRegex(gate.GateError, "not the built-in audited lock"):
                    gate.validate_data_resource_repair_report(
                        report,
                        "0" * 64,
                        server.resolve(),
                        client.resolve(),
                    )

    def validate_content_fixture(self, server: Path, client: Path, report: Path, locks: dict) -> dict:
        report_sha = gate.sha256(report)
        with mock.patch.multiple(
            gate,
            CONTENT_REPAIR_REPORT_SHA256=report_sha,
            **locks,
        ):
            return gate.validate_content_repair_report(
                report,
                report_sha,
                server.resolve(),
                client.resolve(),
            )

    def test_accepts_yuushya_both_tlm_unchanged_client_overlays_and_maid_js(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, locks = prepare_content_repair_fixture(Path(temporary))
            result = self.validate_content_fixture(server, client, report, locks)
            self.assertEqual("PASS_LOCKED_AND_REHASHED", result["status"])
            self.assertEqual(7, result["installed_target_count"])
            self.assertTrue(result["policy"]["maid_js_unchanged"])
            self.assertTrue(result["mcmodsync"]["server"]["globally_disabled"])
            self.assertTrue(result["mcmodsync"]["client"]["globally_disabled"])

    def test_rejects_mutated_server_maid_js(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, locks = prepare_content_repair_fixture(Path(temporary))
            server.joinpath(*PurePosixPath(gate.MAID_JS_RELATIVE).parts).write_bytes(b"recipe restored")
            with self.assertRaisesRegex(gate.GateError, "unchanged server maid.js"):
                self.validate_content_fixture(server, client, report, locks)

    def test_rejects_mcmodsync_anywhere_under_either_side(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            server, client, report, locks = prepare_content_repair_fixture(Path(temporary))
            forbidden = client / "config" / "MCModSync-client.toml"
            forbidden.parent.mkdir()
            forbidden.write_text("enabled=false\n", encoding="utf-8")
            with self.assertRaisesRegex(gate.GateError, "globally absent"):
                self.validate_content_fixture(server, client, report, locks)

    def test_cli_requires_both_attempt10_report_locks(self) -> None:
        common = [
            "--runtime", "runtime",
            "--client", "client",
            "--report", "report.json",
            "--artifacts", "artifacts",
            "--cei-name", CEI_NAME,
            "--cei-sha256", "0" * 64,
            "--cei-bytes", "1",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                gate.parser().parse_args(common)
        parsed = gate.parser().parse_args(
            common
            + [
                "--data-repair-report", "data.json",
                "--data-repair-report-sha256", gate.DATA_REPAIR_REPORT_SHA256,
                "--content-repair-report", "content.json",
                "--content-repair-report-sha256", gate.CONTENT_REPAIR_REPORT_SHA256,
                "--followup-repair-report", "followup.json",
                "--followup-repair-report-sha256", gate.FOLLOWUP_REPAIR_REPORT_SHA256,
            ]
        )
        self.assertEqual(Path("data.json"), parsed.data_repair_report)
        self.assertEqual(Path("content.json"), parsed.content_repair_report)
        self.assertEqual(Path("followup.json"), parsed.followup_repair_report)

    def test_repair_locks_run_before_attempt_claim_or_java_sessions(self) -> None:
        source = inspect.getsource(gate.run)
        self.assertLess(source.index("validate_data_resource_repair_report("), source.index("claim_attempt(runtime)"))
        self.assertLess(source.index("validate_content_repair_report("), source.index("claim_attempt(runtime)"))
        self.assertLess(source.index("validate_followup_repair_report("), source.index("claim_attempt(runtime)"))
        self.assertLess(source.index("validate_content_repair_report("), source.index("legacy.ServerSession("))
        self.assertLess(source.index("validate_followup_repair_report("), source.index("legacy.ServerSession("))


if __name__ == "__main__":
    unittest.main()
