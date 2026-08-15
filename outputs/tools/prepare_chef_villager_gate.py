from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import uuid
from pathlib import Path

from nbt import nbt

import convert_world_nbt as converter


SYNTHETIC_CHEF_UUIDS = {
    "00000000-0000-4000-8000-000000000101",
    "00000000-0000-4000-8000-000000000102",
    "00000000-0000-4000-8000-000000000103",
    "00000000-0000-4000-8000-000000000104",
}


def configured_chef_uuids() -> set[str]:
    """Read local-only fixture IDs without committing real entity identities."""
    raw = os.environ.get("MIGRATION_CHEF_UUIDS", "")
    if not raw.strip():
        return set(SYNTHETIC_CHEF_UUIDS)
    values = {item.strip().lower() for item in raw.split(",") if item.strip()}
    if len(values) != 4:
        raise SystemExit("MIGRATION_CHEF_UUIDS must contain exactly four UUIDs")
    for value in values:
        uuid.UUID(value)
    return values


CHEF_UUIDS = configured_chef_uuids()


def canonical_uuid(value) -> str:
    parts = [int(part) & 0xFFFFFFFF for part in value.value]
    return str(uuid.UUID(bytes=struct.pack(">4I", *parts)))


def json_value(value):
    if isinstance(value, nbt.TAG_Compound):
        return {key: json_value(child) for key, child in sorted(value.items())}
    if isinstance(value, nbt.TAG_List):
        return [json_value(child) for child in value]
    if isinstance(value, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)):
        return [int(child) for child in value.value]
    if isinstance(value, nbt.TAG):
        return value.value
    return value


def critical_snapshot(entity):
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
    return {
        "uuid": canonical_uuid(entity["UUID"]),
        "position": [float(value.value) for value in entity["Pos"]],
        "rotation": [float(value.value) for value in entity["Rotation"]],
        "villager_data": json_value(entity["VillagerData"]),
        "xp": int(entity["Xp"].value),
        "offers": json_value(entity["Offers"]),
        "brain": json_value(entity["Brain"]),
        "attributes": dict(sorted(attributes.items())),
        "state": {
            key: json_value(entity[key])
            for key in ("Age", "Health", "LastRestock", "RestocksToday", "Willing")
            if key in entity
        },
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--game-time", type=int, required=True)
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--target-game-dir", type=Path, required=True)
    args = parser.parse_args()

    inputs = sorted(args.input.glob("*.nbt"))
    found = {path.stem for path in inputs}
    if found != CHEF_UUIDS:
        raise SystemExit(f"chef fixture UUID mismatch: expected={sorted(CHEF_UUIDS)} actual={sorted(found)}")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for source_path in inputs:
        source = nbt.NBTFile(filename=str(source_path))
        source_snapshot = critical_snapshot(source)
        if source_snapshot["uuid"] != source_path.stem:
            raise SystemExit(f"fixture filename/UUID mismatch: {source_path}")
        if source_snapshot["villager_data"].get("profession") != "kaleidoscope_cookery:chef":
            raise SystemExit(f"fixture is not a Cookery chef: {source_path}")

        audit = converter.new_audit(
            args.input,
            args.game_time,
            target_game_dir=args.target_game_dir,
            source_game_dir=args.source_game_dir,
        )
        changed = converter.convert_entity(source, args.game_time, audit)
        blockers = converter.collect_preflight_blockers(audit)
        if blockers:
            raise SystemExit(f"conversion blocked for {source_path.name}: {blockers}")
        target_snapshot = critical_snapshot(source)
        expected_aliases = {
            "minecraft:generic.follow_range",
            "minecraft:generic.movement_speed",
        }
        if not expected_aliases.issubset(target_snapshot["attributes"]):
            raise SystemExit(f"required attribute aliases missing for {source_path.name}")

        # Test-only freeze: it prevents AI, gravity and residual velocity from
        # changing the coordinates while the server save/restart gate runs.
        source["NoAI"] = nbt.TAG_Byte(1)
        source["NoGravity"] = nbt.TAG_Byte(1)
        source["Invulnerable"] = nbt.TAG_Byte(1)
        source["Motion"] = converter.list_tag(
            [nbt.TAG_Double(0.0), nbt.TAG_Double(0.0), nbt.TAG_Double(0.0)],
            nbt.TAG_Double,
        )

        output_path = args.output / source_path.name
        source.write_file(filename=str(output_path))
        round_trip = nbt.NBTFile(filename=str(output_path))
        if critical_snapshot(round_trip) != target_snapshot:
            raise SystemExit(f"fixture round-trip changed critical data: {source_path.name}")

        second_audit = converter.new_audit(
            args.output,
            args.game_time,
            target_game_dir=args.target_game_dir,
            source_game_dir=args.source_game_dir,
        )
        second_changed = converter.convert_entity(round_trip, args.game_time, second_audit)
        second_blockers = converter.collect_preflight_blockers(second_audit)
        if second_changed or second_blockers:
            raise SystemExit(
                f"fixture conversion is not idempotent for {source_path.name}: "
                f"changed={second_changed} blockers={second_blockers}"
            )

        records.append({
            "uuid": source_path.stem,
            "source": str(source_path),
            "output": str(output_path),
            "source_sha256": sha256(source_path),
            "output_sha256": sha256(output_path),
            "changed": changed,
            "attribute_aliases": audit["attribute_aliases"],
            "entity_item_stacks": audit["entity_item_stacks"],
            "source_snapshot": source_snapshot,
            "target_snapshot": target_snapshot,
            "test_instrumentation": {
                "NoAI": 1,
                "NoGravity": 1,
                "Invulnerable": 1,
                "Motion": [0.0, 0.0, 0.0],
            },
            "idempotent": True,
        })

    report = {
        "status": "PASS",
        "fixture_count": len(records),
        "required_uuids": sorted(CHEF_UUIDS),
        "records": records,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "fixtures": len(records),
        "attribute_aliases": sum(len(record["attribute_aliases"]) for record in records),
        "entity_item_stacks": sum(len(record["entity_item_stacks"]) for record in records),
        "report": str(args.report),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
