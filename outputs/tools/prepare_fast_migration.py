#!/usr/bin/env python3
"""Prepare a fail-closed, D-drive-only cutover workspace.

The source game directory is treated as immutable.  The script deliberately
keeps staging, reports, temporary files, and Python bytecode under the chosen
D-drive workspace.  It has six phases:

* manifest: record source metadata without changing anything;
* stage: make a fresh copy and hash an exact raw-input baseline;
* convert: run the already audited converters into staging atomically;
* refresh: after shutdown, hash all inputs and transactionally convert only deltas;
* verify: re-run read-only passes and require zero blockers/second-pass writes.
* sanitize-target: normalize target-only resources in an already assembled
  target copy, without changing source or staging.

This is an orchestration aid, not a replacement for the final full client and
villager runtime gates.  It refuses to operate in-place or to overwrite an
existing staging directory.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from pathlib import PurePosixPath
from typing import Iterable


SOURCE_DEFAULT = Path(r"<TRANS_ROOT>\20260807")
WORK_DEFAULT = Path(r"<AUDIT_ROOT>\cutover-staging")
WAYPOINT_SHA256 = (
    "5572EE1F196038071FB5D7B9D7FF271CCB0E19BA722B83BCC1A2B8C0C844F8EB"
)
BASELINE_SCHEMA = 1
CONVERSION_MARKER_SCHEMA = 2
LEGACY_CONVERSION_MARKER_SCHEMAS = frozenset({1})
CONVERSION_MARKER_RELATIVE = "migration-reports/conversion-complete.json"
WORLD_CONVERTER_NAME = "convert_world_nbt.py"
ADVANCEMENT_CONVERTER_NAME = "convert_player_advancements.py"
ADVANCEMENT_POLICY_NAME = "advancement_id_policy_20260813.json"
ADVANCEMENT_SIDECAR_RELATIVE = (
    ".migration-ledger/advancement-unrecognized.v1.jsonl"
)
MAP_BANNER_SIDECAR_RELATIVE = ".migration-ledger/map-banner.v1.jsonl"
LOCAL_CONVERTER_NAMES = (
    WORLD_CONVERTER_NAME,
    ADVANCEMENT_CONVERTER_NAME,
    ADVANCEMENT_POLICY_NAME,
    "convert_create_fluid_nbt.py",
    "convert_villager_region_entities.py",
    "convert_vanilla_saveddata.py",
    "convert_create_saveddata.py",
    "migrate_mineastr_config.py",
    "migrate_mineastr_cache.py",
)
EASYAUTH_CONVERTER = Path(
    r"<AUDIT_ROOT>\XiyusLogin-migration\tools\migrate_easyauth.py"
)
WORLD_CONVERTER_INPUT_KINDS = frozenset(
    {"world-level", "server-properties", "world-player", "world-region-nbt"}
)
NON_WORLD_CONVERTER_INPUT_KINDS = frozenset(
    {"create-tracks", "create-logistics", "mineastr-config", "mineastr-cache", "easyauth"}
)
ADVANCEMENT_INPUT_KIND = "world-advancement"

# Runtime inputs copied before conversion.  Logs, disposable caches and server
# binaries are intentionally excluded; the target NeoForge installation
# supplies them.  Immersive Paintings is the exception: despite its directory
# name, this cache contains the authoritative player-uploaded image bytes.
COPY_DIRECTORIES = (
    "world",
    "config",
    "defaultconfigs",
    "schematics",
    "immersive_paintings_cache",
)
COPY_FILES = (
    "server.properties",
    "whitelist.json",
    "ops.json",
    "banned-players.json",
    "banned-ips.json",
    "usercache.json",
)
LEGACY_DIMENSIONS = ("world_nether", "world_the_end")
AUTH_DATABASE_FILES = ("easyauth.db", "easyauth.db-wal")
VOLATILE_NAMES = {
    "session.lock",
    # Ledger is intentionally replaced by GriefLogger per the migration
    # decision; never copy its SQLite history into the NeoForge runtime.
    "ledger.sqlite",
    "ledger.sqlite-shm",
    "ledger.sqlite-wal",
}

# Deleting any source input is blocked by default.  These inputs remain
# blockers even when ordinary source deletions are explicitly allowed because
# accepting them would make the world unbootable or discard authentication
# state/configuration during an otherwise incremental cutover.
CRITICAL_SOURCE_DELETIONS = {
    "world/level.dat",
    "server.properties",
    "EasyAuth/easyauth.db",
}

DERIVED_TARGETS = {
    "config/mineastr-common.json": ("config/mineastr-common.toml",),
    "EasyAuth/easyauth.db": ("world/xiyus_player_data.json",),
}

VANILLA_SAVEDDATA_PATH_TO_KIND = {
    "world/data/chunks.dat": "chunks",
    "world/DIM-1/data/chunks.dat": "chunks",
    "world/DIM1/data/chunks.dat": "chunks",
    "world/data/WorldUUID.dat": "world_uuid",
    "world/data/world_border.dat": "border",
    "world/DIM-1/data/world_border.dat": "border",
    "world/DIM1/data/world_border.dat": "border",
    "world/data/raids.dat": "raids",
    "world/DIM-1/data/raids.dat": "raids",
    "world/DIM1/data/raids_end.dat": "raids",
    "world/data/scoreboard.dat": "scoreboard",
}
VANILLA_MAP_PATH = re.compile(r"^world/data/map_(0|[1-9][0-9]*)\.dat$")
VANILLA_SAVEDDATA_KINDS = frozenset(
    {*VANILLA_SAVEDDATA_PATH_TO_KIND.values(), "maps"}
)


class SourceChangedError(RuntimeError):
    """The stopped source changed while its refresh transaction was prepared."""


class TransactionRollbackError(RuntimeError):
    """A staging commit failed and could not be rolled back completely."""


def is_volatile_name(name: str) -> bool:
    return name in VOLATILE_NAMES or name.startswith("ledger.sqlite-")


def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def normalized_relative(value: str) -> str:
    """Validate a manifest path before joining it to source or staging."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid empty manifest path: {value!r}")
    relative = PurePosixPath(value)
    normalized = relative.as_posix()
    if (
        relative.is_absolute()
        or normalized != value
        or any(part in {"", ".", ".."} for part in relative.parts)
        or ":" in relative.parts[0]
    ):
        raise ValueError(f"unsafe manifest path: {value!r}")
    return normalized


def safe_join(root: Path, relative: str) -> Path:
    relative = normalized_relative(relative)
    root = root.resolve()
    candidate = root.joinpath(*PurePosixPath(relative).parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manifest path escapes {root}: {relative}") from exc
    return candidate


def stable_file_record(path: Path, source_path: str, target_path: str) -> dict:
    """Hash one file and reject a concurrent in-place source mutation."""
    if path.is_symlink():
        raise ValueError(f"symbolic links are not accepted as migration inputs: {path}")
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    before_signature = (before.st_size, before.st_mtime_ns)
    after_signature = (after.st_size, after.st_mtime_ns)
    if before_signature != after_signature:
        raise SourceChangedError(f"input changed while hashing: {path}")
    source_path = normalized_relative(source_path)
    target_path = normalized_relative(target_path)
    return {
        "source": source_path,
        "target": target_path,
        "kind": classify_input(source_path),
        "bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "sha256": digest,
    }


def classify_input(relative: str) -> str:
    relative = normalized_relative(relative)
    saveddata_kind = VANILLA_SAVEDDATA_PATH_TO_KIND.get(relative)
    if saveddata_kind is not None:
        return f"vanilla-saveddata-{saveddata_kind}"
    if VANILLA_MAP_PATH.fullmatch(relative):
        return "vanilla-saveddata-maps"
    if relative == "world/level.dat":
        return "world-level"
    if relative == "server.properties":
        return "server-properties"
    if relative == "world/data/create_tracks.dat":
        return "create-tracks"
    if relative == "world/data/create_logistics.dat":
        return "create-logistics"
    if relative == "world/data/mineastr_sign_translations.dat":
        return "mineastr-cache"
    if relative == "config/mineastr-common.json":
        return "mineastr-config"
    if relative in {f"EasyAuth/{name}" for name in AUTH_DATABASE_FILES}:
        return "easyauth"

    parts = PurePosixPath(relative).parts
    if len(parts) == 3 and parts[:2] == ("world", "playerdata") and parts[-1].endswith(".dat"):
        return "world-player"
    if (
        len(parts) == 3
        and parts[:2] == ("world", "advancements")
        and re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json",
            parts[-1],
        )
    ):
        return ADVANCEMENT_INPUT_KIND
    world_parts = parts[1:] if parts and parts[0] == "world" else ()
    if (
        len(world_parts) == 2
        and world_parts[0] in {"region", "entities"}
        and world_parts[1].endswith(".mca")
    ) or (
        len(world_parts) == 3
        and world_parts[0] in {"DIM-1", "DIM1"}
        and world_parts[1] in {"region", "entities"}
        and world_parts[2].endswith(".mca")
    ):
        return "world-region-nbt"
    if world_parts and world_parts[-1].endswith(".mca"):
        # convert_world_nbt currently supports only the three vanilla
        # dimensions. Treat every other Anvil tree as an explicit blocker;
        # copying it raw would silently preserve 1.21.11-only NBT.
        known_poi = (
            len(world_parts) == 2 and world_parts[0] == "poi"
        ) or (
            len(world_parts) == 3
            and world_parts[0] in {"DIM-1", "DIM1"}
            and world_parts[1] == "poi"
        )
        if not known_poi:
            return "unsupported-world-region"
    return "raw"


def unsupported_region_inputs(entries: Iterable[dict]) -> list[str]:
    return sorted(
        entry["source"]
        for entry in entries
        if entry.get("kind") == "unsupported-world-region"
    )


def snapshot_digest(entries: Iterable[dict]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item["source"]):
        for key in ("source", "target", "kind", "bytes", "sha256"):
            digest.update(str(entry[key]).encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def ensure_d_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved.drive.upper() != "D:":
        raise ValueError(f"{label} must be on D: (got {resolved})")
    return resolved


def ensure_distinct(source: Path, staging: Path) -> None:
    source = source.resolve()
    staging = staging.resolve()
    if _paths_overlap(source, staging):
        try:
            staging.relative_to(source)
        except ValueError:
            raise ValueError(
                "source-game-dir must not be inside staging-game-dir"
            )
        raise ValueError("staging must not be inside the read-only source directory")


def ensure_outside_source(source: Path, path: Path, label: str) -> None:
    try:
        path.resolve().relative_to(source.resolve())
    except ValueError:
        return
    raise ValueError(f"{label} must not be inside the read-only source directory")


def _paths_overlap(left: Path, right: Path) -> bool:
    """Return whether either path is an ancestor of the other."""
    left = left.resolve()
    right = right.resolve()
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def ensure_target_copy_isolated(
    source: Path,
    staging: Path,
    target: Path,
    mods: Path,
) -> tuple[Path, Path]:
    """Validate a target copy before allowing target-only mutations.

    The sanitizer intentionally edits its arguments.  Requiring the target
    and its ``mods`` directory to be disjoint from both protected roots keeps
    that mutation outside the raw source baseline and refresh transaction.
    """
    source = source.resolve()
    staging = staging.resolve()
    target_input = Path(target)
    mods_input = Path(mods)
    for path, label in (
        (target_input, "target-game-dir"),
        (target_input / "world", "target world"),
        (target_input / "server.properties", "target server.properties"),
        (mods_input, "target mods"),
    ):
        if path.is_symlink():
            raise ValueError(f"{label} must not be a symbolic link: {path}")
    target = target_input.resolve()
    mods = mods_input.resolve()
    if _paths_overlap(target, source):
        raise ValueError("target-game-dir overlaps the read-only source directory")
    if _paths_overlap(target, staging):
        raise ValueError("target-game-dir overlaps the staging directory")
    try:
        mods.relative_to(target)
    except ValueError as exc:
        raise ValueError("target mods directory must be inside target-game-dir") from exc
    # Re-check the resolved children in case a parent component was replaced
    # by a link between the preflight above and this point.
    for path, label in (
        (target, "target-game-dir"),
        (target / "world", "target world"),
        (target / "server.properties", "target server.properties"),
        (mods, "target mods"),
    ):
        if path.is_symlink():
            raise ValueError(f"{label} must not be a symbolic link: {path}")
    if not target.is_dir():
        raise FileNotFoundError(f"target-game-dir is not a directory: {target}")
    if not (target / "world").is_dir():
        raise FileNotFoundError(f"target world is missing: {target / 'world'}")
    if not (target / "server.properties").is_file():
        raise FileNotFoundError(
            f"target server.properties is missing: {target / 'server.properties'}"
        )
    if not mods.is_dir():
        raise FileNotFoundError(f"target mods directory is missing: {mods}")
    return target, mods


def _load_target_resource_sanitizer():
    """Load the single-file sanitizer for both CLI and direct test imports."""
    try:
        from sanitize_target_resources import sanitize

        return sanitize
    except (ImportError, ModuleNotFoundError):
        module_path = Path(__file__).with_name("sanitize_target_resources.py")
        spec = importlib.util.spec_from_file_location(
            "migration_target_resource_sanitizer", module_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load resource sanitizer: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.sanitize


def _target_resource_tree_manifest(
    target: Path, mods: Path, hash_all: bool = False
) -> dict:
    """Capture target-only tree metadata, including the otherwise external mods tree."""
    return {
        "world": tree_summary(target / "world", hash_all=hash_all),
        "mods": tree_summary(mods, hash_all=hash_all),
        "server_properties": (
            {"bytes": (target / "server.properties").stat().st_size,
             "sha256": sha256(target / "server.properties")}
            if (target / "server.properties").is_file()
            else None
        ),
    }


def sanitize_target_copy(
    source: Path,
    staging: Path,
    target: Path,
    mods: Path | None = None,
    *,
    hash_all: bool = False,
) -> dict:
    """Sanitize an assembled target copy while proving protected trees stayed unchanged.

    This function never passes ``source`` or ``staging`` to the sanitizer.  It
    is deliberately separate from ``convert``/``refresh`` because resource
    normalization changes target-only files that are part of neither the raw
    baseline nor the refresh transaction.
    """
    source = source.resolve()
    staging = staging.resolve()
    target = Path(target)
    mods = target / "mods" if mods is None else Path(mods)
    if not source.is_dir():
        raise FileNotFoundError(f"source-game-dir is not a directory: {source}")
    if not staging.is_dir():
        raise FileNotFoundError(f"staging-game-dir is not a directory: {staging}")
    target, mods = ensure_target_copy_isolated(source, staging, target, mods)

    source_before = critical_manifest(source, hash_all=hash_all)
    staging_before = critical_manifest(staging, hash_all=hash_all)
    target_before = _target_resource_tree_manifest(target, mods, hash_all=hash_all)
    sanitizer = _load_target_resource_sanitizer()
    resource_report = sanitizer(
        target / "world",
        target / "server.properties",
        mods,
    )
    if not isinstance(resource_report, dict):
        raise RuntimeError("target resource sanitizer returned a non-object report")
    # A sanitizer report must never smuggle a path outside the target copy.
    for change in resource_report.get("changes", []):
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            raise RuntimeError("target resource sanitizer returned an invalid change record")
        changed_path = Path(change["path"]).resolve()
        try:
            changed_path.relative_to(target)
        except ValueError as exc:
            raise RuntimeError(
                f"target resource sanitizer changed a path outside target copy: {changed_path}"
            ) from exc

    source_after = critical_manifest(source, hash_all=hash_all)
    staging_after = critical_manifest(staging, hash_all=hash_all)
    if source_after != source_before or staging_after != staging_before:
        raise RuntimeError(
            "target resource sanitization changed a protected source/staging tree"
        )
    target_after = _target_resource_tree_manifest(target, mods, hash_all=hash_all)
    return {
        "schema": 1,
        "status": "SANITIZED_TARGET_COPY",
        "target_game_dir": str(target),
        "target_mods_dir": str(mods),
        "resource_sanitization": resource_report,
        "target_manifest_before": target_before,
        "target_manifest_after": target_after,
        "protected_tree_unchanged": True,
        "source_guard_before": source_before,
        "source_guard_after": source_after,
        "staging_guard_before": staging_before,
        "staging_guard_after": staging_after,
    }


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and not is_volatile_name(path.name):
            yield path


def source_input_paths(source: Path) -> list[tuple[str, str, Path]]:
    """Return every immutable source input and its staging destination."""
    records: list[tuple[str, str, Path]] = []
    for name in COPY_DIRECTORIES:
        root = source / name
        for path in iter_files(root):
            relative = path.relative_to(source).as_posix()
            records.append((relative, relative, path))
    for name in LEGACY_DIMENSIONS:
        root = source / name
        for path in iter_files(root):
            source_relative = path.relative_to(source).as_posix()
            target_relative = (
                PurePosixPath("migration-input")
                / "legacy-dimensions"
                / PurePosixPath(source_relative)
            ).as_posix()
            records.append((source_relative, target_relative, path))
    for name in COPY_FILES:
        path = source / name
        if path.is_file():
            records.append((name, name, path))
    for name in AUTH_DATABASE_FILES:
        auth = source / "EasyAuth" / name
        if auth.is_file():
            records.append(
                (
                    f"EasyAuth/{name}",
                    f"migration-input/EasyAuth/{name}",
                    auth,
                )
            )
    return unique_input_paths(records)


def staged_input_paths(staging: Path) -> list[tuple[str, str, Path]]:
    """Reverse the stage mapping so the baseline hashes exact copied bytes."""
    records: list[tuple[str, str, Path]] = []
    for name in COPY_DIRECTORIES:
        root = staging / name
        for path in iter_files(root):
            relative = path.relative_to(staging).as_posix()
            records.append((relative, relative, path))
    for name in LEGACY_DIMENSIONS:
        root = staging / "migration-input" / "legacy-dimensions" / name
        for path in iter_files(root):
            suffix = path.relative_to(root).as_posix()
            source_relative = (PurePosixPath(name) / suffix).as_posix()
            target_relative = path.relative_to(staging).as_posix()
            records.append((source_relative, target_relative, path))
    for name in COPY_FILES:
        path = staging / name
        if path.is_file():
            records.append((name, name, path))
    for name in AUTH_DATABASE_FILES:
        auth = staging / "migration-input" / "EasyAuth" / name
        if auth.is_file():
            records.append(
                (
                    f"EasyAuth/{name}",
                    f"migration-input/EasyAuth/{name}",
                    auth,
                )
            )
    return unique_input_paths(records)


def unique_input_paths(
    records: Iterable[tuple[str, str, Path]],
) -> list[tuple[str, str, Path]]:
    by_source: dict[str, tuple[str, str, Path]] = {}
    by_target: dict[str, str] = {}
    for source_relative, target_relative, path in records:
        source_relative = normalized_relative(source_relative)
        target_relative = normalized_relative(target_relative)
        if source_relative in by_source:
            raise ValueError(f"duplicate source input mapping: {source_relative}")
        if target_relative in by_target:
            raise ValueError(
                f"duplicate target input mapping: {target_relative} from "
                f"{by_target[target_relative]} and {source_relative}"
            )
        by_source[source_relative] = (source_relative, target_relative, path)
        by_target[target_relative] = source_relative
    return [by_source[key] for key in sorted(by_source)]


def input_snapshot(root: Path, records: Iterable[tuple[str, str, Path]]) -> dict:
    entries = [
        stable_file_record(path, source_relative, target_relative)
        for source_relative, target_relative, path in records
    ]
    return {
        "schema": BASELINE_SCHEMA,
        "root": str(root.resolve()),
        "files": len(entries),
        "bytes": sum(entry["bytes"] for entry in entries),
        "snapshot_sha256": snapshot_digest(entries),
        "entries": entries,
    }


def source_input_snapshot(source: Path) -> dict:
    return input_snapshot(source, source_input_paths(source))


def staged_baseline_manifest(source: Path, staging: Path) -> dict:
    snapshot = input_snapshot(staging, staged_input_paths(staging))
    snapshot.update(
        {
            "kind": "staged-raw-source-baseline",
            "source_root": str(source.resolve()),
            "staging_root": str(staging.resolve()),
        }
    )
    return snapshot


def validate_baseline_manifest(value: object, source: Path, staging: Path) -> dict:
    if not isinstance(value, dict) or value.get("schema") != BASELINE_SCHEMA:
        raise ValueError("baseline manifest has an unsupported schema")
    if Path(str(value.get("source_root", ""))).resolve() != source.resolve():
        raise ValueError("baseline source root does not match --source-game-dir")
    if Path(str(value.get("staging_root", ""))).resolve() != staging.resolve():
        raise ValueError("baseline staging root does not match --staging-game-dir")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise ValueError("baseline manifest entries must be a list")
    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("baseline manifest contains a non-object entry")
        source_relative = normalized_relative(entry.get("source"))
        target_relative = normalized_relative(entry.get("target"))
        expected_kind = classify_input(source_relative)
        if entry.get("kind") != expected_kind:
            raise ValueError(f"baseline kind mismatch for {source_relative}")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"baseline SHA-256 is invalid for {source_relative}")
        size = entry.get("bytes")
        if type(size) is not int or size < 0:
            raise ValueError(f"baseline byte size is invalid for {source_relative}")
        validated.append(
            {
                **entry,
                "source": source_relative,
                "target": target_relative,
                "kind": expected_kind,
            }
        )
    unique_input_paths(
        (
            entry["source"],
            entry["target"],
            staging / entry["target"],
        )
        for entry in validated
    )
    if value.get("files") != len(validated):
        raise ValueError("baseline file count does not match its entries")
    if value.get("bytes") != sum(entry["bytes"] for entry in validated):
        raise ValueError("baseline byte count does not match its entries")
    if value.get("snapshot_sha256") != snapshot_digest(validated):
        raise ValueError("baseline snapshot SHA-256 does not match its entries")
    return {**value, "entries": validated}


def compare_snapshots(baseline: dict, current: dict) -> dict:
    before = {entry["source"]: entry for entry in baseline["entries"]}
    after = {entry["source"]: entry for entry in current["entries"]}
    added = []
    modified = []
    deleted = []
    metadata_only = []
    for relative in sorted(set(before) | set(after)):
        old = before.get(relative)
        new = after.get(relative)
        if old is None:
            added.append(new)
        elif new is None:
            deleted.append(old)
        elif old["target"] != new["target"] or old["kind"] != new["kind"]:
            raise ValueError(f"input mapping changed since baseline: {relative}")
        elif old["sha256"] != new["sha256"]:
            modified.append({"before": old, "after": new})
        elif old.get("mtime_ns") != new.get("mtime_ns"):
            metadata_only.append(new)
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "metadata_only": metadata_only,
        "unchanged": len(set(before) & set(after)) - len(modified),
    }


def assert_source_snapshot_stable(source: Path, snapshot: dict) -> None:
    # Rehash every input. NTFS timestamps can remain unchanged across a rapid
    # same-size rewrite, so a metadata-only second pass is not a data-loss
    # barrier. The maintenance window pays this sequential-read cost in return
    # for a defensible stopped-source boundary.
    actual_snapshot = source_input_snapshot(source)
    expected = {entry["source"]: entry for entry in snapshot["entries"]}
    actual = {entry["source"]: entry for entry in actual_snapshot["entries"]}
    if actual_snapshot["snapshot_sha256"] != snapshot["snapshot_sha256"]:
        added = sorted(set(actual) - set(expected))
        deleted = sorted(set(expected) - set(actual))
        changed = sorted(
            key
            for key in set(actual) & set(expected)
            if (
                actual[key]["target"],
                actual[key]["bytes"],
                actual[key]["sha256"],
            )
            != (
                expected[key]["target"],
                expected[key]["bytes"],
                expected[key]["sha256"],
            )
        )
        raise SourceChangedError(
            "source inputs changed after the full-hash snapshot: "
            f"added={added[:10]}, deleted={deleted[:10]}, changed={changed[:10]}"
        )


def probe_session_lock(world: Path) -> dict:
    """Read-only proof that no Minecraft process currently owns session.lock."""
    path = world / "session.lock"
    if not path.exists():
        return {"path": str(path), "status": "ABSENT"}
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"world session lock is not a regular file: {path}")

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        lock_file = kernel32.LockFileEx
        lock_file.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        lock_file.restype = wintypes.BOOL
        unlock_file = kernel32.UnlockFileEx
        unlock_file.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        unlock_file.restype = wintypes.BOOL

        generic_read = 0x80000000
        share_all = 0x00000001 | 0x00000002 | 0x00000004
        open_existing = 3
        normal_file = 0x00000080
        exclusive_immediate = 0x00000002 | 0x00000001
        handle = create_file(
            str(path),
            generic_read,
            share_all,
            None,
            open_existing,
            normal_file,
            None,
        )
        invalid_handle = ctypes.c_void_p(-1).value
        if handle == invalid_handle:
            error = ctypes.get_last_error()
            raise RuntimeError(
                f"cannot open source session.lock for a read-only lock probe: "
                f"WinError {error}"
            )
        overlapped = Overlapped()
        try:
            if not lock_file(
                handle,
                exclusive_immediate,
                0,
                1,
                0,
                ctypes.byref(overlapped),
            ):
                error = ctypes.get_last_error()
                raise RuntimeError(
                    "source world session.lock is held; stop the Fabric server "
                    f"before refresh (WinError {error})"
                )
            if not unlock_file(handle, 0, 1, 0, ctypes.byref(overlapped)):
                error = ctypes.get_last_error()
                raise RuntimeError(
                    f"failed to release the read-only session.lock probe: WinError {error}"
                )
        finally:
            close_handle(handle)
    else:  # pragma: no cover - production cutover is Windows/D:
        import fcntl

        with path.open("rb") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(
                    "source world session.lock is held; stop the server before refresh"
                ) from exc
            finally:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    return {"path": str(path), "status": "UNLOCKED_READ_ONLY_PROBE"}


def tree_summary(root: Path, hash_all: bool = False) -> dict:
    files = 0
    bytes_total = 0
    digest = hashlib.sha256()
    hashed = []
    for path in iter_files(root):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        files += 1
        bytes_total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        if hash_all:
            hashed.append({"path": relative, "sha256": sha256(path), "bytes": size})
    result = {
        "exists": root.exists(),
        "files": files,
        "bytes": bytes_total,
        "metadata_sha256": digest.hexdigest(),
    }
    if hash_all:
        result["files_sha256"] = hashed
    return result


def content_tree_manifest(root: Path) -> dict:
    """Return a deterministic full-content manifest for a dependency tree."""
    records = []
    digest = hashlib.sha256()
    for path in iter_files(root):
        if path.is_symlink():
            raise RuntimeError(f"dependency tree contains a symbolic link: {path}")
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        file_hash = sha256(path)
        record = {"path": relative, "bytes": size, "sha256": file_hash}
        records.append(record)
        for value in (relative, str(size), file_hash):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
    return {
        "exists": root.is_dir(),
        "files": len(records),
        "bytes": sum(record["bytes"] for record in records),
        "content_sha256": digest.hexdigest(),
        "entries": records,
    }


def validate_schematic_tree_copy(source: Path, target: Path) -> dict:
    """Fail closed unless every Create schematic byte reached the target tree."""
    source_root = source / "schematics"
    target_root = target / "schematics"
    source_manifest = content_tree_manifest(source_root)
    target_manifest = content_tree_manifest(target_root)
    if source_manifest != target_manifest:
        source_entries = {
            entry["path"]: entry for entry in source_manifest["entries"]
        }
        target_entries = {
            entry["path"]: entry for entry in target_manifest["entries"]
        }
        missing = sorted(set(source_entries) - set(target_entries))
        extra = sorted(set(target_entries) - set(source_entries))
        mismatched = sorted(
            path
            for path in set(source_entries) & set(target_entries)
            if source_entries[path] != target_entries[path]
        )
        raise RuntimeError(
            "Create schematic tree copy/hash gate failed: "
            f"missing={missing[:10]}, extra={extra[:10]}, "
            f"mismatched={mismatched[:10]}"
        )
    return {
        "status": "MATCH",
        "source": str(source_root.resolve()),
        "target": str(target_root.resolve()),
        "files": source_manifest["files"],
        "bytes": source_manifest["bytes"],
        "content_sha256": source_manifest["content_sha256"],
        "entries": source_manifest["entries"],
    }


def critical_manifest(game_dir: Path, hash_all: bool = False) -> dict:
    files = {}
    for name in COPY_FILES:
        path = game_dir / name
        if path.is_file():
            files[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    for relative in (
        "config/mineastr-common.json",
        "world/data/create_tracks.dat",
        "world/data/create_logistics.dat",
        "world/data/mineastr_sign_translations.dat",
        "EasyAuth/easyauth.db",
    ):
        path = game_dir / relative
        if path.is_file():
            files[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    trees = {
        name: tree_summary(game_dir / name, hash_all=hash_all)
        for name in (*COPY_DIRECTORIES, *LEGACY_DIMENSIONS)
        if (game_dir / name).exists()
    }
    return {"root": str(game_dir), "files": files, "trees": trees}


def excluded_input_manifest(game_dir: Path) -> dict:
    result = {}
    for relative in (
        "world/ledger.sqlite",
        "world/ledger.sqlite-shm",
        "world/ledger.sqlite-wal",
        "EasyAuth/easyauth.db",
        "EasyAuth/easyauth.db-wal",
        "EasyAuth/easyauth.db-shm",
    ):
        path = game_dir / relative
        if path.is_file():
            result[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    return result


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def conversion_marker_path(staging: Path) -> Path:
    return staging / CONVERSION_MARKER_RELATIVE


def converter_fingerprints(tools_dir: Path | None = None) -> dict[str, dict]:
    """Return content identities for converters whose output is marker-bound."""
    root = Path(tools_dir) if tools_dir is not None else Path(__file__).resolve().parent
    paths = {name: root / name for name in LOCAL_CONVERTER_NAMES}
    paths["xiyuslogin/migrate_easyauth.py"] = EASYAUTH_CONVERTER
    fingerprints = {}
    for name, converter in paths.items():
        if not converter.is_file():
            raise RuntimeError(f"required migration converter is missing: {converter}")
        fingerprints[name] = {
            "bytes": converter.stat().st_size,
            "sha256": sha256(converter),
        }
    return fingerprints


def assert_converter_fingerprints_stable(
    expected: dict[str, dict], tools_dir: Path | None = None
) -> None:
    actual = converter_fingerprints(tools_dir)
    if actual != expected:
        raise RuntimeError(
            "migration converter toolchain changed while conversion was running; "
            "discard the transaction and retry"
        )


def is_converter_input(entry: dict) -> bool:
    kind = entry.get("kind")
    return (
        kind in WORLD_CONVERTER_INPUT_KINDS
        or kind in NON_WORLD_CONVERTER_INPUT_KINDS
        or kind == ADVANCEMENT_INPUT_KIND
        or (isinstance(kind, str) and kind.startswith("vanilla-saveddata-"))
    )


def converter_reconciliation_status(
    marker: dict, tools_dir: Path | None = None
) -> dict:
    """Describe whether marker outputs predate the converter now in use."""
    current = converter_fingerprints(tools_dir)
    recorded = marker.get("converter_fingerprints")
    reasons = []
    if marker.get("schema") in LEGACY_CONVERSION_MARKER_SCHEMAS:
        reasons.append("legacy_marker_schema")
    if not isinstance(recorded, dict):
        reasons.append("converter_fingerprints_missing")
    elif recorded != current:
        reasons.append("converter_fingerprint_mismatch")
    return {
        "required": bool(reasons),
        "reasons": reasons,
        "recorded": recorded,
        "current": current,
    }


def derived_output_paths(
    source_entries: Iterable[dict], pending_saveddata: Iterable[str] = ()
) -> list[str]:
    paths = set()
    entries = list(source_entries)
    sources = {entry["source"] for entry in entries}
    pending = set(pending_saveddata)
    unknown_pending = pending - VANILLA_SAVEDDATA_KINDS
    if unknown_pending:
        raise RuntimeError(f"unknown pending SavedData kinds: {sorted(unknown_pending)}")
    for relative in (
        "world/data/create_tracks.dat",
        "world/data/create_logistics.dat",
        "world/data/mineastr_sign_translations.dat",
    ):
        if relative in sources:
            paths.add(relative)
    if "config/mineastr-common.json" in sources:
        paths.add("config/mineastr-common.toml")
    if "EasyAuth/easyauth.db" in sources:
        paths.add("world/xiyus_player_data.json")
    advancement_paths = {
        entry["source"]
        for entry in entries
        if entry.get("kind") == ADVANCEMENT_INPUT_KIND
    }
    if advancement_paths:
        paths.update(advancement_paths)
        paths.add(ADVANCEMENT_SIDECAR_RELATIVE)
    for source_path, kind in VANILLA_SAVEDDATA_PATH_TO_KIND.items():
        if source_path not in sources or kind in pending:
            continue
        if kind == "border":
            paths.add("world/level.dat")
        else:
            paths.add(source_path)
    if "maps" not in pending:
        paths.update(
            source
            for source in sources
            if VANILLA_MAP_PATH.fullmatch(source)
        )
        if any(VANILLA_MAP_PATH.fullmatch(source) for source in sources):
            paths.add(MAP_BANNER_SIDECAR_RELATIVE)
    return sorted(paths)


def make_conversion_marker(
    source: Path,
    staging: Path,
    baseline: dict,
    report_path: Path,
    output_root: Path,
    replacement_paths: dict[str, Path] | None = None,
    pending_saveddata: Iterable[str] = (),
    tools_dir: Path | None = None,
    converter_fingerprints_value: dict[str, dict] | None = None,
) -> dict:
    replacements = replacement_paths or {}
    pending = sorted(set(pending_saveddata))
    outputs = {}
    for relative in derived_output_paths(baseline["entries"], pending):
        path = replacements.get(relative, safe_join(output_root, relative))
        if not path.is_file():
            raise RuntimeError(f"required conversion output is missing: {path}")
        outputs[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    return {
        "schema": CONVERSION_MARKER_SCHEMA,
        "status": "CONVERTED_STAGING",
        "source_root": str(source.resolve()),
        "staging_root": str(staging.resolve()),
        "baseline_snapshot_sha256": baseline.get("snapshot_sha256"),
        "conversion_report": str(report_path.resolve()),
        "conversion_report_sha256": sha256(report_path)
        if report_path.is_file()
        else None,
        "converter_fingerprints": (
            converter_fingerprints(tools_dir)
            if converter_fingerprints_value is None
            else converter_fingerprints_value
        ),
        "pending_saveddata": pending,
        "outputs": outputs,
    }


def validate_conversion_marker(
    marker_path: Path,
    source: Path,
    staging: Path,
    baseline: dict,
    tools_dir: Path | None = None,
    allow_converter_reconciliation: bool = False,
) -> dict:
    if not marker_path.is_file():
        raise RuntimeError(
            "full conversion completion marker is missing; rerun convert on a "
            "fresh staging copy before refresh"
        )
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    if not isinstance(marker, dict) or marker.get("schema") not in {
        CONVERSION_MARKER_SCHEMA,
        *LEGACY_CONVERSION_MARKER_SCHEMAS,
    }:
        raise RuntimeError("conversion completion marker has an unsupported schema")
    if marker.get("status") != "CONVERTED_STAGING":
        raise RuntimeError("conversion completion marker is not successful")
    if Path(str(marker.get("source_root", ""))).resolve() != source.resolve():
        raise RuntimeError("conversion marker source root does not match refresh source")
    if Path(str(marker.get("staging_root", ""))).resolve() != staging.resolve():
        raise RuntimeError("conversion marker staging root does not match refresh staging")
    baseline_digest = marker.get("baseline_snapshot_sha256")
    if (
        not isinstance(baseline_digest, str)
        or len(baseline_digest) != 64
        or any(value not in "0123456789abcdefABCDEF" for value in baseline_digest)
        or baseline_digest != baseline.get("snapshot_sha256")
    ):
        raise RuntimeError(
            "conversion marker does not correspond to the current raw-input baseline"
        )
    report_path_value = marker.get("conversion_report")
    report_hash = marker.get("conversion_report_sha256")
    if not isinstance(report_path_value, str) or not report_path_value:
        raise RuntimeError("conversion marker has no conversion report path")
    report_path = Path(report_path_value).resolve()
    if not report_path.is_file():
        raise RuntimeError(f"conversion marker report is missing: {report_path}")
    if (
        not isinstance(report_hash, str)
        or len(report_hash) != 64
        or any(value not in "0123456789abcdefABCDEF" for value in report_hash)
        or sha256(report_path).lower() != report_hash.lower()
    ):
        raise RuntimeError("conversion marker report hash does not match its file")
    outputs = marker.get("outputs")
    if not isinstance(outputs, dict):
        raise RuntimeError("conversion marker has no output integrity manifest")
    if "pending_saveddata" not in marker:
        raise RuntimeError("conversion marker lacks the pending SavedData field")
    pending_saveddata = marker.get("pending_saveddata")
    if (
        not isinstance(pending_saveddata, list)
        or any(not isinstance(value, str) for value in pending_saveddata)
        or set(pending_saveddata) - VANILLA_SAVEDDATA_KINDS
    ):
        raise RuntimeError("conversion marker has invalid pending SavedData")
    expected_outputs = set(
        derived_output_paths(baseline["entries"], pending_saveddata)
    )
    if set(outputs) != expected_outputs:
        raise RuntimeError(
            "conversion marker output set does not match the baseline: "
            f"missing={sorted(expected_outputs - set(outputs))}, "
            f"extra={sorted(set(outputs) - expected_outputs)}"
        )
    for relative, expected in outputs.items():
        normalized = normalized_relative(relative)
        expected_hash = expected.get("sha256") if isinstance(expected, dict) else None
        expected_bytes = expected.get("bytes") if isinstance(expected, dict) else None
        if (
            not isinstance(expected, dict)
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(value not in "0123456789abcdefABCDEF" for value in expected_hash)
            or type(expected_bytes) is not int
            or expected_bytes < 0
        ):
            raise RuntimeError(f"conversion marker output record is invalid: {relative}")
        path = safe_join(staging, normalized)
        if (
            not path.is_file()
            or path.stat().st_size != expected_bytes
            or sha256(path).lower() != expected_hash.lower()
        ):
            raise RuntimeError(f"conversion output integrity check failed: {normalized}")
    reconciliation = converter_reconciliation_status(marker, tools_dir)
    if reconciliation["required"] and not allow_converter_reconciliation:
        raise RuntimeError(
            "conversion marker converter fingerprint is stale or missing; run "
            "refresh to transactionally replay all converter inputs before verify: "
            + ", ".join(reconciliation["reasons"])
        )
    return marker


def validate_final_conversion_gate(
    marker_path: Path, source: Path, staging: Path, baseline_path: Path
) -> tuple[dict, dict]:
    """Validate that a staging tree is complete, current, and deployable.

    A preheated tree intentionally carries a marker with pending SavedData.  It
    is useful for preparation, but must never pass the final read-only gate.
    Rechecking the raw-input snapshot here also prevents a stale marker from
    being accepted after the source changed.
    """
    if not baseline_path.is_file():
        raise RuntimeError(
            "final verification requires the full-hash baseline written by stage"
        )
    baseline = validate_baseline_manifest(
        json.loads(baseline_path.read_text(encoding="utf-8")), source, staging
    )
    marker = validate_conversion_marker(marker_path, source, staging, baseline)
    pending = marker.get("pending_saveddata", [])
    if pending:
        raise RuntimeError(
            "conversion is preheated but not final; pending SavedData: "
            + ", ".join(sorted(pending))
        )
    current = source_input_snapshot(source)
    delta = compare_snapshots(baseline, current)
    if delta["added"] or delta["modified"] or delta["deleted"]:
        raise RuntimeError(
            "source changed after staging; run refresh before final verification: "
            f"added={len(delta['added'])}, modified={len(delta['modified'])}, "
            f"deleted={len(delta['deleted'])}"
        )
    verify_unchanged_staging_inputs(staging, baseline["entries"], delta)
    return baseline, marker


def copy_filtered(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite staging path: {target}")
    target.mkdir(parents=True)
    for name in COPY_DIRECTORIES:
        src = source / name
        if not src.exists():
            continue

        def ignore(directory: str, names: list[str]) -> set[str]:
            return {name for name in names if is_volatile_name(name)}

        shutil.copytree(src, target / name, copy_function=shutil.copy2, ignore=ignore)
    # Keep legacy dimension roots outside the runtime world.  The canonical
    # source world already contains DIM-1/DIM1; retaining these inputs makes
    # the cutover manifest auditable without accidentally loading duplicates.
    legacy_root = target / "migration-input" / "legacy-dimensions"
    for name in LEGACY_DIMENSIONS:
        src = source / name
        if src.exists():
            shutil.copytree(src, legacy_root / name, copy_function=shutil.copy2)
    for name in COPY_FILES:
        src = source / name
        if src.is_file():
            shutil.copy2(src, target / name)
    # EasyAuth is an input to the one-way account converter, never a runtime
    # database in the NeoForge target.
    for name in AUTH_DATABASE_FILES:
        db = source / "EasyAuth" / name
        if db.is_file():
            destination = target / "migration-input" / "EasyAuth" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db, destination)


def verify_unchanged_staging_inputs(
    staging: Path, baseline_entries: list[dict], delta: dict
) -> None:
    """A missing unchanged target means the prepared copy is not trustworthy."""
    changed = {
        record["after"]["source"] for record in delta["modified"]
    } | {record["source"] for record in delta["added"]} | {
        record["source"] for record in delta["deleted"]
    }
    missing = []
    invalid = []
    passthrough_mismatches = []
    for entry in baseline_entries:
        if entry["source"] in changed:
            continue
        target = safe_join(staging, entry["target"])
        if not target.exists():
            missing.append(entry["target"])
        elif target.is_symlink() or not target.is_file():
            invalid.append(entry["target"])
        elif entry["kind"] in {"raw", "mineastr-config", "easyauth"}:
            actual_hash = sha256(target)
            if actual_hash != entry["sha256"]:
                passthrough_mismatches.append(
                    {
                        "target": entry["target"],
                        "expected": entry["sha256"],
                        "actual": actual_hash,
                    }
                )
    if missing or invalid or passthrough_mismatches:
        raise RuntimeError(
            "staging no longer contains every unchanged baseline input: "
            f"missing={missing[:10]}, invalid={invalid[:10]}, "
            f"passthrough_mismatches={passthrough_mismatches[:10]}"
        )


def copy_snapshot_entry(source: Path, prepared: Path, entry: dict) -> Path:
    source_path = safe_join(source, entry["source"])
    target_path = safe_join(prepared, entry["target"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)
    copied_hash = sha256(target_path)
    if copied_hash != entry["sha256"] or target_path.stat().st_size != entry["bytes"]:
        raise SourceChangedError(
            f"source changed while copying {entry['source']}: "
            f"snapshot={entry['sha256']}, copied={copied_hash}"
        )
    return target_path


def add_replacement(
    replacements: dict[str, Path], relative: str, path: Path, producer: str
) -> None:
    relative = normalized_relative(relative)
    existing = replacements.get(relative)
    if existing is not None and existing.resolve() != path.resolve():
        raise RuntimeError(
            f"refresh target collision at {relative}: existing={existing}, "
            f"producer={producer}, replacement={path}"
        )
    replacements[relative] = path


def require_free_derived_target(
    replacements: dict[str, Path], relative: str, producer: str
) -> None:
    relative = normalized_relative(relative)
    if relative in replacements:
        raise RuntimeError(
            f"derived output {relative} from {producer} conflicts with a changed "
            "source input; refusing to discard either value"
        )


def require_target_not_owned_by_source(
    entries: Iterable[dict], relative: str, producer: str
) -> None:
    relative = normalized_relative(relative)
    owners = sorted(entry["source"] for entry in entries if entry["target"] == relative)
    if owners:
        raise RuntimeError(
            f"derived output {relative} from {producer} conflicts with source "
            f"input(s) {owners}; refusing to overwrite source-owned content"
        )


def region_selector(entry: dict) -> str | None:
    if entry["kind"] != "world-region-nbt":
        return None
    prefix = "world/"
    if not entry["target"].startswith(prefix):
        raise ValueError(f"world region target has an unexpected path: {entry['target']}")
    return entry["target"][len(prefix):]


def copy_or_link(source: str, target: str) -> str:
    try:
        os.link(source, target)
        return target
    except OSError:
        return shutil.copy2(source, target)


def build_validation_target(
    staging: Path,
    prepared: Path,
    validation: Path,
    changed_entries: list[dict],
    deleted_entries: list[dict],
    waypoint_jar: Path,
) -> None:
    """Compose the post-refresh schematic/mod view without touching staging."""
    source_schematics = staging / "schematics"
    target_schematics = validation / "schematics"
    if source_schematics.is_dir():
        shutil.copytree(
            source_schematics,
            target_schematics,
            copy_function=copy_or_link,
        )
    else:
        target_schematics.mkdir(parents=True)
    for entry in changed_entries:
        if not entry["target"].startswith("schematics/"):
            continue
        source_path = safe_join(prepared, entry["target"])
        target_path = safe_join(validation, entry["target"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Unlink the hard-linked old view first. copy2 opens an existing file
        # in place and would otherwise overwrite the staging inode before the
        # refresh transaction has committed.
        target_path.unlink(missing_ok=True)
        shutil.copy2(source_path, target_path)
    for entry in deleted_entries:
        if not entry["target"].startswith("schematics/"):
            continue
        target_path = safe_join(validation, entry["target"])
        target_path.unlink(missing_ok=True)
    mods = validation / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    shutil.copy2(waypoint_jar, mods / waypoint_jar.name)


def serialized_journal(journal: list[dict]) -> list[dict]:
    return [
        {
            "target": record["relative"],
            "had_original": record["had_original"],
            "original_moved": record.get("original_moved", False),
            "installed": record["installed"],
            "deletion": record["deletion"],
            "state": record.get("state", "UNKNOWN"),
        }
        for record in journal
    ]


def rollback_transaction(journal: list[dict], discard_root: Path) -> None:
    errors = []
    for record in reversed(journal):
        target = record["target"]
        backup = record["backup"]
        try:
            if record["installed"]:
                if not target.is_file():
                    raise FileNotFoundError(f"installed target disappeared: {target}")
                discard = safe_join(discard_root, record["relative"])
                discard.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, discard)
            if record.get("original_moved", False):
                if not backup.is_file():
                    raise FileNotFoundError(f"transaction backup disappeared: {backup}")
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, target)
            elif not record["had_original"] and target.exists():
                raise RuntimeError(f"unexpected target remains after rollback: {target}")
        except Exception as exc:  # keep attempting the remaining rollback entries
            errors.append(f"{record['relative']}: {type(exc).__name__}: {exc}")
    if errors:
        raise TransactionRollbackError(
            "staging rollback was incomplete; retain the transaction directory: "
            + "; ".join(errors[:10])
        )


def update_transaction_journal_status(
    journal_path: Path, status: str, error: str | None = None
) -> None:
    if not journal_path.is_file():
        return
    value = {"schema": 1, "status": status}
    if error is not None:
        value["error"] = error
    atomic_json(transaction_state_path(journal_path), value)


def transaction_state_path(journal_path: Path) -> Path:
    return journal_path.with_name(journal_path.stem + "-state.json")


def orphan_refresh_transactions(staging: Path) -> list[dict]:
    result = []
    prefix = f".{staging.name}-refresh-"
    for path in sorted(staging.parent.glob(prefix + "*")):
        if not path.is_dir():
            continue
        journal = path / "transaction-journal.json"
        state_path = transaction_state_path(journal)
        status = "MISSING_JOURNAL"
        if journal.is_file():
            try:
                value_path = state_path if state_path.is_file() else journal
                value = json.loads(value_path.read_text(encoding="utf-8"))
                status = str(value.get("status", "UNKNOWN"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                status = f"UNREADABLE_JOURNAL: {type(exc).__name__}: {exc}"
        result.append(
            {
                "path": str(path.resolve()),
                "journal": str(journal),
                "state": str(state_path),
                "status": status,
            }
        )
    return result


def commit_transaction(
    staging: Path,
    replacements: dict[str, Path],
    deletions: set[str],
    backup_root: Path,
    discard_root: Path,
    journal_path: Path | None = None,
) -> list[dict]:
    overlap = set(replacements) & deletions
    if overlap:
        raise ValueError(f"replacement/deletion transaction overlap: {sorted(overlap)[:10]}")
    operations = sorted(set(replacements) | deletions)
    journal: list[dict] = []
    for relative in operations:
        target = safe_join(staging, relative)
        backup = safe_join(backup_root, relative)
        prepared = replacements.get(relative)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeError(f"refusing to replace a non-regular target: {target}")
        if prepared is not None and not prepared.is_file():
            raise FileNotFoundError(f"prepared replacement is missing: {prepared}")
        journal.append(
            {
                "relative": relative,
                "target": target,
                "backup": backup,
                "prepared": prepared,
                "had_original": target.is_file(),
                "original_moved": False,
                "installed": False,
                "deletion": relative in deletions,
                "state": "PLANNED",
            }
        )

    def persist(status: str) -> None:
        if journal_path is None:
            return
        if not journal_path.exists():
            atomic_json(
                journal_path,
                {
                    "schema": 1,
                    "status": "PREPARED",
                    "staging": str(staging.resolve()),
                    "backup_root": str(backup_root.resolve()),
                    "discard_root": str(discard_root.resolve()),
                    "operations": [
                        {
                            **record,
                            "target": str(record["target"]),
                            "backup": str(record["backup"]),
                            "prepared": str(record["prepared"])
                            if record["prepared"] is not None
                            else None,
                        }
                        for record in journal
                    ],
                },
            )
        active = next(
            (record for record in reversed(journal) if record["state"] != "PLANNED"),
            None,
        )
        atomic_json(
            transaction_state_path(journal_path),
            {
                "schema": 1,
                "status": status,
                "operation": active["relative"] if active is not None else None,
                "operation_state": active["state"] if active is not None else None,
                "completed_operations": sum(
                    record["state"]
                    in {"REPLACEMENT_INSTALLED", "DELETION_INSTALLED", "ROLLED_BACK"}
                    for record in journal
                ),
                "total_operations": len(journal),
            },
        )

    persist("PREPARED")
    try:
        for record in journal:
            target = record["target"]
            backup = record["backup"]
            prepared = record["prepared"]
            if record["had_original"]:
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, backup)
                record["original_moved"] = True
                record["state"] = "ORIGINAL_MOVED"
                persist("APPLYING")
            if prepared is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(prepared, target)
                record["installed"] = True
                record["state"] = "REPLACEMENT_INSTALLED"
                persist("APPLYING")
            else:
                record["state"] = "DELETION_INSTALLED"
                persist("APPLYING")
        persist("APPLIED")
    except Exception as exc:
        try:
            rollback_transaction(journal, discard_root)
            for record in journal:
                record["state"] = "ROLLED_BACK"
            persist("ROLLED_BACK")
        except TransactionRollbackError as rollback_exc:
            raise TransactionRollbackError(
                f"commit failed ({type(exc).__name__}: {exc}); {rollback_exc}"
            ) from exc
        raise RuntimeError(
            f"staging commit failed and was rolled back: {type(exc).__name__}: {exc}"
        ) from exc
    return journal


def snapshot_easyauth_database(
    database: Path, output: Path, report_path: Path
) -> dict:
    """Create and verify a consistent SQLite backup from D-drive copied inputs."""
    if not database.is_file():
        raise FileNotFoundError(f"EasyAuth database is missing: {database}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite SQLite snapshot: {output}")
    input_files = {}
    for suffix in ("", "-wal"):
        path = Path(str(database) + suffix)
        if path.is_file():
            input_files[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }

    uri = "file:" + database.resolve().as_posix() + "?mode=ro"
    source_connection = sqlite3.connect(uri, uri=True)
    try:
        source_connection.execute("pragma query_only=on")
        source_integrity = [
            row[0] for row in source_connection.execute("pragma integrity_check")
        ]
        if source_integrity != ["ok"]:
            raise RuntimeError(
                f"EasyAuth copied database failed integrity_check: {source_integrity[:10]}"
            )
        destination_connection = sqlite3.connect(str(output))
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
    finally:
        source_connection.close()

    verification = sqlite3.connect(f"file:{output.resolve().as_posix()}?mode=ro", uri=True)
    try:
        output_integrity = [
            row[0] for row in verification.execute("pragma integrity_check")
        ]
        if output_integrity != ["ok"]:
            raise RuntimeError(
                f"EasyAuth snapshot failed integrity_check: {output_integrity[:10]}"
            )
        table = verification.execute(
            "select count(*) from sqlite_master where type='table' and name='easyauth'"
        ).fetchone()[0]
        if table != 1:
            raise RuntimeError("EasyAuth snapshot does not contain the easyauth table")
        records = verification.execute("select count(*) from easyauth").fetchone()[0]
    finally:
        verification.close()

    report = {
        "schema": 1,
        "source_copy": str(database),
        "source_copy_files": input_files,
        "source_integrity_check": source_integrity,
        "snapshot": str(output),
        "snapshot_bytes": output.stat().st_size,
        "snapshot_sha256": sha256(output),
        "snapshot_integrity_check": output_integrity,
        "records": records,
    }
    atomic_json(report_path, report)
    return report


def run_tool(label: str, args: list[str], env: dict[str, str], report: list[dict]) -> None:
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, *args],
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    tails = {"stdout": deque(maxlen=4000), "stderr": deque(maxlen=4000)}

    def forward(stream, target, tail):
        for line in iter(stream.readline, ""):
            print(line, end="", file=target, flush=True)
            tail.extend(line)
        stream.close()

    stdout_thread = threading.Thread(
        target=forward,
        args=(process.stdout, sys.stdout, tails["stdout"]),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=forward,
        args=(process.stderr, sys.stderr, tails["stderr"]),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    record = {
        "label": label,
        "args": args,
        "returncode": returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": "".join(tails["stdout"]),
        "stderr_tail": "".join(tails["stderr"]),
    }
    report.append(record)
    if returncode != 0:
        raise RuntimeError(f"{label} failed with exit {returncode}")


def replace_from_temp(path: Path) -> None:
    temporary = path.with_name(path.name + ".migration.tmp")
    if not temporary.is_file():
        raise FileNotFoundError(temporary)
    os.replace(temporary, path)


def deploy_waypoint_runtime(staging: Path, jar: Path, expected_sha256: str) -> Path:
    jar = jar.resolve()
    if not jar.is_file():
        raise FileNotFoundError(f"waypoint/fire JAR is missing: {jar}")
    actual = sha256(jar)
    if actual.lower() != expected_sha256.strip().lower():
        raise ValueError(
            f"waypoint/fire JAR hash mismatch: expected {expected_sha256}, found {actual}"
        )
    mods = staging / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    deployed = mods / jar.name
    if deployed.exists() and sha256(deployed).lower() != actual.lower():
        raise ValueError(f"refusing to replace a different deployed waypoint/fire JAR: {deployed}")
    if not deployed.exists():
        shutil.copy2(jar, deployed)
    return deployed


def convert_saveddata(
    source_file: Path,
    target_file: Path,
    kind: str,
    tools_dir: Path,
    env: dict[str, str],
    commands: list[dict],
    report_dir: Path,
    source_game_dir: Path,
    target_game_dir: Path,
) -> None:
    if not source_file.is_file():
        return
    temporary = target_file.with_name(target_file.name + ".migration.tmp")
    if temporary.exists():
        temporary.unlink()
    run_tool(
        f"create-{kind}",
        [
            str(tools_dir / "convert_create_saveddata.py"),
            str(source_file),
            "--kind",
            kind,
            "--output",
            str(temporary),
            "--report",
            str(report_dir / f"create-{kind}.json"),
            "--source-game-dir",
            str(source_game_dir),
            "--target-game-dir",
            str(target_game_dir),
        ],
        env,
        commands,
    )
    replace_from_temp(target_file)


def vanilla_saveddata_kinds_for_sources(sources: Iterable[str]) -> set[str]:
    source_set = set(sources)
    kinds = {
        VANILLA_SAVEDDATA_PATH_TO_KIND[source]
        for source in source_set
        if source in VANILLA_SAVEDDATA_PATH_TO_KIND
    }
    if any(VANILLA_MAP_PATH.fullmatch(source) for source in source_set):
        kinds.add("maps")
    return kinds


def vanilla_saveddata_output_paths(source: Path, kinds: Iterable[str]) -> list[str]:
    selected = set(kinds)
    unknown = selected - VANILLA_SAVEDDATA_KINDS
    if unknown:
        raise RuntimeError(f"unknown vanilla SavedData kinds: {sorted(unknown)}")
    paths = set()
    for relative, kind in VANILLA_SAVEDDATA_PATH_TO_KIND.items():
        if kind not in selected or not safe_join(source, relative).is_file():
            continue
        paths.add("world/level.dat" if kind == "border" else relative)
    if "maps" in selected:
        for path in sorted((source / "world" / "data").glob("map_*.dat")):
            relative = path.relative_to(source).as_posix()
            if not VANILLA_MAP_PATH.fullmatch(relative):
                raise RuntimeError(f"invalid map SavedData path: {relative}")
            paths.add(relative)
        paths.add(MAP_BANNER_SIDECAR_RELATIVE)
    return sorted(paths)


def convert_vanilla_saveddata(
    source: Path,
    target_world: Path,
    kinds: Iterable[str],
    tools_dir: Path,
    env: dict[str, str],
    commands: list[dict],
    report_path: Path,
    label: str,
) -> list[str]:
    selected = sorted(set(kinds))
    if not selected:
        return []
    arguments = [
        str(tools_dir / "convert_vanilla_saveddata.py"),
        "--source-world",
        str(source / "world"),
        "--target-world",
        str(target_world),
        "--report",
        str(report_path),
    ]
    for kind in selected:
        arguments.extend(("--only", kind))
    run_tool(label, arguments, env, commands)
    return vanilla_saveddata_output_paths(source, selected)


def convert_player_advancements(
    source: Path,
    target: Path,
    tools_dir: Path,
    env: dict[str, str],
    commands: list[dict],
    report_path: Path,
    label: str,
    *,
    dry_run: bool = False,
) -> list[str]:
    arguments = [
        str(tools_dir / ADVANCEMENT_CONVERTER_NAME),
        "--source-game-dir",
        str(source),
        "--target-game-dir",
        str(target),
        "--policy",
        str(tools_dir / ADVANCEMENT_POLICY_NAME),
        "--report",
        str(report_path),
    ]
    if dry_run:
        arguments.append("--dry-run")
    run_tool(label, arguments, env, commands)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("status") not in {
        "CONVERTED",
        "ALREADY_TARGET",
        "WOULD_CONVERT",
        "DRY_RUN_ALREADY_TARGET",
    }:
        raise RuntimeError(f"advancement converter report is invalid: {report_path}")
    paths = []
    target_root = target.resolve()
    for output in report.get("outputs", []):
        if not isinstance(output, dict) or not isinstance(output.get("path"), str):
            raise RuntimeError(f"advancement converter output record is invalid: {report_path}")
        output_path = Path(output["path"]).resolve()
        try:
            relative = output_path.relative_to(target_root).as_posix()
        except ValueError as exc:
            raise RuntimeError(
                f"advancement converter output escaped its target: {output_path}"
            ) from exc
        paths.append(normalized_relative(relative))
    return sorted(set(paths))


def prepare_refresh_transaction(
    source: Path,
    staging: Path,
    transaction_root: Path,
    current: dict,
    delta: dict,
    tools_dir: Path,
    env: dict[str, str],
    commands: list[dict],
    report_dir: Path,
    waypoint_jar: Path,
    waypoint_sha256: str,
    require_functional_schematics: bool,
    pending_saveddata: Iterable[str] = (),
    reconcile_converters: bool = False,
    world_workers: int = 1,
) -> tuple[dict[str, Path], set[str], dict]:
    prepared = transaction_root / "prepared"
    prepared.mkdir(parents=True)
    changed_entries = list(delta["added"]) + [
        record["after"] for record in delta["modified"]
    ]
    deleted_entries = list(delta["deleted"])
    reconciliation_entries = (
        [
            entry
            for entry in current["entries"]
            if is_converter_input(entry)
        ]
        if reconcile_converters
        else []
    )
    if reconcile_converters and not reconciliation_entries:
        raise RuntimeError(
            "converter reconciliation was required but the source snapshot has "
            "no converter inputs"
        )
    transaction_entries_by_source = {
        entry["source"]: entry
        for entry in (*changed_entries, *reconciliation_entries)
    }
    transaction_entries = [
        transaction_entries_by_source[key]
        for key in sorted(transaction_entries_by_source)
    ]
    replacements: dict[str, Path] = {}
    deletions = {entry["target"] for entry in deleted_entries}
    for entry in deleted_entries:
        deletions.update(DERIVED_TARGETS.get(entry["source"], ()))
    for entry in transaction_entries:
        add_replacement(
            replacements,
            entry["target"],
            copy_snapshot_entry(source, prepared, entry),
            f"source input {entry['source']}",
        )

    current_by_source = {entry["source"]: entry for entry in current["entries"]}
    changed_sources = {entry["source"] for entry in changed_entries}
    effective_changed_sources = changed_sources | {
        entry["source"] for entry in reconciliation_entries
    }
    deleted_sources = {entry["source"] for entry in deleted_entries}
    current_target_owners = {
        entry["target"]: entry["source"] for entry in current["entries"]
    }
    deletion_collisions = {
        target: current_target_owners[target]
        for target in deletions
        if target in current_target_owners
    }
    if deletion_collisions:
        raise RuntimeError(
            "derived deletion conflicts with current source-owned targets: "
            f"{deletion_collisions}"
        )
    world_conversion_entries = [
        entry
        for entry in (
            reconciliation_entries if reconcile_converters else changed_entries
        )
        if entry["kind"] in WORLD_CONVERTER_INPUT_KINDS
    ]
    changed_kinds = {entry["kind"] for entry in changed_entries}
    world_kinds = {"world-level", "world-player", "world-region-nbt"}
    world_conversion_needed = bool(world_conversion_entries) or bool(
        changed_kinds & world_kinds
    ) or ("server.properties" in changed_sources)
    selected_regions = sorted(
        selector
        for selector in (region_selector(entry) for entry in world_conversion_entries)
        if selector is not None
    )
    selected_vanilla_saveddata = vanilla_saveddata_kinds_for_sources(
        effective_changed_sources
    ) | set(pending_saveddata)
    advancement_entries = [
        entry
        for entry in current["entries"]
        if entry.get("kind") == ADVANCEMENT_INPUT_KIND
    ]
    advancement_conversion_needed = reconcile_converters or any(
        entry.get("kind") == ADVANCEMENT_INPUT_KIND
        for entry in (*changed_entries, *deleted_entries)
    )

    if world_conversion_needed:
        level_entry = current_by_source.get("world/level.dat")
        if level_entry is None:
            raise RuntimeError("incremental NBT conversion requires source world/level.dat")
        level_target = safe_join(prepared, level_entry["target"])
        if not level_target.is_file():
            copy_snapshot_entry(source, prepared, level_entry)

        properties_target = prepared / "server.properties"
        if not properties_target.is_file():
            staging_properties = staging / "server.properties"
            if not staging_properties.is_file():
                raise RuntimeError(
                    "incremental NBT conversion requires staging server.properties"
                )
            shutil.copy2(staging_properties, properties_target)

        deployed_waypoint = staging / "mods" / waypoint_jar.name
        if not deployed_waypoint.is_file():
            raise RuntimeError(
                "incremental refresh requires the audited waypoint/fire JAR to "
                f"already be deployed: {deployed_waypoint}"
            )
        deployed_hash = sha256(deployed_waypoint)
        if deployed_hash.lower() != waypoint_sha256.lower():
            raise RuntimeError(
                "deployed waypoint/fire JAR hash changed before refresh: "
                f"expected {waypoint_sha256}, found {deployed_hash}"
            )

        validation_target = transaction_root / "validation-target"
        build_validation_target(
            staging,
            prepared,
            validation_target,
            changed_entries,
            deleted_entries,
            deployed_waypoint,
        )
        only_region_args = [
            value
            for selector in selected_regions
            for value in ("--only-region", selector)
        ]
        run_tool(
            "world-refresh-convert",
            [
                str(tools_dir / "convert_world_nbt.py"),
                "convert",
                "--world",
                str(prepared / "world"),
                "--report",
                str(report_dir / "world-refresh-convert.json"),
                "--source-game-dir",
                str(source),
                "--target-game-dir",
                str(validation_target),
                "--waypoint-fire-compat-jar",
                str(waypoint_jar),
                "--waypoint-fire-compat-sha256",
                waypoint_sha256,
                "--workers",
                str(world_workers),
                *only_region_args,
            ]
            + (
                ["--require-functional-schematics"]
                if require_functional_schematics
                else []
            ),
            env,
            commands,
        )
        # Raw changed players/regions/level.dat were converted in place.  A
        # level.dat conversion can also change server.properties; commit that
        # paired output only when either source input changed.
        if (
            reconcile_converters
            or
            "world/level.dat" in changed_sources
            or "server.properties" in changed_sources
        ):
            add_replacement(
                replacements,
                "server.properties",
                properties_target,
                "world level/game-rule conversion",
            )

    if selected_vanilla_saveddata:
        if "border" in selected_vanilla_saveddata:
            prepared_level = prepared / "world" / "level.dat"
            if not prepared_level.is_file():
                staging_level = staging / "world" / "level.dat"
                if not staging_level.is_file():
                    raise RuntimeError(
                        "vanilla SavedData border conversion requires staging level.dat"
                    )
                prepared_level.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staging_level, prepared_level)
        saveddata_outputs = convert_vanilla_saveddata(
            source,
            prepared / "world",
            selected_vanilla_saveddata,
            tools_dir,
            env,
            commands,
            report_dir / "vanilla-saveddata-refresh.json",
            "vanilla-saveddata-refresh",
        )
        for relative in saveddata_outputs:
            add_replacement(
                replacements,
                relative,
                safe_join(prepared, relative),
                "vanilla SavedData migration",
            )

    if advancement_conversion_needed:
        # The converter builds one deterministic full-server sidecar, so a
        # changed/deleted player requires the complete current advancement set
        # in the isolated transaction overlay. This is small JSON data, not a
        # world copy, and keeps the commit atomic with the player files.
        for entry in advancement_entries:
            prepared_path = safe_join(prepared, entry["target"])
            if not prepared_path.is_file():
                copy_snapshot_entry(source, prepared, entry)
        advancement_outputs = convert_player_advancements(
            source,
            prepared,
            tools_dir,
            env,
            commands,
            report_dir / "player-advancements-refresh.json",
            "player-advancements-refresh",
        )
        for relative in advancement_outputs:
            add_replacement(
                replacements,
                relative,
                safe_join(prepared, relative),
                "player advancement ID migration/sidecar",
            )

    data = prepared / "world" / "data"
    if "world/data/create_tracks.dat" in effective_changed_sources:
        convert_saveddata(
            data / "create_tracks.dat",
            data / "create_tracks.dat",
            "tracks",
            tools_dir,
            env,
            commands,
            report_dir,
            source,
            staging,
        )
    if "world/data/create_logistics.dat" in effective_changed_sources:
        convert_saveddata(
            data / "create_logistics.dat",
            data / "create_logistics.dat",
            "logistics",
            tools_dir,
            env,
            commands,
            report_dir,
            source,
            staging,
        )

    if "config/mineastr-common.json" in effective_changed_sources:
        source_cfg = prepared / "config" / "mineastr-common.json"
        target_cfg = prepared / "config" / "mineastr-common.toml"
        require_free_derived_target(
            replacements, "config/mineastr-common.toml", "MineAstr config migration"
        )
        require_target_not_owned_by_source(
            current["entries"],
            "config/mineastr-common.toml",
            "MineAstr config migration",
        )
        run_tool(
            "mineastr-config-refresh",
            [
                str(tools_dir / "migrate_mineastr_config.py"),
                str(source_cfg),
                "--output",
                str(target_cfg),
                "--report",
                str(report_dir / "mineastr-config-refresh.json"),
            ],
            env,
            commands,
        )
        add_replacement(
            replacements,
            "config/mineastr-common.toml",
            target_cfg,
            "MineAstr config migration",
        )

    if "world/data/mineastr_sign_translations.dat" in effective_changed_sources:
        cache = data / "mineastr_sign_translations.dat"
        run_tool(
            "mineastr-cache-refresh",
            [
                str(tools_dir / "migrate_mineastr_cache.py"),
                str(cache),
                "--output",
                str(cache.with_name(cache.name + ".converted")),
                "--report",
                str(report_dir / "mineastr-cache-refresh.json"),
                "--promote-automatic",
            ],
            env,
            commands,
        )
        converted_cache = cache.with_name(cache.name + ".converted")
        os.replace(converted_cache, cache)

    auth_sources = {f"EasyAuth/{name}" for name in AUTH_DATABASE_FILES}
    auth_changed = bool((effective_changed_sources | deleted_sources) & auth_sources)
    if auth_changed:
        # SQLite may retain committed accounts in -wal after shutdown. Build a
        # complete current database set in the transaction directory before
        # opening it read-only, even when only one sidecar changed/disappeared.
        for auth_source in sorted(auth_sources & set(current_by_source)):
            auth_entry = current_by_source[auth_source]
            auth_target = safe_join(prepared, auth_entry["target"])
            if not auth_target.is_file():
                copy_snapshot_entry(source, prepared, auth_entry)
        auth_db = prepared / "migration-input" / "EasyAuth" / "easyauth.db"
        if not auth_db.is_file():
            raise RuntimeError("EasyAuth refresh requires easyauth.db")
        auth_snapshot = transaction_root / "sqlite" / "easyauth.snapshot.db"
        auth_snapshot_report = snapshot_easyauth_database(
            auth_db,
            auth_snapshot,
            report_dir / "easyauth-sqlite-refresh.json",
        )
        auth_output = prepared / "world" / "xiyus_player_data.json"
        require_free_derived_target(
            replacements, "world/xiyus_player_data.json", "EasyAuth migration"
        )
        require_target_not_owned_by_source(
            current["entries"],
            "world/xiyus_player_data.json",
            "EasyAuth migration",
        )
        auth_output.parent.mkdir(parents=True, exist_ok=True)
        run_tool(
            "easyauth-to-xiyuslogin-refresh",
            [
                str(EASYAUTH_CONVERTER),
                str(auth_snapshot),
                str(auth_output),
                "--manifest",
                str(report_dir / "xiyuslogin-refresh.json"),
                "--expected-records",
                str(auth_snapshot_report["records"]),
                "--force",
            ],
            env,
            commands,
        )
        add_replacement(
            replacements,
            "world/xiyus_player_data.json",
            auth_output,
            "EasyAuth migration",
        )

    for relative, prepared_path in replacements.items():
        if not prepared_path.is_file():
            raise RuntimeError(f"refresh output was not prepared: {relative}")
    return replacements, deletions, {
        "changed_inputs": len(changed_entries),
        "selected_regions": selected_regions,
        "world_conversion_needed": world_conversion_needed,
        "converter_reconciliation": {
            "required": reconcile_converters,
            "inputs": len(reconciliation_entries),
            "world_inputs": len(world_conversion_entries),
        },
        "vanilla_saveddata": sorted(selected_vanilla_saveddata),
        "advancements": {
            "converted": advancement_conversion_needed,
            "source_files": len(advancement_entries),
        },
        "replacement_targets": sorted(replacements),
        "deletion_targets": sorted(deletions),
    }


def build_environment(work_root: Path) -> dict[str, str]:
    temp = work_root / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "TEMP": str(temp),
            "TMP": str(temp),
            "PYTHONPYCACHEPREFIX": str(work_root / "pycache"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(r"<AUDIT_ROOT>\poi-nbtdeps")),
        }
    )
    return env


WORLD_VERIFY_BLOCKER_FIELDS = (
    "preflight_blocked",
    "unsupported_equipment",
    "unsupported_leashes",
    "unsupported_player_items",
    "unsupported_entity_items",
    "unsupported_player_equipment",
    "unsupported_player_respawns",
    "unsupported_entities",
    "unsupported_create_fluids",
    "unsupported_block_entities",
    "unsupported_attributes",
    "unsupported_game_rules",
    "level_blockers",
    "malformed_players",
    "malformed_regions",
)


def world_verify_blockers(report_path: Path, require_functional_schematics: bool) -> dict:
    if not report_path.is_file():
        raise RuntimeError(f"world verify report is missing: {report_path}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"world verify report is not valid JSON: {report_path}") from exc
    if not isinstance(report, dict):
        raise RuntimeError(f"world verify report is not an object: {report_path}")
    blockers = {}
    for field in WORLD_VERIFY_BLOCKER_FIELDS:
        value = report.get(field, [])
        if isinstance(value, list) and value:
            blockers[field] = value
        elif value not in (None, [], {}):
            blockers[field] = value
    if require_functional_schematics:
        inherited = report.get("inherited_missing_schematic_files", [])
        if inherited:
            blockers["inherited_missing_schematic_files"] = inherited
    return {"report": report, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description="D-drive-only fast migration staging orchestrator")
    parser.add_argument(
        "phase",
        choices=("manifest", "stage", "convert", "refresh", "verify", "sanitize-target"),
    )
    parser.add_argument("--source-game-dir", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--staging-game-dir", type=Path, default=WORK_DEFAULT)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--baseline-manifest",
        type=Path,
        help=(
            "full-hash raw-input baseline written by stage and required by refresh "
            "(defaults beside the staging report directory)"
        ),
    )
    parser.add_argument(
        "--allow-source-deletions",
        action="store_true",
        help=(
            "allow non-critical source deletions during refresh; deletions are "
            "blocked by default and critical inputs always remain blockers"
        ),
    )
    parser.add_argument("--hash-all", action="store_true")
    parser.add_argument(
        "--waypoint-fire-jar",
        type=Path,
        default=Path(
            r"<AUDIT_ROOT>\waypoint-fire-equivalence\build\libs\waypoint-fire-equivalence-0.1.0-draft+mc1.21.1.jar"
        ),
    )
    parser.add_argument("--waypoint-fire-sha256", default=WAYPOINT_SHA256)
    parser.add_argument("--villager-baseline", type=Path)
    parser.add_argument(
        "--target-game-dir",
        type=Path,
        help=(
            "assembled NeoForge target copy for sanitize-target; this path is "
            "mutated in place and must be separate from source and staging"
        ),
    )
    parser.add_argument("--target-mods-dir", type=Path)
    parser.add_argument(
        "--require-functional-schematics",
        action="store_true",
        help="turn inherited missing Create schematic files into a blocker",
    )
    parser.add_argument(
        "--world-workers",
        type=int,
        default=1,
        help="region worker processes for world NBT conversion (default: 1)",
    )
    parser.add_argument(
        "--preheat-defer-portal-tickets",
        action="store_true",
        help=(
            "convert every audited SavedData kind except chunks.dat during preheat; "
            "the completion marker remains pending until stopped-source refresh "
            "proves all portal tickets expired and converts chunks strictly"
        ),
    )
    args = parser.parse_args()

    logical_cpus = os.cpu_count() or 1
    if not 1 <= args.world_workers <= logical_cpus:
        parser.error(
            f"--world-workers must be between 1 and {logical_cpus} "
            "(the detected logical CPU count)"
        )

    if args.preheat_defer_portal_tickets and args.phase != "convert":
        raise SystemExit("--preheat-defer-portal-tickets is valid only for convert")

    source = ensure_d_path(args.source_game_dir, "source-game-dir")
    staging = ensure_d_path(args.staging_game_dir, "staging-game-dir")
    ensure_distinct(source, staging)
    tools_dir = Path(__file__).resolve().parent
    target_game_dir = None
    target_game_dir_input = None
    if args.phase == "sanitize-target":
        if args.target_game_dir is None:
            raise SystemExit("sanitize-target requires --target-game-dir")
        target_game_dir_input = Path(args.target_game_dir)
        if target_game_dir_input.is_symlink():
            raise ValueError(
                f"target-game-dir must not be a symbolic link: {args.target_game_dir}"
            )
        target_game_dir = ensure_d_path(target_game_dir_input, "target-game-dir")
        ensure_outside_source(source, target_game_dir, "target-game-dir")
        if _paths_overlap(target_game_dir, staging):
            raise ValueError("target-game-dir must be disjoint from staging-game-dir")
        default_report_root = target_game_dir / "migration-reports"
        default_report_name = "resource-sanitization.json"
    else:
        default_report_root = (
            staging / "migration-reports"
            if args.phase in {"convert", "verify"}
            else staging.parent / f"{staging.name}-reports"
        )
        default_report_name = f"fast-{args.phase}.json"
    report_path = ensure_d_path(
        args.report or (default_report_root / default_report_name),
        "report",
    )
    baseline_path = ensure_d_path(
        args.baseline_manifest
        or (staging.parent / f"{staging.name}-reports" / "source-baseline.json"),
        "baseline-manifest",
    )
    ensure_outside_source(source, report_path, "report")
    ensure_outside_source(source, baseline_path, "baseline-manifest")
    if target_game_dir is not None:
        if _paths_overlap(report_path, staging):
            raise ValueError("sanitize-target report must not overlap staging-game-dir")
        if args.report is not None and Path(args.report).is_symlink():
            raise ValueError(f"sanitize-target report must not be a symbolic link: {args.report}")
    work_root = staging.parent
    env = build_environment(work_root)
    commands: list[dict] = []
    result = {
        "schema": 1,
        "phase": args.phase,
        "source_manifest_before": critical_manifest(source, args.hash_all),
        "excluded_source_inputs": excluded_input_manifest(source),
        "staging": str(staging),
        "commands": commands,
        "accepted_exceptions": {
            "ledger": "source world ledger.sqlite is intentionally not copied (Ledger -> GriefLogger)",
            "easyauth": "source SQLite is retained only under migration-input and converted to XiyusLogin JSON",
            "schematics": "inherited missing files remain warnings unless --require-functional-schematics is set",
        },
    }

    if args.phase == "manifest":
        result["source_manifest_after"] = critical_manifest(source, args.hash_all)
        result["status"] = "READ_ONLY_MANIFEST"
        atomic_json(report_path, result)
        print(json.dumps({"status": result["status"], "report": str(report_path)}, ensure_ascii=False))
        return 0

    if args.phase == "stage":
        copy_filtered(source, staging)
        result["schematics_copy_gate"] = validate_schematic_tree_copy(
            source, staging
        )
        # Hash the exact bytes copied into the fresh raw staging tree.  This is
        # the only reliable baseline if the live source changes after staging
        # but before the eventual maintenance window.
        baseline = staged_baseline_manifest(source, staging)
        atomic_json(baseline_path, baseline)
        result["baseline"] = {
            "path": str(baseline_path),
            "sha256": sha256(baseline_path),
            "snapshot_sha256": baseline["snapshot_sha256"],
            "files": baseline["files"],
            "bytes": baseline["bytes"],
        }
        result["staging_manifest"] = critical_manifest(staging, args.hash_all)
        result["status"] = "STAGED"
        result["source_manifest_after"] = critical_manifest(source, args.hash_all)
        atomic_json(report_path, result)
        print(json.dumps({"status": result["status"], "report": str(report_path)}, ensure_ascii=False))
        return 0

    if not staging.is_dir():
        raise SystemExit(f"staging directory does not exist; run stage first: {staging}")

    if args.phase == "sanitize-target":
        target_mods = (
            args.target_mods_dir
            if args.target_mods_dir is not None
            else target_game_dir / "mods"
        )
        try:
            target_result = sanitize_target_copy(
                source,
                staging,
                target_game_dir_input,
                target_mods,
                hash_all=args.hash_all,
            )
        except Exception as exc:
            result["status"] = "SANITIZE_TARGET_FAILED"
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["target_game_dir"] = str(target_game_dir)
            result["source_manifest_after"] = critical_manifest(source, args.hash_all)
            result["staging_manifest_after"] = critical_manifest(staging, args.hash_all)
            atomic_json(report_path, result)
            raise
        result.update(target_result)
        result["source_manifest_after"] = critical_manifest(source, args.hash_all)
        result["staging_manifest_after"] = critical_manifest(staging, args.hash_all)
        result["status"] = "SANITIZED_TARGET_COPY"
        atomic_json(report_path, result)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "report": str(report_path),
                    "changed_files": result["resource_sanitization"].get(
                        "changed_files", 0
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.target_mods_dir is not None and not args.target_mods_dir.is_dir():
        raise SystemExit(f"target mods directory does not exist: {args.target_mods_dir}")

    world = staging / "world"
    waypoint_args: list[str] = []
    if args.waypoint_fire_jar:
        waypoint_args = [
            "--waypoint-fire-compat-jar",
            str(args.waypoint_fire_jar.resolve()),
            "--waypoint-fire-compat-sha256",
            args.waypoint_fire_sha256,
        ]

    if args.phase == "refresh":
        result["source_stop_probes"] = []
        result["staging_stop_probes"] = []
        try:
            result["source_stop_probes"].append(
                {"point": "before-full-hash", **probe_session_lock(source / "world")}
            )
            result["staging_stop_probes"].append(
                {"point": "before-full-hash", **probe_session_lock(staging / "world")}
            )
        except RuntimeError as exc:
            result["status"] = "BLOCKED_SERVER_ACTIVE"
            result["error"] = f"{type(exc).__name__}: {exc}"
            atomic_json(report_path, result)
            raise
        orphans = orphan_refresh_transactions(staging)
        if orphans:
            result["status"] = "BLOCKED_ORPHAN_REFRESH_TRANSACTION"
            result["orphan_transactions"] = orphans
            atomic_json(report_path, result)
            raise RuntimeError(
                "an earlier refresh transaction requires recovery/audit before "
                f"continuing: {orphans[0]['path']}"
            )
        if not baseline_path.is_file():
            raise RuntimeError(
                f"refresh requires the full-hash baseline written by stage: {baseline_path}"
            )
        baseline = validate_baseline_manifest(
            json.loads(baseline_path.read_text(encoding="utf-8")), source, staging
        )
        marker_path = conversion_marker_path(staging)
        try:
            marker = validate_conversion_marker(
                marker_path,
                source,
                staging,
                baseline,
                tools_dir,
                allow_converter_reconciliation=True,
            )
        except RuntimeError as exc:
            result["status"] = "BLOCKED_CONVERSION_INCOMPLETE_OR_DAMAGED"
            result["error"] = f"{type(exc).__name__}: {exc}"
            atomic_json(report_path, result)
            raise
        converter_reconciliation = converter_reconciliation_status(
            marker, tools_dir
        )
        expected_converter_fingerprints = converter_reconciliation["current"]
        result["conversion_marker_before"] = {
            "path": str(marker_path),
            "sha256": sha256(marker_path),
            "outputs": marker["outputs"],
            "pending_saveddata": marker.get("pending_saveddata", []),
            "converter_reconciliation": converter_reconciliation,
        }
        current = source_input_snapshot(source)
        unsupported_regions = unsupported_region_inputs(current["entries"])
        if unsupported_regions:
            result["status"] = "BLOCKED_UNSUPPORTED_DIMENSION_REGIONS"
            result["unsupported_dimension_regions"] = unsupported_regions
            atomic_json(report_path, result)
            raise RuntimeError(
                "source contains Anvil region trees not supported by the "
                f"targeted converter: {unsupported_regions[:10]}"
            )
        current_snapshot_path = report_path.with_name(
            report_path.stem + "-source-snapshot.json"
        )
        atomic_json(current_snapshot_path, current)
        delta = compare_snapshots(baseline, current)
        result["baseline"] = {
            "path": str(baseline_path),
            "sha256": sha256(baseline_path),
            "snapshot_sha256": baseline["snapshot_sha256"],
            "files": baseline["files"],
            "bytes": baseline["bytes"],
        }
        result["current_source_snapshot"] = {
            "path": str(current_snapshot_path),
            "sha256": sha256(current_snapshot_path),
            "snapshot_sha256": current["snapshot_sha256"],
            "files": current["files"],
            "bytes": current["bytes"],
        }
        result["delta"] = {
            "added": delta["added"],
            "modified": delta["modified"],
            "deleted": delta["deleted"],
            "metadata_only": delta["metadata_only"],
            "unchanged": delta["unchanged"],
        }

        deleted_sources = {entry["source"] for entry in delta["deleted"]}
        critical_deletions = sorted(deleted_sources & CRITICAL_SOURCE_DELETIONS)
        if critical_deletions or (
            deleted_sources and not args.allow_source_deletions
        ):
            result["source_stop_probes"].append(
                {"point": "deletion-block", **probe_session_lock(source / "world")}
            )
            result["staging_stop_probes"].append(
                {"point": "deletion-block", **probe_session_lock(staging / "world")}
            )
            assert_source_snapshot_stable(source, current)
            result["status"] = "BLOCKED_SOURCE_DELETIONS"
            result["deletion_policy"] = {
                "allow_source_deletions": args.allow_source_deletions,
                "critical_deletions": critical_deletions,
                "blocked_deletions": sorted(deleted_sources),
            }
            result["source_manifest_after"] = critical_manifest(source, False)
            atomic_json(report_path, result)
            raise RuntimeError(
                "source deletions blocked the fail-closed refresh; see "
                f"{report_path}"
            )

        verify_unchanged_staging_inputs(staging, baseline["entries"], delta)
        pending_saveddata = set(marker.get("pending_saveddata", []))
        has_content_delta = bool(
            delta["added"] or delta["modified"] or delta["deleted"]
        ) or bool(pending_saveddata) or converter_reconciliation["required"]
        if not has_content_delta:
            result["source_stop_probes"].append(
                {"point": "no-change-final", **probe_session_lock(source / "world")}
            )
            result["staging_stop_probes"].append(
                {"point": "no-change-final", **probe_session_lock(staging / "world")}
            )
            assert_source_snapshot_stable(source, current)
            result["status"] = "REFRESH_NO_CONTENT_CHANGES"
            result["source_manifest_after"] = critical_manifest(source, False)
            atomic_json(report_path, result)
            print(
                json.dumps(
                    {"status": result["status"], "report": str(report_path)},
                    ensure_ascii=False,
                )
            )
            return 0

        transaction_root = Path(
            tempfile.mkdtemp(
                prefix=f".{staging.name}-refresh-", dir=str(staging.parent)
            )
        ).resolve()
        ensure_d_path(transaction_root, "refresh transaction")
        ensure_outside_source(source, transaction_root, "refresh transaction")
        result["transaction"] = {"path": str(transaction_root)}
        transaction_journal_path = transaction_root / "transaction-journal.json"
        journal: list[dict] = []
        retain_transaction = False
        try:
            replacements, deletions, transaction_summary = prepare_refresh_transaction(
                source,
                staging,
                transaction_root,
                current,
                delta,
                tools_dir,
                env,
                commands,
                report_path.parent,
                args.waypoint_fire_jar.resolve(),
                args.waypoint_fire_sha256,
                args.require_functional_schematics,
                pending_saveddata,
                converter_reconciliation["required"],
                args.world_workers,
            )
            result["transaction"].update(transaction_summary)
            assert_converter_fingerprints_stable(
                expected_converter_fingerprints, tools_dir
            )
            new_baseline = {
                **current,
                "kind": "staged-raw-source-baseline",
                "source_root": str(source),
                "staging_root": str(staging),
            }
            previous_conversion_report = Path(
                str(marker.get("conversion_report", report_path))
            )
            marker_payload = make_conversion_marker(
                source,
                staging,
                new_baseline,
                previous_conversion_report,
                staging,
                replacements,
                tools_dir=tools_dir,
                converter_fingerprints_value=expected_converter_fingerprints,
            )
            prepared_marker = safe_join(
                transaction_root / "prepared", CONVERSION_MARKER_RELATIVE
            )
            atomic_json(prepared_marker, marker_payload)
            add_replacement(
                replacements,
                CONVERSION_MARKER_RELATIVE,
                prepared_marker,
                "conversion completion marker",
            )
            result["transaction"]["replacement_targets"] = sorted(replacements)
            result["source_stop_probes"].append(
                {"point": "before-commit", **probe_session_lock(source / "world")}
            )
            result["staging_stop_probes"].append(
                {"point": "before-commit", **probe_session_lock(staging / "world")}
            )
            # A second full hash runs immediately before the first staging
            # rename. Changed files were also hash-checked while copied.
            assert_source_snapshot_stable(source, current)
            assert_converter_fingerprints_stable(
                expected_converter_fingerprints, tools_dir
            )
            journal = commit_transaction(
                staging,
                replacements,
                deletions,
                transaction_root / "backup",
                transaction_root / "rollback-discard",
                transaction_journal_path,
            )
            try:
                # Keep the backups until a second stopped-source stability
                # check has passed. A server restart during commit rolls the
                # entire staging transaction back.
                result["source_stop_probes"].append(
                    {"point": "after-commit", **probe_session_lock(source / "world")}
                )
                result["staging_stop_probes"].append(
                    {"point": "after-commit", **probe_session_lock(staging / "world")}
                )
                assert_source_snapshot_stable(source, current)
                assert_converter_fingerprints_stable(
                    expected_converter_fingerprints, tools_dir
                )
            except Exception:
                rollback_transaction(
                    journal, transaction_root / "post-commit-rollback-discard"
                )
                update_transaction_journal_status(
                    transaction_journal_path, "ROLLED_BACK_SOURCE_CHANGED"
                )
                journal = []
                raise

            atomic_json(baseline_path, new_baseline)
            result["transaction"]["journal"] = serialized_journal(journal)
            result["baseline_after"] = {
                "path": str(baseline_path),
                "sha256": sha256(baseline_path),
                "snapshot_sha256": new_baseline["snapshot_sha256"],
                "files": new_baseline["files"],
                "bytes": new_baseline["bytes"],
            }
            result["status"] = "REFRESHED_INCREMENTALLY"
        except TransactionRollbackError as exc:
            retain_transaction = True
            result["status"] = "REFRESH_ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED"
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["transaction"]["retained_for_recovery"] = True
            result["source_manifest_after"] = critical_manifest(source, False)
            atomic_json(report_path, result)
            raise
        except Exception as exc:
            if journal:
                try:
                    rollback_transaction(
                        journal,
                        transaction_root / "exception-rollback-discard",
                    )
                    update_transaction_journal_status(
                        transaction_journal_path,
                        "ROLLED_BACK_EXCEPTION",
                        f"{type(exc).__name__}: {exc}",
                    )
                    journal = []
                    # If writing the advanced baseline caused the exception,
                    # restore the previous manifest alongside staging.
                    atomic_json(baseline_path, baseline)
                except Exception as rollback_exc:
                    retain_transaction = True
                    result["status"] = (
                        "REFRESH_ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED"
                    )
                    result["error"] = (
                        f"{type(exc).__name__}: {exc}; rollback: "
                        f"{type(rollback_exc).__name__}: {rollback_exc}"
                    )
                    result["transaction"]["retained_for_recovery"] = True
                    result["source_manifest_after"] = critical_manifest(
                        source, False
                    )
                    atomic_json(report_path, result)
                    raise TransactionRollbackError(result["error"]) from exc
            result["status"] = "REFRESH_FAILED_STAGING_UNCHANGED"
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["transaction"]["rollback_complete"] = True
            result["source_manifest_after"] = critical_manifest(source, False)
            atomic_json(report_path, result)
            raise
        finally:
            if not retain_transaction and transaction_root.exists():
                try:
                    shutil.rmtree(transaction_root)
                except OSError as cleanup_exc:
                    # Cleanup cannot change the already committed/rolled-back
                    # staging result. Preserve the path for a later manual
                    # cleanup instead of masking the migration status.
                    result["transaction"]["cleanup_warning"] = (
                        f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                    )
                    result["transaction"]["retained_for_cleanup"] = True

        result["source_manifest_after"] = critical_manifest(source, False)
        result["staging_manifest_after"] = critical_manifest(staging, args.hash_all)
        atomic_json(report_path, result)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "report": str(report_path),
                    "commands": len(commands),
                    "regions": len(
                        result["transaction"].get("selected_regions", [])
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.phase == "verify":
        if not baseline_path.is_file():
            result["status"] = "BLOCKED_BASELINE_MISSING"
            result["error"] = f"baseline manifest is missing: {baseline_path}"
            atomic_json(report_path, result)
            raise RuntimeError(result["error"])
        try:
            baseline = validate_baseline_manifest(
                json.loads(baseline_path.read_text(encoding="utf-8")),
                source,
                staging,
            )
            marker_path = conversion_marker_path(staging)
            marker = validate_conversion_marker(
                marker_path, source, staging, baseline, tools_dir
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            result["status"] = "BLOCKED_CONVERSION_MARKER_OR_BASELINE"
            result["error"] = f"{type(exc).__name__}: {exc}"
            atomic_json(report_path, result)
            raise

        pending_saveddata = marker["pending_saveddata"]
        if pending_saveddata:
            result["status"] = "BLOCKED_PENDING_SAVEDDATA"
            result["pending_saveddata"] = pending_saveddata
            result["conversion_marker"] = {
                "path": str(marker_path),
                "sha256": sha256(marker_path),
                "source_root": marker["source_root"],
                "staging_root": marker["staging_root"],
                "outputs": marker["outputs"],
            }
            atomic_json(report_path, result)
            raise RuntimeError(
                "verify is blocked until pending SavedData is converted: "
                + ", ".join(pending_saveddata)
            )

        try:
            baseline, marker = validate_final_conversion_gate(
                marker_path, source, staging, baseline_path
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            result["status"] = "BLOCKED_CONVERSION_INCOMPLETE_OR_STALE"
            result["error"] = f"{type(exc).__name__}: {exc}"
            atomic_json(report_path, result)
            raise

        result["baseline"] = {
            "path": str(baseline_path),
            "sha256": sha256(baseline_path),
            "snapshot_sha256": baseline["snapshot_sha256"],
            "files": baseline["files"],
            "bytes": baseline["bytes"],
        }
        result["conversion_marker"] = {
            "path": str(marker_path),
            "sha256": sha256(marker_path),
            "source_root": marker["source_root"],
            "staging_root": marker["staging_root"],
            "outputs": marker["outputs"],
            "pending_saveddata": pending_saveddata,
        }
        result["schematics_copy_gate"] = validate_schematic_tree_copy(
            source, staging
        )
        result["staging_stop_probe"] = probe_session_lock(staging / "world")
        world_verify_report = report_path.parent / "world-verify.json"
        run_tool(
            "world-verify",
            [
                str(tools_dir / "convert_world_nbt.py"),
                "dry-run",
                "--world",
                str(world),
                "--report",
                str(world_verify_report),
                "--source-game-dir",
                str(source),
                "--target-game-dir",
                str(staging),
                "--workers",
                str(args.world_workers),
                *waypoint_args,
            ]
            + (
                ["--require-functional-schematics"]
                if args.require_functional_schematics
                else []
            ),
            env,
            commands,
        )
        verification = world_verify_blockers(
            world_verify_report, args.require_functional_schematics
        )
        result["world_verify"] = {
            "report": str(world_verify_report),
            "sha256": sha256(world_verify_report),
            "blockers": verification["blockers"],
        }
        if verification["blockers"]:
            result["status"] = "BLOCKED_WORLD_VERIFY"
            result["source_manifest_after"] = critical_manifest(source, False)
            result["staging_manifest_after"] = critical_manifest(staging, args.hash_all)
            atomic_json(report_path, result)
            raise RuntimeError(
                "world verify reported blocking records; see "
                f"{world_verify_report}"
            )
        result["staging_manifest_after"] = critical_manifest(staging, args.hash_all)
        result["source_manifest_after"] = critical_manifest(source, args.hash_all)
        result["status"] = "VERIFIED_READ_ONLY"
        atomic_json(report_path, result)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "report": str(report_path),
                    "commands": len(commands),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.phase == "convert":
        result["staging_stop_probe"] = probe_session_lock(staging / "world")
        if not baseline_path.is_file():
            raise RuntimeError(
                "convert requires the full-hash baseline written by stage; "
                "prepare a fresh staging copy"
            )
        baseline_for_convert = validate_baseline_manifest(
            json.loads(baseline_path.read_text(encoding="utf-8")), source, staging
        )
        result["schematics_copy_gate"] = validate_schematic_tree_copy(
            source, staging
        )
        unsupported_regions = unsupported_region_inputs(
            baseline_for_convert["entries"]
        )
        if unsupported_regions:
            raise RuntimeError(
                "staged source contains Anvil region trees not supported by the "
                f"converter: {unsupported_regions[:10]}"
            )
        if conversion_marker_path(staging).exists():
            raise RuntimeError(
                "staging already has a successful conversion marker; refuse to "
                "rerun the non-global initial conversion in place, create a fresh stage"
            )
        deployed_waypoint = deploy_waypoint_runtime(
            staging, args.waypoint_fire_jar, args.waypoint_fire_sha256
        )
        result["deployed_waypoint_fire_jar"] = {
            "path": str(deployed_waypoint),
            "sha256": sha256(deployed_waypoint),
        }
        expected_converter_fingerprints = converter_fingerprints(tools_dir)
        result["converter_fingerprints"] = expected_converter_fingerprints
        # convert_world_nbt performs its own complete read-only preflight
        # immediately before writing.  Do not scan the 10 GB world twice.
        result["world_preflight"] = "delegated_to_convert_world_nbt"
        if args.villager_baseline:
            run_tool(
                "villager-preflight",
                [
                    str(tools_dir / "convert_villager_region_entities.py"),
                    "dry-run",
                    "--world",
                    str(world),
                    "--baseline",
                    str(args.villager_baseline.resolve()),
                    "--converter",
                    str(tools_dir / "convert_world_nbt.py"),
                    "--report",
                    str(report_path.parent / "villager-preflight.json"),
                    "--waypoint-fire-runtime",
                ],
                env,
                commands,
            )
        if args.villager_baseline:
            run_tool(
                "villager-convert",
                [
                    str(tools_dir / "convert_villager_region_entities.py"),
                    "convert",
                    "--world",
                    str(world),
                    "--baseline",
                    str(args.villager_baseline.resolve()),
                    "--converter",
                    str(tools_dir / "convert_world_nbt.py"),
                    "--report",
                    str(report_path.parent / "villager-convert.json"),
                    "--waypoint-fire-runtime",
                ],
                env,
                commands,
            )
        run_tool(
            "world-convert",
            [
                str(tools_dir / "convert_world_nbt.py"),
                "convert",
                "--world",
                str(world),
                "--report",
                str(report_path.parent / "world-convert.json"),
                "--source-game-dir",
                str(source),
                "--target-game-dir",
                str(staging),
                "--workers",
                str(args.world_workers),
                *waypoint_args,
            ]
            + (["--require-functional-schematics"] if args.require_functional_schematics else []),
            env,
            commands,
        )

        pending_saveddata = (
            {"chunks"} if args.preheat_defer_portal_tickets else set()
        )
        initial_saveddata = VANILLA_SAVEDDATA_KINDS - pending_saveddata
        saveddata_outputs = convert_vanilla_saveddata(
            source,
            world,
            initial_saveddata,
            tools_dir,
            env,
            commands,
            report_path.parent / "vanilla-saveddata.json",
            "vanilla-saveddata",
        )
        result["vanilla_saveddata"] = {
            "converted": sorted(initial_saveddata),
            "pending": sorted(pending_saveddata),
            "outputs": saveddata_outputs,
        }

        advancement_outputs = convert_player_advancements(
            source,
            staging,
            tools_dir,
            env,
            commands,
            report_path.parent / "player-advancements.json",
            "player-advancements",
        )
        result["player_advancements"] = {
            "report": str(report_path.parent / "player-advancements.json"),
            "outputs": advancement_outputs,
        }

        data = world / "data"
        convert_saveddata(
            data / "create_tracks.dat",
            data / "create_tracks.dat",
            "tracks",
            tools_dir,
            env,
            commands,
            report_path.parent,
            source,
            staging,
        )
        convert_saveddata(
            data / "create_logistics.dat",
            data / "create_logistics.dat",
            "logistics",
            tools_dir,
            env,
            commands,
            report_path.parent,
            source,
            staging,
        )

        source_cfg = source / "config" / "mineastr-common.json"
        target_cfg = staging / "config" / "mineastr-common.toml"
        if source_cfg.is_file():
            run_tool(
                "mineastr-config",
                [
                    str(tools_dir / "migrate_mineastr_config.py"),
                    str(source_cfg),
                    "--output",
                    str(target_cfg),
                    "--report",
                    str(report_path.parent / "mineastr-config.json"),
                ],
                env,
                commands,
            )
        source_cache = source / "world" / "data" / "mineastr_sign_translations.dat"
        target_cache = data / "mineastr_sign_translations.dat"
        if source_cache.is_file():
            run_tool(
                "mineastr-cache",
                [
                    str(tools_dir / "migrate_mineastr_cache.py"),
                    str(source_cache),
                    "--output",
                    str(target_cache),
                    "--report",
                    str(report_path.parent / "mineastr-cache.json"),
                    "--promote-automatic",
                ],
                env,
                commands,
            )

        auth_db = staging / "migration-input" / "EasyAuth" / "easyauth.db"
        auth_output = staging / "world" / "xiyus_player_data.json"
        auth_manifest = report_path.parent / "xiyuslogin-migration.json"
        if auth_db.is_file():
            auth_temp = Path(
                tempfile.mkdtemp(prefix="easyauth-convert-", dir=str(work_root / "tmp"))
            )
            try:
                auth_snapshot = auth_temp / "easyauth.snapshot.db"
                auth_snapshot_report = snapshot_easyauth_database(
                    auth_db,
                    auth_snapshot,
                    report_path.parent / "easyauth-sqlite.json",
                )
                run_tool(
                    "easyauth-to-xiyuslogin",
                    [
                        str(EASYAUTH_CONVERTER),
                        str(auth_snapshot),
                        str(auth_output),
                        "--manifest",
                        str(auth_manifest),
                        "--expected-records",
                        str(auth_snapshot_report["records"]),
                        "--force",
                    ],
                    env,
                    commands,
                )
            finally:
                shutil.rmtree(auth_temp, ignore_errors=True)
        result["staging_manifest_after"] = critical_manifest(staging, args.hash_all)
        result["source_manifest_after"] = critical_manifest(source, args.hash_all)
        result["status"] = (
            "PREHEATED_STAGING_PENDING_SAVEDDATA"
            if pending_saveddata
            else "CONVERTED_STAGING"
        )
        assert_converter_fingerprints_stable(
            expected_converter_fingerprints, tools_dir
        )
        marker_path = conversion_marker_path(staging)
        marker_preview = make_conversion_marker(
            source,
            staging,
            baseline_for_convert,
            report_path,
            staging,
            pending_saveddata=pending_saveddata,
            tools_dir=tools_dir,
            converter_fingerprints_value=expected_converter_fingerprints,
        )
        result["conversion_marker"] = {
            "path": str(marker_path),
            "baseline_snapshot_sha256": marker_preview[
                "baseline_snapshot_sha256"
            ],
            "outputs": marker_preview["outputs"],
        }
        atomic_json(report_path, result)
        marker = make_conversion_marker(
            source,
            staging,
            baseline_for_convert,
            report_path,
            staging,
            pending_saveddata=pending_saveddata,
            tools_dir=tools_dir,
            converter_fingerprints_value=expected_converter_fingerprints,
        )
        atomic_json(marker_path, marker)
        print(json.dumps({"status": result["status"], "report": str(report_path), "commands": len(commands)}, ensure_ascii=False))
        return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fast migration failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
