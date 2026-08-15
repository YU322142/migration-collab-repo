from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = WORKSPACE / "outputs/mechanomania-side-classification-20260813.json"
TARGET_IDS = {
    "byepregen",
    "efficient_hashing",
    "fastrecipesearch",
    "hoporp",
    "jecharacters",
    "mousetweaks",
    "mr_dungeons_andtavernsancientcityoverhaul",
    "mr_epic_structuresvillages",
    "mr_lukis_crazychambers",
    "rhino",
    "yet_another_config_lib_v3",
}
EXPECTED = {
    "byepregen": "BOTH",
    "efficient_hashing": "BOTH",
    "fastrecipesearch": "BOTH",
    "hoporp": "SERVER_ONLY",
    "jecharacters": "CLIENT_ONLY",
    "mousetweaks": "CLIENT_ONLY",
    "mr_dungeons_andtavernsancientcityoverhaul": "BOTH",
    "mr_epic_structuresvillages": "BOTH",
    "mr_lukis_crazychambers": "BOTH",
    "rhino": "BOTH",
    "yet_another_config_lib_v3": "CLIENT_ONLY",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def fail(message: str) -> None:
    raise ValueError(message)


def validate(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if report.get("status") != "PASS_STATIC_SIDE_CLASSIFICATION":
        fail("report status is not PASS_STATIC_SIDE_CLASSIFICATION")
    if report.get("unresolved_mod_ids"):
        fail("report contains unresolved mod IDs")
    if report.get("counts", {}).get("unknown_fail_closed") != 0:
        fail("unknown_fail_closed count is non-zero")

    rows = report.get("classifications") or []
    by_id = {row.get("mod_id"): row for row in rows}
    if set(by_id) != TARGET_IDS or len(rows) != len(TARGET_IDS):
        fail("classification target set is not exact")

    for mod_id, expected in EXPECTED.items():
        row = by_id[mod_id]
        if row.get("classification") != expected:
            fail(f"{mod_id}: expected {expected}, got {row.get('classification')}")
        if row.get("evidence_gate") != "PASS" or row.get("evidence_failures"):
            fail(f"{mod_id}: evidence gate is not clean")
        inspection = row.get("inspection") or {}
        path = Path(str(inspection.get("path") or ""))
        if not path.is_file():
            fail(f"{mod_id}: selected JAR is missing")
        if sha256(path) != inspection.get("sha256"):
            fail(f"{mod_id}: selected JAR hash drift")
        if inspection.get("archive_crc") != "PASS":
            fail(f"{mod_id}: archive CRC is not PASS")
        if inspection.get("bytecode", {}).get("class_parse_errors"):
            fail(f"{mod_id}: class parse errors are present")
        if inspection.get("mixins", {}).get("parse_errors"):
            fail(f"{mod_id}: mixin parse errors are present")
        if row.get("server_bundle") != (expected in {"SERVER_ONLY", "BOTH"}):
            fail(f"{mod_id}: server placement contradicts classification")
        if row.get("client_bundle") != (expected in {"CLIENT_ONLY", "BOTH"}):
            fail(f"{mod_id}: client placement contradicts classification")

    counts = report.get("counts") or {}
    expected_counts = {
        "target_mod_ids": 11,
        "both": 7,
        "server_only": 1,
        "client_only": 3,
        "unknown_fail_closed": 0,
    }
    if counts != expected_counts:
        fail(f"unexpected aggregate counts: {counts}")

    scope = report.get("scope") or {}
    if any(
        scope.get(name) is not False
        for name in (
            "java_or_minecraft_started",
            "release_modified",
            "world_modified",
            "network_used",
        )
    ):
        fail("scope reports an out-of-scope action")

    upstream = report.get("upstream") or {}
    upstream_path = Path(str(upstream.get("path") or ""))
    if not upstream_path.is_file() or sha256(upstream_path) != upstream.get("sha256"):
        fail("upstream audit hash drift")

    for tool in report.get("tools") or []:
        tool_path = Path(str(tool.get("path") or ""))
        if not tool.get("exists") or not tool_path.is_file():
            fail(f"missing audit tool: {tool.get('name')}")
        if sha256(tool_path) != tool.get("sha256"):
            fail(f"audit tool hash drift: {tool.get('name')}")

    contract = report.get("integration_contract") or {}
    expected_server = sorted(mod_id for mod_id, side in EXPECTED.items() if side in {"SERVER_ONLY", "BOTH"})
    expected_client = sorted(mod_id for mod_id, side in EXPECTED.items() if side in {"CLIENT_ONLY", "BOTH"})
    if sorted(contract.get("server_mod_ids") or []) != expected_server:
        fail("server integration contract is inconsistent")
    if sorted(contract.get("client_mod_ids") or []) != expected_client:
        fail("client integration contract is inconsistent")

    return {
        "status": "PASS",
        "report": str(report_path),
        "report_sha256": sha256(report_path),
        "counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    try:
        result = validate(args.report)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED_FAIL_CLOSED", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
