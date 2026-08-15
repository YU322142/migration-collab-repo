#!/usr/bin/env python3
"""Create deterministic, content-verified archives for retired world roots.

The active world is never modified.  The two legacy roots are scanned before
and after archiving, every regular file is hashed, and the marker is written
only when the ZIP contents reproduce the same tree digest.  A later release
gate can rescan the source roots and reject a stale archive.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid
import zipfile
from typing import Any


SCHEMA_VERSION = 1
LEGACY_ROOTS = ("world_nether", "world_the_end")
DECISION = "ARCHIVE_ONLY_DO_NOT_MERGE"
BUFFER_SIZE = 4 * 1024 * 1024


class ArchiveError(RuntimeError):
    """The legacy roots cannot be archived without weakening the contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(BUFFER_SIZE), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _tree_digest(directories: list[str], files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for relative in directories:
        digest.update(b"D\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\n")
    for row in files:
        digest.update(b"F\0")
        digest.update(row["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def scan_tree(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise ArchiveError(f"legacy root is missing, symlinked, or not a directory: {root}")

    directories: list[str] = []
    files: list[dict[str, Any]] = []
    for current_text, dir_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_text)
        dir_names.sort()
        file_names.sort()
        for name in list(dir_names):
            child = current / name
            if child.is_symlink():
                raise ArchiveError(f"symbolic link is not allowed in a legacy root: {child}")
            relative = child.relative_to(root).as_posix()
            directories.append(relative)
        for name in file_names:
            child = current / name
            if child.is_symlink():
                raise ArchiveError(f"symbolic link is not allowed in a legacy root: {child}")
            before = child.stat()
            if not stat.S_ISREG(before.st_mode):
                raise ArchiveError(f"non-regular file is not allowed in a legacy root: {child}")
            digest = sha256_file(child)
            after = child.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ArchiveError(f"legacy file changed while it was hashed: {child}")
            files.append(
                {
                    "path": child.relative_to(root).as_posix(),
                    "bytes": after.st_size,
                    "sha256": digest,
                }
            )

    directories.sort()
    files.sort(key=lambda row: row["path"])
    return {
        "root": str(root),
        "directory_count": len(directories),
        "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "tree_sha256": _tree_digest(directories, files),
        "directories": directories,
        "files": files,
    }


def _zip_info(name: str, is_directory: bool) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name + ("/" if is_directory else ""))
    info.date_time = (1980, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    mode = 0o40755 if is_directory else 0o100644
    info.external_attr = mode << 16
    return info


def write_archive(root: Path, scan: dict[str, Any], destination: Path) -> None:
    root = root.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        for relative in scan["directories"]:
            archive.writestr(_zip_info(relative, True), b"")
        for row in scan["files"]:
            source = root / Path(row["path"])
            with source.open("rb") as input_stream, archive.open(
                _zip_info(row["path"], False), "w", force_zip64=True
            ) as output_stream:
                shutil.copyfileobj(input_stream, output_stream, BUFFER_SIZE)


def scan_archive(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ArchiveError(f"archive is missing, symlinked, or not a file: {path}")
    directories: list[str] = []
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = info.filename
                normalized = name[:-1] if info.is_dir() else name
                parts = Path(normalized).parts
                if (
                    not normalized
                    or Path(normalized).is_absolute()
                    or any(part in {"", ".", ".."} for part in parts)
                    or normalized in seen
                ):
                    raise ArchiveError(f"archive contains an unsafe or duplicate path: {name}")
                seen.add(normalized)
                if info.is_dir():
                    directories.append(normalized)
                    continue
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for block in iter(lambda: stream.read(BUFFER_SIZE), b""):
                        digest.update(block)
                files.append(
                    {
                        "path": normalized,
                        "bytes": info.file_size,
                        "sha256": digest.hexdigest().upper(),
                    }
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"invalid legacy archive: {path}") from exc
    directories.sort()
    files.sort(key=lambda row: row["path"])
    return {
        "directory_count": len(directories),
        "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files),
        "tree_sha256": _tree_digest(directories, files),
        "directories": directories,
        "files": files,
    }


def _same_tree(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = ("directory_count", "file_count", "bytes", "tree_sha256", "directories", "files")
    return all(left.get(key) == right.get(key) for key in keys)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_archives(
    source_game_dir: Path,
    output_dir: Path,
    audit_report: Path,
    marker_path: Path,
) -> dict[str, Any]:
    source = source_game_dir.resolve()
    output = output_dir.resolve()
    marker = marker_path.resolve()
    audit = audit_report.resolve()
    if source.is_symlink() or not source.is_dir():
        raise ArchiveError(f"source game directory is invalid: {source}")
    if audit.is_symlink() or not audit.is_file():
        raise ArchiveError(f"legacy audit report is invalid: {audit}")
    for path, label in ((output, "output directory"), (marker, "marker")):
        if _inside(path, source) or _inside(source, path):
            raise ArchiveError(f"{label} must not overlap the source game directory")
    if not _inside(marker, output):
        raise ArchiveError("marker must be written inside the archive output directory")

    before = {name: scan_tree(source / name) for name in LEGACY_ROOTS}
    prepared: dict[str, tuple[Path, Path]] = {}
    try:
        for name in LEGACY_ROOTS:
            digest_prefix = before[name]["tree_sha256"][:16]
            destination = output / f"{name}-{digest_prefix}.zip"
            temporary = output / f".{destination.name}.tmp-{uuid.uuid4().hex}"
            write_archive(source / name, before[name], temporary)
            archived = scan_archive(temporary)
            if not _same_tree(before[name], archived):
                raise ArchiveError(f"archive content does not match source tree: {name}")
            prepared[name] = (temporary, destination)

        after = {name: scan_tree(source / name) for name in LEGACY_ROOTS}
        for name in LEGACY_ROOTS:
            if not _same_tree(before[name], after[name]):
                raise ArchiveError(f"legacy root changed while it was archived: {name}")

        output.mkdir(parents=True, exist_ok=True)
        archive_rows: dict[str, Any] = {}
        for name in LEGACY_ROOTS:
            temporary, destination = prepared[name]
            os.replace(temporary, destination)
            archive_rows[name] = {
                "path": str(destination),
                "bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
                "source_root": str((source / name).resolve()),
                "source_tree_sha256": before[name]["tree_sha256"],
                "source_file_count": before[name]["file_count"],
                "source_bytes": before[name]["bytes"],
            }

        result = {
            "schema": SCHEMA_VERSION,
            "status": "PASS",
            "decision": DECISION,
            "merge_into_canonical": False,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_game_dir": str(source),
            "roots": list(LEGACY_ROOTS),
            "audit_report": str(audit),
            "audit_report_sha256": sha256_file(audit),
            "archives": archive_rows,
        }
        _atomic_json(marker, result)
        return result
    finally:
        for temporary, _destination in prepared.values():
            temporary.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-game-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_archives(
            args.source_game_dir,
            args.output_dir,
            args.audit_report,
            args.marker,
        )
    except ArchiveError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "marker": str(args.marker.resolve()),
                "roots": result["roots"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
