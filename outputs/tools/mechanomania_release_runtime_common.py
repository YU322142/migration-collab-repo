#!/usr/bin/env python3
"""Validate and install the locked Mechanomania matched static release.

This module is intentionally release-scoped: the current 235/247 JAR counts
are verified from the selected READY/manifests, but are never embedded as a
permanent product cap.  It also applies the non-JAR overlay using the locked
``replace``/``copy_if_absent`` semantics without touching the release tree.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Any


class ReleaseRuntimeError(RuntimeError):
    pass


def is_reparse(path: Path) -> bool:
    """Return true for a symlink, junction, mount point, or other reparse node."""
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    return bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ) or path.is_symlink()


def assert_regular_tree(root: Path, label: str) -> None:
    """Fail closed when a locked input tree contains a path redirection."""
    root = root.resolve()
    if not root.is_dir() or is_reparse(root):
        raise ReleaseRuntimeError(f"{label} root is missing or linked: {root}")
    for path in root.rglob("*"):
        if is_reparse(path):
            raise ReleaseRuntimeError(f"{label} contains a linked/reparse entry: {path}")


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReleaseRuntimeError(f"{label} is missing, linked, or not a file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseRuntimeError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseRuntimeError(f"{label} must be a JSON object: {path}")
    return value


def _safe_rel(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReleaseRuntimeError(f"invalid relative path for {label}: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise ReleaseRuntimeError(f"unsafe relative path for {label}: {value}")
    return value


def bundle_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["file"]).casefold()):
        digest.update(
            (
                f"{row['file']}\0{int(row['bytes'])}\0"
                f"{str(row['sha256']).upper()}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def overlay_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["target_rel"].casefold()):
        digest.update(
            (
                f"{row['target_rel']}\0{int(row['bytes'])}\0"
                f"{str(row['sha256']).upper()}\0{row['layer']}\0"
                f"{row['merge_mode']}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def journeymap_mod_matches(*manifests: dict[str, Any]) -> list[dict[str, str]]:
    """Find JourneyMap even when a selected JAR has been renamed."""
    matches: list[dict[str, str]] = []
    for manifest in manifests:
        for row in manifest.get("rows", []):
            values = [str(row.get("file", "")), *(str(item) for item in row.get("mod_ids", []))]
            if any("journeymap" in value.casefold() for value in values):
                matches.append(
                    {
                        "file": str(row.get("file", "")),
                        "mod_ids": ",".join(str(item) for item in row.get("mod_ids", [])),
                    }
                )
    return matches


def _validate_mod_manifest(root: Path, side: str) -> dict[str, Any]:
    path = root / "manifests" / f"{side}-mods.json"
    value = read_json(path, f"{side} mod manifest")
    rows = value.get("files")
    if (
        value.get("schema") != 1
        or value.get("status") != "PASS_STATIC"
        or value.get("side") != side
        or not isinstance(rows, list)
        or not rows
    ):
        raise ReleaseRuntimeError(f"invalid {side} mod manifest header")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    directory = root / side / "mods"
    if not directory.is_dir() or is_reparse(directory):
        raise ReleaseRuntimeError(f"missing regular {side} mods directory")
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseRuntimeError(f"non-object {side} mod row")
        name = row.get("file")
        size = row.get("bytes")
        digest = str(row.get("sha256", "")).upper()
        ids = row.get("mod_ids")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.lower().endswith(".jar")
            or name.casefold() in seen
            or not isinstance(size, int)
            or size <= 0
            or re.fullmatch(r"[0-9A-F]{64}", digest) is None
            or not isinstance(ids, list)
        ):
            raise ReleaseRuntimeError(f"invalid {side} mod row: {row!r}")
        seen.add(name.casefold())
        source = directory / name
        if (
            not source.is_file()
            or is_reparse(source)
            or source.stat().st_size != size
            or sha256(source) != digest
        ):
            raise ReleaseRuntimeError(f"{side} release JAR differs from manifest: {name}")
        normalized.append({"file": name, "bytes": size, "sha256": digest, "mod_ids": ids})
    actual = {item.name.casefold() for item in directory.iterdir() if item.is_file()}
    if actual != seen or len(actual) != len(list(directory.iterdir())):
        raise ReleaseRuntimeError(f"{side} release mods directory has extra/non-file entries")
    aggregate = {
        "files": len(normalized),
        "bytes": sum(row["bytes"] for row in normalized),
        "bundle_sha256": bundle_digest(normalized),
    }
    if (
        value.get("file_count") != aggregate["files"]
        or value.get("bytes") != aggregate["bytes"]
        or str(value.get("bundle_sha256", "")).upper() != aggregate["bundle_sha256"]
    ):
        raise ReleaseRuntimeError(f"{side} mod manifest aggregate mismatch")
    return {"path": str(path), "sha256": sha256(path), "rows": normalized, **aggregate}


def _validate_overlay_manifest(root: Path, side: str) -> dict[str, Any]:
    path = root / "manifests" / f"{side}-overlay.json"
    value = read_json(path, f"{side} overlay manifest")
    rows = value.get("files")
    if (
        value.get("schema") != 1
        or value.get("status") != "PASS_STATIC"
        or value.get("side") != side
        or not isinstance(rows, list)
        or not rows
    ):
        raise ReleaseRuntimeError(f"invalid {side} overlay manifest header")
    directory = root / side / "overlay"
    if not directory.is_dir() or is_reparse(directory):
        raise ReleaseRuntimeError(f"missing regular {side} overlay directory")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseRuntimeError(f"non-object {side} overlay row")
        rel = _safe_rel(row.get("target_rel"), f"{side} overlay target")
        size = row.get("bytes")
        digest = str(row.get("sha256", "")).upper()
        mode = row.get("merge_mode")
        layer = row.get("layer")
        if (
            rel.casefold() in seen
            or not isinstance(size, int)
            or size < 0
            or re.fullmatch(r"[0-9A-F]{64}", digest) is None
            or mode not in {"replace", "copy_if_absent"}
            or not isinstance(layer, str)
            or not layer
        ):
            raise ReleaseRuntimeError(f"invalid {side} overlay row: {row!r}")
        seen.add(rel.casefold())
        source = directory / Path(rel)
        if (
            not source.is_file()
            or is_reparse(source)
            or source.stat().st_size != size
            or sha256(source) != digest
        ):
            raise ReleaseRuntimeError(f"{side} overlay payload differs: {rel}")
        normalized.append(
            {
                "target_rel": rel,
                "bytes": size,
                "sha256": digest,
                "merge_mode": mode,
                "layer": layer,
            }
        )
    actual = {
        item.relative_to(directory).as_posix().casefold()
        for item in directory.rglob("*")
        if item.is_file()
    }
    if actual != seen:
        raise ReleaseRuntimeError(f"{side} overlay directory differs from manifest")
    aggregate = {
        "files": len(normalized),
        "bytes": sum(row["bytes"] for row in normalized),
        "overlay_sha256": overlay_digest(normalized),
    }
    if (
        value.get("file_count") != aggregate["files"]
        or value.get("bytes") != aggregate["bytes"]
        or str(value.get("overlay_sha256", "")).upper() != aggregate["overlay_sha256"]
    ):
        raise ReleaseRuntimeError(f"{side} overlay manifest aggregate mismatch")
    return {"path": str(path), "sha256": sha256(path), "rows": normalized, **aggregate}


def validate_release(root: Path, ready_sha256: str, build_report: Path, build_sha256: str) -> dict[str, Any]:
    root = root.resolve()
    assert_regular_tree(root, "release")
    ready_path = root / "READY.json"
    lock_path = root / "release-lock.json"
    expected_ready = ready_sha256.upper()
    expected_build = build_sha256.upper()
    if sha256(ready_path) != expected_ready or sha256(lock_path) != expected_ready:
        raise ReleaseRuntimeError("READY/release-lock hash mismatch")
    if ready_path.read_bytes() != lock_path.read_bytes():
        raise ReleaseRuntimeError("READY and release-lock are not byte-identical")
    if sha256(build_report) != expected_build:
        raise ReleaseRuntimeError("build report hash mismatch")
    ready = read_json(ready_path, "Mechanomania READY")
    build = read_json(build_report, "Mechanomania build report")
    if (
        ready.get("schema") != 1
        or ready.get("status") != "STATIC_RELEASE_READY_RUNTIME_BLOCKED"
        or ready.get("static_release_ready") is not True
        or ready.get("runtime_go") is not False
        or Path(str(ready.get("release_root", ""))).resolve() != root
    ):
        raise ReleaseRuntimeError("Mechanomania READY identity mismatch")
    policy = ready.get("extension_policy")
    if (
        not isinstance(policy, dict)
        or policy.get("permanent_file_count_cap") is not False
        or policy.get("permanent_mod_allowlist") is not False
        or policy.get("future_mods_allowed") is not True
    ):
        raise ReleaseRuntimeError("release extension policy would lock future mods")
    server_mods = _validate_mod_manifest(root, "server")
    client_mods = _validate_mod_manifest(root, "client")
    server_overlay = _validate_overlay_manifest(root, "server")
    client_overlay = _validate_overlay_manifest(root, "client")
    checks = ready.get("checks")
    journeymap_matches = journeymap_mod_matches(server_mods, client_mods)
    if (
        not isinstance(checks, dict)
        or checks.get("journeymap_selected") != 0
        or journeymap_matches
    ):
        raise ReleaseRuntimeError(
            f"JourneyMap is still selected in the locked release: {journeymap_matches}"
        )
    for side, mods, overlay in (
        ("server", server_mods, server_overlay),
        ("client", client_mods, client_overlay),
    ):
        bound = ready.get(side)
        if (
            not isinstance(bound, dict)
            or bound.get("mod_file_count") != mods["files"]
            or bound.get("mod_bytes") != mods["bytes"]
            or str(bound.get("bundle_sha256", "")).upper() != mods["bundle_sha256"]
            or str(bound.get("mod_manifest", "")) != mods["path"]
            or bound.get("overlay_file_count") != overlay["files"]
            or bound.get("overlay_bytes") != overlay["bytes"]
            or str(bound.get("overlay_sha256", "")).upper() != overlay["overlay_sha256"]
            or str(bound.get("overlay_manifest", "")) != overlay["path"]
        ):
            raise ReleaseRuntimeError(f"READY {side} binding mismatch")
    if (
        build.get("status") != ready.get("status")
        or Path(str(build.get("release_root", ""))).resolve() != root
        or str(build.get("ready_sha256", "")).upper() != expected_ready
    ):
        raise ReleaseRuntimeError("build report is not bound to this release")
    expected_manifests = build.get("manifest_sha256")
    observed_manifests = {
        "server-mods.json": server_mods["sha256"],
        "client-mods.json": client_mods["sha256"],
        "server-overlay.json": server_overlay["sha256"],
        "client-overlay.json": client_overlay["sha256"],
    }
    if expected_manifests != observed_manifests:
        raise ReleaseRuntimeError("build report manifest hashes mismatch")
    return {
        "root": str(root),
        "ready": {"path": str(ready_path), "sha256": expected_ready},
        "build_report": {"path": str(build_report.resolve()), "sha256": expected_build},
        "server_mods": server_mods,
        "client_mods": client_mods,
        "server_overlay": server_overlay,
        "client_overlay": client_overlay,
        "extension_policy": policy,
        "permanent_mod_count_cap": False,
        "journeymap_selected": 0,
    }


def install_mods(binding: dict[str, Any], side: str, destination: Path) -> dict[str, Any]:
    manifest = binding[f"{side}_mods"]
    source_root = Path(binding["root"]) / side / "mods"
    if destination.exists() or is_reparse(destination):
        raise ReleaseRuntimeError(f"mod destination already exists or is linked: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    copied: list[dict[str, Any]] = []
    for row in manifest["rows"]:
        source = source_root / row["file"]
        target = destination / row["file"]
        shutil.copy2(source, target)
        if target.stat().st_size != row["bytes"] or sha256(target) != row["sha256"]:
            raise ReleaseRuntimeError(f"copied {side} JAR differs: {row['file']}")
        copied.append(row)
    return {
        "files": len(copied),
        "bytes": sum(row["bytes"] for row in copied),
        "bundle_sha256": bundle_digest(copied),
    }


def apply_overlay(binding: dict[str, Any], side: str, target_root: Path) -> dict[str, Any]:
    manifest = binding[f"{side}_overlay"]
    source_root = Path(binding["root"]) / side / "overlay"
    applied = 0
    replaced = 0
    skipped_existing = 0
    for row in manifest["rows"]:
        source = source_root / Path(row["target_rel"])
        target = target_root / Path(row["target_rel"])
        current = target_root
        for part in Path(row["target_rel"]).parts[:-1]:
            current /= part
            if current.exists() and is_reparse(current):
                raise ReleaseRuntimeError(f"overlay target parent is linked: {current}")
        if row["merge_mode"] == "copy_if_absent" and target.exists():
            skipped_existing += 1
            continue
        if target.exists() and (target.is_dir() or is_reparse(target)):
            raise ReleaseRuntimeError(f"overlay target is not a regular file: {target}")
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if target.stat().st_size != row["bytes"] or sha256(target) != row["sha256"]:
            raise ReleaseRuntimeError(f"applied {side} overlay differs: {row['target_rel']}")
        applied += 1
        replaced += int(existed)
    return {
        "declared_files": manifest["files"],
        "applied": applied,
        "replaced": replaced,
        "skipped_existing": skipped_existing,
        "overlay_sha256": manifest["overlay_sha256"],
    }
