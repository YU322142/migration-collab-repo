#!/usr/bin/env python3
"""Freeze fail-closed evidence for the corrected Schematicannon migration."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import audit_candidate4_fullstack_smoke as common


SCHEMA = 2
EXPECTED_CANNON_POSITIONS = (
    (-324, 63, -210),
    (-33, 71, -556),
    (-12, 64, 9),
    (27306, 72, -12883),
)
REGIONS = ["r.-1.-2.mca", "r.-1.-1.mca", "r.-1.0.mca", "r.53.-26.mca"]


class EvidenceError(RuntimeError):
    pass


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def conversion_gate(
    path: Path,
    target: Path,
    expected_world: Path | None = None,
) -> dict[str, Any]:
    value = common.read_json(path, "Schematicannon conversion report")
    conversions = value.get("schematicannon_inventory_conversions")
    unsupported = value.get("unsupported_block_entities")
    malformed = value.get("malformed_regions")
    blockers = []
    if not isinstance(conversions, list) or len(conversions) != len(
        EXPECTED_CANNON_POSITIONS
    ):
        blockers.append("CONVERSION_COUNT_MISMATCH")
    if unsupported != []:
        blockers.append("UNSUPPORTED_BLOCK_ENTITIES_NONEMPTY")
    if malformed != []:
        blockers.append("MALFORMED_REGIONS_NONEMPTY")
    positions = sorted(
        [row.get("x"), row.get("y"), row.get("z")]
        for row in conversions or []
        if isinstance(row, dict)
    )
    if positions != [list(position) for position in EXPECTED_CANNON_POSITIONS]:
        blockers.append("CONVERSION_POSITIONS_MISMATCH")
    expected = (target / "world") if expected_world is None else expected_world
    if Path(str(value.get("world", ""))).resolve() != expected.resolve():
        blockers.append("CONVERSION_TARGET_MISMATCH")
    return {
        "status": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "artifact": common.artifact(path),
        "conversion_count": len(conversions) if isinstance(conversions, list) else None,
        "positions": positions,
    }


def lifecycle_gate(path: Path, expected_records: int) -> dict[str, Any]:
    analysis = common.analyze_log(common.read_text(path))
    blockers = common.lifecycle_failures(
        analysis, expected_records, require_reload=False
    )
    return {
        "status": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "artifact": common.artifact(path, scan_secrets=True),
        "analysis": analysis,
    }


def build_report(
    source: Path,
    target: Path,
    conversion_report: Path,
    prepare_report: Path,
    expected_records: int,
    ports: tuple[int, int, int],
) -> dict[str, Any]:
    source = source.resolve()
    target = target.resolve()
    prepared = common.read_json(prepare_report, "smoke prepare report")
    blockers = []
    if Path(str(prepared.get("output", ""))).resolve() != target:
        blockers.append("PREPARE_TARGET_MISMATCH")
    staging = Path(str(prepared.get("staging", ""))).resolve()
    conversion = conversion_gate(
        conversion_report.resolve(), target, staging / "world"
    )
    if conversion["status"] != "PASS":
        blockers.extend(conversion["blockers"])
    runs = {
        name: lifecycle_gate(target / f"{name}.stdout.log", expected_records)
        for name in ("run1", "run2")
    }
    for name, row in runs.items():
        if row["status"] != "PASS":
            blockers.extend(f"{name.upper()}_{item}" for item in row["blockers"])
    cannons = common.schematicannon_audit(source, target, REGIONS)
    if cannons["status"] != "PASS":
        blockers.append("SCHEMATICANNON_SEMANTIC_COMPARE_FAILED")
    port_rows = {
        name: {"port": port, "closed": common.probe_tcp_closed(port)}
        for name, port in zip(("server", "rcon", "voice"), ports, strict=True)
    }
    if not all(row["closed"] for row in port_rows.values()):
        blockers.append("TEST_PORT_STILL_OPEN")
    return {
        "schema": SCHEMA,
        "status": "PASS" if not blockers else "NO_GO",
        "category": "schematicannon_corrected_smoke",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": str(source),
        "target": str(target),
        "blockers": sorted(set(blockers)),
        "prepare_report": common.artifact(prepare_report.resolve()),
        "conversion": conversion,
        "runs": runs,
        "schematicannons": cannons,
        "runtime_mods": common.scan_runtime_mods(target / "mods"),
        "ports": port_rows,
    }


def markdown(value: dict[str, Any]) -> str:
    lines = [
        "# Corrected Schematicannon Smoke",
        "",
        f"Status: **{value['status']}**",
        "",
        f"- Conversion records: {value['conversion']['conversion_count']}.",
        f"- Run 1: {value['runs']['run1']['status']}.",
        f"- Run 2: {value['runs']['run2']['status']}.",
        f"- Semantic comparison: {value['schematicannons']['status']}.",
        f"- Lost item units: {value['schematicannons']['lost_item_units']}.",
        "",
        "## Cannons",
        "",
    ]
    for row in value["schematicannons"]["comparisons"]:
        inventory = row["target"]["inventory"]
        items = ", ".join(
            f"slot {item['slot']} {item['id']} x{item['count']}"
            for item in inventory["items"]
        )
        lines.append(
            f"- `{row['position']}`: {row['status']}; {inventory['encoding']}; {items}."
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {item}" for item in value["blockers"])
    if not value["blockers"]:
        lines.append("- None in this bounded gate.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--conversion-report", type=Path, required=True)
    parser.add_argument("--prepare-report", type=Path, required=True)
    parser.add_argument("--expected-records", type=int, default=49)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--rcon-port", type=int, required=True)
    parser.add_argument("--voice-port", type=int, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    value = build_report(
        args.source,
        args.target,
        args.conversion_report,
        args.prepare_report,
        args.expected_records,
        (args.server_port, args.rcon_port, args.voice_port),
    )
    atomic_json(args.output_json, value)
    args.output_md.write_text(markdown(value), encoding="utf-8")
    print(json.dumps({"status": value["status"], "blockers": value["blockers"]}))
    return 0 if value["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
