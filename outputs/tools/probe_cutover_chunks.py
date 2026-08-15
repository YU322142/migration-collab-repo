#!/usr/bin/env python3
"""Read-only preflight for the three vanilla ``chunks.dat`` files.

This probe is intended to be run repeatedly while the source server is still
online.  It never writes to the world.  A zero exit status means that every
canonical dimension was read without a concurrent write, the file shape is a
known 1.21.11/1.21.1 shape, and no transient portal ticket remains.  Any
unknown shape, missing dimension file, parse error, or portal ticket returns
exit status 2 so a caller cannot accidentally cut over on incomplete data.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import nbtlib


SCHEMA_VERSION = 1
SUPPORTED_DATA_VERSIONS = {3955, 4671}
DIMENSIONS = (
    ("overworld", Path("data/chunks.dat")),
    ("the_nether", Path("DIM-1/data/chunks.dat")),
    ("the_end", Path("DIM1/data/chunks.dat")),
)
INTEGER_TAGS = (
    nbtlib.Byte,
    nbtlib.Short,
    nbtlib.Int,
    nbtlib.Long,
)
RESOURCE_LOCATION = re.compile(r"^[a-z0-9_.-]+:[a-z0-9/._-]+$")


class ProbeError(ValueError):
    """A chunks.dat file cannot be accepted by the cutover gate."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _integer(value: object, label: str) -> int:
    if not isinstance(value, INTEGER_TAGS):
        raise ProbeError(f"{label} must be an integer tag")
    return int(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, nbtlib.String):
        raise ProbeError(f"{label} must be a string tag")
    return str(value)


def _keys(value: object, allowed: set[str], label: str) -> None:
    if not isinstance(value, nbtlib.Compound):
        raise ProbeError(f"{label} must be a compound")
    unknown = set(value) - allowed
    if unknown:
        raise ProbeError(f"{label} has unknown keys: {sorted(unknown)}")


def _chunk_position(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, nbtlib.IntArray) or len(value) != 2:
        raise ProbeError(f"{label} must be an IntArray of length 2")
    return (_integer(value[0], f"{label}[0]"), _integer(value[1], f"{label}[1]"))


def _validate_mod_forced(value: object) -> int:
    """Validate the optional NeoForge 1.21.1 extension and return controllers."""
    if not isinstance(value, nbtlib.List):
        raise ProbeError("data.ModForced must be a list")
    for index, controller in enumerate(value):
        label = f"data.ModForced[{index}]"
        _keys(controller, {"Controller", "Mod", "ModForced"}, label)
        if "Controller" not in controller and "Mod" not in controller:
            raise ProbeError(f"{label} must have Controller or Mod")
        controller_id = _string(
            controller.get("Controller", controller.get("Mod")),
            f"{label}.Controller",
        )
        if not RESOURCE_LOCATION.fullmatch(controller_id):
            raise ProbeError(f"{label}.Controller is not a resource location")
        entries = controller.get("ModForced")
        if not isinstance(entries, nbtlib.List):
            raise ProbeError(f"{label}.ModForced must be a list")
        for entry_index, entry in enumerate(entries):
            entry_label = f"{label}.ModForced[{entry_index}]"
            _keys(entry, {"Chunk", "Blocks", "TickingBlocks", "Entities", "TickingEntities"}, entry_label)
            _integer(entry.get("Chunk"), f"{entry_label}.Chunk")
            for owner_key in ("Blocks", "TickingBlocks"):
                owners = entry.get(owner_key)
                if owners is None:
                    continue
                if not isinstance(owners, nbtlib.List):
                    raise ProbeError(f"{entry_label}.{owner_key} must be a list")
                for owner_index, owner in enumerate(owners):
                    owner_label = f"{entry_label}.{owner_key}[{owner_index}]"
                    _keys(owner, {"X", "Y", "Z"}, owner_label)
                    for axis in ("X", "Y", "Z"):
                        _integer(owner.get(axis), f"{owner_label}.{axis}")
            for owner_key in ("Entities", "TickingEntities"):
                owners = entry.get(owner_key)
                if owners is None:
                    continue
                if not isinstance(owners, nbtlib.List):
                    raise ProbeError(f"{entry_label}.{owner_key} must be a list")
                for owner_index, owner in enumerate(owners):
                    if not isinstance(owner, nbtlib.IntArray) or len(owner) != 4:
                        raise ProbeError(f"{entry_label}.{owner_key}[{owner_index}] must be a UUID IntArray")
    return len(value)


def _modern_chunks(data: nbtlib.Compound) -> dict[str, Any]:
    _keys(data, {"tickets"}, "data")
    tickets = data.get("tickets")
    if not isinstance(tickets, nbtlib.List):
        raise ProbeError("data.tickets must be a list")
    forced: list[dict[str, int]] = []
    portal: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    unknown_types: list[str] = []
    for index, ticket in enumerate(tickets):
        label = f"data.tickets[{index}]"
        _keys(ticket, {"type", "chunk_pos", "level", "ticks_left"}, label)
        ticket_type = _string(ticket.get("type"), f"{label}.type")
        position = _chunk_position(ticket.get("chunk_pos"), f"{label}.chunk_pos")
        level = _integer(ticket.get("level"), f"{label}.level")
        if ticket_type == "minecraft:forced":
            if set(ticket) != {"type", "chunk_pos", "level"}:
                raise ProbeError(f"{label} forced ticket has an invalid shape")
            if level != 31:
                raise ProbeError(f"{label}.level={level} is not the lossless forced level 31")
            if position in seen:
                raise ProbeError(f"{label} duplicates forced chunk {position}")
            seen.add(position)
            forced.append({"x": position[0], "z": position[1], "level": level})
        elif ticket_type == "minecraft:portal":
            if set(ticket) != {"type", "chunk_pos", "level", "ticks_left"}:
                raise ProbeError(f"{label} portal ticket has an invalid shape")
            ticks_left = _integer(ticket.get("ticks_left"), f"{label}.ticks_left")
            if ticks_left < 0:
                raise ProbeError(f"{label}.ticks_left must not be negative")
            portal.append(
                {"x": position[0], "z": position[1], "level": level, "ticks_left": ticks_left}
            )
        else:
            unknown_types.append(ticket_type)
    if unknown_types:
        raise ProbeError(f"unsupported ticket type(s): {sorted(set(unknown_types))}")
    return {
        "schema": "modern-tickets",
        "ticket_count": len(tickets),
        "forced_count": len(forced),
        "portal_count": len(portal),
        "forced": forced,
        "portal": portal,
        "mod_forced_controllers": 0,
    }


def _target_chunks(data: nbtlib.Compound) -> dict[str, Any]:
    _keys(data, {"Forced", "ModForced"}, "data")
    forced_tag = data.get("Forced")
    if not isinstance(forced_tag, nbtlib.LongArray):
        raise ProbeError("data.Forced must be a LongArray")
    values = [int(value) for value in forced_tag]
    if len(values) != len(set(values)):
        raise ProbeError("data.Forced contains duplicate chunks")
    controllers = _validate_mod_forced(data["ModForced"]) if "ModForced" in data else 0
    return {
        "schema": "target-forced",
        "ticket_count": len(values),
        "forced_count": len(values),
        "portal_count": 0,
        "forced": [{"packed": value} for value in values],
        "portal": [],
        "mod_forced_controllers": controllers,
    }


def _parse_chunks(path: Path) -> dict[str, Any]:
    try:
        root = nbtlib.load(path, gzipped=True)
    except Exception as exc:
        raise ProbeError(f"cannot parse NBT: {type(exc).__name__}: {exc}") from exc
    if not isinstance(root, nbtlib.File):
        raise ProbeError("root is not an NBT file")
    if set(root) != {"DataVersion", "data"}:
        raise ProbeError(
            f"root keys must be exactly ['DataVersion', 'data']; got {sorted(root)}"
        )
    data_version = _integer(root.get("DataVersion"), "DataVersion")
    if data_version not in SUPPORTED_DATA_VERSIONS:
        raise ProbeError(f"unsupported DataVersion {data_version}; expected one of {sorted(SUPPORTED_DATA_VERSIONS)}")
    data = root.get("data")
    if not isinstance(data, nbtlib.Compound):
        raise ProbeError("data must be a compound")
    if not data:
        result = {
            "schema": "empty",
            "ticket_count": 0,
            "forced_count": 0,
            "portal_count": 0,
            "forced": [],
            "portal": [],
            "mod_forced_controllers": 0,
        }
    elif "tickets" in data:
        if data_version != 4671:
            raise ProbeError("tickets schema requires DataVersion 4671")
        result = _modern_chunks(data)
    elif "Forced" in data:
        if data_version != 3955:
            raise ProbeError("Forced schema requires DataVersion 3955")
        result = _target_chunks(data)
    else:
        raise ProbeError("unknown chunks.dat data schema")
    result["data_version"] = data_version
    return result


def _probe_file(dimension: str, relative: Path, path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "dimension": dimension,
        "relative": relative.as_posix(),
        "path": str(path),
        "exists": path.is_file(),
    }
    if not path.is_file():
        record["status"] = "BLOCKED_MISSING"
        record["error"] = "chunks.dat is missing"
        return record
    if path.is_symlink():
        record["status"] = "BLOCKED_SYMLINK"
        record["error"] = "symbolic links are not accepted"
        return record
    try:
        before = path.stat()
        digest = sha256(path)
        after_hash = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after_hash.st_size, after_hash.st_mtime_ns):
            raise ProbeError("file changed while being read; retry after save-all flush")
        record.update(_parse_chunks(path))
        after_parse = path.stat()
        digest_after = sha256(path)
        if (
            (before.st_size, before.st_mtime_ns)
            != (after_parse.st_size, after_parse.st_mtime_ns)
            or digest != digest_after
        ):
            raise ProbeError("file changed while being parsed; retry after save-all flush")
        record.update(
            {"bytes": after_parse.st_size, "mtime_ns": after_parse.st_mtime_ns, "sha256": digest_after}
        )
        record["status"] = "OK"
    except (OSError, ProbeError) as exc:
        record["status"] = "BLOCKED_SCHEMA"
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def probe_world(source_world: Path) -> dict[str, Any]:
    source_world = source_world.resolve()
    dimensions = [_probe_file(name, rel, source_world / rel) for name, rel in DIMENSIONS]
    blockers: list[str] = []
    for record in dimensions:
        if record.get("status") != "OK":
            blockers.append(f"{record['dimension']}: {record.get('error', record['status'])}")
        elif int(record.get("portal_count", 0)):
            blockers.append(f"{record['dimension']}: {record['portal_count']} portal ticket(s)")
    totals = {
        "ticket_count": sum(int(item.get("ticket_count", 0)) for item in dimensions),
        "forced_count": sum(int(item.get("forced_count", 0)) for item in dimensions),
        "portal_count": sum(int(item.get("portal_count", 0)) for item in dimensions),
    }
    if blockers:
        status = "BLOCKED_PORTAL_TICKETS" if totals["portal_count"] else "BLOCKED_SCHEMA"
    else:
        status = "READY_PORTAL_ZERO"
    return {
        "schema": SCHEMA_VERSION,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_world": str(source_world),
        "dimensions": dimensions,
        "totals": totals,
        "blockers": blockers,
        "status": status,
        "exit_code": 0 if not blockers else 2,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_world", type=Path, help="world root to inspect (read-only)")
    parser.add_argument(
        "--report",
        type=Path,
        help="optional report path outside the world; the source remains read-only",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_world = args.source_world.resolve()
    if args.report:
        report_path = args.report.resolve()
        try:
            report_path.relative_to(source_world)
        except ValueError:
            pass
        else:
            print(
                json.dumps(
                    {
                        "status": "BLOCKED_SCHEMA",
                        "exit_code": 2,
                        "error": "--report must be outside source_world; probe is read-only",
                    },
                    ensure_ascii=False,
                )
            )
            return 2
    report = probe_world(args.source_world)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
