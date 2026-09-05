#!/usr/bin/env python3
"""Build fail-closed Candidate12 bundles from the frozen Candidate11 release.

Candidate12 permits exactly one change per side: replace the rejected
``waypoint_fire_equivalence`` JAR.  Every other Candidate11 JAR must remain
byte-identical.  The builder validates the frozen baseline, ZIP CRCs, mod IDs,
case-insensitive filenames, manifests, aggregate digests, and release locks
before publishing a fresh output root atomically.
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CANDIDATE11_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate11-20260811"
)
HISTORICAL_BACKUP_ROOT = Path(r"<TRANS_ROOT>\20260807")
JAR_COUNT = 52
UNCHANGED_ROWS_PER_SIDE = 51
WAYPOINT_MOD_ID = "waypoint_fire_equivalence"
REJECTED_WAYPOINT_FILE = "waypoint-fire-equivalence-0.1.0-draft+mc1.21.1.jar"
REJECTED_WAYPOINT_BYTES = 44_265
REJECTED_WAYPOINT_SHA256 = (
    "5572EE1F196038071FB5D7B9D7FF271CCB0E19BA722B83BCC1A2B8C0C844F8EB"
)


@dataclass(frozen=True)
class Candidate11Lock:
    release_lock_sha256: str
    server_manifest_sha256: str
    client_manifest_sha256: str
    server_bundle_sha256: str
    client_bundle_sha256: str
    bundle_pair_sha256: str
    server_only_file: str
    server_only_sha256: str
    server_only_mod_id: str
    client_only_file: str
    client_only_sha256: str
    client_only_mod_id: str
    waypoint_file: str = REJECTED_WAYPOINT_FILE
    waypoint_bytes: int = REJECTED_WAYPOINT_BYTES
    waypoint_sha256: str = REJECTED_WAYPOINT_SHA256


CANDIDATE11_LOCK = Candidate11Lock(
    release_lock_sha256="613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E",
    server_manifest_sha256="66BA1B734E9A8BE2728A2FC9FCF77A8E49AAAEEFBEC3D0069EA63D0D841DAD3C",
    client_manifest_sha256="1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D",
    server_bundle_sha256="CCFDA18205DF3C6D012B2C61890309CDBC3DAC016E698BB23DAE6DEB8DC2271A",
    client_bundle_sha256="CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B",
    bundle_pair_sha256="FC008BD9ED9ABF5FF23B61E40ADDCAC46986E22147EB2437324C48E2E9242E56",
    server_only_file="grieflogger-1.2.10-1.21.1-neoforge.jar",
    server_only_sha256="FD252BC5466BB94E38D2386BAFB9926B798BC250B26E1A3AA80F878EBCCBC4A5",
    server_only_mod_id="grieflogger",
    client_only_file="chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar",
    client_only_sha256="9CEF2FAC6BD959202E37882B941EBC51A1ED7A4259441D3B41372971FD04F6D8",
    client_only_mod_id="colorizer",
)

RUNTIME_ONLY_TRANSFORM_FILES = (
    "CreateDragonsPlus-1.11.4.jar",
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar",
)


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.candidate12.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def validate_sha256(value: str, label: str) -> str:
    result = value.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{64}", result):
        raise ValueError(f"{label} is not a SHA-256")
    return result


def safe_jar_name(value: object) -> str:
    name = str(value)
    if (
        Path(name).name != name
        or not name.lower().endswith(".jar")
        or name in {".", ".."}
        or "\x00" in name
    ):
        raise ValueError(f"unsafe JAR filename: {name!r}")
    return name


def paths_overlap(left: Path, right: Path) -> bool:
    left_norm = os.path.normcase(str(left.resolve()))
    right_norm = os.path.normcase(str(right.resolve()))
    try:
        common = os.path.normcase(os.path.commonpath((left_norm, right_norm)))
    except ValueError:
        return False
    return common in {left_norm, right_norm}


def jar_mod_ids(path: Path, *, verify_crc: bool = True) -> set[str]:
    if path.is_symlink():
        raise ValueError(f"JAR must not be a symbolic link: {path}")
    if not path.is_file() or not zipfile.is_zipfile(path):
        raise ValueError(f"not a ZIP/JAR: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            if verify_crc:
                bad = archive.testzip()
                if bad is not None:
                    raise ValueError(f"JAR CRC failure in {bad}: {path}")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError(f"JAR has duplicate ZIP entry names: {path}")
            name_set = set(names)
            result: set[str] = set()
            if "fabric.mod.json" in name_set:
                value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                if isinstance(value, dict) and isinstance(value.get("id"), str):
                    result.add(value["id"])
            for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if name not in name_set:
                    continue
                value = tomllib.loads(archive.read(name).decode("utf-8"))
                for mod in value.get("mods", []):
                    mod_id = mod.get("modId") if isinstance(mod, dict) else None
                    if isinstance(mod_id, str) and "${" not in mod_id:
                        result.add(mod_id)
            return result
    except (
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        raise ValueError(f"invalid mod metadata in JAR {path}: {exc}") from exc


def bundle_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row["file"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).upper().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def pair_digest(server_bundle: str, client_bundle: str) -> str:
    payload = (
        f"server\0{server_bundle.upper()}\nclient\0{client_bundle.upper()}\n"
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest().upper()


def _row_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["file"]).casefold()
        if key in result:
            raise ValueError(f"case-insensitive manifest filename collision: {row['file']}")
        result[key] = row
    return result


def _validate_flat_jar_dir(path: Path, label: str) -> dict[str, Path]:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} is not a real directory: {path}")
    entries = sorted(path.iterdir(), key=lambda item: item.name.casefold())
    if len(entries) != JAR_COUNT:
        raise ValueError(f"{label} must contain exactly {JAR_COUNT} entries")
    result: dict[str, Path] = {}
    for entry in entries:
        if entry.is_symlink() or not entry.is_file() or entry.suffix.lower() != ".jar":
            raise ValueError(f"{label} contains a non-regular JAR entry: {entry}")
        key = entry.name.casefold()
        if key in result:
            raise ValueError(f"{label} has a case-insensitive filename collision")
        result[key] = entry
    return result


def _validate_manifest_rows(
    manifest: dict[str, Any], actual_dir: Path, label: str
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != JAR_COUNT:
        raise ValueError(f"{label} manifest must have exactly {JAR_COUNT} rows")
    if manifest.get("file_count") != JAR_COUNT:
        raise ValueError(f"{label} manifest file_count mismatch")
    actual_by_name = _validate_flat_jar_dir(actual_dir, label)
    seen: set[str] = set()
    owners: dict[str, str] = {}
    validated: list[dict[str, Any]] = []
    total_bytes = 0
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise ValueError(f"{label} manifest contains a non-object row")
        name = safe_jar_name(raw_row.get("file"))
        key = name.casefold()
        if key in seen:
            raise ValueError(f"{label} duplicate manifest filename: {name}")
        seen.add(key)
        path = actual_by_name.get(key)
        if path is None:
            raise ValueError(f"{label} JAR missing: {name}")
        expected_hash = validate_sha256(
            str(raw_row.get("sha256", "")), f"{label}:{name}"
        )
        expected_bytes = raw_row.get("bytes")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ValueError(f"{label} invalid byte count for {name}")
        actual_hash = sha256(path)
        if path.stat().st_size != expected_bytes or actual_hash != expected_hash:
            raise ValueError(f"{label} JAR byte/SHA-256 mismatch: {name}")
        actual_ids = jar_mod_ids(path)
        manifest_ids = raw_row.get("mod_ids")
        if not isinstance(manifest_ids, list) or any(
            not isinstance(item, str) for item in manifest_ids
        ):
            raise ValueError(f"{label} invalid mod_ids for {name}")
        if set(manifest_ids) != actual_ids:
            raise ValueError(f"{label} metadata mismatch for {name}")
        for mod_id in actual_ids:
            owner_key = mod_id.casefold()
            owner = owners.get(owner_key)
            if owner is not None:
                raise ValueError(f"{label} duplicate mod ID {mod_id}: {owner}, {name}")
            owners[owner_key] = name
        total_bytes += expected_bytes
        row = dict(raw_row)
        row["file"] = name
        row["bytes"] = expected_bytes
        row["sha256"] = expected_hash
        row["mod_ids"] = sorted(actual_ids)
        row["_path"] = path.resolve()
        validated.append(row)
    if seen != set(actual_by_name):
        raise ValueError(f"{label} manifest/directory filename set mismatch")
    if [row["file"].casefold() for row in validated] != sorted(seen):
        raise ValueError(f"{label} manifest rows are not deterministically sorted")
    if manifest.get("bytes") != total_bytes:
        raise ValueError(f"{label} manifest byte total mismatch")
    computed = bundle_digest(validated)
    if str(manifest.get("bundle_sha256", "")).upper() != computed:
        raise ValueError(f"{label} manifest bundle digest mismatch")
    return validated, owners


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "_path"}


def validate_candidate11_side(
    root: Path, side: str, lock: Candidate11Lock
) -> dict[str, Any]:
    manifest_path = root / "manifests" / f"{side}.json"
    expected_manifest_hash = (
        lock.server_manifest_sha256 if side == "server" else lock.client_manifest_sha256
    )
    expected_bundle_hash = (
        lock.server_bundle_sha256 if side == "server" else lock.client_bundle_sha256
    )
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if sha256(manifest_path) != expected_manifest_hash:
        raise ValueError(f"Candidate11 {side} manifest lock mismatch")
    manifest = read_json(manifest_path)
    bundle_dir = root / f"{side}-mods"
    if (
        manifest.get("schema") != 1
        or manifest.get("candidate") != 11
        or manifest.get("status") != "PASS"
        or manifest.get("side") != side
        or Path(str(manifest.get("bundle_dir", ""))).resolve() != bundle_dir.resolve()
        or Path(str(manifest.get("manifest_path", ""))).resolve()
        != manifest_path.resolve()
    ):
        raise ValueError(f"Candidate11 {side} manifest content binding mismatch")
    rows, owners = _validate_manifest_rows(
        manifest, bundle_dir, f"Candidate11 {side}"
    )
    computed = bundle_digest(rows)
    if computed != expected_bundle_hash:
        raise ValueError(f"Candidate11 {side} bundle lock mismatch")
    waypoint = [row for row in rows if WAYPOINT_MOD_ID in row["mod_ids"]]
    if len(waypoint) != 1:
        raise ValueError(f"Candidate11 {side} must have one Waypoint Fire owner")
    waypoint_row = waypoint[0]
    if (
        waypoint_row["file"] != lock.waypoint_file
        or waypoint_row["bytes"] != lock.waypoint_bytes
        or waypoint_row["sha256"] != lock.waypoint_sha256
        or set(waypoint_row["mod_ids"]) != {WAYPOINT_MOD_ID}
    ):
        raise ValueError(f"Candidate11 {side} rejected Waypoint lock mismatch")
    return {
        "side": side,
        "manifest": manifest,
        "manifest_path": manifest_path.resolve(),
        "manifest_sha256": sha256(manifest_path),
        "bundle_dir": bundle_dir.resolve(),
        "bundle_sha256": computed,
        "rows": rows,
        "owners": owners,
        "waypoint": waypoint_row,
    }


def validate_candidate11(
    root: Path = CANDIDATE11_ROOT,
    lock: Candidate11Lock = CANDIDATE11_LOCK,
) -> dict[str, Any]:
    root = root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Candidate11 root is not a real directory: {root}")
    expected_entries = {
        "server-mods",
        "client-mods",
        "manifests",
        "release-lock.json",
        "READY.json",
    }
    if {entry.name for entry in root.iterdir()} != expected_entries:
        raise ValueError("Candidate11 root entry set mismatch")
    manifests = root / "manifests"
    if manifests.is_symlink() or {entry.name for entry in manifests.iterdir()} != {
        "server.json",
        "client.json",
    }:
        raise ValueError("Candidate11 manifest entry set mismatch")
    release_path = root / "release-lock.json"
    ready_path = root / "READY.json"
    for path in (release_path, ready_path):
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path) != lock.release_lock_sha256:
            raise ValueError(f"Candidate11 lock hash mismatch: {path.name}")
    if release_path.read_bytes() != ready_path.read_bytes():
        raise ValueError("Candidate11 READY/release-lock bytes differ")
    release = read_json(release_path)
    if (
        release.get("schema") != 1
        or release.get("candidate") != 11
        or release.get("status") != "PASS"
        or release.get("source_unchanged") is not True
        or Path(str(release.get("output_root", ""))).resolve() != root
    ):
        raise ValueError("Candidate11 release-lock content binding mismatch")
    server = validate_candidate11_side(root, "server", lock)
    client = validate_candidate11_side(root, "client", lock)
    for side, validated in (("server", server), ("client", client)):
        detail = release.get(side)
        if not isinstance(detail, dict) or (
            detail.get("file_count") != JAR_COUNT
            or str(detail.get("bundle_sha256", "")).upper()
            != validated["bundle_sha256"]
            or str(detail.get("manifest_sha256", "")).upper()
            != validated["manifest_sha256"]
        ):
            raise ValueError(f"Candidate11 release-lock {side} binding mismatch")
    computed_pair = pair_digest(server["bundle_sha256"], client["bundle_sha256"])
    if computed_pair != lock.bundle_pair_sha256 or (
        str(release.get("bundle_pair_sha256", "")).upper() != computed_pair
    ):
        raise ValueError("Candidate11 pair digest mismatch")
    server_rows = _row_map(server["rows"])
    client_rows = _row_map(client["rows"])
    if set(server_rows) - set(client_rows) != {lock.server_only_file.casefold()}:
        raise ValueError("Candidate11 server-only policy mismatch")
    if set(client_rows) - set(server_rows) != {lock.client_only_file.casefold()}:
        raise ValueError("Candidate11 client-only policy mismatch")
    shared = set(server_rows) & set(client_rows)
    if len(shared) != JAR_COUNT - 1:
        raise ValueError("Candidate11 sides do not share exactly 51 filenames")
    for key in shared:
        if server_rows[key]["sha256"] != client_rows[key]["sha256"]:
            raise ValueError(f"Candidate11 shared JAR differs across sides: {key}")
    sentinels = (
        (
            server_rows[lock.server_only_file.casefold()],
            lock.server_only_sha256,
            lock.server_only_mod_id,
        ),
        (
            client_rows[lock.client_only_file.casefold()],
            lock.client_only_sha256,
            lock.client_only_mod_id,
        ),
    )
    for row, expected_hash, expected_id in sentinels:
        if row["sha256"] != expected_hash or set(row["mod_ids"]) != {expected_id}:
            raise ValueError(f"Candidate11 side-specific sentinel mismatch: {row['file']}")
    return {
        "root": root,
        "release": release,
        "release_lock_sha256": sha256(release_path),
        "server": server,
        "client": client,
        "bundle_pair_sha256": computed_pair,
    }


def validate_fixed_waypoint(path: Path, expected_sha256: str) -> dict[str, Any]:
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path)
    name = safe_jar_name(path.name)
    expected = validate_sha256(expected_sha256, "fixed Waypoint SHA-256")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"fixed Waypoint hash mismatch: {actual} != {expected}")
    if actual == REJECTED_WAYPOINT_SHA256:
        raise ValueError("fixed Waypoint is byte-identical to the rejected Candidate11 JAR")
    mod_ids = jar_mod_ids(path)
    if mod_ids != {WAYPOINT_MOD_ID}:
        raise ValueError(
            f"fixed Waypoint must expose only mod ID {WAYPOINT_MOD_ID}; "
            f"found {sorted(mod_ids)}"
        )
    return {
        "path": path,
        "file": name,
        "bytes": path.stat().st_size,
        "sha256": actual,
        "mod_ids": sorted(mod_ids),
    }


def _copy_verified(source: Path, destination: Path, size: int, digest: str) -> None:
    shutil.copy2(source, destination)
    if destination.stat().st_size != size or sha256(destination) != digest:
        raise IOError(f"copy verification failed: {destination}")


def _replacement_row(
    old: dict[str, Any], fixed: dict[str, Any]
) -> dict[str, Any]:
    row = _public_row(old)
    row.update(
        {
            "file": fixed["file"],
            "bytes": fixed["bytes"],
            "sha256": fixed["sha256"],
            "mod_ids": list(fixed["mod_ids"]),
            "role": "replacement",
            "component": "Waypoint Fire command-tree serialization fix",
            "source": str(fixed["path"]),
            "expected_sha256": fixed["sha256"],
            "expected_bytes": fixed["bytes"],
            "replaces_file": old["file"],
            "replaces_sha256": old["sha256"],
            "candidate12_comparison": "replaced_waypoint_fire_join_blocker",
        }
    )
    return row


def copy_and_manifest_side(
    baseline: dict[str, Any],
    fixed: dict[str, Any],
    staging_mods: Path,
    final_mods: Path,
    final_manifest_path: Path,
) -> dict[str, Any]:
    staging_mods.mkdir(parents=True)
    old = baseline["waypoint"]
    old_key = old["file"].casefold()
    fixed_key = fixed["file"].casefold()
    other_names = {
        row["file"].casefold() for row in baseline["rows"] if row is not old
    }
    if fixed_key in other_names:
        raise ValueError(f"fixed Waypoint filename collides with Candidate11: {fixed['file']}")

    output_rows: list[dict[str, Any]] = []
    unchanged = 0
    for source_row in baseline["rows"]:
        if source_row["file"].casefold() == old_key:
            continue
        destination = staging_mods / source_row["file"]
        _copy_verified(
            source_row["_path"],
            destination,
            source_row["bytes"],
            source_row["sha256"],
        )
        row = _public_row(source_row)
        row["candidate12_comparison"] = "exact_candidate11"
        output_rows.append(row)
        unchanged += 1
    if unchanged != UNCHANGED_ROWS_PER_SIDE:
        raise ValueError("Candidate12 did not preserve exactly 51 Candidate11 rows")
    fixed_destination = staging_mods / fixed["file"]
    _copy_verified(fixed["path"], fixed_destination, fixed["bytes"], fixed["sha256"])
    output_rows.append(_replacement_row(old, fixed))
    output_rows.sort(key=lambda row: row["file"].casefold())
    if len(output_rows) != JAR_COUNT:
        raise ValueError("Candidate12 side did not produce exactly 52 rows")
    if len({row["file"].casefold() for row in output_rows}) != JAR_COUNT:
        raise ValueError("Candidate12 side has duplicate case-insensitive filenames")
    return {
        "schema": 1,
        "candidate": 12,
        "status": "PASS",
        "side": baseline["side"],
        "baseline_candidate": 11,
        "baseline_manifest": str(baseline["manifest_path"]),
        "baseline_manifest_sha256": baseline["manifest_sha256"],
        "baseline_bundle_sha256": baseline["bundle_sha256"],
        "bundle_dir": str(final_mods),
        "file_count": len(output_rows),
        "bytes": sum(int(row["bytes"]) for row in output_rows),
        "bundle_sha256": bundle_digest(output_rows),
        "manifest_path": str(final_manifest_path),
        "candidate11_invariance": {
            "baseline_rows": JAR_COUNT,
            "unchanged_rows": UNCHANGED_ROWS_PER_SIDE,
            "replaced_rows": 1,
            "added_rows": 0,
            "removed_rows": 0,
            "allowed_replaced_mod_ids": [WAYPOINT_MOD_ID],
        },
        "waypoint_replacement": {
            "mod_id": WAYPOINT_MOD_ID,
            "before_file": old["file"],
            "before_bytes": old["bytes"],
            "before_sha256": old["sha256"],
            "after_file": fixed["file"],
            "after_bytes": fixed["bytes"],
            "after_sha256": fixed["sha256"],
        },
        "files": output_rows,
    }


def validate_candidate12_side(
    manifest_path: Path,
    actual_dir: Path,
    side: str,
    baseline: dict[str, Any],
    fixed: dict[str, Any],
    *,
    expected_manifest_path: Path | None = None,
    expected_bundle_dir: Path | None = None,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    expected_manifest_path = (expected_manifest_path or manifest_path).resolve()
    expected_bundle_dir = (expected_bundle_dir or actual_dir).resolve()
    if (
        manifest.get("schema") != 1
        or manifest.get("candidate") != 12
        or manifest.get("status") != "PASS"
        or manifest.get("side") != side
        or manifest.get("baseline_candidate") != 11
        or Path(str(manifest.get("manifest_path", ""))).resolve()
        != expected_manifest_path
        or Path(str(manifest.get("bundle_dir", ""))).resolve()
        != expected_bundle_dir
    ):
        raise ValueError(f"Candidate12 {side} manifest content binding mismatch")
    rows, owners = _validate_manifest_rows(
        manifest, actual_dir, f"Candidate12 {side}"
    )
    baseline_rows = _row_map(baseline["rows"])
    output_rows = _row_map(rows)
    old = baseline["waypoint"]
    old_key = old["file"].casefold()
    fixed_key = fixed["file"].casefold()
    unchanged = 0
    for key, old_row in baseline_rows.items():
        if key == old_key:
            continue
        current = output_rows.get(key)
        if current is None or (
            current["bytes"] != old_row["bytes"]
            or current["sha256"] != old_row["sha256"]
        ):
            raise ValueError(f"Candidate12 {side} changed Candidate11 JAR: {old_row['file']}")
        unchanged += 1
    if unchanged != UNCHANGED_ROWS_PER_SIDE:
        raise ValueError(f"Candidate12 {side} invariance row count mismatch")
    expected_names = (set(baseline_rows) - {old_key}) | {fixed_key}
    if set(output_rows) != expected_names:
        raise ValueError(f"Candidate12 {side} has an unapproved JAR-set change")
    fixed_row = output_rows.get(fixed_key)
    if fixed_row is None or (
        fixed_row["bytes"] != fixed["bytes"]
        or fixed_row["sha256"] != fixed["sha256"]
        or set(fixed_row["mod_ids"]) != {WAYPOINT_MOD_ID}
    ):
        raise ValueError(f"Candidate12 {side} Waypoint replacement binding mismatch")
    if any(row["sha256"] == REJECTED_WAYPOINT_SHA256 for row in rows):
        raise ValueError(f"Candidate12 {side} still contains the rejected Waypoint bytes")
    expected_invariance = {
        "baseline_rows": 52,
        "unchanged_rows": 51,
        "replaced_rows": 1,
        "added_rows": 0,
        "removed_rows": 0,
        "allowed_replaced_mod_ids": [WAYPOINT_MOD_ID],
    }
    if manifest.get("candidate11_invariance") != expected_invariance:
        raise ValueError(f"Candidate12 {side} invariance declaration mismatch")
    replacement = manifest.get("waypoint_replacement")
    if not isinstance(replacement, dict) or replacement != {
        "mod_id": WAYPOINT_MOD_ID,
        "before_file": old["file"],
        "before_bytes": old["bytes"],
        "before_sha256": old["sha256"],
        "after_file": fixed["file"],
        "after_bytes": fixed["bytes"],
        "after_sha256": fixed["sha256"],
    }:
        raise ValueError(f"Candidate12 {side} replacement declaration mismatch")
    if owners.get(WAYPOINT_MOD_ID.casefold()) != fixed["file"]:
        raise ValueError(f"Candidate12 {side} Waypoint mod owner mismatch")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path.resolve(),
        "manifest_sha256": sha256(manifest_path),
        "bundle_dir": actual_dir.resolve(),
        "bundle_sha256": bundle_digest(rows),
        "rows": rows,
        "owners": owners,
        "waypoint": fixed_row,
    }


def validate_candidate12_pair(
    server: dict[str, Any], client: dict[str, Any], lock: Candidate11Lock
) -> None:
    server_rows = _row_map(server["rows"])
    client_rows = _row_map(client["rows"])
    if set(server_rows) - set(client_rows) != {lock.server_only_file.casefold()}:
        raise ValueError("Candidate12 server-only policy changed")
    if set(client_rows) - set(server_rows) != {lock.client_only_file.casefold()}:
        raise ValueError("Candidate12 client-only policy changed")
    shared = set(server_rows) & set(client_rows)
    if len(shared) != JAR_COUNT - 1:
        raise ValueError("Candidate12 sides do not share exactly 51 filenames")
    for key in shared:
        if server_rows[key]["sha256"] != client_rows[key]["sha256"]:
            raise ValueError(f"Candidate12 shared JAR differs across sides: {key}")
    sentinels = (
        (
            server_rows[lock.server_only_file.casefold()],
            lock.server_only_sha256,
            lock.server_only_mod_id,
        ),
        (
            client_rows[lock.client_only_file.casefold()],
            lock.client_only_sha256,
            lock.client_only_mod_id,
        ),
    )
    for row, expected_hash, expected_id in sentinels:
        if row["sha256"] != expected_hash or set(row["mod_ids"]) != {expected_id}:
            raise ValueError(f"Candidate12 side-specific sentinel changed: {row['file']}")


def release_record(
    output_root: Path,
    candidate11: dict[str, Any],
    fixed: dict[str, Any],
    server: dict[str, Any],
    client: dict[str, Any],
    lock: Candidate11Lock,
) -> dict[str, Any]:
    return {
        "schema": 1,
        "candidate": 12,
        "status": "PASS",
        "purpose": "Candidate11 with Waypoint Fire command-tree serialization fix",
        "output_root": str(output_root),
        "source_unchanged": True,
        "baseline": {
            "candidate": 11,
            "root": str(candidate11["root"]),
            "release_lock_sha256": candidate11["release_lock_sha256"],
            "server_manifest_sha256": candidate11["server"]["manifest_sha256"],
            "client_manifest_sha256": candidate11["client"]["manifest_sha256"],
            "server_bundle_sha256": candidate11["server"]["bundle_sha256"],
            "client_bundle_sha256": candidate11["client"]["bundle_sha256"],
            "bundle_pair_sha256": candidate11["bundle_pair_sha256"],
        },
        "replacement": {
            "component": "Waypoint Fire",
            "mod_id": WAYPOINT_MOD_ID,
            "operation": "replace_both_sides",
            "reason": "register custom Brigadier argument for command-tree serialization",
            "before_file": lock.waypoint_file,
            "before_bytes": lock.waypoint_bytes,
            "before_sha256": lock.waypoint_sha256,
            "after_file": fixed["file"],
            "after_bytes": fixed["bytes"],
            "after_sha256": fixed["sha256"],
            "after_mod_ids": fixed["mod_ids"],
        },
        "candidate11_invariance": {
            "baseline_rows_per_side": JAR_COUNT,
            "unchanged_rows_per_side": UNCHANGED_ROWS_PER_SIDE,
            "replaced_rows_per_side": 1,
            "added_rows_per_side": 0,
            "removed_rows_per_side": 0,
        },
        "server": {
            "mods_dir": str(output_root / "server-mods"),
            "file_count": JAR_COUNT,
            "bytes": server["manifest"]["bytes"],
            "bundle_sha256": server["bundle_sha256"],
            "manifest": str(output_root / "manifests" / "server.json"),
            "manifest_sha256": server["manifest_sha256"],
        },
        "client": {
            "mods_dir": str(output_root / "client-mods"),
            "file_count": JAR_COUNT,
            "bytes": client["manifest"]["bytes"],
            "bundle_sha256": client["bundle_sha256"],
            "manifest": str(output_root / "manifests" / "client.json"),
            "manifest_sha256": client["manifest_sha256"],
        },
        "bundle_pair_sha256": pair_digest(
            server["bundle_sha256"], client["bundle_sha256"]
        ),
        "side_specific_policy": {
            "server_only_file": lock.server_only_file,
            "server_only_mod_id": lock.server_only_mod_id,
            "client_only_file": lock.client_only_file,
            "client_only_mod_id": lock.client_only_mod_id,
        },
        "runtime_sanitization_policy": {
            "published_bundle_state": "unsanitized",
            "scope": "disposable_server_runtime_copy_only",
            "allowed_jar_transforms": list(RUNTIME_ONLY_TRANSFORM_FILES),
            "waypoint_jar_must_remain_byte_identical": True,
            "client_runtime_jar_transforms_allowed": False,
        },
        "verification": {
            "zip_crc_archives_tested": JAR_COUNT * 2,
            "duplicate_filenames": [],
            "duplicate_mod_ids": [],
            "all_other_rows_byte_identical": True,
        },
    }


def _validate_release_bindings(
    root: Path,
    release: dict[str, Any],
    candidate11: dict[str, Any],
    fixed: dict[str, Any],
    server: dict[str, Any],
    client: dict[str, Any],
    lock: Candidate11Lock,
) -> None:
    expected = release_record(root, candidate11, fixed, server, client, lock)
    if release != expected:
        raise ValueError("Candidate12 release-lock content binding mismatch")


def validate_published_candidate12(
    root: Path,
    fixed_waypoint_path: Path,
    fixed_waypoint_sha256: str,
    *,
    baseline_root: Path = CANDIDATE11_ROOT,
    lock: Candidate11Lock = CANDIDATE11_LOCK,
) -> dict[str, Any]:
    root = root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Candidate12 root is not a real directory: {root}")
    expected_entries = {
        "server-mods",
        "client-mods",
        "manifests",
        "release-lock.json",
        "READY.json",
    }
    if {entry.name for entry in root.iterdir()} != expected_entries:
        raise ValueError("Candidate12 root entry set mismatch")
    manifests = root / "manifests"
    if manifests.is_symlink() or {entry.name for entry in manifests.iterdir()} != {
        "server.json",
        "client.json",
    }:
        raise ValueError("Candidate12 manifest entry set mismatch")
    release_path = root / "release-lock.json"
    ready_path = root / "READY.json"
    if release_path.is_symlink() or ready_path.is_symlink():
        raise ValueError("Candidate12 lock files must not be symbolic links")
    if release_path.read_bytes() != ready_path.read_bytes():
        raise ValueError("Candidate12 READY/release-lock bytes differ")
    release = read_json(release_path)
    if release.get("status") != "PASS" or release.get("candidate") != 12:
        raise ValueError("Candidate12 READY is not PASS")
    candidate11 = validate_candidate11(baseline_root, lock)
    fixed = validate_fixed_waypoint(fixed_waypoint_path, fixed_waypoint_sha256)
    replacement = release.get("replacement")
    if not isinstance(replacement, dict) or (
        replacement.get("after_file") != fixed["file"]
        or str(replacement.get("after_sha256", "")).upper() != fixed["sha256"]
    ):
        raise ValueError("Candidate12 READY Waypoint binding mismatch")
    server = validate_candidate12_side(
        root / "manifests" / "server.json",
        root / "server-mods",
        "server",
        candidate11["server"],
        fixed,
    )
    client = validate_candidate12_side(
        root / "manifests" / "client.json",
        root / "client-mods",
        "client",
        candidate11["client"],
        fixed,
    )
    validate_candidate12_pair(server, client, lock)
    _validate_release_bindings(
        root, release, candidate11, fixed, server, client, lock
    )
    return {
        "root": root,
        "release_lock_sha256": sha256(release_path),
        "ready_sha256": sha256(ready_path),
        "server": server,
        "client": client,
        "waypoint": fixed,
        "bundle_pair_sha256": pair_digest(
            server["bundle_sha256"], client["bundle_sha256"]
        ),
    }


def build_candidate12(
    fixed_waypoint_path: Path,
    fixed_waypoint_sha256: str,
    output_root: Path,
    *,
    baseline_root: Path = CANDIDATE11_ROOT,
    lock: Candidate11Lock = CANDIDATE11_LOCK,
) -> dict[str, Any]:
    baseline_root = baseline_root.resolve()
    fixed_waypoint_path = fixed_waypoint_path.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to reuse existing output root: {output_root}")
    if paths_overlap(output_root, baseline_root):
        raise ValueError("output root overlaps the locked Candidate11 baseline")
    if paths_overlap(output_root, HISTORICAL_BACKUP_ROOT):
        raise ValueError("output root overlaps the protected historical backup")
    if paths_overlap(output_root, fixed_waypoint_path):
        raise ValueError("output root overlaps the fixed Waypoint artifact")

    candidate11 = validate_candidate11(baseline_root, lock)
    fixed = validate_fixed_waypoint(fixed_waypoint_path, fixed_waypoint_sha256)
    all_baseline_names = {
        row["file"].casefold()
        for side in (candidate11["server"], candidate11["client"])
        for row in side["rows"]
        if WAYPOINT_MOD_ID not in row["mod_ids"]
    }
    if fixed["file"].casefold() in all_baseline_names:
        raise ValueError("fixed Waypoint filename collides with a non-Waypoint JAR")
    all_baseline_hashes = {
        row["sha256"]
        for side in (candidate11["server"], candidate11["client"])
        for row in side["rows"]
    }
    if fixed["sha256"] in all_baseline_hashes:
        raise ValueError("fixed Waypoint hash collides with a Candidate11 JAR")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=output_root.parent)
    )
    published = False
    try:
        staging_manifests = staging_root / "manifests"
        staging_manifests.mkdir()
        final_manifests = output_root / "manifests"
        server_manifest = copy_and_manifest_side(
            candidate11["server"],
            fixed,
            staging_root / "server-mods",
            output_root / "server-mods",
            final_manifests / "server.json",
        )
        client_manifest = copy_and_manifest_side(
            candidate11["client"],
            fixed,
            staging_root / "client-mods",
            output_root / "client-mods",
            final_manifests / "client.json",
        )
        atomic_write(staging_manifests / "server.json", stable_json(server_manifest))
        atomic_write(staging_manifests / "client.json", stable_json(client_manifest))

        staged_server = validate_candidate12_side(
            staging_manifests / "server.json",
            staging_root / "server-mods",
            "server",
            candidate11["server"],
            fixed,
            expected_manifest_path=final_manifests / "server.json",
            expected_bundle_dir=output_root / "server-mods",
        )
        staged_client = validate_candidate12_side(
            staging_manifests / "client.json",
            staging_root / "client-mods",
            "client",
            candidate11["client"],
            fixed,
            expected_manifest_path=final_manifests / "client.json",
            expected_bundle_dir=output_root / "client-mods",
        )
        validate_candidate12_pair(staged_server, staged_client, lock)
        release = release_record(
            output_root, candidate11, fixed, staged_server, staged_client, lock
        )
        release_bytes = stable_json(release)
        atomic_write(staging_root / "release-lock.json", release_bytes)
        atomic_write(staging_root / "READY.json", release_bytes)

        # Close the source-race window immediately before atomic publication.
        validate_candidate11(baseline_root, lock)
        validate_fixed_waypoint(fixed_waypoint_path, fixed_waypoint_sha256)
        os.replace(staging_root, output_root)
        published = True
        return validate_published_candidate12(
            output_root,
            fixed_waypoint_path,
            fixed_waypoint_sha256,
            baseline_root=baseline_root,
            lock=lock,
        )
    finally:
        if not published and staging_root.exists():
            shutil.rmtree(staging_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or validate fail-closed Candidate12 Waypoint bundles"
    )
    parser.add_argument("--waypoint-jar", type=Path, required=True)
    parser.add_argument("--waypoint-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--validate-existing",
        action="store_true",
        help="validate an existing Candidate12 root instead of building it",
    )
    args = parser.parse_args()
    if args.validate_existing:
        result = validate_published_candidate12(
            args.output_root, args.waypoint_jar, args.waypoint_sha256
        )
    else:
        result = build_candidate12(
            args.waypoint_jar, args.waypoint_sha256, args.output_root
        )
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "validate" if args.validate_existing else "build",
                "output_root": str(result["root"]),
                "waypoint_sha256": result["waypoint"]["sha256"],
                "server_bundle_sha256": result["server"]["bundle_sha256"],
                "client_bundle_sha256": result["client"]["bundle_sha256"],
                "bundle_pair_sha256": result["bundle_pair_sha256"],
                "ready_sha256": result["ready_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
