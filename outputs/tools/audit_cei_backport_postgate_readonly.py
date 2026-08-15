#!/usr/bin/env python3
"""Fail-closed, read-only post-gate audit for the CEI 2.5.1 backport.

This tool never starts Java or Minecraft and never writes below a world or
runtime directory.  ``prepare`` locks the two production Blaze Forgers.
``verify`` consumes a stopped-gate result, checks the backport JAR statically,
rescans the saved world, and proves both legacy Forger preservation and the
new 2.5.1 persistence fixtures.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any


MOD_ID = "create_enchantment_industry"
FORGER_ID = f"{MOD_ID}:blaze_forger"
COMPOSER_ID = f"{MOD_ID}:blaze_composer"
MODE_NAMES = {0: "MERGE", 1: "APPLY", 2: "EXTRACT"}

LOCKED_FORGERS = (
    {
        "dimension": "minecraft:overworld",
        "position": [-176, 63, -127],
        "region_file": "region/r.-1.-1.mca",
        "chunk": [-11, -8],
    },
    {
        "dimension": "minecraft:overworld",
        "position": [27319, 72, -12892],
        "region_file": "region/r.53.-26.mca",
        "chunk": [1707, -806],
    },
)

EXPECTED_NEW_REGISTRY = {
    "block": [COMPOSER_ID],
    "block_item": [COMPOSER_ID],
    "block_entity": [COMPOSER_ID],
    "item": [
        f"{MOD_ID}:incomplete_brass_affix_template",
        f"{MOD_ID}:incomplete_crystal_affix_template",
        f"{MOD_ID}:incomplete_apotheotic_affix_template",
    ],
    "data_component_type": [
        f"{MOD_ID}:affix_template",
        f"{MOD_ID}:overlimit_affixes",
    ],
    "custom_stat": [f"{MOD_ID}:compose_affix"],
    "creative_mode_tab": [f"{MOD_ID}:apotheotic"],
    "arm_interaction_point": ["blaze_composer"],
    "data_map": ["enchantment_processing/rules"],
    "custom_registry_key": [f"{MOD_ID}:printing_behaviour"],
    "printing_behaviour_providers": [
        "package_address",
        "package_pattern",
        "copy",
        "custom_name",
        "enchanted_book",
        "written_book",
        "banner_pattern",
    ],
}

STATIC_REQUIRED_ENTRIES = (
    "assets/create_enchantment_industry/blockstates/blaze_composer.json",
    "assets/create_enchantment_industry/models/item/blaze_composer.json",
    "assets/create_enchantment_industry/models/item/incomplete_brass_affix_template.json",
    "assets/create_enchantment_industry/models/item/incomplete_crystal_affix_template.json",
    "assets/create_enchantment_industry/models/item/incomplete_apotheotic_affix_template.json",
    "data/create_enchantment_industry/loot_table/blocks/blaze_composer.json",
    "data/create_enchantment_industry/recipe/smithing/blaze_composer.json",
    "data/create_enchantment_industry/advancement/recipes/misc/smithing/blaze_composer.json",
    "data/create_enchantment_industry/recipe/sequenced_assembly/brass_affix_template.json",
    "data/create_enchantment_industry/recipe/sequenced_assembly/crystal_affix_template.json",
    "data/create_enchantment_industry/recipe/sequenced_assembly/apotheotic_affix_template.json",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/BlazeComposerBlock.class",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/BlazeComposerBlockEntity.class",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/BlazeComposerInventory.class",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/template/AffixTemplateData.class",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/OverlimitAffixes.class",
)

STATIC_CLASS_TOKENS = {
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXBlocks.class": [
        "blaze_composer"
    ],
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXBlockEntities.class": [
        "blaze_composer"
    ],
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXItems.class": [
        "incomplete_brass_affix_template",
        "incomplete_crystal_affix_template",
        "incomplete_apotheotic_affix_template",
    ],
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXDataComponents.class": [
        "affix_template",
        "overlimit_affixes",
    ],
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXStats.class": [
        "compose_affix"
    ],
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXCreativeModeTabs.class": [
        "APOTHEOTIC"
    ],
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXArmInteractionPoints.class": [
        "blaze_composer"
    ],
    "plus/dragons/createenchantmentindustry/api/registry/CEIRegistries.class": [
        "printing_behaviour"
    ],
    "plus/dragons/createenchantmentindustry/common/registry/CEIDataMaps.class": [
        "enchantment_processing/rules"
    ],
    "plus/dragons/createenchantmentindustry/common/fluids/printer/behaviour/CEIPrintingBehaviours.class": [
        "package_address",
        "package_pattern",
        "copy",
        "custom_name",
        "enchanted_book",
        "written_book",
        "banner_pattern",
    ],
    "plus/dragons/createenchantmentindustry/common/processing/forger/BlazeForgerBlockEntity.class": [
        "ForgingMode"
    ],
    "plus/dragons/createenchantmentindustry/common/processing/forger/BlazeForgerInventory.class": [
        "Mode",
        "Operation",
    ],
}

FATAL_LOG_PATTERNS = {
    "mod_loading_exception": r"ModLoadingException",
    "registry_missing": r"Registry Object not present|Missing.*registry|Unknown registry element",
    "server_tick_crash": r"Exception in server tick loop",
    "failed_start": r"Failed to start the minecraft server|Errors during loading",
    "crash_report": r"---- Minecraft Crash Report ----",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest().upper()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def file_stamp(path: Path, include_hash: bool = True) -> dict[str, Any]:
    stat = path.stat()
    result = {
        "path": str(path.resolve()),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    if include_hash:
        result["sha256"] = sha256(path)
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_scanner(path: Path):
    scanner_path = path.resolve()
    if not scanner_path.is_file():
        raise FileNotFoundError(f"CEI world scanner not found: {scanner_path}")
    sys.path.insert(0, str(scanner_path.parent))
    return importlib.import_module(scanner_path.stem)


def check(checks: list[dict[str, Any]], check_id: str, passed: bool, evidence: Any) -> bool:
    checks.append({"id": check_id, "pass": bool(passed), "evidence": evidence})
    return bool(passed)


def normalize_position(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    if not all(isinstance(item, (int, float)) for item in value):
        return None
    return tuple(int(item) for item in value)


def inventory_snapshot(block_entity_nbt: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    inventory = block_entity_nbt.get("Inventory")
    if not isinstance(inventory, dict):
        return {
            "valid": False,
            "errors": ["Inventory compound is absent or not a compound"],
            "size": None,
            "slots": [],
        }
    size = inventory.get("Size")
    if not isinstance(size, int):
        errors.append(f"Inventory.Size is not an int: {size!r}")
        slot_count = 0
    else:
        slot_count = max(0, int(size))
    raw_items = inventory.get("Items")
    if not isinstance(raw_items, list):
        errors.append("Inventory.Items is absent or not a list")
        raw_items = []
    by_slot: dict[int, Any] = {}
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            errors.append(f"Inventory.Items[{index}] is not a compound")
            continue
        slot = raw.get("Slot", raw.get("slot"))
        if not isinstance(slot, int):
            errors.append(f"Inventory.Items[{index}] has no integer Slot")
            continue
        slot = int(slot)
        if slot < 0 or slot >= slot_count:
            errors.append(f"Inventory.Items[{index}] Slot={slot} is outside Size={slot_count}")
            continue
        if slot in by_slot:
            errors.append(f"Inventory.Items has duplicate Slot={slot}")
            continue
        content = {str(key): value for key, value in raw.items() if str(key) not in {"Slot", "slot"}}
        by_slot[slot] = content
    slots = []
    for slot in range(slot_count):
        content = by_slot.get(slot)
        state = {"empty": content is None}
        if content is not None:
            state["item_stack"] = content
        slots.append(
            {
                "slot": slot,
                **state,
                "content_sha256": digest_value(state),
            }
        )
    result = {
        "valid": not errors,
        "errors": errors,
        "size": size,
        "items_list_count": len(raw_items),
        "slots": slots,
        "slots_sha256": digest_value(slots),
        "fields": {
            "Mode": {"present": "Mode" in inventory, "value": inventory.get("Mode")},
            "Operation": {
                "present": "Operation" in inventory,
                "value": inventory.get("Operation"),
            },
            "ForgingMode": {
                "present": "ForgingMode" in block_entity_nbt,
                "value": block_entity_nbt.get("ForgingMode"),
            },
        },
    }
    present_modes = [
        field["value"]
        for field in result["fields"].values()
        if field["present"] and isinstance(field["value"], int)
    ]
    result["effective_mode"] = present_modes[0] if present_modes else 0
    result["effective_mode_name"] = MODE_NAMES.get(result["effective_mode"], "INVALID")
    return result


def scan_locked_regions(world: Path, scanner: Any, targets: list[dict[str, Any]]) -> dict[str, Any]:
    region_results: dict[str, Any] = {}
    metadata_changes: list[dict[str, Any]] = []
    for relative in sorted({str(target["region_file"]) for target in targets}):
        path = world / Path(relative)
        if not path.is_file():
            region_results[relative] = {"error": f"region file not found: {path}"}
            continue
        before = file_stamp(path)
        result = scanner.scan_region_file(str(path), str(world))
        after = file_stamp(path)
        if before != after:
            metadata_changes.append({"file": relative, "before": before, "after": after})
        region_results[relative] = result
    snapshots: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for target in targets:
        relative = str(target["region_file"])
        result = region_results.get(relative, {})
        if result.get("error"):
            errors.append({"target": target, "error": result["error"]})
            continue
        errors.extend(result.get("parse_errors", []))
        wanted = normalize_position(target["position"])
        block_states = [
            item
            for item in result.get("scan", {}).get("block_states", [])
            if normalize_position(item.get("position")) == wanted
        ]
        block_entities = [
            item
            for item in result.get("scan", {}).get("block_entities", [])
            if normalize_position(item.get("position")) == wanted
        ]
        if len(block_states) != 1 or len(block_entities) != 1:
            errors.append(
                {
                    "target": target,
                    "error": "expected exactly one CEI block state and one CEI block entity",
                    "block_state_count": len(block_states),
                    "block_entity_count": len(block_entities),
                }
            )
            continue
        block = block_states[0]
        block_entity = block_entities[0]
        nbt = block_entity.get("nbt")
        if not isinstance(nbt, dict):
            errors.append({"target": target, "error": "block entity NBT is unavailable/truncated"})
            continue
        snapshots.append(
            {
                "dimension": target["dimension"],
                "position": list(wanted),
                "chunk": target["chunk"],
                "region_file": relative,
                "region_manifest": result.get("manifest"),
                "block": {
                    "id": block.get("block_id"),
                    "properties": block.get("properties", {}),
                    "state_sha256": digest_value(
                        {"id": block.get("block_id"), "properties": block.get("properties", {})}
                    ),
                },
                "block_entity": {
                    "id": block_entity.get("block_entity_id"),
                    "nbt": nbt,
                    "nbt_sha256": digest_value(nbt),
                    "stable_identity": {
                        key: nbt.get(key)
                        for key in ("id", "x", "y", "z", "Owner", "isCreative")
                    },
                    "inventory": inventory_snapshot(nbt),
                },
            }
        )
    return {
        "snapshots": sorted(snapshots, key=lambda item: item["position"]),
        "errors": errors,
        "metadata_snapshot_changed_during_scan": bool(metadata_changes),
        "metadata_changes": metadata_changes,
    }


def extract_expected_registry(jar_audit: dict[str, Any] | None) -> dict[str, Any]:
    if jar_audit:
        candidate = jar_audit.get("registry", {}).get("new")
        if isinstance(candidate, dict) and candidate:
            return candidate
    return EXPECTED_NEW_REGISTRY


def prepare_baseline(args: argparse.Namespace) -> int:
    world = args.world.resolve()
    if not world.is_dir():
        raise SystemExit(f"world root does not exist: {world}")
    scanner = load_scanner(args.scanner)
    jar_audit = load_json(args.jar_audit.resolve()) if args.jar_audit else None
    target_scan = scan_locked_regions(world, scanner, list(LOCKED_FORGERS))
    checks: list[dict[str, Any]] = []
    check(checks, "locked_forger_count", len(target_scan["snapshots"]) == 2, len(target_scan["snapshots"]))
    check(checks, "target_region_parse", not target_scan["errors"], target_scan["errors"])
    check(
        checks,
        "world_static_during_scan",
        not target_scan["metadata_snapshot_changed_during_scan"],
        target_scan["metadata_changes"],
    )
    for snapshot in target_scan["snapshots"]:
        key = ",".join(map(str, snapshot["position"]))
        inventory = snapshot["block_entity"]["inventory"]
        check(checks, f"{key}:block_id", snapshot["block"]["id"] == FORGER_ID, snapshot["block"])
        check(
            checks,
            f"{key}:block_entity_id",
            snapshot["block_entity"]["id"] == FORGER_ID,
            snapshot["block_entity"]["id"],
        )
        check(checks, f"{key}:inventory_valid", inventory["valid"], inventory["errors"])
        check(checks, f"{key}:inventory_size_6", inventory["size"] == 6, inventory["size"])
        check(checks, f"{key}:slot_count_6", len(inventory["slots"]) == 6, len(inventory["slots"]))
    passed = all(item["pass"] for item in checks)
    payload = {
        "schema": 1,
        "kind": "CEI_BACKPORT_POSTGATE_BASELINE_LOCK",
        "generated_at_utc": utc_now(),
        "status": "PASS_BASELINE_LOCKED" if passed else "FAIL_BASELINE_NOT_LOCKED",
        "scope": {
            "minecraft": "1.21.1",
            "loader": "NeoForge",
            "mod_id": MOD_ID,
            "read_only": True,
            "minecraft_or_java_started": False,
            "world_files_written": False,
        },
        "world": {
            "root_at_capture": str(world),
            "level_dat": file_stamp(world / "level.dat") if (world / "level.dat").is_file() else None,
        },
        "locked_forgers": target_scan["snapshots"],
        "expected_new_251_registry": extract_expected_registry(jar_audit),
        "recommended_backport_version": (
            jar_audit.get("recommended_release", {}).get("version") if jar_audit else None
        )
        or "2.4.2-cei251-backport.1",
        "policy": {
            "inventory_slots_must_remain_exact": True,
            "inventory_size_must_remain": 6,
            "post_save_required_fields": ["ForgingMode", "Inventory.Operation", "Inventory.Mode"],
            "post_save_mode_values_must_match": True,
            "new_251_world_fixtures_required": True,
            "missing_fixture_is_failure_not_a_skip": True,
        },
        "checks": checks,
        "scan_errors": target_scan["errors"],
        "metadata_changes": target_scan["metadata_changes"],
    }
    payload["baseline_payload_sha256"] = digest_value(payload)
    write_json(args.output.resolve(), payload)
    print(json.dumps({"status": payload["status"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if passed else 2


def metadata_mod_id_and_version(zf: zipfile.ZipFile) -> tuple[str | None, str | None, str | None]:
    for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        if name not in zf.namelist():
            continue
        text = zf.read(name).decode("utf-8", "replace")
        mod_match = re.search(r'(?m)^\s*modId\s*=\s*["\']([^"\']+)["\']', text)
        version_match = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', text)
        return (
            mod_match.group(1) if mod_match else None,
            version_match.group(1) if version_match else None,
            name,
        )
    return None, None, None


def static_jar_audit(jar: Path, expected_version: str, mods_dir: Path | None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if not jar.is_file():
        check(checks, "backport_jar_exists", False, str(jar))
        return {"status": "FAIL", "checks": checks}
    check(checks, "backport_jar_exists", True, str(jar))
    result: dict[str, Any] = {"jar": file_stamp(jar), "checks": checks}
    try:
        with zipfile.ZipFile(jar) as zf:
            bad = zf.testzip()
            check(checks, "jar_zip_integrity", bad is None, bad)
            mod_id, version, metadata_path = metadata_mod_id_and_version(zf)
            result["metadata"] = {"path": metadata_path, "mod_id": mod_id, "version": version}
            check(checks, "jar_mod_id", mod_id == MOD_ID, result["metadata"])
            check(checks, "jar_version", version == expected_version, {"expected": expected_version, "actual": version})
            names = set(zf.namelist())
            missing_entries = [name for name in STATIC_REQUIRED_ENTRIES if name not in names]
            check(checks, "new_251_archive_entries", not missing_entries, {"missing": missing_entries})
            token_failures = []
            token_passes = []
            for entry, tokens in STATIC_CLASS_TOKENS.items():
                if entry not in names:
                    token_failures.append({"entry": entry, "missing_entry": True, "missing_tokens": tokens})
                    continue
                data = zf.read(entry)
                missing = [token for token in tokens if token.encode("utf-8") not in data]
                if missing:
                    token_failures.append({"entry": entry, "missing_tokens": missing})
                else:
                    token_passes.append({"entry": entry, "tokens": tokens})
            check(
                checks,
                "new_251_registry_and_forger_bridge_literals",
                not token_failures,
                {"failures": token_failures, "passes": token_passes},
            )
    except Exception as exc:
        check(checks, "jar_read", False, f"{type(exc).__name__}: {exc}")
    if mods_dir is not None:
        duplicates = []
        errors = []
        if not mods_dir.is_dir():
            check(checks, "mods_dir_exists", False, str(mods_dir))
        else:
            for candidate in sorted(mods_dir.glob("*.jar")):
                try:
                    with zipfile.ZipFile(candidate) as zf:
                        candidate_mod, candidate_version, _ = metadata_mod_id_and_version(zf)
                    if candidate_mod == MOD_ID:
                        duplicates.append(
                            {
                                "path": str(candidate.resolve()),
                                "version": candidate_version,
                                "sha256": sha256(candidate),
                            }
                        )
                except Exception as exc:
                    errors.append({"path": str(candidate), "error": f"{type(exc).__name__}: {exc}"})
            expected_hash = result.get("jar", {}).get("sha256")
            exact = [item for item in duplicates if item["sha256"] == expected_hash]
            check(
                checks,
                "single_active_cei_jar",
                len(duplicates) == 1 and len(exact) == 1,
                {"cei_jars": duplicates, "unreadable_jars": errors},
            )
    result["status"] = "PASS" if all(item["pass"] for item in checks) else "FAIL"
    return result


def resolve_gate_path(gate: dict[str, Any], names: tuple[str, ...]) -> Path | None:
    containers = [gate, gate.get("artifacts", {}), gate.get("paths", {})]
    for container in containers:
        if not isinstance(container, dict):
            continue
        for name in names:
            value = container.get(name)
            if isinstance(value, str) and value.strip():
                return Path(value).resolve()
    return None


def gate_preconditions(gate: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    accepted = {"COMPLETE_STOPPED", "PASS_STOPPED", "GATE_COMPLETE_STOPPED"}
    status = str(gate.get("status", "")).upper()
    check(checks, "gate_status_complete_stopped", status in accepted, status)
    for field in ("server_stopped", "startup_reached_done", "clean_stop", "world_saved"):
        check(checks, f"gate_{field}", gate.get(field) is True, gate.get(field))
    running = gate.get("minecraft_or_java_running")
    check(checks, "gate_no_running_minecraft_or_java", running is False, running)
    return checks


def compare_forgers(
    baseline: dict[str, Any], post_scan: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    baseline_map = {
        tuple(item["position"]): item for item in baseline.get("locked_forgers", [])
    }
    post_map = {tuple(item["position"]): item for item in post_scan.get("snapshots", [])}
    expected_modes = gate.get("fixtures", {}).get("forger_expected_modes", {})
    comparisons = []
    for position in sorted(baseline_map):
        key = ",".join(map(str, position))
        before = baseline_map[position]
        after = post_map.get(position)
        check(checks, f"{key}:present_after_gate", after is not None, after and after["block_entity"]["id"])
        if after is None:
            continue
        before_inventory = before["block_entity"]["inventory"]
        after_inventory = after["block_entity"]["inventory"]
        expected_mode = expected_modes.get(key, before_inventory.get("effective_mode", 0))
        mode_fields = after_inventory.get("fields", {})
        mode_evidence = {
            name: mode_fields.get(name) for name in ("ForgingMode", "Operation", "Mode")
        }
        all_present = all(
            isinstance(mode_fields.get(name), dict) and mode_fields[name].get("present")
            for name in ("ForgingMode", "Operation", "Mode")
        )
        values = [mode_fields.get(name, {}).get("value") for name in ("ForgingMode", "Operation", "Mode")]
        check(checks, f"{key}:block_id", after["block"]["id"] == FORGER_ID, after["block"])
        check(checks, f"{key}:block_state_preserved", after["block"] == before["block"], {"before": before["block"], "after": after["block"]})
        check(
            checks,
            f"{key}:stable_identity_preserved",
            after["block_entity"]["stable_identity"] == before["block_entity"]["stable_identity"],
            {"before": before["block_entity"]["stable_identity"], "after": after["block_entity"]["stable_identity"]},
        )
        check(checks, f"{key}:inventory_valid", after_inventory.get("valid") is True, after_inventory.get("errors"))
        check(checks, f"{key}:inventory_size_6", after_inventory.get("size") == 6, after_inventory.get("size"))
        check(checks, f"{key}:six_slots", len(after_inventory.get("slots", [])) == 6, len(after_inventory.get("slots", [])))
        check(
            checks,
            f"{key}:slot_contents_exact",
            after_inventory.get("slots_sha256") == before_inventory.get("slots_sha256"),
            {
                "before_sha256": before_inventory.get("slots_sha256"),
                "after_sha256": after_inventory.get("slots_sha256"),
                "before_slots": before_inventory.get("slots"),
                "after_slots": after_inventory.get("slots"),
            },
        )
        check(checks, f"{key}:dual_write_fields_present", all_present, mode_evidence)
        check(
            checks,
            f"{key}:mode_fields_consistent",
            all_present and all(value == expected_mode for value in values),
            {"expected": expected_mode, "expected_name": MODE_NAMES.get(expected_mode), "fields": mode_evidence},
        )
        comparisons.append(
            {
                "position": list(position),
                "expected_mode": expected_mode,
                "before_inventory_sha256": before_inventory.get("slots_sha256"),
                "after_inventory_sha256": after_inventory.get("slots_sha256"),
                "post_mode_fields": mode_evidence,
                "before_nbt_sha256": before["block_entity"].get("nbt_sha256"),
                "after_nbt_sha256": after["block_entity"].get("nbt_sha256"),
            }
        )
    check(
        checks,
        "locked_region_static_during_scan",
        not post_scan.get("metadata_snapshot_changed_during_scan"),
        post_scan.get("metadata_changes"),
    )
    check(checks, "locked_region_parse", not post_scan.get("errors"), post_scan.get("errors"))
    return {
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "checks": checks,
        "comparisons": comparisons,
    }


def dynamic_persistence_audit(world_scan: dict[str, Any]) -> dict[str, Any]:
    records = world_scan.get("records", {})
    block_states = records.get("block_states", [])
    block_entities = records.get("block_entities", [])
    item_stacks = records.get("item_stacks", [])
    occurrences = records.get("namespace_occurrences", [])
    checks: list[dict[str, Any]] = []
    composer_blocks = [item for item in block_states if item.get("block_id") == COMPOSER_ID]
    composer_bes = [item for item in block_entities if item.get("block_entity_id") == COMPOSER_ID]
    composer_mode_bes = [
        item
        for item in composer_bes
        if isinstance(item.get("nbt"), dict) and "BlazeComposerMode" in item["nbt"]
    ]
    check(checks, "saved_blaze_composer_block", bool(composer_blocks), composer_blocks)
    check(checks, "saved_blaze_composer_block_entity", bool(composer_bes), composer_bes)
    check(
        checks,
        "saved_blaze_composer_mode_field",
        bool(composer_mode_bes),
        [
            {"position": item.get("position"), "BlazeComposerMode": item.get("nbt", {}).get("BlazeComposerMode")}
            for item in composer_bes
        ],
    )
    item_hits: dict[str, list[dict[str, Any]]] = {}
    for item_id in EXPECTED_NEW_REGISTRY["item"]:
        hits = [item for item in item_stacks if item.get("item_id") == item_id]
        item_hits[item_id] = hits
        check(checks, f"saved_item:{item_id}", bool(hits), hits)
    component_hits: dict[str, list[dict[str, Any]]] = {}
    for component_id in EXPECTED_NEW_REGISTRY["data_component_type"]:
        hits = [
            item
            for item in item_stacks
            if component_id in item.get("cei_tokens_in_components", [])
        ]
        component_hits[component_id] = hits
        check(checks, f"saved_component:{component_id}", bool(hits), hits)
    stat_id = EXPECTED_NEW_REGISTRY["custom_stat"][0]
    stat_hits = [
        item
        for item in occurrences
        if item.get("token") == stat_id and item.get("source_kind") == "stats_json"
    ]
    check(checks, f"saved_custom_stat:{stat_id}", bool(stat_hits), stat_hits)
    advancement_token = f"{MOD_ID}:recipes/misc/smithing/blaze_composer"
    advancement_hits = [
        item
        for item in occurrences
        if item.get("token") == advancement_token and item.get("source_kind") == "advancement_json"
    ]
    check(
        checks,
        f"saved_recipe_advancement:{advancement_token}",
        bool(advancement_hits),
        advancement_hits,
    )
    check(
        checks,
        "full_world_scan_read_only",
        world_scan.get("status") == "PASS_READ_ONLY",
        {
            "status": world_scan.get("status"),
            "parse_errors": world_scan.get("parse_errors"),
            "decode_errors": records.get("decode_errors"),
            "read_only_contract": world_scan.get("read_only_contract"),
        },
    )
    return {
        "status": "PASS" if all(item["pass"] for item in checks) else "FAIL_MISSING_OR_UNREADABLE_2_5_FIXTURE",
        "checks": checks,
        "summary": {
            "composer_blocks": len(composer_blocks),
            "composer_block_entities": len(composer_bes),
            "items": {key: len(value) for key, value in item_hits.items()},
            "components": {key: len(value) for key, value in component_hits.items()},
            "compose_affix_stats": len(stat_hits),
            "blaze_composer_recipe_advancements": len(advancement_hits),
        },
    }


def log_audit(path: Path | None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if path is None or not path.is_file():
        check(checks, "gate_log_exists", False, str(path) if path else None)
        return {"status": "FAIL", "checks": checks}
    data = path.read_bytes()
    text = data.decode("utf-8", "replace")
    check(checks, "gate_log_exists", True, file_stamp(path))
    check(checks, "gate_log_reached_done", re.search(r'Done \([0-9.]+s\)!', text) is not None, "Done (...)!")
    check(checks, "gate_log_clean_stop", "Stopping server" in text, "Stopping server")
    fatal_hits = {
        name: [match.group(0) for match in re.finditer(pattern, text, re.IGNORECASE)][:20]
        for name, pattern in FATAL_LOG_PATTERNS.items()
    }
    fatal_hits = {name: hits for name, hits in fatal_hits.items() if hits}
    check(checks, "gate_log_no_fatal_patterns", not fatal_hits, fatal_hits)
    return {"status": "PASS" if all(item["pass"] for item in checks) else "FAIL", "checks": checks}


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# CEI backport 启动门禁后只读复核",
        "",
        f"- 结论：`{report['status']}`",
        f"- 生成时间：`{report['generated_at_utc']}`",
        f"- 世界：`{report.get('inputs', {}).get('world')}`",
        f"- backport JAR：`{report.get('inputs', {}).get('backport_jar')}`",
        "- 执行契约：未启动 Java/Minecraft；未写世界或 runtime；仅写本报告目录。",
        "",
        "## 分项",
        "",
    ]
    sections = [
        ("门禁状态", report.get("gate_preconditions", {})),
        ("JAR 静态注册", report.get("static_jar", {})),
        ("两台 Blaze Forger", report.get("forgers", {})),
        ("2.5 新内容存档读取", report.get("dynamic_persistence", {})),
        ("启动日志", report.get("log", {})),
    ]
    for title, section in sections:
        lines.extend([f"### {title}", "", f"状态：`{section.get('status', 'UNKNOWN')}`", ""])
        for item in section.get("checks", []):
            mark = "PASS" if item.get("pass") else "FAIL"
            lines.append(f"- `{mark}` `{item.get('id')}`")
        lines.append("")
    dynamic = report.get("dynamic_persistence", {}).get("summary")
    if dynamic:
        lines.extend(["## 2.5 持久化命中计数", "", "```json", json.dumps(dynamic, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(
        [
            "## 判定规则",
            "",
            "- 任一生产 Forger 丢失、`Inventory.Size != 6`、任一槽位变化，直接阻断。",
            "- 门禁保存后必须同时存在且一致：`ForgingMode`、`Inventory.Operation`、`Inventory.Mode`。",
            "- 仅有启动成功不算 2.5 持久化通过；必须在门禁副本中命中 Blaze Composer、三种 incomplete 模板、两个数据组件、compose_affix 统计及配方进度。",
            "- 全世界扫描中如有解析错误、解码错误或扫描期间文件元数据变化，直接阻断。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def verify(args: argparse.Namespace) -> int:
    baseline_path = args.baseline.resolve()
    gate_path = args.gate_result.resolve()
    baseline = load_json(baseline_path)
    gate = load_json(gate_path)
    output_dir = args.out_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preconditions = gate_preconditions(gate)
    precondition_section = {
        "status": "PASS" if all(item["pass"] for item in preconditions) else "FAIL",
        "checks": preconditions,
    }
    world = args.world.resolve() if args.world else resolve_gate_path(gate, ("world_root", "world"))
    jar = args.backport_jar.resolve() if args.backport_jar else resolve_gate_path(gate, ("backport_jar", "cei_backport_jar"))
    mods_dir = args.mods_dir.resolve() if args.mods_dir else resolve_gate_path(gate, ("mods_dir",))
    log_path = args.log.resolve() if args.log else resolve_gate_path(gate, ("server_log", "latest_log", "log"))
    path_checks: list[dict[str, Any]] = []
    check(path_checks, "post_world_path", world is not None and world.is_dir(), str(world) if world else None)
    check(path_checks, "backport_jar_path", jar is not None and jar.is_file(), str(jar) if jar else None)
    precondition_section["checks"].extend(path_checks)
    precondition_section["status"] = "PASS" if all(item["pass"] for item in precondition_section["checks"]) else "FAIL"
    if precondition_section["status"] != "PASS":
        report = {
            "schema": 1,
            "generated_at_utc": utc_now(),
            "status": "BLOCKED_GATE_INCOMPLETE",
            "scope": {"read_only": True, "minecraft_or_java_started": False, "world_files_written": False},
            "inputs": {"baseline": str(baseline_path), "gate_result": str(gate_path)},
            "gate_preconditions": precondition_section,
        }
        report["report_payload_sha256"] = digest_value(report)
        write_json(output_dir / "CEI-backport-postgate-readonly-result.json", report)
        write_markdown(output_dir / "CEI-backport-postgate-readonly-result.md", report)
        print(json.dumps({"status": report["status"], "out_dir": str(output_dir)}, ensure_ascii=False))
        return 2
    assert world is not None and jar is not None
    expected_version = str(
        gate.get("expected_backport_version")
        or baseline.get("recommended_backport_version")
        or "2.4.2-cei251-backport.1"
    )
    scanner = load_scanner(args.scanner)
    static = static_jar_audit(jar, expected_version, mods_dir)
    target_scan = scan_locked_regions(world, scanner, baseline.get("locked_forgers", list(LOCKED_FORGERS)))
    forgers = compare_forgers(baseline, target_scan, gate)
    progress = output_dir / "world-scan-progress.json"
    world_scan = scanner.scan_world(world, args.workers, progress, "cei_backport_postgate")
    world_scan_path = output_dir / "postgate-cei-world-scan.json"
    write_json(world_scan_path, world_scan)
    dynamic = dynamic_persistence_audit(world_scan)
    log_result = log_audit(log_path)
    passed = all(
        section.get("status") == "PASS"
        for section in (precondition_section, static, forgers, dynamic, log_result)
    )
    report = {
        "schema": 1,
        "generated_at_utc": utc_now(),
        "status": "PASS_POSTGATE_CEI_BACKPORT_READONLY" if passed else "FAIL_POSTGATE_CEI_BACKPORT_BLOCKED",
        "scope": {
            "minecraft": "1.21.1",
            "loader": "NeoForge",
            "mod_id": MOD_ID,
            "read_only": True,
            "minecraft_or_java_started": False,
            "world_files_written": False,
            "runtime_files_written": False,
            "only_output_directory_written": str(output_dir),
        },
        "inputs": {
            "baseline": str(baseline_path),
            "baseline_sha256": sha256(baseline_path),
            "gate_result": str(gate_path),
            "gate_result_sha256": sha256(gate_path),
            "world": str(world),
            "backport_jar": str(jar),
            "mods_dir": str(mods_dir) if mods_dir else None,
            "server_log": str(log_path) if log_path else None,
            "expected_backport_version": expected_version,
        },
        "gate_preconditions": precondition_section,
        "static_jar": static,
        "forgers": forgers,
        "dynamic_persistence": dynamic,
        "log": log_result,
        "world_scan": {
            "path": str(world_scan_path),
            "sha256": sha256(world_scan_path),
            "status": world_scan.get("status"),
            "summary": world_scan.get("summary"),
            "read_only_contract": world_scan.get("read_only_contract"),
        },
    }
    report["report_payload_sha256"] = digest_value(report)
    json_path = output_dir / "CEI-backport-postgate-readonly-result.json"
    md_path = output_dir / "CEI-backport-postgate-readonly-result.md"
    write_json(json_path, report)
    write_markdown(md_path, report)
    print(
        json.dumps(
            {"status": report["status"], "json": str(json_path), "markdown": str(md_path)},
            ensure_ascii=False,
        )
    )
    return 0 if passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_scanner = Path(__file__).with_name("audit_cei_world_data_readonly.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="capture the immutable two-Forger baseline")
    prepare.add_argument("--world", required=True, type=Path)
    prepare.add_argument("--jar-audit", type=Path)
    prepare.add_argument("--scanner", type=Path, default=default_scanner)
    prepare.add_argument("--output", required=True, type=Path)
    prepare.set_defaults(function=prepare_baseline)
    post = subparsers.add_parser("verify", help="verify a completed, stopped startup gate")
    post.add_argument("--baseline", required=True, type=Path)
    post.add_argument("--gate-result", required=True, type=Path)
    post.add_argument("--out-dir", required=True, type=Path)
    post.add_argument("--world", type=Path)
    post.add_argument("--backport-jar", type=Path)
    post.add_argument("--mods-dir", type=Path)
    post.add_argument("--log", type=Path)
    post.add_argument("--scanner", type=Path, default=default_scanner)
    post.add_argument("--workers", type=int, default=4)
    post.set_defaults(function=verify)
    args = parser.parse_args()
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
