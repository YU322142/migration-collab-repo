#!/usr/bin/env python3
"""Static, read-only verifier for the Yuushya 2.3.0 Patchouli safety patch."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


ORIGINAL = Path(
    r"D:\Trans\migration-audit-work\mechanomania-matched-client-attempt9-20260814\mods\yuushya-1.21.0-neoforge-2.3.0.jar"
)
BUILD1 = Path(
    r"D:\Trans\migration-audit-work\yuushya-230-patchouli-fix-artifacts-20260814\yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.1.jar"
)
BUILD2 = Path(
    r"D:\Trans\migration-audit-work\yuushya-230-patchouli-fix-artifacts-20260814\yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.2.jar"
)

GUIDE_ROOTS = (
    "assets/yuushya/patchouli_books/yuushya_guidebook/",
    "data/yuushya/patchouli_books/yuushya_guidebook/",
)

MAPPING = {
    "yuushya:pos_trans_item": "minecraft:barrier",
    "yuushya:get_showblock_item": "minecraft:barrier",
    "yuushya:rot_trans_item": "minecraft:barrier",
    "yuushya:scale_trans_item": "minecraft:barrier",
    "yuushya:slot_trans_item": "minecraft:barrier",
    "yuushya:get_blockstate_item": "minecraft:barrier",
    "yuushya:micro_pos_trans_item": "minecraft:barrier",
    "yuushya:get_lit_item": "minecraft:barrier",
    "yuushya:the_encyclopedia": "minecraft:book",
}

EXPECTED_MAPPING_COUNTS = Counter(
    {
        "yuushya:pos_trans_item": 10,
        "yuushya:get_showblock_item": 4,
        "yuushya:rot_trans_item": 2,
        "yuushya:scale_trans_item": 2,
        "yuushya:slot_trans_item": 4,
        "yuushya:get_blockstate_item": 2,
        "yuushya:micro_pos_trans_item": 2,
        "yuushya:get_lit_item": 2,
        "yuushya:the_encyclopedia": 4,
    }
)

EXPECTED_CHANGED_ENTRIES = {
    f"{root}{suffix}"
    for root in GUIDE_ROOTS
    for suffix in (
        "en_us/categories/mod_functions.json",
        "en_us/entries/mod_functions/mf_block_modeling_basic.json",
        "en_us/entries/mod_functions/mf_block_modeling_basic_adjust.json",
        "en_us/entries/mod_functions/mf_block_modeling_block_layer.json",
        "en_us/entries/mod_functions/mf_block_modeling_special.json",
        "en_us/entries/building_techniques/bt_survival_gameplay.json",
        "en_us/entries/building_techniques/bt_survival_building_material.json",
    )
}

EXPECTED_PATCHED_STACK_REFS = {
    "minecraft:barrier",
    "minecraft:book",
    "yuushya:a_pink_blindwall",
    "yuushya:extra_shapes_blueprint",
    "yuushya:facility_blueprint",
    "yuushya:oriental_lantern",
}

EXPECTED_VALID_RECIPES = {
    "yuushya:block_blueprint",
    "yuushya:extra_shapes_blueprint",
    "yuushya:facility_blueprint",
    "yuushya:form_trans_item",
    "yuushya:furniture_blueprint",
    "yuushya:sign_blueprint",
}

EXPECTED_MISSING_RECIPES = {
    "yuushya:dailylife_stuff_blueprint",
    "yuushya:deco_blueprint",
    "yuushya:everlasting_wood",
    "yuushya:floating_bloom",
    "yuushya:get_blockstate_item",
    "yuushya:get_lit_item",
    "yuushya:get_showblock_item",
    "yuushya:micro_pos_trans_item",
    "yuushya:move_transformdata_item",
    "yuushya:pos_trans_item",
    "yuushya:rot_trans_item",
    "yuushya:scale_trans_item",
    "yuushya:shimmering_pearl",
    "yuushya:slot_trans_item",
    "yuushya:sparking_flame",
    "yuushya:sprouting_dirt",
    "yuushya:the_encyclopedia",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def zip_map(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist()]
        assert len(names) == len(set(names)), f"duplicate ZIP entry in {path}"
        return names, {name: archive.read(name) for name in names}


def walk_refs(value, wanted_keys: set[str], refs: list[tuple[str, str]], path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in wanted_keys and isinstance(child, str):
                refs.append((child_path, child))
            walk_refs(child, wanted_keys, refs, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_refs(child, wanted_keys, refs, f"{path}[{index}]")


def compare_json(original, patched, changes: Counter, path=""):
    assert type(original) is type(patched), f"type changed at {path}"
    if isinstance(original, dict):
        assert original.keys() == patched.keys(), f"keys changed at {path}"
        for key in original:
            child_path = f"{path}.{key}" if path else key
            left, right = original[key], patched[key]
            if left != right and key in {"icon", "item"} and isinstance(left, str):
                assert left in MAPPING, f"unexpected stack reference edit at {child_path}: {left!r}"
                assert right == MAPPING[left], (
                    f"wrong mapping at {child_path}: {left!r} -> {right!r}"
                )
                changes[left] += 1
            else:
                compare_json(left, right, changes, child_path)
    elif isinstance(original, list):
        assert len(original) == len(patched), f"list length changed at {path}"
        for index, (left, right) in enumerate(zip(original, patched)):
            compare_json(left, right, changes, f"{path}[{index}]")
    else:
        assert original == patched, f"non-stack content changed at {path}"


def guide_jsons(files: dict[str, bytes]) -> dict[str, object]:
    result = {}
    for name, payload in files.items():
        if name.endswith(".json") and name.startswith(GUIDE_ROOTS):
            result[name] = json.loads(payload.decode("utf-8"))
    return result


def registered_reference_evidence(files: dict[str, bytes]):
    items = json.loads(files["data/yuushya/register/items.json"].decode("utf-8"))
    explicit_items = {entry["name"] for entry in items["item"]}
    assert {"facility_blueprint", "extra_shapes_blueprint"} <= explicit_items

    lighting = json.loads(
        files["data/yuushya/register/block_lighting.json"].decode("utf-8")
    )
    lighting_blocks = {
        entry.get("name")
        for entry in lighting["block"]
        if entry.get("class_type") != "_comment"
    }
    assert "oriental_lantern" in lighting_blocks

    texture = json.loads(files["data/yuushya/register/texture.json"].decode("utf-8"))
    texture_blocks = {
        entry.get("name")
        for entry in texture["block"]
        if entry.get("class_type") != "_comment"
    }
    assert "a_pink_blindwall" in texture_blocks


def available_recipe_ids(files: dict[str, bytes]) -> set[str]:
    result = set()
    for name in files:
        parts = PurePosixPath(name).parts
        if len(parts) == 4 and parts[0] == "data" and parts[2] in {"recipe", "recipes"}:
            if parts[3].endswith(".json"):
                result.add(f"{parts[1]}:{parts[3][:-5]}")
    return result


def main() -> None:
    for path in (ORIGINAL, BUILD1, BUILD2):
        assert path.is_file(), f"missing file: {path}"

    assert BUILD1.read_bytes() == BUILD2.read_bytes(), "two builds are not byte-identical"
    assert sha256(BUILD1) == "31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D"
    assert BUILD1.stat().st_size == 28_197_402

    original_names, original_files = zip_map(ORIGINAL)
    patched_names, patched_files = zip_map(BUILD1)
    assert len(original_names) == len(patched_names)
    assert set(original_names) == set(patched_names), "ZIP entry set changed"

    changed_entries = {
        name for name in original_names if original_files[name] != patched_files[name]
    }
    assert changed_entries == EXPECTED_CHANGED_ENTRIES, (
        f"unexpected changed entries: {sorted(changed_entries ^ EXPECTED_CHANGED_ENTRIES)}"
    )

    original_guides = guide_jsons(original_files)
    patched_guides = guide_jsons(patched_files)
    assert original_guides.keys() == patched_guides.keys()
    changes = Counter()
    for name in original_guides:
        compare_json(original_guides[name], patched_guides[name], changes, name)
    assert changes == EXPECTED_MAPPING_COUNTS, f"mapping counts differ: {changes}"

    patched_stack_refs: list[tuple[str, str]] = []
    patched_recipe_refs: list[tuple[str, str]] = []
    for name, data in patched_guides.items():
        local_stack_refs: list[tuple[str, str]] = []
        local_recipe_refs: list[tuple[str, str]] = []
        walk_refs(data, {"icon", "item"}, local_stack_refs, name)
        walk_refs(data, {"recipe", "recipe2"}, local_recipe_refs, name)
        patched_stack_refs.extend(local_stack_refs)
        patched_recipe_refs.extend(local_recipe_refs)

    stack_values = {value for _, value in patched_stack_refs}
    assert stack_values == EXPECTED_PATCHED_STACK_REFS, stack_values
    assert not (stack_values & set(MAPPING)), "legacy invalid stack reference remains"

    registered_reference_evidence(patched_files)

    recipe_values = {value for _, value in patched_recipe_refs}
    available = available_recipe_ids(patched_files)
    valid_recipe_refs = recipe_values & available
    missing_recipe_refs = recipe_values - available
    assert valid_recipe_refs == EXPECTED_VALID_RECIPES, valid_recipe_refs
    assert missing_recipe_refs == EXPECTED_MISSING_RECIPES, missing_recipe_refs

    # Preserve every recipe reference, page, title and text for later Yuushya add-on/OTA recovery.
    original_recipe_refs: list[tuple[str, str]] = []
    for name, data in original_guides.items():
        walk_refs(data, {"recipe", "recipe2"}, original_recipe_refs, name)
    assert patched_recipe_refs == original_recipe_refs

    # The legacy assets/ and current data/ copies must remain exact mirrors.
    for name, payload in patched_files.items():
        if name.startswith(GUIDE_ROOTS[0]) and name.endswith(".json"):
            suffix = name[len(GUIDE_ROOTS[0]) :]
            peer = GUIDE_ROOTS[1] + suffix
            assert peer in patched_files, f"missing data mirror: {peer}"
            assert payload == patched_files[peer], f"assets/data mismatch: {suffix}"

    print("PASS: Yuushya 2.3.0 Patchouli safety patch")
    print(f"original_sha256={sha256(ORIGINAL)}")
    print(f"patched_sha256={sha256(BUILD1)}")
    print(f"zip_entries={len(original_names)}")
    print(f"changed_entries={len(changed_entries)}")
    print(f"mapped_stack_fields={sum(changes.values())}")
    print(f"valid_recipe_refs={len(valid_recipe_refs)}")
    print(f"missing_recipe_refs_preserved={len(missing_recipe_refs)}")


if __name__ == "__main__":
    main()
