#!/usr/bin/env python3
"""Build the first-release Candidate14 mod bundle from a locked Candidate13.

This builder is intentionally fail-closed.  It reads the published Candidate13
tree, verifies every byte and archive CRC, copies all 52 baseline rows without
modification, then adds two BOTH-side crash/data-safety guards to both sides.
MCModSync is audited and hash-locked but deliberately not installed in this
runtime bundle until a valid Config.jar and HTTPS manifest have been frozen.
A fresh staging tree is published with one atomic rename; an existing
Candidate14 output is never reused.

No Minecraft/Java process is started by this module.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib
from typing import Any
import zipfile


WORKSPACE = Path(__file__).resolve().parents[2]
CANDIDATE13_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate13-20260812"
)
DEFAULT_OUTPUT_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate14-20260812"
)
DEFAULT_REPORT = WORKSPACE / "outputs/candidate14-bundle-build-20260812.json"
DEFAULT_MARKDOWN = WORKSPACE / "outputs/candidate14-bundle-build-20260812.md"

CANDIDATE13_LOCK = {
    "ready_sha256": "FA992151079AEE46DCDAEB49D23487F0F4642099E86F0962469E2257E830BA3F",
    "server_manifest_sha256": "FE8771CFAEBCD6E1522ABF27D153D47595DCBDE037BC3A1EE5D1C59156810496",
    "client_manifest_sha256": "261ADB612DB2A2D992F8A8CAC0FC8C753D6620B98B8CB79E693CC434E57216BE",
    "server_bundle_sha256": "C1B8326DC78C4D3558C82C6199278F8F95EFB0CE3FCC7A7F9FE107F3FCB7EFD3",
    "client_bundle_sha256": "AC9887DB6F12E0A9E9F8B77030C3F904276DB8BFD4BDF9D01C4B9DAF9EEA4495",
    "bundle_pair_sha256": "FBE4463D0287FFB8D84EF6A88642C5C87D567009577D8FA39136EF83BBF07D8B",
}

SCARECROW_FILE = (
    "kaleidoscope-cookery-scarecrow-compat-1.0.0+neoforge.1.21.1-candidate13.1.jar"
)
SCARECROW_SOURCE = (
    WORKSPACE
    / "outputs/projects/kaleidoscope-cookery-scarecrow-compat/build/libs"
    / SCARECROW_FILE
)
SCARECROW_SHA256 = "E06FCFEA1FF76FB22EAD50964C18F22657971E42B6E82F0A2FE844C2F048B463"
SCARECROW_MOD_ID = "kaleidoscope_cookery_scarecrow_compat"

PROTECTION_FILE = (
    "deferred-content-protection-1.0.0+neoforge.1.21.1-first-release.1.jar"
)
PROTECTION_SOURCE = (
    WORKSPACE
    / "outputs/projects/deferred-content-protection-neoforge/build/libs"
    / PROTECTION_FILE
)
PROTECTION_SHA256 = "1C7C4B2A76978C563C18EE05ABA9292099E6B15BA920CF2699904068F0B1104B"
PROTECTION_MOD_ID = "deferred_content_protection"

MCSYNC_FILE = "MCModSync-1.9.1.jar"
MCSYNC_SOURCE = WORKSPACE / "outputs/outputs/MCModSync-1.9.1.jar"
MCSYNC_SHA256 = "2DD2BEC977B8669D0EF6C90FC54A06021DC0998E903B583517052B1B5CDA25AA"
MCSYNC_MOD_ID = "mcmodsync"

RUNTIME_SANITIZED_ROOT = Path(
    r"<AUDIT_ROOT>\manual-test-candidate13-runtime-r2-20260812\mods"
)
RUNTIME_SANITIZER_LOCK = {
    "CreateDragonsPlus-1.11.4.jar": {
        "sha256": "123A7636377C64B9A92C3712D6572C6D69BE69FD892FEFF44034AB5B738F972B",
        "bytes": 1024746,
    },
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar": {
        "sha256": "490D90CCACA95F97C469D55136AC0F231681BC9DC6C335A5B20BAEF704C191FE",
        "bytes": 1019472,
    },
}


@dataclass(frozen=True)
class BaselineLock:
    ready_sha256: str
    server_manifest_sha256: str
    client_manifest_sha256: str
    server_bundle_sha256: str
    client_bundle_sha256: str
    bundle_pair_sha256: str


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.candidate14.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _real_dir(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} is not a real directory: {path}")


def _real_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is not a regular file: {path}")


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


def _metadata(path: Path) -> dict[str, Any]:
    """Return IDs and explicit side declarations from JAR metadata."""
    _real_file(path, "JAR")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a ZIP/JAR: {path}")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"JAR CRC failure in {bad}: {path}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"JAR has duplicate entries: {path}")
        ids: set[str] = set()
        sides: set[str] = set()
        metadata_files: list[str] = []
        if "fabric.mod.json" in names:
            metadata_files.append("fabric.mod.json")
            value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
            if isinstance(value, dict) and isinstance(value.get("id"), str):
                ids.add(value["id"])
            environment = value.get("environment") if isinstance(value, dict) else None
            if environment in {"client", "server", "*"}:
                sides.add("CLIENT" if environment == "client" else "SERVER" if environment == "server" else "BOTH")
        for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
            if name not in names:
                continue
            metadata_files.append(name)
            value = tomllib.loads(archive.read(name).decode("utf-8"))
            for mod in value.get("mods", []):
                if isinstance(mod, dict) and isinstance(mod.get("modId"), str):
                    if "${" not in mod["modId"]:
                        ids.add(mod["modId"])
                    side = mod.get("side")
                    if isinstance(side, str):
                        sides.add(side.upper())
            for deps in value.values():
                if isinstance(deps, list):
                    for entry in deps:
                        if isinstance(entry, dict) and isinstance(entry.get("side"), str):
                            sides.add(entry["side"].upper())
            dependencies = value.get("dependencies")
            if isinstance(dependencies, dict):
                for entries in dependencies.values():
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        if isinstance(entry, dict) and isinstance(entry.get("side"), str):
                            sides.add(entry["side"].upper())
        return {
            "mod_ids": sorted(ids),
            "declared_sides": sorted(sides),
            "metadata_files": metadata_files,
        }


def _snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(
        (p for p in root.rglob("*") if p.is_file()),
        key=lambda p: str(p.relative_to(root)).casefold(),
    ):
        result[str(path.relative_to(root)).replace("\\", "/")] = sha256(path)
    return result


def _snapshot_digest(snapshot: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, value in snapshot.items():
        digest.update(name.encode("utf-8")); digest.update(b"\0"); digest.update(value.encode("ascii")); digest.update(b"\n")
    return digest.hexdigest().upper()


def _validate_candidate13(root: Path, lock: BaselineLock) -> dict[str, Any]:
    root = root.resolve()
    _real_dir(root, "Candidate13 root")
    expected = {"server-mods", "client-mods", "manifests", "READY.json", "release-lock.json"}
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError("Candidate13 root entry set mismatch")
    ready = root / "READY.json"
    release = root / "release-lock.json"
    if ready.read_bytes() != release.read_bytes():
        raise ValueError("Candidate13 READY/release-lock bytes differ")
    if sha256(ready) != lock.ready_sha256.upper():
        raise ValueError("Candidate13 READY hash lock mismatch")
    release_json = read_json(ready)
    if release_json.get("schema") != 1 or release_json.get("candidate") != 13 or release_json.get("status") != "PASS":
        raise ValueError("Candidate13 release header mismatch")
    if release_json.get("source_unchanged") is not True:
        raise ValueError("Candidate13 source_unchanged lock mismatch")
    sides: dict[str, Any] = {}
    for side in ("server", "client"):
        manifest_path = root / "manifests" / f"{side}.json"
        mods_dir = root / f"{side}-mods"
        _real_file(manifest_path, f"Candidate13 {side} manifest")
        _real_dir(mods_dir, f"Candidate13 {side} mods")
        expected_m = getattr(lock, f"{side}_manifest_sha256")
        if sha256(manifest_path) != expected_m.upper():
            raise ValueError(f"Candidate13 {side} manifest lock mismatch")
        manifest = read_json(manifest_path)
        rows = manifest.get("files")
        if manifest.get("candidate") != 13 or manifest.get("status") != "PASS" or manifest.get("file_count") != 52 or not isinstance(rows, list) or len(rows) != 52:
            raise ValueError(f"Candidate13 {side} manifest header/count mismatch")
        actual = {p.name.casefold(): p for p in mods_dir.iterdir()}
        if len(actual) != 52 or any(p.is_symlink() or not p.is_file() or p.suffix.lower() != ".jar" for p in actual.values()):
            raise ValueError(f"Candidate13 {side} mods directory mismatch")
        seen: set[str] = set(); normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("file"), str):
                raise ValueError(f"Candidate13 {side} invalid manifest row")
            filename = row["file"]; key = filename.casefold()
            if key in seen or key not in actual:
                raise ValueError(f"Candidate13 {side} row/file mismatch: {filename}")
            seen.add(key); path = actual[key]
            if path.stat().st_size != row.get("bytes") or sha256(path) != str(row.get("sha256", "")).upper():
                raise ValueError(f"Candidate13 {side} byte/hash mismatch: {filename}")
            meta = _metadata(path)
            if set(row.get("mod_ids", [])) != set(meta["mod_ids"]):
                raise ValueError(f"Candidate13 {side} mod ID mismatch: {filename}")
            copied = dict(row); copied["_path"] = path; normalized.append(copied)
        if seen != set(actual) or normalized != sorted(normalized, key=lambda r: str(r["file"]).casefold()):
            raise ValueError(f"Candidate13 {side} manifest ordering/set mismatch")
        bundle = bundle_digest(normalized)
        if bundle != str(manifest.get("bundle_sha256", "")).upper() or bundle != getattr(lock, f"{side}_bundle_sha256").upper():
            raise ValueError(f"Candidate13 {side} bundle digest lock mismatch")
        sides[side] = {"manifest": manifest, "manifest_path": manifest_path, "rows": normalized, "bundle_sha256": bundle, "mods_dir": mods_dir}
    pair = pair_digest(sides["server"]["bundle_sha256"], sides["client"]["bundle_sha256"])
    if pair != str(release_json.get("bundle_pair_sha256", "")).upper() or pair != lock.bundle_pair_sha256.upper():
        raise ValueError("Candidate13 pair digest lock mismatch")
    for side in ("server", "client"):
        bound = release_json.get(side)
        if (
            not isinstance(bound, dict)
            or bound.get("file_count") != 52
            or str(bound.get("bundle_sha256", "")).upper() != sides[side]["bundle_sha256"]
            or str(bound.get("manifest_sha256", "")).upper() != sha256(sides[side]["manifest_path"])
        ):
            raise ValueError(f"Candidate13 release-lock {side} binding mismatch")
    # Existing side-specific policy must remain exactly the baseline policy.
    if release_json.get("side_specific_policy", {}).get("server_only_file") not in {r["file"] for r in sides["server"]["rows"]}:
        raise ValueError("Candidate13 side-specific policy is malformed")
    return {"root": root, "ready": ready, "ready_hash": sha256(ready), "release": release_json, **sides, "pair": pair}


def _new_artifact(path: Path, filename: str, expected_sha: str, mod_id: str, role: str, side: str) -> dict[str, Any]:
    _real_file(path, f"new {filename}")
    if path.name != filename:
        raise ValueError(f"new artifact filename mismatch: {path.name} != {filename}")
    actual_sha = sha256(path)
    if actual_sha != expected_sha.upper():
        raise ValueError(f"new artifact hash mismatch {filename}: {actual_sha} != {expected_sha}")
    meta = _metadata(path)
    if set(meta["mod_ids"]) != {mod_id}:
        raise ValueError(f"new artifact mod ID mismatch {filename}: {meta['mod_ids']}")
    return {
        "path": path.resolve(), "file": filename, "bytes": path.stat().st_size,
        "sha256": actual_sha, "mod_ids": [mod_id], "metadata": meta,
        "role": role, "side": side,
    }


def _build_side(base: dict[str, Any], additions: list[dict[str, Any]], staging: Path, output_root: Path, side: str) -> dict[str, Any]:
    destination = staging / f"{side}-mods"; destination.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    for old in base["rows"]:
        out = destination / str(old["file"])
        shutil.copy2(old["_path"], out)
        if out.stat().st_size != old["bytes"] or sha256(out) != str(old["sha256"]).upper():
            raise IOError(f"baseline copy verification failed: {side}/{out.name}")
        row = {k: v for k, v in old.items() if k != "_path"}
        rows.append(row)
    for artifact in additions:
        out = destination / artifact["file"]
        shutil.copy2(artifact["path"], out)
        if out.stat().st_size != artifact["bytes"] or sha256(out) != artifact["sha256"]:
            raise IOError(f"new artifact copy verification failed: {side}/{out.name}")
        rows.append({
            "file": artifact["file"], "bytes": artifact["bytes"], "sha256": artifact["sha256"],
            "mod_ids": artifact["mod_ids"], "role": "candidate14_addition", "component": artifact["role"],
            "source": str(artifact["path"]), "expected_sha256": artifact["sha256"], "expected_bytes": artifact["bytes"],
            "side_policy": artifact["side"], "metadata_files": artifact["metadata"]["metadata_files"],
            "declared_sides": artifact["metadata"]["declared_sides"],
        })
    rows.sort(key=lambda row: str(row["file"]).casefold())
    if len(rows) != 52 + len(additions) or len({str(r["file"]).casefold() for r in rows}) != len(rows):
        raise ValueError(f"Candidate14 {side} row count or duplicate filename mismatch")
    ids: dict[str, str] = {}
    for row in rows:
        for mod_id in row.get("mod_ids", []):
            if mod_id in ids and ids[mod_id] != row["file"]:
                raise ValueError(f"duplicate mod ID {mod_id}: {ids[mod_id]} / {row['file']}")
            ids[mod_id] = row["file"]
    manifest = {
        "schema": 1, "candidate": 14, "status": "PASS", "side": side,
        "baseline_candidate": 13, "baseline_manifest": str(base["manifest_path"].resolve()),
        "baseline_manifest_sha256": sha256(base["manifest_path"]), "baseline_bundle_sha256": base["bundle_sha256"],
        "bundle_dir": str((output_root / f"{side}-mods").resolve()), "file_count": len(rows),
        "bytes": sum(int(r["bytes"]) for r in rows), "bundle_sha256": bundle_digest(rows),
        "manifest_path": str((output_root / "manifests" / f"{side}.json").resolve()),
        "candidate13_invariance": {"baseline_rows": 52, "unchanged_rows": 52, "replaced_rows": 0, "added_rows": len(additions), "removed_rows": 0, "all_baseline_rows_byte_identical": True},
        "files": rows,
    }
    return {"side": side, "rows": rows, "manifest": manifest, "bundle_sha256": manifest["bundle_sha256"], "mods_dir": destination}


def _validate_built_side(result: dict[str, Any], baseline: dict[str, Any], tree_root: Path) -> None:
    side = result["side"]
    rows = result["rows"]
    current = {str(row["file"]).casefold(): row for row in rows}
    old = {str(row["file"]).casefold(): row for row in baseline["rows"]}
    if len(old) != 52 or len(current) != len(rows):
        raise ValueError(f"Candidate14 {side} row cardinality mismatch")
    for key, row in old.items():
        expected = {name: value for name, value in row.items() if name != "_path"}
        if current.get(key) != expected:
            raise ValueError(f"Candidate14 changed Candidate13 manifest row: {side}/{row['file']}")
    mods_dir = tree_root / f"{side}-mods"
    actual = {p.name.casefold(): p for p in mods_dir.iterdir()}
    if set(actual) != set(current) or len(actual) != len(rows):
        raise ValueError(f"Candidate14 {side} published file set mismatch")
    for key, row in current.items():
        path = actual[key]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row["bytes"]
            or sha256(path) != str(row["sha256"]).upper()
            or set(_metadata(path)["mod_ids"]) != set(row.get("mod_ids", []))
        ):
            raise ValueError(f"Candidate14 {side} published JAR validation failed: {path.name}")
    manifest_path = tree_root / "manifests" / f"{side}.json"
    if read_json(manifest_path) != result["manifest"]:
        raise ValueError(f"Candidate14 {side} manifest content mismatch")
    if bundle_digest(rows) != result["bundle_sha256"]:
        raise ValueError(f"Candidate14 {side} bundle digest mismatch")


def _runtime_identity(
    server_rows: list[dict[str, Any]],
    runtime_root: Path = RUNTIME_SANITIZED_ROOT,
) -> dict[str, Any] | None:
    """Calculate the Candidate14 runtime identity using only the two locked transforms."""
    if not runtime_root.is_dir():
        return None
    rows: list[dict[str, Any]] = []
    for row in server_rows:
        filename = str(row["file"])
        if filename in RUNTIME_SANITIZER_LOCK:
            path = runtime_root / filename
            expected = RUNTIME_SANITIZER_LOCK[filename]
            _real_file(path, f"sanitized runtime {filename}")
            if path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
                raise ValueError(f"sanitized runtime lock mismatch: {filename}")
            rows.append({"file": filename, "bytes": expected["bytes"], "sha256": expected["sha256"]})
        else:
            rows.append({"file": filename, "bytes": row["bytes"], "sha256": row["sha256"]})
    return {"files": len(rows), "bytes": sum(int(r["bytes"]) for r in rows), "bundle_sha256": bundle_digest(rows), "sanitized_jars": sorted(RUNTIME_SANITIZER_LOCK)}


def build_candidate14(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    baseline_root: Path = CANDIDATE13_ROOT,
    report_path: Path = DEFAULT_REPORT,
    markdown_path: Path = DEFAULT_MARKDOWN,
    lock: BaselineLock | None = None,
    scarecrow_source: Path = SCARECROW_SOURCE,
    scarecrow_sha256: str = SCARECROW_SHA256,
    protection_source: Path = PROTECTION_SOURCE,
    protection_sha256: str = PROTECTION_SHA256,
    mcsync_source: Path = MCSYNC_SOURCE,
    mcsync_sha256: str = MCSYNC_SHA256,
    runtime_sanitized_root: Path = RUNTIME_SANITIZED_ROOT,
) -> dict[str, Any]:
    output_root = output_root.resolve(); baseline_root = baseline_root.resolve()
    report_path = report_path.resolve(); markdown_path = markdown_path.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to reuse existing output root: {output_root}")
    if report_path.exists() or markdown_path.exists():
        raise FileExistsError("refusing to overwrite existing Candidate14 build report")
    lock = lock or BaselineLock(**CANDIDATE13_LOCK)
    baseline = _validate_candidate13(baseline_root, lock)
    before_snapshot = _snapshot(baseline_root)
    scarecrow = _new_artifact(scarecrow_source.resolve(), SCARECROW_FILE, scarecrow_sha256, SCARECROW_MOD_ID, "scarecrow legacy NBT compat", "BOTH")
    protection = _new_artifact(protection_source.resolve(), PROTECTION_FILE, protection_sha256, PROTECTION_MOD_ID, "deferred content protection", "BOTH")
    mcsync = _new_artifact(mcsync_source.resolve(), MCSYNC_FILE, mcsync_sha256, MCSYNC_MOD_ID, "client OTA synchronizer", "CLIENT")
    if not any(s in {"CLIENT"} for s in mcsync["metadata"]["declared_sides"]):
        raise ValueError("MCModSync metadata does not declare CLIENT side")
    for artifact in (scarecrow, protection):
        if artifact["metadata"]["declared_sides"] and not any(s in {"BOTH", "*"} for s in artifact["metadata"]["declared_sides"]):
            raise ValueError(f"BOTH-side artifact metadata mismatch: {artifact['file']}")
    additions = {"server": [scarecrow, protection], "client": [scarecrow, protection]}
    parent = output_root.parent; parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=parent)); published = False
    try:
        (staging / "manifests").mkdir()
        server = _build_side(baseline["server"], additions["server"], staging, output_root, "server")
        client = _build_side(baseline["client"], additions["client"], staging, output_root, "client")
        server_map = {str(r["file"]).casefold(): r for r in server["rows"]}; client_map = {str(r["file"]).casefold(): r for r in client["rows"]}
        if set(server_map) - set(client_map) != {"grieflogger-1.2.10-1.21.1-neoforge.jar"}:
            raise ValueError("server-only side policy changed")
        if set(client_map) - set(server_map) != {"chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar"}:
            raise ValueError("client-only side policy changed")
        for key in set(server_map) & set(client_map):
            if server_map[key]["sha256"] != client_map[key]["sha256"]:
                raise ValueError(f"shared JAR differs across sides: {key}")
        write_atomic(staging / "manifests/server.json", stable_json(server["manifest"]))
        write_atomic(staging / "manifests/client.json", stable_json(client["manifest"]))
        _validate_built_side(server, baseline["server"], staging)
        _validate_built_side(client, baseline["client"], staging)
        runtime = _runtime_identity(server["rows"], runtime_sanitized_root.resolve())
        release = {
            "schema": 1, "candidate": 14, "status": "PASS",
            "purpose": "First release: P0 join/crash guards and fail-closed deferred item carrier",
            "output_root": str(output_root), "source_unchanged": True,
            "baseline": {"candidate": 13, "root": str(baseline_root), "ready_sha256": baseline["ready_hash"], "server_manifest_sha256": sha256(baseline["server"]["manifest_path"]), "client_manifest_sha256": sha256(baseline["client"]["manifest_path"]), "server_bundle_sha256": baseline["server"]["bundle_sha256"], "client_bundle_sha256": baseline["client"]["bundle_sha256"], "bundle_pair_sha256": baseline["pair"]},
            "additions": {"server_and_client": [{"file": a["file"], "mod_id": a["mod_ids"][0], "sha256": a["sha256"], "bytes": a["bytes"], "side": a["side"]} for a in (scarecrow, protection)], "client_only": []},
            "candidate13_invariance": {"baseline_rows_per_side": 52, "unchanged_rows_per_side": 52, "replaced_rows_per_side": 0, "added_server_rows": 2, "added_client_rows": 2, "removed_rows_per_side": 0, "all_baseline_rows_byte_identical": True},
            "side_specific_policy": {"server_only_files": ["grieflogger-1.2.10-1.21.1-neoforge.jar"], "client_only_files": ["chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar"], "mcmodsync_server_install": "forbidden", "mcmodsync_client_install": "deferred_until_locked_config_and_https_manifest"},
            "extension_policy": {
                "release_lock_semantics": "acceptance_snapshot_not_permanent_allowlist",
                "current_file_counts_are_not_production_caps": True,
                "additive_server_mods_allowed": True,
                "additive_client_mods_allowed": True,
                "ota_additions_allowed": True,
                "requirements_for_extension": [
                    "new signed manifest or release lock",
                    "Minecraft/NeoForge and side compatibility check",
                    "dependency and duplicate mod ID audit",
                    "archive CRC and artifact digest verification",
                    "proportionate startup/join/data-safety regression gate",
                ],
                "runtime_global_mod_denylist": False,
                "permanent_exact_mod_count_enforcement": False,
                "existing_release_snapshot_remains_immutable": True,
            },
            "ota_preparation": {"runtime_install_status": "NOT_INSTALLED", "reason": "bare MCModSync defaults require a manifest and must not block the only runnable client", "audited_artifact": {"file": mcsync["file"], "mod_id": mcsync["mod_ids"][0], "sha256": mcsync["sha256"], "bytes": mcsync["bytes"], "declared_sides": mcsync["metadata"]["declared_sides"]}, "required_before_install": ["locked Config.jar", "reachable HTTPS v4 manifest", "offline/failure fallback verified"], "not_present_in_server_bundle": True, "not_present_in_client_bundle": True},
            "runtime_sanitization_policy": {"published_bundle_state": "unsanitized", "scope": "disposable_server_runtime_copy_only", "allowed_jar_transforms": ["CreateDragonsPlus-1.11.4.jar", "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar"], "waypoint_jar_must_remain_byte_identical": True, "new_guard_jars_must_remain_byte_identical": True, "client_runtime_jar_transforms_allowed": False},
            "server": {"mods_dir": str(output_root / "server-mods"), "file_count": len(server["rows"]), "bytes": server["manifest"]["bytes"], "bundle_sha256": server["bundle_sha256"], "manifest": str(output_root / "manifests/server.json"), "manifest_sha256": sha256(staging / "manifests/server.json")},
            "client": {"mods_dir": str(output_root / "client-mods"), "file_count": len(client["rows"]), "bytes": client["manifest"]["bytes"], "bundle_sha256": client["bundle_sha256"], "manifest": str(output_root / "manifests/client.json"), "manifest_sha256": sha256(staging / "manifests/client.json")},
            "bundle_pair_sha256": pair_digest(server["bundle_sha256"], client["bundle_sha256"]), "runtime_server_identity": runtime,
            "verification": {"zip_crc_archives_tested": len(server["rows"]) + len(client["rows"]), "duplicate_filenames": [], "duplicate_mod_ids": [], "all_baseline_rows_byte_identical": True},
        }
        payload = stable_json(release); write_atomic(staging / "release-lock.json", payload); write_atomic(staging / "READY.json", payload)
        if before_snapshot != _snapshot(baseline_root):
            raise RuntimeError("Candidate13 changed while Candidate14 was building")
        os.replace(staging, output_root); published = True
        if (output_root / "READY.json").read_bytes() != (output_root / "release-lock.json").read_bytes():
            raise RuntimeError("published READY/release-lock bytes differ")
        if read_json(output_root / "READY.json") != release:
            raise RuntimeError("published Candidate14 release-lock content mismatch")
        _validate_built_side(server, baseline["server"], output_root)
        _validate_built_side(client, baseline["client"], output_root)
        result = {"status": "PASS", "output_root": str(output_root), "ready_sha256": sha256(output_root / "READY.json"), "release_lock_sha256": sha256(output_root / "release-lock.json"), "server_manifest_sha256": sha256(output_root / "manifests/server.json"), "client_manifest_sha256": sha256(output_root / "manifests/client.json"), "server_bundle_sha256": server["bundle_sha256"], "client_bundle_sha256": client["bundle_sha256"], "bundle_pair_sha256": release["bundle_pair_sha256"], "runtime_server_identity": runtime, "candidate13_snapshot_sha256": _snapshot_digest(before_snapshot)}
        try:
            write_atomic(report_path, stable_json(result))
            markdown = "# Candidate14 Bundle Build\n\nStatus: PASS\n\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            write_atomic(markdown_path, markdown.encode("utf-8"))
        except Exception:
            report_path.unlink(missing_ok=True)
            markdown_path.unlink(missing_ok=True)
            raise
        return result
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-root", type=Path, default=CANDIDATE13_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--scarecrow", type=Path, default=SCARECROW_SOURCE)
    parser.add_argument("--scarecrow-sha256", default=SCARECROW_SHA256)
    parser.add_argument("--protection", type=Path, default=PROTECTION_SOURCE)
    parser.add_argument("--protection-sha256", default=PROTECTION_SHA256)
    parser.add_argument("--mcsync", type=Path, default=MCSYNC_SOURCE)
    parser.add_argument("--mcsync-sha256", default=MCSYNC_SHA256)
    parser.add_argument("--runtime-sanitized-root", type=Path, default=RUNTIME_SANITIZED_ROOT)
    args = parser.parse_args()
    result = build_candidate14(
        args.output_root,
        baseline_root=args.baseline_root,
        report_path=args.report,
        markdown_path=args.markdown,
        scarecrow_source=args.scarecrow,
        scarecrow_sha256=args.scarecrow_sha256,
        protection_source=args.protection,
        protection_sha256=args.protection_sha256,
        mcsync_source=args.mcsync,
        mcsync_sha256=args.mcsync_sha256,
        runtime_sanitized_root=args.runtime_sanitized_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
