from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import nbtlib


def plain(value):
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def tag_name(value):
    name = type(value).__name__
    return name.removeprefix("TAG_")


def type_signature(value, depth=0):
    if depth >= 8:
        return tag_name(value)
    if isinstance(value, dict):
        fields = ",".join(
            f"{key}:{type_signature(child, depth + 1)}"
            for key, child in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
        return f"{tag_name(value)}{{{fields}}}"
    if isinstance(value, (list, tuple)):
        children = sorted({type_signature(child, depth + 1) for child in value})
        return f"{tag_name(value)}[{','.join(children) or '-'}]"
    return tag_name(value)


def canonical_json(value):
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bounded_value(value, limit=8000):
    result = plain(value)
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) <= limit:
        return result
    return {
        "_truncated": True,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "json_chars": len(encoded),
        "preview": encoded[:limit],
    }


def is_item_stack(value):
    if not isinstance(value, dict):
        return False
    identifier = plain(value.get("id"))
    if not isinstance(identifier, str) or ":" not in identifier:
        return False
    return any(key in value for key in ("count", "Count", "components"))


def path_text(parts):
    result = ""
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif result:
            result += f".{part}"
        else:
            result = str(part)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("player_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-examples", type=int, default=25)
    args = parser.parse_args()

    component_stats = {}
    item_instances = collections.Counter()
    files = sorted(args.player_dir.glob("*.dat"))
    old_files = sorted(args.player_dir.glob("*.dat_old"))
    parse_errors = []
    roots_scanned = collections.Counter()
    players_with_components = set()
    total_stacks = 0

    def component_record(identifier):
        return component_stats.setdefault(
            identifier,
            {
                "instances": 0,
                "players": set(),
                "parent_items": collections.Counter(),
                "root_fields": collections.Counter(),
                "type_signatures": collections.Counter(),
                "value_shapes": collections.Counter(),
                "examples": [],
            },
        )

    def visit(value, player, parts, root_field):
        nonlocal total_stacks
        if isinstance(value, dict):
            if is_item_stack(value):
                total_stacks += 1
                item_id = str(plain(value.get("id")))
                count = int(plain(value.get("count", value.get("Count", 1))) or 1)
                item_instances[item_id] += count
                components = value.get("components")
                if isinstance(components, dict):
                    for component_id, component_value in components.items():
                        component_id = str(component_id)
                        record = component_record(component_id)
                        signature = type_signature(component_value)
                        shape = canonical_json(component_value)
                        record["instances"] += 1
                        record["players"].add(player)
                        record["parent_items"][item_id] += 1
                        record["root_fields"][root_field] += 1
                        record["type_signatures"][signature] += 1
                        record["value_shapes"][shape] += 1
                        players_with_components.add(player)
                        if len(record["examples"]) < args.max_examples:
                            record["examples"].append(
                                {
                                    "player": player,
                                    "path": path_text(parts + ["components", component_id]),
                                    "item_id": item_id,
                                    "stack_count": count,
                                    "nbt_type": signature,
                                    "value": bounded_value(component_value),
                                }
                            )
            for key, child in value.items():
                visit(child, player, parts + [str(key)], root_field)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                visit(child, player, parts + [index], root_field)

    for path in files:
        try:
            root = nbtlib.load(path)
        except Exception as exc:
            parse_errors.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for root_field, root_value in root.items():
            root_field = str(root_field)
            roots_scanned[root_field] += 1
            visit(root_value, path.stem, [root_field], root_field)

    serial_components = {}
    for component_id, record in sorted(component_stats.items()):
        shapes = record.pop("value_shapes")
        serial_components[component_id] = {
            **record,
            "players": sorted(record["players"]),
            "player_count": len(record["players"]),
            "parent_items": dict(record["parent_items"].most_common()),
            "root_fields": dict(record["root_fields"].most_common()),
            "type_signatures": dict(record["type_signatures"].most_common()),
            "distinct_values": len(shapes),
            "most_common_values": [
                {"count": count, "value": json.loads(encoded)}
                for encoded, count in shapes.most_common(args.max_examples)
            ],
        }

    output = {
        "source": str(args.player_dir.resolve()),
        "files": len(files),
        "dat_old_files_excluded": len(old_files),
        "parsed_files": len(files) - len(parse_errors),
        "parse_errors": parse_errors,
        "roots_scanned": dict(roots_scanned),
        "item_stack_instances": total_stacks,
        "players_with_components": len(players_with_components),
        "component_type_count": len(serial_components),
        "item_counts": dict(item_instances.most_common()),
        "components": serial_components,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "files": output["files"],
                "parsed_files": output["parsed_files"],
                "item_stack_instances": output["item_stack_instances"],
                "players_with_components": output["players_with_components"],
                "components": {
                    key: {
                        "instances": value["instances"],
                        "player_count": value["player_count"],
                        "distinct_values": value["distinct_values"],
                    }
                    for key, value in serial_components.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
