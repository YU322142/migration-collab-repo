#!/usr/bin/env python3
"""Sanitize target-only resource incompatibilities in a copied migration tree.

The source server is never opened by this tool.  It operates on a disposable
target copy (or a copied ``mods`` directory) and is intentionally conservative:
only resources proven to be invalid when their optional dependency is absent are
removed.  Every changed file is reported with before/after hashes so a smoke
bundle can be reproduced and audited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
import zipfile
from pathlib import Path
from typing import Iterable


TARGET_PACK_FORMAT = 48
TRANSFER_PERMISSION_LEVEL = 3
ETERNAL_LOOT_PREFIX = "kaleidoscope_nether:integration/eternalnether/"
ETERNAL_LOOT_RESOURCE_PREFIX = (
    "data/kaleidoscope_nether/loot_modifiers/integration/eternalnether/"
)
CREATE_DRAGONS_OPTIONAL_DATA_MAPS = (
    "data/create_dragons_plus/data_maps/block/"
    "air_current_block_interaction/blasting.json",
    "data/create_dragons_plus/data_maps/block/"
    "air_current_block_interaction/freezing.json",
    "data/create_dragons_plus/data_maps/block/"
    "air_current_block_interaction/smoking.json",
    "data/create_dragons_plus/data_maps/block/"
    "air_current_block_interaction/splashing.json",
    "data/create_dragons_plus/data_maps/block/fragile_fluid_tank/lava.json",
    "data/create_dragons_plus/data_maps/block/fragile_fluid_tank/water.json",
)
CREATE_DRAGONS_OPTIONAL_MOD_IDS = {"simulated"}
# These are the source world's mod-generated pack IDs.  They are not arbitrary
# user datapacks; NeoForge discovers the corresponding mod packs under its own
# runtime IDs and rewrites the list after the first save.
LEGACY_SOURCE_MOD_PACK_IDS = {
    "computercraft",
    "create",
    "create_dragons_plus",
    "create_enchantment_industry",
    "create_nerfad",
    "cyclopscore",
    "easyauth",
    "fabric-convention-tags-v2",
    "ftbultimine",
    "immersive_paintings",
    "kaleidoscope_cookery",
    "kaleidoscope_end",
    "kaleidoscope_nether",
    "kaleidoscope_nether_froglight_fix",
    "kaleidoscope_tavern",
    "ledger",
    "mishanguc",
    "mr_potted_farms",
    "server_translations_api",
    "toms_storage",
    "wooltostring",
    "yuushya",
}


class SanitizeError(RuntimeError):
    """Raised when a target resource cannot be audited safely."""


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=str(path.parent), prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def stable_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def normalize_bukkit_pack(world: Path, changes: list[dict]) -> dict:
    """Make the old Paper-generated Bukkit pack readable by 1.21.1."""
    path = world / "datapacks" / "bukkit" / "pack.mcmeta"
    result = {"path": path.as_posix(), "status": "absent"}
    if not path.is_file():
        return result
    before = sha256(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise SanitizeError(f"Bukkit pack metadata is not valid JSON: {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("pack"), dict):
        raise SanitizeError(f"Bukkit pack metadata has no pack object: {path}")
    pack = dict(value["pack"])
    # 1.21.1's metadata reader requires the legacy integer key.  The source
    # Paper file only has the 1.21.11 min/max tuple and is rejected outright.
    if pack.get("pack_format") != TARGET_PACK_FORMAT:
        pack["pack_format"] = TARGET_PACK_FORMAT
    pack.pop("min_format", None)
    pack.pop("max_format", None)
    normalized = dict(value)
    normalized["pack"] = pack
    payload = stable_json(normalized)
    if payload != path.read_bytes():
        atomic_write(path, payload)
        after = sha256(path)
        changes.append(
            {
                "path": path.as_posix(),
                "kind": "bukkit-pack-metadata",
                "before_sha256": before,
                "after_sha256": after,
                "pack_format": TARGET_PACK_FORMAT,
            }
        )
        result.update({"status": "normalized", "before_sha256": before, "after_sha256": after})
    else:
        result.update({"status": "already-normalized", "sha256": before})
    return result


def normalize_transfer_functions(
    world: Path, server_properties: Path, changes: list[dict]
) -> dict:
    """Keep the source transfer functions usable with the 1.21.1 command tree.

    In 1.21.1 vanilla, ``TransferCommand`` is registered at permission level 3,
    while the source Paper server accepts it from functions at level 2.  We
    raise only the function execution level in the target copy when a transfer
    function is actually present; the function bodies and destination remain
    byte-for-byte unchanged.
    """
    datapack_root = world / "datapacks"
    functions = sorted(datapack_root.glob("*/data/moon/function/*.mcfunction"))
    transfer_functions = []
    command_pattern = re.compile(r"^\s*transfer\s+\S+\s+\d{1,5}(?:\s+.+)?\s*$")
    for path in functions:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise SanitizeError(f"cannot read function {path}") from exc
        if any(command_pattern.match(line) for line in lines):
            transfer_functions.append(path)
    result = {
        "functions": [path.as_posix() for path in transfer_functions],
        "status": "absent" if not transfer_functions else "unchanged-bodies",
    }
    if not transfer_functions:
        return result
    if not server_properties.is_file():
        raise SanitizeError(f"server.properties is missing: {server_properties}")
    try:
        lines = server_properties.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise SanitizeError(f"cannot read {server_properties}") from exc
    seen = False
    updated = []
    changed = False
    for line in lines:
        if line.startswith("#") or "=" not in line:
            updated.append(line)
            continue
        key, current = line.split("=", 1)
        if key != "function-permission-level":
            updated.append(line)
            continue
        seen = True
        try:
            old_level = int(current.strip())
        except ValueError as exc:
            raise SanitizeError(
                f"function-permission-level is not an integer in {server_properties}"
            ) from exc
        new_level = max(old_level, TRANSFER_PERMISSION_LEVEL)
        updated.append(f"{key}={new_level}")
        changed |= new_level != old_level
    if not seen:
        updated.append(f"function-permission-level={TRANSFER_PERMISSION_LEVEL}")
        changed = True
    if changed:
        before = sha256(server_properties)
        atomic_write(server_properties, ("\n".join(updated) + "\n").encode("utf-8"))
        after = sha256(server_properties)
        changes.append(
            {
                "path": server_properties.as_posix(),
                "kind": "transfer-function-permission",
                "before_sha256": before,
                "after_sha256": after,
                "function_permission_level": TRANSFER_PERMISSION_LEVEL,
                "functions": [path.as_posix() for path in transfer_functions],
            }
        )
        result.update({"status": "permission-raised", "before_sha256": before, "after_sha256": after})
    return result


def normalize_datapack_selection(
    world: Path, available: set[str], changes: list[dict]
) -> dict:
    """Remove only known source mod-pack IDs from the copied level.dat.

    Bare source mod IDs are stale in NeoForge's pack repository.  Keeping them
    causes noisy one-time warnings and does not disable the target mod packs:
    NeoForge adds its own internal packs automatically.  Unknown names,
    namespaced packs, and ``file/*`` packs are retained to protect custom user
    datapacks.
    """
    path = world / "level.dat"
    result = {"path": path.as_posix(), "status": "absent"}
    if not path.is_file():
        return result
    try:
        import nbtlib
    except ImportError:
        result["status"] = "nbtlib-unavailable"
        return result
    before = sha256(path)
    try:
        root = nbtlib.load(path, gzipped=True)
        data = root["Data"]
        packs = data["DataPacks"]
        enabled = packs["Enabled"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise SanitizeError(f"cannot read DataPacks from {path}") from exc
    removable = LEGACY_SOURCE_MOD_PACK_IDS | (available & LEGACY_SOURCE_MOD_PACK_IDS)
    retained = []
    removed = []
    for item in enabled:
        name = str(item)
        if name in removable:
            removed.append(name)
        else:
            retained.append(item)
    result["removed"] = removed
    if not removed:
        result.update({"status": "already-normalized", "sha256": before})
        return result
    packs["Enabled"] = nbtlib.List(retained)
    temporary = path.with_name(f".{path.name}.sanitize.tmp")
    try:
        root.save(temporary, gzipped=True)
        nbtlib.load(temporary, gzipped=True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    after = sha256(path)
    changes.append(
        {
            "path": path.as_posix(),
            "kind": "legacy-mod-datapack-selection",
            "before_sha256": before,
            "after_sha256": after,
            "removed": removed,
        }
    )
    result.update({"status": "normalized", "before_sha256": before, "after_sha256": after})
    return result


def read_mod_ids(path: Path) -> set[str]:
    """Read Fabric/NeoForge IDs without requiring a game runtime."""
    ids: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "fabric.mod.json" in names:
                value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                if isinstance(value, dict) and isinstance(value.get("id"), str):
                    ids.add(value["id"])
            for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if name not in names:
                    continue
                value = tomllib.loads(archive.read(name).decode("utf-8"))
                for mod in value.get("mods", []):
                    mod_id = mod.get("modId")
                    if isinstance(mod_id, str) and "${" not in mod_id:
                        ids.add(mod_id)
    except (OSError, zipfile.BadZipFile, ValueError, UnicodeDecodeError):
        return set()
    return ids


def available_mod_ids(mods_dir: Path) -> set[str]:
    ids: set[str] = set()
    for path in sorted(mods_dir.glob("*.jar"), key=lambda item: item.name.lower()):
        ids.update(read_mod_ids(path))
    return ids


def runtime_mod_manifest(mods_dir: Path) -> dict:
    """Hash the exact post-sanitizer JAR set that the runtime will load."""
    rows = []
    bundle = hashlib.sha256()
    for path in sorted(mods_dir.glob("*.jar"), key=lambda item: item.name.lower()):
        if path.is_symlink():
            raise SanitizeError(f"runtime mod JAR must not be a symbolic link: {path}")
        if not zipfile.is_zipfile(path):
            raise SanitizeError(f"runtime mod artifact is not a ZIP/JAR: {path}")
        digest = sha256(path)
        row = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "mod_ids": sorted(read_mod_ids(path)),
        }
        rows.append(row)
        bundle.update(path.name.encode("utf-8"))
        bundle.update(b"\0")
        bundle.update(digest.encode("ascii"))
        bundle.update(b"\n")
    return {
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": bundle.hexdigest().upper(),
        "files": rows,
    }


def patch_zip(path: Path, transform, changes: list[dict]) -> dict:
    """Apply a deterministic ZIP transform atomically and report its hash."""
    before = sha256(path)
    with zipfile.ZipFile(path, "r") as source:
        entries = []
        changed_entries = []
        for info in source.infolist():
            data = source.read(info.filename)
            replacement = transform(info.filename, data)
            if replacement is None:
                changed_entries.append(info.filename)
                continue
            if replacement != data:
                changed_entries.append(info.filename)
            entries.append((info, replacement))
    if not changed_entries:
        return {"path": path.as_posix(), "status": "unchanged", "sha256": before}
    temporary = path.with_name(f".{path.name}.sanitize.tmp")
    try:
        with zipfile.ZipFile(temporary, "w") as target:
            for info, data in entries:
                target.writestr(info, data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    after = sha256(path)
    changes.append(
        {
            "path": path.as_posix(),
            "kind": "jar-resource-sanitize",
            "before_sha256": before,
            "after_sha256": after,
            "entries": sorted(changed_entries),
        }
    )
    return {
        "path": path.as_posix(),
        "status": "patched",
        "before_sha256": before,
        "after_sha256": after,
        "entries": sorted(changed_entries),
    }


def patch_kaleidoscope_nether(path: Path, optional_mods: set[str], changes: list[dict]) -> dict:
    """Drop stale Eternal Nether GLM registrations when that mod is absent."""
    if "eternalnether" in optional_mods:
        return {"path": path.as_posix(), "status": "dependency-present"}
    global_list = "data/neoforge/loot_modifiers/global_loot_modifiers.json"

    def transform(name: str, data: bytes) -> bytes | None:
        if name.startswith(ETERNAL_LOOT_RESOURCE_PREFIX):
            return None
        if name != global_list:
            return data
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            raise SanitizeError(f"invalid Kaleidoscope Nether GLM list in {path}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
            raise SanitizeError(f"unexpected Kaleidoscope Nether GLM list in {path}")
        filtered = [
            entry
            for entry in value["entries"]
            if not (isinstance(entry, str) and entry.startswith(ETERNAL_LOOT_PREFIX))
        ]
        if len(filtered) == len(value["entries"]):
            return data
        value = dict(value)
        value["entries"] = filtered
        return stable_json(value)

    return patch_zip(path, transform, changes)


def patch_create_dragons_plus(path: Path, optional_mods: set[str], changes: list[dict]) -> dict:
    """Drop DataMaps whose registry exists only with the optional Simulated mod."""
    if optional_mods & CREATE_DRAGONS_OPTIONAL_MOD_IDS:
        return {"path": path.as_posix(), "status": "dependency-present"}
    wanted = set(CREATE_DRAGONS_OPTIONAL_DATA_MAPS)

    def transform(name: str, data: bytes) -> bytes | None:
        return None if name in wanted else data

    return patch_zip(path, transform, changes)


def sanitize(
    world: Path, server_properties: Path, mods_dir: Path
) -> dict:
    if not world.is_dir():
        raise FileNotFoundError(world)
    if not server_properties.is_file():
        raise FileNotFoundError(server_properties)
    if not mods_dir.is_dir():
        raise FileNotFoundError(mods_dir)
    changes: list[dict] = []
    available = available_mod_ids(mods_dir)
    result = {
        "schema": 1,
        "world": str(world.resolve()),
        "server_properties": str(server_properties.resolve()),
        "mods": str(mods_dir.resolve()),
        "available_mod_ids": sorted(available),
        "changes": changes,
    }
    result["bukkit"] = normalize_bukkit_pack(world, changes)
    result["transfer"] = normalize_transfer_functions(world, server_properties, changes)
    result["datapacks"] = normalize_datapack_selection(world, available, changes)
    kaleidoscope = sorted(mods_dir.glob("kaleidoscope_nether-*.jar"))
    if len(kaleidoscope) > 1:
        raise SanitizeError(f"multiple Kaleidoscope Nether JARs found: {kaleidoscope}")
    if kaleidoscope:
        result["kaleidoscope_nether"] = patch_kaleidoscope_nether(
            kaleidoscope[0], available, changes
        )
    else:
        result["kaleidoscope_nether"] = {"status": "absent"}
    dragons = sorted(mods_dir.glob("CreateDragonsPlus-*.jar"))
    if len(dragons) > 1:
        raise SanitizeError(f"multiple Create Dragons Plus JARs found: {dragons}")
    if dragons:
        result["create_dragons_plus"] = patch_create_dragons_plus(
            dragons[0], available, changes
        )
    else:
        result["create_dragons_plus"] = {"status": "absent"}
    result["runtime_mod_manifest"] = runtime_mod_manifest(mods_dir)
    result["changed_files"] = len(changes)
    result["status"] = "SANITIZED" if changes else "ALREADY_CLEAN"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize target-only migration resources")
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--server-properties", type=Path, required=True)
    parser.add_argument("--mods", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = sanitize(args.world.resolve(), args.server_properties.resolve(), args.mods.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "changed_files": report["changed_files"], "report": str(args.report.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
