#!/usr/bin/env python3
"""Build candidate9 bundles by replacing only candidate6's Happy Ghast JAR."""

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


WORKSPACE = Path(__file__).resolve().parents[2]
HAPPY_MOD_ID = "happyghast_equivalence"
EXPECTED_JAR_COUNT = 50


@dataclass(frozen=True)
class Candidate6Lock:
    server_manifest_sha256: str
    client_manifest_sha256: str
    server_bundle_sha256: str
    client_bundle_sha256: str
    old_happy_sha256: str
    old_happy_file: str
    server_only_file: str
    server_only_sha256: str
    server_only_mod_id: str
    client_only_file: str
    client_only_sha256: str
    client_only_mod_id: str


CANDIDATE6_LOCK = Candidate6Lock(
    server_manifest_sha256="9F103C249B03D8BEDDAC66679B2794D2AAD57F87660B9F67C73611D19EB193B9",
    client_manifest_sha256="B27197DBECFD34023DCB8FED64E424B2519054ED585549C9A204C9AB9EBB1C8C",
    server_bundle_sha256="CF8D89759625A42E8FBA924D2A89A619825F1144892EEC1438B957BA550C15C7",
    client_bundle_sha256="368A5C53E75F0550BBF03079DE6930D45C3E72F6A7B298108D051FAD132E82BF",
    old_happy_sha256="A6D18C6B050316283569AC0376718A0C94287322F227903F741A31AB0EB52D2F",
    old_happy_file="happyghast-equivalence-1.0.0-equivalence.1+mc1.21.1.jar",
    server_only_file="grieflogger-1.2.10-1.21.1-neoforge.jar",
    server_only_sha256="FD252BC5466BB94E38D2386BAFB9926B798BC250B26E1A3AA80F878EBCCBC4A5",
    server_only_mod_id="grieflogger",
    client_only_file="chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar",
    client_only_sha256="9CEF2FAC6BD959202E37882B941EBC51A1ED7A4259441D3B41372971FD04F6D8",
    client_only_mod_id="colorizer",
)


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def validate_sha256(value: str, label: str) -> str:
    result = value.strip().upper()
    if not re.fullmatch(r"[0-9A-F]{64}", result):
        raise ValueError(f"{label} is not an uppercase-normalizable SHA-256")
    return result


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def safe_jar_name(value: object) -> str:
    name = str(value)
    if Path(name).name != name or not name.lower().endswith(".jar"):
        raise ValueError(f"unsafe JAR filename: {name!r}")
    if name in {".", ".."} or "\x00" in name:
        raise ValueError(f"unsafe JAR filename: {name!r}")
    return name


def jar_mod_ids(path: Path, *, verify_crc: bool = True) -> set[str]:
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
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
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
        f"server\0{server_bundle.upper()}\n"
        f"client\0{client_bundle.upper()}\n"
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest().upper()


def paths_overlap(left: Path, right: Path) -> bool:
    left_norm = os.path.normcase(str(left.resolve()))
    right_norm = os.path.normcase(str(right.resolve()))
    try:
        common = os.path.normcase(os.path.commonpath((left_norm, right_norm)))
    except ValueError:
        return False
    return common in {left_norm, right_norm}


def _row_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["file"]).casefold(): row for row in rows}


def validate_bundle_manifest(
    manifest_path: Path,
    side: str,
    expected_manifest_sha256: str,
    expected_bundle_sha256: str,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    actual_manifest_hash = sha256(manifest_path)
    if actual_manifest_hash != expected_manifest_sha256:
        raise ValueError(
            f"{side} candidate6 manifest hash mismatch: "
            f"{actual_manifest_hash} != {expected_manifest_sha256}"
        )
    manifest = read_json(manifest_path)
    if manifest.get("schema") != 1 or manifest.get("side") != side:
        raise ValueError(f"{side} candidate6 manifest schema/side mismatch")
    if manifest.get("status") != "PASS":
        raise ValueError(f"{side} candidate6 manifest is not PASS")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != EXPECTED_JAR_COUNT:
        raise ValueError(f"{side} candidate6 manifest must have exactly 50 rows")
    if manifest.get("file_count") != EXPECTED_JAR_COUNT:
        raise ValueError(f"{side} candidate6 file_count is not 50")
    bundle_dir_value = manifest.get("bundle_dir")
    if not isinstance(bundle_dir_value, str):
        raise ValueError(f"{side} candidate6 manifest has no bundle_dir")
    bundle_dir = Path(bundle_dir_value).resolve()
    if not bundle_dir.is_dir():
        raise FileNotFoundError(bundle_dir)

    entries = sorted(bundle_dir.iterdir(), key=lambda item: item.name.casefold())
    if len(entries) != EXPECTED_JAR_COUNT or any(
        not item.is_file() or item.suffix.lower() != ".jar" for item in entries
    ):
        raise ValueError(f"{side} candidate6 directory is not a flat exact 50-JAR set")
    files_by_name = {item.name.casefold(): item for item in entries}
    if len(files_by_name) != EXPECTED_JAR_COUNT:
        raise ValueError(f"{side} candidate6 has case-insensitive filename collisions")

    names_seen: set[str] = set()
    mod_owners: dict[str, str] = {}
    validated_rows: list[dict[str, Any]] = []
    total_bytes = 0
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise ValueError(f"{side} candidate6 manifest contains a non-object row")
        name = safe_jar_name(raw_row.get("file"))
        name_key = name.casefold()
        if name_key in names_seen:
            raise ValueError(f"{side} duplicate manifest filename: {name}")
        names_seen.add(name_key)
        path = files_by_name.get(name_key)
        if path is None:
            raise ValueError(f"{side} candidate6 JAR missing: {name}")
        expected_hash = validate_sha256(str(raw_row.get("sha256", "")), f"{side}:{name}")
        expected_bytes = raw_row.get("bytes")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ValueError(f"{side} invalid byte count for {name}")
        actual_hash = sha256(path)
        if path.stat().st_size != expected_bytes or actual_hash != expected_hash:
            raise ValueError(f"{side} candidate6 hash/size mismatch: {name}")
        actual_ids = jar_mod_ids(path)
        manifest_ids = raw_row.get("mod_ids")
        if not isinstance(manifest_ids, list) or any(
            not isinstance(item, str) for item in manifest_ids
        ):
            raise ValueError(f"{side} invalid mod_ids for {name}")
        if set(manifest_ids) != actual_ids:
            raise ValueError(
                f"{side} mod ID mismatch for {name}: "
                f"manifest={sorted(manifest_ids)}, actual={sorted(actual_ids)}"
            )
        for mod_id in actual_ids:
            owner = mod_owners.get(mod_id)
            if owner is not None:
                raise ValueError(f"{side} duplicate mod ID {mod_id}: {owner}, {name}")
            mod_owners[mod_id] = name
        total_bytes += expected_bytes
        row = dict(raw_row)
        row["file"] = name
        row["sha256"] = expected_hash
        row["mod_ids"] = sorted(actual_ids)
        row["_path"] = path
        validated_rows.append(row)

    if names_seen != set(files_by_name):
        raise ValueError(f"{side} manifest/directory filename set mismatch")
    if [row["file"].casefold() for row in validated_rows] != sorted(names_seen):
        raise ValueError(f"{side} candidate6 rows are not deterministically sorted")
    if total_bytes != manifest.get("bytes"):
        raise ValueError(f"{side} candidate6 byte total mismatch")
    actual_bundle_hash = bundle_digest(validated_rows)
    if actual_bundle_hash != expected_bundle_sha256:
        raise ValueError(
            f"{side} candidate6 locked bundle hash mismatch: "
            f"{actual_bundle_hash} != {expected_bundle_sha256}"
        )
    if actual_bundle_hash != str(manifest.get("bundle_sha256", "")).upper():
        raise ValueError(f"{side} candidate6 manifest bundle hash mismatch")
    return {
        "side": side,
        "manifest_path": manifest_path,
        "manifest_sha256": actual_manifest_hash,
        "bundle_dir": bundle_dir,
        "bundle_sha256": actual_bundle_hash,
        "rows": validated_rows,
        "mod_owners": mod_owners,
    }


def validate_candidate6_pair(
    server: dict[str, Any], client: dict[str, Any], lock: Candidate6Lock
) -> tuple[dict[str, Any], dict[str, Any]]:
    server_rows = _row_map(server["rows"])
    client_rows = _row_map(client["rows"])
    server_only = set(server_rows) - set(client_rows)
    client_only = set(client_rows) - set(server_rows)
    if server_only != {lock.server_only_file.casefold()}:
        raise ValueError(f"unexpected candidate6 server-only files: {sorted(server_only)}")
    if client_only != {lock.client_only_file.casefold()}:
        raise ValueError(f"unexpected candidate6 client-only files: {sorted(client_only)}")
    if len(set(server_rows) & set(client_rows)) != EXPECTED_JAR_COUNT - 1:
        raise ValueError("candidate6 sides do not share exactly 49 filenames")
    for name in set(server_rows) & set(client_rows):
        if server_rows[name]["sha256"] != client_rows[name]["sha256"]:
            raise ValueError(f"candidate6 shared JAR differs across sides: {name}")

    sentinels = (
        (server_rows[lock.server_only_file.casefold()], lock.server_only_sha256, lock.server_only_mod_id),
        (client_rows[lock.client_only_file.casefold()], lock.client_only_sha256, lock.client_only_mod_id),
    )
    for row, expected_hash, expected_id in sentinels:
        if row["sha256"] != expected_hash or set(row["mod_ids"]) != {expected_id}:
            raise ValueError(f"side-specific sentinel mismatch: {row['file']}")

    happy_rows: list[dict[str, Any]] = []
    for side, rows in (("server", server["rows"]), ("client", client["rows"])):
        matches = [row for row in rows if HAPPY_MOD_ID in row["mod_ids"]]
        if len(matches) != 1:
            raise ValueError(f"{side} must contain exactly one {HAPPY_MOD_ID} owner")
        row = matches[0]
        if (
            row["file"] != lock.old_happy_file
            or row["sha256"] != lock.old_happy_sha256
            or set(row["mod_ids"]) != {HAPPY_MOD_ID}
        ):
            raise ValueError(f"{side} old Happy Ghast lock mismatch")
        happy_rows.append(row)
    if happy_rows[0]["sha256"] != happy_rows[1]["sha256"]:
        raise ValueError("candidate6 Happy Ghast JAR differs across sides")
    return happy_rows[0], happy_rows[1]


def validate_replacement(path: Path, expected_sha256: str, lock: Candidate6Lock) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    name = safe_jar_name(path.name)
    expected = validate_sha256(expected_sha256, "replacement SHA-256")
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"replacement hash mismatch: {actual} != {expected}")
    if actual == lock.old_happy_sha256:
        raise ValueError("replacement is byte-identical to the rejected candidate6 Happy Ghast JAR")
    mod_ids = jar_mod_ids(path)
    if mod_ids != {HAPPY_MOD_ID}:
        raise ValueError(
            f"replacement must expose only mod ID {HAPPY_MOD_ID}; found {sorted(mod_ids)}"
        )
    return {
        "path": path,
        "file": name,
        "bytes": path.stat().st_size,
        "sha256": actual,
        "mod_ids": sorted(mod_ids),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "_path"}


def copy_and_manifest_side(
    baseline: dict[str, Any],
    old_happy: dict[str, Any],
    replacement: dict[str, Any],
    staging_mods: Path,
    final_mods: Path,
    final_manifest_path: Path,
) -> dict[str, Any]:
    staging_mods.mkdir(parents=True)
    output_rows: list[dict[str, Any]] = []
    replacement_key = replacement["file"].casefold()
    other_names = {
        row["file"].casefold()
        for row in baseline["rows"]
        if row["file"] != old_happy["file"]
    }
    if replacement_key in other_names:
        raise ValueError(f"replacement filename collides with candidate6: {replacement['file']}")

    for row in baseline["rows"]:
        if row["file"] == old_happy["file"]:
            continue
        source = row["_path"]
        destination = staging_mods / row["file"]
        shutil.copy2(source, destination)
        if destination.stat().st_size != row["bytes"] or sha256(destination) != row["sha256"]:
            raise IOError(f"copy verification failed: {destination}")
        output = _public_row(row)
        output["source"] = str(source)
        output["candidate6_comparison"] = "exact_candidate6"
        output_rows.append(output)

    replacement_destination = staging_mods / replacement["file"]
    shutil.copy2(replacement["path"], replacement_destination)
    if (
        replacement_destination.stat().st_size != replacement["bytes"]
        or sha256(replacement_destination) != replacement["sha256"]
    ):
        raise IOError(f"replacement copy verification failed: {replacement_destination}")
    replacement_row = {
        "file": replacement["file"],
        "bytes": replacement["bytes"],
        "sha256": replacement["sha256"],
        "mod_ids": replacement["mod_ids"],
        "role": old_happy.get("role", "candidate"),
        "component": old_happy.get("component", "Happy Ghast"),
        "source": str(replacement["path"]),
        "candidate6_comparison": "happyghast_stat_compat_replacement",
        "replaces_file": old_happy["file"],
        "replaces_sha256": old_happy["sha256"],
    }
    output_rows.append(replacement_row)
    output_rows.sort(key=lambda row: row["file"].casefold())
    return {
        "schema": 1,
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
        "replacement": {
            "mod_id": HAPPY_MOD_ID,
            "old_file": old_happy["file"],
            "old_sha256": old_happy["sha256"],
            "new_file": replacement["file"],
            "new_sha256": replacement["sha256"],
        },
        "files": output_rows,
    }


def validate_output_side(mods_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    rows = manifest["files"]
    entries = sorted(mods_dir.iterdir(), key=lambda item: item.name.casefold())
    if len(entries) != EXPECTED_JAR_COUNT or len(rows) != EXPECTED_JAR_COUNT:
        raise ValueError(f"assembled {manifest['side']} bundle is not exactly 50 JARs")
    if any(not item.is_file() or item.suffix.lower() != ".jar" for item in entries):
        raise ValueError(f"assembled {manifest['side']} bundle is not flat/JAR-only")
    files_by_name = {item.name.casefold(): item for item in entries}
    if len(files_by_name) != EXPECTED_JAR_COUNT:
        raise ValueError(f"assembled {manifest['side']} bundle has filename collisions")
    mod_owners: dict[str, str] = {}
    for row in rows:
        name = safe_jar_name(row["file"])
        path = files_by_name.get(name.casefold())
        if path is None:
            raise ValueError(f"assembled JAR missing: {name}")
        actual_hash = sha256(path)
        if path.stat().st_size != row["bytes"] or actual_hash != row["sha256"]:
            raise ValueError(f"assembled JAR hash/size mismatch: {name}")
        actual_ids = jar_mod_ids(path)
        if actual_ids != set(row["mod_ids"]):
            raise ValueError(f"assembled JAR mod ID mismatch: {name}")
        for mod_id in actual_ids:
            owner = mod_owners.get(mod_id)
            if owner is not None:
                raise ValueError(f"assembled duplicate mod ID {mod_id}: {owner}, {name}")
            mod_owners[mod_id] = name
    if bundle_digest(rows) != manifest["bundle_sha256"]:
        raise ValueError(f"assembled {manifest['side']} bundle digest mismatch")
    if sum(item.stat().st_size for item in entries) != manifest["bytes"]:
        raise ValueError(f"assembled {manifest['side']} byte total mismatch")
    return mod_owners


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_bundles(
    server_manifest_path: Path,
    client_manifest_path: Path,
    replacement_path: Path,
    replacement_sha256: str,
    output_root: Path,
    *,
    lock: Candidate6Lock = CANDIDATE6_LOCK,
) -> dict[str, Any]:
    server_manifest_path = server_manifest_path.resolve()
    client_manifest_path = client_manifest_path.resolve()
    replacement_path = replacement_path.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite output root: {output_root}")

    server = validate_bundle_manifest(
        server_manifest_path,
        "server",
        lock.server_manifest_sha256,
        lock.server_bundle_sha256,
    )
    client = validate_bundle_manifest(
        client_manifest_path,
        "client",
        lock.client_manifest_sha256,
        lock.client_bundle_sha256,
    )
    server_happy, client_happy = validate_candidate6_pair(server, client, lock)
    replacement = validate_replacement(replacement_path, replacement_sha256, lock)

    backup_root = Path(r"D:\Trans\20260807").resolve()
    if paths_overlap(output_root, backup_root):
        raise ValueError(f"output root overlaps the historical backup: {output_root}")
    for source_dir in (server["bundle_dir"], client["bundle_dir"]):
        if paths_overlap(output_root, source_dir):
            raise ValueError(f"output root overlaps candidate6 source: {source_dir}")
    if paths_overlap(output_root, replacement_path):
        raise ValueError("output root overlaps the replacement JAR path")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.build-", dir=output_root.parent)
    ).resolve()
    published = False
    try:
        staging_server = staging_root / "server-mods"
        staging_client = staging_root / "client-mods"
        final_server = output_root / "server-mods"
        final_client = output_root / "client-mods"
        final_server_manifest = output_root / "manifests" / "server.json"
        final_client_manifest = output_root / "manifests" / "client.json"
        server_manifest = copy_and_manifest_side(
            server,
            server_happy,
            replacement,
            staging_server,
            final_server,
            final_server_manifest,
        )
        client_manifest = copy_and_manifest_side(
            client,
            client_happy,
            replacement,
            staging_client,
            final_client,
            final_client_manifest,
        )
        server_owners = validate_output_side(staging_server, server_manifest)
        client_owners = validate_output_side(staging_client, client_manifest)
        if server_owners.get(lock.server_only_mod_id) != lock.server_only_file:
            raise ValueError("assembled server lost the GriefLogger side sentinel")
        if lock.server_only_mod_id in client_owners:
            raise ValueError("assembled client unexpectedly contains GriefLogger")
        if client_owners.get(lock.client_only_mod_id) != lock.client_only_file:
            raise ValueError("assembled client lost the Chest Colorizer side sentinel")
        if lock.client_only_mod_id in server_owners:
            raise ValueError("assembled server unexpectedly contains Chest Colorizer")

        server_rows = _row_map(server_manifest["files"])
        client_rows = _row_map(client_manifest["files"])
        if set(server_rows) - set(client_rows) != {lock.server_only_file.casefold()}:
            raise ValueError("assembled server/client filename delta changed")
        if set(client_rows) - set(server_rows) != {lock.client_only_file.casefold()}:
            raise ValueError("assembled client/server filename delta changed")
        for name in set(server_rows) & set(client_rows):
            if server_rows[name]["sha256"] != client_rows[name]["sha256"]:
                raise ValueError(f"assembled shared JAR differs across sides: {name}")

        staging_manifests = staging_root / "manifests"
        write_json(staging_manifests / "server.json", server_manifest)
        write_json(staging_manifests / "client.json", client_manifest)
        server_manifest_hash = sha256(staging_manifests / "server.json")
        client_manifest_hash = sha256(staging_manifests / "client.json")
        release = {
            "schema": 1,
            "status": "PASS",
            "purpose": "candidate6 plus Happy Ghast statistic compatibility replacement",
            "output_root": str(output_root),
            "source_unchanged": True,
            "replacement": {
                "file": replacement["file"],
                "bytes": replacement["bytes"],
                "sha256": replacement["sha256"],
                "mod_ids": replacement["mod_ids"],
                "replaces_file": lock.old_happy_file,
                "replaces_sha256": lock.old_happy_sha256,
            },
            "server": {
                "mods_dir": str(final_server),
                "file_count": server_manifest["file_count"],
                "bytes": server_manifest["bytes"],
                "bundle_sha256": server_manifest["bundle_sha256"],
                "manifest": str(final_server_manifest),
                "manifest_sha256": server_manifest_hash,
            },
            "client": {
                "mods_dir": str(final_client),
                "file_count": client_manifest["file_count"],
                "bytes": client_manifest["bytes"],
                "bundle_sha256": client_manifest["bundle_sha256"],
                "manifest": str(final_client_manifest),
                "manifest_sha256": client_manifest_hash,
            },
            "bundle_pair_sha256": pair_digest(
                server_manifest["bundle_sha256"], client_manifest["bundle_sha256"]
            ),
            "side_specific_policy": {
                "server_only_file": lock.server_only_file,
                "server_only_mod_id": lock.server_only_mod_id,
                "client_only_file": lock.client_only_file,
                "client_only_mod_id": lock.client_only_mod_id,
            },
        }
        write_json(staging_root / "release-lock.json", release)

        # Re-read and re-hash every candidate6 input after assembly. Any concurrent
        # source mutation aborts before the staging root can be published.
        server_after = validate_bundle_manifest(
            server_manifest_path,
            "server",
            lock.server_manifest_sha256,
            lock.server_bundle_sha256,
        )
        client_after = validate_bundle_manifest(
            client_manifest_path,
            "client",
            lock.client_manifest_sha256,
            lock.client_bundle_sha256,
        )
        validate_candidate6_pair(server_after, client_after, lock)

        os.replace(staging_root, output_root)
        published = True
        validate_output_side(output_root / "server-mods", server_manifest)
        validate_output_side(output_root / "client-mods", client_manifest)
        if sha256(output_root / "manifests" / "server.json") != server_manifest_hash:
            raise IOError("published server manifest hash mismatch")
        if sha256(output_root / "manifests" / "client.json") != client_manifest_hash:
            raise IOError("published client manifest hash mismatch")
        write_json(output_root / "READY.json", release)
        return release
    finally:
        if not published and staging_root.exists():
            shutil.rmtree(staging_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build fresh 50-JAR server/client bundles from the byte-locked candidate6 "
            "baseline, replacing only Happy Ghast"
        )
    )
    parser.add_argument(
        "--server-manifest",
        type=Path,
        default=WORKSPACE / "outputs/final-server-mods-candidate6-manifest-20260810.json",
    )
    parser.add_argument(
        "--client-manifest",
        type=Path,
        default=WORKSPACE / "outputs/final-client-mods-candidate6-manifest-20260810.json",
    )
    parser.add_argument("--replacement-jar", type=Path, required=True)
    parser.add_argument("--replacement-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_bundles(
        args.server_manifest,
        args.client_manifest,
        args.replacement_jar,
        args.replacement_sha256,
        args.output_root,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "output_root": result["output_root"],
                "replacement_sha256": result["replacement"]["sha256"],
                "server_bundle_sha256": result["server"]["bundle_sha256"],
                "client_bundle_sha256": result["client"]["bundle_sha256"],
                "bundle_pair_sha256": result["bundle_pair_sha256"],
                "ready": str(Path(result["output_root"]) / "READY.json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
