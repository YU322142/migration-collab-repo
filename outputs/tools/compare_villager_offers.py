from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def canonical_component(name: str, value):
    if name in {"minecraft:stored_enchantments", "minecraft:enchantments"} and isinstance(value, dict):
        if set(value) == {"levels"} and isinstance(value["levels"], dict):
            return {"levels": value["levels"]}
        return {"levels": value}
    if name == "minecraft:dyed_color":
        if isinstance(value, dict) and set(value) == {"rgb"}:
            return int(value["rgb"])
        if isinstance(value, (int, float)):
            return int(value)
    return value


def canonical_stack(stack):
    if not isinstance(stack, dict):
        return stack
    result = {key: value for key, value in stack.items() if key != "components"}
    components = stack.get("components")
    if isinstance(components, dict):
        result["components"] = {
            key: canonical_component(key, value)
            for key, value in components.items()
        }
    elif components is not None:
        result["components"] = components
    return result


def canonical_recipe(recipe):
    if not isinstance(recipe, dict):
        return recipe
    return {
        key: canonical_stack(value) if key in ("buy", "buyB", "sell") else value
        for key, value in recipe.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    target = json.loads(args.target.read_text(encoding="utf-8"))
    source_map = {row["uuid"]: row for row in source["villagers"]}
    target_map = {row["uuid"]: row for row in target["villagers"]}
    raw_changed = []
    canonical_changed = []
    component_deltas = collections.Counter()
    examples = {}
    for uuid, source_row in source_map.items():
        target_row = target_map.get(uuid)
        if target_row is None:
            continue
        source_recipes = source_row.get("recipes", [])
        target_recipes = target_row.get("recipes", [])
        if source_recipes != target_recipes:
            raw_changed.append(uuid)
        source_canonical = [canonical_recipe(recipe) for recipe in source_recipes]
        target_canonical = [canonical_recipe(recipe) for recipe in target_recipes]
        if source_canonical != target_canonical:
            canonical_changed.append(uuid)
            for index, (source_recipe, target_recipe) in enumerate(
                zip(source_recipes, target_recipes)
            ):
                for side in ("buy", "buyB", "sell"):
                    source_stack = source_recipe.get(side) or {}
                    target_stack = target_recipe.get(side) or {}
                    source_components = source_stack.get("components", {})
                    target_components = target_stack.get("components", {})
                    if not isinstance(source_components, dict) or not isinstance(
                        target_components, dict
                    ):
                        continue
                    for name in set(source_components) | set(target_components):
                        left = canonical_component(name, source_components.get(name))
                        right = canonical_component(name, target_components.get(name))
                        if left != right:
                            key = f"{side}:{name}"
                            component_deltas[key] += 1
                            examples.setdefault(
                                key,
                                {
                                    "uuid": uuid,
                                    "recipe": index,
                                    "source": source_components.get(name),
                                    "target": target_components.get(name),
                                },
                            )
    report = {
        "source_villagers": len(source_map),
        "target_villagers": len(target_map),
        "raw_trade_changed_villagers": len(raw_changed),
        "canonical_trade_changed_villagers": len(canonical_changed),
        "raw_changed_uuids": raw_changed,
        "canonical_changed_uuids": canonical_changed,
        "component_deltas": dict(component_deltas),
        "component_examples": examples,
        "status": "PASS" if not canonical_changed else "DIFF",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in report if key not in ("raw_changed_uuids", "canonical_changed_uuids")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
