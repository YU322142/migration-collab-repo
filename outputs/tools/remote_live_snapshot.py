#!/usr/bin/env python3
"""Mirror a live Minecraft server's migration inputs without touching its source.

The command has two deliberately separate modes:

* preheat reads an online (or stopped) source and publishes a fresh local
  raw-input mirror by renaming a fully verified temporary tree. A changing
  source aborts the publication rather than producing a false baseline.
* refresh requires a stopped/unlocked source, hashes it again, and applies
  only added/changed files (and explicitly approved non-critical deletions) to
  the existing mirror through the audited file transaction helper.

The mirror contains the source-relative migration inputs selected by
prepare_fast_migration.py. It intentionally excludes volatile files such as
session.lock and Ledger SQLite history, so it can be passed as the
<LIVE_SNAPSHOT> source to the normal staging/conversion pipeline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import uuid
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = 1
BUFFER = 4 * 1024 * 1024
MANIFEST_KIND = "remote-live-migration-input-mirror"
REPORT_KIND = "remote-live-migration-input-mirror-operation"
REPARSE_POINT = 0x400
DEFAULT_RETRIES = 3
CRITICAL_DELETIONS = frozenset(
    {
        "world/level.dat",
        "server.properties",
        "EasyAuth/easyauth.db",
    }
)


class SnapshotError(RuntimeError):
    """A fail-closed source, mirror, or transaction condition."""


class SourceChangedError(SnapshotError):
    """The source changed while a stable hash/copy was being prepared."""


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SnapshotError(f"cannot load migration helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_TOOL_ROOT = Path(__file__).resolve().parent
_MIGRATION = _load_module(
    _TOOL_ROOT / "prepare_fast_migration.py", "remote_snapshot_fast_migration"
)
_REMOTE = _load_module(
    _TOOL_ROOT.parent / "remote-cutover-prep-src" / "remote_cutover.py",
    "remote_snapshot_cutover_probe",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(BUFFER)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _signature(path: Path) -> tuple[int, int, int, int]:
    info = path.stat()
    return (info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino)


def _is_linklike(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & REPARSE_POINT
    )


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(_resolved(left))) == os.path.normcase(
        str(_resolved(right))
    )


def _overlap(left: Path, right: Path) -> bool:
    left = _resolved(left)
    right = _resolved(right)
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


def _assert_no_link_ancestors(path: Path, label: str) -> None:
    """Reject symlink/reparse ancestors before any destination is created."""
    current = _resolved(path)
    if not current.exists():
        current = current.parent
    while True:
        if current.exists() and _is_linklike(current):
            raise SnapshotError(f"{label} contains a symlink/reparse point: {current}")
        parent = current.parent
        if parent == current:
            break
        current = parent


def _require_source(source: Path) -> Path:
    source = _resolved(source)
    if _is_linklike(source) or not source.is_dir():
        raise SnapshotError(
            f"source root is missing, linked, or not a directory: {source}"
        )
    _assert_no_link_ancestors(source, "source")
    world = source / "world"
    if _is_linklike(world) or not world.is_dir():
        raise SnapshotError(f"source world is missing or linked: {world}")
    return source


def _require_mirror_parent(mirror: Path) -> Path:
    mirror = _resolved(mirror)
    parent = mirror.parent
    parent.mkdir(parents=True, exist_ok=True)
    _assert_no_link_ancestors(parent, "mirror parent")
    if mirror.exists() and _is_linklike(mirror):
        raise SnapshotError(f"mirror is a symlink/reparse point: {mirror}")
    return mirror


def _require_disjoint_roots(source: Path, mirror: Path) -> tuple[Path, Path]:
    source = _require_source(source)
    mirror = _resolved(mirror)
    if _overlap(source, mirror):
        raise SnapshotError(
            f"source and local mirror must be disjoint; source={source}, mirror={mirror}"
        )
    # Check the mirror path and every existing parent before creating anything.
    _assert_no_link_ancestors(mirror.parent, "mirror parent")
    if mirror.exists() and _is_linklike(mirror):
        raise SnapshotError(f"mirror is a symlink/reparse point: {mirror}")
    return source, mirror


def _require_external(source: Path, mirror: Path, path: Path, label: str) -> Path:
    path = _resolved(path)
    if _overlap(path, source) or _overlap(path, mirror):
        raise SnapshotError(f"{label} must be outside both source and mirror: {path}")
    _assert_no_link_ancestors(path.parent, label)
    if path.exists() and _is_linklike(path):
        raise SnapshotError(f"{label} is a symlink/reparse point: {path}")
    return path


def _validate_relative(value: str) -> str:
    try:
        normalized = _MIGRATION.normalized_relative(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"unsafe migration input path: {value!r}") from exc
    return normalized


def _assert_input_tree_safe(source: Path) -> None:
    """Reject links in every tree that can contribute migration inputs."""
    roots = tuple(_MIGRATION.COPY_DIRECTORIES) + tuple(_MIGRATION.LEGACY_DIMENSIONS)
    for name in roots:
        root = source / name
        if not root.exists():
            continue
        if _is_linklike(root) or not root.is_dir():
            raise SnapshotError(
                f"migration input tree is linked or not a directory: {root}"
            )
        for current_text, dir_names, file_names in os.walk(
            root, topdown=True, followlinks=False
        ):
            current = Path(current_text)
            for name_in_dir in list(dir_names):
                child = current / name_in_dir
                if _is_linklike(child) or not child.is_dir():
                    raise SnapshotError(
                        f"migration input tree contains linked/non-directory entry: {child}"
                    )
            for name_in_dir in file_names:
                child = current / name_in_dir
                if _is_linklike(child) or not child.is_file():
                    raise SnapshotError(
                        f"migration input tree contains linked/non-regular entry: {child}"
                    )
    for relative in _MIGRATION.COPY_FILES:
        path = source / relative
        if path.exists() and (_is_linklike(path) or not path.is_file()):
            raise SnapshotError(f"migration input is linked/non-regular: {path}")
    for name in _MIGRATION.AUTH_DATABASE_FILES:
        path = source / "EasyAuth" / name
        if path.exists() and (_is_linklike(path) or not path.is_file()):
            raise SnapshotError(f"authentication input is linked/non-regular: {path}")


def input_paths(root: Path) -> list[tuple[str, str, Path]]:
    root = _resolved(root)
    _assert_input_tree_safe(root)
    try:
        records = _MIGRATION.source_input_paths(root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise SnapshotError(f"cannot enumerate migration inputs: {exc}") from exc
    result: list[tuple[str, str, Path]] = []
    seen_casefold: dict[str, str] = {}
    for source_relative, _target_relative, path in records:
        source_relative = _validate_relative(source_relative)
        # A raw mirror preserves the source layout. prepare_fast_migration will
        # apply its staging-only target mapping later.
        target_relative = source_relative
        if _is_linklike(path) or not path.is_file():
            raise SnapshotError(
                f"migration input is missing/linked/non-regular: {path}"
            )
        try:
            _resolved(path).relative_to(root)
        except ValueError as exc:
            raise SnapshotError(f"migration input escapes source root: {path}") from exc
        folded = source_relative.casefold()
        previous = seen_casefold.get(folded)
        if previous is not None and previous != source_relative:
            raise SnapshotError(
                f"case-insensitive migration input collision: {previous} / {source_relative}"
            )
        seen_casefold[folded] = source_relative
        result.append((source_relative, target_relative, _resolved(path)))
    return sorted(result, key=lambda row: row[0])


def snapshot_digest(entries: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item["source"]):
        for key in ("source", "target", "kind", "bytes", "sha256"):
            digest.update(str(entry[key]).encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _entry(
    source_relative: str,
    target_relative: str,
    digest: str,
    signature: tuple[int, int, int, int],
) -> dict[str, Any]:
    return {
        "source": source_relative,
        "target": target_relative,
        "kind": _MIGRATION.classify_input(source_relative),
        "bytes": signature[0],
        "mtime_ns": signature[1],
        "sha256": digest,
    }


def stable_source_entry(
    source_relative: str,
    target_relative: str,
    path: Path,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Hash a source twice and require both bytes and metadata to be stable."""
    last_error = ""
    for attempt in range(max(1, retries)):
        try:
            if _is_linklike(path) or not path.is_file():
                raise SnapshotError(f"source input became linked/missing: {path}")
            _assert_no_link_ancestors(path.parent, "source input")
            before = _signature(path)
            first_hash = sha256_file(path)
            middle = _signature(path)
            second_hash = sha256_file(path)
            after = _signature(path)
        except (FileNotFoundError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        if before == middle == after and first_hash == second_hash:
            return _entry(
                _validate_relative(source_relative),
                _validate_relative(target_relative),
                second_hash,
                after,
            )
        last_error = f"source changed while hashing (attempt {attempt + 1})"
    raise SourceChangedError(
        f"source input could not be stabilized: {source_relative}; {last_error}"
    )


def source_snapshot(
    source: Path,
    *,
    label: str,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    source = _require_source(source)
    last_error = ""
    for attempt in range(max(1, retries)):
        try:
            pairs = input_paths(source)
            entries = [
                stable_source_entry(relative, target, path, retries)
                for relative, target, path in pairs
            ]
            after_pairs = input_paths(source)
        except SourceChangedError as exc:
            last_error = str(exc)
            continue
        before_keys = [(row[0], row[1]) for row in pairs]
        after_keys = [(row[0], row[1]) for row in after_pairs]
        if before_keys != after_keys:
            last_error = "migration input set changed while hashing"
            continue
        unsupported = sorted(
            row["source"]
            for row in entries
            if row.get("kind") == "unsupported-world-region"
        )
        if unsupported:
            raise SnapshotError(
                "source contains unsupported world-region migration inputs: "
                + ", ".join(unsupported[:10])
            )
        return {
            "schema": SCHEMA,
            "kind": MANIFEST_KIND,
            "source_root": str(source),
            "source_label": label,
            "created_unix_ns": time.time_ns(),
            "file_count": len(entries),
            "bytes": sum(row["bytes"] for row in entries),
            "snapshot_sha256": snapshot_digest(entries),
            "entries": entries,
            "attempts": attempt + 1,
        }
    raise SourceChangedError(
        f"source migration inputs did not stabilize after {max(1, retries)} attempts: {last_error}"
    )


def _atomic_copy_verified(
    source: Path,
    destination: Path,
    expected: dict[str, Any],
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Copy one file into a temporary destination and prove source stability."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_link_ancestors(destination.parent, "mirror destination")
    last_error = ""
    for attempt in range(max(1, retries)):
        temporary = destination.with_name(
            f".{destination.name}.copy-{uuid.uuid4().hex}.tmp"
        )
        try:
            if _is_linklike(source) or not source.is_file():
                raise SnapshotError(f"source input became linked/missing: {source}")
            _assert_no_link_ancestors(source.parent, "source input")
            before = _signature(source)
            first_hash = sha256_file(source)
            with source.open("rb") as reader, temporary.open("xb") as writer:
                while True:
                    block = reader.read(BUFFER)
                    if not block:
                        break
                    writer.write(block)
                writer.flush()
                os.fsync(writer.fileno())
            copied_hash = sha256_file(temporary)
            second_hash = sha256_file(source)
            after = _signature(source)
            if (
                before != after
                or first_hash != second_hash
                or copied_hash != second_hash
            ):
                last_error = f"source changed while copying (attempt {attempt + 1})"
                continue
            if copied_hash != expected["sha256"] or after[0] != expected["bytes"]:
                raise SourceChangedError(
                    f"source no longer matches prepared snapshot: {source}"
                )
            os.utime(temporary, ns=(after[1], after[1]))
            os.replace(temporary, destination)
            return _entry(
                expected["source"],
                expected["target"],
                copied_hash,
                (after[0], after[1], after[2], after[3]),
            )
        except FileNotFoundError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        finally:
            temporary.unlink(missing_ok=True)
    raise SourceChangedError(
        f"could not copy a stable source file: {source}; {last_error}"
    )


def _manifest_payload(
    source: Path,
    mirror: Path,
    label: str,
    snapshot: dict[str, Any],
    *,
    operation: str,
    session_probe: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": MANIFEST_KIND,
        "source_root": str(_resolved(source)),
        "source_label": label,
        "mirror_root": str(_resolved(mirror)),
        "created_unix_ns": time.time_ns(),
        "created_by": "remote_live_snapshot.py",
        "last_operation": operation,
        "session_lock": session_probe,
        "file_count": snapshot["file_count"],
        "bytes": snapshot["bytes"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "entries": snapshot["entries"],
    }


def atomic_json(path: Path, value: object) -> None:
    path = _resolved(path)
    if path.exists() and _is_linklike(path):
        raise SnapshotError(f"report/manifest is a symlink/reparse point: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_link_ancestors(path.parent, "report/manifest parent")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_bytes(path: Path, value: bytes) -> None:
    path = _resolved(path)
    if path.exists() and _is_linklike(path):
        raise SnapshotError(f"output is a symlink/reparse point: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _base_report(
    operation: str, source: Path, mirror: Path, manifest: Path
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "kind": REPORT_KIND,
        "operation": operation,
        "source_root": str(_resolved(source)),
        "mirror_root": str(_resolved(mirror)),
        "manifest": str(_resolved(manifest)),
        "started_unix_ns": time.time_ns(),
        "read_only_source": True,
        "source_writes": 0,
    }


def _failure(
    report: dict[str, Any], status: str, error: Exception | str
) -> dict[str, Any]:
    report = dict(report)
    report["status"] = status
    report["exit_code"] = 2
    report["error"] = (
        error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    )
    report["finished_unix_ns"] = time.time_ns()
    return report


def _success(report: dict[str, Any], status: str) -> dict[str, Any]:
    report = dict(report)
    report["status"] = status
    report["exit_code"] = 0
    report["finished_unix_ns"] = time.time_ns()
    return report


def _probe(source: Path) -> dict[str, Any]:
    try:
        value = _REMOTE.probe_session_lock(_resolved(source) / "world")
    except Exception as exc:
        raise SnapshotError(f"session.lock read-only probe failed: {exc}") from exc
    if not isinstance(value, dict) or value.get("status") not in {
        "ABSENT",
        "UNLOCKED",
        "HELD",
    }:
        raise SnapshotError(f"session.lock probe returned an invalid result: {value!r}")
    return dict(value)


def _require_stopped(source: Path) -> dict[str, Any]:
    probe = _probe(source)
    if probe["status"] not in {"ABSENT", "UNLOCKED"}:
        raise SnapshotError(
            "refresh requires a stopped/unlocked source; "
            f"session.lock status is {probe['status']}"
        )
    return probe


def _orphan_transactions(mirror: Path) -> list[str]:
    parent = _resolved(mirror).parent
    prefix = f".{_resolved(mirror).name}.refresh-"
    return [
        str(path)
        for path in sorted(
            parent.glob(prefix + "*"), key=lambda item: str(item).casefold()
        )
        if path.is_dir() and not _is_linklike(path)
    ]


def _validate_manifest(
    manifest_path: Path,
    source: Path,
    mirror: Path,
) -> dict[str, Any]:
    manifest_path = _resolved(manifest_path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(
            f"cannot read mirror manifest: {manifest_path}: {exc}"
        ) from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise SnapshotError("mirror manifest has an unsupported schema")
    if value.get("kind") != MANIFEST_KIND:
        raise SnapshotError("mirror manifest kind is not recognized")
    if not _same_path(Path(str(value.get("source_root", ""))), source):
        raise SnapshotError("mirror manifest source root does not match current source")
    if not _same_path(Path(str(value.get("mirror_root", ""))), mirror):
        raise SnapshotError("mirror manifest mirror root does not match current mirror")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise SnapshotError("mirror manifest entries must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    folded: dict[str, str] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise SnapshotError("mirror manifest contains a non-object entry")
        source_relative = _validate_relative(raw.get("source"))
        target_relative = _validate_relative(raw.get("target"))
        if source_relative != target_relative:
            raise SnapshotError(
                f"mirror entry is not source-relative (source={source_relative}, target={target_relative})"
            )
        if source_relative in seen:
            raise SnapshotError(f"duplicate mirror manifest entry: {source_relative}")
        prior = folded.get(source_relative.casefold())
        if prior is not None and prior != source_relative:
            raise SnapshotError(
                f"case-insensitive mirror manifest collision: {prior} / {source_relative}"
            )
        folded[source_relative.casefold()] = source_relative
        seen.add(source_relative)
        digest = raw.get("sha256")
        size = raw.get("bytes")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in digest)
            or type(size) is not int
            or size < 0
        ):
            raise SnapshotError(f"invalid mirror manifest hash/size: {source_relative}")
        if raw.get("kind") != _MIGRATION.classify_input(source_relative):
            raise SnapshotError(f"mirror manifest kind mismatch: {source_relative}")
        normalized.append(
            {
                **raw,
                "source": source_relative,
                "target": target_relative,
                "kind": _MIGRATION.classify_input(source_relative),
                "sha256": digest.lower(),
            }
        )
    normalized.sort(key=lambda item: item["source"])
    if value.get("file_count") != len(normalized):
        raise SnapshotError("mirror manifest file count mismatch")
    if value.get("bytes") != sum(row["bytes"] for row in normalized):
        raise SnapshotError("mirror manifest byte count mismatch")
    if value.get("snapshot_sha256") != snapshot_digest(normalized):
        raise SnapshotError("mirror manifest snapshot SHA-256 mismatch")
    return {**value, "entries": normalized}


def _entry_maps(
    before: Iterable[dict[str, Any]], after: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    old = {entry["source"]: entry for entry in before}
    new = {entry["source"]: entry for entry in after}
    added = [new[key] for key in sorted(set(new) - set(old))]
    deleted = [old[key] for key in sorted(set(old) - set(new))]
    modified = [
        {"before": old[key], "after": new[key]}
        for key in sorted(set(old) & set(new))
        if old[key]["sha256"] != new[key]["sha256"]
    ]
    metadata_only = [
        new[key]
        for key in sorted(set(old) & set(new))
        if old[key]["sha256"] == new[key]["sha256"]
        and old[key].get("mtime_ns") != new[key].get("mtime_ns")
    ]
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "metadata_only": metadata_only,
        "unchanged": len(set(old) & set(new)) - len(modified),
    }


def _mirror_matches_manifest(mirror: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    actual = source_snapshot(
        mirror,
        label=str(manifest.get("source_label", "<LIVE_SNAPSHOT>")),
        retries=DEFAULT_RETRIES,
    )
    delta = _entry_maps(manifest["entries"], actual["entries"])
    exact = (
        not delta["added"]
        and not delta["modified"]
        and not delta["deleted"]
        and actual["snapshot_sha256"] == manifest["snapshot_sha256"]
    )
    return {
        "status": "PASS" if exact else "FAIL",
        "exit_code": 0 if exact else 2,
        "expected_snapshot_sha256": manifest["snapshot_sha256"],
        "actual_snapshot_sha256": actual["snapshot_sha256"],
        "delta": delta,
        "actual": actual,
    }


def _write_copy_set(
    source: Path,
    transaction_root: Path,
    entries: Iterable[dict[str, Any]],
    retries: int,
) -> dict[str, Path]:
    prepared_root = transaction_root / "prepared"
    replacements: dict[str, Path] = {}
    for entry in entries:
        relative = _validate_relative(entry["source"])
        destination = prepared_root / PurePosixPath(relative)
        copied = _atomic_copy_verified(
            _resolved(source) / PurePosixPath(relative),
            destination,
            entry,
            retries,
        )
        if copied["sha256"] != entry["sha256"] or copied["bytes"] != entry["bytes"]:
            raise SourceChangedError(
                f"prepared copy does not match source entry: {relative}"
            )
        replacements[relative] = destination
    return replacements


def preheat(
    source: Path,
    mirror: Path,
    manifest_path: Path,
    *,
    label: str = "<LIVE_SERVER>",
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Build and atomically publish a new mirror; never overwrite an old one."""
    source = _resolved(source)
    mirror = _resolved(mirror)
    manifest_path = _resolved(manifest_path)
    report = _base_report("preheat", source, mirror, manifest_path)
    transaction_root: Path | None = None
    try:
        source, mirror = _require_disjoint_roots(source, mirror)
        manifest_path = _require_external(source, mirror, manifest_path, "manifest")
        mirror = _require_mirror_parent(mirror)
        if mirror.exists():
            raise SnapshotError(f"refusing to overwrite existing mirror: {mirror}")
        if manifest_path.exists():
            raise SnapshotError(
                f"refusing to overwrite existing manifest: {manifest_path}"
            )
        if _orphan_transactions(mirror):
            raise SnapshotError("orphan refresh transaction exists beside mirror")
        session = _probe(source)
        report["session_lock_before"] = session
        snapshot = source_snapshot(source, label=label, retries=retries)
        transaction_root = Path(
            tempfile.mkdtemp(prefix=f".{mirror.name}.preheat-", dir=str(mirror.parent))
        ).resolve()
        _assert_no_link_ancestors(transaction_root, "preheat transaction")
        replacements = _write_copy_set(
            source,
            transaction_root,
            snapshot["entries"],
            retries,
        )
        staged_root = transaction_root / "mirror"
        staged_root.mkdir()
        for relative, prepared in replacements.items():
            target = staged_root / PurePosixPath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(prepared, target)
        mirrored = source_snapshot(staged_root, label=label, retries=retries)
        delta = _entry_maps(snapshot["entries"], mirrored["entries"])
        if delta["added"] or delta["modified"] or delta["deleted"]:
            raise SnapshotError(
                "preheat mirror verification did not match source snapshot"
            )
        final_source = source_snapshot(source, label=label, retries=retries)
        if final_source["snapshot_sha256"] != snapshot["snapshot_sha256"]:
            raise SourceChangedError(
                "source changed after preheat copies; discard and retry"
            )
        session_after = _probe(source)
        payload = _manifest_payload(
            source,
            mirror,
            label,
            final_source,
            operation="preheat",
            session_probe={"before": session, "after": session_after},
        )
        os.replace(staged_root, mirror)
        try:
            atomic_json(manifest_path, payload)
        except Exception:
            # The mirror did not exist before this operation. If the external
            # manifest cannot be published, remove only this transaction-owned
            # tree so no unbound baseline is left behind.
            shutil.rmtree(mirror)
            raise
        report.update(
            {
                "session_lock_after": session_after,
                "snapshot": {
                    "file_count": final_source["file_count"],
                    "bytes": final_source["bytes"],
                    "snapshot_sha256": final_source["snapshot_sha256"],
                },
                "manifest_sha256": sha256_file(manifest_path),
                "mirror_verification": {
                    "status": "PASS",
                    "snapshot_sha256": mirrored["snapshot_sha256"],
                },
                "source_stable_after_copy": True,
            }
        )
        return _success(report, "PREHEATED_MIRROR_PUBLISHED")
    except SourceChangedError as exc:
        return _failure(report, "BLOCKED_SOURCE_CHANGED_DURING_PREHEAT", exc)
    except (SnapshotError, OSError, ValueError, RuntimeError) as exc:
        return _failure(report, "BLOCKED_PREHEAT", exc)
    finally:
        if transaction_root is not None and transaction_root.exists():
            shutil.rmtree(transaction_root, ignore_errors=True)


def refresh(
    source: Path,
    mirror: Path,
    manifest_path: Path,
    *,
    allow_source_deletions: bool = False,
    retries: int = DEFAULT_RETRIES,
) -> dict[str, Any]:
    """Refresh only deltas from a stopped source with rollback on any failure."""
    source = _resolved(source)
    mirror = _resolved(mirror)
    manifest_path = _resolved(manifest_path)
    report = _base_report("refresh", source, mirror, manifest_path)
    transaction_root: Path | None = None
    journal: list[dict[str, Any]] = []
    manifest_before: bytes | None = None
    manifest_replaced = False
    retain_transaction = False
    try:
        source, mirror = _require_disjoint_roots(source, mirror)
        manifest_path = _require_external(source, mirror, manifest_path, "manifest")
        if not mirror.is_dir() or _is_linklike(mirror):
            raise SnapshotError(
                f"mirror is missing, linked, or not a directory: {mirror}"
            )
        if _orphan_transactions(mirror):
            raise SnapshotError("orphan refresh transaction exists beside mirror")
        manifest = _validate_manifest(manifest_path, source, mirror)
        manifest_before = manifest_path.read_bytes()
        mirror_check = _mirror_matches_manifest(mirror, manifest)
        report["mirror_before"] = {
            key: value for key, value in mirror_check.items() if key != "actual"
        }
        if mirror_check["status"] != "PASS":
            raise SnapshotError("existing mirror does not match its manifest")
        stopped_before = _require_stopped(source)
        report["session_lock_before"] = stopped_before
        current = source_snapshot(
            source,
            label=str(manifest.get("source_label", "<LIVE_SERVER>")),
            retries=retries,
        )
        report["source_snapshot"] = {
            "file_count": current["file_count"],
            "bytes": current["bytes"],
            "snapshot_sha256": current["snapshot_sha256"],
        }
        delta = _entry_maps(manifest["entries"], current["entries"])
        report["delta"] = delta
        deleted_sources = {entry["source"] for entry in delta["deleted"]}
        critical = sorted(deleted_sources & CRITICAL_DELETIONS)
        report["deletion_policy"] = {
            "allow_source_deletions": allow_source_deletions,
            "critical_deletions": critical,
            "all_deletions": sorted(deleted_sources),
        }
        if critical or (deleted_sources and not allow_source_deletions):
            raise SnapshotError(
                "source deletions are blocked; "
                f"critical={critical}, all={sorted(deleted_sources)[:20]}"
            )
        if not delta["added"] and not delta["modified"] and not delta["deleted"]:
            final = source_snapshot(
                source,
                label=str(manifest.get("source_label", "<LIVE_SERVER>")),
                retries=retries,
            )
            if final["snapshot_sha256"] != current["snapshot_sha256"]:
                raise SourceChangedError("source changed during no-op refresh")
            stopped_after = _require_stopped(source)
            report.update(
                {
                    "session_lock_after": stopped_after,
                    "mirror_after": {
                        key: value
                        for key, value in mirror_check.items()
                        if key != "actual"
                    },
                    "source_stable_after_copy": True,
                }
            )
            return _success(report, "REFRESH_NO_CHANGES")

        transaction_root = Path(
            tempfile.mkdtemp(prefix=f".{mirror.name}.refresh-", dir=str(mirror.parent))
        ).resolve()
        _assert_no_link_ancestors(transaction_root, "refresh transaction")
        report["transaction"] = {
            "path": str(transaction_root),
            "retained_for_recovery": False,
        }
        replacements = _write_copy_set(
            source,
            transaction_root,
            [*delta["added"], *(row["after"] for row in delta["modified"])],
            retries,
        )
        prepared_source = source_snapshot(
            source,
            label=str(manifest.get("source_label", "<LIVE_SERVER>")),
            retries=retries,
        )
        if prepared_source["snapshot_sha256"] != current["snapshot_sha256"]:
            raise SourceChangedError(
                "source changed while preparing refresh transaction"
            )

        deletions = {entry["source"] for entry in delta["deleted"]}
        journal_path = transaction_root / "transaction-journal.json"
        journal = _MIGRATION.commit_transaction(
            mirror,
            replacements,
            deletions,
            transaction_root / "backup",
            transaction_root / "discard",
            journal_path,
        )
        stopped_after_commit = _require_stopped(source)
        final_source = source_snapshot(
            source,
            label=str(manifest.get("source_label", "<LIVE_SERVER>")),
            retries=retries,
        )
        if final_source["snapshot_sha256"] != current["snapshot_sha256"]:
            raise SourceChangedError("source changed after refresh commit")
        mirror_after = source_snapshot(
            mirror,
            label=str(manifest.get("source_label", "<LIVE_SNAPSHOT>")),
            retries=retries,
        )
        final_delta = _entry_maps(final_source["entries"], mirror_after["entries"])
        if (
            final_delta["added"]
            or final_delta["modified"]
            or final_delta["deleted"]
            or final_source["snapshot_sha256"] != mirror_after["snapshot_sha256"]
        ):
            raise SnapshotError("committed mirror does not equal stopped source inputs")
        new_manifest = _manifest_payload(
            source,
            mirror,
            str(manifest.get("source_label", "<LIVE_SERVER>")),
            final_source,
            operation="refresh",
            session_probe={"before": stopped_before, "after": stopped_after_commit},
        )
        manifest_tmp = transaction_root / "manifest.json"
        atomic_json(manifest_tmp, new_manifest)
        os.replace(manifest_tmp, manifest_path)
        manifest_replaced = True
        report.update(
            {
                "session_lock_after": stopped_after_commit,
                "source_stable_after_copy": True,
                "mirror_after": {
                    "status": "PASS",
                    "snapshot_sha256": mirror_after["snapshot_sha256"],
                    "file_count": mirror_after["file_count"],
                    "bytes": mirror_after["bytes"],
                },
                "manifest_sha256": sha256_file(manifest_path),
                "transaction": {
                    "path": str(transaction_root),
                    "operations": len(journal),
                    "changed_or_added": len(replacements),
                    "deletions": len(deletions),
                    "rollback_complete": False,
                },
            }
        )
        return _success(report, "REFRESHED_MIRROR")
    except SnapshotError as exc:
        if journal:
            try:
                _MIGRATION.rollback_transaction(
                    journal,
                    (transaction_root or mirror.parent) / "post-commit-discard",
                )
                if manifest_replaced and manifest_before is not None:
                    atomic_bytes(manifest_path, manifest_before)
            except (OSError, RuntimeError, ValueError) as rollback_exc:
                retain_transaction = True
                report.setdefault("transaction", {})["retained_for_recovery"] = True
                return _failure(
                    report,
                    "REFRESH_ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED",
                    f"{exc}; rollback: {type(rollback_exc).__name__}: {rollback_exc}",
                )
        status = (
            "BLOCKED_SOURCE_DELETIONS"
            if "source deletions are blocked" in str(exc)
            else "BLOCKED_REFRESH"
        )
        if journal:
            report.setdefault("transaction", {})["rollback_complete"] = True
        return _failure(report, status, exc)
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, _MIGRATION.TransactionRollbackError):
            retain_transaction = True
            report.setdefault("transaction", {})["retained_for_recovery"] = True
            return _failure(
                report,
                "REFRESH_ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED",
                exc,
            )
        if journal:
            try:
                _MIGRATION.rollback_transaction(
                    journal,
                    (transaction_root or mirror.parent) / "post-commit-discard",
                )
                if manifest_replaced and manifest_before is not None:
                    atomic_bytes(manifest_path, manifest_before)
            except (OSError, RuntimeError, ValueError) as rollback_exc:
                retain_transaction = True
                report.setdefault("transaction", {})["retained_for_recovery"] = True
                return _failure(
                    report,
                    "REFRESH_ROLLBACK_FAILED_MANUAL_RECOVERY_REQUIRED",
                    f"{exc}; rollback: {type(rollback_exc).__name__}: {rollback_exc}",
                )
        if journal:
            report.setdefault("transaction", {})["rollback_complete"] = True
        return _failure(report, "BLOCKED_REFRESH", exc)
    finally:
        if (
            not retain_transaction
            and transaction_root is not None
            and transaction_root.exists()
        ):
            shutil.rmtree(transaction_root, ignore_errors=True)


def write_report(path: Path, report: dict[str, Any]) -> None:
    atomic_json(_resolved(path), report)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    preheat_parser = sub.add_parser(
        "preheat", help="online/stopped atomic mirror publication"
    )
    preheat_parser.add_argument("--source", type=Path, required=True)
    preheat_parser.add_argument("--mirror", type=Path, required=True)
    preheat_parser.add_argument("--manifest", type=Path, required=True)
    preheat_parser.add_argument("--report", type=Path, required=True)
    preheat_parser.add_argument("--label", default="<LIVE_SERVER>")
    preheat_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    refresh_parser = sub.add_parser(
        "refresh", help="stopped-source transactional delta refresh"
    )
    refresh_parser.add_argument("--source", type=Path, required=True)
    refresh_parser.add_argument("--mirror", type=Path, required=True)
    refresh_parser.add_argument("--manifest", type=Path, required=True)
    refresh_parser.add_argument("--report", type=Path, required=True)
    refresh_parser.add_argument(
        "--allow-source-deletions",
        action="store_true",
        help="apply non-critical source deletions after explicit review",
    )
    refresh_parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.retries < 1:
            raise SnapshotError("--retries must be at least 1")
        source = _resolved(args.source)
        mirror = _resolved(args.mirror)
        manifest = _resolved(args.manifest)
        report_path = _require_external(source, mirror, args.report, "report")
        if _same_path(report_path, manifest):
            raise SnapshotError("report and manifest must be different files")
        if args.operation == "preheat":
            report = preheat(
                source,
                mirror,
                manifest,
                label=args.label,
                retries=args.retries,
            )
        else:
            report = refresh(
                source,
                mirror,
                manifest,
                allow_source_deletions=args.allow_source_deletions,
                retries=args.retries,
            )
        write_report(report_path, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return int(report.get("exit_code", 2))
    except (SnapshotError, OSError, ValueError, RuntimeError) as exc:
        report = _failure(
            _base_report(
                getattr(args, "operation", "unknown"),
                _resolved(args.source),
                _resolved(args.mirror),
                _resolved(args.manifest),
            ),
            "BLOCKED_ARGUMENT_OR_PATH",
            exc,
        )
        try:
            write_report(_resolved(args.report), report)
        except (OSError, RuntimeError, ValueError) as report_exc:
            print(f"could not write failure report: {report_exc}", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
