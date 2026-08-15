#!/usr/bin/env python3
"""Fail-closed 1.21.11 -> 1.21.1 conversion for vanilla SavedData.

The source world is never modified. All selected inputs are validated before any
target file is replaced, and a failed multi-file commit is rolled back.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

import nbtlib


TARGET_DATA_VERSION = 3955
KINDS = ("chunks", "world_uuid", "border", "raids", "scoreboard", "maps")
MAP_SIDECAR_RELATIVE = Path(".migration-ledger/map-banner.v1.jsonl")


class ConversionError(RuntimeError):
    pass


class ConversionLockError(ConversionError):
    pass


def conversion_lock_path(target: Path) -> Path:
    return target.parent / f".{target.name}.saveddata-conversion.lock"


def _existing_lock_description(path: Path) -> str:
    try:
        raw = path.read_bytes()[:65536]
    except OSError as exc:
        return f"<unreadable: {type(exc).__name__}: {exc}>"
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"<invalid JSON: {type(exc).__name__}: {exc}>"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class TargetConversionLock:
    """Atomic, operator-recoverable lock for one target world."""

    def __init__(self, target: Path):
        self.target = target
        self.path = conversion_lock_path(target)
        self.token = uuid.uuid4().hex
        self.fd: int | None = None

    def __enter__(self) -> "TargetConversionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            self.fd = os.open(self.path, flags, 0o600)
        except FileExistsError as exc:
            description = _existing_lock_description(self.path)
            raise ConversionLockError(
                f"conversion lock already exists: {self.path}; the existing lock was "
                "left untouched. Another converter may still be active. Inspect its "
                "PID/time/target metadata, confirm that process is no longer running, "
                "then inspect all .migration.tmp/.migration.bak files under the target. "
                "Only after operator recovery is complete may the lock be manually "
                f"archived or removed and the conversion retried. metadata={description}"
            ) from exc

        metadata = {
            "pid": os.getpid(),
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "target_world": str(self.target),
            "token": self.token,
        }
        payload = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(self.fd, payload[offset:])
                if written <= 0:
                    raise OSError("short write while recording conversion lock metadata")
                offset += written
            os.fsync(self.fd)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        assert self.fd is not None
        ownership_error: ConversionError | None = None
        try:
            try:
                metadata = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                ownership_error = ConversionError(
                    f"cannot verify ownership of conversion lock {self.path}; it was "
                    "left in place for operator recovery"
                )
                ownership_error.__cause__ = exc
            else:
                if metadata.get("token") != self.token:
                    ownership_error = ConversionError(
                        f"conversion lock ownership changed at {self.path}; it was left "
                        "in place for operator recovery"
                    )
        finally:
            os.close(self.fd)
            self.fd = None

        if ownership_error is not None:
            if exc_value is not None:
                raise ConversionError(
                    f"{ownership_error}; original failure was "
                    f"{type(exc_value).__name__}: {exc_value}"
                ) from exc_value
            raise ownership_error
        try:
            self.path.unlink()
        except OSError as exc:
            raise ConversionError(
                f"conversion finished but its lock could not be released: {self.path}; "
                "confirm the converter is stopped, inspect transaction artifacts, and "
                "remove the lock manually before retrying"
            ) from exc
        return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_nbt(path: Path) -> nbtlib.File:
    if not path.is_file():
        raise ConversionError(f"required NBT file is missing: {path}")
    try:
        return nbtlib.load(path, gzipped=True)
    except Exception as exc:  # nbtlib exposes multiple parse exception types
        raise ConversionError(f"cannot parse {path}: {exc}") from exc


def ensure_file_shape(root: nbtlib.File, path: Path) -> nbtlib.Compound:
    unknown = set(root) - {"DataVersion", "data"}
    if unknown:
        raise ConversionError(f"{path.name} has unknown root keys: {sorted(unknown)}")
    data = root.get("data")
    if not isinstance(data, nbtlib.Compound):
        raise ConversionError(f"{path.name} data must be a compound")
    return data


def ensure_exact_keys(value: nbtlib.Compound, allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ConversionError(f"{label} has unknown keys: {sorted(unknown)}")


def as_int(value: object, label: str) -> int:
    if not isinstance(value, (nbtlib.Byte, nbtlib.Short, nbtlib.Int, nbtlib.Long)):
        raise ConversionError(f"{label} must be an integer tag")
    return int(value)


def as_number(value: object, label: str) -> float:
    if not isinstance(
        value,
        (nbtlib.Byte, nbtlib.Short, nbtlib.Int, nbtlib.Long, nbtlib.Float, nbtlib.Double),
    ):
        raise ConversionError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ConversionError(f"{label} must be finite")
    return result


def new_file(data: nbtlib.Compound) -> nbtlib.File:
    return nbtlib.File(
        {"DataVersion": nbtlib.Int(TARGET_DATA_VERSION), "data": data},
        gzipped=True,
    )


def pack_chunk(x: int, z: int) -> int:
    unsigned = ((z & 0xFFFFFFFF) << 32) | (x & 0xFFFFFFFF)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


RESOURCE_LOCATION = re.compile(r"^[a-z0-9_.-]+:[a-z0-9/._-]+$")


def validate_mod_forced(value: object) -> nbtlib.List:
    if not isinstance(value, nbtlib.List):
        raise ConversionError("chunks.dat data.ModForced must be a list")
    for outer_index, controller in enumerate(value):
        label = f"chunks.dat data.ModForced[{outer_index}]"
        if not isinstance(controller, nbtlib.Compound):
            raise ConversionError(f"{label} must be a compound")
        ensure_exact_keys(controller, {"Controller", "Mod", "ModForced"}, label)
        controller_id = controller.get("Controller", controller.get("Mod"))
        if not isinstance(controller_id, nbtlib.String):
            raise ConversionError(f"{label} must have a Controller or Mod string")
        rendered = str(controller_id)
        if "Controller" not in controller:
            rendered = f"{rendered}:default"
        if not RESOURCE_LOCATION.fullmatch(rendered):
            raise ConversionError(f"{label} has an invalid controller id")
        entries = controller.get("ModForced")
        if not isinstance(entries, nbtlib.List):
            raise ConversionError(f"{label}.ModForced must be a list")
        for inner_index, entry in enumerate(entries):
            inner_label = f"{label}.ModForced[{inner_index}]"
            if not isinstance(entry, nbtlib.Compound):
                raise ConversionError(f"{inner_label} must be a compound")
            ensure_exact_keys(
                entry,
                {"Chunk", "Blocks", "TickingBlocks", "Entities", "TickingEntities"},
                inner_label,
            )
            as_int(entry.get("Chunk"), f"{inner_label}.Chunk")
            for key in ("Blocks", "TickingBlocks"):
                if key not in entry:
                    continue
                owners = entry[key]
                if not isinstance(owners, nbtlib.List):
                    raise ConversionError(f"{inner_label}.{key} must be a list")
                for owner_index, owner in enumerate(owners):
                    if not isinstance(owner, nbtlib.Compound):
                        raise ConversionError(
                            f"{inner_label}.{key}[{owner_index}] must be a compound"
                        )
                    ensure_exact_keys(owner, {"X", "Y", "Z"}, f"{inner_label}.{key}[{owner_index}]")
                    for axis in ("X", "Y", "Z"):
                        as_int(owner.get(axis), f"{inner_label}.{key}[{owner_index}].{axis}")
            for key in ("Entities", "TickingEntities"):
                if key not in entry:
                    continue
                owners = entry[key]
                if not isinstance(owners, nbtlib.List):
                    raise ConversionError(f"{inner_label}.{key} must be a list")
                for owner_index, owner in enumerate(owners):
                    if not isinstance(owner, nbtlib.IntArray) or len(owner) != 4:
                        raise ConversionError(
                            f"{inner_label}.{key}[{owner_index}] must be an IntArray UUID"
                        )
    return copy.deepcopy(value)


def convert_chunks(path: Path) -> tuple[nbtlib.File, dict]:
    root = load_nbt(path)
    data = ensure_file_shape(root, path)
    if not data:
        return new_file(nbtlib.Compound({"Forced": nbtlib.LongArray([])})), {
            "schema": "1.21.11",
            "forced": 0,
            "portal": 0,
        }
    if "Forced" in data and set(data) <= {"Forced", "ModForced"}:
        forced = data["Forced"]
        if not isinstance(forced, nbtlib.LongArray):
            raise ConversionError("chunks.dat data.Forced must be a LongArray")
        values = [int(value) for value in forced]
        if len(values) != len(set(values)):
            raise ConversionError("chunks.dat data.Forced contains duplicate chunks")
        desired = nbtlib.Compound({"Forced": nbtlib.LongArray(values)})
        if "ModForced" in data:
            desired["ModForced"] = validate_mod_forced(data["ModForced"])
        return new_file(desired), {
            "schema": "1.21.1",
            "forced": len(values),
            "portal": 0,
            "mod_forced_controllers": len(data.get("ModForced", [])),
        }

    ensure_exact_keys(data, {"tickets"}, "chunks.dat data")
    tickets = data.get("tickets")
    if not isinstance(tickets, nbtlib.List):
        raise ConversionError("chunks.dat data.tickets must be a list")
    forced_values: list[int] = []
    portal_count = 0
    for index, ticket in enumerate(tickets):
        label = f"chunks.dat data.tickets[{index}]"
        if not isinstance(ticket, nbtlib.Compound):
            raise ConversionError(f"{label} must be a compound")
        ticket_type = ticket.get("type")
        if not isinstance(ticket_type, nbtlib.String):
            raise ConversionError(f"{label}.type must be a string")
        if str(ticket_type) == "minecraft:portal":
            ensure_exact_keys(
                ticket, {"type", "chunk_pos", "level", "ticks_left"}, label
            )
            portal_count += 1
            continue
        if str(ticket_type) != "minecraft:forced":
            raise ConversionError(f"{label} has unsupported ticket type {ticket_type}")
        ensure_exact_keys(ticket, {"type", "chunk_pos", "level"}, label)
        position = ticket.get("chunk_pos")
        if not isinstance(position, nbtlib.IntArray) or len(position) != 2:
            raise ConversionError(f"{label}.chunk_pos must be an IntArray of length 2")
        level = as_int(ticket.get("level"), f"{label}.level")
        if level != 31:
            raise ConversionError(f"{label}.level={level} cannot be represented losslessly")
        forced_values.append(pack_chunk(int(position[0]), int(position[1])))
    if portal_count:
        raise ConversionError(
            f"chunks.dat still contains {portal_count} portal ticket(s); wait for expiry, "
            "save-all flush, stop the source server, and retry"
        )
    if len(forced_values) != len(set(forced_values)):
        raise ConversionError("chunks.dat forced tickets collapse to duplicate chunks")
    return new_file(
        nbtlib.Compound({"Forced": nbtlib.LongArray(forced_values)})
    ), {"schema": "1.21.11", "forced": len(forced_values), "portal": 0}


def convert_world_uuid(path: Path) -> tuple[nbtlib.File, dict]:
    root = load_nbt(path)
    data = ensure_file_shape(root, path)
    if set(data) == {"WorldUUID"}:
        wrapper = data["WorldUUID"]
        if not isinstance(wrapper, nbtlib.Compound):
            raise ConversionError("WorldUUID.dat data.WorldUUID must be a compound")
        ensure_exact_keys(wrapper, {"world_uuid"}, "WorldUUID.dat data.WorldUUID")
        value = wrapper.get("world_uuid")
        schema = "1.21.1"
    else:
        ensure_exact_keys(data, {"world_uuid"}, "WorldUUID.dat data")
        value = data.get("world_uuid")
        schema = "1.21.11"
    if not isinstance(value, nbtlib.String):
        raise ConversionError("WorldUUID.dat world_uuid must be a string")
    try:
        parsed = str(uuid.UUID(str(value)))
    except ValueError as exc:
        raise ConversionError("WorldUUID.dat contains an invalid UUID") from exc
    return new_file(
        nbtlib.Compound(
            {"WorldUUID": nbtlib.Compound({"world_uuid": nbtlib.String(parsed)})}
        )
    ), {"schema": schema, "uuid_preserved": True}


BORDER_FIELDS = {
    "center_x": ("BorderCenterX", nbtlib.Double),
    "center_z": ("BorderCenterZ", nbtlib.Double),
    "size": ("BorderSize", nbtlib.Double),
    "lerp_target": ("BorderSizeLerpTarget", nbtlib.Double),
    "lerp_time": ("BorderSizeLerpTime", nbtlib.Long),
    "safe_zone": ("BorderSafeZone", nbtlib.Double),
    "damage_per_block": ("BorderDamagePerBlock", nbtlib.Double),
    "warning_blocks": ("BorderWarningBlocks", nbtlib.Double),
    "warning_time": ("BorderWarningTime", nbtlib.Double),
}


def read_border(path: Path) -> tuple[dict[str, int | float], dict]:
    border_root = load_nbt(path)
    border = ensure_file_shape(border_root, path)
    ensure_exact_keys(border, set(BORDER_FIELDS), "world_border.dat data")
    values: dict[str, int | float] = {}
    for source_key, (_, tag_type) in BORDER_FIELDS.items():
        raw = border.get(source_key)
        values[source_key] = (
            as_int(raw, f"{path} data.{source_key}")
            if tag_type is nbtlib.Long
            else as_number(raw, f"{path} data.{source_key}")
        )
    return values, {
        "fields": len(BORDER_FIELDS),
        "warning_time": int(values["warning_time"]),
    }


def convert_borders(paths: list[Path], level_path: Path) -> tuple[nbtlib.File, dict]:
    if not paths:
        raise ConversionError("no world_border.dat was found")
    dimension_values: dict[str, dict[str, int | float]] = {}
    dimension_metrics: dict[str, dict] = {}
    world_root = paths[0].parents[1]
    for path in paths:
        values, metrics = read_border(path)
        relative = path.parents[1].relative_to(world_root).as_posix()
        dimension = relative if relative != "." else "overworld"
        dimension_values[dimension] = values
        dimension_metrics[dimension] = metrics
    canonical = next(iter(dimension_values.values()))
    mismatched = [
        dimension
        for dimension, values in dimension_values.items()
        if values != canonical
    ]
    if mismatched:
        raise ConversionError(
            "per-dimension world borders differ and cannot be represented by the "
            f"single 1.21.1 level.dat border: {mismatched}"
        )
    level_root = load_nbt(level_path)
    level_data = level_root.get("Data")
    if not isinstance(level_data, nbtlib.Compound):
        raise ConversionError("level.dat Data must be a compound")
    desired = copy.deepcopy(level_root)
    desired_data = desired["Data"]
    for source_key, (target_key, tag_type) in BORDER_FIELDS.items():
        desired_data[target_key] = tag_type(canonical[source_key])
    return desired, {
        "schema": "1.21.11",
        "fields": len(BORDER_FIELDS),
        "warning_time": int(canonical["warning_time"]),
        "dimensions": dimension_metrics,
    }


def convert_raids(path: Path) -> tuple[nbtlib.File, dict]:
    root = load_nbt(path)
    data = ensure_file_shape(root, path)
    if set(data) <= {"NextAvailableID", "Tick", "Raids"} and {
        "NextAvailableID",
        "Tick",
        "Raids",
    } <= set(data):
        raids = data["Raids"]
        if not isinstance(raids, nbtlib.List):
            raise ConversionError("raids.dat data.Raids must be a list")
        desired = copy.deepcopy(data)
        desired["NextAvailableID"] = nbtlib.Int(
            as_int(data["NextAvailableID"], "raids.dat NextAvailableID")
        )
        desired["Tick"] = nbtlib.Int(as_int(data["Tick"], "raids.dat Tick"))
        return new_file(desired), {
            "schema": "1.21.1",
            "active": len(raids),
            "preserved": True,
        }

    ensure_exact_keys(data, {"next_id", "tick", "raids"}, "raids.dat data")
    raids = data.get("raids", nbtlib.List([]))
    if not isinstance(raids, nbtlib.List):
        raise ConversionError("raids.dat data.raids must be a list")
    if len(raids):
        raise ConversionError(
            f"raids.dat contains {len(raids)} active raid(s); active raid reverse codec "
            "is not implemented"
        )
    next_id = as_int(data.get("next_id"), "raids.dat data.next_id")
    tick = as_int(data.get("tick"), "raids.dat data.tick")
    return new_file(
        nbtlib.Compound(
            {
                "NextAvailableID": nbtlib.Int(next_id),
                "Tick": nbtlib.Int(tick),
                "Raids": nbtlib.List[nbtlib.Compound]([]),
            }
        )
    ), {"schema": "1.21.11", "active": 0, "next_id": next_id}


def normalize_component(value: str) -> str:
    try:
        json.loads(value)
        return value
    except json.JSONDecodeError:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def validate_score_entry(entry: object, index: int) -> nbtlib.Compound:
    if not isinstance(entry, nbtlib.Compound):
        raise ConversionError(f"scoreboard PlayerScores[{index}] must be a compound")
    ensure_exact_keys(
        entry,
        {"Name", "Objective", "Score", "Locked", "display", "format"},
        f"scoreboard PlayerScores[{index}]",
    )
    for key in ("Name", "Objective"):
        if not isinstance(entry.get(key), nbtlib.String):
            raise ConversionError(f"scoreboard PlayerScores[{index}].{key} must be a string")
    as_int(entry.get("Score"), f"scoreboard PlayerScores[{index}].Score")
    if "Locked" in entry:
        as_int(entry["Locked"], f"scoreboard PlayerScores[{index}].Locked")
    return copy.deepcopy(entry)


def convert_scoreboard(path: Path) -> tuple[nbtlib.File, dict]:
    root = load_nbt(path)
    data = ensure_file_shape(root, path)
    ensure_exact_keys(data, {"PlayerScores", "Objectives", "Teams", "DisplaySlots"}, "scoreboard.dat data")
    scores = data.get("PlayerScores", nbtlib.List[nbtlib.Compound]([]))
    objectives = data.get("Objectives", nbtlib.List[nbtlib.Compound]([]))
    if not isinstance(scores, nbtlib.List) or not isinstance(objectives, nbtlib.List):
        raise ConversionError("scoreboard PlayerScores/Objectives must be lists")
    normalized_scores = [validate_score_entry(entry, index) for index, entry in enumerate(scores)]
    target_schema = all(
        isinstance(entry, nbtlib.Compound)
        and {"CriteriaName", "RenderType", "DisplayName", "Name"} <= set(entry)
        for entry in objectives
    )
    if target_schema:
        return new_file(copy.deepcopy(data)), {
            "schema": "1.21.1",
            "objectives": len(objectives),
            "scores": len(scores),
            "preserved": True,
        }
    teams = data.get("Teams")
    if teams is not None and (not isinstance(teams, nbtlib.List) or len(teams)):
        raise ConversionError("modern scoreboard teams require an explicit reverse codec")
    normalized_objectives: list[nbtlib.Compound] = []
    for index, objective in enumerate(objectives):
        label = f"scoreboard Objectives[{index}]"
        if not isinstance(objective, nbtlib.Compound):
            raise ConversionError(f"{label} must be a compound")
        ensure_exact_keys(objective, {"Name", "DisplayName"}, label)
        name = objective.get("Name")
        display = objective.get("DisplayName")
        if not isinstance(name, nbtlib.String) or not isinstance(display, nbtlib.String):
            raise ConversionError(f"{label} Name/DisplayName must be strings")
        normalized_objectives.append(
            nbtlib.Compound(
                {
                    "Name": nbtlib.String(str(name)),
                    "CriteriaName": nbtlib.String("dummy"),
                    "RenderType": nbtlib.String("integer"),
                    "display_auto_update": nbtlib.Byte(0),
                    "DisplayName": nbtlib.String(normalize_component(str(display))),
                }
            )
        )
    converted = nbtlib.Compound(
        {
            "PlayerScores": nbtlib.List[nbtlib.Compound](normalized_scores),
            "Teams": nbtlib.List[nbtlib.Compound]([]),
            "Objectives": nbtlib.List[nbtlib.Compound](normalized_objectives),
        }
    )
    if "DisplaySlots" in data:
        converted["DisplaySlots"] = copy.deepcopy(data["DisplaySlots"])
    return new_file(converted), {
        "schema": "1.21.11",
        "objectives": len(objectives),
        "scores": len(scores),
    }


MAP_FILE_NAME = re.compile(r"^map_(0|[1-9][0-9]*)\.dat$")


def convert_map(path: Path) -> tuple[nbtlib.File, dict]:
    """Normalize the target-required map banner list without touching payloads.

    Minecraft 1.21.1 unconditionally decodes ``data.banners`` with a list
    codec.  A missing key is presented to that codec as ``null`` and emits the
    persistent ``Not a list: null`` warning.  Modern map saves always write the
    key, so the only bounded repair is an empty compound list when it is absent.
    Existing lists and every other map field are preserved byte-semantically.
    """
    if MAP_FILE_NAME.fullmatch(path.name) is None:
        raise ConversionError(f"invalid map SavedData file name: {path.name}")
    root = load_nbt(path)
    data = ensure_file_shape(root, path)
    desired = copy.deepcopy(root)
    banners = data.get("banners")
    added = banners is None
    if added:
        desired["data"]["banners"] = nbtlib.List[nbtlib.Compound]([])
        banner_count = 0
    else:
        if not isinstance(banners, nbtlib.List):
            raise ConversionError(f"{path.name} data.banners must be a list")
        for index, banner in enumerate(banners):
            if not isinstance(banner, nbtlib.Compound):
                raise ConversionError(
                    f"{path.name} data.banners[{index}] must be a compound"
                )
        banner_count = len(banners)
    frames = data.get("frames")
    if frames is not None and not isinstance(frames, nbtlib.List):
        raise ConversionError(f"{path.name} data.frames must be a list when present")
    return desired, {
        "source_sha256": sha256(path),
        "data_version": int(root["DataVersion"])
        if isinstance(root.get("DataVersion"), nbtlib.Int)
        else None,
        "banners_added": added,
        "banners": banner_count,
        "frames": len(frames) if isinstance(frames, nbtlib.List) else 0,
        "other_fields_preserved": True,
    }


def typed(value: object) -> object:
    if isinstance(value, nbtlib.Compound):
        return (
            "Compound",
            tuple((key, typed(value[key])) for key in sorted(value)),
        )
    if isinstance(value, nbtlib.List):
        return (type(value).__name__, tuple(typed(item) for item in value))
    if isinstance(value, nbtlib.Array):
        return (type(value).__name__, tuple(int(item) for item in value))
    if isinstance(value, nbtlib.String):
        return ("String", str(value))
    if isinstance(value, nbtlib.Base):
        return (type(value).__name__, value.unpack())
    if isinstance(value, nbtlib.File):
        return (
            "File",
            tuple((key, typed(value[key])) for key in sorted(value)),
        )
    return value


def write_transaction(plans: dict[Path, nbtlib.File | bytes]) -> list[dict]:
    changed: list[tuple[Path, nbtlib.File | bytes]] = []
    output: list[dict] = []
    for path, desired in plans.items():
        before = sha256(path) if path.is_file() else None
        already_target = (
            path.is_file() and path.read_bytes() == desired
            if isinstance(desired, bytes)
            else path.is_file() and typed(load_nbt(path)) == typed(desired)
        )
        if already_target:
            output.append({"path": str(path), "changed": False, "sha256": before})
            continue
        changed.append((path, desired))
        output.append({"path": str(path), "changed": True, "sha256_before": before})

    temporary: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    committed: list[Path] = []
    commit_complete = False
    rollback_complete = False
    try:
        for path, desired in changed:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".migration.tmp")
            backup = path.with_name(path.name + ".migration.bak")
            for stale in (temp, backup):
                if stale.exists():
                    raise ConversionError(
                        f"stale SavedData transaction artifact requires recovery: {stale}"
                    )
            if isinstance(desired, bytes):
                temp.write_bytes(desired)
                if temp.read_bytes() != desired:
                    raise ConversionError(f"temporary byte write verification failed: {temp}")
            else:
                desired.save(temp, gzipped=True)
                # Parse every temporary file before touching the destination.
                load_nbt(temp)
            temporary[path] = temp
            if path.exists():
                shutil.copy2(path, backup)
                backups[path] = backup
            else:
                backups[path] = None
        for path, _ in changed:
            committed.append(path)
            os.replace(temporary[path], path)
        commit_complete = True
    except BaseException as commit_error:
        rollback_failures: list[str] = []
        for path in reversed(committed):
            backup = backups.get(path)
            try:
                if backup is None:
                    if path.exists():
                        path.unlink()
                elif backup.exists():
                    os.replace(backup, path)
                else:
                    rollback_failures.append(f"missing backup for {path}")
            except BaseException as rollback_error:
                rollback_failures.append(
                    f"{path}: {type(rollback_error).__name__}: {rollback_error}"
                )
        if rollback_failures:
            raise ConversionError(
                "SavedData commit failed and rollback is incomplete; retain .migration.bak "
                f"files for recovery: {rollback_failures}"
            ) from commit_error
        rollback_complete = True
        raise
    finally:
        for temp in temporary.values():
            if temp.exists():
                temp.unlink()
        if commit_complete or rollback_complete:
            for backup in backups.values():
                if backup is not None and backup.exists():
                    backup.unlink()

    by_path = {entry["path"]: entry for entry in output}
    for path, _ in changed:
        by_path[str(path)]["sha256"] = sha256(path)
    return output


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _run_locked(args: argparse.Namespace) -> int:
    source = args.source_world.resolve()
    target = args.target_world.resolve()
    report_path = args.report.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ConversionError(
            "source and target worlds must be disjoint; neither may contain the other"
        )
    selected = set(args.only or KINDS)
    unknown = selected - set(KINDS)
    if unknown:
        raise ConversionError(f"unknown conversion kinds: {sorted(unknown)}")
    plans: dict[Path, nbtlib.File | bytes] = {}
    metrics: dict[str, dict] = {}
    skipped_missing: list[str] = []
    data_source = source / "data"
    data_target = target / "data"
    dimensions = ((Path(), "overworld"), (Path("DIM-1"), "the_nether"), (Path("DIM1"), "the_end"))
    if "chunks" in selected:
        chunk_metrics = {}
        chunk_errors = []
        for relative, label in dimensions:
            source_path = source / relative / "data" / "chunks.dat"
            if not source_path.is_file():
                continue
            target_path = target / relative / "data" / "chunks.dat"
            try:
                plans[target_path], chunk_metrics[label] = convert_chunks(source_path)
            except ConversionError as exc:
                chunk_errors.append(f"{label}: {exc}")
        if chunk_errors:
            raise ConversionError("; ".join(chunk_errors))
        if chunk_metrics:
            metrics["chunks"] = chunk_metrics
        else:
            metrics["chunks"] = {"schema": "absent", "skipped": True}
            skipped_missing.append("chunks")
    if "world_uuid" in selected:
        source_path = data_source / "WorldUUID.dat"
        if source_path.is_file():
            plans[data_target / "WorldUUID.dat"], metrics["world_uuid"] = convert_world_uuid(source_path)
        else:
            metrics["world_uuid"] = {"schema": "absent", "skipped": True}
            skipped_missing.append("world_uuid")
    if "border" in selected:
        border_paths = [
            source / relative / "data" / "world_border.dat"
            for relative, _ in dimensions
            if (source / relative / "data" / "world_border.dat").is_file()
        ]
        if border_paths:
            plans[target / "level.dat"], metrics["border"] = convert_borders(
                border_paths, target / "level.dat"
            )
        else:
            metrics["border"] = {"schema": "absent", "skipped": True}
            skipped_missing.append("border")
    if "raids" in selected:
        raid_metrics = {}
        raid_paths = (
            (Path("data/raids.dat"), "overworld"),
            (Path("DIM-1/data/raids.dat"), "the_nether"),
            (Path("DIM1/data/raids_end.dat"), "the_end"),
        )
        for relative, label in raid_paths:
            source_path = source / relative
            if not source_path.is_file():
                continue
            plans[target / relative], raid_metrics[label] = convert_raids(source_path)
        if raid_metrics:
            metrics["raids"] = raid_metrics
        else:
            metrics["raids"] = {"schema": "absent", "skipped": True}
            skipped_missing.append("raids")
    if "scoreboard" in selected:
        source_path = data_source / "scoreboard.dat"
        if source_path.is_file():
            plans[data_target / "scoreboard.dat"], metrics["scoreboard"] = convert_scoreboard(source_path)
        else:
            metrics["scoreboard"] = {"schema": "absent", "skipped": True}
            skipped_missing.append("scoreboard")
    if "maps" in selected:
        map_paths = sorted(
            data_source.glob("map_*.dat"),
            key=lambda path: (
                int(MAP_FILE_NAME.fullmatch(path.name).group(1))
                if MAP_FILE_NAME.fullmatch(path.name)
                else -1,
                path.name,
            ),
        )
        invalid_names = [
            path.name for path in map_paths if MAP_FILE_NAME.fullmatch(path.name) is None
        ]
        if invalid_names:
            raise ConversionError(
                f"invalid map SavedData file names: {sorted(invalid_names)}"
            )
        map_metrics = {}
        for source_path in map_paths:
            target_path = data_target / source_path.name
            plans[target_path], map_metrics[source_path.name] = convert_map(source_path)
        if map_metrics:
            repaired = []
            for name, item in map_metrics.items():
                if not item["banners_added"]:
                    continue
                target_map = plans[data_target / name]
                assert isinstance(target_map, nbtlib.File)
                repaired.append(
                    {
                        "schema": 1,
                        "record_type": "map_banner_missing_field",
                        "dimension": str(target_map["data"].get("dimension", "unknown")),
                        "map_id": int(MAP_FILE_NAME.fullmatch(name).group(1)),
                        "source_file": f"world/data/{name}",
                        "source_sha256": item["source_sha256"],
                        "banner_index": None,
                        "repair": "add-empty-banners-list",
                        "frames_preserved": item["frames"],
                        "other_fields_preserved": True,
                    }
                )
            sidecar_payload = b"".join(
                (
                    json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode("utf-8")
                for record in sorted(repaired, key=lambda record: record["map_id"])
            )
            sidecar_path = target.parent / MAP_SIDECAR_RELATIVE
            if sidecar_path.exists() and sidecar_path.read_bytes() != sidecar_payload:
                raise ConversionError(
                    f"existing map banner sidecar differs from deterministic source plan: {sidecar_path}"
                )
            plans[sidecar_path] = sidecar_payload
            metrics["maps"] = {
                "files": len(map_metrics),
                "normalized_missing_banners": sum(
                    bool(item["banners_added"]) for item in map_metrics.values()
                ),
                "sidecar": MAP_SIDECAR_RELATIVE.as_posix(),
                "sidecar_records": len(repaired),
                "records": map_metrics,
            }
        else:
            metrics["maps"] = {"schema": "absent", "skipped": True}
            skipped_missing.append("maps")
    outputs = write_transaction(plans)
    report = {
        "status": "CONVERTED" if any(item["changed"] for item in outputs) else "ALREADY_TARGET",
        "source_world": str(source),
        "target_world": str(target),
        "selected": sorted(selected),
        "metrics": metrics,
        "skipped_missing": sorted(skipped_missing),
        "outputs": outputs,
    }
    write_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


def run(args: argparse.Namespace) -> int:
    source = args.source_world.resolve()
    target = args.target_world.resolve()
    report_path = args.report.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ConversionError(
            "source and target worlds must be disjoint; neither may contain the other"
        )
    selected = set(args.only or KINDS)
    unknown = selected - set(KINDS)
    if unknown:
        raise ConversionError(f"unknown conversion kinds: {sorted(unknown)}")
    lock_path = conversion_lock_path(target)
    if report_path == lock_path:
        raise ConversionError(f"report path must not be the conversion lock: {lock_path}")

    with TargetConversionLock(target):
        try:
            return _run_locked(args)
        except ConversionError as exc:
            report = {
                "status": "BLOCKED",
                "source_world": str(source),
                "target_world": str(target),
                "selected": sorted(selected),
                "blockers": [str(exc)],
            }
            write_report(report_path, report)
            raise


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--target-world", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--only", action="append", choices=KINDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args)
    except ConversionError as exc:
        report = {
            "status": "BLOCKED",
            "source_world": str(args.source_world.resolve()),
            "target_world": str(args.target_world.resolve()),
            "selected": sorted(set(args.only or KINDS)),
            "blockers": [str(exc)],
        }
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
