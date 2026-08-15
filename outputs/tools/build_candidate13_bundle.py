#!/usr/bin/env python3
"""Build a fresh, fail-closed Candidate13 mod bundle.

Candidate13 is deliberately a small delta from the locked Candidate12 bundle:
the two 52-JAR sides retain every Candidate12 artifact byte-for-byte except
for the resource-error overlay.  The output is assembled in a private staging
directory and published with one atomic rename; Candidate12 and all source
artifacts are read-only inputs.
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
import zipfile
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[2]
CANDIDATE12_ROOT = Path(
    r"D:\Trans\migration-audit-work\final-mod-bundles-candidate12-20260812"
)
DEFAULT_OVERLAY = (
    WORKSPACE
    / "outputs/candidate13-resource-closure-20260812/"
    "migration-resource-overlay-1.2.0+mc1.21.1-candidate13.jar"
)
DEFAULT_RESOURCE_REPORT = (
    WORKSPACE / "outputs/candidate13-resource-closure-20260812/build-report.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    r"D:\Trans\migration-audit-work\final-mod-bundles-candidate13-20260812"
)
DEFAULT_REPORT = WORKSPACE / "outputs/candidate13-bundle-build-20260812.json"

JAR_COUNT = 52
OVERLAY_MOD_ID = "migration_resource_overlay"
OLD_OVERLAY_FILE = "migration-resource-overlay-1.1.0+mc1.21.1.jar"
OLD_OVERLAY_SHA256 = (
    "C7B2F2F7E7D81EED4523F1C092E434E6B94E60F7BFB40A1E4B1A142B0057ADD8"
)
NEW_OVERLAY_FILE = "migration-resource-overlay-1.2.0+mc1.21.1-candidate13.jar"
NEW_OVERLAY_SHA256 = (
    "BCCB7D7CF8019D8895A081D563E578712D7CDF93DA0AD9EAFB31067439C62862"
)

# These locks are intentionally pinned.  If Candidate12 is rebuilt, this
# script must not silently consume it; update the lock after an explicit audit.
CANDIDATE12_LOCK = {
    "ready_sha256": "DA1D10702486593A9E8CD00B81B726EA33B69529B6DFDBB148AAF03EE56CCB60",
    "server_manifest_sha256": "2A4E1AF27125A19F2BDC8040CDBE9E3CB998EE0E145AE51C66A0E1D72671A466",
    "client_manifest_sha256": "4A37B8DDEEE4A31AC901BD0C6C13FD9C19128904E56079282EE6A3935DCDA3E6",
    "server_bundle_sha256": "8D02000218EC3FCB79BE4B628FB5C682CFCD1C025D82E24282F32B4ECC7B0B57",
    "client_bundle_sha256": "4F960FCA4FF3820EA40F1AED326E1A8435922DDAA49FBB3078532380B8543A24",
    "bundle_pair_sha256": "2B6B501D042E708AA5FA21457B34866AB65DC7CA79E671B35D512DC45B88F839",
}


@dataclass(frozen=True)
class BaselineLock:
    """Optional Candidate12 hashes used by validation and synthetic tests."""

    ready_sha256: str | None = None
    server_manifest_sha256: str | None = None
    client_manifest_sha256: str | None = None
    server_bundle_sha256: str | None = None
    client_bundle_sha256: str | None = None
    bundle_pair_sha256: str | None = None


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
    temporary = path.with_name(f".{path.name}.candidate13.tmp")
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


def jar_mod_ids(path: Path) -> set[str]:
    _real_file(path, "JAR")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a ZIP/JAR: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ValueError(f"JAR CRC failure in {bad}: {path}")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError(f"JAR has duplicate entries: {path}")
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
                    if isinstance(mod, dict) and isinstance(mod.get("modId"), str):
                        if "${" not in mod["modId"]:
                            result.add(mod["modId"])
            return result
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid metadata in JAR {path}: {exc}") from exc


def _check_lock(actual: str, expected: str | None, label: str) -> None:
    if expected is not None and actual.upper() != expected.upper():
        raise ValueError(f"Candidate12 {label} lock mismatch: {actual} != {expected}")


def _validate_side(root: Path, side: str, lock: BaselineLock) -> dict[str, Any]:
    manifest_path = root / "manifests" / f"{side}.json"
    mods_dir = root / f"{side}-mods"
    _real_file(manifest_path, f"Candidate12 {side} manifest")
    _real_dir(mods_dir, f"Candidate12 {side} mods")
    manifest_hash = sha256(manifest_path)
    expected_manifest = getattr(lock, f"{side}_manifest_sha256")
    _check_lock(manifest_hash, expected_manifest, f"{side} manifest")
    manifest = read_json(manifest_path)
    if manifest.get("schema") != 1 or manifest.get("candidate") != 12 or manifest.get("status") != "PASS":
        raise ValueError(f"Candidate12 {side} manifest header mismatch")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != JAR_COUNT or manifest.get("file_count") != JAR_COUNT:
        raise ValueError(f"Candidate12 {side} must contain exactly {JAR_COUNT} rows")
    actual_files = {p.name.casefold(): p for p in mods_dir.iterdir()}
    if len(actual_files) != JAR_COUNT or any(p.is_symlink() or not p.is_file() or p.suffix.lower() != ".jar" for p in actual_files.values()):
        raise ValueError(f"Candidate12 {side} mods directory is not a flat {JAR_COUNT}-JAR set")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise ValueError(f"Candidate12 {side} invalid row")
        filename = row["file"]
        key = filename.casefold()
        if key in seen:
            raise ValueError(f"Candidate12 {side} duplicate row: {filename}")
        seen.add(key)
        path = actual_files.get(key)
        if path is None:
            raise ValueError(f"Candidate12 {side} missing JAR: {filename}")
        expected_sha = str(row.get("sha256", "")).upper()
        expected_bytes = row.get("bytes")
        actual_sha = sha256(path)
        if not isinstance(expected_bytes, int) or path.stat().st_size != expected_bytes or actual_sha != expected_sha:
            raise ValueError(f"Candidate12 {side} JAR hash/size mismatch: {filename}")
        ids = jar_mod_ids(path)
        declared = row.get("mod_ids")
        if not isinstance(declared, list) or set(declared) != ids:
            raise ValueError(f"Candidate12 {side} mod ID mismatch: {filename}")
        copied = dict(row)
        copied["_path"] = path
        normalized.append(copied)
    if {p.casefold() for p in actual_files} != seen:
        raise ValueError(f"Candidate12 {side} contains unmanifested JARs")
    if normalized != sorted(normalized, key=lambda r: str(r["file"]).casefold()):
        raise ValueError(f"Candidate12 {side} manifest is not deterministically sorted")
    computed = bundle_digest(normalized)
    if str(manifest.get("bundle_sha256", "")).upper() != computed:
        raise ValueError(f"Candidate12 {side} bundle digest mismatch")
    _check_lock(computed, getattr(lock, f"{side}_bundle_sha256"), f"{side} bundle")
    return {
        "side": side,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_hash,
        "mods_dir": mods_dir,
        "rows": normalized,
        "bundle_sha256": computed,
    }


def _validate_candidate12(root: Path, lock: BaselineLock) -> dict[str, Any]:
    root = root.resolve()
    _real_dir(root, "Candidate12 root")
    expected_entries = {"server-mods", "client-mods", "manifests", "READY.json", "release-lock.json"}
    if {p.name for p in root.iterdir()} != expected_entries:
        raise ValueError("Candidate12 root entry set mismatch")
    manifests_dir = root / "manifests"
    _real_dir(manifests_dir, "Candidate12 manifests")
    if {p.name for p in manifests_dir.iterdir()} != {"server.json", "client.json"}:
        raise ValueError("Candidate12 manifest entry set mismatch")
    ready = root / "READY.json"
    release = root / "release-lock.json"
    _real_file(ready, "Candidate12 READY")
    _real_file(release, "Candidate12 release lock")
    if ready.read_bytes() != release.read_bytes():
        raise ValueError("Candidate12 READY/release-lock bytes differ")
    ready_hash = sha256(ready)
    _check_lock(ready_hash, lock.ready_sha256, "READY")
    release_json = read_json(ready)
    if (
        release_json.get("schema") != 1
        or release_json.get("candidate") != 12
        or release_json.get("status") != "PASS"
        or release_json.get("source_unchanged") is not True
        or Path(str(release_json.get("output_root", ""))).resolve() != root
    ):
        raise ValueError("Candidate12 release lock is not PASS")
    server = _validate_side(root, "server", lock)
    client = _validate_side(root, "client", lock)
    server_map = {str(r["file"]).casefold(): r for r in server["rows"]}
    client_map = {str(r["file"]).casefold(): r for r in client["rows"]}
    if set(server_map) - set(client_map) != {str(release_json.get("side_specific_policy", {}).get("server_only_file", "")).casefold()}:
        raise ValueError("Candidate12 server-only policy mismatch")
    if set(client_map) - set(server_map) != {str(release_json.get("side_specific_policy", {}).get("client_only_file", "")).casefold()}:
        raise ValueError("Candidate12 client-only policy mismatch")
    shared = set(server_map) & set(client_map)
    if len(shared) != JAR_COUNT - 1:
        raise ValueError("Candidate12 sides do not share 51 filenames")
    for key in shared:
        if str(server_map[key]["sha256"]).upper() != str(client_map[key]["sha256"]).upper():
            raise ValueError(f"Candidate12 shared JAR differs across sides: {key}")
    expected_pair = pair_digest(server["bundle_sha256"], client["bundle_sha256"])
    if str(release_json.get("bundle_pair_sha256", "")).upper() != expected_pair:
        raise ValueError("Candidate12 pair digest mismatch")
    _check_lock(expected_pair, lock.bundle_pair_sha256, "bundle pair")
    for side, validated in (("server", server), ("client", client)):
        detail = release_json.get(side)
        if not isinstance(detail, dict) or (
            detail.get("file_count") != JAR_COUNT
            or str(detail.get("bundle_sha256", "")).upper()
            != validated["bundle_sha256"]
            or str(detail.get("manifest_sha256", "")).upper()
            != validated["manifest_sha256"]
        ):
            raise ValueError(f"Candidate12 release-lock {side} binding mismatch")
    return {
        "root": root,
        "ready": ready,
        "ready_hash": ready_hash,
        "release": release_json,
        "server": server,
        "client": client,
        "pair": expected_pair,
    }


def _snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: str(p.relative_to(root)).casefold()):
        result[str(path.relative_to(root)).replace("\\", "/")] = sha256(path)
    return result


def _snapshot_digest(snapshot: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, value in snapshot.items():
        digest.update(name.encode("utf-8")); digest.update(b"\0"); digest.update(value.encode("ascii")); digest.update(b"\n")
    return digest.hexdigest().upper()


def _load_overlay(path: Path, expected_sha256: str) -> dict[str, Any]:
    _real_file(path, "Candidate13 overlay")
    actual = sha256(path)
    if actual != expected_sha256.upper():
        raise ValueError(f"Candidate13 overlay hash mismatch: {actual} != {expected_sha256}")
    ids = jar_mod_ids(path)
    if ids != {OVERLAY_MOD_ID}:
        raise ValueError(f"Candidate13 overlay mod IDs mismatch: {sorted(ids)}")
    return {"path": path.resolve(), "file": path.name, "bytes": path.stat().st_size, "sha256": actual, "mod_ids": sorted(ids)}


def _validate_resource_report(path: Path | None, overlay_sha: str) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.is_file():
        raise FileNotFoundError(path)
    report = read_json(path)
    if report.get("status") != "PASS" or report.get("category") != "candidate13_resource_closure_build":
        raise ValueError("resource closure report is not PASS")
    output = report.get("outputs", {}).get("overlay", {})
    if str(output.get("sha256", "")).upper() != overlay_sha.upper():
        raise ValueError("resource closure report overlay hash mismatch")
    return {"path": str(path.resolve()), "sha256": sha256(path), "local_resource_pack": report.get("outputs", {}).get("local_resource_pack"), "transformations": report.get("transformations", [])}


def _replacement_row(old: dict[str, Any], overlay: dict[str, Any], resource_report: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "file": overlay["file"],
        "bytes": overlay["bytes"],
        "sha256": overlay["sha256"],
        "mod_ids": list(overlay["mod_ids"]),
        "role": "replacement",
        "component": "Resource Error Overlay",
        "source": str(overlay["path"]),
        "expected_sha256": overlay["sha256"],
        "expected_bytes": overlay["bytes"],
        "replaces_file": old["file"],
        "replaces_sha256": old["sha256"],
        "candidate13_comparison": "replaced_resource_error_overlay_closure",
        **({"resource_closure_report": resource_report["path"]} if resource_report else {}),
    }


def _build_side(
    baseline: dict[str, Any],
    overlay: dict[str, Any],
    staging_root: Path,
    output_root: Path,
    resource_report: dict[str, Any] | None,
    *,
    old_overlay_file: str,
    old_overlay_sha256: str,
) -> dict[str, Any]:
    side = baseline["side"]
    destination = staging_root / f"{side}-mods"
    destination.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    old_rows = [r for r in baseline["rows"] if OVERLAY_MOD_ID in set(r.get("mod_ids", []))]
    if len(old_rows) != 1:
        raise ValueError(f"Candidate12 {side} must contain exactly one resource overlay row")
    old = old_rows[0]
    if (
        old["file"] != old_overlay_file
        or str(old["sha256"]).upper() != old_overlay_sha256.upper()
    ):
        raise ValueError(f"Candidate12 {side} old overlay lock mismatch")
    for row in baseline["rows"]:
        if row is old:
            continue
        out = destination / str(row["file"])
        shutil.copy2(row["_path"], out)
        if out.stat().st_size != row["bytes"] or sha256(out) != str(row["sha256"]).upper():
            raise IOError(f"Candidate13 unchanged copy verification failed: {out}")
        copied = {k: v for k, v in row.items() if k != "_path"}
        rows.append(copied)
    new_path = destination / overlay["file"]
    shutil.copy2(overlay["path"], new_path)
    if new_path.stat().st_size != overlay["bytes"] or sha256(new_path) != overlay["sha256"]:
        raise IOError(f"Candidate13 overlay copy verification failed: {new_path}")
    rows.append(_replacement_row(old, overlay, resource_report))
    rows.sort(key=lambda r: str(r["file"]).casefold())
    if len(rows) != JAR_COUNT or len({str(r["file"]).casefold() for r in rows}) != JAR_COUNT:
        raise ValueError(f"Candidate13 {side} must contain exactly {JAR_COUNT} unique rows")
    manifest = {
        "schema": 1,
        "candidate": 13,
        "status": "PASS",
        "side": side,
        "baseline_candidate": 12,
        "baseline_manifest": str(baseline["manifest_path"].resolve()),
        "baseline_manifest_sha256": baseline["manifest_sha256"],
        "baseline_bundle_sha256": baseline["bundle_sha256"],
        "bundle_dir": str((output_root / f"{side}-mods").resolve()),
        "file_count": JAR_COUNT,
        "bytes": sum(int(r["bytes"]) for r in rows),
        "bundle_sha256": bundle_digest(rows),
        "manifest_path": str((output_root / "manifests" / f"{side}.json").resolve()),
        "candidate12_invariance": {
            "baseline_rows": JAR_COUNT,
            "unchanged_rows": JAR_COUNT - 1,
            "replaced_rows": 1,
            "added_rows": 0,
            "removed_rows": 0,
            "allowed_replaced_mod_ids": [OVERLAY_MOD_ID],
        },
        "resource_overlay_replacement": {
            "mod_id": OVERLAY_MOD_ID,
            "before_file": old["file"],
            "before_bytes": old["bytes"],
            "before_sha256": old["sha256"],
            "after_file": overlay["file"],
            "after_bytes": overlay["bytes"],
            "after_sha256": overlay["sha256"],
        },
        "files": rows,
    }
    return {"side": side, "manifest": manifest, "rows": rows, "bundle_sha256": manifest["bundle_sha256"], "mods_dir": destination}


def _validate_built_side(
    result: dict[str, Any],
    baseline: dict[str, Any],
    tree_root: Path,
    *,
    new_overlay_file: str,
    new_overlay_sha256: str,
) -> None:
    side = result["side"]
    rows = result["rows"]
    if len(rows) != JAR_COUNT:
        raise ValueError(f"published Candidate13 {side} row count mismatch")
    current = {str(r["file"]).casefold(): r for r in rows}
    old = {str(r["file"]).casefold(): r for r in baseline["rows"]}
    old_overlay = next(r for r in baseline["rows"] if OVERLAY_MOD_ID in set(r.get("mod_ids", [])))
    new_key = new_overlay_file.casefold()
    if new_key not in current or old_overlay["file"].casefold() in current:
        raise ValueError(f"published Candidate13 {side} overlay JAR set mismatch")
    if str(current[new_key].get("sha256", "")).upper() != new_overlay_sha256.upper():
        raise ValueError(f"published Candidate13 {side} overlay hash mismatch")
    for key, row in old.items():
        if key == old_overlay["file"].casefold():
            continue
        expected_row = {k: v for k, v in row.items() if k != "_path"}
        if key not in current or current[key] != expected_row:
            raise ValueError(f"published Candidate13 changed an unapproved row: {side}/{row['file']}")
    if bundle_digest(rows) != result["bundle_sha256"]:
        raise ValueError(f"published Candidate13 {side} bundle digest mismatch")
    mods_dir = tree_root / f"{side}-mods"
    actual_files = {p.name.casefold(): p for p in mods_dir.iterdir()}
    if set(actual_files) != set(current) or len(actual_files) != JAR_COUNT:
        raise ValueError(f"published Candidate13 {side} JAR set mismatch")
    for key, row in current.items():
        path = actual_files[key]
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row["bytes"]
            or sha256(path) != str(row["sha256"]).upper()
            or jar_mod_ids(path) != set(row["mod_ids"])
        ):
            raise ValueError(f"published Candidate13 {side} JAR validation failed: {path.name}")
    manifest_path = tree_root / "manifests" / f"{side}.json"
    if read_json(manifest_path) != result["manifest"]:
        raise ValueError(f"published Candidate13 {side} manifest mismatch")


def build_candidate13(
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    *,
    baseline_root: Path = CANDIDATE12_ROOT,
    overlay_path: Path = DEFAULT_OVERLAY,
    overlay_sha256: str = NEW_OVERLAY_SHA256,
    resource_report_path: Path = DEFAULT_RESOURCE_REPORT,
    lock: BaselineLock | None = None,
    old_overlay_file: str = OLD_OVERLAY_FILE,
    old_overlay_sha256: str = OLD_OVERLAY_SHA256,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    baseline_root = baseline_root.resolve()
    overlay_path = overlay_path.resolve()
    if output_root.exists():
        raise FileExistsError(f"refusing to reuse existing output root: {output_root}")
    lock = lock or BaselineLock(**CANDIDATE12_LOCK)
    print("[candidate13] validating locked Candidate12", flush=True)
    baseline = _validate_candidate12(baseline_root, lock)
    before_snapshot = _snapshot(baseline_root)
    overlay = _load_overlay(overlay_path, overlay_sha256)
    if overlay["file"] != NEW_OVERLAY_FILE:
        raise ValueError(f"Candidate13 overlay filename mismatch: {overlay['file']}")
    resource_report = _validate_resource_report(
        resource_report_path.resolve() if resource_report_path is not None else None,
        overlay["sha256"],
    )
    parent = output_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.staging-", dir=parent))
    published = False
    try:
        (staging_root / "manifests").mkdir()
        print("[candidate13] copying and verifying server/client bundles", flush=True)
        server = _build_side(
            baseline["server"], overlay, staging_root, output_root, resource_report,
            old_overlay_file=old_overlay_file,
            old_overlay_sha256=old_overlay_sha256,
        )
        client = _build_side(
            baseline["client"], overlay, staging_root, output_root, resource_report,
            old_overlay_file=old_overlay_file,
            old_overlay_sha256=old_overlay_sha256,
        )
        # Both sides must have the same shared JAR set and hash; only the
        # documented server-only/client-only filenames may differ.
        server_map = {str(r["file"]).casefold(): r for r in server["rows"]}
        client_map = {str(r["file"]).casefold(): r for r in client["rows"]}
        baseline_server_map = {str(r["file"]).casefold(): r for r in baseline["server"]["rows"]}
        baseline_client_map = {str(r["file"]).casefold(): r for r in baseline["client"]["rows"]}
        if set(server_map) - set(client_map) != set(baseline_server_map) - set(baseline_client_map):
            raise ValueError("Candidate13 server-only JAR set changed")
        if set(client_map) - set(server_map) != set(baseline_client_map) - set(baseline_server_map):
            raise ValueError("Candidate13 client-only JAR set changed")
        for key in set(server_map) & set(client_map):
            if server_map[key]["sha256"] != client_map[key]["sha256"]:
                raise ValueError(f"Candidate13 shared JAR differs across sides: {key}")
        write_atomic(staging_root / "manifests/server.json", stable_json(server["manifest"]))
        write_atomic(staging_root / "manifests/client.json", stable_json(client["manifest"]))
        _validate_built_side(
            server, baseline["server"], staging_root,
            new_overlay_file=overlay["file"], new_overlay_sha256=overlay["sha256"],
        )
        _validate_built_side(
            client, baseline["client"], staging_root,
            new_overlay_file=overlay["file"], new_overlay_sha256=overlay["sha256"],
        )
        pair = pair_digest(server["bundle_sha256"], client["bundle_sha256"])
        release = {
            "schema": 1,
            "candidate": 13,
            "status": "PASS",
            "purpose": "Candidate12 with audited resource/render closure overlay",
            "output_root": str(output_root),
            "source_unchanged": True,
            "baseline": {
                "candidate": 12,
                "root": str(baseline_root),
                "ready_sha256": baseline["ready_hash"],
                "server_manifest_sha256": baseline["server"]["manifest_sha256"],
                "client_manifest_sha256": baseline["client"]["manifest_sha256"],
                "server_bundle_sha256": baseline["server"]["bundle_sha256"],
                "client_bundle_sha256": baseline["client"]["bundle_sha256"],
                "bundle_pair_sha256": baseline["pair"],
            },
            "replacement": {
                "component": "Resource Error Overlay",
                "mod_id": OVERLAY_MOD_ID,
                "operation": "replace_both_sides",
                "reason": "close audited Yuushya/resource-pack client render gaps while preserving gameplay state",
                "before_file": old_overlay_file,
                "before_sha256": old_overlay_sha256.upper(),
                "after_file": overlay["file"],
                "after_bytes": overlay["bytes"],
                "after_sha256": overlay["sha256"],
                "after_mod_ids": overlay["mod_ids"],
            },
            "candidate12_invariance": {
                "baseline_rows_per_side": JAR_COUNT,
                "unchanged_rows_per_side": JAR_COUNT - 1,
                "replaced_rows_per_side": 1,
                "added_rows_per_side": 0,
                "removed_rows_per_side": 0,
                "all_other_rows_byte_identical": True,
            },
            "server": {
                "mods_dir": str(output_root / "server-mods"),
                "file_count": JAR_COUNT,
                "bytes": server["manifest"]["bytes"],
                "bundle_sha256": server["bundle_sha256"],
                "manifest": str(output_root / "manifests/server.json"),
                "manifest_sha256": sha256(staging_root / "manifests/server.json"),
            },
            "client": {
                "mods_dir": str(output_root / "client-mods"),
                "file_count": JAR_COUNT,
                "bytes": client["manifest"]["bytes"],
                "bundle_sha256": client["bundle_sha256"],
                "manifest": str(output_root / "manifests/client.json"),
                "manifest_sha256": sha256(staging_root / "manifests/client.json"),
            },
            "bundle_pair_sha256": pair,
            "side_specific_policy": baseline["release"].get("side_specific_policy", {}),
            "runtime_sanitization_policy": baseline["release"].get("runtime_sanitization_policy", {}),
            "resource_closure": resource_report,
            "verification": {
                "zip_crc_archives_tested": JAR_COUNT * 2,
                "duplicate_filenames": [],
                "duplicate_mod_ids": [],
                "all_other_rows_byte_identical": True,
            },
        }
        release_bytes = stable_json(release)
        write_atomic(staging_root / "release-lock.json", release_bytes)
        write_atomic(staging_root / "READY.json", release_bytes)
        after_snapshot = _snapshot(baseline_root)
        if before_snapshot != after_snapshot:
            raise RuntimeError("Candidate12 changed while Candidate13 was building")
        print("[candidate13] publishing verified staging tree atomically", flush=True)
        os.replace(staging_root, output_root)
        published = True
        # Validate the published tree and both lock files after the rename.
        if (output_root / "READY.json").read_bytes() != (output_root / "release-lock.json").read_bytes():
            raise RuntimeError("published READY/release-lock bytes differ")
        published_release = read_json(output_root / "READY.json")
        if published_release != release:
            raise RuntimeError("published Candidate13 release-lock content mismatch")
        for built, base in ((server, baseline["server"]), (client, baseline["client"])):
            _validate_built_side(
                built, base, output_root,
                new_overlay_file=overlay["file"], new_overlay_sha256=overlay["sha256"],
            )
        print("[candidate13] PASS", flush=True)
        return {
            "status": "PASS",
            "output_root": str(output_root),
            "ready_sha256": sha256(output_root / "READY.json"),
            "release_lock_sha256": sha256(output_root / "release-lock.json"),
            "server_bundle_sha256": server["bundle_sha256"],
            "client_bundle_sha256": client["bundle_sha256"],
            "bundle_pair_sha256": pair,
            "overlay_sha256": overlay["sha256"],
            "candidate12_snapshot_sha256": _snapshot_digest(before_snapshot),
        }
    finally:
        if not published and staging_root.exists():
            shutil.rmtree(staging_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, default=CANDIDATE12_ROOT)
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument("--overlay-sha256", default=NEW_OVERLAY_SHA256)
    parser.add_argument("--resource-report", type=Path, default=DEFAULT_RESOURCE_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = build_candidate13(
        args.output_root,
        baseline_root=args.baseline_root,
        overlay_path=args.overlay,
        overlay_sha256=args.overlay_sha256,
        resource_report_path=args.resource_report,
    )
    write_atomic(args.report.resolve(), stable_json(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
