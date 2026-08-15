from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import uuid
from pathlib import Path

from convert_world_nbt import (
    as_int,
    clone_tag,
    comparable_tag,
    convert_item_stack,
    list_tag,
    nbt,
    string_value,
    walk_entity_item_stacks,
)
from convert_create_fluid_nbt import convert_create_fluid_tree


TARGET_DATA_VERSION = 3955
OVERWORLD = "minecraft:overworld"
NETWORK_KEYS = {"Id", "Promises", "Links", "Owner", "Locked"}
PROMISE_KEYS = {"ticks_existed", "promised_stack"}
BIG_STACK_KEYS = {"item_stack", "count"}
ITEM_CONTEXT_LISTS = (
    "blockers",
    "text_components",
    "clipboard_hovers",
    "axolotl_variants",
    "schematic_files",
    "inherited_missing_schematic_files",
    "tooltip_displays",
)

TRACK_KEYS = {"RailGraphs", "SignalBlocks", "DimensionPalette", "Trains"}
TRACK_UUID_KEYS = {"Id", "Owner", "Graph", "TrainId", "UUID"}
DIMENSION_KEYS = {"Id"}
SIGNAL_KEYS = {"Id", "Connected", "Color", "Fallback"}
EDGE_GROUP_COLORS = {
    "YELLOW",
    "GREEN",
    "BLUE",
    "ORANGE",
    "LAVENDER",
    "RED",
    "CYAN",
    "BROWN",
    "WHITE",
}
SCHEDULE_RUNTIME_STATES = {"PRE_TRANSIT", "IN_TRANSIT", "POST_TRANSIT"}
DIRECTIONS = {"DOWN", "UP", "NORTH", "SOUTH", "WEST", "EAST"}
DIRECTION_3D_IDS = {
    "DOWN": 0,
    "UP": 1,
    "NORTH": 2,
    "SOUTH": 3,
    "WEST": 4,
    "EAST": 5,
}
UUID_SET_KEYS = {"Id"}
BEZIER_KEYS = {
    "Positions",
    "Starts",
    "Axes",
    "Normals",
    "Primary",
    "Girder",
    "Material",
    "Smoothing",
}
SOURCE_PORT_KEYS = {"address", "offlineBuffer", "primed", "restoring"}
TARGET_PORT_KEYS = {"Address", "OfflineBuffer", "Primed", "Pos"}
NAVIGATION_KEYS = {
    "Destination",
    "DistanceToDestination",
    "DistanceStartedAt",
    "BehindTrain",
    "AnnounceArrival",
    "Path",
    "BlockingSignal",
    "BlockingSignalSide",
    "DistanceToSignal",
    "TicksWaitingForSignal",
}


def json_component_text(value, path, blockers, source_format):
    """Normalize Create train names to the JSON string consumed by Component.Serializer."""
    if not isinstance(value, nbt.TAG_String):
        fail(blockers, path, "train Name is not a string")
        return None
    raw = string_value(value)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
        if not source_format:
            fail(blockers, path, "target train Name is not valid component JSON")
            return None
    if source_format and not isinstance(parsed, (dict, list, str, int, float, bool)):
        # A raw source name is ordinary text; encode it as a JSON string.
        raw = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    elif source_format and isinstance(parsed, str):
        # It is already a JSON string literal. Keep it byte-for-byte.
        raw = raw
    elif not source_format and parsed is None:
        fail(blockers, path, "target train Name component JSON resolves to null")
        return None
    return nbt.TAG_String(raw)


def convert_uuid_set(value, path, blockers, source_format):
    """Create 1.21.11 writes UUID sets as int arrays; 1.21.1 reads {Id:int[]}."""
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "UUID set is not a list")
        return None
    result = []
    seen = set()
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            uid = uuid_int_array(entry, entry_path, blockers, False)
            if uid is None:
                continue
            key = tuple(int(x) for x in uid.value)
            if key in seen:
                fail(blockers, entry_path, "UUID set contains duplicate UUID")
            seen.add(key)
            item = nbt.TAG_Compound()
            item["Id"] = uid
            result.append(item)
        else:
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != UUID_SET_KEYS:
                fail(blockers, entry_path, "target UUID set entry is not {Id:int[4]}")
                continue
            uid = uuid_int_array(entry.get("Id"), f"{entry_path}.Id", blockers, False)
            if uid is None:
                continue
            key = tuple(int(x) for x in uid.value)
            if key in seen:
                fail(blockers, entry_path, "UUID set contains duplicate UUID")
            seen.add(key)
            result.append(clone_tag(entry))
    if any(item.get("path", "").startswith(path) for item in blockers):
        return None
    return list_tag(result, nbt.TAG_Compound)


def convert_schedule_columns(schedule, path, blockers, source_format):
    if not isinstance(schedule, nbt.TAG_Compound):
        fail(blockers, path, "Schedule is not a compound")
        return
    entries = schedule.get("Entries")
    if not isinstance(entries, nbt.TAG_List):
        fail(blockers, f"{path}.Entries", "Schedule Entries is not a list")
        return
    for index, entry in enumerate(entries):
        entry_path = f"{path}.Entries[{index}]"
        if not isinstance(entry, nbt.TAG_Compound):
            fail(blockers, entry_path, "schedule entry is not a compound")
            continue
        conditions = entry.get("Conditions")
        if not isinstance(conditions, nbt.TAG_List):
            fail(blockers, f"{entry_path}.Conditions", "Conditions is not a list")
            continue
        # Source production files use the DynamicOps encode path, whose shape is
        # already the same List<List<Compound>> consumed by Create 6.0.10.
        for column_index, column in enumerate(conditions):
            column_path = f"{entry_path}.Conditions[{column_index}]"
            if not isinstance(column, nbt.TAG_List):
                fail(blockers, column_path, "condition column is not a list")
                continue
            for condition_index, condition in enumerate(column):
                if not isinstance(condition, nbt.TAG_Compound):
                    fail(blockers, f"{column_path}[{condition_index}]", "schedule condition is not a compound")


def convert_schedule_runtime_state(runtime, path, blockers, source_format):
    if not isinstance(runtime, nbt.TAG_Compound):
        fail(blockers, path, "train Runtime is not a compound")
        return
    state = runtime.get("State")
    if not isinstance(state, nbt.TAG_String):
        fail(blockers, f"{path}.State", "schedule runtime State is not a string")
        return
    raw_state = string_value(state)
    normalized_state = raw_state.upper() if source_format else raw_state
    if not source_format and raw_state != raw_state.upper():
        fail(blockers, f"{path}.State", "target schedule runtime State is not the canonical uppercase enum", value=raw_state)
        return
    if normalized_state not in SCHEDULE_RUNTIME_STATES:
        fail(blockers, f"{path}.State", "schedule runtime State is not a known enum value", value=raw_state)
        return
    runtime["State"] = nbt.TAG_String(normalized_state)


def convert_navigation(value, path, blockers, source_format):
    if not isinstance(value, nbt.TAG_Compound):
        fail(blockers, path, "Navigation is not a compound")
        return None
    if not source_format:
        # Empty Navigation is canonical and common. Validate only the path when present.
        path_list = value.get("Path")
        if path_list is not None:
            if not isinstance(path_list, nbt.TAG_List):
                fail(blockers, f"{path}.Path", "target Navigation Path is not a list")
            else:
                for index, entry in enumerate(path_list):
                    p = f"{path}.Path[{index}]"
                    if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Nodes"} or not isinstance(entry.get("Nodes"), nbt.TAG_List) or len(entry["Nodes"]) != 2:
                        fail(blockers, p, "target Navigation path entry is not {Nodes:[2 locations]}")
        return value
    path_list = value.get("Path")
    if path_list is None:
        return value
    if not isinstance(path_list, nbt.TAG_List):
        fail(blockers, f"{path}.Path", "source Navigation Path is not a list")
        return value
    converted = []
    for index, entry in enumerate(path_list):
        p = f"{path}.Path[{index}]"
        if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"First", "Second"}:
            fail(blockers, p, "source Navigation path entry is not {First,Second}")
            continue
        nodes = nbt.TAG_List()
        nodes.extend([clone_tag(entry["First"]), clone_tag(entry["Second"])])
        out = nbt.TAG_Compound()
        out["Nodes"] = nodes
        converted.append(out)
    value["Path"] = list_tag(converted, nbt.TAG_Compound)
    return value


def block_pos_tag(value, path, blockers):
    if isinstance(value, nbt.TAG_Int_Array) and len(value.value) == 3:
        return clone_tag(value)
    if isinstance(value, nbt.TAG_Compound) and set(value.keys()) == {"X", "Y", "Z"} and all(integer(value.get(k)) for k in ("X", "Y", "Z")):
        result = nbt.TAG_Int_Array()
        result.value = [as_int(value[axis]) for axis in ("X", "Y", "Z")]
        result.update_fmt(3)
        return result
    fail(blockers, path, "value is not a three-int block position")
    return None


def convert_track_node_locations(value, path, blockers, source_format):
    """Convert only compounds that have the narrow TrackNodeLocation shape."""
    if isinstance(value, nbt.TAG_Compound):
        keys = set(value.keys())
        if "Pos" in keys and keys.issubset({"Pos", "D", "YO"}):
            pos_path = f"{path}.Pos"
            if source_format:
                converted = block_pos_tag(value["Pos"], pos_path, blockers)
                if converted is not None:
                    value["Pos"] = converted
            elif block_pos_tag(value["Pos"], pos_path, blockers) is None:
                return
        for key, child in list(value.items()):
            convert_track_node_locations(child, f"{path}.{key}" if path else key, blockers, source_format)
    elif isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            convert_track_node_locations(child, f"{path}[{index}]", blockers, source_format)


def convert_vector_couple(value, path, blockers, source_format):
    if not isinstance(value, nbt.TAG_List) or len(value) != 2:
        fail(blockers, path, "vector couple is not a two-element list")
        return None
    result = []
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            if not isinstance(entry, nbt.TAG_List) or len(entry) != 3 or any(not isinstance(part, nbt.TAG_Double) for part in entry):
                fail(blockers, entry_path, "source vector is not a three-double list")
                continue
            wrapper = nbt.TAG_Compound()
            wrapper["V"] = clone_tag(entry)
            result.append(wrapper)
        else:
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"V"}:
                fail(blockers, entry_path, "target vector is not {V:[3 doubles]}")
                continue
            vector = entry.get("V")
            if not isinstance(vector, nbt.TAG_List) or len(vector) != 3 or any(not isinstance(part, nbt.TAG_Double) for part in vector):
                fail(blockers, f"{entry_path}.V", "target vector V is not a three-double list")
                continue
            result.append(clone_tag(entry))
    if any(item.get("path", "").startswith(path) for item in blockers):
        return None
    return list_tag(result, nbt.TAG_Compound)


def convert_bezier_positions(value, path, blockers, source_format):
    if not isinstance(value, nbt.TAG_List) or len(value) != 2:
        fail(blockers, path, "Bezier Positions is not a two-element list")
        return None
    result = []
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            position = block_pos_tag(entry, f"{entry_path}.Pos", blockers)
            if position is None:
                continue
            wrapper = nbt.TAG_Compound()
            wrapper["Pos"] = position
            result.append(wrapper)
        else:
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Pos"}:
                fail(blockers, entry_path, "target Bezier position is not {Pos:block_pos}")
                continue
            if block_pos_tag(entry.get("Pos"), f"{entry_path}.Pos", blockers) is None:
                continue
            result.append(clone_tag(entry))
    if any(item.get("path", "").startswith(path) for item in blockers):
        return None
    return list_tag(result, nbt.TAG_Compound)


def convert_integer_couple(value, path, blockers, source_format):
    if not isinstance(value, nbt.TAG_List) or len(value) != 2:
        fail(blockers, path, "integer couple is not a two-element list")
        return None
    result = []
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            if not integer(entry):
                fail(blockers, entry_path, "source integer couple entry is not an integer")
                continue
            wrapper = nbt.TAG_Compound()
            wrapper["V"] = nbt.TAG_Int(as_int(entry))
            result.append(wrapper)
        else:
            if (
                not isinstance(entry, nbt.TAG_Compound)
                or set(entry.keys()) != {"V"}
                or not integer(entry.get("V"))
            ):
                fail(blockers, entry_path, "target integer couple entry is not {V:int}")
                continue
            result.append(clone_tag(entry))
    if any(item.get("path", "").startswith(path) for item in blockers):
        return None
    return list_tag(result, nbt.TAG_Compound)


def convert_bezier_edge_data(edge_data, path, blockers, source_format):
    if not isinstance(edge_data, nbt.TAG_Compound):
        fail(blockers, path, "track EdgeData is not a compound")
        return
    if source_format and "BezierConnection" in edge_data:
        nested = edge_data["BezierConnection"]
        if not isinstance(nested, nbt.TAG_Compound):
            fail(blockers, f"{path}.BezierConnection", "BezierConnection is not a compound")
            return
        if "Material" in nested and "Material" in edge_data and string_value(nested["Material"]) != string_value(edge_data["Material"]):
            fail(blockers, path, "Bezier inner and edge materials differ")
        for key, child in nested.items():
            if key == "Material":
                continue
            if key in edge_data:
                fail(blockers, f"{path}.{key}", "Bezier field collides with outer EdgeData")
                continue
            edge_data[key] = clone_tag(child)
        del edge_data["BezierConnection"]
    elif not source_format and "BezierConnection" in edge_data:
        fail(blockers, f"{path}.BezierConnection", "target EdgeData still contains nested BezierConnection")

    if "Positions" not in edge_data:
        return
    required = {"Positions", "Starts", "Axes", "Normals", "Primary", "Girder", "Material"}
    missing = sorted(required - set(edge_data.keys()))
    if missing:
        fail(blockers, path, "Bezier edge is missing required fields", fields=missing)
    allowed = required | {"Signals", "Smoothing"}
    unknown = sorted(set(edge_data.keys()) - allowed)
    if unknown:
        fail(blockers, path, "Bezier edge has unknown fields", fields=unknown)
    positions = convert_bezier_positions(edge_data["Positions"], f"{path}.Positions", blockers, source_format)
    if positions is not None:
        edge_data["Positions"] = positions
    for key in ("Starts", "Axes", "Normals"):
        if key not in edge_data:
            fail(blockers, f"{path}.{key}", "Bezier vector couple is missing")
            continue
        vectors = convert_vector_couple(edge_data[key], f"{path}.{key}", blockers, source_format)
        if vectors is not None:
            edge_data[key] = vectors
    for key in ("Primary", "Girder"):
        if not isinstance(edge_data.get(key), nbt.TAG_Byte) or as_int(edge_data[key]) not in (0, 1):
            fail(blockers, f"{path}.{key}", f"Bezier {key} is not a byte boolean")
    if resource_location(edge_data.get("Material")) is None:
        fail(blockers, f"{path}.Material", "Bezier Material is not a resource location")
    if "Smoothing" in edge_data:
        smoothing = convert_integer_couple(
            edge_data["Smoothing"],
            f"{path}.Smoothing",
            blockers,
            source_format,
        )
        if smoothing is not None:
            edge_data["Smoothing"] = smoothing


def convert_graph_geometry(graphs, path, blockers, source_format):
    if not isinstance(graphs, nbt.TAG_List):
        return
    for graph_index, graph in enumerate(graphs):
        graph_path = f"{path}[{graph_index}]"
        if not isinstance(graph, nbt.TAG_Compound):
            continue
        nodes = graph.get("Nodes")
        if not isinstance(nodes, nbt.TAG_List):
            fail(blockers, f"{graph_path}.Nodes", "graph Nodes is not a list")
            continue
        for node_index, node in enumerate(nodes):
            node_path = f"{graph_path}.Nodes[{node_index}]"
            if not isinstance(node, nbt.TAG_Compound):
                fail(blockers, node_path, "graph node is not a compound")
                continue
            convert_track_node_locations(node.get("Location"), f"{node_path}.Location", blockers, source_format)
            connections = node.get("Connections")
            if not isinstance(connections, nbt.TAG_List):
                fail(blockers, f"{node_path}.Connections", "node Connections is not a list")
                continue
            for connection_index, connection in enumerate(connections):
                connection_path = f"{node_path}.Connections[{connection_index}]"
                if not isinstance(connection, nbt.TAG_Compound):
                    fail(blockers, connection_path, "graph connection is not a compound")
                    continue
                convert_bezier_edge_data(connection.get("EdgeData"), f"{connection_path}.EdgeData", blockers, source_format)


def convert_entity_positioning(
    carriages,
    path,
    blockers,
    source_format,
    fluid_normalizations=None,
):
    if not isinstance(carriages, nbt.TAG_List):
        return
    for carriage_index, carriage in enumerate(carriages):
        carriage_path = f"{path}[{carriage_index}]"
        if not isinstance(carriage, nbt.TAG_Compound):
            continue
        positioning = carriage.get("EntityPositioning")
        if not isinstance(positioning, nbt.TAG_List):
            fail(blockers, f"{carriage_path}.EntityPositioning", "EntityPositioning is not a list")
            continue
        for item_index, item in enumerate(positioning):
            item_path = f"{carriage_path}.EntityPositioning[{item_index}]"
            if not isinstance(item, nbt.TAG_Compound):
                fail(blockers, item_path, "EntityPositioning entry is not a compound")
                continue
            if "RotationAnchors" in item:
                anchors = convert_vector_couple(item["RotationAnchors"], f"{item_path}.RotationAnchors", blockers, source_format)
                if anchors is not None:
                    item["RotationAnchors"] = anchors
            if "Pivot" in item:
                convert_track_node_locations(item["Pivot"], f"{item_path}.Pivot", blockers, source_format)
            for storage_key in ("items", "fluids"):
                if storage_key in item:
                    convert_mounted_storage_list(
                        item[storage_key],
                        f"{item_path}.{storage_key}",
                        blockers,
                        source_format,
                        fluid_normalizations,
                    )


def _mounted_target_pos(value, path, blockers, source_format):
    """Normalize Create's local mounted-storage position codec."""
    if source_format:
        if not isinstance(value, nbt.TAG_Int_Array) or len(value.value) != 3:
            fail(blockers, path, "source mounted storage pos is not IntArray[3]")
            return None
        result = nbt.TAG_Compound()
        for axis, coordinate in zip(("X", "Y", "Z"), value.value):
            result[axis] = nbt.TAG_Int(int(coordinate))
        return result
    if not isinstance(value, nbt.TAG_Compound) or set(value.keys()) != {"X", "Y", "Z"}:
        fail(blockers, path, "target mounted storage pos is not {X,Y,Z}")
        return None
    if any(not integer(value.get(axis)) for axis in ("X", "Y", "Z")):
        fail(blockers, path, "target mounted storage pos contains a non-integer coordinate")
        return None
    return clone_tag(value)


def convert_mounted_storage_list(
    value,
    path,
    blockers,
    source_format,
    fluid_normalizations=None,
):
    """Convert mounted item/fluid storage entries and their nested fluid codecs."""
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "mounted storage collection is not a list")
        return 0
    converted_count = 0
    seen_positions = set()
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"pos", "storage"}:
            fail(blockers, entry_path, "mounted storage entry is not {pos,storage}")
            continue
        position = _mounted_target_pos(entry["pos"], f"{entry_path}.pos", blockers, source_format)
        if position is None:
            continue
        position_key = tuple(as_int(position[axis]) for axis in ("X", "Y", "Z"))
        if position_key in seen_positions:
            fail(blockers, f"{entry_path}.pos", "mounted storage collection contains duplicate positions")
        seen_positions.add(position_key)
        storage = entry["storage"]
        if not isinstance(storage, nbt.TAG_Compound) or not isinstance(storage.get("type"), nbt.TAG_String):
            fail(blockers, f"{entry_path}.storage", "mounted storage is missing a string type")
            continue
        converted_storage = convert_create_fluid_tree(
            storage,
            f"{entry_path}.storage",
            blockers,
            source_format,
            fluid_normalizations,
        )
        if converted_storage is None:
            continue
        if source_format:
            entry["pos"] = position
        elif comparable_tag(entry["pos"]) != comparable_tag(position):
            entry["pos"] = position
        if comparable_tag(storage) != comparable_tag(converted_storage):
            entry["storage"] = converted_storage
            converted_count += 1
    return converted_count


def _finite_number(value):
    return isinstance(value, (nbt.TAG_Double, nbt.TAG_Float)) and math.isfinite(float(value.value))


def _float_tag(value, path, blockers):
    """Narrow a source double to the float representation used by target AABB codec."""
    if not _finite_number(value):
        fail(blockers, path, "value is not a finite floating point number")
        return None
    try:
        narrowed = struct.unpack(">f", struct.pack(">f", float(value.value)))[0]
    except (OverflowError, struct.error):
        fail(blockers, path, "value is not representable as a target float")
        return None
    if not math.isfinite(narrowed):
        fail(blockers, path, "value narrows to a non-finite target float")
        return None
    return nbt.TAG_Float(narrowed)


def convert_contraption_bounds(value, path, blockers, source_format):
    """Convert Create's source double AABB list to target's float AABB list."""
    before = len(blockers)
    if not isinstance(value, nbt.TAG_List) or len(value) != 6:
        fail(blockers, path, "contraption BoundsFront is not a six-number list")
        return None
    expected = nbt.TAG_Double if source_format else nbt.TAG_Float
    if any(not isinstance(part, expected) for part in value):
        fail(blockers, path, "contraption BoundsFront has the wrong numeric element type", expected=expected.__name__)
        return None
    result = []
    for index, part in enumerate(value):
        if source_format:
            converted = _float_tag(part, f"{path}[{index}]", blockers)
        else:
            converted = clone_tag(part) if _finite_number(part) else None
            if converted is None:
                fail(blockers, f"{path}[{index}]", "target BoundsFront contains a non-finite float")
        if converted is not None:
            result.append(converted)
    if len(result) == 6:
        if any(result[index].value > result[index + 3].value for index in range(3)):
            fail(blockers, path, "contraption BoundsFront min exceeds max")
    if len(blockers) != before:
        return None
    return list_tag(result, nbt.TAG_Float)


def _convert_position_list(value, path, blockers, source_format):
    """Convert source List<IntArray> positions to target List<{Pos:IntArray}>."""
    before = len(blockers)
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "contraption position collection is not a list")
        return None
    result = []
    seen = set()
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            position = block_pos_tag(entry, entry_path, blockers)
            if position is None:
                continue
            item = nbt.TAG_Compound()
            item["Pos"] = position
        else:
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Pos"}:
                fail(blockers, entry_path, "target contraption position is not {Pos:int[3]}")
                continue
            position = block_pos_tag(entry.get("Pos"), f"{entry_path}.Pos", blockers)
            if position is None:
                continue
            item = clone_tag(entry)
        key = tuple(int(part) for part in position.value)
        if key in seen:
            fail(blockers, entry_path, "contraption position collection contains duplicate positions")
        seen.add(key)
        result.append(item)
    if len(blockers) != before:
        return None
    return list_tag(result, nbt.TAG_Compound)


def _double_vector(value, path, blockers):
    if not isinstance(value, nbt.TAG_List) or len(value) != 3 or any(not _finite_number(part) for part in value):
        fail(blockers, path, "vector is not a three-number finite list")
        return None
    return clone_tag(value)


def convert_contraption_superglue(value, path, blockers, source_format):
    before = len(blockers)
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "contraption Superglue is not a list")
        return None
    result = []
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            if not isinstance(entry, nbt.TAG_List) or len(entry) != 6 or any(not isinstance(part, nbt.TAG_Double) for part in entry):
                fail(blockers, entry_path, "source Superglue entry is not six doubles")
                continue
            if any(not math.isfinite(float(part.value)) for part in entry):
                fail(blockers, entry_path, "source Superglue entry contains non-finite coordinates")
                continue
            item = nbt.TAG_Compound()
            item["From"] = list_tag([clone_tag(part) for part in entry[:3]], nbt.TAG_Double)
            item["To"] = list_tag([clone_tag(part) for part in entry[3:]], nbt.TAG_Double)
        else:
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"From", "To"}:
                fail(blockers, entry_path, "target Superglue entry is not {From,To}")
                continue
            start = _double_vector(entry.get("From"), f"{entry_path}.From", blockers)
            end = _double_vector(entry.get("To"), f"{entry_path}.To", blockers)
            if start is None or end is None:
                continue
            item = clone_tag(entry)
        result.append(item)
    if len(blockers) != before:
        return None
    return list_tag(result, nbt.TAG_Compound)


def _normalize_direction(value, path, blockers, source_format):
    if not isinstance(value, nbt.TAG_String):
        fail(blockers, path, "contraption direction is not a string")
        return None
    raw = string_value(value)
    normalized = raw.upper() if source_format else raw
    if normalized not in DIRECTIONS or (not source_format and raw != normalized):
        fail(blockers, path, "contraption direction is not canonical", value=raw)
        return None
    return nbt.TAG_String(normalized)


def convert_initial_orientation(
    entity,
    path,
    blockers,
    source_format,
    normalizations=None,
):
    """Normalize OrientedContraptionEntity's enum and require a horizontal value.

    Create 1.21.11 writes enum names in lowercase, while Create 6.0.10's
    NBTHelper.readEnum expects the canonical Java enum name.  If the lowercase
    value is left untouched, the target silently falls back to Direction.UP;
    train-control rendering later calls getCounterClockWise() and crashes.
    """
    if not isinstance(entity, nbt.TAG_Compound):
        fail(blockers, path, "contraption Entity is not a compound")
        return
    value = entity.get("InitialOrientation")
    if value is None:
        fail(blockers, f"{path}.InitialOrientation", "contraption InitialOrientation is missing")
        return
    raw = string_value(value) if isinstance(value, nbt.TAG_String) else None
    direction = _normalize_direction(
        value,
        f"{path}.InitialOrientation",
        blockers,
        source_format,
    )
    if direction is None:
        return
    normalized = string_value(direction)
    if normalized not in {"NORTH", "SOUTH", "WEST", "EAST"}:
        fail(
            blockers,
            f"{path}.InitialOrientation",
            "contraption InitialOrientation is not horizontal",
            value=normalized,
        )
        return
    entity["InitialOrientation"] = direction
    if source_format and raw != normalized and normalizations is not None:
        normalizations.append(
            {
                "path": f"{path}.InitialOrientation",
                "source": raw,
                "target": normalized,
            }
        )


def infer_contraption_source_format(entity, path, blockers):
    """Infer the nested codec from BoundsFront, which changed element type."""
    if not isinstance(entity, nbt.TAG_Compound):
        fail(blockers, path, "contraption entity is not a compound")
        return None
    contraption = entity.get("Contraption")
    if not isinstance(contraption, nbt.TAG_Compound):
        fail(blockers, f"{path}.Contraption", "Contraption is not a compound")
        return None
    bounds = contraption.get("BoundsFront")
    if not isinstance(bounds, nbt.TAG_List) or len(bounds) != 6:
        fail(blockers, f"{path}.Contraption.BoundsFront", "contraption BoundsFront is not a six-number list")
        return None
    if all(isinstance(part, nbt.TAG_Double) for part in bounds):
        return True
    if all(isinstance(part, nbt.TAG_Float) for part in bounds):
        return False
    fail(
        blockers,
        f"{path}.Contraption.BoundsFront",
        "contraption BoundsFront mixes or uses unsupported numeric element types",
    )
    return None


def convert_contraption_facing(contraption, path, blockers, source_format):
    """Normalize subclass Direction serialization used by gantry/bearing contraptions."""
    value = contraption.get("Facing")
    if value is None:
        return
    if isinstance(value, nbt.TAG_Int):
        if not 0 <= as_int(value) <= 5:
            fail(blockers, path, "contraption Facing integer is outside Direction's 0..5 range")
        return
    if not source_format or not isinstance(value, nbt.TAG_String):
        fail(blockers, path, "contraption Facing is neither a source Direction string nor target integer")
        return
    direction = _normalize_direction(value, path, blockers, True)
    if direction is not None:
        contraption["Facing"] = nbt.TAG_Int(DIRECTION_3D_IDS[string_value(direction)])


def convert_contraption_subcontraptions(value, path, blockers, source_format):
    """Convert UUID->BlockFace map emitted by the old DynamicOps codec."""
    before = len(blockers)
    if source_format:
        if not isinstance(value, nbt.TAG_Compound):
            fail(blockers, path, "source SubContraptions is not a compound map")
            return None
        result = []
        for raw_uuid, location in value.items():
            entry_path = f"{path}.{raw_uuid}"
            try:
                uid = uuid.UUID(str(raw_uuid))
            except (ValueError, AttributeError):
                fail(blockers, entry_path, "source SubContraptions key is not a UUID")
                continue
            if not isinstance(location, nbt.TAG_Compound):
                fail(blockers, entry_path, "source SubContraptions value is not a BlockFace compound")
                continue
            keys = set(location.keys())
            if keys == {"pos", "direction"}:
                pos = block_pos_tag(location.get("pos"), f"{entry_path}.pos", blockers)
                direction = _normalize_direction(location.get("direction"), f"{entry_path}.direction", blockers, True)
                location_out = nbt.TAG_Compound()
                if pos is not None:
                    location_out["Pos"] = pos
                if direction is not None:
                    location_out["Face"] = direction
            elif keys == {"Pos", "Face"}:
                pos = block_pos_tag(location.get("Pos"), f"{entry_path}.Pos", blockers)
                direction = _normalize_direction(location.get("Face"), f"{entry_path}.Face", blockers, True)
                location_out = nbt.TAG_Compound()
                if pos is not None:
                    location_out["Pos"] = pos
                if direction is not None:
                    location_out["Face"] = direction
            else:
                fail(blockers, entry_path, "source SubContraptions BlockFace has unknown fields", fields=sorted(keys))
                continue
            item = nbt.TAG_Compound()
            item["Id"] = nbt.TAG_Int_Array()
            item["Id"].value = list(uid.int.to_bytes(16, "big", signed=False))
            item["Id"].value = [int.from_bytes(bytes(item["Id"].value[i:i + 4]), "big", signed=True) for i in range(0, 16, 4)]
            item["Id"].update_fmt(4)
            item["Location"] = location_out
            result.append(item)
    else:
        if not isinstance(value, nbt.TAG_List):
            fail(blockers, path, "target SubContraptions is not a compound list")
            return None
        result = []
        seen = set()
        for index, entry in enumerate(value):
            entry_path = f"{path}[{index}]"
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Id", "Location"}:
                fail(blockers, entry_path, "target SubContraptions entry is not {Id,Location}")
                continue
            uid = uuid_value(entry.get("Id"))
            if uid is None or uid in seen:
                fail(blockers, f"{entry_path}.Id", "target SubContraptions Id is invalid or duplicated")
                continue
            seen.add(uid)
            location = entry.get("Location")
            if not isinstance(location, nbt.TAG_Compound) or set(location.keys()) != {"Pos", "Face"}:
                fail(blockers, f"{entry_path}.Location", "target SubContraptions Location is not {Pos,Face}")
                continue
            if block_pos_tag(location.get("Pos"), f"{entry_path}.Location.Pos", blockers) is None:
                continue
            direction = _normalize_direction(location.get("Face"), f"{entry_path}.Location.Face", blockers, False)
            if direction is None:
                continue
            result.append(clone_tag(entry))
    if len(blockers) != before:
        return None
    return list_tag(result, nbt.TAG_Compound)


def convert_conductor_seats(value, path, blockers, source_format):
    """Validate the already compound-shaped conductor-seat list."""
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "ConductorSeats is not a list")
        return
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Pos", "Forward", "Backward"}:
            fail(blockers, entry_path, "ConductorSeats entry has an unexpected shape")
            continue
        block_pos_tag(entry.get("Pos"), f"{entry_path}.Pos", blockers)
        for key in ("Forward", "Backward"):
            if not isinstance(entry.get(key), nbt.TAG_Byte) or as_int(entry[key]) not in (0, 1):
                fail(blockers, f"{entry_path}.{key}", "ConductorSeats flag is not a byte boolean")


def convert_captured_multiblocks(value, path, blockers, source_format):
    """Normalize CapturedMultiblocks Parts from dense positions to target compounds."""
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "CapturedMultiblocks is not a list")
        return
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != {"Controller", "Parts"}:
            fail(blockers, entry_path, "CapturedMultiblocks entry has an unexpected shape")
            continue
        block_pos_tag(entry.get("Controller"), f"{entry_path}.Controller", blockers)
        parts = entry.get("Parts")
        if not isinstance(parts, nbt.TAG_List):
            fail(blockers, f"{entry_path}.Parts", "CapturedMultiblocks Parts is not a list")
            continue
        converted = []
        seen = set()
        for part_index, part in enumerate(parts):
            part_path = f"{entry_path}.Parts[{part_index}]"
            if source_format:
                position = block_pos_tag(part, part_path, blockers)
                if position is None:
                    continue
                wrapped = nbt.TAG_Compound()
                wrapped["Pos"] = position
            else:
                if not isinstance(part, nbt.TAG_Compound) or set(part.keys()) != {"Pos"}:
                    fail(blockers, part_path, "target CapturedMultiblocks Part is not {Pos:int[3]}")
                    continue
                position = block_pos_tag(part.get("Pos"), f"{part_path}.Pos", blockers)
                if position is None:
                    continue
                wrapped = clone_tag(part)
            key = tuple(int(component) for component in position.value)
            if key in seen:
                fail(blockers, part_path, "CapturedMultiblocks Parts contains duplicate positions")
            seen.add(key)
            converted.append(wrapped)
        if source_format:
            entry["Parts"] = list_tag(converted, nbt.TAG_Compound)
        else:
            entry["Parts"] = list_tag(converted, nbt.TAG_Compound)


def convert_contraption_entity(
    entity,
    path,
    blockers,
    source_format=None,
    fluid_normalizations=None,
    initial_orientation_normalizations=None,
):
    # Disassembled/placeholder carriages can legitimately omit Entity.  When it
    # is present, however, a malformed Contraption must block rather than be
    # silently dropped by Create's optional entity reader.
    if entity is None:
        return
    if not isinstance(entity, nbt.TAG_Compound):
        fail(blockers, path, "contraption Entity is not a compound")
        return
    contraption = entity.get("Contraption")
    if not isinstance(contraption, nbt.TAG_Compound):
        fail(blockers, f"{path}.Contraption", "Contraption is not a compound")
        return
    if source_format is None:
        source_format = infer_contraption_source_format(entity, path, blockers)
        if source_format is None:
            return
    convert_initial_orientation(
        entity,
        path,
        blockers,
        source_format,
        initial_orientation_normalizations,
    )
    required = {
        "BoundsFront",
        "Superglue",
        "Seats",
        "Interactors",
        "SubContraptions",
        "Anchor",
        "Actors",
        "CapturedMultiblocks",
        "DisabledActors",
        "Blocks",
        "Type",
        "Stalled",
        "BottomlessSupply",
    }
    missing = sorted(required - set(contraption.keys()))
    if missing:
        fail(blockers, f"{path}.Contraption", "Contraption is missing core fields", fields=missing)
    if "AssemblyDirection" in contraption:
        direction = _normalize_direction(
            contraption.get("AssemblyDirection"),
            f"{path}.Contraption.AssemblyDirection",
            blockers,
            source_format,
        )
        if direction is not None:
            contraption["AssemblyDirection"] = direction
    convert_contraption_facing(
        contraption,
        f"{path}.Contraption.Facing",
        blockers,
        source_format,
    )
    bounds = convert_contraption_bounds(contraption.get("BoundsFront"), f"{path}.Contraption.BoundsFront", blockers, source_format)
    if bounds is not None:
        contraption["BoundsFront"] = bounds
    for key in ("Seats", "Interactors"):
        converted = _convert_position_list(contraption.get(key), f"{path}.Contraption.{key}", blockers, source_format)
        if converted is not None:
            contraption[key] = converted
    glue = convert_contraption_superglue(contraption.get("Superglue"), f"{path}.Contraption.Superglue", blockers, source_format)
    if glue is not None:
        contraption["Superglue"] = glue
    sub = convert_contraption_subcontraptions(contraption.get("SubContraptions"), f"{path}.Contraption.SubContraptions", blockers, source_format)
    if sub is not None:
        contraption["SubContraptions"] = sub
    if "ConductorSeats" in contraption:
        convert_conductor_seats(
            contraption.get("ConductorSeats"),
            f"{path}.Contraption.ConductorSeats",
            blockers,
            source_format,
        )
    convert_captured_multiblocks(
        contraption.get("CapturedMultiblocks"),
        f"{path}.Contraption.CapturedMultiblocks",
        blockers,
        source_format,
    )
    for storage_key in ("items", "fluids"):
        if storage_key in contraption:
            convert_mounted_storage_list(
                contraption[storage_key],
                f"{path}.Contraption.{storage_key}",
                blockers,
                source_format,
                fluid_normalizations,
            )
    for key in ("Actors", "DisabledActors"):
        value = contraption.get(key)
        if not isinstance(value, nbt.TAG_List):
            fail(blockers, f"{path}.Contraption.{key}", f"{key} is not a list")
        elif any(not isinstance(entry, nbt.TAG_Compound) for entry in value):
            fail(blockers, f"{path}.Contraption.{key}", f"{key} contains a non-compound entry")


def empty_source_stack(stack):
    if not isinstance(stack, nbt.TAG_Compound):
        return False
    if not stack:
        return True
    identifier = stack.get("id")
    count = stack.get("count", stack.get("Count"))
    return (
        isinstance(identifier, nbt.TAG_String)
        and string_value(identifier) == "minecraft:air"
        and integer(count)
        and as_int(count) == 0
    )


def convert_offline_buffer(value, path, blockers, source_format):
    """Convert Fabric's dense Size/Stacks handler to NeoForge's sparse Size/Items handler."""
    if not isinstance(value, nbt.TAG_Compound):
        fail(blockers, path, "station port OfflineBuffer is not a compound")
        return None
    if source_format:
        if set(value.keys()) != {"Size", "Stacks"}:
            fail(blockers, path, "source OfflineBuffer is not {Size,Stacks}")
            return None
        size_tag = value.get("Size")
        stacks = value.get("Stacks")
        if not integer(size_tag) or as_int(size_tag) < 0:
            fail(blockers, f"{path}.Size", "source OfflineBuffer Size is not a non-negative integer")
            return None
        size = as_int(size_tag)
        if not isinstance(stacks, nbt.TAG_List) or len(stacks) != size:
            fail(blockers, f"{path}.Stacks", "source OfflineBuffer Stacks length does not match Size")
            return None
        items = []
        for slot, stack in enumerate(stacks):
            stack_path = f"{path}.Stacks[{slot}]"
            if empty_source_stack(stack):
                continue
            if not isinstance(stack, nbt.TAG_Compound):
                fail(blockers, stack_path, "source OfflineBuffer stack is not a compound")
                continue
            identifier = stack.get("id")
            count = stack.get("count", stack.get("Count"))
            if (
                not isinstance(identifier, nbt.TAG_String)
                or resource_location(identifier) is None
                or not integer(count)
                or as_int(count) <= 0
            ):
                fail(blockers, stack_path, "source OfflineBuffer stack is neither empty nor a valid ItemStack")
                continue
            target_stack = clone_tag(stack)
            target_stack["Slot"] = nbt.TAG_Int(slot)
            items.append(target_stack)
        target = nbt.TAG_Compound()
        target["Items"] = list_tag(items, nbt.TAG_Compound)
        target["Size"] = nbt.TAG_Int(size)
        return target

    if set(value.keys()) != {"Items", "Size"}:
        fail(blockers, path, "target OfflineBuffer is not {Items,Size}")
        return None
    size_tag = value.get("Size")
    items = value.get("Items")
    if not integer(size_tag) or as_int(size_tag) < 0:
        fail(blockers, f"{path}.Size", "target OfflineBuffer Size is not a non-negative integer")
        return None
    size = as_int(size_tag)
    if not isinstance(items, nbt.TAG_List):
        fail(blockers, f"{path}.Items", "target OfflineBuffer Items is not a list")
        return None
    seen_slots = set()
    for index, stack in enumerate(items):
        stack_path = f"{path}.Items[{index}]"
        if not isinstance(stack, nbt.TAG_Compound) or not integer(stack.get("Slot")):
            fail(blockers, stack_path, "target OfflineBuffer item has no integer Slot")
            continue
        slot = as_int(stack["Slot"])
        if slot < 0 or slot >= size:
            fail(blockers, f"{stack_path}.Slot", "target OfflineBuffer Slot is outside Size")
        if slot in seen_slots:
            fail(blockers, f"{stack_path}.Slot", "target OfflineBuffer contains duplicate Slot")
        seen_slots.add(slot)
    return clone_tag(value)


def convert_station_ports(station, path, blockers, source_format):
    if not isinstance(station, nbt.TAG_Compound):
        fail(blockers, path, "station point is not a compound")
        return
    ports = station.get("Ports")
    if source_format:
        if not isinstance(ports, nbt.TAG_Compound) or set(ports.keys()) != {"Keys", "Values"}:
            fail(blockers, f"{path}.Ports", "source Ports is not {Keys,Values}")
            return
        keys, values = ports["Keys"], ports["Values"]
        if not isinstance(keys, nbt.TAG_List) or not isinstance(values, nbt.TAG_List) or len(keys) != len(values):
            fail(blockers, f"{path}.Ports", "source Ports keys/values lengths differ or are not lists")
            return
        out = []
        for index, (key, value) in enumerate(zip(keys, values)):
            item_path = f"{path}.Ports[{index}]"
            pos = block_pos_tag(key, f"{item_path}.Pos", blockers)
            if not isinstance(value, nbt.TAG_Compound):
                fail(blockers, item_path, "source port value is not a compound")
                continue
            if set(value.keys()) != SOURCE_PORT_KEYS:
                fail(blockers, item_path, "source port value does not have exact address/offlineBuffer/primed/restoring fields")
                continue
            if (
                not isinstance(value.get("address"), nbt.TAG_String)
                or not isinstance(value.get("primed"), nbt.TAG_Byte)
                or as_int(value["primed"]) not in (0, 1)
                or not isinstance(value.get("restoring"), nbt.TAG_Byte)
                or as_int(value["restoring"]) not in (0, 1)
            ):
                fail(blockers, item_path, "source port value has invalid field types")
                continue
            if as_int(value["restoring"]) != 0:
                fail(blockers, f"{item_path}.restoring", "source port is mid-restore and has no stable target representation")
                continue
            offline_buffer = convert_offline_buffer(value["offlineBuffer"], f"{item_path}.offlineBuffer", blockers, True)
            if pos is None or offline_buffer is None:
                continue
            target = nbt.TAG_Compound()
            target["Address"] = clone_tag(value["address"])
            target["OfflineBuffer"] = offline_buffer
            target["Primed"] = clone_tag(value["primed"])
            target["Pos"] = pos
            out.append(target)
        station["Ports"] = list_tag(out, nbt.TAG_Compound)
    else:
        if not isinstance(ports, nbt.TAG_List):
            fail(blockers, f"{path}.Ports", "target Ports is not a list")
            return
        for index, port in enumerate(ports):
            p = f"{path}.Ports[{index}]"
            if not isinstance(port, nbt.TAG_Compound) or set(port.keys()) != TARGET_PORT_KEYS:
                fail(blockers, p, "target port is not {Address,OfflineBuffer,Primed,Pos}")
                continue
            if not isinstance(port.get("Address"), nbt.TAG_String):
                fail(blockers, f"{p}.Address", "target port Address is not a string")
            if not isinstance(port.get("Primed"), nbt.TAG_Byte) or as_int(port["Primed"]) not in (0, 1):
                fail(blockers, f"{p}.Primed", "target port Primed is not a byte boolean")
            block_pos_tag(port.get("Pos"), f"{p}.Pos", blockers)
            convert_offline_buffer(port.get("OfflineBuffer"), f"{p}.OfflineBuffer", blockers, False)
    return len(ports) if isinstance(ports, nbt.TAG_List) else 0


def signed_int32(value):
    """Return the signed Java int representation used by UUID int arrays."""
    return struct.unpack(">i", struct.pack(">I", value & 0xFFFFFFFF))[0]


def uuid_int_array(value, path, blockers, source_format):
    """Normalize the two Create UUID encodings without guessing arbitrary strings."""
    if isinstance(value, nbt.TAG_Int_Array) and len(value.value) == 4:
        return clone_tag(value)
    if source_format and isinstance(value, nbt.TAG_String):
        try:
            parsed = uuid.UUID(string_value(value))
        except (ValueError, AttributeError) as exc:
            fail(blockers, path, "UUID string is malformed", value=string_value(value))
            return None
        high = (parsed.int >> 64) & 0xFFFFFFFFFFFFFFFF
        low = parsed.int & 0xFFFFFFFFFFFFFFFF
        result = nbt.TAG_Int_Array()
        result.value = [
            signed_int32(high >> 32),
            signed_int32(high),
            signed_int32(low >> 32),
            signed_int32(low),
        ]
        result.update_fmt(4)
        return result
    fail(blockers, path, "UUID is not a four-int array" if not source_format else "UUID is neither a UUID string nor a four-int array")
    return None


def convert_dimension_palette(value, path, blockers, source_format):
    """Convert Create's 1.21.11 string palette to the 1.21.1 compound palette."""
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "DimensionPalette is not a list")
        return None
    result = []
    seen = set()
    for index, entry in enumerate(value):
        entry_path = f"{path}[{index}]"
        if source_format:
            if not isinstance(entry, nbt.TAG_String):
                fail(blockers, entry_path, "source dimension palette entry is not a string")
                continue
            dimension = resource_location(entry)
            if dimension is None:
                fail(blockers, entry_path, "source dimension palette entry is not a namespaced resource location")
                continue
            target = nbt.TAG_Compound()
            target["Id"] = nbt.TAG_String(dimension)
        else:
            if not isinstance(entry, nbt.TAG_Compound) or set(entry.keys()) != DIMENSION_KEYS:
                fail(blockers, entry_path, "target dimension palette entry is not {Id:string}")
                continue
            dimension = resource_location(entry.get("Id"))
            if dimension is None:
                fail(blockers, f"{entry_path}.Id", "target dimension palette Id is not a namespaced resource location")
                continue
            target = clone_tag(entry)
        if dimension in seen:
            fail(blockers, entry_path, "dimension palette contains duplicate dimension", dimension=dimension)
        seen.add(dimension)
        result.append(target)
    if blockers and any(item.get("path", "").startswith(path) for item in blockers):
        return None
    return list_tag(result, nbt.TAG_Compound)


def convert_signal_blocks(value, path, blockers, source_format):
    """Convert SignalEdgeGroup UUID and Connected map representations."""
    if not isinstance(value, nbt.TAG_List):
        fail(blockers, path, "SignalBlocks is not a list")
        return None
    result = []
    ids = set()
    for index, group in enumerate(value):
        group_path = f"{path}[{index}]"
        if not isinstance(group, nbt.TAG_Compound):
            fail(blockers, group_path, "signal group is not a compound")
            continue
        unknown = sorted(set(group.keys()) - SIGNAL_KEYS)
        if unknown:
            fail(blockers, group_path, "signal group has unknown fields", fields=unknown)
        group_id = uuid_int_array(group.get("Id"), f"{group_path}.Id", blockers, source_format)
        if group_id is not None:
            identity = tuple(int(x) for x in group_id.value)
            if identity in ids:
                fail(blockers, group_path, "duplicate signal group UUID")
            ids.add(identity)
        connected = group.get("Connected")
        target_connected = []
        if source_format:
            if not isinstance(connected, nbt.TAG_Compound):
                fail(blockers, f"{group_path}.Connected", "source Connected is not a compound UUID map")
            else:
                for key, target_value in connected.items():
                    key_tag = nbt.TAG_String(key)
                    key_uuid = uuid_int_array(key_tag, f"{group_path}.Connected.{key}.Key", blockers, True)
                    value_uuid = uuid_int_array(target_value, f"{group_path}.Connected.{key}.Value", blockers, True)
                    if key_uuid is None or value_uuid is None:
                        continue
                    pair = nbt.TAG_Compound()
                    pair["Key"] = key_uuid
                    pair["Value"] = value_uuid
                    target_connected.append(pair)
        else:
            if not isinstance(connected, nbt.TAG_List):
                fail(blockers, f"{group_path}.Connected", "target Connected is not a list")
            else:
                for pair_index, pair in enumerate(connected):
                    pair_path = f"{group_path}.Connected[{pair_index}]"
                    if not isinstance(pair, nbt.TAG_Compound) or set(pair.keys()) != {"Key", "Value"}:
                        fail(blockers, pair_path, "target Connected entry is not {Key,Value}")
                        continue
                    key_uuid = uuid_int_array(pair.get("Key"), f"{pair_path}.Key", blockers, False)
                    value_uuid = uuid_int_array(pair.get("Value"), f"{pair_path}.Value", blockers, False)
                    if key_uuid is None or value_uuid is None:
                        continue
                    target_connected.append(clone_tag(pair))
        if group_id is None:
            continue
        color = group.get("Color")
        if not isinstance(color, nbt.TAG_String):
            fail(blockers, f"{group_path}.Color", "signal group Color is not a string")
            normalized_color = None
        else:
            raw_color = string_value(color)
            normalized_color = raw_color.upper() if source_format else raw_color
            if not source_format and raw_color != raw_color.upper():
                fail(blockers, f"{group_path}.Color", "target signal group Color is not the canonical uppercase enum", value=raw_color)
                normalized_color = None
            elif normalized_color not in EDGE_GROUP_COLORS:
                fail(blockers, f"{group_path}.Color", "signal group Color is not a known EdgeGroupColor", value=raw_color)
                normalized_color = None
        fallback = group.get("Fallback")
        if not isinstance(fallback, nbt.TAG_Byte) or as_int(fallback) not in (0, 1):
            fail(blockers, f"{group_path}.Fallback", "signal group Fallback is not a byte boolean")
        target = nbt.TAG_Compound()
        target["Id"] = group_id
        target["Connected"] = list_tag(target_connected, nbt.TAG_Compound)
        if normalized_color is not None:
            target["Color"] = nbt.TAG_String(normalized_color)
        if isinstance(fallback, nbt.TAG_Byte) and as_int(fallback) in (0, 1):
            target["Fallback"] = clone_tag(fallback)
        result.append(target)
    if any(item.get("path", "").startswith(path) for item in blockers):
        return None
    return list_tag(result, nbt.TAG_Compound)


def validate_track_collections(data, path, blockers):
    for key in ("RailGraphs", "Trains"):
        value = data.get(key)
        if not isinstance(value, nbt.TAG_List) or any(not isinstance(entry, nbt.TAG_Compound) for entry in value):
            fail(blockers, f"{path}.{key}", f"{key} is not a compound list")
    if not isinstance(data.get("SignalBlocks"), nbt.TAG_List):
        fail(blockers, f"{path}.SignalBlocks", "SignalBlocks is not a list")


def track_schema_counts(data, source_format):
    counts = {
        "train_names": 0,
        "train_names_requiring_json": 0,
        "runtime_state_conversions": 0,
        "schedule_entries": 0,
        "condition_columns": 0,
        "conditions": 0,
        "reserved_signal_blocks": 0,
        "occupied_observers": 0,
        "navigation_path_entries": 0,
        "rotation_anchor_couples": 0,
        "mounted_item_storage_entries": 0,
        "mounted_fluid_storage_entries": 0,
        "mounted_nonempty_fluid_stacks": 0,
        "bezier_connections": 0,
        "bezier_position_couples": 0,
        "bezier_vector_couples": 0,
        "stations": 0,
        "station_ports": 0,
        "carriage_contraptions": 0,
        "contraption_bounds": 0,
        "contraption_seats": 0,
        "contraption_interactors": 0,
        "contraption_superglue": 0,
        "contraption_subcontraptions": 0,
        "captured_multiblock_parts": 0,
    }
    graphs = data.get("RailGraphs") if isinstance(data, nbt.TAG_Compound) else None
    if isinstance(graphs, nbt.TAG_List):
        for graph in graphs:
            if not isinstance(graph, nbt.TAG_Compound):
                continue
            points = graph.get("Points")
            stations = points.get("create:station") if isinstance(points, nbt.TAG_Compound) else None
            if isinstance(stations, nbt.TAG_List):
                counts["stations"] += len(stations)
                for station in stations:
                    if not isinstance(station, nbt.TAG_Compound):
                        continue
                    ports = station.get("Ports")
                    if source_format and isinstance(ports, nbt.TAG_Compound) and isinstance(ports.get("Keys"), nbt.TAG_List):
                        counts["station_ports"] += len(ports["Keys"])
                    elif not source_format and isinstance(ports, nbt.TAG_List):
                        counts["station_ports"] += len(ports)
            nodes = graph.get("Nodes")
            if not isinstance(nodes, nbt.TAG_List):
                continue
            for node in nodes:
                connections = node.get("Connections") if isinstance(node, nbt.TAG_Compound) else None
                if not isinstance(connections, nbt.TAG_List):
                    continue
                for connection in connections:
                    edge_data = connection.get("EdgeData") if isinstance(connection, nbt.TAG_Compound) else None
                    if not isinstance(edge_data, nbt.TAG_Compound):
                        continue
                    curve = edge_data.get("BezierConnection") if source_format else edge_data
                    if not isinstance(curve, nbt.TAG_Compound) or "Positions" not in curve:
                        continue
                    counts["bezier_connections"] += 1
                    counts["bezier_position_couples"] += 1
                    counts["bezier_vector_couples"] += sum(key in curve for key in ("Starts", "Axes", "Normals"))

    trains = data.get("Trains") if isinstance(data, nbt.TAG_Compound) else None
    if not isinstance(trains, nbt.TAG_List):
        return counts
    for train in trains:
        if not isinstance(train, nbt.TAG_Compound):
            continue
        name = train.get("Name")
        if isinstance(name, nbt.TAG_String):
            counts["train_names"] += 1
            if source_format:
                try:
                    parsed_name = json.loads(string_value(name))
                except (TypeError, ValueError):
                    parsed_name = None
                if parsed_name is None:
                    counts["train_names_requiring_json"] += 1
        for key, count_key in (
            ("ReservedSignalBlocks", "reserved_signal_blocks"),
            ("OccupiedObservers", "occupied_observers"),
        ):
            value = train.get(key)
            if isinstance(value, nbt.TAG_List):
                counts[count_key] += len(value)
        navigation = train.get("Navigation")
        if isinstance(navigation, nbt.TAG_Compound) and isinstance(navigation.get("Path"), nbt.TAG_List):
            counts["navigation_path_entries"] += len(navigation["Path"])
        runtime = train.get("Runtime")
        if source_format and isinstance(runtime, nbt.TAG_Compound) and isinstance(runtime.get("State"), nbt.TAG_String):
            if string_value(runtime["State"]) != string_value(runtime["State"]).upper():
                counts["runtime_state_conversions"] += 1
        schedule = runtime.get("Schedule") if isinstance(runtime, nbt.TAG_Compound) else None
        entries = schedule.get("Entries") if isinstance(schedule, nbt.TAG_Compound) else None
        if isinstance(entries, nbt.TAG_List):
            counts["schedule_entries"] += len(entries)
            for entry in entries:
                columns = entry.get("Conditions") if isinstance(entry, nbt.TAG_Compound) else None
                if not isinstance(columns, nbt.TAG_List):
                    continue
                counts["condition_columns"] += len(columns)
                for column in columns:
                    if isinstance(column, nbt.TAG_List):
                        counts["conditions"] += len(column)
        carriages = train.get("Carriages")
        if not isinstance(carriages, nbt.TAG_List):
            continue
        for carriage in carriages:
            positioning = carriage.get("EntityPositioning") if isinstance(carriage, nbt.TAG_Compound) else None
            if not isinstance(positioning, nbt.TAG_List):
                continue
            counts["rotation_anchor_couples"] += sum(
                isinstance(item, nbt.TAG_Compound) and "RotationAnchors" in item
                for item in positioning
            )
            for item in positioning:
                if not isinstance(item, nbt.TAG_Compound):
                    continue
                for storage_key, count_key in (
                    ("items", "mounted_item_storage_entries"),
                    ("fluids", "mounted_fluid_storage_entries"),
                ):
                    entries = item.get(storage_key)
                    if isinstance(entries, nbt.TAG_List):
                        counts[count_key] += len(entries)
                        if storage_key == "fluids":
                            counts["mounted_nonempty_fluid_stacks"] += sum(
                                isinstance(entry, nbt.TAG_Compound)
                                and isinstance(entry.get("storage"), nbt.TAG_Compound)
                                and isinstance(entry["storage"].get("fluid"), nbt.TAG_Compound)
                                and bool(entry["storage"]["fluid"])
                                for entry in entries
                            )
            entity = carriage.get("Entity") if isinstance(carriage, nbt.TAG_Compound) else None
            contraption = entity.get("Contraption") if isinstance(entity, nbt.TAG_Compound) else None
            if isinstance(contraption, nbt.TAG_Compound):
                counts["carriage_contraptions"] += 1
                captured = contraption.get("CapturedMultiblocks")
                if isinstance(captured, nbt.TAG_List):
                    for captured_entry in captured:
                        if isinstance(captured_entry, nbt.TAG_Compound) and isinstance(captured_entry.get("Parts"), nbt.TAG_List):
                            counts["captured_multiblock_parts"] += len(captured_entry["Parts"])
                bounds = contraption.get("BoundsFront")
                if isinstance(bounds, nbt.TAG_List):
                    counts["contraption_bounds"] += 1
                for key in ("Seats", "Interactors", "Superglue", "SubContraptions"):
                    value = contraption.get(key)
                    if key == "SubContraptions" and isinstance(value, nbt.TAG_Compound) and source_format:
                        counts["contraption_subcontraptions"] += len(value)
                    elif key == "Seats" and isinstance(value, nbt.TAG_List):
                        counts["contraption_seats"] += len(value)
                    elif key == "Interactors" and isinstance(value, nbt.TAG_List):
                        counts["contraption_interactors"] += len(value)
                    elif key == "Superglue" and isinstance(value, nbt.TAG_List):
                        counts["contraption_superglue"] += len(value)
                for storage_key, count_key in (
                    ("items", "mounted_item_storage_entries"),
                    ("fluids", "mounted_fluid_storage_entries"),
                ):
                    entries = contraption.get(storage_key)
                    if isinstance(entries, nbt.TAG_List):
                        counts[count_key] += len(entries)
                        if storage_key == "fluids":
                            counts["mounted_nonempty_fluid_stacks"] += sum(
                                isinstance(entry, nbt.TAG_Compound)
                                and isinstance(entry.get("storage"), nbt.TAG_Compound)
                                and isinstance(entry["storage"].get("fluid"), nbt.TAG_Compound)
                                and bool(entry["storage"]["fluid"])
                                for entry in entries
                            )
    return counts


def convert_track_nested_schema(
    data,
    blockers,
    source_format,
    fluid_normalizations=None,
    initial_orientation_normalizations=None,
):
    """Normalize the nested Create railway codecs that changed shape between releases."""
    graphs = data.get("RailGraphs")
    convert_graph_geometry(graphs, "data.RailGraphs", blockers, source_format)
    if isinstance(graphs, nbt.TAG_List):
        for graph_index, graph in enumerate(graphs):
            if not isinstance(graph, nbt.TAG_Compound):
                continue
            points = graph.get("Points")
            if not isinstance(points, nbt.TAG_Compound):
                continue
            stations = points.get("create:station")
            if not isinstance(stations, nbt.TAG_List):
                fail(blockers, f"data.RailGraphs[{graph_index}].Points.create:station", "station points is not a list")
                continue
            for station_index, station in enumerate(stations):
                station_path = f"data.RailGraphs[{graph_index}].Points.create:station[{station_index}]"
                if isinstance(station, nbt.TAG_Compound) and "BlockEntityPos" in station:
                    converted_pos = block_pos_tag(station["BlockEntityPos"], f"{station_path}.BlockEntityPos", blockers)
                    if converted_pos is not None:
                        station["BlockEntityPos"] = converted_pos
                convert_station_ports(
                    station,
                    station_path,
                    blockers,
                    source_format,
                )

    trains = data.get("Trains")
    if not isinstance(trains, nbt.TAG_List):
        return
    for train_index, train in enumerate(trains):
        train_path = f"data.Trains[{train_index}]"
        if not isinstance(train, nbt.TAG_Compound):
            continue
        if "Name" not in train:
            fail(blockers, f"{train_path}.Name", "train Name is missing")
        else:
            normalized_name = json_component_text(train["Name"], f"{train_path}.Name", blockers, source_format)
            if normalized_name is not None:
                train["Name"] = normalized_name

        for key in ("ReservedSignalBlocks", "OccupiedObservers"):
            if key not in train:
                fail(blockers, f"{train_path}.{key}", "train UUID set is missing")
                continue
            converted = convert_uuid_set(train[key], f"{train_path}.{key}", blockers, source_format)
            if converted is not None:
                train[key] = converted

        navigation = train.get("Navigation")
        if navigation is None:
            fail(blockers, f"{train_path}.Navigation", "Navigation is missing")
        else:
            converted_navigation = convert_navigation(navigation, f"{train_path}.Navigation", blockers, source_format)
            if converted_navigation is not None:
                train["Navigation"] = converted_navigation

        runtime = train.get("Runtime")
        convert_schedule_runtime_state(runtime, f"{train_path}.Runtime", blockers, source_format)
        if isinstance(runtime, nbt.TAG_Compound) and "Schedule" in runtime:
            convert_schedule_columns(runtime["Schedule"], f"{train_path}.Runtime.Schedule", blockers, source_format)
        carriages = train.get("Carriages")
        convert_entity_positioning(
            carriages,
            f"{train_path}.Carriages",
            blockers,
            source_format,
            fluid_normalizations,
        )
        if isinstance(carriages, nbt.TAG_List):
            for carriage_index, carriage in enumerate(carriages):
                if not isinstance(carriage, nbt.TAG_Compound):
                    continue
                convert_contraption_entity(
                    carriage.get("Entity"),
                    f"{train_path}.Carriages[{carriage_index}].Entity",
                    blockers,
                    source_format,
                    fluid_normalizations,
                    initial_orientation_normalizations,
                )

    # Bogey travelling points, graph nodes, stations, navigation and migrations all
    # reuse TrackNodeLocation. Its Pos switched from int[3] to a BlockPos compound.
    convert_track_node_locations(data, "data", blockers, source_format)

    return data


def convert_tracks_root(root, source_game_dir, target_game_dir=None):
    """Fail-closed conversion for Create RailwaySavedData (create_tracks.dat)."""
    working = clone_file(root)
    blockers = []
    unknown_root = sorted(set(working.keys()) - {"DataVersion", "data"})
    if unknown_root:
        fail(blockers, "", "SavedData root has unknown fields", fields=unknown_root)
    version = working.get("DataVersion")
    if not integer(version) or as_int(version) not in (3955, 4671):
        fail(blockers, "DataVersion", "unsupported Create tracks DataVersion")
        source_version = None
    else:
        source_version = as_int(version)
    source_format = source_version == 4671
    data = working.get("data")
    if not isinstance(data, nbt.TAG_Compound):
        fail(blockers, "data", "Create tracks data is not a compound")
        data = None
    elif set(data.keys()) != TRACK_KEYS:
        fail(blockers, "data", "Create tracks data has an unexpected top-level shape", fields=sorted(set(data.keys()) ^ TRACK_KEYS))
    context = item_context(source_game_dir, target_game_dir, {"saved_data": "create_tracks.dat"})
    fluid_normalizations = []
    initial_orientation_normalizations = []
    schema_counts = track_schema_counts(data, source_format) if data is not None else {}
    if data is not None:
        validate_track_collections(data, "data", blockers)
        palette = convert_dimension_palette(data.get("DimensionPalette"), "data.DimensionPalette", blockers, source_format)
        signals = convert_signal_blocks(data.get("SignalBlocks"), "data.SignalBlocks", blockers, source_format)
        if palette is not None:
            data["DimensionPalette"] = palette
        if signals is not None:
            data["SignalBlocks"] = signals
        convert_track_nested_schema(
            data,
            blockers,
            source_format,
            fluid_normalizations,
            initial_orientation_normalizations,
        )
        # Create stores carriage entities and their contraption inventories inside
        # this SavedData file, outside the ordinary entity MCA pipeline.
        walk_entity_item_stacks(data, "data", context)
    blockers.extend(context["blockers"])
    if blockers:
        return None, {
            "status": "BLOCKED",
            "source_format": "1.21.11" if source_format else "1.21.1-or-unknown",
            "source_data_version": source_version,
            "schema_counts": schema_counts,
            "fluid_semantic_floor_normalizations": fluid_normalizations,
            "blockers": blockers,
        }
    if data is not None:
        working["data"] = data
    working["DataVersion"] = nbt.TAG_Int(TARGET_DATA_VERSION)
    semantic_sha = tag_digest(working["data"])
    changed = comparable_tag(root) != comparable_tag(working)
    return working, {
        "status": "CONVERTED" if changed else "ALREADY_1_21_1",
        "source_format": "1.21.11" if source_format else "1.21.1",
        "source_data_version": source_version,
        "target_data_version": TARGET_DATA_VERSION,
        "rail_graphs": len(data["RailGraphs"]) if data is not None else 0,
        "signal_groups": len(data["SignalBlocks"]) if data is not None else 0,
        "trains": len(data["Trains"]) if data is not None else 0,
        "dimensions": len(data["DimensionPalette"]) if data is not None else 0,
        "item_stacks_scanned": context["scanned"],
        "item_stacks_changed": len(context["changed_stacks"]),
        "signal_uuid_conversions": sum(
            1 for group in (root.get("data", {}).get("SignalBlocks", []) if source_format else [])
            if isinstance(group, nbt.TAG_Compound) and isinstance(group.get("Id"), nbt.TAG_String)
        ),
        "signal_color_conversions": sum(
            1 for group in (root.get("data", {}).get("SignalBlocks", []) if source_format else [])
            if isinstance(group, nbt.TAG_Compound)
            and isinstance(group.get("Color"), nbt.TAG_String)
            and string_value(group["Color"]) != string_value(group["Color"]).upper()
        ),
        "schema_counts": schema_counts,
        "fluid_semantic_floor_normalizations": fluid_normalizations,
        "initial_orientation_normalizations": initial_orientation_normalizations,
        "semantic_sha256": semantic_sha,
        "source_nbt_sha256": tag_digest(root),
        "target_nbt_sha256": tag_digest(working),
        "blockers": [],
    }


class ConversionBlocked(ValueError):
    pass


def clone_file(root):
    result = nbt.NBTFile()
    result.name = getattr(root, "name", "")
    for key, value in root.items():
        result[key] = clone_tag(value)
    return result


def tag_digest(value):
    return hashlib.sha256(repr(comparable_tag(value)).encode("utf-8")).hexdigest()


def fail(blockers, path, reason, **details):
    blockers.append({"path": path, "reason": reason, **details})


def integer(value):
    return isinstance(value, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long))


def uuid_value(value):
    if not isinstance(value, nbt.TAG_Int_Array) or len(value.value) != 4:
        return None
    return tuple(int(part) for part in value.value)


def vector_value(value):
    if not isinstance(value, nbt.TAG_Int_Array) or len(value.value) != 3:
        return None
    return tuple(int(part) for part in value.value)


def resource_location(value):
    if not isinstance(value, nbt.TAG_String):
        return None
    text = string_value(value)
    if ":" not in text or any(char.isspace() for char in text):
        return None
    namespace, path = text.split(":", 1)
    if not namespace or not path:
        return None
    return text


def item_context(source_game_dir, target_game_dir, reference):
    context = {
        "reference": reference,
        "game_dir": Path(source_game_dir),
        "target_game_dir": Path(target_game_dir) if target_game_dir else None,
        "changed_stacks": set(),
        "visited": set(),
        "scanned": 0,
    }
    for key in ITEM_CONTEXT_LISTS:
        context[key] = []
    return context


def validate_promises(value, path, blockers, context):
    if not isinstance(value, nbt.TAG_Compound):
        fail(blockers, path, "Promises is not a compound")
        return []
    unknown = sorted(set(value.keys()) - {"List"})
    if unknown:
        fail(blockers, path, "Promises has unknown fields", fields=unknown)
    promises = value.get("List")
    if not isinstance(promises, nbt.TAG_List):
        fail(blockers, f"{path}.List", "promise list is missing or not a list")
        return []
    semantic = []
    for index, promise in enumerate(promises):
        promise_path = f"{path}.List[{index}]"
        if not isinstance(promise, nbt.TAG_Compound):
            fail(blockers, promise_path, "promise is not a compound")
            continue
        unknown = sorted(set(promise.keys()) - PROMISE_KEYS)
        if unknown:
            fail(blockers, promise_path, "promise has unknown fields", fields=unknown)
        ticks = promise.get("ticks_existed")
        if not integer(ticks) or as_int(ticks) < 0:
            fail(blockers, f"{promise_path}.ticks_existed", "ticks_existed is not a non-negative integer")
            continue
        wrapper = promise.get("promised_stack")
        if not isinstance(wrapper, nbt.TAG_Compound):
            fail(blockers, f"{promise_path}.promised_stack", "promised_stack is not a compound")
            continue
        unknown = sorted(set(wrapper.keys()) - BIG_STACK_KEYS)
        if unknown:
            fail(blockers, f"{promise_path}.promised_stack", "BigItemStack has unknown fields", fields=unknown)
        count = wrapper.get("count")
        if not integer(count) or as_int(count) < 0:
            fail(blockers, f"{promise_path}.promised_stack.count", "BigItemStack count is not a non-negative integer")
            continue
        stack = wrapper.get("item_stack")
        before_blockers = len(context["blockers"])
        convert_item_stack(stack, f"{promise_path}.promised_stack.item_stack", context)
        if len(context["blockers"]) != before_blockers:
            continue
        semantic.append({
            "ticks_existed": as_int(ticks),
            "count": as_int(count),
            "item_stack": repr(comparable_tag(stack)),
        })
    return semantic


def source_link(link, path, blockers):
    if not isinstance(link, nbt.TAG_Compound):
        fail(blockers, path, "link is not a compound")
        return None, None
    unknown = sorted(set(link.keys()) - {"pos", "dimension"})
    if unknown:
        fail(blockers, path, "source link has unknown fields", fields=unknown)
    pos = vector_value(link.get("pos"))
    dimension = resource_location(link.get("dimension"))
    if pos is None:
        fail(blockers, f"{path}.pos", "source link pos is not a 3-element IntArray")
    if dimension is None:
        fail(blockers, f"{path}.dimension", "source link dimension is not a namespaced string")
    if pos is None or dimension is None:
        return None, None
    target_pos = nbt.TAG_Compound()
    target_pos["X"] = nbt.TAG_Int(pos[0])
    target_pos["Y"] = nbt.TAG_Int(pos[1])
    target_pos["Z"] = nbt.TAG_Int(pos[2])
    target = nbt.TAG_Compound()
    target["Pos"] = target_pos
    if dimension != OVERWORLD:
        target["Dim"] = nbt.TAG_String(dimension)
    return target, (dimension, pos)


def target_link(link, path, blockers):
    if not isinstance(link, nbt.TAG_Compound):
        fail(blockers, path, "link is not a compound")
        return None
    unknown = sorted(set(link.keys()) - {"Pos", "Dim"})
    if unknown:
        fail(blockers, path, "target link has unknown fields", fields=unknown)
    pos_tag = link.get("Pos")
    if not isinstance(pos_tag, nbt.TAG_Compound):
        fail(blockers, f"{path}.Pos", "target link Pos is not a compound")
        return None
    unknown_pos = sorted(set(pos_tag.keys()) - {"X", "Y", "Z"})
    if unknown_pos:
        fail(blockers, f"{path}.Pos", "target link Pos has unknown fields", fields=unknown_pos)
    if any(not integer(pos_tag.get(axis)) for axis in ("X", "Y", "Z")):
        fail(blockers, f"{path}.Pos", "target link Pos is missing integer coordinates")
        return None
    dimension = OVERWORLD
    if "Dim" in link:
        dimension = resource_location(link["Dim"])
        if dimension is None:
            fail(blockers, f"{path}.Dim", "target link Dim is not a namespaced string")
            return None
        if dimension == OVERWORLD:
            fail(blockers, f"{path}.Dim", "target overworld link must omit Dim")
    return (dimension, tuple(as_int(pos_tag[axis]) for axis in ("X", "Y", "Z")))


def validate_network(network, path, blockers, context, source_format):
    if not isinstance(network, nbt.TAG_Compound):
        fail(blockers, path, "network is not a compound")
        return None, None
    unknown = sorted(set(network.keys()) - NETWORK_KEYS)
    if unknown:
        fail(blockers, path, "network has unknown fields", fields=unknown)
    network_id = uuid_value(network.get("Id"))
    if network_id is None:
        fail(blockers, f"{path}.Id", "network Id is not a four-int UUID")
    owner = None
    if "Owner" in network:
        owner = uuid_value(network["Owner"])
        if owner is None:
            fail(blockers, f"{path}.Owner", "network Owner is not a four-int UUID")
    locked = network.get("Locked")
    if not isinstance(locked, nbt.TAG_Byte) or as_int(locked) not in (0, 1):
        fail(blockers, f"{path}.Locked", "network Locked is not a byte boolean")
    promises = validate_promises(network.get("Promises"), f"{path}.Promises", blockers, context)
    links = network.get("Links")
    semantic_links = []
    target_links = []
    if not isinstance(links, nbt.TAG_List):
        fail(blockers, f"{path}.Links", "network Links is not a list")
    else:
        for index, link in enumerate(links):
            link_path = f"{path}.Links[{index}]"
            if source_format:
                converted, semantic = source_link(link, link_path, blockers)
                if converted is not None:
                    target_links.append(converted)
                if semantic is not None:
                    semantic_links.append(semantic)
            else:
                semantic = target_link(link, link_path, blockers)
                if semantic is not None:
                    semantic_links.append(semantic)
        if len(set(semantic_links)) != len(semantic_links):
            fail(blockers, f"{path}.Links", "network contains duplicate links")
    semantic = {
        "id": network_id,
        "owner": owner,
        "locked": as_int(locked) if isinstance(locked, nbt.TAG_Byte) else None,
        "links": sorted(semantic_links),
        "promises": promises,
    }
    if not source_format:
        return network, semantic
    target = nbt.TAG_Compound()
    for key in ("Id", "Promises", "Owner", "Locked"):
        if key in network:
            target[key] = clone_tag(network[key])
    target["Links"] = list_tag(target_links, nbt.TAG_Compound)
    return target, semantic


def convert_logistics_root(root, source_game_dir, target_game_dir=None):
    working = clone_file(root)
    blockers = []
    unknown_root = sorted(set(working.keys()) - {"DataVersion", "data"})
    if unknown_root:
        fail(blockers, "", "SavedData root has unknown fields", fields=unknown_root)
    version = working.get("DataVersion")
    if not integer(version) or as_int(version) < 0:
        fail(blockers, "DataVersion", "DataVersion is not a non-negative integer")
        source_version = None
    else:
        source_version = as_int(version)
    data = working.get("data")
    source_format = isinstance(data, nbt.TAG_List)
    if source_format:
        networks = data
    elif isinstance(data, nbt.TAG_Compound) and set(data.keys()) == {"LogisticsNetworks"}:
        networks = data["LogisticsNetworks"]
    else:
        fail(blockers, "data", "unknown create_logistics data shape")
        networks = None
    if networks is not None and not isinstance(networks, nbt.TAG_List):
        fail(blockers, "data.LogisticsNetworks", "network collection is not a list")
        networks = None

    context = item_context(
        source_game_dir,
        target_game_dir,
        {"saved_data": "create_logistics.dat"},
    )
    target_networks = []
    semantic_networks = []
    ids = []
    if networks is not None:
        for index, network in enumerate(networks):
            target, semantic = validate_network(
                network,
                f"data{'[' if source_format else '.LogisticsNetworks['}{index}]",
                blockers,
                context,
                source_format,
            )
            if target is not None:
                target_networks.append(target)
            if semantic is not None:
                semantic_networks.append(semantic)
                if semantic["id"] is not None:
                    ids.append(semantic["id"])
    if len(set(ids)) != len(ids):
        fail(blockers, "data", "duplicate logistics network UUID")
    blockers.extend(context["blockers"])
    if blockers:
        return None, {
            "status": "BLOCKED",
            "source_format": "1.21.11" if source_format else "1.21.1-or-unknown",
            "source_data_version": source_version,
            "blockers": blockers,
        }

    if source_format:
        target_data = nbt.TAG_Compound()
        target_data["LogisticsNetworks"] = list_tag(target_networks, nbt.TAG_Compound)
        working["data"] = target_data
    working["DataVersion"] = nbt.TAG_Int(TARGET_DATA_VERSION)
    semantic_networks.sort(key=lambda network: network["id"])
    semantic_digest = hashlib.sha256(
        json.dumps(semantic_networks, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    changed = comparable_tag(root) != comparable_tag(working)
    return working, {
        "status": "CONVERTED" if changed else "ALREADY_1_21_1",
        "source_format": "1.21.11" if source_format else "1.21.1",
        "source_data_version": source_version,
        "target_data_version": TARGET_DATA_VERSION,
        "networks": len(semantic_networks),
        "links": sum(len(network["links"]) for network in semantic_networks),
        "promises": sum(len(network["promises"]) for network in semantic_networks),
        "item_stacks_scanned": context["scanned"],
        "item_stacks_changed": len(context["changed_stacks"]),
        "semantic_sha256": semantic_digest,
        "source_nbt_sha256": tag_digest(root),
        "target_nbt_sha256": tag_digest(working),
        "item_changes": {
            "text_components": context["text_components"],
            "clipboard_hovers": context["clipboard_hovers"],
            "axolotl_variants": context["axolotl_variants"],
            "tooltip_displays": context["tooltip_displays"],
        },
        "blockers": [],
    }


def atomic_write(root, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".migration.tmp")
    root.write_file(filename=str(temporary))
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description="Fail-closed Create SavedData downgrade converter")
    parser.add_argument("source", type=Path, help="source SavedData file")
    parser.add_argument("--kind", choices=("logistics", "tracks"), default="logistics", help="SavedData schema to convert")
    parser.add_argument("--output", type=Path, help="target file; omitted means read-only dry-run")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--source-game-dir", type=Path)
    parser.add_argument("--target-game-dir", type=Path)
    args = parser.parse_args()

    source_game_dir = args.source_game_dir or args.source.resolve().parents[2]
    root = nbt.NBTFile(filename=str(args.source))
    if args.kind == "tracks":
        converted, report = convert_tracks_root(root, source_game_dir, args.target_game_dir)
    else:
        converted, report = convert_logistics_root(root, source_game_dir, args.target_game_dir)
    report.update({
        "source": str(args.source.resolve()),
        "output": str(args.output.resolve()) if args.output else None,
        "writes": 0,
    })
    if converted is not None and args.output:
        if args.source.resolve() == args.output.resolve():
            raise SystemExit("refusing in-place SavedData conversion; use a staging output path")
        atomic_write(converted, args.output)
        report["writes"] = 1
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    raise SystemExit(0 if converted is not None else 2)


if __name__ == "__main__":
    main()
