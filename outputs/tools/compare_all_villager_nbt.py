from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from nbt import nbt

import convert_world_nbt as converter
from compare_chef_villager_gate import compare_attributes
from compare_villager_offers import canonical_recipe
from prepare_chef_villager_gate import canonical_uuid, json_value


SECTIONS = (
    "uuid",
    "position",
    "rotation",
    "villager_data",
    "xp",
    "offers",
    "brain",
    "state",
    "attributes",
)


def canonical_offers(value):
    """Normalize the three known 1.21.11 -> 1.21.1 item codec spellings."""
    if not isinstance(value, dict):
        return value
    result = dict(value)
    recipes = value.get("Recipes")
    if isinstance(recipes, list):
        result["Recipes"] = [canonical_recipe(recipe) for recipe in recipes]
    return result


def rotation_equivalent(expected, actual, tolerance: float) -> bool:
    if len(expected) != len(actual):
        return False
    if not expected:
        return True
    yaw_delta = ((float(actual[0]) - float(expected[0]) + 180.0) % 360.0) - 180.0
    if not math.isclose(yaw_delta, 0.0, rel_tol=0.0, abs_tol=tolerance):
        return False
    return all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected[1:], actual[1:])
    )


def villager_snapshot(entity) -> dict:
    attributes = {}
    for attribute in entity.get("attributes", []):
        identifier = str(attribute.get("id"))
        attributes[identifier] = {
            "base": float(attribute["base"].value),
            "modifiers": sorted(
                (
                    {
                        "id": str(modifier["id"]),
                        "amount": float(modifier["amount"].value),
                        "operation": str(modifier["operation"]),
                    }
                    for modifier in attribute.get("modifiers", [])
                ),
                key=lambda modifier: modifier["id"],
            ),
        }
    snapshot = {
        "uuid": canonical_uuid(entity["UUID"]),
        "position": [float(value.value) for value in entity["Pos"]],
        "rotation": [float(value.value) for value in entity["Rotation"]],
        "villager_data": json_value(entity["VillagerData"]),
        "xp": int(entity["Xp"].value),
        # Missing and empty are intentionally distinct. This catches a codec
        # silently creating or deleting an Offers/Brain payload.
        "offers_raw": json_value(entity["Offers"]) if "Offers" in entity else None,
        "brain": json_value(entity["Brain"]) if "Brain" in entity else None,
        "attributes": dict(sorted(attributes.items())),
        "state": {
            key: json_value(entity[key])
            for key in ("Age", "Health", "LastRestock", "RestocksToday", "Willing")
            if key in entity
        },
    }
    snapshot["offers"] = canonical_offers(snapshot["offers_raw"])
    return snapshot


def canonical_json(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def compare_float_lists(expected, actual, tolerance: float) -> bool:
    return len(expected) == len(actual) and all(
        math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected, actual)
    )


def bounded_diff(expected, actual, limit: int = 100) -> list[dict]:
    differences: list[dict] = []

    def visit(left, right, path: str) -> None:
        if len(differences) >= limit:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) - set(right)):
                differences.append({
                    "path": f"{path}.{key}",
                    "kind": "missing",
                    "expected": left[key],
                })
                if len(differences) >= limit:
                    return
            for key in sorted(set(right) - set(left)):
                differences.append({
                    "path": f"{path}.{key}",
                    "kind": "extra",
                    "actual": right[key],
                })
                if len(differences) >= limit:
                    return
            for key in sorted(set(left) & set(right)):
                visit(left[key], right[key], f"{path}.{key}")
            return
        if isinstance(left, list) and isinstance(right, list):
            if len(left) != len(right):
                differences.append({
                    "path": path,
                    "kind": "length",
                    "expected": len(left),
                    "actual": len(right),
                })
                if len(differences) >= limit:
                    return
            for index, (left_child, right_child) in enumerate(zip(left, right)):
                visit(left_child, right_child, f"{path}[{index}]")
            return
        if left != right:
            differences.append({
                "path": path,
                "kind": "changed",
                "expected": left,
                "actual": right,
            })

    visit(expected, actual, "$ ".strip())
    if len(differences) == limit:
        differences.append({
            "path": "$",
            "kind": "truncated",
            "limit": limit,
        })
    return differences


def compare_snapshots(expected: dict, actual: dict, tolerance: float) -> dict:
    checks = {
        "uuid": expected["uuid"] == actual["uuid"],
        "position": compare_float_lists(
            expected["position"], actual["position"], tolerance
        ),
        "rotation": rotation_equivalent(
            expected["rotation"], actual["rotation"], tolerance
        ),
        "villager_data": expected["villager_data"] == actual["villager_data"],
        "xp": expected["xp"] == actual["xp"],
        "offers": expected["offers"] == actual["offers"],
        "brain": expected["brain"] == actual["brain"],
        "state": expected["state"] == actual["state"],
    }
    attributes = compare_attributes(expected["attributes"], actual["attributes"])
    checks["attributes"] = attributes["pass"]
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "expected_hashes": {
            section: digest(expected[section]) for section in SECTIONS
        },
        "actual_hashes": {
            section: digest(actual[section]) for section in SECTIONS
        },
        "raw_offer_hashes": {
            "expected": digest(expected["offers_raw"]),
            "actual": digest(actual["offers_raw"]),
        },
        "attributes": attributes,
        "normalizations": {
            "offers_codec": expected["offers_raw"] != actual["offers_raw"],
            "rotation_wrap": not compare_float_lists(
                expected["rotation"], actual["rotation"], tolerance
            ) and checks["rotation"],
        },
    }
    if result["status"] == "FAIL":
        result["differences"] = {
            section: bounded_diff(expected[section], actual[section])
            for section, passed in checks.items()
            if not passed and section != "attributes"
        }
    return result


def ensure_within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exception:
        raise ValueError(f"source path escapes the read-only root: {resolved}") from exception
    return resolved


def load_targets(root: Path) -> tuple[dict[str, dict], list[str]]:
    snapshots: dict[str, dict] = {}
    duplicates: list[str] = []
    for path in sorted(root.glob("*.nbt")):
        entity = nbt.NBTFile(filename=str(path))
        snapshot = villager_snapshot(entity)
        identifier = snapshot["uuid"]
        if identifier in snapshots:
            duplicates.append(identifier)
        snapshots[identifier] = snapshot
    return snapshots, sorted(set(duplicates))


def load_expected(
    baseline: dict,
    source_root: Path,
    target_game_dir: Path,
    game_time: int,
) -> tuple[dict[str, dict], dict]:
    by_region: dict[Path, dict[int, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    baseline_by_uuid: dict[str, dict] = {}
    for record in baseline["villagers"]:
        identifier = record["uuid"]
        if identifier in baseline_by_uuid:
            raise ValueError(f"duplicate UUID in source baseline: {identifier}")
        baseline_by_uuid[identifier] = record
        region = ensure_within(Path(record["source"]["region"]), source_root)
        by_region[region][int(record["source"]["slot"])].add(identifier)

    audit = converter.new_audit(
        source_root,
        game_time,
        source_game_dir=source_root,
        target_game_dir=target_game_dir,
        runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
    )
    expected: dict[str, dict] = {}
    raw_source: dict[str, dict] = {}
    visited_slots: set[tuple[Path, int]] = set()
    for region, wanted_slots in sorted(by_region.items(), key=lambda pair: str(pair[0])):
        for slot, _offset, _sectors, compression, payload in converter.read_slots(region):
            if slot not in wanted_slots:
                continue
            visited_slots.add((region, slot))
            chunk = nbt.NBTFile(
                buffer=io.BytesIO(converter.decode(payload, compression))
            )
            wanted_uuids = wanted_slots[slot]
            for entity in chunk.get("Entities", []):
                if not isinstance(entity, nbt.TAG_Compound):
                    continue
                if converter.string_value(
                    entity.get("id", nbt.TAG_String(""))
                ) != "minecraft:villager":
                    continue
                snapshot = villager_snapshot(entity)
                identifier = snapshot["uuid"]
                if identifier not in wanted_uuids:
                    continue
                if identifier in expected:
                    raise ValueError(f"duplicate source entity UUID: {identifier}")
                raw_source[identifier] = snapshot
                converted = converter.clone_tag(entity)
                converter.convert_entity(converted, game_time, audit)
                expected[identifier] = villager_snapshot(converted)

    missing_slots = sorted(
        f"{region}:{slot}"
        for region, slots in by_region.items()
        for slot in slots
        if (region, slot) not in visited_slots
    )
    missing_entities = sorted(set(baseline_by_uuid) - set(expected))
    baseline_mismatches = []
    for identifier in sorted(set(baseline_by_uuid) & set(raw_source)):
        baseline_record = baseline_by_uuid[identifier]
        snapshot = raw_source[identifier]
        checks = {
            "position": compare_float_lists(
                baseline_record["position"], snapshot["position"], 1e-9
            ),
            "rotation": compare_float_lists(
                baseline_record["rotation"], snapshot["rotation"], 1e-9
            ),
            "villager_data": baseline_record["villager_data"]
            == snapshot["villager_data"],
            "xp": baseline_record["xp"] == snapshot["xp"],
        }
        if not all(checks.values()):
            baseline_mismatches.append({"uuid": identifier, "checks": checks})

    blockers = converter.collect_preflight_blockers(audit)
    metadata = {
        "baseline_villagers": len(baseline_by_uuid),
        "source_regions": len(by_region),
        "source_slots": sum(len(slots) for slots in by_region.values()),
        "visited_source_slots": len(visited_slots),
        "expected_loaded": len(expected),
        "missing_slots": missing_slots,
        "missing_entities": missing_entities,
        "baseline_mismatches": baseline_mismatches,
        "conversion": {
            "blockers": blockers,
            "attribute_aliases": len(audit["attribute_aliases"]),
            "legacy_attribute_containers": len(
                audit["legacy_attribute_containers"]
            ),
            "legacy_attribute_modifier_merges": len(
                audit["legacy_attribute_modifier_merges"]
            ),
            "attribute_alias_counts": dict(sorted(Counter(
                f"{row['source']} -> {row['target']}"
                for row in audit["attribute_aliases"]
            ).items())),
            "consumed_default_attributes": len(
                audit["consumed_default_attributes"]
            ),
            "retained_compatibility_attributes": len(
                audit["retained_compatibility_attributes"]
            ),
            "entity_item_stacks": len(audit["entity_item_stacks"]),
            "item_component_schema_aliases": len(
                audit["item_component_schema_aliases"]
            ),
            "item_component_schema_alias_counts": dict(sorted(Counter(
                row["component"]
                for row in audit["item_component_schema_aliases"]
            ).items())),
            "unsupported_entity_items": len(audit["unsupported_entity_items"]),
            "unsupported_attributes": len(audit["unsupported_attributes"]),
        },
    }
    return expected, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-dumps", type=Path, required=True)
    parser.add_argument("--target-game-dir", type=Path, required=True)
    parser.add_argument("--game-time", type=int, required=True)
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    expected, source = load_expected(
        baseline,
        source_root,
        args.target_game_dir.resolve(),
        args.game_time,
    )
    actual, target_duplicates = load_targets(args.target_dumps.resolve())
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    comparisons = {
        identifier: compare_snapshots(
            expected[identifier], actual[identifier], args.position_tolerance
        )
        for identifier in sorted(set(expected) & set(actual))
    }
    failed = {
        identifier: comparison
        for identifier, comparison in comparisons.items()
        if comparison["status"] != "PASS"
    }
    section_failures = Counter(
        section
        for comparison in failed.values()
        for section, passed in comparison["checks"].items()
        if not passed
    )
    allowed_default_counts = Counter(
        identifier
        for comparison in comparisons.values()
        for identifier in comparison["attributes"]["allowed_target_defaults"]
    )
    normalization_counts = Counter(
        name
        for comparison in comparisons.values()
        for name, applied in comparison["normalizations"].items()
        if applied
    )
    source_clean = (
        source["baseline_villagers"] == len(expected)
        and not source["missing_slots"]
        and not source["missing_entities"]
        and not source["baseline_mismatches"]
        and not source["conversion"]["blockers"]
    )
    passed = (
        source_clean
        and not target_duplicates
        and not missing
        and not extra
        and not failed
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "baseline": str(args.baseline.resolve()),
        "source_root": str(source_root),
        "target_dumps": str(args.target_dumps.resolve()),
        "target_game_dir": str(args.target_game_dir.resolve()),
        "game_time": args.game_time,
        "position_tolerance": args.position_tolerance,
        "source": source,
        "target": {
            "dumps_loaded": len(actual),
            "duplicate_uuids": target_duplicates,
            "missing": missing,
            "extra": extra,
        },
        "summary": {
            "expected": len(expected),
            "compared": len(comparisons),
            "passed": len(comparisons) - len(failed),
            "failed": len(failed),
            "section_failures": dict(sorted(section_failures.items())),
            "allowed_target_default_attribute_counts": dict(
                sorted(allowed_default_counts.items())
            ),
            "normalization_counts": dict(sorted(normalization_counts.items())),
        },
        "comparisons": comparisons,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "source": source,
        "target": report["target"],
        "summary": report["summary"],
        "report": str(args.report.resolve()),
    }, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
