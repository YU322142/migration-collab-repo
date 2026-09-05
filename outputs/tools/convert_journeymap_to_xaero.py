#!/usr/bin/env python3
"""Deterministically stage a JourneyMap export for Xaero Minimap/World Map.

This tool never launches Minecraft and never writes into a live client.  It emits a
staging tree, exhaustive manifests, and static validation results.  Large output is
intended for <AUDIT_ROOT>.

The map writer intentionally targets Xaero World Map's legacy region format v4.
Xaero World Map 1.41.2 still reads this format and upgrades it on load.  Every
non-empty raster pixel is represented by an explicit legacy block-state id.  This
avoids the v4 custom-colour field, which Xaero 1.41.2 reads but discards.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import sys
import threading
import zlib
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Iterator, Sequence

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - exercised by CLI preflight
    raise SystemExit(
        "This converter needs NumPy and Pillow. Use the Codex workspace Python "
        "runtime reported by codex_app__load_workspace_dependencies."
    ) from exc


SCHEMA = "journeymap-to-xaero/1"
REGION_SCHEMA = "xaero-world-map-v4-explicit-state/1"
BUILD_DATE = "2026-08-13"
WAYPOINT_ESCAPE = "§§"
XAERO_MULTIWORLD_ID = "mw$default"
DEFAULT_PRODUCTION_SERVER_PORT = 25566
REGION_NAME_RE = re.compile(r"^(-?\d+),(-?\d+)\.png$")

DIMENSIONS: tuple[dict[str, Any], ...] = (
    {
        "source": "overworld",
        "resource": "minecraft:overworld",
        "world_map_dir": "null",
        "minimap_dir": "dim%0",
        "legacy_suffix": "null",
        "light": 0,
    },
    {
        "source": "the_nether",
        "resource": "minecraft:the_nether",
        "world_map_dir": "DIM-1",
        "minimap_dir": "dim%-1",
        "legacy_suffix": "DIM-1",
        "light": 15,
    },
    {
        "source": "the_end",
        "resource": "minecraft:the_end",
        "world_map_dir": "DIM1",
        "minimap_dir": "dim%1",
        "legacy_suffix": "DIM1",
        "light": 0,
    },
)
DIMENSION_BY_RESOURCE = {d["resource"]: d for d in DIMENSIONS}
DIMENSION_BY_SOURCE = {d["source"]: d for d in DIMENSIONS}

XAERO_WAYPOINT_COLORS: tuple[int, ...] = (
    0x000000,
    0x0000AA,
    0x00AA00,
    0x00AAAA,
    0xAA0000,
    0xAA00AA,
    0xFFAA00,
    0xAAAAAA,
    0x555555,
    0x5555FF,
    0x55FF55,
    0x55FFFF,
    0xFF5555,
    0xFF55FF,
    0xFFFF55,
    0xFFFFFF,
)

# Manual corrections from the audited upstream JMtoXaero converter.
LEAF_STATES = {
    161,
    49170,
    24594,
    32929,
    8210,
    18,
    57362,
    53409,
    4257,
    16402,
    20641,
    49313,
    32786,
    37025,
    16545,
    40978,
}

REGION_RECORD_DTYPE = np.dtype(
    [("parameters", ">u4"), ("state", ">u4"), ("biome", "u1")], align=False
)
COLOR_LUT_DTYPE = np.dtype(
    [
        ("source_rgb", ">u4"),
        ("source_pixel_count", ">u8"),
        ("legacy_state_id", ">u4"),
        ("target_rgb", ">u4"),
        ("distance_squared", ">u4"),
    ],
    align=False,
)


class ConversionError(RuntimeError):
    """A fail-closed conversion or validation error."""


def sha256_file(path: Path, block_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        # ASCII-safe JSON avoids Windows PowerShell 5.1's default ANSI decode trap.
        # JSON parsers restore the original Unicode strings from \uXXXX escapes.
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    )


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class NBTReader:
    """Minimal uncompressed Java NBT reader sufficient for the audited inputs."""

    def __init__(self, stream: BinaryIO):
        self.stream = stream

    def read_exact(self, length: int) -> bytes:
        data = self.stream.read(length)
        if len(data) != length:
            raise ConversionError(f"truncated NBT: expected {length} bytes")
        return data

    def unpack(self, fmt: str) -> Any:
        size = struct.calcsize(fmt)
        values = struct.unpack(fmt, self.read_exact(size))
        return values[0] if len(values) == 1 else values

    def string(self) -> str:
        length = self.unpack(">H")
        return self.read_exact(length).decode("utf-8")

    def named_tag(self) -> tuple[str, Any]:
        tag_type = self.unpack(">B")
        if tag_type == 0:
            raise ConversionError("root NBT tag cannot be TAG_End")
        name = self.string()
        return name, self.payload(tag_type)

    def payload(self, tag_type: int) -> Any:
        if tag_type == 1:
            return self.unpack(">b")
        if tag_type == 2:
            return self.unpack(">h")
        if tag_type == 3:
            return self.unpack(">i")
        if tag_type == 4:
            return self.unpack(">q")
        if tag_type == 5:
            return self.unpack(">f")
        if tag_type == 6:
            return self.unpack(">d")
        if tag_type == 7:
            length = self.unpack(">i")
            if length < 0:
                raise ConversionError("negative TAG_Byte_Array length")
            return self.read_exact(length)
        if tag_type == 8:
            return self.string()
        if tag_type == 9:
            child_type = self.unpack(">B")
            length = self.unpack(">i")
            if length < 0:
                raise ConversionError("negative TAG_List length")
            return [self.payload(child_type) for _ in range(length)]
        if tag_type == 10:
            result: dict[str, Any] = {}
            while True:
                child_type = self.unpack(">B")
                if child_type == 0:
                    return result
                child_name = self.string()
                if child_name in result:
                    raise ConversionError(f"duplicate NBT compound key: {child_name}")
                result[child_name] = self.payload(child_type)
        if tag_type == 11:
            length = self.unpack(">i")
            if length < 0:
                raise ConversionError("negative TAG_Int_Array length")
            return list(struct.unpack(f">{length}i", self.read_exact(length * 4)))
        if tag_type == 12:
            length = self.unpack(">i")
            if length < 0:
                raise ConversionError("negative TAG_Long_Array length")
            return list(struct.unpack(f">{length}q", self.read_exact(length * 8)))
        raise ConversionError(f"unsupported NBT tag type: {tag_type}")


def read_nbt_bytes(data: bytes) -> dict[str, Any]:
    stream = io.BytesIO(data)
    _, root = NBTReader(stream).named_tag()
    if not isinstance(root, dict):
        raise ConversionError("NBT root is not a compound")
    if stream.read(1):
        raise ConversionError("trailing bytes after NBT root")
    return root


@dataclasses.dataclass(frozen=True)
class VanillaStateTable:
    states: dict[int, str]
    record_count: int
    duplicate_overwrites: tuple[dict[str, Any], ...]

    def audit(self) -> dict[str, Any]:
        duplicate_keys = sorted(
            {int(row["composite_state_id"]) for row in self.duplicate_overwrites}
        )
        conflicting = [row for row in self.duplicate_overwrites if not row["same_nbt"]]
        return {
            "record_count": self.record_count,
            "unique_composite_state_ids": len(self.states),
            "duplicate_record_count": len(self.duplicate_overwrites),
            "duplicate_composite_state_id_count": len(duplicate_keys),
            "conflicting_duplicate_record_count": len(conflicting),
            "duplicate_composite_state_ids": duplicate_keys,
            "overwrites_in_file_order": list(self.duplicate_overwrites),
            "composite_key_layout": {
                "block_id": "key & 0xFFF",
                "legacy_state_index": "(key >> 12) & 0xFFFFF",
            },
            "duplicate_semantics": (
                "last record wins for the same (block_id, legacy_state_index), "
                "matching Xaero World Map 1.41.2 OldFormatSupport.loadStates/putState"
            ),
        }


def load_vanilla_state_table(path: Path) -> VanillaStateTable:
    states: dict[int, str] = {}
    state_tags: dict[int, dict[str, Any]] = {}
    duplicate_overwrites: list[dict[str, Any]] = []
    record_count = 0
    with path.open("rb") as stream:
        reader = NBTReader(stream)
        while True:
            raw_state = stream.read(4)
            if not raw_state:
                break
            if len(raw_state) != 4:
                raise ConversionError("truncated vanilla_states.dat state id")
            state_id = struct.unpack(">i", raw_state)[0]
            _, tag = reader.named_tag()
            if not isinstance(tag, dict) or "Name" not in tag:
                raise ConversionError(f"state {state_id} has no Name compound member")
            if state_id in states:
                prior_tag = state_tags[state_id]
                duplicate_overwrites.append(
                    {
                        "record_index": record_count,
                        "composite_state_id": state_id,
                        "block_id": state_id & 0xFFF,
                        "legacy_state_index": (state_id >> 12) & 0xFFFFF,
                        "prior_name": states[state_id],
                        "replacement_name": str(tag["Name"]),
                        "same_nbt": prior_tag == tag,
                    }
                )
            # Xaero's nested HashMap.put calls overwrite in file order.
            states[state_id] = str(tag["Name"])
            state_tags[state_id] = tag
            record_count += 1
    if not states or states.get(0) != "minecraft:air":
        raise ConversionError("vanilla state table does not start with air state 0")
    return VanillaStateTable(
        states=states,
        record_count=record_count,
        duplicate_overwrites=tuple(duplicate_overwrites),
    )


def load_vanilla_states(path: Path) -> dict[int, str]:
    """Compatibility wrapper returning Xaero's final last-record-wins state map."""
    return load_vanilla_state_table(path).states


@dataclasses.dataclass(frozen=True)
class Palette:
    rgb: np.ndarray
    state_ids: np.ndarray
    state_names: tuple[str, ...]
    source_rows: int


def load_block_palette(mapping_path: Path, vanilla_states: dict[int, str]) -> Palette:
    color_to_state: dict[int, int] = {}
    source_rows = 0
    for line_number, raw_line in enumerate(
        mapping_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            state_id, signed_color = (int(piece) for piece in line.split(",", 1))
        except Exception as exc:
            raise ConversionError(
                f"invalid mapping row {line_number}: {raw_line!r}"
            ) from exc
        source_rows += 1
        if state_id not in vanilla_states:
            raise ConversionError(
                f"mapping state {state_id} is absent from vanilla_states.dat"
            )
        if signed_color == -1 or state_id == 122:
            continue
        if state_id == 2:
            signed_color = -10914762
        if state_id in LEAF_STATES:
            signed_color = -14399980
        rgb = signed_color & 0xFFFFFF
        prior = color_to_state.get(rgb)
        if prior is None or state_id < prior:
            color_to_state[rgb] = state_id
    if not color_to_state:
        raise ConversionError("block-state colour mapping is empty")
    # Lower state id wins exact distance ties, independent of dict/hash order.
    entries = sorted(
        ((state_id, rgb) for rgb, state_id in color_to_state.items()),
        key=lambda pair: (pair[0], pair[1]),
    )
    state_ids = np.asarray([state for state, _ in entries], dtype=np.uint32)
    rgb = np.asarray([color for _, color in entries], dtype=np.uint32)
    names = tuple(vanilla_states[int(state)] for state in state_ids)
    return Palette(rgb=rgb, state_ids=state_ids, state_names=names, source_rows=source_rows)


def _nearest_palette_batch(
    source_colors: np.ndarray, palette_rgb: np.ndarray, palette_states: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    colors = source_colors.astype(np.int32, copy=False)
    palette = palette_rgb.astype(np.int32, copy=False)
    cr = ((colors >> 16) & 255)[:, None]
    cg = ((colors >> 8) & 255)[:, None]
    cb = (colors & 255)[:, None]
    pr = ((palette >> 16) & 255)[None, :]
    pg = ((palette >> 8) & 255)[None, :]
    pb = (palette & 255)[None, :]
    red_mean = (cr + pr) >> 1
    dr = cr - pr
    dg = cg - pg
    db = cb - pb
    distance = (
        (((512 + red_mean) * dr * dr) >> 8)
        + 4 * dg * dg
        + (((767 - red_mean) * db * db) >> 8)
    )
    choice = np.argmin(distance, axis=1)
    rows = np.arange(len(colors))
    return (
        palette_states[choice].astype(np.uint32),
        palette_rgb[choice].astype(np.uint32),
        distance[rows, choice].astype(np.uint32),
    )


def map_colors_to_palette(
    source_colors: np.ndarray,
    palette: Palette,
    workers: int,
    batch_size: int = 4096,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    batches = [source_colors[i : i + batch_size] for i in range(0, len(source_colors), batch_size)]
    state_parts: list[np.ndarray] = []
    color_parts: list[np.ndarray] = []
    distance_parts: list[np.ndarray] = []
    palette_workers = max(1, min(workers, 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=palette_workers) as executor:
        results = executor.map(
            lambda batch: _nearest_palette_batch(batch, palette.rgb, palette.state_ids),
            batches,
        )
        for states, colors, distances in results:
            state_parts.append(states)
            color_parts.append(colors)
            distance_parts.append(distances)
    if not state_parts:
        return (
            np.empty(0, dtype=np.uint32),
            np.empty(0, dtype=np.uint32),
            np.empty(0, dtype=np.uint32),
        )
    return (
        np.concatenate(state_parts),
        np.concatenate(color_parts),
        np.concatenate(distance_parts),
    )


def xaero_root_id(server: str) -> str:
    """Mirror Xaero's current (root format 5) multiplayer folder naming."""
    value = server.strip()
    if value.count(":") > 1:
        divider = value.rfind("]:") + 1
    else:
        divider = value.find(":")
    if divider > 0:
        value = value[:divider]
    value = value.rstrip(".")
    value = value.replace("[", "").replace("]", "")
    value = value.replace(":", ".").strip()
    value = re.sub(r"[. ]+$", lambda match: "," * len(match.group(0)), value)
    if not value:
        value = "Empty Address"
    return "Multiplayer_" + value


def verify_server_identity(server: str, port: int) -> None:
    """Fail closed on values that cannot map back to the requested server exactly."""
    if not server or server != server.strip():
        raise ConversionError("server host must be a non-empty trimmed value")
    if any(character in server for character in "/\\\r\n\t"):
        raise ConversionError("server host contains an unsafe path/control character")
    if ":" in server:
        raise ConversionError("pass the server port with --port, not inside --server")
    if not 1 <= port <= 65535:
        raise ConversionError("--port must be between 1 and 65535")


def verify_port_separation(audit_port: int, production_port: int) -> None:
    """Keep disposable conversion/test traffic distinct from production."""
    if not 1 <= production_port <= 65535:
        raise ConversionError("--production-port must be between 1 and 65535")
    if audit_port == production_port:
        raise ConversionError(
            "disposable conversion port must differ from the production server port"
        )


def safe_waypoint_field(value: str) -> str:
    value = value.replace("\r", " ").replace("\n", " ")
    if WAYPOINT_ESCAPE in value:
        raise ConversionError(
            f"waypoint field already contains Xaero escape token {WAYPOINT_ESCAPE!r}"
        )
    return value.replace(":", WAYPOINT_ESCAPE)


def safe_set_names(groups: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    mapping: dict[str, str] = {}
    changes: list[dict[str, str]] = []
    used: set[str] = set()
    for group_id, group in groups.items():
        source_name = str(group.get("name") or group_id).replace("\r", " ").replace("\n", " ")
        target = source_name.replace(":", "∶").replace(WAYPOINT_ESCAPE, "§ §")
        if not target:
            target = str(group_id)
        base = target
        suffix = 2
        while target in used:
            target = f"{base} ({suffix})"
            suffix += 1
        used.add(target)
        mapping[str(group_id)] = target
        if target != source_name:
            changes.append(
                {"group_id": str(group_id), "source": source_name, "target": target}
            )
    return mapping, changes


def waypoint_initials(name: str) -> str:
    characters = [character for character in name if not character.isspace()]
    return "".join(characters[:2]) or "?"


def nearest_waypoint_color(signed_argb: int) -> tuple[int, int, float]:
    source = signed_argb & 0xFFFFFF
    sr, sg, sb = (source >> 16) & 255, (source >> 8) & 255, source & 255
    scored: list[tuple[int, int]] = []
    for index, target in enumerate(XAERO_WAYPOINT_COLORS):
        tr, tg, tb = (target >> 16) & 255, (target >> 8) & 255, target & 255
        scored.append(((sr - tr) ** 2 + (sg - tg) ** 2 + (sb - tb) ** 2, index))
    distance_squared, index = min(scored)
    return index, XAERO_WAYPOINT_COLORS[index], math.sqrt(distance_squared)


def parse_waypoints(path: Path) -> dict[str, Any]:
    root = read_nbt_bytes(path.read_bytes())
    groups = root.get("groups")
    waypoints = root.get("waypoints")
    if not isinstance(groups, dict) or not isinstance(waypoints, dict):
        raise ConversionError("WaypointData.dat lacks groups/waypoints compounds")
    return {"groups": groups, "waypoints": waypoints}


def convert_waypoints(
    waypoint_path: Path,
    output_root: Path,
    world_root: str,
) -> dict[str, Any]:
    parsed = parse_waypoints(waypoint_path)
    groups: dict[str, Any] = parsed["groups"]
    waypoints: dict[str, Any] = parsed["waypoints"]
    group_names, set_name_changes = safe_set_names(groups)

    default_group = "journeymap_default" if "journeymap_default" in groups else next(iter(groups))
    ordered_group_ids = [default_group] + [key for key in groups if key != default_group]
    ordered_sets = [group_names[key] for key in ordered_group_ids]
    current_set = group_names[default_group]

    records_by_dimension: dict[str, list[dict[str, Any]]] = {
        d["resource"]: [] for d in DIMENSIONS
    }
    audit_records: list[dict[str, Any]] = []
    for source_index, (compound_key, waypoint) in enumerate(waypoints.items()):
        if not isinstance(waypoint, dict):
            raise ConversionError(f"waypoint {compound_key} is not a compound")
        guid = str(waypoint.get("guid", compound_key))
        pos = waypoint.get("pos")
        dimensions = waypoint.get("dimensions")
        if not isinstance(pos, dict) or not isinstance(dimensions, list) or not dimensions:
            raise ConversionError(f"waypoint {guid} has invalid pos/dimensions")
        position_dimension = str(pos.get("dimension", ""))
        dimension_names = [str(value) for value in dimensions]
        if position_dimension not in dimension_names:
            raise ConversionError(
                f"waypoint {guid} pos.dimension is not included in dimensions"
            )
        unsupported = [value for value in dimension_names if value not in DIMENSION_BY_RESOURCE]
        if unsupported:
            raise ConversionError(f"waypoint {guid} uses unsupported dimensions: {unsupported}")
        group_id = str(waypoint.get("groupId", default_group))
        if group_id not in group_names:
            raise ConversionError(f"waypoint {guid} references unknown group {group_id}")
        name = str(waypoint.get("name", guid))
        initials = waypoint_initials(name)
        color_signed = int(waypoint.get("color", -1))
        color_index, target_color, color_distance = nearest_waypoint_color(color_signed)
        settings = waypoint.get("settings") if isinstance(waypoint.get("settings"), dict) else {}
        enabled = bool(int(settings.get("enable", 1)))
        waypoint_type = 2 if group_id == "journeymap_death" else 0  # OLD_DEATH or NORMAL
        record_base = {
            "source_index": source_index,
            "compound_key": str(compound_key),
            "guid": guid,
            "name": name,
            "initials": initials,
            "x": int(pos["x"]),
            "y": int(pos["y"]),
            "z": int(pos["z"]),
            "position_dimension": position_dimension,
            "dimensions": dimension_names,
            "group_id": group_id,
            "xaero_set": group_names[group_id],
            "source_color_argb_signed": color_signed,
            "source_rgb": f"#{color_signed & 0xFFFFFF:06X}",
            "xaero_color_index": color_index,
            "xaero_color_rgb": f"#{target_color:06X}",
            "xaero_color_euclidean_distance": round(color_distance, 6),
            "enabled": enabled,
            "xaero_disabled": not enabled,
            "xaero_type": waypoint_type,
            "xaero_type_name": "OLD_DEATH" if waypoint_type == 2 else "NORMAL",
            "source_settings": settings,
            "source_icon": waypoint.get("icon"),
            "source_origin": waypoint.get("origin"),
            "source_mod_id": waypoint.get("modId"),
        }
        audit_records.append(record_base)
        for dimension_name in dimension_names:
            record = dict(record_base)
            record["output_dimension"] = dimension_name
            records_by_dimension[dimension_name].append(record)

    native_paths: dict[str, str] = {}
    legacy_lines: list[str] = []
    for dimension in DIMENSIONS:
        resource = dimension["resource"]
        legacy_world_id = f"{world_root}_{dimension['legacy_suffix']}"
        set_fields = ":".join(ordered_sets)
        legacy_lines.append(f"world:{legacy_world_id}:{current_set}:{set_fields}")
        native_lines = [
            "sets:" + ":".join([current_set] + [value for value in ordered_sets if value != current_set]),
            "#",
            "#waypoint:name:initials:x:y:z:color:disabled:type:set:rotate_on_tp:tp_yaw:visibility_type:destination",
            "#",
        ]
        for record in records_by_dimension[resource]:
            name = safe_waypoint_field(record["name"])
            initials = safe_waypoint_field(record["initials"])
            disabled = str(record["xaero_disabled"]).lower()
            common = (
                f"{name}:{initials}:{record['x']}:{record['y']}:{record['z']}:"
                f"{record['xaero_color_index']}:{disabled}:{record['xaero_type']}:"
                f"{record['xaero_set']}:false:0"
            )
            native_lines.append(f"waypoint:{common}:LOCAL:false")
            legacy_lines.append(f"waypoint:{legacy_world_id}:{common}")
        native_path = (
            output_root
            / "staging"
            / "xaero"
            / "minimap"
            / world_root
            / dimension["minimap_dir"]
            / f"{XAERO_MULTIWORLD_ID}.txt"
        )
        atomic_write_text(native_path, "\n".join(native_lines) + "\n")
        native_paths[resource] = relative_posix(native_path, output_root)

    minimap_config = (
        "//waypoints config options\n"
        "usingMultiworldDetection:false\n"
        "ignoreServerLevelId:true\n"
        f"defaultMultiworldId:{XAERO_MULTIWORLD_ID}\n"
        "teleportationEnabled:true\n"
        "usingDefaultTeleportCommand:true\n"
        "sortType:NONE\n"
        "sortReversed:false\n\n"
        "//other config options\n"
        "ignoreHeightmaps:false\n"
    )
    atomic_write_text(
        output_root / "staging" / "xaero" / "minimap" / world_root / "config.txt",
        minimap_config,
    )
    legacy_path = (
        output_root
        / "alternatives"
        / "legacy-waypoint-import"
        / "config"
        / "xaerowaypoints.txt"
    )
    atomic_write_text(legacy_path, "\n".join(legacy_lines) + "\n")

    audit = {
        "schema": SCHEMA,
        "source_unique_waypoints": len(waypoints),
        "output_waypoint_records": sum(len(value) for value in records_by_dimension.values()),
        "source_group_count": len(groups),
        "current_set": current_set,
        "group_to_set": group_names,
        "set_name_changes": set_name_changes,
        "dimension_counts": {
            key: len(value) for key, value in records_by_dimension.items()
        },
        "native_files": native_paths,
        "legacy_import_file": relative_posix(legacy_path, output_root),
        "legacy_import_is_alternative_not_primary_staging": True,
        "native_world_node": XAERO_MULTIWORLD_ID,
        "records": audit_records,
        "preserved_group_compounds": groups,
    }
    audit_path = output_root / "waypoints" / "waypoints-audit.json"
    atomic_write_json(audit_path, audit)
    return audit


def discover_day_tiles(source_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for dimension in DIMENSIONS:
        day_root = source_root / dimension["source"] / "day"
        if not day_root.is_dir():
            raise ConversionError(f"missing JourneyMap day layer: {day_root}")
        for path in sorted(day_root.glob("*.png"), key=lambda item: item.name):
            match = REGION_NAME_RE.fullmatch(path.name)
            if not match:
                raise ConversionError(f"unexpected day tile name: {path}")
            rx, rz = (int(match.group(1)), int(match.group(2)))
            key = (dimension["source"], rx, rz)
            if key in seen:
                raise ConversionError(f"duplicate day tile: {key}")
            seen.add(key)
            records.append(
                {
                    "path": path,
                    "dimension": dimension["source"],
                    "resource": dimension["resource"],
                    "rx": rx,
                    "rz": rz,
                }
            )
    records.sort(key=lambda row: (row["dimension"], row["rx"], row["rz"]))
    return records


def scan_day_tile(record: dict[str, Any], source_root: Path) -> dict[str, Any]:
    path: Path = record["path"]
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as image:
        if image.size != (512, 512):
            raise ConversionError(f"day tile is not 512x512: {path} => {image.size}")
        rgba = np.asarray(image.convert("RGBA"))
    alpha = rgba[:, :, 3]
    nontransparent = alpha != 0
    rgb = (
        (rgba[:, :, 0].astype(np.uint32) << 16)
        | (rgba[:, :, 1].astype(np.uint32) << 8)
        | rgba[:, :, 2].astype(np.uint32)
    )
    colors, counts = np.unique(rgb[nontransparent], return_counts=True)
    result = dict(record)
    result.update(
        {
            "relative_path": relative_posix(path, source_root),
            "source_bytes": len(raw),
            "source_sha256": sha256_bytes(raw),
            "pixel_count": int(rgba.shape[0] * rgba.shape[1]),
            "transparent_pixels": int(np.count_nonzero(alpha == 0)),
            "partial_alpha_pixels": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
            "opaque_pixels": int(np.count_nonzero(alpha == 255)),
            "_colors": colors.astype(np.uint32),
            "_counts": counts.astype(np.uint64),
        }
    )
    return result


def build_color_universe(
    scans: Sequence[dict[str, Any]], palette: Palette, workers: int
) -> dict[str, Any]:
    color_arrays = [record["_colors"] for record in scans if len(record["_colors"])]
    if not color_arrays:
        raise ConversionError("all JourneyMap day tiles are fully transparent")
    source_colors = np.unique(np.concatenate(color_arrays)).astype(np.uint32)
    counts = np.zeros(len(source_colors), dtype=np.uint64)
    for record in scans:
        indices = np.searchsorted(source_colors, record["_colors"])
        counts[indices] += record["_counts"]
    states, target_colors, distance_squared = map_colors_to_palette(
        source_colors, palette, workers
    )
    total = int(counts.sum())
    distances = np.sqrt(distance_squared.astype(np.float64))
    mean = float(np.dot(distances, counts.astype(np.float64)) / total)
    rmse = math.sqrt(
        float(np.dot(distance_squared.astype(np.float64), counts.astype(np.float64)) / total)
    )
    order = np.argsort(distances, kind="stable")
    cumulative = np.cumsum(counts[order], dtype=np.uint64)
    p95_index = int(np.searchsorted(cumulative, math.ceil(total * 0.95), side="left"))
    metrics = {
        "source_unique_rgb_colors": int(len(source_colors)),
        "nontransparent_pixel_count": total,
        "exact_palette_pixel_count": int(counts[distance_squared == 0].sum()),
        "exact_palette_pixel_ratio": float(counts[distance_squared == 0].sum() / total),
        "weighted_mean_color_distance": mean,
        "weighted_rmse_color_distance": rmse,
        "weighted_p95_color_distance": float(distances[order[p95_index]]),
        "maximum_color_distance": float(distances.max(initial=0.0)),
    }
    return {
        "source_colors": source_colors,
        "counts": counts,
        "states": states,
        "target_colors": target_colors,
        "distance_squared": distance_squared,
        "metrics": metrics,
    }


def write_color_lut(path: Path, universe: dict[str, Any]) -> None:
    records = np.empty(len(universe["source_colors"]), dtype=COLOR_LUT_DTYPE)
    records["source_rgb"] = universe["source_colors"]
    records["source_pixel_count"] = universe["counts"]
    records["legacy_state_id"] = universe["states"]
    records["target_rgb"] = universe["target_colors"]
    records["distance_squared"] = universe["distance_squared"]
    raw = b"JMXCOLOR1" + struct.pack(">I", len(records)) + records.tobytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as sink:
        with gzip.GzipFile(filename="", mode="wb", fileobj=sink, mtime=0, compresslevel=9) as gz:
            gz.write(raw)
        sink.flush()
        os.fsync(sink.fileno())
    os.replace(temporary, path)


def region_comment(source_sha256: str, conversion_fingerprint: str) -> bytes:
    return (
        f"{REGION_SCHEMA};source-sha256={source_sha256};"
        f"conversion-sha256={conversion_fingerprint}"
    ).encode("ascii")


def build_region_payload(
    rgba: np.ndarray,
    source_colors: np.ndarray,
    mapped_states: np.ndarray,
    light: int,
) -> tuple[bytes, dict[str, int]]:
    if rgba.shape != (512, 512, 4):
        raise ConversionError(f"unexpected RGBA shape: {rgba.shape}")
    alpha = rgba[:, :, 3]
    rgb = (
        (rgba[:, :, 0].astype(np.uint32) << 16)
        | (rgba[:, :, 1].astype(np.uint32) << 8)
        | rgba[:, :, 2].astype(np.uint32)
    )
    nontransparent_flat = alpha.ravel() != 0
    flat_rgb = rgb.ravel()
    nontransparent_rgb = flat_rgb[nontransparent_flat]
    indices = np.searchsorted(source_colors, nontransparent_rgb)
    if np.any(indices >= len(source_colors)):
        raise ConversionError("source color is absent from global color universe")
    if np.any(source_colors[indices] != nontransparent_rgb):
        raise ConversionError("source color lookup mismatch")
    flat_states = np.zeros(flat_rgb.shape, dtype=np.uint32)
    flat_states[nontransparent_flat] = mapped_states[indices]
    states = flat_states.reshape((512, 512))

    output = io.BytesIO()
    output.write(b"\xff")
    output.write(struct.pack(">i", 4))
    parameters = 1 | (light << 8) | (64 << 12) | 1048576
    record_buffer = np.empty(256, dtype=REGION_RECORD_DTYPE)
    record_buffer["parameters"] = parameters
    record_buffer["biome"] = 1  # plains, matching the audited colour palette
    empty_map_tiles = 0
    nonempty_map_tiles = 0
    explicit_air_pixels = 0
    for chunk_x in range(8):
        for chunk_z in range(8):
            output.write(bytes(((chunk_x << 4) | chunk_z,)))
            for tile_x in range(4):
                for tile_z in range(4):
                    x0 = chunk_x * 64 + tile_x * 16
                    z0 = chunk_z * 64 + tile_z * 16
                    tile_alpha = alpha[z0 : z0 + 16, x0 : x0 + 16]
                    if not np.any(tile_alpha):
                        output.write(struct.pack(">i", -1))
                        empty_map_tiles += 1
                        continue
                    tile_states = states[z0 : z0 + 16, x0 : x0 + 16].T.reshape(256)
                    record_buffer["state"] = tile_states
                    output.write(record_buffer.tobytes())
                    output.write(b"\x00")  # legacy world interpretation version
                    nonempty_map_tiles += 1
                    explicit_air_pixels += int(np.count_nonzero(tile_states == 0))
    return output.getvalue(), {
        "empty_map_tiles": empty_map_tiles,
        "nonempty_map_tiles": nonempty_map_tiles,
        "explicit_air_pixels_in_nonempty_tiles": explicit_air_pixels,
    }


def write_region_zip(
    path: Path,
    payload: bytes,
    source_sha256: str,
    conversion_fingerprint: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    info = zipfile.ZipInfo("region.xaero", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    with zipfile.ZipFile(temporary, "w") as archive:
        archive.comment = region_comment(source_sha256, conversion_fingerprint)
        archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    os.replace(temporary, path)


def validate_region_zip(
    path: Path,
    known_state_ids: set[int],
    expected_source_sha256: str | None = None,
    expected_conversion_fingerprint: str | None = None,
) -> dict[str, Any]:
    if (expected_source_sha256 is None) != (
        expected_conversion_fingerprint is None
    ):
        raise ConversionError(
            "region validation requires both source and conversion fingerprints"
        )
    with zipfile.ZipFile(path, "r") as archive:
        if archive.namelist() != ["region.xaero"]:
            raise ConversionError(f"{path}: zip must contain only region.xaero")
        if (
            expected_source_sha256 is not None
            and expected_conversion_fingerprint is not None
            and archive.comment
            != region_comment(expected_source_sha256, expected_conversion_fingerprint)
        ):
            raise ConversionError(f"{path}: source hash/schema zip comment mismatch")
        payload = archive.read("region.xaero")  # also validates ZIP CRC
    if len(payload) < 5 or payload[0] != 0xFF or struct.unpack_from(">i", payload, 1)[0] != 4:
        raise ConversionError(f"{path}: invalid Xaero v4 header")
    position = 5
    seen_chunks: set[int] = set()
    empty_map_tiles = 0
    nonempty_map_tiles = 0
    explicit_air_pixels = 0
    used_states: set[int] = set()
    for expected_x in range(8):
        for expected_z in range(8):
            if position >= len(payload):
                raise ConversionError(f"{path}: truncated before chunk coordinate")
            coordinate = payload[position]
            position += 1
            expected = (expected_x << 4) | expected_z
            if coordinate != expected or coordinate in seen_chunks:
                raise ConversionError(
                    f"{path}: unexpected/duplicate chunk coordinate {coordinate:#x}, expected {expected:#x}"
                )
            seen_chunks.add(coordinate)
            for _ in range(16):
                if position + 4 > len(payload):
                    raise ConversionError(f"{path}: truncated map tile")
                first = struct.unpack_from(">i", payload, position)[0]
                if first == -1:
                    position += 4
                    empty_map_tiles += 1
                    continue
                record_bytes = 256 * REGION_RECORD_DTYPE.itemsize
                if position + record_bytes + 1 > len(payload):
                    raise ConversionError(f"{path}: truncated non-empty map tile")
                records = np.frombuffer(
                    payload, dtype=REGION_RECORD_DTYPE, count=256, offset=position
                )
                params = records["parameters"].astype(np.uint32)
                if np.any((params & 1) == 0):
                    raise ConversionError(f"{path}: implicit grass records are not in converter schema")
                if np.any((params & 2) != 0) or np.any(((params >> 2) & 3) != 0):
                    raise ConversionError(f"{path}: unexpected overlays/custom colours")
                if np.any((params & 1048576) == 0):
                    raise ConversionError(f"{path}: biome marker missing")
                if np.any(records["biome"] != 1):
                    raise ConversionError(f"{path}: unexpected legacy biome id")
                unique_states = {int(value) for value in np.unique(records["state"])}
                unknown = unique_states - known_state_ids
                if unknown:
                    raise ConversionError(f"{path}: unknown legacy state ids {sorted(unknown)[:10]}")
                used_states.update(unique_states)
                explicit_air_pixels += int(np.count_nonzero(records["state"] == 0))
                position += record_bytes
                if payload[position] != 0:
                    raise ConversionError(f"{path}: unexpected interpretation version")
                position += 1
                nonempty_map_tiles += 1
    if position != len(payload):
        raise ConversionError(f"{path}: {len(payload) - position} trailing region bytes")
    if len(seen_chunks) != 64 or empty_map_tiles + nonempty_map_tiles != 1024:
        raise ConversionError(f"{path}: incomplete region structure")
    return {
        "payload_bytes": len(payload),
        "zip_bytes": path.stat().st_size,
        "empty_map_tiles": empty_map_tiles,
        "nonempty_map_tiles": nonempty_map_tiles,
        "explicit_air_pixels_in_nonempty_tiles": explicit_air_pixels,
        "unique_legacy_state_count": len(used_states),
    }


def output_region_path(output_root: Path, world_root: str, record: dict[str, Any]) -> Path:
    dimension = DIMENSION_BY_SOURCE[record["dimension"]]
    return (
        output_root
        / "staging"
        / "xaero"
        / "world-map"
        / world_root
        / dimension["world_map_dir"]
        / XAERO_MULTIWORLD_ID
        / f"{record['rx']}_{record['rz']}.zip"
    )


def convert_region(
    scan: dict[str, Any],
    source_colors: np.ndarray,
    mapped_states: np.ndarray,
    output_root: Path,
    world_root: str,
    known_state_ids: set[int],
    conversion_fingerprint: str,
    resume: bool,
) -> dict[str, Any]:
    output_path = output_region_path(output_root, world_root, scan)
    resumed = False
    if resume and output_path.is_file():
        try:
            validation = validate_region_zip(
                output_path,
                known_state_ids,
                scan["source_sha256"],
                conversion_fingerprint,
            )
            resumed = True
        except Exception:
            resumed = False
    if not resumed:
        with Image.open(scan["path"]) as image:
            rgba = np.asarray(image.convert("RGBA"))
        dimension = DIMENSION_BY_SOURCE[scan["dimension"]]
        payload, writer_stats = build_region_payload(
            rgba, source_colors, mapped_states, int(dimension["light"])
        )
        write_region_zip(
            output_path,
            payload,
            scan["source_sha256"],
            conversion_fingerprint,
        )
        validation = validate_region_zip(
            output_path,
            known_state_ids,
            scan["source_sha256"],
            conversion_fingerprint,
        )
        if writer_stats != {
            key: validation[key]
            for key in (
                "empty_map_tiles",
                "nonempty_map_tiles",
                "explicit_air_pixels_in_nonempty_tiles",
            )
        }:
            raise ConversionError(f"writer/validator statistic mismatch for {output_path}")
    return {
        "dimension": scan["dimension"],
        "resource": scan["resource"],
        "rx": scan["rx"],
        "rz": scan["rz"],
        "source_relative_path": scan["relative_path"],
        "source_bytes": scan["source_bytes"],
        "source_sha256": scan["source_sha256"],
        "source_transparent_pixels": scan["transparent_pixels"],
        "source_partial_alpha_pixels": scan["partial_alpha_pixels"],
        "output_relative_path": relative_posix(output_path, output_root),
        "output_sha256": sha256_file(output_path),
        **validation,
    }


def write_world_map_configs(output_root: Path, world_root: str) -> None:
    root = output_root / "staging" / "xaero" / "world-map" / world_root
    server_config = (
        "multiworldType:0\n"
        "ignoreServerLevelId:true\n"
        "ignoreHeightmaps:false\n"
        "playerTeleportCommandFormat:/tp @s {name}\n"
        "normalTeleportCommandFormat:/tp @s {x} {y} {z}\n"
        "dimensionTeleportCommandFormat:/execute as @s in {d} run tp {x} {y} {z}\n"
        "useDefaultMapTeleport:true\n"
        "useDefaultPlayerTeleport:true\n"
    )
    atomic_write_text(root / "server_config.txt", server_config)
    for dimension in DIMENSIONS:
        text = (
            f"confirmedMultiworld:{XAERO_MULTIWORLD_ID}\n"
            f"MWName:{XAERO_MULTIWORLD_ID}:JourneyMap Import\n"
            "caveModeType:1\n"
            f"dimensionTypeId:{dimension['resource']}\n"
        )
        atomic_write_text(root / dimension["world_map_dir"] / "dimension_config.txt", text)


def verify_source_zip_matches_extracted(
    source_zip: Path,
    source_root: Path,
    workers: int,
) -> dict[str, Any]:
    """Prove that the read-only extracted tree is byte-identical to the source ZIP.

    ZIP CRC32 and uncompressed sizes let us exhaustively bind all files without
    materializing a second extraction.  The inventory phase separately records
    SHA-256 for every extracted file.
    """
    with zipfile.ZipFile(source_zip, "r") as archive:
        infos = sorted(
            (info for info in archive.infolist() if not info.is_dir()),
            key=lambda info: info.filename,
        )
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            duplicates = [name for name, count in Counter(names).items() if count > 1]
            raise ConversionError(f"source ZIP contains duplicate file names: {duplicates[:10]}")
        for info in infos:
            path = Path(info.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ConversionError(f"unsafe source ZIP path: {info.filename}")

    extracted_paths = sorted(
        (path for path in source_root.rglob("*") if path.is_file()),
        key=lambda path: relative_posix(path, source_root),
    )
    extracted_names = [relative_posix(path, source_root) for path in extracted_paths]
    if names != extracted_names:
        missing = sorted(set(names) - set(extracted_names))
        extra = sorted(set(extracted_names) - set(names))
        raise ConversionError(
            "source ZIP and extracted tree file sets differ; "
            f"missing={missing[:10]}, extra={extra[:10]}"
        )

    info_by_name = {info.filename: info for info in infos}

    def check(path: Path) -> tuple[int, int]:
        relative = relative_posix(path, source_root)
        info = info_by_name[relative]
        size = 0
        crc = 0
        with path.open("rb") as stream:
            while chunk := stream.read(4 * 1024 * 1024):
                size += len(chunk)
                crc = zlib.crc32(chunk, crc)
        crc &= 0xFFFFFFFF
        if size != info.file_size or crc != info.CRC:
            raise ConversionError(
                f"extracted file differs from ZIP: {relative}; "
                f"size {size}/{info.file_size}, CRC32 {crc:08x}/{info.CRC:08x}"
            )
        return size, crc

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        checked = list(executor.map(check, extracted_paths))
    return {
        "zip_file_entries": len(infos),
        "extracted_file_entries": len(extracted_paths),
        "uncompressed_bytes": sum(size for size, _ in checked),
        "all_sizes_and_crc32_match": True,
    }


def verify_xaero_jars(
    minimap_jar: Path,
    world_map_jar: Path,
    vanilla_states: Path,
) -> dict[str, Any]:
    """Fail closed if the audited target jars or embedded state table drift."""
    minimap_required = {
        "xaero/hud/minimap/waypoint/io/WaypointIO.class",
        "xaero/hud/minimap/world/container/config/io/RootConfigIO.class",
        "xaero/hud/minimap/world/io/MinimapWorldManagerIO.class",
        "xaero/hud/minimap/world/state/MinimapWorldStateUpdater.class",
    }
    world_map_required = {
        "assets/xaeroworldmap/vanilla_states.dat",
        "xaero/map/file/MapSaveLoad.class",
        "xaero/map/file/OldFormatSupport.class",
        "xaero/map/world/MapDimension.class",
        "xaero/map/world/MapWorld.class",
    }
    minimap_markers = {
        "xaero/hud/minimap/waypoint/io/WaypointIO.class": (
            b"sets",
            b"waypoint",
            b"LOCAL",
            WAYPOINT_ESCAPE.encode("utf-8"),
        ),
        "xaero/hud/minimap/world/container/config/io/RootConfigIO.class": (
            b"usingMultiworldDetection",
            b"ignoreServerLevelId",
            b"defaultMultiworldId",
        ),
        "xaero/hud/minimap/world/io/MinimapWorldManagerIO.class": (
            b"waypoints.txt",
            b".txt",
        ),
    }
    world_map_markers = {
        "xaero/map/file/MapSaveLoad.class": (b"region.xaero", b".zip", b".xaero"),
        "xaero/map/file/OldFormatSupport.class": (
            b"vanilla_states.dat",
            b"readInt",
            b"putState",
            b"getStateForId",
        ),
        "xaero/map/world/MapDimension.class": (
            XAERO_MULTIWORLD_ID.encode("ascii"),
            b"confirmedMultiworld",
            b"MWName",
            b"dimension_config.txt",
        ),
        "xaero/map/world/MapWorld.class": (b"multiworldType", b"ignoreServerLevelId"),
    }
    with zipfile.ZipFile(minimap_jar, "r") as archive:
        minimap_names = set(archive.namelist())
        manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        missing_minimap = sorted(minimap_required - minimap_names)
        if missing_minimap:
            raise ConversionError(f"Xaero Minimap jar lacks audited classes: {missing_minimap}")
        if "Implementation-Version: 26.1.0" not in manifest:
            raise ConversionError("Xaero Minimap jar is not version 26.1.0")
        for name, markers in minimap_markers.items():
            data = archive.read(name)
            missing = [marker.hex() for marker in markers if marker not in data]
            if missing:
                raise ConversionError(
                    f"Xaero Minimap audited format markers missing in {name}: {missing}"
                )
        minimap_class_hashes = {
            name: sha256_bytes(archive.read(name)) for name in sorted(minimap_required)
        }
    with zipfile.ZipFile(world_map_jar, "r") as archive:
        world_map_names = set(archive.namelist())
        manifest = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        missing_world_map = sorted(world_map_required - world_map_names)
        if missing_world_map:
            raise ConversionError(
                f"Xaero World Map jar lacks audited classes/resources: {missing_world_map}"
            )
        if "Implementation-Version: 1.41.2" not in manifest:
            raise ConversionError("Xaero World Map jar is not version 1.41.2")
        for name, markers in world_map_markers.items():
            data = archive.read(name)
            missing = [marker.hex() for marker in markers if marker not in data]
            if missing:
                raise ConversionError(
                    f"Xaero World Map audited format markers missing in {name}: {missing}"
                )
        embedded_states = archive.read("assets/xaeroworldmap/vanilla_states.dat")
        if sha256_bytes(embedded_states) != sha256_file(vanilla_states):
            raise ConversionError(
                "provided vanilla_states.dat does not match Xaero World Map jar"
            )
        world_map_class_hashes = {
            name: sha256_bytes(archive.read(name))
            for name in sorted(world_map_required)
            if name.endswith(".class")
        }
    return {
        "minimap_version": "26.1.0",
        "world_map_version": "1.41.2",
        "minimap_audited_class_sha256": minimap_class_hashes,
        "world_map_audited_class_sha256": world_map_class_hashes,
        "embedded_vanilla_states_sha256": sha256_bytes(embedded_states),
        "embedded_vanilla_states_matches_reference": True,
        "waypoint_escape_token_utf8_hex": WAYPOINT_ESCAPE.encode("utf-8").hex(),
        "world_map_default_multiworld_id": XAERO_MULTIWORLD_ID,
    }


def inventory_source_tree(source_root: Path, workers: int) -> list[dict[str, Any]]:
    paths = sorted((path for path in source_root.rglob("*") if path.is_file()), key=lambda p: p.as_posix())

    def inspect(path: Path) -> dict[str, Any]:
        relative = relative_posix(path, source_root)
        pieces = relative.split("/")
        layer = pieces[1] if len(pieces) >= 3 and pieces[0] in DIMENSION_BY_SOURCE else None
        return {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "extension": path.suffix.lower(),
            "dimension": pieces[0] if pieces and pieces[0] in DIMENSION_BY_SOURCE else None,
            "layer": layer,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(inspect, paths))


def summarize_reference_layers(inventory: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"files": 0, "bytes": 0})
    )
    for record in inventory:
        dimension = record.get("dimension")
        if not dimension:
            continue
        layer = record.get("layer") or "(dimension-root)"
        grouped[dimension][layer]["files"] += 1
        grouped[dimension][layer]["bytes"] += int(record["bytes"])
    result: dict[str, Any] = {}
    for dimension in sorted(grouped):
        result[dimension] = {
            layer: grouped[dimension][layer] for layer in sorted(grouped[dimension])
        }
    return result


def verify_pack(pack_zip: Path) -> dict[str, Any]:
    with zipfile.ZipFile(pack_zip, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        names = set(archive.namelist())
    files = manifest.get("files", [])
    xaero_minimap = [row for row in files if row.get("projectID") == 263420]
    xaero_world_map = [row for row in files if row.get("projectID") == 317780]
    journey_map = [row for row in files if row.get("projectID") == 32274]
    if xaero_minimap != [
        {"projectID": 263420, "fileID": 8231212, "required": True, "isLocked": False}
    ]:
        raise ConversionError(f"unexpected Xaero Minimap manifest row: {xaero_minimap}")
    if xaero_world_map != [
        {"projectID": 317780, "fileID": 8298694, "required": True, "isLocked": False}
    ]:
        raise ConversionError(f"unexpected Xaero World Map manifest row: {xaero_world_map}")
    return {
        "path": str(pack_zip),
        "bytes": pack_zip.stat().st_size,
        "sha256": sha256_file(pack_zip),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "minecraft": manifest.get("minecraft"),
        "xaero_minimap_manifest_rows": xaero_minimap,
        "xaero_world_map_manifest_rows": xaero_world_map,
        "journeymap_manifest_rows": journey_map,
        "journeymap_mod_selected": bool(journey_map),
        "stale_journeymap_config_override_present": "overrides/config/journeymap-server.toml" in names,
    }


def build_conversion_identity(args: argparse.Namespace) -> dict[str, Any]:
    bound_inputs = {
        "source_zip": {
            "path": str(args.source_zip),
            "sha256": sha256_file(args.source_zip),
        },
        "pack_zip": {
            "path": str(args.pack_zip),
            "sha256": sha256_file(args.pack_zip),
        },
        "mapping": {
            "path": str(args.mapping),
            "sha256": sha256_file(args.mapping),
        },
        "vanilla_states": {
            "path": str(args.vanilla_states),
            "sha256": sha256_file(args.vanilla_states),
        },
        "xaero_minimap_jar": {
            "path": str(args.xaero_minimap_jar),
            "sha256": sha256_file(args.xaero_minimap_jar),
        },
        "xaero_world_map_jar": {
            "path": str(args.xaero_world_map_jar),
            "sha256": sha256_file(args.xaero_world_map_jar),
        },
        "converter": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
    }
    identity = {
        "schema": SCHEMA,
        "server": args.server,
        "disposable_audit_port": args.port,
        "production_port": args.production_port,
        "world_root": xaero_root_id(f"{args.server}:{args.port}"),
        "multiworld_id": XAERO_MULTIWORLD_ID,
        "bound_inputs": bound_inputs,
    }
    fingerprint_payload = {
        "schema": identity["schema"],
        "server": identity["server"],
        "disposable_audit_port": identity["disposable_audit_port"],
        "production_port": identity["production_port"],
        "world_root": identity["world_root"],
        "multiworld_id": identity["multiworld_id"],
        "bound_input_sha256": {
            name: value["sha256"] for name, value in bound_inputs.items()
        },
    }
    canonical = json.dumps(
        fingerprint_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    identity["fingerprint_sha256"] = sha256_bytes(canonical.encode("ascii"))
    return identity


def prepare_output_root(
    output_root: Path,
    resume: bool,
    conversion_identity: dict[str, Any],
) -> None:
    sentinel = output_root / ".journeymap-xaero-conversion-root.json"
    if output_root.exists() and not sentinel.is_file():
        if any(output_root.iterdir()):
            raise ConversionError(
                f"refusing to use non-empty output without converter sentinel: {output_root}"
            )
    output_root.mkdir(parents=True, exist_ok=True)
    if sentinel.is_file():
        prior = json.loads(sentinel.read_text(encoding="utf-8"))
        if not resume:
            raise ConversionError("output already exists; pass --resume to continue/verify")
        prior_fingerprint = prior.get("conversion_identity", {}).get("fingerprint_sha256")
        if prior_fingerprint is not None and prior_fingerprint != conversion_identity[
            "fingerprint_sha256"
        ]:
            raise ConversionError(
                "output sentinel belongs to different input content/configuration"
            )
        if prior_fingerprint is None:
            legacy_source = prior.get("source_zip")
            expected_source = conversion_identity["bound_inputs"]["source_zip"]["path"]
            if prior.get("schema") != SCHEMA or legacy_source != expected_source:
                raise ConversionError("legacy output sentinel belongs to a different source")
    atomic_write_json(
        sentinel,
        {
            "schema": SCHEMA,
            "build_date": BUILD_DATE,
            "conversion_identity": conversion_identity,
        },
    )


def write_progress(output_root: Path, phase: str, **fields: Any) -> None:
    payload = {"schema": SCHEMA, "updated_utc": now_utc(), "phase": phase, **fields}
    atomic_write_json(output_root / "progress.json", payload)


def render_report_markdown(report: dict[str, Any]) -> str:
    tiles = report["tiles"]
    waypoints = report["waypoints"]
    metrics = report["visual_quantization"]
    lines = [
        "# JourneyMap → Xaero 静态转换报告",
        "",
        f"- 状态：`{report['status']}`",
        f"- 构建日期：`{report['build_date']}`",
        f"- 一次性审计身份：`{report['server']['address']}:{report['server']['port']}`（仅用于确定缓存主机名）",
        f"- 生产服务器：`{report['server']['address']}:{report['server']['production_port']}`（未修改）",
        f"- Xaero 缓存根：`{report['server']['xaero_root_id']}`（Xaero 当前格式会从目录名剥离端口）",
        f"- Minecraft 启动：`{str(report['execution']['minecraft_launched']).lower()}`",
        "",
        "## 结果",
        "",
        f"- JourneyMap 原始 waypoint：{waypoints['source_unique_waypoints']} 个；Xaero 输出记录：{waypoints['output_waypoint_records']} 个。",
        f"- JourneyMap day 区域图：{tiles['source_day_tiles']} 张；Xaero v4 region ZIP：{tiles['output_region_zips']} 个。",
        f"- 静态解析通过：{tiles['validated_region_zips']} / {tiles['output_region_zips']}。",
        f"- 非透明像素：{metrics['nontransparent_pixel_count']:,}；精确命中调色板：{metrics['exact_palette_pixel_ratio']:.4%}。",
        f"- 加权平均颜色距离：{metrics['weighted_mean_color_distance']:.3f}；RMSE：{metrics['weighted_rmse_color_distance']:.3f}；P95：{metrics['weighted_p95_color_distance']:.3f}。",
        "",
        "## 明确保留但未原生表达的内容",
        "",
    ]
    lines.extend(f"- {entry}" for entry in report["known_losses_and_preservation"])
    lines.extend(
        [
            "",
            "## 安装边界",
            "",
            "`staging/` 是可复制到客户端 `.minecraft/` 的主路径；`alternatives/legacy-waypoint-import/` 只是一次性旧格式导入备选，不能与原生 waypoint 文件同时安装。",
            "",
            f"`{report['server']['port']}` 是一次性审计/测试端口；生产服务器端口保持 `{report['server']['production_port']}`。Xaero 目录名会剥离端口，因此本输出只绑定主机 `{report['server']['address']}`，不写入生产端口配置。",
            "",
            "本任务没有修改 Prism 实例、现有 release、服务器端口或任何 Minecraft 配置。转换输出也不包含 JourneyMap 模组。",
            "",
        ]
    )
    return "\n".join(lines)


def write_sha256s(output_root: Path) -> list[dict[str, Any]]:
    excluded = {"SHA256SUMS.txt", "progress.json"}
    paths = sorted(
        (
            path
            for path in output_root.rglob("*")
            if path.is_file() and path.name not in excluded and not path.name.endswith(".tmp")
        ),
        key=lambda path: relative_posix(path, output_root),
    )
    records = [
        {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "path": relative_posix(path, output_root),
        }
        for path in paths
    ]
    text = "".join(f"{row['sha256']} *{row['path']}\n" for row in records)
    atomic_write_text(output_root / "SHA256SUMS.txt", text)
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--source-extracted", type=Path, required=True)
    parser.add_argument("--pack-zip", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--vanilla-states", type=Path, required=True)
    parser.add_argument("--xaero-minimap-jar", type=Path, required=True)
    parser.add_argument("--xaero-world-map-jar", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--server", default="play.example.invalid")
    parser.add_argument("--port", type=int, default=12341)
    parser.add_argument(
        "--production-port",
        type=int,
        default=DEFAULT_PRODUCTION_SERVER_PORT,
        help=(
            "production server port for the handoff boundary only; never written "
            "to the staged Xaero cache (default: 25566)"
        ),
    )
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.workers <= 22:
        raise ConversionError("--workers must be between 1 and 22")
    verify_server_identity(args.server, args.port)
    verify_port_separation(args.port, args.production_port)
    required_files = (
        args.source_zip,
        args.pack_zip,
        args.mapping,
        args.vanilla_states,
        args.xaero_minimap_jar,
        args.xaero_world_map_jar,
    )
    for path in required_files:
        if not path.is_file():
            raise ConversionError(f"required file does not exist: {path}")
    if not args.source_extracted.is_dir():
        raise ConversionError(f"source extraction does not exist: {args.source_extracted}")
    conversion_identity = build_conversion_identity(args)
    prepare_output_root(args.output_root, args.resume, conversion_identity)
    write_progress(args.output_root, "preflight", workers=args.workers)
    server_with_port = f"{args.server}:{args.port}"
    world_root = xaero_root_id(server_with_port)

    print("[1/7] Auditing source, pack, and Xaero legacy state table...", flush=True)
    source_zip_hash_future: concurrent.futures.Future[str]
    audit_workers = max(1, (args.workers - 2) // 2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        source_zip_hash_future = executor.submit(sha256_file, args.source_zip)
        pack_future = executor.submit(verify_pack, args.pack_zip)
        inventory_future = executor.submit(
            inventory_source_tree, args.source_extracted, audit_workers
        )
        source_binding_future = executor.submit(
            verify_source_zip_matches_extracted,
            args.source_zip,
            args.source_extracted,
            audit_workers,
        )
        vanilla_state_table = load_vanilla_state_table(args.vanilla_states)
        vanilla_states = vanilla_state_table.states
        pack_audit = pack_future.result()
        inventory = inventory_future.result()
        source_binding = source_binding_future.result()
        source_zip_hash = source_zip_hash_future.result()
    xaero_jar_audit = verify_xaero_jars(
        args.xaero_minimap_jar,
        args.xaero_world_map_jar,
        args.vanilla_states,
    )
    palette = load_block_palette(args.mapping, vanilla_states)
    vanilla_state_audit = vanilla_state_table.audit()
    reference_summary = summarize_reference_layers(inventory)
    atomic_write_json(args.output_root / "manifests" / "source-inventory.json", inventory)
    atomic_write_json(
        args.output_root / "manifests" / "reference-layers.json", reference_summary
    )
    atomic_write_json(
        args.output_root / "manifests" / "vanilla-state-table-audit.json",
        vanilla_state_audit,
    )
    write_progress(
        args.output_root,
        "source-audited",
        source_files=len(inventory),
        legacy_states=len(vanilla_states),
        palette_colors=len(palette.rgb),
    )

    print("[2/7] Scanning 512x512 day tiles and building exact RGB universe...", flush=True)
    day_tiles = discover_day_tiles(args.source_extracted)
    scans: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(scan_day_tile, record, args.source_extracted): record
            for record in day_tiles
        }
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            scans.append(future.result())
            if completed % 20 == 0 or completed == len(futures):
                print(f"  scanned {completed}/{len(futures)}", flush=True)
    scans.sort(key=lambda row: (row["dimension"], row["rx"], row["rz"]))
    universe = build_color_universe(scans, palette, args.workers)
    lut_path = args.output_root / "manifests" / "color-lut.bin.gz"
    write_color_lut(lut_path, universe)
    write_progress(
        args.output_root,
        "color-lut-built",
        tiles=len(scans),
        source_unique_colors=universe["metrics"]["source_unique_rgb_colors"],
    )

    print("[3/7] Converting WaypointData.dat to native and legacy Xaero formats...", flush=True)
    waypoint_source = args.source_extracted / "waypoints" / "WaypointData.dat"
    if not waypoint_source.is_file():
        raise ConversionError(f"missing waypoint source: {waypoint_source}")
    reference_root = args.output_root / "reference"
    reference_root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(waypoint_source, reference_root / "WaypointData.dat")
    shutil.copyfile(args.mapping, reference_root / "blockstateidtocolor.txt")
    shutil.copyfile(args.vanilla_states, reference_root / "vanilla_states.dat")
    waypoint_audit = convert_waypoints(waypoint_source, args.output_root, world_root)
    write_progress(
        args.output_root,
        "waypoints-converted",
        source_waypoints=waypoint_audit["source_unique_waypoints"],
        output_records=waypoint_audit["output_waypoint_records"],
    )

    print(
        f"[4/7] Converting {len(scans)} day tiles with {args.workers} workers (resumable)...",
        flush=True,
    )
    write_world_map_configs(args.output_root, world_root)
    known_state_ids = set(vanilla_states)
    tile_results: list[dict[str, Any]] = []
    progress_lock = threading.Lock()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                convert_region,
                scan,
                universe["source_colors"],
                universe["states"],
                args.output_root,
                world_root,
                known_state_ids,
                conversion_identity["fingerprint_sha256"],
                args.resume,
            ): scan
            for scan in scans
        }
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            tile_results.append(result)
            if completed % 5 == 0 or completed == len(futures):
                with progress_lock:
                    print(
                        f"  converted+validated {completed}/{len(futures)} "
                        f"({result['dimension']} {result['rx']},{result['rz']})",
                        flush=True,
                    )
                    write_progress(
                        args.output_root,
                        "tiles-converting",
                        completed=completed,
                        total=len(futures),
                        workers=args.workers,
                    )
    tile_results.sort(key=lambda row: (row["dimension"], row["rx"], row["rz"]))
    atomic_write_json(args.output_root / "manifests" / "native-tiles.json", tile_results)

    print("[5/7] Running whole-output static validation...", flush=True)
    if len(tile_results) != len(scans):
        raise ConversionError("output region count differs from source day tile count")
    source_keys = {
        (row["dimension"], row["rx"], row["rz"]) for row in scans
    }
    output_keys = {
        (row["dimension"], row["rx"], row["rz"]) for row in tile_results
    }
    if source_keys != output_keys:
        raise ConversionError("source/output tile key sets differ")
    for resource, path_text in waypoint_audit["native_files"].items():
        path = args.output_root / path_text
        lines = path.read_text(encoding="utf-8").splitlines()
        expected = waypoint_audit["dimension_counts"][resource]
        actual = sum(line.startswith("waypoint:") for line in lines)
        if actual != expected:
            raise ConversionError(
                f"native waypoint file {path} has {actual} records, expected {expected}"
            )
        for line in lines:
            if line.startswith("waypoint:") and len(line.split(":")) != 14:
                raise ConversionError(f"native waypoint field count mismatch: {line}")
    legacy_lines = (
        args.output_root
        / waypoint_audit["legacy_import_file"]
    ).read_text(encoding="utf-8").splitlines()
    if sum(line.startswith("waypoint:") for line in legacy_lines) != waypoint_audit[
        "output_waypoint_records"
    ]:
        raise ConversionError("legacy waypoint import record count mismatch")

    dimension_tile_counts = Counter(row["dimension"] for row in tile_results)
    source_png_count = sum(1 for row in inventory if row["extension"] == ".png")
    source_day_paths = {row["relative_path"] for row in scans}
    non_day_png_count = sum(
        1
        for row in inventory
        if row["extension"] == ".png" and row["path"] not in source_day_paths
    )
    tile_summary = {
        "source_day_tiles": len(scans),
        "output_region_zips": len(tile_results),
        "validated_region_zips": len(tile_results),
        "dimension_counts": dict(sorted(dimension_tile_counts.items())),
        "source_all_png_files": source_png_count,
        "reference_png_files_not_imported": non_day_png_count,
        "output_zip_bytes": sum(row["zip_bytes"] for row in tile_results),
        "output_payload_bytes": sum(row["payload_bytes"] for row in tile_results),
        "nonempty_map_tiles": sum(row["nonempty_map_tiles"] for row in tile_results),
        "empty_map_tiles": sum(row["empty_map_tiles"] for row in tile_results),
        "explicit_air_pixels_in_nonempty_tiles": sum(
            row["explicit_air_pixels_in_nonempty_tiles"] for row in tile_results
        ),
        "partial_alpha_pixels": sum(row["source_partial_alpha_pixels"] for row in tile_results),
    }

    print("[6/7] Writing deterministic reports and handoff instructions...", flush=True)
    report = {
        "schema": SCHEMA,
        "status": "STATIC_VALIDATION_PASSED",
        "build_date": BUILD_DATE,
        "source": {
            "zip_path": str(args.source_zip),
            "zip_bytes": args.source_zip.stat().st_size,
            "zip_sha256": source_zip_hash,
            "extracted_reference_root": str(args.source_extracted),
            "extracted_file_count": len(inventory),
            "extracted_bytes": sum(row["bytes"] for row in inventory),
            "source_was_modified": False,
            "zip_to_extracted_binding": source_binding,
        },
        "server": {
            "address": args.server,
            "port": args.port,
            "port_role": "disposable_conversion_audit_only",
            "production_port": args.production_port,
            "production_port_role": "production_server_unchanged",
            "port_was_modified": False,
            "production_port_was_modified": False,
            "production_config_touched": False,
            "xaero_root_id": world_root,
            "xaero_root_id_excludes_port_by_mod_format": True,
        },
        "target": {
            "minecraft": "1.21.1",
            "loader": "NeoForge 21.1.233",
            "xaero_minimap": "26.1.0",
            "xaero_world_map": "1.41.2",
            "pack": pack_audit,
            "xaero_minimap_jar": {
                "path": str(args.xaero_minimap_jar),
                "bytes": args.xaero_minimap_jar.stat().st_size,
                "sha256": sha256_file(args.xaero_minimap_jar),
            },
            "xaero_world_map_jar": {
                "path": str(args.xaero_world_map_jar),
                "bytes": args.xaero_world_map_jar.stat().st_size,
                "sha256": sha256_file(args.xaero_world_map_jar),
            },
            "xaero_jar_static_format_audit": xaero_jar_audit,
        },
        "format_evidence": {
            "waypoint_name_escape_token": WAYPOINT_ESCAPE,
            "legacy_waypoint_world_ids": {
                d["resource"]: f"{world_root}_{d['legacy_suffix']}" for d in DIMENSIONS
            },
            "native_minimap_dimension_dirs": {
                d["resource"]: d["minimap_dir"] for d in DIMENSIONS
            },
            "world_map_dimension_dirs": {
                d["resource"]: d["world_map_dir"] for d in DIMENSIONS
            },
            "world_map_region_format": "v4, one region.xaero entry per deterministic ZIP",
            "world_map_multiworld_id": XAERO_MULTIWORLD_ID,
            "world_map_slot_is_explicitly_confirmed": True,
            "server_level_id_is_ignored_for_import_visibility": True,
            "world_map_pixel_strategy": "explicit legacy block state for every pixel in non-empty 16x16 tiles",
            "legacy_state_table_records": vanilla_state_audit["record_count"],
            "legacy_state_table_entries": len(vanilla_states),
            "legacy_state_table_duplicate_records": vanilla_state_audit[
                "duplicate_record_count"
            ],
            "legacy_state_table_conflicting_duplicate_records": vanilla_state_audit[
                "conflicting_duplicate_record_count"
            ],
            "legacy_state_table_duplicate_semantics": vanilla_state_audit[
                "duplicate_semantics"
            ],
            "palette_source_rows": palette.source_rows,
            "palette_unique_colors": len(palette.rgb),
            "mapping_sha256": sha256_file(args.mapping),
            "vanilla_states_sha256": sha256_file(args.vanilla_states),
        },
        "execution": {
            "workers": args.workers,
            "conversion_fingerprint_sha256": conversion_identity[
                "fingerprint_sha256"
            ],
            "resume_identity_bound_inputs": conversion_identity["bound_inputs"],
            "disposable_audit_port": args.port,
            "production_server_port": args.production_port,
            "production_server_properties_modified": False,
            "production_proxy_or_firewall_modified": False,
            "minecraft_launched": False,
            "prism_instance_modified": False,
            "release_modified": False,
            "resumable_atomic_region_writes": True,
        },
        "waypoints": {
            key: waypoint_audit[key]
            for key in (
                "source_unique_waypoints",
                "output_waypoint_records",
                "source_group_count",
                "dimension_counts",
                "native_files",
                "legacy_import_file",
                "native_world_node",
            )
        },
        "tiles": tile_summary,
        "visual_quantization": universe["metrics"],
        "reference_layers": reference_summary,
        "journeymap": {
            "included_in_converter_output": False,
            "selected_in_pack_manifest": pack_audit["journeymap_mod_selected"],
            "must_be_excluded_from_final_selection": True,
            "stale_pack_config_to_remove_when_merging": (
                "overrides/config/journeymap-server.toml"
                if pack_audit["stale_journeymap_config_override_present"]
                else None
            ),
        },
        "known_losses_and_preservation": [
            "地图来自 JourneyMap day 栅格，不含原始方块身份；每个 RGB 被确定性量化到 Xaero 1.41.2 可解析的最近旧版方块状态。完整 RGB→状态 LUT 已保存在 manifests/color-lut.bin.gz。",
            "地图高度统一写为 Y=64、biome 统一写为 plains；Nether 使用满光照。源高度切片、biome、topo、night、JMD/JMM 均未伪装导入，而是由 source-inventory/reference-layers 清单和原 ZIP/解压根保留。",
            "全透明 16×16 图块保持 void；非空图块内部的透明像素显式写为 air，避免黑色填洞。部分透明像素的 alpha 无法由 Xaero v4 表达，其 RGB 仍参与量化并在统计中单列。",
            "Waypoint 坐标、名称、维度、启用状态与分组→set 被迁移；颜色缩减为 Xaero 16 色。JourneyMap GUID、原色、图标资源、opacity、group 设置等完整保存在 waypoints-audit.json。",
            "JourneyMap death 分组映射为 Xaero OLD_DEATH，保留历史死亡点语义并降低被“到达后删除当前死亡点”设置误删的风险。",
            "主 staging 使用原生 Xaero waypoint 文件；alternatives/legacy-waypoint-import 是可回退的一次性导入方式，二者不得同时安装。",
            "为保证首次连接即可命中已转换缓存，本服务器专属 Xaero 缓存配置把 World Map 和 Minimap 绑定到 mw$default，并忽略服务端 levelId。此设置不改服务端，也不是全局模组限制；若以后需要按 levelId 分隔多个同维度世界，应先迁移缓存目录，再在该服务器的 Xaero 配置中重新启用 levelId。",
            "所有不可原生表达的信息仍可从原始 ZIP、D 盘解压审计根及本输出 reference/manifests 恢复；转换未改动源文件。",
        ],
    }
    atomic_write_json(args.output_root / "conversion-report.json", report)
    atomic_write_text(args.output_root / "conversion-report.md", render_report_markdown(report))
    readme = (
        "# JourneyMap → Xaero handoff\n\n"
        "Status: `STATIC_VALIDATION_PASSED`. Minecraft was not launched.\n\n"
        "Primary install candidate: copy the contents of `staging/` into a stopped client's `.minecraft/` only after backing up that client's existing `xaero/` directory. Do not copy `alternatives/legacy-waypoint-import/` at the same time.\n\n"
        f"Cache identity was audited with disposable `{args.server}:{args.port}`. Production remains `{args.server}:{args.production_port}`. Xaero's cache directory is `{world_root}` because its current path algorithm removes the port before sanitizing the address.\n\n"
        f"Port boundary: `{args.port}` is disposable/audit-only; `{args.production_port}` is production and was not changed. No production `server.properties`, proxy routing, firewall rule, or live server was touched.\n\n"
        f"The native map and waypoint world node is `{XAERO_MULTIWORLD_ID}`. The staged per-server Xaero cache configs explicitly select it and ignore an unknown server levelId so the imported data is visible on first connection. This does not change the server or any global mod setting.\n\n"
        "`manifests/source-inventory.json` and `manifests/reference-layers.json` point to every preserved source layer. The complete source is intentionally not duplicated here; use the original ZIP or the extracted D: audit root recorded in `conversion-report.json`.\n\n"
        "JourneyMap is not part of this staging output. The Mechanomania pack manifest already selects Xaero Minimap and World Map, but its stale `overrides/config/journeymap-server.toml` should be omitted when the final client is assembled.\n"
    )
    atomic_write_text(args.output_root / "README.md", readme)

    print("[7/7] Hashing final output set...", flush=True)
    hashes = write_sha256s(args.output_root)
    write_progress(
        args.output_root,
        "complete",
        status="STATIC_VALIDATION_PASSED",
        files_hashed=len(hashes),
        regions=len(tile_results),
        waypoints=waypoint_audit["source_unique_waypoints"],
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output_root": str(args.output_root),
                "regions": len(tile_results),
                "waypoints": waypoint_audit["source_unique_waypoints"],
                "source_zip_sha256": source_zip_hash,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ConversionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(2) from exc
