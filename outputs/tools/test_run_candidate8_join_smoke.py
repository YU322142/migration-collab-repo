from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile


MODULE_PATH = Path(__file__).with_name("run_candidate8_join_smoke.py")
SPEC = importlib.util.spec_from_file_location("run_candidate8_join_smoke", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class Candidate10JoinSmokeTest(unittest.TestCase):
    def test_candidate10_identity_is_frozen(self) -> None:
        self.assertEqual(smoke.SYNTHETIC_USERNAME, "Candidate10Gate")
        self.assertEqual(
            smoke.SYNTHETIC_UUID, "00000000-0000-0000-0000-000000001001"
        )

    def test_command_plan_is_exact_and_save_is_last(self) -> None:
        commands = [value["command"] for value in smoke.command_plan()]
        self.assertEqual(
            commands,
            [
                "forceload add -159 -42",
                "forceload add -165 -92",
                "forceload add 1414 -5102",
                "forceload add 27319 -12919",
                "tp Candidate10Gate -159 65 -42",
                "tp Candidate10Gate -165 65 -92",
                "tp Candidate10Gate 1414 66 -5102",
                "tp Candidate10Gate 27319 70 -12919",
                "save-all flush",
            ],
        )

    def test_all_candidate7_failure_markers_are_blockers(self) -> None:
        examples = {
            "WHITELIST_REJECTION": "You are not white-listed on this server!",
            "FLUID_MAX_CAPACITY_COMPONENT": (
                "No component with type: 'create:fluid_max_capacity'"
            ),
            "UNKNOWN_CREATE_MILK": "Unknown registry key in ResourceKey create:milk",
            "INVALID_FLUID": "Tried to load invalid fluid from disk",
            "INVALID_STATISTIC": (
                "Invalid statistic in stats/player.json: Don't know what "
                "minecraft:happy_ghast_one_cm is"
            ),
            "FLUIDSTACK_FAILURE": "Failed to decode FluidStack",
            "CONTRAPTION_BOUNDS": "No key Contraption.bounds in MapLike",
            "ASSEMBLY_EXCEPTION": "create:elevator_pulley AssemblyException codec",
            "ENTITY_LOAD_EXCEPTION": "Exception loading entity create:stationary_contraption",
            "MILLSTONE_CODEC_FAILURE": (
                "kaleidoscope_cookery:millstone codec expected UUID IntArray"
            ),
            "ELEVATOR_CODEC_FAILURE": (
                "create:elevator_pulley failed to decode LastException"
            ),
        }
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                names = {value["marker"] for value in smoke.strict_marker_hits(text)}
                self.assertIn(expected, names)

    def test_client_fatal_is_scoped_to_client_scan(self) -> None:
        text = '[Render thread/FATAL] Minecraft has crashed\n'
        server_names = {value["marker"] for value in smoke.strict_marker_hits(text)}
        client_names = {
            value["marker"] for value in smoke.strict_marker_hits(text, client=True)
        }
        self.assertNotIn("CLIENT_RENDER_FATAL", server_names)
        self.assertIn("CLIENT_RENDER_FATAL", client_names)
        self.assertIn("CLIENT_GAME_CRASH", client_names)

    def test_client_resource_pack_failures_and_remote_activity_are_blockers(self) -> None:
        examples = {
            "CLIENT_RESOURCE_PACK_REMOVED": (
                "[Render thread/WARN] Removed resource pack file/world.zip from "
                "options because it doesn't seem to exist anymore"
            ),
            "CLIENT_RESOURCE_PACK_FAILURE": "Failed to apply resource pack world.zip",
            "CLIENT_REMOTE_RESOURCE_PACK_ACTIVITY": (
                "Downloading server resource pack from https://example.invalid/pack.zip"
            ),
        }
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                names = {
                    value["marker"]
                    for value in smoke.strict_marker_hits(text, client=True)
                }
                self.assertIn(expected, names)

    def test_known_harmless_warning_does_not_trip_strict_scan(self) -> None:
        text = (
            "[Server thread/WARN] Can't keep up! Is the server overloaded?\n"
            "[Render thread/WARN] Missing optional resource pack metadata\n"
        )
        self.assertEqual(smoke.strict_marker_hits(text, client=True), [])

    def test_candidate8g4_server_data_errors_are_strict_blockers(self) -> None:
        g4_log = (
            MODULE_PATH.parents[1]
            / "candidate8g4-join-smoke-20260811-artifacts-20260811T075739Z"
            / "server-round1.latest.log"
        )
        self.assertTrue(g4_log.is_file(), f"Candidate8g4 evidence missing: {g4_log}")
        hits = smoke.strict_marker_hits(g4_log.read_text(encoding="utf-8"))
        by_name = {value["marker"]: value for value in hits}
        self.assertEqual(by_name["UNALLOWLISTED_SERVER_THREAD_ERROR"]["count"], 8)
        self.assertEqual(by_name["INVALID_ITEM_LOAD"]["count"], 6)
        self.assertEqual(by_name["BLOCK_ENTITY_DATA_LOAD_FAILURE"]["count"], 2)

    def test_candidate8g4_removed_local_pack_is_a_strict_client_blocker(self) -> None:
        client_log = (
            MODULE_PATH.parents[1]
            / "candidate8g4-join-smoke-20260811-artifacts-20260811T075739Z"
            / "client-round1.stdout.log"
        )
        self.assertTrue(client_log.is_file(), f"Candidate8g4 evidence missing: {client_log}")
        names = {
            value["marker"]
            for value in smoke.strict_marker_hits(
                client_log.read_text(encoding="utf-8", errors="replace"), client=True
            )
        }
        self.assertIn("CLIENT_RESOURCE_PACK_REMOVED", names)

    def test_new_server_data_loss_markers_block_without_thread_prefix(self) -> None:
        examples = {
            "INVALID_ITEM_LOAD": "Tried to load invalid item: bad components",
            "BLOCK_ENTITY_DATA_LOAD_FAILURE": (
                "Failed to load data for block entity create:basin"
            ),
            "SKIPPED_BLOCK_ENTITY": "Skipping BlockEntity with id create:basin",
            "COMPONENT_LOAD_FAILURE": "Failed to load components for stack",
        }
        for expected, text in examples.items():
            with self.subTest(expected=expected):
                names = {value["marker"] for value in smoke.strict_marker_hits(text)}
                self.assertIn(expected, names)

    def test_join_and_disconnect_counters_are_identity_specific(self) -> None:
        text = (
            "Candidate10Gate joined the game\n"
            "SomeoneElse joined the game\n"
            "Candidate10Gate lost connection: Disconnected\n"
        )
        self.assertEqual(smoke.joined_count(text), 1)
        self.assertEqual(smoke.lost_count(text), 1)

    def test_save_response_is_strict(self) -> None:
        smoke.validate_command_response("save-all flush", "Saved the game")
        with self.assertRaisesRegex(smoke.GateError, "confirm persistence"):
            smoke.validate_command_response("save-all flush", "Saving is disabled")
        with self.assertRaisesRegex(smoke.GateError, "RCON command failed"):
            smoke.validate_command_response(
                "tp Candidate10Gate 0 64 0", "No player was found"
            )

    def test_whitelist_normalization_is_atomic_and_removes_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "server.properties"
            path.write_text(
                "server-ip=127.0.0.1\nwhite-list=true\n# keep\n"
                "white-list=false\nenforce-whitelist=true\n",
                encoding="utf-8",
            )
            result = smoke.normalize_disposable_whitelist(path)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(result["changed"])
            self.assertEqual(text.count("white-list="), 1)
            self.assertEqual(text.count("enforce-whitelist="), 1)
            self.assertIn("white-list=false", text)
            self.assertIn("enforce-whitelist=false", text)
            properties = smoke.read_properties(path)
            self.assertEqual(properties["white-list"], "false")
            self.assertEqual(properties["enforce-whitelist"], "false")

    def test_server_property_gate_requires_loopback_ports_and_no_whitelist(self) -> None:
        properties = {
            "server-ip": "127.0.0.1",
            "server-port": "12341",
            "enable-rcon": "true",
            "rcon.port": "12342",
            "rcon.password": "synthetic-secret",
            "online-mode": "false",
            "white-list": "false",
            "enforce-whitelist": "false",
            "level-name": "world",
        }
        smoke.validate_server_properties(properties, 12341, 12342)
        properties["server-ip"] = ""
        with self.assertRaisesRegex(smoke.GateError, "mismatched"):
            smoke.validate_server_properties(properties, 12341, 12342)

    def test_resource_pack_policy_writes_and_validates_declined_server_entry(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            client_root = Path(raw) / ".minecraft"
            client_root.mkdir()
            servers_dat = client_root / "servers.dat"
            servers_dat.write_bytes(b"previous server list")
            properties_path = Path(raw) / "server.properties"
            properties_path.write_text(
                "resource-pack=https\\://example.invalid/pack.zip\n"
                "require-resource-pack=false\n",
                encoding="utf-8",
            )
            properties_before = properties_path.read_bytes()
            properties = smoke.read_properties(properties_path)

            result = smoke.configure_disposable_resource_pack_rejection(
                client_root, 12341, properties, properties_path
            )

            expected = smoke.candidate8_servers_dat_payload("127.0.0.1:12341")
            self.assertEqual(servers_dat.read_bytes(), expected)
            self.assertIn(b"\x01\x00\x0eacceptTextures\x00", expected)
            self.assertEqual(result["policy"], "reject_optional")
            self.assertEqual(result["client_response"], "DECLINED")
            self.assertFalse(result["accept_textures"])
            self.assertTrue(result["servers_dat"]["changed"])
            self.assertTrue(result["servers_dat"]["exact_payload_validated"])
            self.assertEqual(properties_path.read_bytes(), properties_before)
            self.assertTrue(result["server_properties"]["unchanged"])

            second = smoke.configure_disposable_resource_pack_rejection(
                client_root, 12341, properties, properties_path
            )
            self.assertFalse(second["servers_dat"]["changed"])
            self.assertEqual(
                second["servers_dat"]["before"]["sha256"],
                second["servers_dat"]["after"]["sha256"],
            )
            validation = smoke.validate_disposable_resource_pack_rejection(
                client_root,
                12341,
                properties_path,
                expected_properties_sha256=second["server_properties"][
                    "after_sha256"
                ],
                expected_properties_fingerprint=second["server_properties"][
                    "semantic_fingerprint"
                ],
            )
            self.assertTrue(validation["exact_payload_validated"])
            self.assertEqual(validation["client_response"], "DECLINED")
            self.assertFalse(validation["accept_textures"])

            servers_dat.write_bytes(b"accepted or unknown")
            with self.assertRaisesRegex(smoke.GateError, "acceptTextures=false"):
                smoke.validate_disposable_resource_pack_rejection(
                    client_root,
                    12341,
                    properties_path,
                    expected_properties_sha256=second["server_properties"][
                        "after_sha256"
                    ],
                    expected_properties_fingerprint=second["server_properties"][
                        "semantic_fingerprint"
                    ],
                )

    def test_server_resource_pack_rejection_allows_java_format_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            client_root = Path(raw) / ".minecraft"
            client_root.mkdir()
            properties_path = Path(raw) / "server.properties"
            properties_path.write_text(
                "resource-pack=https\\://example.invalid/pack.zip\n"
                "require-resource-pack=false\n"
                "server-ip=127.0.0.1\n"
                "server-port=12341\n"
                "online-mode=false\n"
                "white-list=false\n"
                "enforce-whitelist=false\n"
                "enable-rcon=true\n"
                "rcon.port=12342\n"
                "rcon.password=secret\n"
                "level-name=world\n",
                encoding="utf-8",
            )
            properties = smoke.read_properties(properties_path)
            setup = smoke.configure_disposable_resource_pack_rejection(
                client_root, 12341, properties, properties_path
            )
            properties_path.write_text(
                "# normalized by java.util.Properties\n"
                "motd=added default\n"
                "level-name=world\n"
                "rcon.password=secret\n"
                "rcon.port=12342\n"
                "enable-rcon=true\n"
                "enforce-whitelist=false\n"
                "white-list=false\n"
                "online-mode=false\n"
                "server-port=12341\n"
                "server-ip=127.0.0.1\n"
                "require-resource-pack=false\n"
                "resource-pack=https\\://example.invalid/pack.zip\n",
                encoding="utf-8",
            )
            validation = smoke.validate_disposable_resource_pack_rejection(
                client_root,
                12341,
                properties_path,
                expected_properties_sha256=setup["server_properties"][
                    "after_sha256"
                ],
                expected_properties_fingerprint=setup["server_properties"][
                    "semantic_fingerprint"
                ],
            )
            self.assertTrue(validation["server_properties"]["semantic_unchanged"])
            self.assertTrue(
                validation["server_properties"]["raw_normalized_by_server"]
            )

    def test_server_resource_pack_rejection_detects_protected_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            client_root = Path(raw) / ".minecraft"
            client_root.mkdir()
            properties_path = Path(raw) / "server.properties"
            properties_path.write_text(
                "resource-pack=https\\://example.invalid/pack.zip\n"
                "require-resource-pack=false\n",
                encoding="utf-8",
            )
            properties = smoke.read_properties(properties_path)
            setup = smoke.configure_disposable_resource_pack_rejection(
                client_root, 12341, properties, properties_path
            )
            properties_path.write_text(
                "resource-pack=https\\://attacker.invalid/pack.zip\n"
                "require-resource-pack=false\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(smoke.GateError, "protected values changed"):
                smoke.validate_disposable_resource_pack_rejection(
                    client_root,
                    12341,
                    properties_path,
                    expected_properties_sha256=setup["server_properties"][
                        "after_sha256"
                    ],
                    expected_properties_fingerprint=setup["server_properties"][
                        "semantic_fingerprint"
                    ],
                )

    def test_resource_pack_policy_refuses_required_pack_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            client_root = Path(raw) / ".minecraft"
            client_root.mkdir()
            servers_dat = client_root / "servers.dat"
            servers_dat.write_bytes(b"keep me")
            properties_path = Path(raw) / "server.properties"
            properties_path.write_text(
                "resource-pack=https\\://example.invalid/pack.zip\n"
                "require-resource-pack=true\n",
                encoding="utf-8",
            )
            properties = smoke.read_properties(properties_path)
            with self.assertRaisesRegex(smoke.GateError, "pack is required"):
                smoke.configure_disposable_resource_pack_rejection(
                    client_root, 12341, properties, properties_path
                )
            self.assertEqual(servers_dat.read_bytes(), b"keep me")

    def test_exact_local_world_pack_is_copied_enabled_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            client_root = root / ".minecraft"
            client_root.mkdir()
            (client_root / "options.txt").write_text(
                'resourcePacks:["fabric"]\nincompatibleResourcePacks:[]\n',
                encoding="utf-8",
            )
            source = root / "bound-pack.zip"
            source_mcmeta = (
                b'{\r\n  "pack": {\r\n'
                b'    "min_format": 1,\r\n'
                b'    "max_format": 9999,\r\n'
                b'    "description": "bound"\r\n'
                b'  }\r\n}\r\n'
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", source_mcmeta)
                archive.writestr("assets/example/value.txt", "value")
            expected_sha = smoke.sha256_file(source)
            expected_bytes = source.stat().st_size
            filename = "\u4e16\u754c\u6307\u5b9a\u8d44\u6e90\u5305\u55b5.zip"

            result = smoke.configure_local_world_resource_pack(
                client_root,
                source=source,
                filename=filename,
                expected_sha256=expected_sha,
                expected_bytes=expected_bytes,
                expected_zip_entries=2,
            )

            destination = client_root / "resourcepacks" / filename
            self.assertNotEqual(smoke.sha256_file(destination), expected_sha)
            self.assertEqual(smoke.sha256_file(source), expected_sha)
            self.assertEqual(
                smoke.resource_packs_option(client_root / "options.txt"),
                ["fabric", f"file/{filename}"],
            )
            self.assertTrue((client_root / "options.txt").read_bytes().isascii())
            with zipfile.ZipFile(destination) as archive:
                expected_mcmeta = source_mcmeta.replace(
                    b'"pack": {\r\n    ',
                    b'"pack": {\r\n    "pack_format": 34,\r\n    ',
                    1,
                )
                self.assertEqual(archive.read("pack.mcmeta"), expected_mcmeta)
                self.assertEqual(archive.read("assets/example/value.txt"), b"value")
            self.assertTrue(result["destination"]["changed"])
            self.assertTrue(result["options"]["changed"])
            self.assertTrue(result["enabled_exactly_once"])
            self.assertTrue(result["source"]["unchanged"])
            self.assertTrue(
                result["derivation"]["non_metadata_content_unchanged"]
            )
            self.assertEqual(result["derivation"]["non_metadata_entries"], 1)
            self.assertEqual(
                result["derivation"]["added_field"],
                {"name": "pack_format", "value": 34},
            )

            second = smoke.configure_local_world_resource_pack(
                client_root,
                source=source,
                filename=filename,
                expected_sha256=expected_sha,
                expected_bytes=expected_bytes,
                expected_zip_entries=2,
            )
            self.assertFalse(second["destination"]["changed"])
            self.assertFalse(second["options"]["changed"])
            self.assertEqual(
                second["options"]["selected_after"].count(f"file/{filename}"), 1
            )

    def test_resource_pack_content_manifest_detects_non_metadata_change(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "first.zip"
            second = root / "second.zip"
            for path, payload in ((first, b"one"), (second, b"two")):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(
                        "pack.mcmeta", '{"pack":{"pack_format":34}}'
                    )
                    archive.writestr("assets/example/value.txt", payload)
            first_evidence = smoke.resource_pack_zip_evidence(first, 2)
            second_evidence = smoke.resource_pack_zip_evidence(second, 2)
            self.assertNotEqual(
                first_evidence["non_metadata_content_manifest_sha256"],
                second_evidence["non_metadata_content_manifest_sha256"],
            )

    def test_local_world_pack_hash_mismatch_does_not_mutate_client(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            client_root = root / ".minecraft"
            client_root.mkdir()
            options = client_root / "options.txt"
            options.write_text('resourcePacks:["fabric"]\n', encoding="utf-8")
            before = options.read_bytes()
            source = root / "wrong.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("pack.mcmeta", "{}")
            with self.assertRaisesRegex(smoke.GateError, "source hash/size mismatch"):
                smoke.configure_local_world_resource_pack(
                    client_root,
                    source=source,
                    filename="world-pack.zip",
                    expected_sha256="0" * 64,
                    expected_bytes=source.stat().st_size,
                    expected_zip_entries=1,
                )
            self.assertEqual(options.read_bytes(), before)
            self.assertFalse((client_root / "resourcepacks").exists())

    def test_prepare_report_must_bind_target_and_ports(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "candidate8"
            target.mkdir()
            report = root / "prepare.json"
            value = {
                "status": "PREPARED",
                "output": str(target),
                "ports": {"server": 12341, "rcon": 12342, "voice": 26341},
                "network_safety": {
                    "server_bind": "127.0.0.1",
                    "online_mode": False,
                    "mineastr_enabled": False,
                },
            }
            report.write_text(json.dumps(value), encoding="utf-8")
            binding = smoke.validate_prepare_report(
                report, target, 12341, 12342, 26341
            )
            self.assertEqual(binding["status"], "PREPARED")
            value["ports"]["rcon"] = 12343
            report.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(smoke.GateError, "port binding"):
                smoke.validate_prepare_report(report, target, 12341, 12342, 26341)

    def test_client_prepare_report_binds_identity_root_and_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            client_root = root / "client"
            for name in (
                "assets",
                "config",
                "data",
                "defaultconfigs",
                "libraries",
                "mods",
                "natives",
                "resourcepacks",
                "versions",
            ):
                (client_root / name).mkdir(parents=True)
            options_path = client_root / "options.txt"
            options_path.write_text('resourcePacks:["fabric"]\n', encoding="utf-8")
            bundle = {
                "root": str((client_root / "mods").resolve()),
                "files": 50,
                "bytes": 123,
                "bundle_sha256": "A" * 64,
            }
            report = root / "client-prepare.json"
            value = {
                "status": "PREPARED",
                "output_root": str(client_root),
                "source_unchanged": True,
                "saves_logs_caches_absent": True,
                "forbidden_runtime_state_found": [],
                "candidate8_root_read_or_written": False,
                "java_started": False,
                "historical_backup_accessed": False,
                "copied_non_world_client_state": {
                    "options.txt": {
                        "files": 1,
                        "bytes": options_path.stat().st_size,
                        "sha256": smoke.sha256_file(options_path),
                    }
                },
                "offline_identity": {
                    "username": smoke.SYNTHETIC_USERNAME,
                    "uuid": smoke.SYNTHETIC_UUID,
                    "inherited_account_cache": False,
                },
                "client_bundle": {
                    "destination": str(client_root / "mods"),
                    "file_count": 50,
                    "bytes": 123,
                    "bundle_sha256": "A" * 64,
                    "exact_manifest_match": True,
                },
            }
            report.write_text(json.dumps(value), encoding="utf-8")
            binding = smoke.validate_client_prepare_report(
                report, client_root, bundle
            )
            self.assertEqual(binding["bundle_sha256"], "A" * 64)
            reused_native = client_root / "natives" / "reused.dll"
            reused_native.write_bytes(b"runtime state")
            with self.assertRaisesRegex(smoke.GateError, "reused natives state"):
                smoke.validate_client_prepare_report(report, client_root, bundle)
            reused_native.unlink()
            value["offline_identity"]["username"] = "WrongClient"
            report.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(smoke.GateError, "identity mismatch"):
                smoke.validate_client_prepare_report(report, client_root, bundle)

            value["offline_identity"]["username"] = smoke.SYNTHETIC_USERNAME
            value["forbidden_runtime_state_found"] = ["logs"]
            report.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(smoke.GateError, "forbidden runtime state"):
                smoke.validate_client_prepare_report(report, client_root, bundle)

    def test_clean_private_client_state_accepts_evidence_and_extra_fields(self) -> None:
        value = {
            "status": "STOPPED",
            "private_desktop": True,
            "foreground_activation": False,
            "exit_code": 1,
            "processes_closed": True,
            "process_status": {"java": True, "launcher": True, "helper": True},
            "startup_evidence": {
                "kind": "stdout_marker",
                "marker": "JVM info:",
                "path": "C:/gate/client.stdout.log",
            },
        }
        self.assertTrue(smoke.valid_clean_private_client_state(value))
        value["processes_closed"] = False
        self.assertFalse(smoke.valid_clean_private_client_state(value))

    def test_historical_backup_is_always_rejected(self) -> None:
        client = smoke.WORKSPACE_CLIENT_ROOT / "client"
        report = smoke.OUTPUTS / "candidate8-report.json"
        with self.assertRaisesRegex(smoke.GateError, "historical source"):
            smoke.validate_paths(smoke.FORBIDDEN_SOURCE, client, report)

    def test_report_has_atomic_sha256_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "report.json"
            digest = smoke.atomic_json(path, {"schema": 1, "status": "PASS"})
            self.assertEqual(digest, smoke.sha256_file(path))
            self.assertEqual(
                path.with_name("report.json.sha256").read_text(encoding="ascii"),
                f"{digest} *report.json\n",
            )

    def test_bundle_binding_changes_when_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "one.jar").write_bytes(b"one")
            first = smoke.bundle_binding(root)
            (root / "one.jar").write_bytes(b"two")
            second = smoke.bundle_binding(root)
            self.assertNotEqual(first["bundle_sha256"], second["bundle_sha256"])

    def test_current_process_exists_but_invalid_pid_does_not(self) -> None:
        self.assertTrue(smoke.process_exists(os.getpid()))
        self.assertFalse(smoke.process_exists(-1))

    def test_client_failure_preserves_exit_code_and_log_paths(self) -> None:
        message = smoke.client_state_failure_message(
            {
                "error": "Java exited before startup evidence",
                "exit_code": 1,
                "stdout": "C:/gate/client.stdout.log",
                "stderr": "C:/gate/client.stderr.log",
            }
        )
        self.assertIn("exit_code=1", message)
        self.assertIn("C:/gate/client.stdout.log", message)
        self.assertIn("C:/gate/client.stderr.log", message)

    def test_running_state_requires_explicit_jvm_startup_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw) / "client.state.json"
            session = object.__new__(smoke.PrivateClientSession)
            session.state_path = state
            session.round_number = 1
            value = {
                "status": "RUNNING",
                "private_desktop": True,
                "foreground_activation": False,
                "java_pid": os.getpid(),
            }
            state.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(smoke.GateError, "startup evidence"):
                session._running_state()
            value["startup_evidence"] = {
                "kind": "stdout_marker",
                "marker": "JVM info:",
                "path": "C:/gate/client.stdout.log",
            }
            state.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(session._running_state(), value)

    def test_private_launcher_contract_records_exit_and_startup_evidence(self) -> None:
        launcher = MODULE_PATH.with_name("launch_neoforge_client_isolated.ps1").read_text(
            encoding="utf-8"
        )
        helper = MODULE_PATH.with_name("run_private_desktop_client_session.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[string] $ExitPath", launcher)
        self.assertIn("exit_code = $process.ExitCode", launcher)
        self.assertIn("Write-State 'STARTING'", helper)
        self.assertIn("Get-StartupEvidence", helper)
        self.assertIn("Write-State 'FAILED'", helper)

    def _run_fake_round(self, *, disconnect_early: bool = False):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "server"
            artifact_dir = root / "artifacts"
            (target / "logs").mkdir(parents=True)
            artifact_dir.mkdir()

            class FakeServer:
                active = None

                def __init__(self, target, *_args, **_kwargs):
                    type(self).active = self
                    self.latest_log = target / "logs/latest.log"
                    self.text = 'Done (1.0s)! For help, type "help"\n'
                    self.latest_log.write_text(self.text, encoding="utf-8")
                    self.process = SimpleNamespace(returncode=None)
                    self.stdout_path = artifact_dir / "server.stdout"
                    self.stderr_path = artifact_dir / "server.stderr"
                    self.stdout_path.write_text("", encoding="utf-8")
                    self.stderr_path.write_text("", encoding="utf-8")

                def _write(self):
                    self.latest_log.write_text(self.text, encoding="utf-8")

                def wait_ready(self, _timeout):
                    return None

                def current_log(self):
                    return self.text

                def assert_alive(self):
                    if self.process.returncode is not None:
                        raise smoke.GateError("server exited")

                def command(self, command):
                    return "Saved the game" if command == "save-all flush" else "OK"

                def stop(self):
                    self.process.returncode = 0
                    return "Stopping the server"

                def abort(self):
                    return None

            class FakeClient:
                def __init__(self, *_args, **_kwargs):
                    server = FakeServer.active
                    server.text += "Candidate10Gate joined the game\n"
                    if disconnect_early:
                        server.text += "Candidate10Gate lost connection: Disconnected\n"
                    server._write()

                def assert_running(self):
                    return None

                def stop(self):
                    server = FakeServer.active
                    server.text += "Candidate10Gate lost connection: Disconnected\n"
                    server._write()
                    return {
                        "status": "STOPPED",
                        "private_desktop": True,
                        "foreground_activation": False,
                        "exit_code": 1,
                        "process_status": {
                            "java": True,
                            "launcher": True,
                            "helper": True,
                        },
                        "processes_closed": True,
                        "startup_evidence": {
                            "kind": "stdout_marker",
                            "marker": "JVM info:",
                            "path": "client.stdout.log",
                        },
                    }

                def abort(self):
                    return None

            kwargs = {
                "target": target,
                "artifact_dir": artifact_dir,
                "round_number": 1,
                "java": Path("java"),
                "powershell": Path("powershell"),
                "helper": Path("helper"),
                "launcher": Path("launcher"),
                "client_root": root / "client",
                "win_args": "@win_args.txt",
                "server_port": 12341,
                "rcon_port": 12342,
                "rcon_password": "secret",
                "server_memory_mb": 4096,
                "client_memory_mb": 2048,
                "startup_timeout": 1,
                "join_timeout": 1,
                "client_launch_timeout": 1,
                "client_session_timeout": 1,
                "teleport_pause": 0,
                "settle_seconds": 0,
            }
            with (
                mock.patch.object(smoke, "ServerSession", FakeServer),
                mock.patch.object(smoke, "PrivateClientSession", FakeClient),
                mock.patch.object(smoke, "capture_round_artifacts", return_value={}),
            ):
                return smoke.run_round(**kwargs)

    def test_fake_round_proves_join_commands_save_and_clean_stop(self) -> None:
        result = self._run_fake_round()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["join"]["new_join_lines"], 1)
        self.assertEqual(result["server_exit_code"], 0)
        self.assertTrue(smoke.valid_clean_private_client_state(result["client_state"]))
        self.assertEqual(
            [value["command"] for value in result["commands"]],
            [value["command"] for value in smoke.command_plan()],
        )

    def test_fake_round_fails_if_client_disconnects_before_controlled_stop(self) -> None:
        with self.assertRaisesRegex(smoke.GateError, "disconnected before"):
            self._run_fake_round(disconnect_early=True)


if __name__ == "__main__":
    unittest.main()
