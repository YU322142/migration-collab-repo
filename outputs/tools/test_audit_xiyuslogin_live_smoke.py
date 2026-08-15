from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("audit_xiyuslogin_live_smoke.py")
SPEC = importlib.util.spec_from_file_location("audit_xiyuslogin_live_smoke", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


class AuditXiyusLoginLiveSmokeTest(unittest.TestCase):
    def test_synthetic_output_requires_cost12_and_two_reauthentications(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "xiyus_player_data.json"
            record = {field: None for field in audit.auth_gate.EXPECTED_FIELDS}
            record.update(
                {
                    "username": "Synthetic",
                    "uuid": "00000000-0000-0000-0000-000000000001",
                    "passwordHash": "$2b$12$" + "A" * 53,
                    "passwordScheme": "bcrypt",
                    "loginCount": 2,
                }
            )
            path.write_text(json.dumps({"synthetic": record}), encoding="utf-8")
            summary = audit.audit_synthetic_output(path)
            self.assertEqual(summary["bcrypt_cost_12"], 1)
            self.assertEqual(summary["login_count_after_two_successful_reauthentications"], 2)

            record["loginCount"] = 1
            path.write_text(json.dumps({"synthetic": record}), encoding="utf-8")
            with self.assertRaisesRegex(audit.AuditError, "SYNTHETIC_OUTPUT_LOGIN_COUNT"):
                audit.audit_synthetic_output(path)

    def test_fatal_missing_bytes_marker_is_rejected(self) -> None:
        with self.assertRaisesRegex(audit.AuditError, "NoClassDefFoundError"):
            audit.assert_no_fatal_auth_error(
                "NoClassDefFoundError: at/favre/lib/bytes/Bytes", "FIXTURE"
            )

    def test_candidate_log_marker_comes_from_exact_jar_name(self) -> None:
        marker = "xiyuslogin-1.4-migration4.jar"
        self.assertEqual(
            audit.require_at_least(
                f'Found mod file "{marker}"', marker, 1, "CANDIDATE"
            ),
            1,
        )
        with self.assertRaisesRegex(audit.AuditError, "CANDIDATE"):
            audit.require_at_least(
                'Found mod file "xiyuslogin-1.4-migration3.jar"',
                marker,
                1,
                "CANDIDATE",
            )

    def test_runtime_dependency_markers_fail_closed_when_missing(self) -> None:
        log = 'Found library file "bytes-1.5.0.jar"'
        with self.assertRaisesRegex(audit.AuditError, "BCRYPT_RUNTIME"):
            audit.require_at_least(
                log,
                "bcrypt-0.10.2.jar",
                1,
                "BCRYPT_RUNTIME",
            )

    def test_markdown_never_claims_strict_pass(self) -> None:
        report = {
            "candidate": {
                "file": "xiyuslogin-1.4-migration4.jar",
                "bytes": 170065,
                "sha256": "D" * 64,
                "version": "1.4-migration4",
            },
            "scenarios": {
                name: {"status": audit.SYNTHETIC_PASS}
                for name in audit.auth_gate.REQUIRED_LIVE_SCENARIOS
            },
            "remaining_blockers": ["synthetic blocker"],
        }
        text = audit.render_markdown(report)
        self.assertIn("Aggregate status: **BLOCKED**", text)
        self.assertNotIn("READY_AUTH_CUTOVER", text)


if __name__ == "__main__":
    unittest.main()
