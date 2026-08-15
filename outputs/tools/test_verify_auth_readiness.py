from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import zipfile


MODULE_PATH = Path(__file__).with_name("verify_auth_readiness.py")
SPEC = importlib.util.spec_from_file_location("verify_auth_readiness", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class VerifyAuthReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = os.environ.get("MIGRATION_TEST_TMPDIR")
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.allowed = self.root / "allowed"
        self.staging = self.root / "staging"
        self.reports = self.root / "reports"
        self.database = self.allowed / "copy" / "EasyAuth" / "easyauth.db"
        self.output = self.staging / "world" / "xiyus_player_data.json"
        self.sqlite_report = self.reports / "easyauth-sqlite.json"
        self.migration_report = self.reports / "xiyuslogin-migration.json"
        self.candidate = self.root / "candidate" / "xiyuslogin.jar"
        self.converter = self.root / "tools" / "fixture_converter.py"
        self.report = self.root / "gate-output" / "auth-readiness.json"
        self._write_database()
        self._write_output_and_reports()
        self._write_candidate()
        self._write_converter()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_database(self) -> None:
        self.database.parent.mkdir(parents=True)
        connection = sqlite3.connect(self.database)
        connection.execute(
            "create table easyauth ("
            "id integer primary key, username text, username_lower text, "
            "uuid text, data text)"
        )
        bcrypt = "$2b$12$" + "A" * 53
        rows = [
            (
                "Alpha",
                "alpha",
                str(uuid.UUID("11111111-1111-1111-1111-111111111111")),
                bcrypt,
            ),
            (
                "Premium",
                "premium",
                str(uuid.UUID("22222222-2222-2222-2222-222222222222")),
                "",
            ),
            ("NewPlayer", "newplayer", None, ""),
        ]
        for username, lower, player_uuid, password in rows:
            data = {
                "password": password,
                "last_ip": "",
                "last_authenticated_date": "1970-01-01T00:00:00",
                "login_tries": 0,
                "last_kicked_date": "1970-01-01T00:00:00",
                "online_account": "UNKNOWN",
                "registration_date": "2026-01-01T01:02:03",
                "data_version": 1,
            }
            connection.execute(
                "insert into easyauth(username, username_lower, uuid, data) "
                "values (?, ?, ?, ?)",
                (username, lower, player_uuid, json.dumps(data)),
            )
        connection.commit()
        connection.close()

    def _write_output_and_reports(self) -> None:
        records, summary = gate.source_records(self.database.resolve())
        self.output.parent.mkdir(parents=True)
        self.output.write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.reports.mkdir(parents=True)
        self.sqlite_report.write_text(
            json.dumps(
                {
                    "source_copy_files": {
                        "easyauth.db": {
                            "bytes": self.database.stat().st_size,
                            "sha256": digest(self.database).lower(),
                        }
                    },
                    "source_integrity_check": ["ok"],
                    "snapshot_integrity_check": ["ok"],
                    "records": summary["records"],
                }
            ),
            encoding="utf-8",
        )
        self.migration_report.write_text(
            json.dumps(
                {
                    "records": summary["records"],
                    "hashes": {
                        "bcrypt": summary["bcrypt"],
                        "empty": summary["empty"],
                    },
                    "uuidPresent": summary["uuid_present"],
                    "plaintextStored": False,
                    "output": str(self.output),
                    "outputSha256": digest(self.output).lower(),
                }
            ),
            encoding="utf-8",
        )

    def _write_candidate(self, version: str = gate.EXPECTED_JAR_VERSION) -> None:
        self.candidate.parent.mkdir(parents=True, exist_ok=True)
        metadata = f"""
  modLoader = "javafml"
  [[mods]]
  modId = "xiyuslogin"
                version = "{version}"
  [[dependencies."xiyuslogin"]]
  modId = "neoforge"
  versionRange = "[21.1.215,21.2.0)"
"""
        with zipfile.ZipFile(self.candidate, "w") as archive:
            archive.writestr("META-INF/neoforge.mods.toml", metadata)
            archive.writestr(
                "META-INF/xiyuslogin-security.properties",
                "\n".join(
                    f"{key}={value}"
                    for key, value in gate.expected_security_properties(version).items()
                )
                + "\n",
            )
            runtime_jars = []
            for artifact, expected in gate.EXPECTED_RUNTIME_JARS.items():
                nested_buffer = io.BytesIO()
                with zipfile.ZipFile(nested_buffer, "w") as nested:
                    nested.writestr(expected["required_class"], b"synthetic class fixture")
                archive.writestr(expected["path"], nested_buffer.getvalue())
                runtime_jars.append(
                    {
                        "identifier": {
                            "group": expected["group"],
                            "artifact": artifact,
                        },
                        "version": {
                            "range": f"[{expected['version']},)",
                            "artifactVersion": expected["version"],
                        },
                        "path": expected["path"],
                        "isObfuscated": False,
                    }
                )
            archive.writestr(
                "META-INF/jarjar/metadata.json",
                json.dumps({"jars": runtime_jars}, sort_keys=True),
            )

    def _write_converter(self) -> None:
        self.converter.parent.mkdir(parents=True)
        self.converter.write_text(
            """from __future__ import annotations
import argparse, hashlib, importlib.util, json
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('db',type=Path); parser.add_argument('output',type=Path)
parser.add_argument('--manifest',type=Path,required=True)
args=parser.parse_args()
module_path=Path(r'"""
            + str(MODULE_PATH)
            + """')
spec=importlib.util.spec_from_file_location('auth_gate_for_fixture',module_path)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
records,summary=module.source_records(args.db.resolve())
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\\n',encoding='utf-8')
out_hash=hashlib.sha256(args.output.read_bytes()).hexdigest()
manifest={'records':summary['records'],'hashes':{'bcrypt':summary['bcrypt'],'empty':summary['empty']},'uuidPresent':summary['uuid_present'],'plaintextStored':False,'outputSha256':out_hash}
args.manifest.parent.mkdir(parents=True,exist_ok=True)
args.manifest.write_text(json.dumps(manifest,sort_keys=True),encoding='utf-8')
""",
            encoding="utf-8",
        )

    def args(self, live: Path | None = None, report: Path | None = None) -> list[str]:
        values = [
            "--source-db",
            str(self.database),
            "--allowed-source-root",
            str(self.allowed),
            "--staging-root",
            str(self.staging),
            "--output",
            str(self.output),
            "--sqlite-report",
            str(self.sqlite_report),
            "--migration-report",
            str(self.migration_report),
            "--candidate-jar",
            str(self.candidate),
            "--migration-tool",
            str(self.converter),
            "--report",
            str(report or self.report),
            "--expected-source-sha256",
            digest(self.database),
            "--expected-jar-sha256",
            digest(self.candidate),
            "--expected-jar-bytes",
            str(self.candidate.stat().st_size),
            "--expected-records",
            "3",
            "--expected-bcrypt",
            "1",
            "--expected-empty",
            "2",
            "--expected-uuids",
            "2",
        ]
        if live is not None:
            values.extend(["--live-login-report", str(live)])
        return values

    def test_data_passes_but_missing_live_evidence_returns_two(self) -> None:
        self.assertEqual(gate.main(self.args()), 2)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "BLOCKED_LIVE_LOGIN_NOT_PROVEN")
        self.assertEqual(report["accounts"]["records"], 3)
        self.assertTrue(report["idempotence"]["hashes_equal"])
        self.assertTrue(report["source"]["read_only"])
        rendered = self.report.read_text(encoding="utf-8")
        for forbidden in ("Alpha", "Premium", "NewPlayer", "$2b$", "token", "endpoint"):
            self.assertNotIn(forbidden, rendered)

    def test_migration4_version_and_security_default_are_explicitly_supported(self) -> None:
        self._write_candidate("1.4-migration4")
        args = self.args() + ["--expected-jar-version", "1.4-migration4"]
        self.assertEqual(gate.main(args), 2)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["candidate_jar"]["version"], "1.4-migration4")
        self.assertEqual(
            report["candidate_jar"]["security_defaults"][
                "unauthenticatedBlindness.default"
            ],
            "false",
        )

    def test_bound_complete_live_evidence_returns_ready(self) -> None:
        live = self.root / "live.json"
        scenarios = {}
        for name in gate.REQUIRED_LIVE_SCENARIOS:
            artifact = self.root / (name + ".redacted.txt")
            artifact.write_text("synthetic redacted auth evidence\\n", encoding="utf-8")
            scenarios[name] = {
                "status": "PASS",
                "artifacts": [
                    {
                        "path": artifact.name,
                        "sha256": digest(artifact),
                        "kind": "redacted_transcript",
                        "contains_secrets": False,
                    }
                ],
            }
        live.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "status": "PASS",
                    "contains_secrets": False,
                    "tested_with_secrets": False,
                    "source_sha256": digest(self.database),
                    "output_sha256": digest(self.output),
                    "candidate_jar_sha256": digest(self.candidate),
                    "scenarios": scenarios,
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(gate.main(self.args(live)), 0)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "READY_AUTH_CUTOVER")
        self.assertTrue(report["live_login"]["evidence_bound"])
        self.assertEqual(
            set(report["live_login"]["scenario_evidence"]),
            set(gate.REQUIRED_LIVE_SCENARIOS),
        )

    def test_explicit_incomplete_live_evidence_remains_release_blocked(self) -> None:
        live = self.root / "live-blocked.json"
        scenarios = {
            name: {
                "status": (
                    "BLOCKED_RUNTIME_MISSING"
                    if name in {"bedrock_floodgate_uuid_mapping", "proxy_ip_session_policy"}
                    else "PASS_SYNTHETIC_NETWORK_RUNTIME"
                )
            }
            for name in gate.REQUIRED_LIVE_SCENARIOS
        }
        live.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "status": "BLOCKED_LIVE_LOGIN_INCOMPLETE",
                    "contains_secrets": False,
                    "tested_with_secrets": False,
                    "source_sha256": digest(self.database),
                    "output_sha256": digest(self.output),
                    "candidate_jar_sha256": digest(self.candidate),
                    "scenarios": scenarios,
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(gate.main(self.args(live)), 2)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "BLOCKED_LIVE_LOGIN_NOT_PROVEN")
        self.assertEqual(
            report["live_login"]["status"], "BLOCKED_LIVE_LOGIN_INCOMPLETE"
        )
        self.assertFalse(report["live_login"]["evidence_bound"])

    def test_live_scenario_without_bound_artifact_is_no_go(self) -> None:
        live = self.root / "live-missing-artifact.json"
        live.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "status": "PASS",
                    "contains_secrets": False,
                    "tested_with_secrets": False,
                    "source_sha256": digest(self.database),
                    "output_sha256": digest(self.output),
                    "candidate_jar_sha256": digest(self.candidate),
                    "scenarios": {
                        name: {"status": "PASS", "artifacts": []}
                        for name in gate.REQUIRED_LIVE_SCENARIOS
                    },
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(gate.main(self.args(live)), 1)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(
            report["error_code"],
            "LIVE_REPORT_SCENARIO_ARTIFACTS_MISSING:java_existing_bcrypt_correct",
        )

    def test_live_scenario_secret_flag_or_hash_mismatch_is_no_go(self) -> None:
        live = self.root / "live-secret-artifact.json"
        artifact = self.root / "secret-flag.txt"
        artifact.write_text("synthetic redacted evidence\\n", encoding="utf-8")
        scenarios = {
            name: {
                "status": "PASS",
                "artifacts": [
                    {
                        "path": artifact.name,
                        "sha256": digest(artifact),
                        "kind": "redacted_transcript",
                        "contains_secrets": name == "java_existing_bcrypt_correct",
                    }
                ],
            }
            for name in gate.REQUIRED_LIVE_SCENARIOS
        }
        live.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "status": "PASS",
                    "contains_secrets": False,
                    "tested_with_secrets": False,
                    "source_sha256": digest(self.database),
                    "output_sha256": digest(self.output),
                    "candidate_jar_sha256": digest(self.candidate),
                    "scenarios": scenarios,
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(gate.main(self.args(live)), 1)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(
            report["error_code"],
            "LIVE_REPORT_SCENARIO_ARTIFACT_SECRET_FLAG:java_existing_bcrypt_correct",
        )
        first = scenarios["java_existing_bcrypt_correct"]["artifacts"][0]
        first["contains_secrets"] = False
        first["sha256"] = "0" * 64
        value = json.loads(live.read_text(encoding="utf-8"))
        value["scenarios"] = scenarios
        live.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(gate.main(self.args(live)), 1)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(
            report["error_code"],
            "LIVE_REPORT_SCENARIO_ARTIFACT_HASH_MISMATCH:java_existing_bcrypt_correct",
        )

    def test_tampered_output_fails_closed(self) -> None:
        value = json.loads(self.output.read_text(encoding="utf-8"))
        next(iter(value.values()))["loginCount"] = 9
        self.output.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(gate.main(self.args()), 1)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "BLOCKED_AUTH_DATA")
        self.assertEqual(report["error_code"], "OUTPUT_SEMANTICS_MISMATCH")

    def test_candidate_missing_transitive_runtime_class_fails_closed(self) -> None:
        with zipfile.ZipFile(self.candidate, "r") as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        nested_buffer = io.BytesIO()
        with zipfile.ZipFile(nested_buffer, "w") as nested:
            nested.writestr("fixture/not-the-required-class.txt", b"missing bytes class")
        entries[gate.EXPECTED_RUNTIME_JARS["bytes"]["path"]] = nested_buffer.getvalue()
        with zipfile.ZipFile(self.candidate, "w") as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)

        self.assertEqual(gate.main(self.args()), 1)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(
            report["error_code"], "CANDIDATE_JAR_RUNTIME_CLASS_MISSING:bytes"
        )

    def test_report_inside_source_is_rejected_without_write(self) -> None:
        unsafe = self.allowed / "auth-readiness.json"
        self.assertEqual(gate.main(self.args(report=unsafe)), 1)
        self.assertFalse(unsafe.exists())


if __name__ == "__main__":
    unittest.main()
