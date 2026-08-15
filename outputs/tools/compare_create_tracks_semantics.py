#!/usr/bin/env python3
"""Compare two target-format Create railway SavedData files semantically.

Create rebuilds node indices and its dimension palette while saving. Raw NBT
comparison therefore reports thousands of false differences. This comparator
resolves palette indices and graph references before sorting only collections
whose order is not part of the railway model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from nbt import nbt


INTEGER_TAGS = (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)
ARRAY_TAGS = (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)


def scalar(value):
    return getattr(value, "value", value)


def integer(value):
    return isinstance(value, INTEGER_TAGS)


def canonical(value, palette=None):
    """Return a JSON-safe, type-preserving representation of an NBT value."""
    if isinstance(value, nbt.TAG_Compound):
        # TrackNodeLocation is the only generic D/Pos compound in this file.
        if palette is not None and "D" in value and "Pos" in value:
            return {"$track_location": track_location(value, palette)}
        result = {}
        for key in sorted(value.keys()):
            if key == "fluids" and isinstance(value[key], nbt.TAG_List) and len(value[key]) == 0:
                # Mounted storage omits its empty fluid collection on the next save.
                continue
            if key in {"BlockEntityDimension", "Dim"} and palette is not None and integer(value[key]):
                result[key] = dimension_at(value[key], palette, key)
            else:
                result[key] = canonical(value[key], palette)
        return result
    if isinstance(value, nbt.TAG_List):
        return [canonical(child, palette) for child in value]
    if isinstance(value, ARRAY_TAGS):
        return {"$type": type(value).__name__, "$value": [int(item) for item in value.value]}
    return {"$type": type(value).__name__, "$value": scalar(value)}


def stable_key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(stable_key(value).encode("utf-8")).hexdigest().upper()


def dimension_at(value, palette, path):
    if not integer(value):
        raise ValueError(f"{path}: dimension index is not an integer")
    index = int(value.value)
    if index < 0 or index >= len(palette):
        raise ValueError(f"{path}: dimension index {index} is outside palette size {len(palette)}")
    return palette[index]


def track_location(value, palette):
    if not isinstance(value, nbt.TAG_Compound):
        raise ValueError("track location is not a compound")
    if not isinstance(value.get("Pos"), nbt.TAG_Int_Array) or len(value["Pos"].value) != 3:
        raise ValueError("track location Pos is not int[3]")
    result = {
        "dimension": dimension_at(value.get("D"), palette, "track location D"),
        "pos": [int(item) for item in value["Pos"].value],
    }
    if "YO" in value:
        result["y_offset"] = canonical(value["YO"], palette)
    unknown = set(value.keys()) - {"D", "Pos", "YO"}
    if unknown:
        raise ValueError(f"track location has unknown fields: {sorted(unknown)}")
    return result


def uuid_key(value):
    if not isinstance(value, nbt.TAG_Int_Array) or len(value.value) != 4:
        raise ValueError("UUID is not int[4]")
    return ":".join(str(int(part)) for part in value.value)


def normalize_edge_data(value, palette):
    result = canonical(value, palette)
    signals = result.get("Signals") if isinstance(result, dict) else None
    if isinstance(signals, dict) and isinstance(signals.get("Points"), list):
        signals["Points"] = sorted(signals["Points"], key=stable_key)
    return result


def normalize_graph(graph, palette):
    if not isinstance(graph, nbt.TAG_Compound):
        raise ValueError("rail graph is not a compound")
    nodes = graph.get("Nodes")
    if not isinstance(nodes, nbt.TAG_List):
        raise ValueError("rail graph Nodes is not a list")

    locations = []
    for index, node in enumerate(nodes):
        if not isinstance(node, nbt.TAG_Compound):
            raise ValueError(f"node {index} is not a compound")
        location = track_location(node.get("Location"), palette)
        normal = canonical(node.get("Normal"), palette)
        locations.append({"location": location, "normal": normal})

    normalized_nodes = []
    for index, node in enumerate(nodes):
        connections = node.get("Connections")
        if not isinstance(connections, nbt.TAG_List):
            raise ValueError(f"node {index} Connections is not a list")
        normalized_connections = []
        for connection_index, connection in enumerate(connections):
            if not isinstance(connection, nbt.TAG_Compound) or not integer(connection.get("To")):
                raise ValueError(f"node {index} connection {connection_index} is malformed")
            target = int(connection["To"].value)
            if target < 0 or target >= len(locations):
                raise ValueError(f"node {index} connection target {target} is outside graph")
            normalized_connections.append(
                {
                    "to": locations[target],
                    "edge_data": normalize_edge_data(connection.get("EdgeData"), palette),
                }
            )
        normalized_nodes.append(
            {
                **locations[index],
                "connections": sorted(normalized_connections, key=stable_key),
            }
        )

    points = graph.get("Points")
    normalized_points = canonical(points, palette)
    if isinstance(normalized_points, dict):
        for point_type, entries in normalized_points.items():
            if isinstance(entries, list):
                normalized_points[point_type] = sorted(entries, key=stable_key)

    known = {"Id", "Color", "Nodes", "Points"}
    extras = {
        key: canonical(graph[key], palette)
        for key in sorted(set(graph.keys()) - known)
    }
    return {
        "id": uuid_key(graph.get("Id")),
        "color": canonical(graph.get("Color"), palette),
        "nodes": sorted(normalized_nodes, key=stable_key),
        "points": normalized_points,
        "extras": extras,
    }


def normalize_signal_group(group, palette):
    result = canonical(group, palette)
    if isinstance(result, dict) and isinstance(result.get("Connected"), list):
        result["Connected"] = sorted(result["Connected"], key=stable_key)
    return result


def normalize_train(train, palette):
    result = canonical(train, palette)
    if not isinstance(result, dict):
        raise ValueError("train is not a compound")
    for key in ("ReservedSignalBlocks", "OccupiedObservers"):
        if isinstance(result.get(key), list):
            result[key] = sorted(result[key], key=stable_key)
    return result


def read_palette(data):
    raw = data.get("DimensionPalette")
    if not isinstance(raw, nbt.TAG_List):
        raise ValueError("DimensionPalette is not a list")
    palette = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Id"}:
            raise ValueError(f"DimensionPalette[{index}] is not {{Id:string}}")
        identifier = entry.get("Id")
        if not isinstance(identifier, nbt.TAG_String):
            raise ValueError(f"DimensionPalette[{index}].Id is not a string")
        palette.append(str(identifier.value))
    if len(palette) != len(set(palette)):
        raise ValueError("DimensionPalette contains duplicates")
    return palette


def snapshot(path):
    root = nbt.NBTFile(filename=str(path))
    data = root.get("data")
    if not isinstance(data, nbt.TAG_Compound):
        raise ValueError("root data is not a compound")
    palette = read_palette(data)
    graphs = [normalize_graph(graph, palette) for graph in data.get("RailGraphs", [])]
    signals = [normalize_signal_group(group, palette) for group in data.get("SignalBlocks", [])]
    trains = [normalize_train(train, palette) for train in data.get("Trains", [])]
    normalized = {
        "graphs": sorted(graphs, key=lambda value: value["id"]),
        "signals": sorted(signals, key=stable_key),
        "trains": sorted(trains, key=lambda value: stable_key(value.get("Id"))),
    }
    return normalized


def first_differences(left, right, path="", limit=100, result=None):
    if result is None:
        result = []
    if len(result) >= limit:
        return result
    if type(left) is not type(right):
        result.append({"path": path, "left": type(left).__name__, "right": type(right).__name__})
    elif isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            child_path = f"{path}.{key}" if path else key
            if key not in left:
                result.append({"path": child_path, "left": "<missing>", "right": right[key]})
            elif key not in right:
                result.append({"path": child_path, "left": left[key], "right": "<missing>"})
            else:
                first_differences(left[key], right[key], child_path, limit, result)
            if len(result) >= limit:
                break
    elif isinstance(left, list):
        if len(left) != len(right):
            result.append({"path": f"{path}.length", "left": len(left), "right": len(right)})
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            first_differences(left_item, right_item, f"{path}[{index}]", limit, result)
            if len(result) >= limit:
                break
    elif left != right:
        result.append({"path": path, "left": left, "right": right})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    left = snapshot(args.left)
    right = snapshot(args.right)
    differences = first_differences(left, right, limit=args.limit)
    report = {
        "left": str(args.left.resolve()),
        "right": str(args.right.resolve()),
        "equivalent": not differences,
        "left_semantic_sha256": digest(left),
        "right_semantic_sha256": digest(right),
        "counts": {
            "left": {key: len(value) for key, value in left.items()},
            "right": {key: len(value) for key, value in right.items()},
        },
        "differences": differences,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if report["equivalent"] else 1)


if __name__ == "__main__":
    main()
