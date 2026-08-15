#!/usr/bin/env python3
"""Atomically assemble a production NeoForge target from verified staging.

This is deliberately separate from the network-isolated smoke builder.  It
preserves production configuration, requires a final (non-preheated)
conversion marker, verifies every server JAR, sanitizes only the new target
copy, and publishes the target directory only after all preparation succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

RUNTIME_FILES = ("run.bat", "run.sh", "user_jvm_args.txt")
STAGING_FILES = (
    "server.properties",
    "whitelist.json",
    "ops.json",
    "banned-players.json",
    "banned-ips.json",
    "usercache.json",
)
STAGING_DIRECTORIES = (
    "world",
    "config",
    "defaultconfigs",
    "schematics",
    # Authoritative player content, not a disposable runtime cache.
    "immersive_paintings_cache",
)
BUFFER_SIZE = 4 * 1024 * 1024
FINAL_CONVERSION_MARKER_RELATIVE = Path("migration-reports/conversion-complete.json")
FINAL_CONVERSION_MARKER_SCHEMA = 2
SANITIZER_REPORT_RELATIVE = Path("migration-reports/resource-sanitization.json")
RUNTIME_MANIFEST_RELATIVE = Path("migration-reports/runtime-mod-manifest.json")
INPUT_MODS_MANIFEST_RELATIVE = Path("migration-reports/server-mods-input-manifest.json")
TARGET_READY_MARKER_RELATIVE = Path("migration-reports/production-target-ready.json")
HEX_SHA256 = re.compile(r"^[0-9A-Fa-f]{64}$")


class AssemblyError(RuntimeError):
    """The target cannot be published under the production contract."""


def _load_tool(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssemblyError(f"cannot load required tool: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(BUFFER_SIZE), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _path_exists(path: Path) -> bool:
    """Return true for regular paths and dangling links/reparse points."""
    return os.path.lexists(path)


def _is_link_or_junction(path: Path) -> bool:
    try:
        is_junction = getattr(path, "is_junction", lambda: False)
        return path.is_symlink() or bool(is_junction())
    except OSError:
        # An unreadable reparse candidate is not safe to follow during release.
        return True


def _reject_reparse_components(path: Path, label: str) -> None:
    """Reject symlinks and Windows junctions in every existing path component."""
    candidate = path if path.is_absolute() else Path.cwd() / path
    for component in (candidate, *candidate.parents):
        if _is_link_or_junction(component):
            raise AssemblyError(
                f"{label} contains a symbolic link or junction: {component}"
            )


def _resolved_no_reparse(path: Path, label: str) -> Path:
    _reject_reparse_components(Path(path), label)
    return Path(path).resolve()


def _path_identity(path: Path, label: str) -> tuple[int, int, int]:
    """Return an identity that survives rename but changes on path replacement."""
    path = Path(path)
    _reject_reparse_components(path, label)
    if _is_link_or_junction(path):
        raise AssemblyError(f"{label} is a symbolic link or junction: {path}")
    try:
        value = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise AssemblyError(f"cannot inspect {label}: {path}") from exc
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _assert_path_identity(
    path: Path, expected: tuple[int, int, int], label: str
) -> None:
    if _path_identity(path, label) != expected:
        raise AssemblyError(
            f"{label} was replaced by another filesystem object: {path}"
        )


def _stable_file(path: Path, label: str) -> dict[str, Any]:
    path = Path(path)
    _reject_reparse_components(path, label)
    if not path.is_file():
        raise AssemblyError(f"{label} is missing or is not a regular file: {path}")
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    _reject_reparse_components(path, label)
    signature = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_signature = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if signature != after_signature:
        raise AssemblyError(f"{label} changed while it was hashed: {path}")
    return {
        "path": str(path.resolve()),
        "bytes": after.st_size,
        "device": after.st_dev,
        "file_id": after.st_ino,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "sha256": digest,
    }


def _assert_file_unchanged(path: Path, expected: dict[str, Any], label: str) -> None:
    current = _stable_file(path, label)
    if any(
        current[key] != expected[key]
        for key in ("bytes", "device", "file_id", "mtime_ns", "ctime_ns", "sha256")
    ):
        raise AssemblyError(f"{label} changed during production assembly: {path}")


def _inside(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _assert_disjoint(target: Path, roots: list[Path]) -> None:
    for root in roots:
        if _inside(target, root) or _inside(root, target):
            raise AssemblyError(f"target must not overlap protected input: {root}")


def _assert_pairwise_disjoint(paths: list[tuple[Path, str]]) -> None:
    for index, (left, left_label) in enumerate(paths):
        for right, right_label in paths[index + 1 :]:
            if _inside(left, right) or _inside(right, left):
                raise AssemblyError(
                    f"protected paths overlap: {left_label}={left}, {right_label}={right}"
                )


def _iter_regular_tree_files(root: Path) -> list[Path]:
    """Walk without following symlinks, junctions, or other reparse points."""
    root = Path(root)
    _reject_reparse_components(root, "tree")
    if not root.is_dir():
        raise AssemblyError(f"tree is missing or not a directory: {root}")
    files: list[Path] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        _reject_reparse_components(directory, "tree")
        try:
            with os.scandir(directory) as stream:
                entries = sorted(stream, key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise AssemblyError(f"cannot scan assembled tree: {directory}") from exc
        for entry in entries:
            path = Path(entry.path)
            if _is_link_or_junction(path):
                raise AssemblyError(
                    f"symbolic links and junctions are not allowed in an assembled tree: {path}"
                )
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(path)
                else:
                    raise AssemblyError(
                        f"special/non-regular entry is not allowed in an assembled tree: {path}"
                    )
            except OSError as exc:
                raise AssemblyError(
                    f"cannot inspect assembled tree entry: {path}"
                ) from exc
    return sorted(files, key=lambda item: item.relative_to(root).as_posix().casefold())


def _tree_summary(root: Path) -> dict[str, Any]:
    root = _resolved_no_reparse(Path(root), "tree")
    if not root.is_dir():
        raise AssemblyError(f"tree is missing, symlinked, or not a directory: {root}")
    digest = hashlib.sha256()
    count = total = 0
    for path in _iter_regular_tree_files(root):
        relative = path.relative_to(root).as_posix()
        checked = _stable_file(path, f"tree file {relative}")
        size = checked["bytes"]
        file_digest = checked["sha256"]
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
        count += 1
        total += size
    return {
        "files": count,
        "bytes": total,
        "tree_sha256": digest.hexdigest().upper(),
    }


def _copy_tree_verified(source: Path, destination: Path) -> dict[str, Any]:
    source = _resolved_no_reparse(Path(source), "copy source")
    destination = Path(destination)
    _reject_reparse_components(destination, "copy destination")
    if _path_exists(destination):
        raise AssemblyError(f"copy destination already exists: {destination}")
    if not source.is_dir():
        raise AssemblyError(
            f"copy source is missing, symlinked, or not a directory: {source}"
        )
    before = _tree_summary(source)
    try:
        shutil.copytree(
            source,
            destination,
            copy_function=shutil.copy2,
            symlinks=False,
            ignore_dangling_symlinks=False,
        )
    except (OSError, shutil.Error) as exc:
        raise AssemblyError(f"failed to copy tree: {source} -> {destination}") from exc
    after_source = _tree_summary(source)
    copied = _tree_summary(destination)
    if before != after_source:
        raise AssemblyError(f"copy source changed while it was assembled: {source}")
    if before != copied:
        raise AssemblyError(f"copied tree failed content verification: {destination}")
    return before


def _copy_file_verified(source: Path, destination: Path) -> dict[str, Any]:
    source = Path(source)
    destination = Path(destination)
    _reject_reparse_components(source, "copy source")
    _reject_reparse_components(destination, "copy destination")
    if _path_exists(destination):
        raise AssemblyError(f"copy destination already exists: {destination}")
    if _is_link_or_junction(source) or not source.is_file():
        raise AssemblyError(
            f"copy source is missing, symlinked, or not a file: {source}"
        )
    before = _stable_file(source, "copy source")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    _assert_file_unchanged(source, before, "copy source")
    copied = _stable_file(destination, "copied file")
    if copied["bytes"] != before["bytes"] or copied["sha256"] != before["sha256"]:
        raise AssemblyError(f"copied file failed content verification: {destination}")
    return {"bytes": before["bytes"], "sha256": before["sha256"]}


def _bundle_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["file"].lower()):
        digest.update(row["file"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def _read_json_stable(path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = _stable_file(path, label)
    try:
        value = json.loads(Path(path).read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssemblyError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AssemblyError(f"{label} must contain a JSON object: {path}")
    _assert_file_unchanged(path, summary, label)
    return value, summary


def _validate_manifest_filename(name: object, seen: set[str]) -> str:
    if not isinstance(name, str) or not name or len(name) > 240:
        raise AssemblyError("server bundle manifest contains an invalid filename")
    windows = PureWindowsPath(name)
    if (
        windows.name != name
        or windows.is_absolute()
        or windows.drive
        or any(part in {"", ".", ".."} for part in windows.parts)
        or "/" in name
        or "\\" in name
        or name.casefold() in seen
        or not name.casefold().endswith(".jar")
    ):
        raise AssemblyError(
            "server bundle manifest contains an unsafe or duplicate filename"
        )
    seen.add(name.casefold())
    return name


def validate_mod_bundle(mods: Path, manifest_path: Path) -> dict[str, Any]:
    mods = _resolved_no_reparse(Path(mods), "server mods directory")
    if not mods.is_dir():
        raise AssemblyError(f"server mods directory is invalid: {mods}")
    manifest_path = Path(manifest_path)
    manifest, manifest_summary = _read_json_stable(
        manifest_path, "server bundle manifest"
    )
    if manifest.get("schema") != 1 or manifest.get("side") != "server":
        raise AssemblyError("server bundle manifest has the wrong schema or side")
    expected_rows = manifest.get("files")
    if not isinstance(expected_rows, list) or not expected_rows:
        raise AssemblyError("server bundle manifest has no files")
    expected: dict[str, dict[str, Any]] = {}
    seen_names: set[str] = set()
    for row in expected_rows:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise AssemblyError("server bundle manifest contains an invalid row")
        name = _validate_manifest_filename(row["file"], seen_names)
        if type(row.get("bytes")) is not int or row["bytes"] < 0:
            raise AssemblyError(
                f"server bundle manifest has invalid byte count: {name}"
            )
        if not isinstance(row.get("sha256"), str) or not HEX_SHA256.fullmatch(
            row["sha256"]
        ):
            raise AssemblyError(f"server bundle manifest has invalid SHA-256: {name}")
        expected[name] = row
    try:
        entries = list(mods.iterdir())
    except OSError as exc:
        raise AssemblyError(f"cannot enumerate server mods directory: {mods}") from exc
    actual: dict[str, Path] = {}
    actual_casefold: set[str] = set()
    for path in entries:
        if _is_link_or_junction(path) or not path.is_file():
            raise AssemblyError(
                "server mods directory contains a non-file or symbolic link"
            )
        if path.name.casefold() in actual_casefold:
            raise AssemblyError(
                "server mods directory contains case-colliding filenames"
            )
        actual_casefold.add(path.name.casefold())
        actual[path.name] = path
    if set(actual) != set(expected):
        raise AssemblyError(
            "server mods directory does not match the locked manifest filenames"
        )
    rows: list[dict[str, Any]] = []
    for name in sorted(expected, key=str.lower):
        path = actual[name]
        row = expected[name]
        checked = _stable_file(path, f"server bundle JAR {name}")
        digest = checked["sha256"]
        if (
            row.get("bytes") != checked["bytes"]
            or str(row.get("sha256", "")).upper() != digest
        ):
            raise AssemblyError(f"server JAR differs from locked manifest: {name}")
        rows.append({"file": name, "bytes": checked["bytes"], "sha256": digest})
    bundle = _bundle_digest(rows)
    if (
        manifest.get("file_count") != len(rows)
        or str(manifest.get("bundle_sha256", "")).upper() != bundle
    ):
        raise AssemblyError(
            "server bundle aggregate digest does not match the manifest"
        )
    _assert_file_unchanged(manifest_path, manifest_summary, "server bundle manifest")
    return {
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": manifest_summary["sha256"],
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": bundle,
    }


def _rewrite_prefix(value: Any, before: Path, after: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: _rewrite_prefix(item, before, after) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rewrite_prefix(item, before, after) for item in value]
    if isinstance(value, str):
        before_text = str(before.resolve()).replace("\\", "/")
        after_text = str(after.resolve()).replace("\\", "/")
        normalized = value.replace("\\", "/")
        folded = normalized.casefold() if os.name == "nt" else normalized
        before_folded = before_text.casefold() if os.name == "nt" else before_text
        if folded == before_folded or folded.startswith(before_folded + "/"):
            suffix = normalized[len(before_text) :]
            rewritten = after_text + suffix
            # Keep the report's original separator convention.  Sanitizer
            # reports commonly use Path.as_posix() even on Windows.
            if "\\" in value and "/" not in value:
                rewritten = rewritten.replace("/", "\\")
            return rewritten
    return value


def _contains_prefix(value: Any, prefix: Path) -> bool:
    if isinstance(value, dict):
        return any(_contains_prefix(item, prefix) for item in value.values())
    if isinstance(value, list):
        return any(_contains_prefix(item, prefix) for item in value)
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        expected = str(prefix.resolve()).replace("\\", "/")
        folded = normalized.casefold() if os.name == "nt" else normalized
        expected = expected.casefold() if os.name == "nt" else expected
        return folded == expected or folded.startswith(expected + "/")
    return False


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path = Path(path)
    _reject_reparse_components(path.parent, "JSON evidence parent")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    _reject_reparse_components(temporary, "temporary JSON evidence path")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with temporary.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_temp(path: Path, value: dict[str, Any]) -> Path:
    """Write evidence beside its final path without replacing the final file."""
    path = Path(path)
    _reject_reparse_components(path.parent, "evidence report parent")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".pending-" + uuid.uuid4().hex)
    _reject_reparse_components(temporary, "temporary evidence path")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with temporary.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _rename_no_replace(source: Path, destination: Path, label: str) -> None:
    """Publish with no-clobber semantics (Windows rename is atomic/no-replace)."""
    _reject_reparse_components(source, f"{label} source")
    _reject_reparse_components(destination, f"{label} destination")
    if _path_exists(destination):
        raise AssemblyError(f"{label} destination already exists: {destination}")
    try:
        # The production host is Windows, where os.rename refuses to replace
        # an existing directory/file.  The preflight plus a single rename also
        # keeps the target invisible until all staged bytes are complete.
        os.rename(source, destination)
    except FileExistsError as exc:
        raise AssemblyError(
            f"{label} destination appeared during publication: {destination}"
        ) from exc


def _safe_remove_tree(
    path: Path, expected_identity: tuple[int, int, int] | None = None
) -> None:
    """Remove only a newly-created tree, never traversing a reparse point."""
    path = Path(path)
    if not _path_exists(path):
        return
    if expected_identity is not None:
        _assert_path_identity(path, expected_identity, "rollback tree")
    if _is_link_or_junction(path):
        try:
            path.unlink()
        except (IsADirectoryError, PermissionError):
            path.rmdir()
        return
    if not path.is_dir():
        path.unlink()
        return
    with os.scandir(path) as stream:
        children = [Path(entry.path) for entry in stream]
    for child in children:
        _safe_remove_tree(child)
    path.rmdir()


def _remove_owned_path(
    path: Path, expected_identity: tuple[int, int, int], label: str
) -> None:
    """Remove a transaction artifact only while its filesystem identity matches."""
    path = Path(path)
    if not _path_exists(path):
        return
    _assert_path_identity(path, expected_identity, label)
    if stat.S_ISDIR(expected_identity[2]):
        _safe_remove_tree(path, expected_identity)
    else:
        path.unlink()


def _validate_final_marker(
    marker_path: Path, source: Path, staging: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bind the validator input to the final marker in this staging tree."""
    marker_path = Path(marker_path)
    expected_path = staging / FINAL_CONVERSION_MARKER_RELATIVE
    if marker_path.resolve() != expected_path.resolve():
        raise AssemblyError(
            "conversion marker must be staging/migration-reports/conversion-complete.json"
        )
    marker, summary = _read_json_stable(marker_path, "staging final conversion marker")
    if (
        marker.get("schema") != FINAL_CONVERSION_MARKER_SCHEMA
        or marker.get("status") != "CONVERTED_STAGING"
    ):
        raise AssemblyError(
            "staging final conversion marker is not a successful final marker"
        )
    pending = marker.get("pending_saveddata")
    if pending != []:
        raise AssemblyError(
            "staging final conversion marker is preheated or has invalid pending SavedData"
        )
    for key, expected in (("source_root", source), ("staging_root", staging)):
        value = marker.get(key)
        if not isinstance(value, str) or Path(value).resolve() != expected.resolve():
            raise AssemblyError(
                f"staging final conversion marker {key} does not match inputs"
            )
    report_value = marker.get("conversion_report")
    report_hash = marker.get("conversion_report_sha256")
    if not isinstance(report_value, str) or not isinstance(report_hash, str):
        raise AssemblyError(
            "staging final conversion marker lacks conversion report binding"
        )
    if not HEX_SHA256.fullmatch(report_hash):
        raise AssemblyError(
            "staging final conversion marker has an invalid report hash"
        )
    conversion_report = Path(report_value)
    _reject_reparse_components(conversion_report, "staging conversion report")
    if _inside(conversion_report, source):
        raise AssemblyError("staging conversion report must not be inside source")
    report_summary = _stable_file(conversion_report, "staging conversion report")
    if report_summary["sha256"] != report_hash.upper():
        raise AssemblyError("staging conversion report hash does not match its marker")
    return marker, summary, report_summary


def _validate_runtime_manifest(mods: Path, manifest: object) -> dict[str, Any]:
    """Validate the post-sanitizer runtime JAR manifest against physical files."""
    if not isinstance(manifest, dict):
        raise AssemblyError("target sanitizer omitted runtime_mod_manifest")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise AssemblyError("target runtime mod manifest has no files")
    expected: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise AssemblyError("target runtime mod manifest has an invalid row")
        name = _validate_manifest_filename(row.get("file"), seen)
        if type(row.get("bytes")) is not int or row["bytes"] < 0:
            raise AssemblyError(
                f"target runtime mod manifest has invalid bytes: {name}"
            )
        if not isinstance(row.get("sha256"), str) or not HEX_SHA256.fullmatch(
            row["sha256"]
        ):
            raise AssemblyError(
                f"target runtime mod manifest has invalid SHA-256: {name}"
            )
        expected[name] = row
    mods = _resolved_no_reparse(Path(mods), "target mods directory")
    actual: dict[str, Path] = {}
    for path in mods.iterdir():
        if _is_link_or_junction(path) or not path.is_file():
            raise AssemblyError(f"target mods contains a non-regular entry: {path}")
        actual[path.name] = path
    if set(actual) != set(expected):
        raise AssemblyError(
            "target runtime mod manifest filenames do not match target mods"
        )
    rows_for_digest: list[dict[str, Any]] = []
    for name in sorted(expected, key=str.lower):
        path = actual[name]
        checked = _stable_file(path, f"target runtime JAR {name}")
        digest = checked["sha256"]
        row = expected[name]
        if row["bytes"] != checked["bytes"] or row["sha256"].upper() != digest:
            raise AssemblyError(
                f"target JAR differs from post-sanitizer manifest: {name}"
            )
        rows_for_digest.append(
            {"file": name, "bytes": checked["bytes"], "sha256": digest}
        )
    bundle = _bundle_digest(rows_for_digest)
    if manifest.get("file_count") != len(rows_for_digest):
        raise AssemblyError("target runtime mod manifest file_count is inconsistent")
    if manifest.get("bytes") != sum(row["bytes"] for row in rows_for_digest):
        raise AssemblyError("target runtime mod manifest byte total is inconsistent")
    if str(manifest.get("bundle_sha256", "")).upper() != bundle:
        raise AssemblyError(
            "target runtime mod manifest aggregate digest is inconsistent"
        )
    return {
        "file_count": len(rows_for_digest),
        "bytes": sum(row["bytes"] for row in rows_for_digest),
        "bundle_sha256": bundle,
    }


def _validate_sanitizer_result(result: object, temporary: Path) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "SANITIZED_TARGET_COPY":
        raise AssemblyError("target sanitizer did not return SANITIZED_TARGET_COPY")
    if result.get("protected_tree_unchanged") is not True:
        raise AssemblyError("target sanitizer did not prove protected trees unchanged")
    nested = result.get("resource_sanitization")
    if not isinstance(nested, dict) or nested.get("status") not in {
        "SANITIZED",
        "ALREADY_CLEAN",
    }:
        raise AssemblyError("target sanitizer returned a conditional resource result")
    expected_target = temporary.resolve()
    expected_mods = (temporary / "mods").resolve()
    for key, expected in (
        ("target_game_dir", expected_target),
        ("target_mods_dir", expected_mods),
    ):
        value = result.get(key)
        if not isinstance(value, str) or Path(value).resolve() != expected:
            raise AssemblyError(
                f"target sanitizer {key} is not the unpublished target copy"
            )
    # Validate every reported mutation before path rewriting.  This catches a
    # malicious/custom sanitizer trying to smuggle a source or staging path.
    changes = nested.get("changes", [])
    if not isinstance(changes, list):
        raise AssemblyError("target sanitizer changes must be a list")
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            raise AssemblyError("target sanitizer returned an invalid change record")
        changed = Path(change["path"])
        _reject_reparse_components(changed, "target sanitizer change")
        if not _inside(changed, expected_target):
            raise AssemblyError(
                "target sanitizer changed a path outside the unpublished target"
            )
    _validate_runtime_manifest(expected_mods, nested.get("runtime_mod_manifest"))
    # A full walk after sanitizer makes junction insertion fail before publish.
    _tree_summary(expected_target)
    return result


def assemble(
    source: Path,
    staging: Path,
    runtime_template: Path,
    mods: Path,
    mods_manifest: Path,
    baseline: Path,
    conversion_marker: Path,
    output: Path,
    report: Path,
    *,
    conversion_validator: Callable[..., Any] | None = None,
    sanitizer: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    raw_paths = {
        "source-game-dir": Path(source),
        "verified-staging": Path(staging),
        "runtime-template": Path(runtime_template),
        "server-mods": Path(mods),
        "server-mods-manifest": Path(mods_manifest),
        "baseline-manifest": Path(baseline),
        "conversion-marker": Path(conversion_marker),
        "output": Path(output),
        "assembly-report": Path(report),
    }
    for label, path in raw_paths.items():
        _reject_reparse_components(path, label)

    source = _resolved_no_reparse(raw_paths["source-game-dir"], "source-game-dir")
    staging = _resolved_no_reparse(raw_paths["verified-staging"], "verified-staging")
    runtime_template = _resolved_no_reparse(
        raw_paths["runtime-template"], "runtime-template"
    )
    mods = _resolved_no_reparse(raw_paths["server-mods"], "server-mods")
    output = raw_paths["output"].resolve()
    report = raw_paths["assembly-report"].resolve()
    mods_manifest = raw_paths["server-mods-manifest"]
    baseline = raw_paths["baseline-manifest"]
    conversion_marker = raw_paths["conversion-marker"]

    protected_named = [
        (source, "source-game-dir"),
        (staging, "verified-staging"),
        (runtime_template, "runtime-template"),
        (mods, "server-mods"),
    ]
    _assert_pairwise_disjoint(protected_named)
    for path, label in protected_named:
        if not path.is_dir():
            raise AssemblyError(f"required input directory is missing: {path}")

    if _path_exists(output):
        raise AssemblyError(f"refusing to overwrite production target: {output}")
    if _path_exists(report):
        raise AssemblyError(f"refusing to overwrite assembly report: {report}")
    _assert_disjoint(output, [path for path, _label in protected_named])
    _assert_disjoint(report, [path for path, _label in protected_named] + [output])

    # The final marker is deliberately constrained to the verified staging
    # tree.  Baseline and bundle manifests are immutable audit inputs and may
    # live beside (but never inside) a protected tree.
    expected_marker = staging / FINAL_CONVERSION_MARKER_RELATIVE
    if conversion_marker.resolve() != expected_marker.resolve():
        raise AssemblyError(
            "conversion-marker must be verified-staging/migration-reports/conversion-complete.json"
        )
    for path, label in (
        (mods_manifest, "server-mods-manifest"),
        (baseline, "baseline-manifest"),
    ):
        _reject_reparse_components(path, label)
        if any(_inside(path, root) for root, _root_label in protected_named):
            raise AssemblyError(
                f"{label} must be outside protected input trees: {path}"
            )

    marker_summary = _stable_file(conversion_marker, "staging final conversion marker")
    baseline_summary = _stable_file(baseline, "baseline manifest")
    bundle_manifest_summary = _stable_file(mods_manifest, "server bundle manifest")

    if conversion_validator is None:
        migration = _load_tool(
            "prepare_fast_migration.py", "production_assembly_migration"
        )
        conversion_validator = migration.validate_final_conversion_gate
    _marker, checked_marker_summary, conversion_report_summary = _validate_final_marker(
        conversion_marker, source, staging
    )
    if checked_marker_summary["sha256"] != marker_summary["sha256"]:
        raise AssemblyError("staging final conversion marker changed during preflight")
    _assert_file_unchanged(
        conversion_marker, marker_summary, "staging final conversion marker"
    )
    _assert_file_unchanged(baseline, baseline_summary, "baseline manifest")
    bundle = validate_mod_bundle(mods, mods_manifest)
    _assert_file_unchanged(
        mods_manifest, bundle_manifest_summary, "server bundle manifest"
    )

    if sanitizer is None:
        migration = _load_tool(
            "prepare_fast_migration.py", "production_assembly_sanitizer"
        )
        sanitizer = migration.sanitize_target_copy

    temporary = output.with_name("." + output.name + ".assembling-" + uuid.uuid4().hex)
    _reject_reparse_components(temporary, "temporary assembly path")
    if _path_exists(temporary):
        raise AssemblyError(f"temporary assembly path already exists: {temporary}")
    _assert_disjoint(temporary, [path for path, _label in protected_named] + [output])
    transaction_id = temporary.name.rsplit("-", 1)[-1]
    copy_manifest: dict[str, Any] = {"runtime": {}, "staging": {}, "mods": None}
    published = False
    report_committed = False
    temporary_identity: tuple[int, int, int] | None = None
    report_pending: Path | None = None
    report_pending_identity: tuple[int, int, int] | None = None
    try:
        temporary.mkdir(parents=True)
        temporary_identity = _path_identity(temporary, "temporary assembly tree")
        libraries = runtime_template / "libraries"
        if _path_exists(libraries) and (
            _is_link_or_junction(libraries) or not libraries.is_dir()
        ):
            raise AssemblyError(
                f"runtime libraries is not a regular directory: {libraries}"
            )
        copy_manifest["runtime"]["libraries"] = _copy_tree_verified(
            libraries, temporary / "libraries"
        )
        launcher_count = 0
        for name in RUNTIME_FILES:
            path = runtime_template / name
            if _path_exists(path):
                if _is_link_or_junction(path) or not path.is_file():
                    raise AssemblyError(f"runtime file is not a regular file: {path}")
                copy_manifest["runtime"][name] = _copy_file_verified(
                    path, temporary / name
                )
                launcher_count += name in {"run.bat", "run.sh"}
        if launcher_count == 0:
            raise AssemblyError("runtime template has neither run.bat nor run.sh")

        for name in STAGING_DIRECTORIES:
            path = staging / name
            if _path_exists(path):
                if _is_link_or_junction(path) or not path.is_dir():
                    raise AssemblyError(
                        f"staging directory is not a regular directory: {path}"
                    )
                copy_manifest["staging"][name] = _copy_tree_verified(
                    path, temporary / name
                )
        for required in ("world", "config"):
            if required not in copy_manifest["staging"]:
                raise AssemblyError(
                    f"required staging directory is missing: {staging / required}"
                )

        for name in STAGING_FILES:
            path = staging / name
            if _path_exists(path):
                if _is_link_or_junction(path) or not path.is_file():
                    raise AssemblyError(f"staging file is not a regular file: {path}")
                copy_manifest["staging"][name] = _copy_file_verified(
                    path, temporary / name
                )
        if "server.properties" not in copy_manifest["staging"]:
            raise AssemblyError(
                f"required staging file is missing: {staging / 'server.properties'}"
            )

        copy_manifest["mods"] = _copy_tree_verified(mods, temporary / "mods")
        evidence_dir = temporary / "migration-reports"
        _copy_file_verified(
            conversion_marker, evidence_dir / FINAL_CONVERSION_MARKER_RELATIVE.name
        )
        _copy_file_verified(mods_manifest, temporary / INPUT_MODS_MANIFEST_RELATIVE)
        copied_marker = _stable_file(
            evidence_dir / FINAL_CONVERSION_MARKER_RELATIVE.name,
            "copied staging final conversion marker",
        )
        copy_manifest["staging"]["conversion-marker"] = {
            "bytes": copied_marker["bytes"],
            "sha256": copied_marker["sha256"],
        }
        (temporary / "eula.txt").write_text("eula=true\n", encoding="ascii")

        _assert_file_unchanged(
            conversion_marker, marker_summary, "staging final conversion marker"
        )
        _assert_file_unchanged(baseline, baseline_summary, "baseline manifest")
        _assert_file_unchanged(
            mods_manifest, bundle_manifest_summary, "server bundle manifest"
        )

        sanitizer_result = sanitizer(
            source, staging, temporary, temporary / "mods", hash_all=True
        )
        sanitizer_result = _validate_sanitizer_result(sanitizer_result, temporary)
        sanitizer_result = _rewrite_prefix(sanitizer_result, temporary, output)
        if _contains_prefix(sanitizer_result, temporary):
            raise AssemblyError(
                "sanitizer report still contains unpublished temporary paths"
            )

        # Evidence is written while the target is still unpublished.  This
        # ensures a single directory rename exposes a complete target tree.
        sanitizer_path = temporary / SANITIZER_REPORT_RELATIVE
        _atomic_json(sanitizer_path, sanitizer_result)
        runtime_manifest = sanitizer_result["resource_sanitization"][
            "runtime_mod_manifest"
        ]
        runtime_summary = _validate_runtime_manifest(
            temporary / "mods", runtime_manifest
        )
        runtime_path = temporary / RUNTIME_MANIFEST_RELATIVE
        _atomic_json(runtime_path, runtime_manifest)
        target_marker_path = temporary / TARGET_READY_MARKER_RELATIVE
        target_marker_payload = {
            "schema": 1,
            "status": "ASSEMBLY_PREPARED",
            "transaction_id": transaction_id,
            "target_game_dir": str(output),
            "external_report": str(report),
            "staging_final_marker": str(output / FINAL_CONVERSION_MARKER_RELATIVE),
            "sanitizer_report": str(output / SANITIZER_REPORT_RELATIVE),
            "runtime_manifest": str(output / RUNTIME_MANIFEST_RELATIVE),
            "input_mods_manifest": str(output / INPUT_MODS_MANIFEST_RELATIVE),
            "source_game_dir": str(source),
            "verified_staging": str(staging),
            "conversion_marker_sha256": marker_summary["sha256"],
            "baseline_manifest_sha256": baseline_summary["sha256"],
            "server_bundle_manifest_sha256": bundle_manifest_summary["sha256"],
            "server_bundle_sha256": bundle["bundle_sha256"],
            "runtime_bundle_sha256": runtime_summary["bundle_sha256"],
            "ready_to_start": False,
        }
        _atomic_json(target_marker_path, target_marker_payload)
        _tree_summary(temporary)

        # Close the source/staging gate at the last possible pre-publication
        # point. Copy verification protects each copied tree; this final pass
        # catches a stopped-source or marker drift that occurred afterwards.
        _assert_file_unchanged(
            conversion_marker, marker_summary, "staging final conversion marker"
        )
        _assert_file_unchanged(
            Path(conversion_report_summary["path"]),
            conversion_report_summary,
            "staging conversion report",
        )
        _assert_file_unchanged(baseline, baseline_summary, "baseline manifest")
        _assert_file_unchanged(
            mods_manifest, bundle_manifest_summary, "server bundle manifest"
        )
        try:
            conversion_validator(conversion_marker, source, staging, baseline)
        except Exception as exc:
            raise AssemblyError(f"staging final conversion gate failed: {exc}") from exc
        _assert_file_unchanged(
            conversion_marker, marker_summary, "staging final conversion marker"
        )
        _assert_file_unchanged(
            Path(conversion_report_summary["path"]),
            conversion_report_summary,
            "staging conversion report",
        )

        prepared_at = time.perf_counter()
        _assert_path_identity(temporary, temporary_identity, "temporary assembly tree")
        _rename_no_replace(temporary, output, "production target publication")
        published = True
        _assert_path_identity(output, temporary_identity, "published production target")
        published_at = time.perf_counter()
        result = {
            "schema": 1,
            "status": "ASSEMBLED_PRODUCTION_TARGET",
            "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "transaction_id": transaction_id,
            "source_game_dir": str(source),
            "verified_staging": str(staging),
            "runtime_template": str(runtime_template),
            "target_game_dir": str(output),
            "baseline_manifest": str(baseline.resolve()),
            "baseline_manifest_sha256": baseline_summary["sha256"],
            "conversion_marker": str(conversion_marker.resolve()),
            "conversion_marker_sha256": marker_summary["sha256"],
            "server_bundle": bundle,
            "copy_manifest": copy_manifest,
            "sanitizer_report": str(output / SANITIZER_REPORT_RELATIVE),
            "sanitizer_report_sha256": _stable_file(
                output / SANITIZER_REPORT_RELATIVE, "published sanitizer report"
            )["sha256"],
            "runtime_manifest": str(output / RUNTIME_MANIFEST_RELATIVE),
            "runtime_manifest_sha256": _stable_file(
                output / RUNTIME_MANIFEST_RELATIVE, "published runtime manifest"
            )["sha256"],
            "input_mods_manifest": str(output / INPUT_MODS_MANIFEST_RELATIVE),
            "input_mods_manifest_sha256": _stable_file(
                output / INPUT_MODS_MANIFEST_RELATIVE, "copied input mods manifest"
            )["sha256"],
            "target_ready_marker": str(output / TARGET_READY_MARKER_RELATIVE),
            "timing_seconds": {
                "total_through_publish": round(published_at - started, 3),
                "prepublish_prepare": round(prepared_at - started, 3),
                "atomic_publish": round(published_at - prepared_at, 3),
            },
            "ready_to_start": True,
        }
        report_pending = _write_json_temp(report, result)
        report_pending_identity = _path_identity(
            report_pending, "pending assembly report"
        )
        _rename_no_replace(report_pending, report, "assembly report publication")
        report_committed = True
        _assert_path_identity(
            report, report_pending_identity, "published assembly report"
        )

        # Flip the target marker only after the external evidence report is
        # durable.  A crash in either publication window leaves a conspicuous
        # non-ready target rather than something an operator could start.
        target_marker = output / TARGET_READY_MARKER_RELATIVE
        target_marker_payload.update(
            {
                "status": "ASSEMBLED_PRODUCTION_TARGET",
                "ready_to_start": True,
                "assembly_report_sha256": sha256(report),
            }
        )
        _atomic_json(target_marker, target_marker_payload)
        return result
    except BaseException as exc:
        cleanup_errors: list[str] = []
        pending_report_exists = report_pending is not None and _path_exists(
            report_pending
        )
        if report_pending is not None and report_pending_identity is not None:
            try:
                _remove_owned_path(
                    report_pending,
                    report_pending_identity,
                    "pending assembly report rollback",
                )
            except (AssemblyError, OSError) as cleanup_exc:
                cleanup_errors.append(f"pending report cleanup: {cleanup_exc}")
        elif report_pending is not None and _path_exists(report_pending):
            cleanup_errors.append(
                "pending report cleanup: transaction ownership could not be established"
            )
        # If the pending path vanished, rename may have succeeded immediately
        # before an asynchronous exception.  Reclaim only the same file ID.
        report_may_be_published = report_committed or (
            report_pending_identity is not None and not pending_report_exists
        )
        if report_may_be_published and _path_exists(report):
            try:
                assert report_pending_identity is not None
                _remove_owned_path(
                    report,
                    report_pending_identity,
                    "published assembly report rollback",
                )
            except (AssemblyError, OSError) as cleanup_exc:
                cleanup_errors.append(f"assembly report rollback: {cleanup_exc}")
        elif report_may_be_published:
            cleanup_errors.append(
                "assembly report rollback: published report disappeared before rollback"
            )

        temporary_exists = _path_exists(temporary)
        if temporary_exists and temporary_identity is not None:
            try:
                _remove_owned_path(
                    temporary, temporary_identity, "temporary assembly tree rollback"
                )
            except (AssemblyError, OSError) as cleanup_exc:
                cleanup_errors.append(f"temporary tree cleanup: {cleanup_exc}")
        elif temporary_exists:
            cleanup_errors.append(
                "temporary tree cleanup: transaction ownership could not be established"
            )

        # The missing temporary path also covers an exception delivered in the
        # tiny window after rename but before ``published`` was assigned.
        target_may_be_published = temporary_identity is not None and (
            published or not temporary_exists
        )
        if target_may_be_published and _path_exists(output):
            try:
                assert temporary_identity is not None
                _remove_owned_path(
                    output,
                    temporary_identity,
                    "published production target rollback",
                )
            except (AssemblyError, OSError) as cleanup_exc:
                cleanup_errors.append(f"published target rollback: {cleanup_exc}")
        elif target_may_be_published:
            cleanup_errors.append(
                "published target rollback: published target disappeared before rollback"
            )
        if cleanup_errors:
            raise AssemblyError(
                f"assembly failed and rollback was incomplete: {type(exc).__name__}: {exc}; "
                + "; ".join(cleanup_errors)
            ) from exc
        raise


def _d_path(path: Path, label: str) -> Path:
    resolved = _resolved_no_reparse(Path(path), label)
    if resolved.drive.upper() != "D:":
        raise AssemblyError(f"{label} must be on D: {resolved}")
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--verified-staging", type=Path, required=True)
    parser.add_argument("--runtime-template", type=Path, required=True)
    parser.add_argument("--server-mods", type=Path, required=True)
    parser.add_argument("--server-mods-manifest", type=Path, required=True)
    parser.add_argument("--baseline-manifest", type=Path, required=True)
    parser.add_argument("--conversion-marker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = assemble(
            _d_path(args.source_game_dir, "source-game-dir"),
            _d_path(args.verified_staging, "verified-staging"),
            _d_path(args.runtime_template, "runtime-template"),
            _d_path(args.server_mods, "server-mods"),
            _d_path(args.server_mods_manifest, "server-mods-manifest"),
            _d_path(args.baseline_manifest, "baseline-manifest"),
            _d_path(args.conversion_marker, "conversion-marker"),
            _d_path(args.output, "output"),
            _d_path(args.report, "report"),
        )
    except (AssemblyError, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps({"status": result["status"], "target": result["target_game_dir"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
