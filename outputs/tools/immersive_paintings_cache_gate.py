#!/usr/bin/env python3
"""Fail-closed audit and cold-deploy gate for Immersive Paintings images.

Immersive Paintings stores only image metadata in
``world/data/immersive_paintings.dat``.  The authoritative PNG bytes live in
the game-root ``immersive_paintings_cache`` directory.  Treating that
directory as an ordinary disposable cache silently turns every migrated
painting into an empty canvas.

This tool deliberately has no hot-deploy mode.  ``deploy`` requires a locked
manifest, a matching target SavedData index, an absent or already-identical
target cache, and an unlocked/missing ``world/session.lock``.  It publishes a
fully verified sibling directory with one no-replace rename.
"""

from __future__ import annotations

import argparse
import binascii
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import struct
import sys
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import nbtlib


SCHEMA = 1
DEFAULT_EXPECTED_PAINTINGS = 87
INDEX_RELATIVE = PurePosixPath("world/data/immersive_paintings.dat")
CACHE_RELATIVE = PurePosixPath("immersive_paintings_cache")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_PNG_BYTES = 128 * 1024 * 1024
MAX_PNG_DIMENSION = 16_384
MAX_INFLATED_PNG_BYTES = 512 * 1024 * 1024
RESOURCE_KEY = re.compile(
    r"^immersive_paintings:"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"([0-9a-f]{32})$"
)
HEX_SHA256 = re.compile(r"^[0-9A-F]{64}$")


class GateError(RuntimeError):
    """The image set cannot be accepted or deployed safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise GateError(f"cannot inspect filesystem object: {path}") from exc
    attributes = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    try:
        junction = bool(getattr(path, "is_junction", lambda: False)())
    except OSError:
        junction = True
    return path.is_symlink() or junction or bool(attributes & reparse_flag)


def _regular_directory(path: Path, label: str) -> None:
    if not path.exists():
        raise GateError(f"{label} is missing: {path}")
    if _is_reparse(path) or not path.is_dir():
        raise GateError(f"{label} is not a regular directory: {path}")


def _regular_file(path: Path, label: str) -> os.stat_result:
    if not path.exists():
        raise GateError(f"{label} is missing: {path}")
    if _is_reparse(path):
        raise GateError(f"{label} is a symbolic link, junction, or reparse point: {path}")
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise GateError(f"cannot inspect {label}: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise GateError(f"{label} is not a regular file: {path}")
    return info


def _stable_bytes(path: Path, label: str, limit: int) -> tuple[bytes, os.stat_result]:
    before = _regular_file(path, label)
    if before.st_size > limit:
        raise GateError(f"{label} exceeds the {limit}-byte safety limit: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise GateError(f"cannot read {label}: {path}") from exc
    after = _regular_file(path, label)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or len(data) != after.st_size:
        raise GateError(f"{label} changed while it was being read: {path}")
    return data, after


def _decompress_index(raw: bytes, path: Path) -> tuple[bytes, str]:
    if raw.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
                payload = stream.read(MAX_INDEX_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise GateError(f"invalid gzip SavedData index: {path}") from exc
        if len(payload) > MAX_INDEX_BYTES:
            raise GateError(f"inflated SavedData index exceeds safety limit: {path}")
        return payload, "gzip"
    return raw, "raw"


def _decode_uuid(words: object, label: str) -> str:
    if not isinstance(words, nbtlib.IntArray) or len(words) != 4:
        raise GateError(f"{label} must be an IntArray[4]")
    value = 0
    for word in words:
        value = (value << 32) | (int(word) & 0xFFFFFFFF)
    return str(uuid.UUID(int=value))


def _parse_index(
    index_path: Path,
    expected_paintings: int,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    raw, info = _stable_bytes(index_path, "Immersive Paintings index", MAX_INDEX_BYTES)
    payload, encoding = _decompress_index(raw, index_path)
    stream = io.BytesIO(payload)
    try:
        root = nbtlib.File.parse(stream, byteorder="big")
    except Exception as exc:
        raise GateError(f"cannot parse Immersive Paintings SavedData: {index_path}") from exc
    if stream.read(1):
        raise GateError(f"SavedData index has trailing bytes: {index_path}")
    data = root.get("data")
    if not isinstance(data, nbtlib.Compound):
        raise GateError("SavedData root.data must be a Compound")
    paintings = data.get("paintings")
    if not isinstance(paintings, nbtlib.Compound):
        raise GateError("SavedData data.paintings must be a Compound")
    if len(paintings) != expected_paintings:
        raise GateError(
            "unexpected painting count: "
            f"expected={expected_paintings}, actual={len(paintings)}"
        )

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_key in paintings:
        key = str(raw_key)
        match = RESOURCE_KEY.fullmatch(key)
        if match is None:
            raise GateError(f"invalid painting resource key: {key!r}")
        author_uuid, image_hash = match.groups()
        try:
            if str(uuid.UUID(author_uuid)) != author_uuid:
                raise ValueError
        except ValueError as exc:
            raise GateError(f"painting key has a non-canonical UUID: {key!r}") from exc
        metadata = paintings[raw_key]
        if not isinstance(metadata, nbtlib.Compound):
            raise GateError(f"painting metadata must be a Compound: {key!r}")
        metadata_hash = metadata.get("hash")
        if not isinstance(metadata_hash, nbtlib.String) or str(metadata_hash) != image_hash:
            raise GateError(f"painting metadata hash does not match its key: {key!r}")
        metadata_uuid = _decode_uuid(metadata.get("authorUUID"), f"{key} authorUUID")
        if metadata_uuid != author_uuid:
            raise GateError(f"painting authorUUID does not match its key: {key!r}")
        for suffix, kind in ((".png", "original"), ("_thumbnail.png", "thumbnail")):
            relative = f"{author_uuid}/{image_hash}{suffix}"
            folded = relative.casefold()
            if folded in seen:
                raise GateError(f"duplicate or case-colliding expected image path: {relative}")
            seen.add(folded)
            rows.append(
                {
                    "resource": key,
                    "kind": kind,
                    "path": relative,
                }
            )
    rows.sort(key=lambda row: row["path"])
    semantic_rows = [
        {"resource": row["resource"], "kind": row["kind"], "path": row["path"]}
        for row in rows
    ]
    summary = {
        "relative_path": INDEX_RELATIVE.as_posix(),
        "bytes": info.st_size,
        "sha256": _sha256(raw),
        "encoding": encoding,
        "painting_count": len(paintings),
        "semantic_sha256": _sha256(_json_bytes(semantic_rows)),
    }
    return summary, rows


def _png_metadata(data: bytes, label: str) -> tuple[int, int]:
    if len(data) > MAX_PNG_BYTES:
        raise GateError(f"PNG exceeds the {MAX_PNG_BYTES}-byte safety limit: {label}")
    if not data.startswith(PNG_SIGNATURE):
        raise GateError(f"PNG signature is invalid: {label}")
    position = len(PNG_SIGNATURE)
    first = True
    saw_ihdr = False
    saw_idat = False
    saw_iend = False
    idat_finished = False
    idat = bytearray()
    width = height = 0
    while position < len(data):
        if len(data) - position < 12:
            raise GateError(f"PNG chunk header is truncated: {label}")
        length = struct.unpack(">I", data[position : position + 4])[0]
        chunk_type = data[position + 4 : position + 8]
        position += 8
        if not all(65 <= value <= 90 or 97 <= value <= 122 for value in chunk_type):
            raise GateError(f"PNG chunk type is invalid: {label}")
        if length > MAX_PNG_BYTES or position + length + 4 > len(data):
            raise GateError(f"PNG chunk is truncated or oversized: {label}")
        chunk = data[position : position + length]
        expected_crc = struct.unpack(">I", data[position + length : position + length + 4])[0]
        actual_crc = binascii.crc32(chunk_type + chunk) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise GateError(f"PNG chunk CRC mismatch: {label}")
        position += length + 4

        if first:
            if chunk_type != b"IHDR" or length != 13:
                raise GateError(f"PNG must start with a 13-byte IHDR chunk: {label}")
            first = False
        if chunk_type == b"IHDR":
            if saw_ihdr or length != 13:
                raise GateError(f"PNG has an invalid or duplicate IHDR chunk: {label}")
            saw_ihdr = True
            width, height, depth, colour, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if not 0 < width <= MAX_PNG_DIMENSION or not 0 < height <= MAX_PNG_DIMENSION:
                raise GateError(f"PNG dimensions are outside the safety bounds: {label}")
            if colour not in valid_depths or depth not in valid_depths[colour]:
                raise GateError(f"PNG bit depth/colour type combination is invalid: {label}")
            if compression != 0 or filtering != 0 or interlace not in {0, 1}:
                raise GateError(f"PNG IHDR encoding fields are invalid: {label}")
        elif chunk_type == b"IDAT":
            if idat_finished:
                raise GateError(f"PNG IDAT chunks are not consecutive: {label}")
            saw_idat = True
            idat.extend(chunk)
            if len(idat) > MAX_PNG_BYTES:
                raise GateError(f"PNG compressed image stream exceeds safety limit: {label}")
        elif saw_idat:
            idat_finished = True

        if chunk_type == b"IEND":
            if saw_iend or length != 0:
                raise GateError(f"PNG has an invalid or duplicate IEND chunk: {label}")
            saw_iend = True
            if position != len(data):
                raise GateError(f"PNG has data after IEND: {label}")
            break

    if not saw_ihdr or not saw_idat or not saw_iend:
        raise GateError(f"PNG is missing IHDR, IDAT, or IEND: {label}")
    inflater = zlib.decompressobj()
    inflated = 0
    try:
        for offset in range(0, len(idat), 64 * 1024):
            block = bytes(idat[offset : offset + 64 * 1024])
            while block:
                output = inflater.decompress(
                    block,
                    MAX_INFLATED_PNG_BYTES - inflated + 1,
                )
                inflated += len(output)
                if inflated > MAX_INFLATED_PNG_BYTES:
                    raise GateError(f"PNG inflated stream exceeds safety limit: {label}")
                block = inflater.unconsumed_tail
        output = inflater.flush(MAX_INFLATED_PNG_BYTES - inflated + 1)
        inflated += len(output)
    except zlib.error as exc:
        raise GateError(f"PNG IDAT zlib stream is invalid: {label}") from exc
    if inflated > MAX_INFLATED_PNG_BYTES:
        raise GateError(f"PNG inflated stream exceeds safety limit: {label}")
    if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise GateError(f"PNG IDAT zlib stream is incomplete or has trailing data: {label}")
    return width, height


def _walk_regular_tree(root: Path) -> tuple[set[str], dict[str, Path]]:
    _regular_directory(root, "Immersive Paintings cache")
    directories: set[str] = set()
    files: dict[str, Path] = {}
    casefolded: dict[str, str] = {}
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in sorted(directory_names):
            path = current_path / name
            if _is_reparse(path) or not path.is_dir():
                raise GateError(f"cache contains a non-regular directory: {path}")
            relative = path.relative_to(root).as_posix()
            folded = relative.casefold()
            previous = casefolded.setdefault(folded, relative)
            if previous != relative:
                raise GateError(f"cache contains case-colliding paths: {previous!r}, {relative!r}")
            directories.add(relative)
        for name in sorted(file_names):
            path = current_path / name
            _regular_file(path, "cache entry")
            relative = path.relative_to(root).as_posix()
            folded = relative.casefold()
            previous = casefolded.setdefault(folded, relative)
            if previous != relative:
                raise GateError(f"cache contains case-colliding paths: {previous!r}, {relative!r}")
            files[relative] = path
    return directories, files


def _audit_cache(cache_path: Path, expected_rows: list[dict[str, str]]) -> dict[str, Any]:
    expected_files = {row["path"] for row in expected_rows}
    expected_directories = {PurePosixPath(path).parent.as_posix() for path in expected_files}
    actual_directories, actual_files = _walk_regular_tree(cache_path)
    missing = sorted(expected_files - set(actual_files))
    extra = sorted(set(actual_files) - expected_files)
    missing_directories = sorted(expected_directories - actual_directories)
    extra_directories = sorted(actual_directories - expected_directories)
    if missing or extra or missing_directories or extra_directories:
        raise GateError(
            "cache paths do not exactly match SavedData: "
            f"missing={missing[:8]}, extra={extra[:8]}, "
            f"missing_directories={missing_directories[:8]}, "
            f"extra_directories={extra_directories[:8]}"
        )

    rows: list[dict[str, Any]] = []
    total_bytes = 0
    for expected in expected_rows:
        relative = expected["path"]
        payload, info = _stable_bytes(actual_files[relative], "painting PNG", MAX_PNG_BYTES)
        width, height = _png_metadata(payload, relative)
        rows.append(
            {
                "path": relative,
                "kind": expected["kind"],
                "bytes": info.st_size,
                "sha256": _sha256(payload),
                "width": width,
                "height": height,
            }
        )
        total_bytes += info.st_size
    rows.sort(key=lambda row: row["path"])
    tree_digest = hashlib.sha256()
    for row in rows:
        tree_digest.update(
            f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode("ascii")
        )
    return {
        "relative_path": CACHE_RELATIVE.as_posix(),
        "directories": sorted(actual_directories),
        "original_count": sum(row["kind"] == "original" for row in rows),
        "thumbnail_count": sum(row["kind"] == "thumbnail" for row in rows),
        "file_count": len(rows),
        "bytes": total_bytes,
        "tree_sha256": tree_digest.hexdigest().upper(),
        "files": rows,
    }


def audit_game_dir(game_dir: Path, expected_paintings: int = DEFAULT_EXPECTED_PAINTINGS) -> dict[str, Any]:
    if expected_paintings < 0:
        raise GateError("expected painting count cannot be negative")
    game_dir = Path(game_dir).resolve()
    _regular_directory(game_dir, "game directory")
    index, expected_rows = _parse_index(game_dir / INDEX_RELATIVE, expected_paintings)
    cache = _audit_cache(game_dir / CACHE_RELATIVE, expected_rows)
    return {
        "schema": SCHEMA,
        "kind": "immersive_paintings_cache_manifest",
        "status": "PASS",
        "index": index,
        "cache": cache,
    }


def _validate_manifest_shape(manifest: object) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise GateError("manifest root must be an object")
    if manifest.get("schema") != SCHEMA or manifest.get("kind") != "immersive_paintings_cache_manifest":
        raise GateError("unsupported Immersive Paintings manifest schema")
    index = manifest.get("index")
    cache = manifest.get("cache")
    if not isinstance(index, dict) or not isinstance(cache, dict):
        raise GateError("manifest index/cache sections must be objects")
    if not isinstance(index.get("painting_count"), int) or index["painting_count"] < 0:
        raise GateError("manifest painting_count is invalid")
    for label, value in (
        ("index sha256", index.get("sha256")),
        ("index semantic_sha256", index.get("semantic_sha256")),
        ("cache tree_sha256", cache.get("tree_sha256")),
    ):
        if not isinstance(value, str) or HEX_SHA256.fullmatch(value) is None:
            raise GateError(f"manifest {label} is invalid")
    files = cache.get("files")
    if not isinstance(files, list) or len(files) != index["painting_count"] * 2:
        raise GateError("manifest cache file count does not equal twice the painting count")
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    payload, _ = _stable_bytes(Path(path), "manifest", MAX_INDEX_BYTES)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"manifest is not valid UTF-8 JSON: {path}") from exc
    return _validate_manifest_shape(value)


def verify_manifest(game_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manifest = _validate_manifest_shape(manifest)
    actual = audit_game_dir(Path(game_dir), manifest["index"]["painting_count"])
    if actual != manifest:
        raise GateError("game directory does not match the locked image manifest")
    return actual


def _atomic_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _assert_distinct(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    if source == target:
        raise GateError("source and target game directories must be different")
    for candidate, parent, label in (
        (source, target, "source inside target"),
        (target, source, "target inside source"),
    ):
        try:
            candidate.relative_to(parent)
        except ValueError:
            continue
        raise GateError(f"game directories overlap ({label})")


def _assert_server_stopped(target_game_dir: Path) -> None:
    lock_path = target_game_dir / "world" / "session.lock"
    if not lock_path.exists():
        return
    _regular_file(lock_path, "target session.lock")
    try:
        with lock_path.open("r+b", buffering=0) as stream:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - Windows is the production platform
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise GateError("target server appears to be running; cold deployment is required") from exc


def _safe_remove_deploy_temp(path: Path, expected_parent: Path) -> None:
    if path.parent.resolve() != expected_parent.resolve():
        raise GateError(f"refusing to clean a deployment path outside its expected parent: {path}")
    if not path.name.startswith(".immersive_paintings_cache.deploy-"):
        raise GateError(f"refusing to clean an unrecognized deployment path: {path}")
    if path.exists():
        if _is_reparse(path) or not path.is_dir():
            raise GateError(f"refusing to clean a non-regular deployment directory: {path}")
        shutil.rmtree(path)


def _copy_cache(source_cache: Path, destination: Path, manifest: dict[str, Any]) -> None:
    destination.mkdir()
    for row in manifest["cache"]["files"]:
        relative = PurePosixPath(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise GateError(f"unsafe cache path in manifest: {row['path']!r}")
        source = source_cache.joinpath(*relative.parts)
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _audit_cache_against_manifest(
    cache_path: Path,
    index_path: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    index, expected_rows = _parse_index(index_path, manifest["index"]["painting_count"])
    if index != manifest["index"]:
        raise GateError("target or temporary SavedData index does not match the manifest")
    cache = _audit_cache(cache_path, expected_rows)
    if cache != manifest["cache"]:
        raise GateError("target or temporary cache does not match the manifest")
    return cache


def deploy_cache(
    source_game_dir: Path,
    target_game_dir: Path,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    manifest = _validate_manifest_shape(manifest)
    source_game_dir = Path(source_game_dir).resolve()
    target_game_dir = Path(target_game_dir).resolve()
    _regular_directory(source_game_dir, "source game directory")
    _regular_directory(target_game_dir, "target game directory")
    _assert_distinct(source_game_dir, target_game_dir)
    _assert_server_stopped(target_game_dir)
    verify_manifest(source_game_dir, manifest)

    target_index, _ = _parse_index(
        target_game_dir / INDEX_RELATIVE,
        manifest["index"]["painting_count"],
    )
    if target_index != manifest["index"]:
        raise GateError("target SavedData index does not exactly match the locked source index")

    target_cache = target_game_dir / CACHE_RELATIVE
    if target_cache.exists():
        try:
            verify_manifest(target_game_dir, manifest)
        except GateError as exc:
            raise GateError("target cache exists but differs; refusing to overwrite it") from exc
        return {
            "schema": SCHEMA,
            "status": "ALREADY_DEPLOYED",
            "painting_count": manifest["index"]["painting_count"],
            "file_count": manifest["cache"]["file_count"],
            "tree_sha256": manifest["cache"]["tree_sha256"],
        }

    temporary = target_game_dir / f".immersive_paintings_cache.deploy-{uuid.uuid4().hex}"
    if temporary.exists():
        raise GateError(f"deployment temporary path already exists: {temporary}")
    try:
        _copy_cache(source_game_dir / CACHE_RELATIVE, temporary, manifest)
        _audit_cache_against_manifest(
            temporary,
            target_game_dir / INDEX_RELATIVE,
            manifest,
        )
        verify_manifest(source_game_dir, manifest)
        try:
            os.rename(temporary, target_cache)
        except OSError as exc:
            raise GateError("atomic no-replace cache publication failed") from exc
        verify_manifest(target_game_dir, manifest)
    finally:
        if temporary.exists():
            _safe_remove_deploy_temp(temporary, target_game_dir)
    return {
        "schema": SCHEMA,
        "status": "DEPLOYED",
        "painting_count": manifest["index"]["painting_count"],
        "file_count": manifest["cache"]["file_count"],
        "tree_sha256": manifest["cache"]["tree_sha256"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("manifest", help="audit a game directory and write a locked manifest")
    create.add_argument("--game-dir", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--expected-paintings", type=int, default=DEFAULT_EXPECTED_PAINTINGS)

    verify = subparsers.add_parser("verify", help="verify a game directory against a locked manifest")
    verify.add_argument("--game-dir", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--report", type=Path)

    deploy = subparsers.add_parser("deploy", help="cold-deploy a verified cache to a matching target world")
    deploy.add_argument("--source-game-dir", type=Path, required=True)
    deploy.add_argument("--target-game-dir", type=Path, required=True)
    deploy.add_argument("--manifest", type=Path, required=True)
    deploy.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "manifest":
            result = audit_game_dir(args.game_dir, args.expected_paintings)
            _atomic_json(args.output, result)
            output = {
                "schema": SCHEMA,
                "status": "PASS",
                "manifest": str(args.output.resolve()),
                "index_sha256": result["index"]["sha256"],
                "painting_count": result["index"]["painting_count"],
                "file_count": result["cache"]["file_count"],
                "tree_sha256": result["cache"]["tree_sha256"],
            }
        elif args.command == "verify":
            manifest = load_manifest(args.manifest)
            verified = verify_manifest(args.game_dir, manifest)
            output = {
                "schema": SCHEMA,
                "status": "PASS",
                "game_dir": str(args.game_dir.resolve()),
                "index_sha256": verified["index"]["sha256"],
                "painting_count": verified["index"]["painting_count"],
                "file_count": verified["cache"]["file_count"],
                "tree_sha256": verified["cache"]["tree_sha256"],
            }
            if args.report:
                _atomic_json(args.report, output)
        else:
            manifest = load_manifest(args.manifest)
            deployed = deploy_cache(args.source_game_dir, args.target_game_dir, manifest)
            output = {
                **deployed,
                "source_game_dir": str(args.source_game_dir.resolve()),
                "target_game_dir": str(args.target_game_dir.resolve()),
                "completed_at": _utc_now(),
            }
            _atomic_json(args.report, output)
    except Exception as exc:
        failure = {
            "schema": SCHEMA,
            "status": "NO_GO",
            "error": f"{type(exc).__name__}: {exc}",
        }
        report = getattr(args, "report", None)
        if report:
            try:
                _atomic_json(report, failure)
            except Exception:
                pass
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
