#!/usr/bin/env python3
"""Build Candidate11 from the byte-locked Candidate10 mod bundles.

Candidate11 permits exactly two additions on each side:

* add the sole ``cctweaked_startup_guard`` JAR while retaining CC:Tweaked;
* add the sole ``create_chute_unload_guard`` JAR.

All 50 Candidate10 rows must remain byte-identical.  The published
bundle is deliberately the unsanitized release form; the two established
resource transforms remain confined to disposable server runtime copies.
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


CANDIDATE10_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate10-20260811"
)
HISTORICAL_BACKUP_ROOT = Path(r"<TRANS_ROOT>\20260807")
BASELINE_JAR_COUNT = 50
OUTPUT_JAR_COUNT = 52
CC_BASE_MOD_ID = "computercraft"
CC_COMPAT_MOD_ID = "cctweaked_startup_guard"
GUARD_MOD_ID = "create_chute_unload_guard"

RUNTIME_ONLY_TRANSFORM_FILES = (
    "CreateDragonsPlus-1.11.4.jar",
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar",
)


@dataclass(frozen=True)
class Candidate10Lock:
    release_lock_sha256: str
    server_manifest_sha256: str
    client_manifest_sha256: str
    server_bundle_sha256: str
    client_bundle_sha256: str
    bundle_pair_sha256: str
    cc_file: str
    cc_sha256: str
    server_only_file: str
    server_only_sha256: str
    server_only_mod_id: str
    client_only_file: str
    client_only_sha256: str
    client_only_mod_id: str


@dataclass(frozen=True)
class GuardLock:
    file: str
    bytes: int
    sha256: str
    mod_id: str = GUARD_MOD_ID


CANDIDATE10_LOCK = Candidate10Lock(
    release_lock_sha256="71D13227E80AB70B04CDD800D6E786821ABA759F99397B52960974715DFF5108",
    server_manifest_sha256="79B43927F7D5F99133F4E6B4F2A4C2AEB271ABC9252DE1DADA82D92FCA541054",
    client_manifest_sha256="79677A95935DD67E4196C8CCC99F92D9D817087C1DC7402DCE3A614B44C89553",
    server_bundle_sha256="9C2314D72319339D03D427DE0EFA1CBB85BCEA9C3CE74A0BCD2D0CEC3A2444B5",
    client_bundle_sha256="CEC51F141A226E53E5CB0F64851E6EA37DE6FFC7BFD307863FE2563AA606737F",
    bundle_pair_sha256="21A99DAB3305B072680755446C94A6D6BB03D3234A2CDAA91ED461C12B8444D5",
    cc_file="cc-tweaked-1.21.1-forge-1.120.0.jar",
    cc_sha256="81A903710D109D129C249C105695A96F4BAD5E0ACF7068920FB191BA791C14CE",
    server_only_file="grieflogger-1.2.10-1.21.1-neoforge.jar",
    server_only_sha256="FD252BC5466BB94E38D2386BAFB9926B798BC250B26E1A3AA80F878EBCCBC4A5",
    server_only_mod_id="grieflogger",
    client_only_file="chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar",
    client_only_sha256="9CEF2FAC6BD959202E37882B941EBC51A1ED7A4259441D3B41372971FD04F6D8",
    client_only_mod_id="colorizer",
)

GUARD_LOCK = GuardLock(
    file="create-chute-unload-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar",
    bytes=4018,
    sha256="AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A",
)

CC_COMPAT_LOCK: GuardLock | None = GuardLock(
    file="cctweaked-startup-shutdown-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar",
    bytes=3919,
    sha256="6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7",
    mod_id=CC_COMPAT_MOD_ID,
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
    temporary = path.with_name(f".{path.name}.candidate11.tmp")
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
        raise ValueError(f"{label} is not an uppercase-normalizable SHA-256")
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
            names = set(archive.namelist())
            result: set[str] = set()
            if "fabric.mod.json" in names:
                value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                if isinstance(value, dict) and isinstance(value.get("id"), str):
                    result.add(value["id"])
            for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if name not in names:
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


def _validate_flat_jar_dir(path: Path, expected_count: int, label: str) -> dict[str, Path]:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} is not a real directory: {path}")
    entries = sorted(path.iterdir(), key=lambda item: item.name.casefold())
    if len(entries) != expected_count:
        raise ValueError(f"{label} must contain exactly {expected_count} entries")
    result: dict[str, Path] = {}
    for entry in entries:
        if entry.is_symlink() or not entry.is_file() or entry.suffix.lower() != ".jar":
            raise ValueError(f"{label} contains a non-regular JAR entry: {entry}")
        key = entry.name.casefold()
        if key in result:
            raise ValueError(f"{label} has a case-insensitive collision: {entry.name}")
        result[key] = entry
    return result


def _validate_manifest_rows(
    manifest: dict[str, Any],
    actual_dir: Path,
    expected_count: int,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != expected_count:
        raise ValueError(f"{label} manifest must have exactly {expected_count} rows")
    if manifest.get("file_count") != expected_count:
        raise ValueError(f"{label} manifest file_count mismatch")
    actual_by_name = _validate_flat_jar_dir(actual_dir, expected_count, label)
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
        expected_hash = validate_sha256(str(raw_row.get("sha256", "")), f"{label}:{name}")
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
            owner = owners.get(mod_id.casefold())
            if owner is not None:
                raise ValueError(f"{label} duplicate mod ID {mod_id}: {owner}, {name}")
            owners[mod_id.casefold()] = name
        total_bytes += expected_bytes
        row = dict(raw_row)
        row["file"] = name
        row["bytes"] = expected_bytes
        row["sha256"] = expected_hash
        row["mod_ids"] = sorted(actual_ids)
        row["_path"] = path
        validated.append(row)
    if seen != set(actual_by_name):
        raise ValueError(f"{label} manifest/directory filename set mismatch")
    if [row["file"].casefold() for row in validated] != sorted(seen):
        raise ValueError(f"{label} rows are not deterministically sorted")
    if manifest.get("bytes") != total_bytes:
        raise ValueError(f"{label} manifest byte total mismatch")
    computed = bundle_digest(validated)
    if str(manifest.get("bundle_sha256", "")).upper() != computed:
        raise ValueError(f"{label} manifest bundle digest mismatch")
    return validated, owners


def validate_candidate10_side(
    root: Path,
    side: str,
    lock: Candidate10Lock,
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
    actual_manifest_hash = sha256(manifest_path)
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError(f"Candidate10 {side} manifest lock mismatch")
    manifest = read_json(manifest_path)
    bundle_dir = root / f"{side}-mods"
    if (
        manifest.get("schema") != 1
        or manifest.get("status") != "PASS"
        or manifest.get("side") != side
        or Path(str(manifest.get("bundle_dir", ""))).resolve() != bundle_dir.resolve()
        or Path(str(manifest.get("manifest_path", ""))).resolve() != manifest_path.resolve()
    ):
        raise ValueError(f"Candidate10 {side} manifest content binding mismatch")
    rows, owners = _validate_manifest_rows(
        manifest, bundle_dir, BASELINE_JAR_COUNT, f"Candidate10 {side}"
    )
    computed = bundle_digest(rows)
    if computed != expected_bundle_hash:
        raise ValueError(f"Candidate10 {side} bundle lock mismatch")
    return {
        "side": side,
        "manifest_path": manifest_path.resolve(),
        "manifest_sha256": actual_manifest_hash,
        "bundle_dir": bundle_dir.resolve(),
        "bundle_sha256": computed,
        "rows": rows,
        "owners": owners,
    }


def validate_candidate10(
    root: Path = CANDIDATE10_ROOT,
    lock: Candidate10Lock = CANDIDATE10_LOCK,
) -> dict[str, Any]:
    root = root.resolve()
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Candidate10 root is not a real directory: {root}")
    expected_root_entries = {
        "server-mods",
        "client-mods",
        "manifests",
        "release-lock.json",
        "READY.json",
    }
    if {entry.name for entry in root.iterdir()} != expected_root_entries:
        raise ValueError("Candidate10 root entry set mismatch")
    manifests = root / "manifests"
    if manifests.is_symlink() or not manifests.is_dir():
        raise ValueError("Candidate10 manifests is not a real directory")
    if {entry.name for entry in manifests.iterdir()} != {"server.json", "client.json"}:
        raise ValueError("Candidate10 manifest entry set mismatch")

    release_path = root / "release-lock.json"
    ready_path = root / "READY.json"
    for path in (release_path, ready_path):
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path) != lock.release_lock_sha256:
            raise ValueError(f"Candidate10 lock file hash mismatch: {path.name}")
    if release_path.read_bytes() != ready_path.read_bytes():
        raise ValueError("Candidate10 READY/release-lock bytes differ")
    release = read_json(release_path)

    server = validate_candidate10_side(root, "server", lock)
    client = validate_candidate10_side(root, "client", lock)
    if (
        release.get("schema") != 1
        or release.get("status") != "PASS"
        or Path(str(release.get("output_root", ""))).resolve() != root
        or release.get("source_unchanged") is not True
    ):
        raise ValueError("Candidate10 release-lock content binding mismatch")
    for side, validated in (("server", server), ("client", client)):
        detail = release.get(side)
        if not isinstance(detail, dict) or (
            detail.get("file_count") != BASELINE_JAR_COUNT
            or str(detail.get("bundle_sha256", "")).upper()
            != validated["bundle_sha256"]
            or str(detail.get("manifest_sha256", "")).upper()
            != validated["manifest_sha256"]
        ):
            raise ValueError(f"Candidate10 release-lock {side} binding mismatch")
    computed_pair = pair_digest(server["bundle_sha256"], client["bundle_sha256"])
    if computed_pair != lock.bundle_pair_sha256 or (
        str(release.get("bundle_pair_sha256", "")).upper() != computed_pair
    ):
        raise ValueError("Candidate10 pair digest mismatch")

    server_rows = _row_map(server["rows"])
    client_rows = _row_map(client["rows"])
    server_only = set(server_rows) - set(client_rows)
    client_only = set(client_rows) - set(server_rows)
    if server_only != {lock.server_only_file.casefold()}:
        raise ValueError(f"Candidate10 unexpected server-only files: {sorted(server_only)}")
    if client_only != {lock.client_only_file.casefold()}:
        raise ValueError(f"Candidate10 unexpected client-only files: {sorted(client_only)}")
    shared = set(server_rows) & set(client_rows)
    if len(shared) != BASELINE_JAR_COUNT - 1:
        raise ValueError("Candidate10 sides do not share exactly 49 filenames")
    for key in shared:
        if server_rows[key]["sha256"] != client_rows[key]["sha256"]:
            raise ValueError(f"Candidate10 shared JAR differs across sides: {key}")
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
            raise ValueError(f"Candidate10 side-specific sentinel mismatch: {row['file']}")
    cc_rows: list[dict[str, Any]] = []
    for side, validated in (("server", server), ("client", client)):
        matches = [
            row for row in validated["rows"] if CC_BASE_MOD_ID in row["mod_ids"]
        ]
        if len(matches) != 1:
            raise ValueError(f"Candidate10 {side} must have one {CC_BASE_MOD_ID} owner")
        row = matches[0]
        if (
            row["file"] != lock.cc_file
            or row["sha256"] != lock.cc_sha256
            or set(row["mod_ids"]) != {CC_BASE_MOD_ID}
        ):
            raise ValueError(f"Candidate10 {side} CC lock mismatch")
        cc_rows.append(row)
    if cc_rows[0]["sha256"] != cc_rows[1]["sha256"]:
        raise ValueError("Candidate10 CC differs across sides")
    return {
        "root": root,
        "release": release,
        "release_lock_sha256": sha256(release_path),
        "server": server,
        "client": client,
        "server_cc_base": cc_rows[0],
        "client_cc_base": cc_rows[1],
    }


def validate_patch(
    path: Path,
    expected_sha256: str,
    expected_mod_id: str,
    label: str,
    *,
    rejected_sha256: str | None = None,
    exact_lock: GuardLock | None = None,
) -> dict[str, Any]:
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path)
    name = safe_jar_name(path.name)
    expected = validate_sha256(expected_sha256, f"{label} SHA-256")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: {actual} != {expected}")
    if rejected_sha256 is not None and actual == rejected_sha256:
        raise ValueError(f"{label} is byte-identical to the rejected baseline JAR")
    mod_ids = jar_mod_ids(path)
    if mod_ids != {expected_mod_id}:
        raise ValueError(
            f"{label} must expose only mod ID {expected_mod_id}; found {sorted(mod_ids)}"
        )
    if exact_lock is not None and (
        name != exact_lock.file
        or path.stat().st_size != exact_lock.bytes
        or actual != exact_lock.sha256
        or expected_mod_id != exact_lock.mod_id
    ):
        raise ValueError(f"{label} does not match its delivered artifact lock")
    return {
        "path": path,
        "file": name,
        "bytes": path.stat().st_size,
        "sha256": actual,
        "mod_ids": sorted(mod_ids),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "_path"}


def _copy_verified(source: Path, destination: Path, size: int, digest: str) -> None:
    shutil.copy2(source, destination)
    if destination.stat().st_size != size or sha256(destination) != digest:
        raise IOError(f"copy verification failed: {destination}")


def copy_and_manifest_side(
    baseline: dict[str, Any],
    cc_compat: dict[str, Any],
    guard: dict[str, Any],
    staging_mods: Path,
    final_mods: Path,
    final_manifest_path: Path,
) -> dict[str, Any]:
    staging_mods.mkdir(parents=True)
    existing_names = {row["file"].casefold() for row in baseline["rows"]}
    if cc_compat["file"].casefold() in existing_names:
        raise ValueError(f"CC compat filename collides with Candidate10: {cc_compat['file']}")
    if guard["file"].casefold() in existing_names | {cc_compat["file"].casefold()}:
        raise ValueError(f"guard filename collides with Candidate10/CC compat: {guard['file']}")

    output_rows: list[dict[str, Any]] = []
    for row in baseline["rows"]:
        destination = staging_mods / row["file"]
        _copy_verified(row["_path"], destination, row["bytes"], row["sha256"])
        output = _public_row(row)
        output["source"] = str(row["_path"])
        output["candidate10_comparison"] = "exact_candidate10"
        output_rows.append(output)

    cc_destination = staging_mods / cc_compat["file"]
    _copy_verified(
        cc_compat["path"], cc_destination, cc_compat["bytes"], cc_compat["sha256"]
    )
    output_rows.append(
        {
            "file": cc_compat["file"],
            "bytes": cc_compat["bytes"],
            "sha256": cc_compat["sha256"],
            "mod_ids": cc_compat["mod_ids"],
            "role": "compatibility_guard",
            "component": "CC:Tweaked startup and shutdown guard",
            "source": str(cc_compat["path"]),
            "candidate10_comparison": "added_cc_stop_worker_guard",
        }
    )
    guard_destination = staging_mods / guard["file"]
    _copy_verified(guard["path"], guard_destination, guard["bytes"], guard["sha256"])
    output_rows.append(
        {
            "file": guard["file"],
            "bytes": guard["bytes"],
            "sha256": guard["sha256"],
            "mod_ids": guard["mod_ids"],
            "role": "compatibility_guard",
            "component": "Create chute unload guard",
            "source": str(guard["path"]),
            "candidate10_comparison": "added_create_chute_guard",
        }
    )
    output_rows.sort(key=lambda row: row["file"].casefold())
    if len(output_rows) != OUTPUT_JAR_COUNT:
        raise ValueError("Candidate11 side did not produce exactly 52 rows")
    return {
        "schema": 1,
        "candidate": 11,
        "status": "PASS",
        "side": baseline["side"],
        "baseline_manifest": str(baseline["manifest_path"]),
        "baseline_manifest_sha256": baseline["manifest_sha256"],
        "baseline_bundle_sha256": baseline["bundle_sha256"],
        "bundle_dir": str(final_mods),
        "file_count": len(output_rows),
        "bytes": sum(int(row["bytes"]) for row in output_rows),
        "bundle_sha256": bundle_digest(output_rows),
        "manifest_path": str(final_manifest_path),
        "candidate10_invariance": {
            "baseline_rows": BASELINE_JAR_COUNT,
            "unchanged_rows": BASELINE_JAR_COUNT,
            "replaced_rows": 0,
            "added_rows": 2,
            "allowed_added_mod_ids": [CC_COMPAT_MOD_ID, GUARD_MOD_ID],
        },
        "cc_compat_addition": {
            "mod_id": CC_COMPAT_MOD_ID,
            "file": cc_compat["file"],
            "sha256": cc_compat["sha256"],
        },
        "guard_addition": {
            "mod_id": GUARD_MOD_ID,
            "file": guard["file"],
            "sha256": guard["sha256"],
        },
        "files": output_rows,
    }


def validate_candidate11_side(
    manifest_path: Path,
    actual_dir: Path,
    side: str,
    baseline: dict[str, Any],
    cc_compat: dict[str, Any],
    guard: dict[str, Any],
    *,
    expected_manifest_path: Path | None = None,
    expected_bundle_dir: Path | None = None,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    expected_manifest_path = (expected_manifest_path or manifest_path).resolve()
    expected_bundle_dir = (expected_bundle_dir or actual_dir).resolve()
    if (
        manifest.get("schema") != 1
        or manifest.get("candidate") != 11
        or manifest.get("status") != "PASS"
        or manifest.get("side") != side
        or Path(str(manifest.get("manifest_path", ""))).resolve()
        != expected_manifest_path
        or Path(str(manifest.get("bundle_dir", ""))).resolve() != expected_bundle_dir
    ):
        raise ValueError(f"Candidate11 {side} manifest content binding mismatch")
    rows, owners = _validate_manifest_rows(
        manifest, actual_dir, OUTPUT_JAR_COUNT, f"Candidate11 {side}"
    )
    baseline_rows = _row_map(baseline["rows"])
    output_rows = _row_map(rows)
    unchanged = 0
    for key, old in baseline_rows.items():
        current = output_rows.get(key)
        if current is None or (
            current["bytes"] != old["bytes"] or current["sha256"] != old["sha256"]
        ):
            raise ValueError(f"Candidate11 {side} changed Candidate10 JAR: {old['file']}")
        unchanged += 1
    if unchanged != BASELINE_JAR_COUNT:
        raise ValueError(f"Candidate11 {side} baseline invariance count mismatch")
    expected_names = set(baseline_rows) | {
        cc_compat["file"].casefold(),
        guard["file"].casefold(),
    }
    if set(output_rows) != expected_names:
        raise ValueError(f"Candidate11 {side} has an unapproved third JAR-set change")
    cc_row = output_rows.get(cc_compat["file"].casefold())
    guard_row = output_rows.get(guard["file"].casefold())
    if cc_row is None or (
        cc_row["bytes"] != cc_compat["bytes"]
        or cc_row["sha256"] != cc_compat["sha256"]
        or set(cc_row["mod_ids"]) != {CC_COMPAT_MOD_ID}
    ):
        raise ValueError(f"Candidate11 {side} CC compat binding mismatch")
    if guard_row is None or (
        guard_row["bytes"] != guard["bytes"]
        or guard_row["sha256"] != guard["sha256"]
        or set(guard_row["mod_ids"]) != {GUARD_MOD_ID}
    ):
        raise ValueError(f"Candidate11 {side} guard binding mismatch")
    invariance = manifest.get("candidate10_invariance")
    if not isinstance(invariance, dict) or invariance != {
        "baseline_rows": 50,
        "unchanged_rows": 50,
        "replaced_rows": 0,
        "added_rows": 2,
        "allowed_added_mod_ids": [CC_COMPAT_MOD_ID, GUARD_MOD_ID],
    }:
        raise ValueError(f"Candidate11 {side} invariance declaration mismatch")
    if owners.get(CC_COMPAT_MOD_ID.casefold()) != cc_compat["file"]:
        raise ValueError(f"Candidate11 {side} CC compat owner mismatch")
    if owners.get(CC_BASE_MOD_ID.casefold()) != baseline["owners"][CC_BASE_MOD_ID.casefold()]:
        raise ValueError(f"Candidate11 {side} original CC owner changed")
    if owners.get(GUARD_MOD_ID.casefold()) != guard["file"]:
        raise ValueError(f"Candidate11 {side} guard owner mismatch")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path.resolve(),
        "manifest_sha256": sha256(manifest_path),
        "bundle_dir": actual_dir.resolve(),
        "bundle_sha256": bundle_digest(rows),
        "rows": rows,
    }


def validate_candidate11_pair(
    server: dict[str, Any],
    client: dict[str, Any],
    lock: Candidate10Lock,
) -> None:
    server_rows = _row_map(server["rows"])
    client_rows = _row_map(client["rows"])
    if set(server_rows) - set(client_rows) != {lock.server_only_file.casefold()}:
        raise ValueError("Candidate11 server-only policy changed")
    if set(client_rows) - set(server_rows) != {lock.client_only_file.casefold()}:
        raise ValueError("Candidate11 client-only policy changed")
    shared = set(server_rows) & set(client_rows)
    if len(shared) != OUTPUT_JAR_COUNT - 1:
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
            raise ValueError(f"Candidate11 side-specific sentinel changed: {row['file']}")


def release_record(
    output_root: Path,
    candidate10: dict[str, Any],
    cc_compat: dict[str, Any],
    guard: dict[str, Any],
    server: dict[str, Any],
    client: dict[str, Any],
    lock: Candidate10Lock,
) -> dict[str, Any]:
    return {
        "schema": 1,
        "candidate": 11,
        "status": "PASS",
        "purpose": "Candidate10 plus Create chute and CC startup/shutdown guards",
        "output_root": str(output_root),
        "source_unchanged": True,
        "baseline": {
            "candidate": 10,
            "root": str(candidate10["root"]),
            "release_lock_sha256": candidate10["release_lock_sha256"],
            "server_manifest_sha256": candidate10["server"]["manifest_sha256"],
            "client_manifest_sha256": candidate10["client"]["manifest_sha256"],
            "server_bundle_sha256": candidate10["server"]["bundle_sha256"],
            "client_bundle_sha256": candidate10["client"]["bundle_sha256"],
            "bundle_pair_sha256": lock.bundle_pair_sha256,
        },
        "patches": {
            "cc_stop_worker_compat": {
                "file": cc_compat["file"],
                "bytes": cc_compat["bytes"],
                "sha256": cc_compat["sha256"],
                "mod_ids": cc_compat["mod_ids"],
                "operation": "add_both_sides",
                "requires_file": lock.cc_file,
                "requires_sha256": lock.cc_sha256,
            },
            "create_chute_guard": {
                "file": guard["file"],
                "bytes": guard["bytes"],
                "sha256": guard["sha256"],
                "mod_ids": guard["mod_ids"],
                "operation": "add_both_sides",
            },
        },
        "candidate10_invariance": {
            "baseline_rows_per_side": BASELINE_JAR_COUNT,
            "unchanged_rows_per_side": BASELINE_JAR_COUNT,
            "replaced_rows_per_side": 0,
            "added_rows_per_side": 2,
        },
        "server": {
            "mods_dir": str(output_root / "server-mods"),
            "file_count": OUTPUT_JAR_COUNT,
            "bytes": server["manifest"]["bytes"],
            "bundle_sha256": server["bundle_sha256"],
            "manifest": str(output_root / "manifests" / "server.json"),
            "manifest_sha256": server["manifest_sha256"],
        },
        "client": {
            "mods_dir": str(output_root / "client-mods"),
            "file_count": OUTPUT_JAR_COUNT,
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
            "must_remain_byte_identical": [cc_compat["file"], guard["file"]],
            "client_runtime_jar_transforms_allowed": False,
        },
    }


def _validate_release_bindings(
    root: Path,
    release: dict[str, Any],
    candidate10: dict[str, Any],
    cc_compat: dict[str, Any],
    guard: dict[str, Any],
    server: dict[str, Any],
    client: dict[str, Any],
    lock: Candidate10Lock,
) -> None:
    expected = release_record(
        root, candidate10, cc_compat, guard, server, client, lock
    )
    if release != expected:
        raise ValueError("Candidate11 release-lock content binding mismatch")


def validate_published_candidate11(
    root: Path,
    *,
    baseline_root: Path = CANDIDATE10_ROOT,
    lock: Candidate10Lock = CANDIDATE10_LOCK,
    guard_lock: GuardLock = GUARD_LOCK,
    cc_compat_lock: GuardLock | None = CC_COMPAT_LOCK,
) -> dict[str, Any]:
    if cc_compat_lock is None:
        raise ValueError("final CC compatibility artifact lock is not configured")
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
    if release_path.is_symlink() or ready_path.is_symlink():
        raise ValueError("Candidate11 lock files must not be symbolic links")
    if release_path.read_bytes() != ready_path.read_bytes():
        raise ValueError("Candidate11 READY/release-lock bytes differ")
    release = read_json(release_path)
    if release.get("status") != "PASS" or release.get("candidate") != 11:
        raise ValueError("Candidate11 READY is not PASS")

    candidate10 = validate_candidate10(baseline_root, lock)
    patches = release.get("patches")
    if not isinstance(patches, dict):
        raise ValueError("Candidate11 READY has no patch binding")
    cc_detail = patches.get("cc_stop_worker_compat")
    guard_detail = patches.get("create_chute_guard")
    if not isinstance(cc_detail, dict) or not isinstance(guard_detail, dict):
        raise ValueError("Candidate11 READY patch binding is incomplete")
    cc_file = safe_jar_name(cc_detail.get("file"))
    guard_file = safe_jar_name(guard_detail.get("file"))
    cc_path = root / "server-mods" / cc_file
    guard_path = root / "server-mods" / guard_file
    cc_compat = validate_patch(
        cc_path,
        str(cc_detail.get("sha256", "")),
        CC_COMPAT_MOD_ID,
        "published CC compatibility guard",
        exact_lock=cc_compat_lock,
    )
    guard = validate_patch(
        guard_path,
        str(guard_detail.get("sha256", "")),
        GUARD_MOD_ID,
        "published Create chute guard",
        exact_lock=guard_lock,
    )
    server = validate_candidate11_side(
        root / "manifests" / "server.json",
        root / "server-mods",
        "server",
        candidate10["server"],
        cc_compat,
        guard,
    )
    client = validate_candidate11_side(
        root / "manifests" / "client.json",
        root / "client-mods",
        "client",
        candidate10["client"],
        cc_compat,
        guard,
    )
    validate_candidate11_pair(server, client, lock)
    _validate_release_bindings(
        root, release, candidate10, cc_compat, guard, server, client, lock
    )
    return {
        "root": root,
        "release_lock_sha256": sha256(release_path),
        "ready_sha256": sha256(ready_path),
        "server": server,
        "client": client,
        "cc_compat": cc_compat,
        "guard": guard,
        "bundle_pair_sha256": pair_digest(
            server["bundle_sha256"], client["bundle_sha256"]
        ),
    }


def build_candidate11(
    cc_compat_path: Path,
    cc_compat_sha256: str,
    guard_path: Path,
    guard_sha256: str,
    output_root: Path,
    *,
    baseline_root: Path = CANDIDATE10_ROOT,
    lock: Candidate10Lock = CANDIDATE10_LOCK,
    guard_lock: GuardLock = GUARD_LOCK,
    cc_compat_lock: GuardLock | None = CC_COMPAT_LOCK,
) -> dict[str, Any]:
    if cc_compat_lock is None:
        raise ValueError("final CC compatibility artifact lock is not configured")
    baseline_root = baseline_root.resolve()
    cc_compat_path = cc_compat_path.resolve()
    guard_path = guard_path.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to reuse existing output root: {output_root}")
    if paths_overlap(output_root, baseline_root):
        raise ValueError("output root overlaps the locked Candidate10 baseline")
    if paths_overlap(output_root, HISTORICAL_BACKUP_ROOT):
        raise ValueError("output root overlaps the protected historical backup")
    if paths_overlap(output_root, cc_compat_path) or paths_overlap(output_root, guard_path):
        raise ValueError("output root overlaps an input patch artifact")
    if cc_compat_path == guard_path:
        raise ValueError("CC compat and Create chute guard must be distinct artifacts")

    candidate10 = validate_candidate10(baseline_root, lock)
    cc_compat = validate_patch(
        cc_compat_path,
        cc_compat_sha256,
        CC_COMPAT_MOD_ID,
        "CC startup/shutdown compatibility guard",
        exact_lock=cc_compat_lock,
    )
    guard = validate_patch(
        guard_path,
        guard_sha256,
        GUARD_MOD_ID,
        "Create chute guard",
        exact_lock=guard_lock,
    )
    baseline_hashes = {
        row["sha256"]
        for side in (candidate10["server"], candidate10["client"])
        for row in side["rows"]
    }
    if cc_compat["sha256"] in baseline_hashes or guard["sha256"] in baseline_hashes:
        raise ValueError("a Candidate11 patch is byte-identical to a Candidate10 JAR")
    if cc_compat["sha256"] == guard["sha256"]:
        raise ValueError("Candidate11 patch artifacts have identical hashes")

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
            candidate10["server"],
            cc_compat,
            guard,
            staging_root / "server-mods",
            output_root / "server-mods",
            final_manifests / "server.json",
        )
        client_manifest = copy_and_manifest_side(
            candidate10["client"],
            cc_compat,
            guard,
            staging_root / "client-mods",
            output_root / "client-mods",
            final_manifests / "client.json",
        )
        atomic_write(staging_manifests / "server.json", stable_json(server_manifest))
        atomic_write(staging_manifests / "client.json", stable_json(client_manifest))

        staged_server = validate_candidate11_side(
            staging_manifests / "server.json",
            staging_root / "server-mods",
            "server",
            candidate10["server"],
            cc_compat,
            guard,
            expected_manifest_path=final_manifests / "server.json",
            expected_bundle_dir=output_root / "server-mods",
        )
        staged_client = validate_candidate11_side(
            staging_manifests / "client.json",
            staging_root / "client-mods",
            "client",
            candidate10["client"],
            cc_compat,
            guard,
            expected_manifest_path=final_manifests / "client.json",
            expected_bundle_dir=output_root / "client-mods",
        )
        validate_candidate11_pair(staged_server, staged_client, lock)
        release = release_record(
            output_root,
            candidate10,
            cc_compat,
            guard,
            staged_server,
            staged_client,
            lock,
        )
        atomic_write(staging_root / "release-lock.json", stable_json(release))

        # Close the source-race window before publication.  READY is still absent.
        validate_candidate10(baseline_root, lock)
        validate_patch(
            cc_compat_path,
            cc_compat_sha256,
            CC_COMPAT_MOD_ID,
            "CC startup/shutdown compatibility guard",
            exact_lock=cc_compat_lock,
        )
        validate_patch(
            guard_path,
            guard_sha256,
            GUARD_MOD_ID,
            "Create chute guard",
            exact_lock=guard_lock,
        )
        os.replace(staging_root, output_root)
        published = True

        published_server = validate_candidate11_side(
            output_root / "manifests" / "server.json",
            output_root / "server-mods",
            "server",
            candidate10["server"],
            cc_compat,
            guard,
        )
        published_client = validate_candidate11_side(
            output_root / "manifests" / "client.json",
            output_root / "client-mods",
            "client",
            candidate10["client"],
            cc_compat,
            guard,
        )
        validate_candidate11_pair(published_server, published_client, lock)
        published_release = read_json(output_root / "release-lock.json")
        _validate_release_bindings(
            output_root,
            published_release,
            candidate10,
            cc_compat,
            guard,
            published_server,
            published_client,
            lock,
        )
        atomic_write(output_root / "READY.json", stable_json(published_release))
        return validate_published_candidate11(
            output_root,
            baseline_root=baseline_root,
            lock=lock,
            guard_lock=guard_lock,
            cc_compat_lock=cc_compat_lock,
        )
    finally:
        if not published and staging_root.exists():
            shutil.rmtree(staging_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build fail-closed Candidate11 server/client mod bundles"
    )
    parser.add_argument("--cc-compat-jar", type=Path, required=True)
    parser.add_argument("--cc-compat-sha256", required=True)
    parser.add_argument("--guard-jar", type=Path, required=True)
    parser.add_argument("--guard-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_candidate11(
        args.cc_compat_jar,
        args.cc_compat_sha256,
        args.guard_jar,
        args.guard_sha256,
        args.output_root,
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "output_root": str(result["root"]),
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
