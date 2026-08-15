#!/usr/bin/env python3
"""Apply the reviewed Attempt11 loot/tag follow-up fixes transactionally.

This script is deliberately bound to the two fresh Attempt11 roots on D:.
It never starts Java.  Its only candidate mutations are the two copies of the
DnT JAR, the two copies of the Tracks JAR, and deletion of one exact server
debug loot-table override.  Every input and pre-state is hash locked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any


AUDIT_ROOT = Path(r"D:\Trans\migration-audit-work")
SERVER = AUDIT_ROOT / "mechanomania-matched-runtime-attempt11-20260814"
CLIENT = AUDIT_ROOT / "mechanomania-matched-client-attempt11-20260814"
BACKUP = AUDIT_ROOT / "attempt11-followup-fixes-backup-20260814"
PREFLIGHT_REPORT = AUDIT_ROOT / "attempt11-followup-fixes-preflight-20260814.json"
APPLY_REPORT = AUDIT_ROOT / "attempt11-followup-fixes-apply-20260814.json"
POSTVERIFY_REPORT = AUDIT_ROOT / "attempt11-followup-fixes-postverify-20260814.json"

DNT_NAME = "DnT-ancient-city-overhaul-v2 [NeoForge].jar"
TRACKS_NAME = "tracks-neoforge-1.21.1-1.0.1.jar"
DNT_ARTIFACT = (
    AUDIT_ROOT
    / "attempt10-loot-followup-fixes-20260814"
    / "jars"
    / DNT_NAME
)
TRACKS_ARTIFACT = (
    AUDIT_ROOT
    / "tracks-tag-fix-artifacts-20260814"
    / "tracks-neoforge-1.21.1-1.0.1-block-tag-fix.1.jar"
)

DNT_OLD_SHA256 = "3BF31C37B82B474C447E003C07DE96D5CF38DB1E5BD19F8A4482202B0BC30F39"
DNT_OLD_BYTES = 945_261
DNT_NEW_SHA256 = "A7D3ABB6C39FB50C791D52E596C9D14C22D0287EAF6BA055A687C31C0A4C8A7E"
DNT_NEW_BYTES = 945_155
TRACKS_OLD_SHA256 = "B5022C73AE4A36E8798D1E57D8128EB42DA2964C6E38C722D2AD7CCD2FF443E5"
TRACKS_OLD_BYTES = 165_882
TRACKS_NEW_SHA256 = "3119FA84955907FD734EF77F2296EC2E546F4442BC3AE13B04046C5D71F61CCF"
TRACKS_NEW_BYTES = 165_818

RING_REL = Path("kubejs/data/irons_spellbooks/loot_table/test/ring_gen_break_me.json")
RING_SHA256 = "C836FCE6BE894AB5C5004692A4F2215B6FCCAF7EE88848E2F476CC3C0F189636"
RING_BYTES = 466
IRON_NAME = "irons_spellbooks-1.21.1-3.15.6.jar"
IRON_SHA256 = "BD8235AEF2F7F4827D8005E9700C1C04E5F3A84C50E0F92685674CAC49E985DB"
IRON_BYTES = 13_584_342
IRON_RING_ENTRY = "data/irons_spellbooks/loot_table/test/ring_gen_break_me.json"
MAID_REL = Path("kubejs/server_scripts/maid.js")
MAID_SHA256 = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
MAID_BYTES = 119

DNT_CHANGED_ENTRIES = {
    "data/minecraft/loot_table/chests/illager_mansion/library_chest.json": (2, 2, 60),
    "data/minecraft/loot_table/chests/illager_mansion/secret_room.json": (1, 3, 30),
}
TRACKS_CHANGED_ENTRIES = {
    "data/create/tags/block/safe_nbt.json",
    "data/minecraft/tags/block/mineable/pickaxe.json",
}
TRACKS_OLD_VALUES = [
    "tracks:track_mount",
    "tracks:suspension_track",
    "tracks:track_drive_wheel",
]
TRACKS_NEW_VALUES = ["tracks:track_mount"]

EXPECTED_MOD_COUNTS = {"server": 236, "client": 247}
GATE_MARKER = ".mechanomania-startup-gate-attempt.json"
MCMODSYNC_RE = re.compile(r"mcmodsync", re.IGNORECASE)
MOD_ID_RE = re.compile(r"\bmodId\s*=\s*['\"]mcmodsync['\"]", re.IGNORECASE)


class FollowupError(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def exact_file(path: Path, expected_bytes: int, expected_sha256: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise FollowupError(f"missing, non-file, or linked exact input: {path}")
    actual_bytes = path.stat().st_size
    actual_sha256 = sha256_file(path)
    if actual_bytes != expected_bytes or actual_sha256 != expected_sha256:
        raise FollowupError(
            f"exact file mismatch: {path}: {actual_bytes}/{actual_sha256} "
            f"!= {expected_bytes}/{expected_sha256}"
        )
    return {
        "path": str(path.resolve()),
        "bytes": actual_bytes,
        "sha256": actual_sha256,
    }


def load_json_bytes(data: bytes, label: str) -> Any:
    try:
        return json.loads(data.decode("utf-8-sig"))
    except Exception as exc:
        raise FollowupError(f"invalid JSON in {label}: {exc}") from exc


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise FollowupError(f"invalid JSON: {path}: {exc}") from exc


def empty_function_paths(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "functions" and isinstance(child, list):
                for index, function in enumerate(child):
                    if function == {}:
                        found.append(f"{child_path}[{index}]")
            found.extend(empty_function_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(empty_function_paths(child, f"{path}[{index}]"))
    return found


def checked_zip(path: Path) -> tuple[list[str], list[str]]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            bad = archive.testzip()
            if bad is not None:
                raise FollowupError(f"ZIP CRC failure in {path}: {bad}")
            names = archive.namelist()
    except zipfile.BadZipFile as exc:
        raise FollowupError(f"invalid ZIP/JAR: {path}: {exc}") from exc
    if len(names) != len(set(names)):
        raise FollowupError(f"duplicate ZIP entries in {path}")
    signatures = [
        name
        for name in names
        if name.upper().startswith("META-INF/")
        and name.upper().endswith((".SF", ".RSA", ".DSA"))
    ]
    if signatures:
        raise FollowupError(f"modified JAR unexpectedly contains signatures: {path}: {signatures}")
    return names, signatures


def zip_changed_entries(old: Path, new: Path) -> list[str]:
    old_names, _ = checked_zip(old)
    new_names, _ = checked_zip(new)
    if old_names != new_names:
        raise FollowupError(f"JAR entry order/set differs: {old} -> {new}")
    with zipfile.ZipFile(old, "r") as old_zip, zipfile.ZipFile(new, "r") as new_zip:
        return [name for name in old_names if old_zip.read(name) != new_zip.read(name)]


def verify_dnt_semantics(path: Path) -> dict[str, Any]:
    names, _ = checked_zip(path)
    parsed_loot = 0
    empty_functions: list[dict[str, str]] = []
    with zipfile.ZipFile(path, "r") as archive:
        for name in names:
            normalized = name.replace("\\", "/")
            if not normalized.endswith(".json") or not (
                "/loot_table/" in normalized or "/item_modifier/" in normalized
            ):
                continue
            parsed_loot += 1
            obj = load_json_bytes(archive.read(name), f"{path}!/{name}")
            for json_path in empty_function_paths(obj):
                empty_functions.append({"entry": name, "path": json_path})
        if empty_functions:
            raise FollowupError(f"DnT still contains empty loot function objects: {empty_functions}")

        for name, (pool_index, entry_index, expected_weight) in DNT_CHANGED_ENTRIES.items():
            obj = load_json_bytes(archive.read(name), f"{path}!/{name}")
            try:
                entry = obj["pools"][pool_index]["entries"][entry_index]
            except Exception as exc:
                raise FollowupError(f"DnT target entry missing in {name}: {exc}") from exc
            if entry.get("type") != "minecraft:item" or entry.get("name") != "minecraft:book":
                raise FollowupError(f"DnT target book identity changed in {name}")
            if entry.get("weight") != expected_weight:
                raise FollowupError(f"DnT target book weight changed in {name}")
            if "functions" in entry:
                raise FollowupError(f"DnT target functions property remains in {name}")
            expected_outer = [
                {"function": "minecraft:reference", "name": "nova_structures:loot_modifier"}
            ]
            if obj.get("functions") != expected_outer:
                raise FollowupError(f"DnT outer Nova modifier changed in {name}")

        modifier_name = "data/nova_structures/item_modifier/loot_modifier.json"
        modifier = load_json_bytes(archive.read(modifier_name), f"{path}!/{modifier_name}")
        if modifier != []:
            raise FollowupError("DnT Nova no-op item modifier changed")

    return {
        "entry_count": len(names),
        "loot_and_item_modifier_json_parsed": parsed_loot,
        "empty_function_objects": 0,
        "target_entries": sorted(DNT_CHANGED_ENTRIES),
        "zip_crc": "PASS",
    }


def verify_tracks_semantics(path: Path) -> dict[str, Any]:
    names, _ = checked_zip(path)
    values: dict[str, list[str]] = {}
    with zipfile.ZipFile(path, "r") as archive:
        for name in sorted(TRACKS_CHANGED_ENTRIES):
            obj = load_json_bytes(archive.read(name), f"{path}!/{name}")
            if obj != {"values": TRACKS_NEW_VALUES}:
                raise FollowupError(f"Tracks corrected block tag has unexpected semantics: {name}: {obj}")
            values[name] = obj["values"]
    return {
        "entry_count": len(names),
        "corrected_tags": values,
        "zip_crc": "PASS",
    }


def verify_old_tracks_semantics(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        for name in TRACKS_CHANGED_ENTRIES:
            obj = load_json_bytes(archive.read(name), f"{path}!/{name}")
            if obj != {"values": TRACKS_OLD_VALUES}:
                raise FollowupError(f"Tracks pre-state tag changed unexpectedly: {name}: {obj}")


def root_for(side: str) -> Path:
    if side == "server":
        return SERVER
    if side == "client":
        return CLIENT
    raise FollowupError(f"invalid side: {side}")


def relative_target(side: str, relative: Path) -> Path:
    root = root_for(side).resolve()
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise FollowupError(f"target escapes root: {side}/{relative}") from exc
    return target


def allowed_mutation(side: str, relative: Path) -> bool:
    normalized = relative.as_posix()
    return (side, normalized) in {
        ("server", f"mods/{DNT_NAME}"),
        ("client", f"mods/{DNT_NAME}"),
        ("server", f"mods/{TRACKS_NAME}"),
        ("client", f"mods/{TRACKS_NAME}"),
        ("server", RING_REL.as_posix()),
    }


def ensure_root_safety() -> None:
    expected = {
        SERVER: "mechanomania-matched-runtime-attempt11-20260814",
        CLIENT: "mechanomania-matched-client-attempt11-20260814",
    }
    audit_resolved = AUDIT_ROOT.resolve()
    forbidden = Path(r"D:\Trans\20260807").resolve()
    for value, leaf in expected.items():
        if not value.is_dir() or value.is_symlink():
            raise FollowupError(f"unsafe target root: {value}")
        resolved = value.resolve()
        if resolved.name != leaf:
            raise FollowupError(f"Attempt11 target leaf mismatch: {resolved}")
        try:
            resolved.relative_to(audit_resolved)
        except ValueError as exc:
            raise FollowupError(f"target outside D audit root: {resolved}") from exc
        try:
            resolved.relative_to(forbidden)
        except ValueError:
            pass
        else:
            raise FollowupError(f"target overlaps authoritative migration source: {resolved}")
        for runtime_name in ("logs", "crash-reports", GATE_MARKER):
            if (resolved / runtime_name).exists():
                raise FollowupError(f"Attempt11 root already has runtime state: {resolved / runtime_name}")


def active_mcmodsync_hits(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*"):
        if MCMODSYNC_RE.search(path.name):
            hits.append(f"path:{path.relative_to(root).as_posix()}")
    for jar in sorted((root / "mods").glob("*.jar")):
        try:
            with zipfile.ZipFile(jar, "r") as archive:
                names = archive.namelist()
                for name in names:
                    lowered = name.lower().replace("\\", "/")
                    if lowered.startswith(("assets/mcmodsync/", "data/mcmodsync/")):
                        hits.append(f"jar-namespace:{jar.name}!/{name}")
                for metadata in (
                    "META-INF/neoforge.mods.toml",
                    "META-INF/mods.toml",
                    "fabric.mod.json",
                ):
                    if metadata not in names:
                        continue
                    raw = archive.read(metadata).decode("utf-8", errors="replace")
                    if MOD_ID_RE.search(raw):
                        hits.append(f"jar-mod-id:{jar.name}!/{metadata}")
                    if metadata == "fabric.mod.json":
                        try:
                            obj = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if str(obj.get("id", "")).lower() == "mcmodsync":
                            hits.append(f"jar-mod-id:{jar.name}!/{metadata}")
        except zipfile.BadZipFile as exc:
            raise FollowupError(f"invalid active mod JAR while auditing MCModSync: {jar}: {exc}") from exc
    return sorted(set(hits))


def config_snapshot(root: Path) -> dict[str, Any]:
    config = root / "config"
    if not config.is_dir() or config.is_symlink():
        raise FollowupError(f"missing or linked protected config directory: {config}")
    digest = hashlib.sha256()
    files = 0
    total_bytes = 0
    for path in sorted(config.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise FollowupError(f"linked file in protected config tree: {path}")
        relative = path.relative_to(config).as_posix()
        size = path.stat().st_size
        file_hash = sha256_file(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
        files += 1
        total_bytes += size
    return {
        "method": "full-content-sha256-manifest",
        "files": files,
        "bytes": total_bytes,
        "manifest_sha256": digest.hexdigest().upper(),
    }


def sampled_region_hash(path: Path) -> str:
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        offsets = sorted(set((0, max(0, size // 2 - 2048), max(0, size - 4096))))
        for offset in offsets:
            stream.seek(offset)
            digest.update(str(offset).encode("ascii"))
            digest.update(b":")
            digest.update(stream.read(4096))
    return digest.hexdigest().upper()


def world_snapshot(root: Path) -> dict[str, Any]:
    world = root / "world"
    if not world.is_dir() or world.is_symlink():
        raise FollowupError(f"missing or linked protected world directory: {world}")
    metadata = hashlib.sha256()
    content = hashlib.sha256()
    files = 0
    region_files = 0
    total_bytes = 0
    fully_hashed_bytes = 0
    sampled_region_bytes = 0
    for path in sorted(world.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise FollowupError(f"linked file in protected world tree: {path}")
        stat = path.stat()
        relative = path.relative_to(world).as_posix()
        metadata.update(relative.encode("utf-8"))
        metadata.update(b"\0")
        metadata.update(str(stat.st_size).encode("ascii"))
        metadata.update(b"\0")
        metadata.update(str(stat.st_mtime_ns).encode("ascii"))
        metadata.update(b"\n")
        if path.suffix.lower() == ".mca":
            file_hash = sampled_region_hash(path)
            region_files += 1
            sampled_region_bytes += min(stat.st_size, 3 * 4096)
        else:
            file_hash = sha256_file(path)
            fully_hashed_bytes += stat.st_size
        content.update(relative.encode("utf-8"))
        content.update(b"\0")
        content.update(file_hash.encode("ascii"))
        content.update(b"\n")
        files += 1
        total_bytes += stat.st_size
    return {
        "method": "all-path-size-mtime + full non-region hashes + 3-point region samples",
        "files": files,
        "region_files": region_files,
        "bytes": total_bytes,
        "fully_hashed_bytes": fully_hashed_bytes,
        "sampled_region_bytes": sampled_region_bytes,
        "metadata_manifest_sha256": metadata.hexdigest().upper(),
        "content_manifest_sha256": content.hexdigest().upper(),
    }


def protected_snapshot() -> dict[str, Any]:
    maid = exact_file(SERVER / MAID_REL, MAID_BYTES, MAID_SHA256)
    if (CLIENT / MAID_REL).exists():
        raise FollowupError(f"unexpected client maid.js appeared: {CLIENT / MAID_REL}")
    return {
        "server_world": world_snapshot(SERVER),
        "server_config": config_snapshot(SERVER),
        "client_config": config_snapshot(CLIENT),
        "server_maid_js": maid,
        "client_maid_js": "ABSENT",
    }


def verify_ring_prestate() -> dict[str, Any]:
    ring = exact_file(SERVER / RING_REL, RING_BYTES, RING_SHA256)
    obj = load_json_file(SERVER / RING_REL)
    try:
        spells = obj["pools"][0]["entries"][0]["functions"][0]["spell_filter"]["spells"]
    except Exception as exc:
        raise FollowupError(f"debug ring marker structure changed: {exc}") from exc
    if spells != ["none"]:
        raise FollowupError(f"debug ring marker changed: {spells!r}")
    if (CLIENT / RING_REL).exists():
        raise FollowupError(f"unexpected client loose debug ring table: {CLIENT / RING_REL}")
    return {**ring, "classification": "official-pack orphan test override", "spells": spells}


def verify_irons_embedded_absence() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for side in ("server", "client"):
        path = root_for(side) / "mods" / IRON_NAME
        rows[side] = exact_file(path, IRON_BYTES, IRON_SHA256)
        with zipfile.ZipFile(path, "r") as archive:
            if IRON_RING_ENTRY in archive.namelist():
                raise FollowupError(f"Iron's Spells JAR unexpectedly embeds debug table: {side}")
        rows[side]["debug_ring_entry"] = "ABSENT"
    return rows


def validate_sources() -> dict[str, Any]:
    dnt = exact_file(DNT_ARTIFACT, DNT_NEW_BYTES, DNT_NEW_SHA256)
    tracks = exact_file(TRACKS_ARTIFACT, TRACKS_NEW_BYTES, TRACKS_NEW_SHA256)
    dnt["semantics"] = verify_dnt_semantics(DNT_ARTIFACT)
    tracks["semantics"] = verify_tracks_semantics(TRACKS_ARTIFACT)
    return {"dnt": dnt, "tracks": tracks}


def mod_counts() -> dict[str, int]:
    result = {
        "server": len(list((SERVER / "mods").glob("*.jar"))),
        "client": len(list((CLIENT / "mods").glob("*.jar"))),
    }
    if result != EXPECTED_MOD_COUNTS:
        raise FollowupError(f"unexpected active mod counts: {result} != {EXPECTED_MOD_COUNTS}")
    return result


def validate_prestate() -> dict[str, Any]:
    ensure_root_safety()
    sources = validate_sources()
    installed: dict[str, Any] = {}
    for side in ("server", "client"):
        dnt = root_for(side) / "mods" / DNT_NAME
        tracks = root_for(side) / "mods" / TRACKS_NAME
        installed[f"{side}_dnt"] = exact_file(dnt, DNT_OLD_BYTES, DNT_OLD_SHA256)
        installed[f"{side}_tracks"] = exact_file(tracks, TRACKS_OLD_BYTES, TRACKS_OLD_SHA256)
        verify_old_tracks_semantics(tracks)
        dnt_changes = sorted(zip_changed_entries(dnt, DNT_ARTIFACT))
        if dnt_changes != sorted(DNT_CHANGED_ENTRIES):
            raise FollowupError(f"DnT changed-entry set mismatch on {side}: {dnt_changes}")
        tracks_changes = sorted(zip_changed_entries(tracks, TRACKS_ARTIFACT))
        if tracks_changes != sorted(TRACKS_CHANGED_ENTRIES):
            raise FollowupError(f"Tracks changed-entry set mismatch on {side}: {tracks_changes}")
        installed[f"{side}_dnt"]["artifact_changed_entries"] = dnt_changes
        installed[f"{side}_tracks"]["artifact_changed_entries"] = tracks_changes

    mcmodsync = {
        "server": active_mcmodsync_hits(SERVER),
        "client": active_mcmodsync_hits(CLIENT),
    }
    if mcmodsync["server"] or mcmodsync["client"]:
        raise FollowupError(f"MCModSync is active: {mcmodsync}")

    return {
        "sources": sources,
        "installed_before": installed,
        "ring_before": verify_ring_prestate(),
        "irons_spellbooks": verify_irons_embedded_absence(),
        "mod_counts": mod_counts(),
        "mcmodsync_active_hits": mcmodsync,
        "protected": protected_snapshot(),
    }


def backup_path(side: str, relative: Path) -> Path:
    return BACKUP / "originals" / side / relative


def validate_backup() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for side in ("server", "client"):
        rows[f"{side}_dnt"] = exact_file(
            backup_path(side, Path("mods") / DNT_NAME), DNT_OLD_BYTES, DNT_OLD_SHA256
        )
        rows[f"{side}_tracks"] = exact_file(
            backup_path(side, Path("mods") / TRACKS_NAME),
            TRACKS_OLD_BYTES,
            TRACKS_OLD_SHA256,
        )
    rows["server_ring"] = exact_file(backup_path("server", RING_REL), RING_BYTES, RING_SHA256)
    return rows


def validate_installed(expected_protected: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_root_safety()
    sources = validate_sources()
    installed: dict[str, Any] = {}
    for side in ("server", "client"):
        installed[f"{side}_dnt"] = exact_file(
            root_for(side) / "mods" / DNT_NAME, DNT_NEW_BYTES, DNT_NEW_SHA256
        )
        installed[f"{side}_tracks"] = exact_file(
            root_for(side) / "mods" / TRACKS_NAME, TRACKS_NEW_BYTES, TRACKS_NEW_SHA256
        )
        installed[f"{side}_dnt"]["semantics"] = verify_dnt_semantics(
            root_for(side) / "mods" / DNT_NAME
        )
        installed[f"{side}_tracks"]["semantics"] = verify_tracks_semantics(
            root_for(side) / "mods" / TRACKS_NAME
        )
    if (SERVER / RING_REL).exists() or (CLIENT / RING_REL).exists():
        raise FollowupError("loose debug ring table remains active")
    mcmodsync = {
        "server": active_mcmodsync_hits(SERVER),
        "client": active_mcmodsync_hits(CLIENT),
    }
    if mcmodsync["server"] or mcmodsync["client"]:
        raise FollowupError(f"MCModSync is active after integration: {mcmodsync}")
    protected = protected_snapshot()
    if expected_protected is not None and protected != expected_protected:
        raise FollowupError("protected world/config/maid.js snapshot changed during transaction")
    return {
        "sources": sources,
        "installed_after": installed,
        "ring_after": {"server": "ABSENT", "client": "ABSENT"},
        "irons_spellbooks": verify_irons_embedded_absence(),
        "mod_counts": mod_counts(),
        "mcmodsync_active_hits": mcmodsync,
        "protected": protected,
        "backup": validate_backup(),
    }


def atomic_json(path: Path, value: Any) -> None:
    if path.parent.resolve() != AUDIT_ROOT.resolve():
        raise FollowupError(f"report must remain external in D audit root: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def report_envelope(mode: str, status: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "mechanomania-attempt11-followup-transaction/v1",
        "generated_at_utc": now_utc(),
        "mode": mode,
        "status": status,
        "java_started": False,
        "targets": {"server": str(SERVER), "client": str(CLIENT)},
        "allowed_mutations": [
            f"server/mods/{DNT_NAME}",
            f"client/mods/{DNT_NAME}",
            f"server/mods/{TRACKS_NAME}",
            f"client/mods/{TRACKS_NAME}",
            f"server/{RING_REL.as_posix()} (delete exact file)",
        ],
        "protected_paths": [
            "server/world/**",
            "server/config/**",
            "client/config/**",
            f"server/{MAID_REL.as_posix()}",
        ],
        "detail": detail,
    }


def copy_originals_to_backup() -> dict[str, Any]:
    if BACKUP.exists():
        raise FollowupError(f"backup path must be fresh: {BACKUP}")
    BACKUP.mkdir(parents=True)
    operations = [
        ("server", Path("mods") / DNT_NAME),
        ("client", Path("mods") / DNT_NAME),
        ("server", Path("mods") / TRACKS_NAME),
        ("client", Path("mods") / TRACKS_NAME),
        ("server", RING_REL),
    ]
    for side, relative in operations:
        if not allowed_mutation(side, relative):
            raise FollowupError(f"internal mutation allowlist rejected: {side}/{relative}")
        source = relative_target(side, relative)
        destination = backup_path(side, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    rows = validate_backup()
    manifest = {
        "schema": "mechanomania-attempt11-followup-rollback/v1",
        "generated_at_utc": now_utc(),
        "restore_only_to": {"server": str(SERVER), "client": str(CLIENT)},
        "files": rows,
    }
    atomic_backup_json = BACKUP / "ROLLBACK-MANIFEST.json"
    temporary = BACKUP / f".rollback-manifest.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, atomic_backup_json)
    finally:
        if temporary.exists():
            temporary.unlink()
    return rows


def stage_artifact(source: Path, target: Path, size: int, digest: str) -> Path:
    staged = target.with_name(f".{target.name}.attempt11-followup-{uuid.uuid4().hex}.stage")
    shutil.copyfile(source, staged)
    exact_file(staged, size, digest)
    return staged


def cleanup_stages(stages: list[Path]) -> None:
    for path in stages:
        if path.exists():
            path.unlink()


def rollback() -> dict[str, Any]:
    restored: dict[str, Any] = {}
    operations = [
        ("server", Path("mods") / DNT_NAME, DNT_OLD_BYTES, DNT_OLD_SHA256),
        ("client", Path("mods") / DNT_NAME, DNT_OLD_BYTES, DNT_OLD_SHA256),
        ("server", Path("mods") / TRACKS_NAME, TRACKS_OLD_BYTES, TRACKS_OLD_SHA256),
        ("client", Path("mods") / TRACKS_NAME, TRACKS_OLD_BYTES, TRACKS_OLD_SHA256),
        ("server", RING_REL, RING_BYTES, RING_SHA256),
    ]
    for side, relative, size, digest in operations:
        if not allowed_mutation(side, relative):
            raise FollowupError(f"rollback allowlist rejected: {side}/{relative}")
        source = backup_path(side, relative)
        target = relative_target(side, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored[f"{side}/{relative.as_posix()}"] = exact_file(target, size, digest)
    return restored


def apply_transaction() -> dict[str, Any]:
    if APPLY_REPORT.exists():
        raise FollowupError(f"apply report path must be fresh: {APPLY_REPORT}")
    prestate = validate_prestate()
    backup_rows = copy_originals_to_backup()
    stages: list[Path] = []
    committed: list[str] = []
    try:
        plans = [
            ("server", Path("mods") / DNT_NAME, DNT_ARTIFACT, DNT_NEW_BYTES, DNT_NEW_SHA256),
            ("client", Path("mods") / DNT_NAME, DNT_ARTIFACT, DNT_NEW_BYTES, DNT_NEW_SHA256),
            (
                "server",
                Path("mods") / TRACKS_NAME,
                TRACKS_ARTIFACT,
                TRACKS_NEW_BYTES,
                TRACKS_NEW_SHA256,
            ),
            (
                "client",
                Path("mods") / TRACKS_NAME,
                TRACKS_ARTIFACT,
                TRACKS_NEW_BYTES,
                TRACKS_NEW_SHA256,
            ),
        ]
        staged_plans: list[tuple[str, Path, Path]] = []
        for side, relative, source, size, digest in plans:
            if not allowed_mutation(side, relative):
                raise FollowupError(f"commit allowlist rejected: {side}/{relative}")
            target = relative_target(side, relative)
            staged = stage_artifact(source, target, size, digest)
            stages.append(staged)
            staged_plans.append((side, relative, staged))

        for side, relative, staged in staged_plans:
            target = relative_target(side, relative)
            os.replace(staged, target)
            committed.append(f"replace:{side}/{relative.as_posix()}")

        ring = relative_target("server", RING_REL)
        exact_file(ring, RING_BYTES, RING_SHA256)
        ring.unlink()
        committed.append(f"delete:server/{RING_REL.as_posix()}")

        installed = validate_installed(prestate["protected"])
        detail = {
            "transaction": "COMMITTED",
            "committed_operations": committed,
            "backup_root": str(BACKUP),
            "backup_files": backup_rows,
            "prestate": prestate,
            "poststate": installed,
            "protected_unchanged": True,
            "world_changes": 0,
            "config_changes": 0,
            "maid_js_changes": 0,
            "mcmodsync_active": False,
        }
        report = report_envelope("apply", "PASS", detail)
        atomic_json(APPLY_REPORT, report)
        return report
    except Exception as exc:
        rollback_error: str | None = None
        restored: dict[str, Any] = {}
        try:
            restored = rollback()
        except Exception as rollback_exc:  # pragma: no cover - catastrophic filesystem failure
            rollback_error = repr(rollback_exc)
        failure = report_envelope(
            "apply",
            "ROLLED_BACK" if rollback_error is None else "ROLLBACK_FAILED",
            {
                "error": repr(exc),
                "committed_before_failure": committed,
                "restored": restored,
                "rollback_error": rollback_error,
                "backup_root": str(BACKUP),
            },
        )
        try:
            atomic_json(APPLY_REPORT, failure)
        except Exception:
            pass
        if rollback_error is not None:
            raise FollowupError(f"transaction failed and rollback failed: {exc!r}; {rollback_error}") from exc
        raise FollowupError(f"transaction failed and was rolled back: {exc!r}") from exc
    finally:
        cleanup_stages(stages)


def run_preflight() -> dict[str, Any]:
    if PREFLIGHT_REPORT.exists():
        raise FollowupError(f"preflight report path must be fresh: {PREFLIGHT_REPORT}")
    if BACKUP.exists() or APPLY_REPORT.exists():
        raise FollowupError("preflight requires fresh backup/apply-report paths")
    detail = validate_prestate()
    report = report_envelope("preflight", "PASS", detail)
    atomic_json(PREFLIGHT_REPORT, report)
    return report


def run_postverify() -> dict[str, Any]:
    if POSTVERIFY_REPORT.exists():
        raise FollowupError(f"postverify report path must be fresh: {POSTVERIFY_REPORT}")
    if not APPLY_REPORT.is_file() or not BACKUP.is_dir():
        raise FollowupError("postverify requires committed apply report and rollback backup")
    apply_obj = load_json_file(APPLY_REPORT)
    if apply_obj.get("status") != "PASS" or apply_obj.get("detail", {}).get("transaction") != "COMMITTED":
        raise FollowupError("apply report does not prove a committed PASS transaction")
    expected_protected = apply_obj["detail"]["prestate"]["protected"]
    detail = validate_installed(expected_protected)
    detail["apply_report"] = {
        "path": str(APPLY_REPORT),
        "sha256": sha256_file(APPLY_REPORT),
        "status": "PASS",
    }
    detail["protected_unchanged"] = True
    report = report_envelope("postverify", "PASS", detail)
    atomic_json(POSTVERIFY_REPORT, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="apply the exact transaction")
    mode.add_argument(
        "--verify-installed", action="store_true", help="verify committed installed state only"
    )
    args = parser.parse_args()
    try:
        if args.apply:
            report = apply_transaction()
            path = APPLY_REPORT
        elif args.verify_installed:
            report = run_postverify()
            path = POSTVERIFY_REPORT
        else:
            report = run_preflight()
            path = PREFLIGHT_REPORT
    except FollowupError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "mode": report["mode"],
                "report": str(path),
                "java_started": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
