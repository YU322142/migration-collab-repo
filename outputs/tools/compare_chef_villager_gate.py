from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from nbt import nbt

from prepare_chef_villager_gate import CHEF_UUIDS, critical_snapshot


ALLOWED_TARGET_DEFAULT_ATTRIBUTES = {
    "minecraft:generic.oxygen_bonus": {"base": 0.0, "modifiers": []},
}


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def section_hash(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def compare_float_lists(expected, actual, tolerance=1e-9):
    return len(expected) == len(actual) and all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected, actual)
    )


def compare_attributes(expected, actual):
    missing = sorted(set(expected) - set(actual))
    changed = []
    for identifier in sorted(set(expected) & set(actual)):
        if expected[identifier] != actual[identifier]:
            changed.append({
                "id": identifier,
                "expected": expected[identifier],
                "actual": actual[identifier],
            })
    unsupported_extra = {
        identifier: value
        for identifier, value in actual.items()
        if identifier not in expected
        and ALLOWED_TARGET_DEFAULT_ATTRIBUTES.get(identifier) != value
    }
    allowed_extra = {
        identifier: value
        for identifier, value in actual.items()
        if identifier not in expected
        and ALLOWED_TARGET_DEFAULT_ATTRIBUTES.get(identifier) == value
    }
    return {
        "pass": not missing and not changed and not unsupported_extra,
        "missing": missing,
        "changed": changed,
        "allowed_target_defaults": allowed_extra,
        "unsupported_extra": unsupported_extra,
    }


def compare_one(expected, actual):
    checks = {
        "uuid": expected["uuid"] == actual["uuid"],
        "position": compare_float_lists(expected["position"], actual["position"]),
        "rotation": compare_float_lists(expected["rotation"], actual["rotation"]),
        "villager_data": expected["villager_data"] == actual["villager_data"],
        "xp": expected["xp"] == actual["xp"],
        "offers": expected["offers"] == actual["offers"],
        "brain": expected["brain"] == actual["brain"],
        "state": expected["state"] == actual["state"],
    }
    attributes = compare_attributes(expected["attributes"], actual["attributes"])
    checks["attributes"] = attributes["pass"]
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "attributes": attributes,
        "expected_hashes": {
            key: section_hash(expected[key])
            for key in ("offers", "brain", "attributes", "state")
        },
        "actual_hashes": {
            key: section_hash(actual[key])
            for key in ("offers", "brain", "attributes", "state")
        },
        "expected": expected,
        "actual": actual,
    }


def load_snapshots(root: Path):
    snapshots = {}
    for path in sorted(root.glob("*.nbt")):
        entity = nbt.NBTFile(filename=str(path))
        snapshot = critical_snapshot(entity)
        snapshots[snapshot["uuid"]] = snapshot
    return snapshots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--actual", type=Path, action="append", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    expected = load_snapshots(args.expected)
    if set(expected) != CHEF_UUIDS:
        raise SystemExit(f"expected fixture UUID mismatch: {sorted(expected)}")
    rounds = []
    for actual_root in args.actual:
        actual = load_snapshots(actual_root)
        missing = sorted(CHEF_UUIDS - set(actual))
        extra = sorted(set(actual) - CHEF_UUIDS)
        comparisons = {
            identifier: compare_one(expected[identifier], actual[identifier])
            for identifier in sorted(CHEF_UUIDS & set(actual))
        }
        rounds.append({
            "path": str(actual_root),
            "status": "PASS" if not missing and not extra and all(
                comparison["pass"] for comparison in comparisons.values()
            ) else "FAIL",
            "missing": missing,
            "extra": extra,
            "comparisons": comparisons,
        })

    report = {
        "status": "PASS" if all(round_["status"] == "PASS" for round_ in rounds) else "FAIL",
        "expected": str(args.expected),
        "rounds": rounds,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "rounds": [
            {
                "path": round_["path"],
                "status": round_["status"],
                "villagers": len(round_["comparisons"]),
                "missing": len(round_["missing"]),
                "extra": len(round_["extra"]),
            }
            for round_ in rounds
        ],
        "report": str(args.report),
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
