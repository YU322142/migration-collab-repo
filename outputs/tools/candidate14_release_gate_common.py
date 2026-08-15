#!/usr/bin/env python3
"""Dynamic Candidate14 release binding for the first-release runtime gate.

The lock is intentionally release-scoped: it verifies one immutable READY and
its manifests, but it does not turn today's JAR count into a permanent cap.
Future additive mod releases get a new READY/build-report pair and can pass the
same validator without source changes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile
from typing import Any


SANITIZER_JARS = (
    "CreateDragonsPlus-1.11.4.jar",
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar",
)
REQUIRED_MOD_IDS = (
    "cctweaked_startup_guard",
    "create_chute_unload_guard",
    "deferred_content_protection",
    "kaleidoscope_cookery_scarecrow_compat",
)
FORBIDDEN_RUNNABLE_MOD_IDS = ("mcmodsync",)


class ReleaseError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ReleaseError(f"{label} is missing, linked, or not a file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"{label} must be a JSON object: {path}")
    return value


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


def _normalized_manifest(
    path: Path, side: str, release_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    value = read_json(path, f"Candidate14 {side} manifest")
    rows = value.get("files")
    if (
        value.get("schema") != 1
        or value.get("candidate") != 14
        or value.get("status") != "PASS"
        or value.get("side") != side
        or not isinstance(rows, list)
        or not rows
    ):
        raise ReleaseError(f"Candidate14 {side} manifest header is invalid")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ReleaseError(f"Candidate14 {side} manifest has a non-object row")
        name = row.get("file")
        digest = str(row.get("sha256", "")).upper()
        size = row.get("bytes")
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
            or not all(isinstance(item, str) and item for item in ids)
        ):
            raise ReleaseError(f"Candidate14 {side} manifest row is invalid: {row!r}")
        seen.add(name.casefold())
        normalized.append({"file": name, "bytes": size, "sha256": digest, "mod_ids": ids})
    if normalized != sorted(normalized, key=lambda row: row["file"].casefold()):
        raise ReleaseError(f"Candidate14 {side} manifest rows are not sorted")
    aggregate = {
        "files": len(normalized),
        "bytes": sum(row["bytes"] for row in normalized),
        "bundle_sha256": bundle_digest(normalized),
    }
    if (
        value.get("file_count") != aggregate["files"]
        or value.get("bytes") != aggregate["bytes"]
        or str(value.get("bundle_sha256", "")).upper() != aggregate["bundle_sha256"]
        or Path(str(value.get("bundle_dir", ""))).resolve()
        != (release_root / f"{side}-mods").resolve()
    ):
        raise ReleaseError(f"Candidate14 {side} manifest aggregate/path mismatch")
    return value, normalized, aggregate


def _verify_published_files(
    directory: Path, rows: list[dict[str, Any]], label: str
) -> None:
    if not directory.is_dir() or directory.is_symlink():
        raise ReleaseError(f"{label} directory is missing or linked: {directory}")
    entries = list(directory.iterdir())
    if any(not item.is_file() or item.is_symlink() for item in entries):
        raise ReleaseError(f"{label} must contain only regular JAR files")
    actual = {item.name.casefold(): item for item in entries}
    expected = {row["file"].casefold(): row for row in rows}
    if len(actual) != len(entries) or set(actual) != set(expected):
        raise ReleaseError(f"{label} exact release snapshot differs from manifest")
    for key, row in expected.items():
        path = actual[key]
        if (
            path.suffix.lower() != ".jar"
            or path.stat().st_size != row["bytes"]
            or sha256(path) != row["sha256"]
            or not zipfile.is_zipfile(path)
        ):
            raise ReleaseError(f"{label} artifact mismatch: {path.name}")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ReleaseError(f"{label} JAR has duplicate entries: {path.name}")
            if archive.testzip() is not None:
                raise ReleaseError(f"{label} JAR CRC failure: {path.name}")


def _id_index(rows: list[dict[str, Any]], side: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        for mod_id in row["mod_ids"]:
            if mod_id in result and result[mod_id] != row["file"]:
                raise ReleaseError(
                    f"Candidate14 {side} duplicate mod ID {mod_id}: "
                    f"{result[mod_id]} / {row['file']}"
                )
            result[mod_id] = row["file"]
    return result


def validate_release(
    release_root: Path,
    ready_sha256: str,
    build_report: Path,
    build_report_sha256: str,
) -> dict[str, Any]:
    release_root = release_root.resolve()
    if not release_root.is_dir() or release_root.is_symlink():
        raise ReleaseError(f"Candidate14 release root is missing or linked: {release_root}")
    ready_path = release_root / "READY.json"
    lock_path = release_root / "release-lock.json"
    server_path = release_root / "manifests" / "server.json"
    client_path = release_root / "manifests" / "client.json"
    expected_ready = ready_sha256.upper()
    expected_build = build_report_sha256.upper()
    if sha256(ready_path) != expected_ready or sha256(lock_path) != expected_ready:
        raise ReleaseError("Candidate14 READY/release-lock hash mismatch")
    if ready_path.read_bytes() != lock_path.read_bytes():
        raise ReleaseError("Candidate14 READY/release-lock are not byte-identical")
    if sha256(build_report) != expected_build:
        raise ReleaseError("Candidate14 build-report hash mismatch")
    ready = read_json(ready_path, "Candidate14 READY")
    build = read_json(build_report, "Candidate14 build report")
    if (
        ready.get("schema") != 1
        or ready.get("candidate") != 14
        or ready.get("status") != "PASS"
        or ready.get("source_unchanged") is not True
        or Path(str(ready.get("output_root", ""))).resolve() != release_root
    ):
        raise ReleaseError("Candidate14 READY identity mismatch")
    policy = ready.get("extension_policy")
    if (
        not isinstance(policy, dict)
        or policy.get("release_lock_semantics")
        != "acceptance_snapshot_not_permanent_allowlist"
        or policy.get("current_file_counts_are_not_production_caps") is not True
        or policy.get("additive_server_mods_allowed") is not True
        or policy.get("additive_client_mods_allowed") is not True
        or policy.get("permanent_exact_mod_count_enforcement") is not False
        or policy.get("existing_release_snapshot_remains_immutable") is not True
    ):
        raise ReleaseError("Candidate14 extension policy would lock future mod additions")
    server_manifest, server_rows, server = _normalized_manifest(
        server_path, "server", release_root
    )
    client_manifest, client_rows, client = _normalized_manifest(
        client_path, "client", release_root
    )
    _verify_published_files(release_root / "server-mods", server_rows, "server release")
    _verify_published_files(release_root / "client-mods", client_rows, "client release")
    server_ids = _id_index(server_rows, "server")
    client_ids = _id_index(client_rows, "client")
    for mod_id in REQUIRED_MOD_IDS:
        if mod_id not in server_ids or mod_id not in client_ids:
            raise ReleaseError(f"Candidate14 required safety mod is absent: {mod_id}")
        srow = next(row for row in server_rows if mod_id in row["mod_ids"])
        crow = next(row for row in client_rows if mod_id in row["mod_ids"])
        if srow["sha256"] != crow["sha256"]:
            raise ReleaseError(f"Candidate14 safety mod differs across sides: {mod_id}")
    for mod_id in FORBIDDEN_RUNNABLE_MOD_IDS:
        if mod_id in server_ids or mod_id in client_ids:
            raise ReleaseError(f"unconfigured OTA bootstrap is installed: {mod_id}")
    pair = pair_digest(server["bundle_sha256"], client["bundle_sha256"])
    if str(ready.get("bundle_pair_sha256", "")).upper() != pair:
        raise ReleaseError("Candidate14 release pair digest mismatch")
    for side, manifest, aggregate, manifest_path in (
        ("server", server_manifest, server, server_path),
        ("client", client_manifest, client, client_path),
    ):
        bound = ready.get(side)
        if (
            not isinstance(bound, dict)
            or bound.get("file_count") != aggregate["files"]
            or bound.get("bytes") != aggregate["bytes"]
            or str(bound.get("bundle_sha256", "")).upper()
            != aggregate["bundle_sha256"]
            or str(bound.get("manifest_sha256", "")).upper() != sha256(manifest_path)
            or manifest.get("file_count") != aggregate["files"]
        ):
            raise ReleaseError(f"Candidate14 READY {side} binding mismatch")
    runtime = ready.get("runtime_server_identity")
    sanitization = ready.get("runtime_sanitization_policy")
    if (
        not isinstance(runtime, dict)
        or runtime.get("files") != server["files"]
        or sorted(runtime.get("sanitized_jars", [])) != sorted(SANITIZER_JARS)
        or not isinstance(sanitization, dict)
        or sorted(sanitization.get("allowed_jar_transforms", []))
        != sorted(SANITIZER_JARS)
        or sanitization.get("client_runtime_jar_transforms_allowed") is not False
    ):
        raise ReleaseError("Candidate14 runtime sanitizer boundary mismatch")
    if (
        build.get("status") != "PASS"
        or Path(str(build.get("output_root", ""))).resolve() != release_root
        or str(build.get("ready_sha256", "")).upper() != expected_ready
        or str(build.get("server_manifest_sha256", "")).upper() != sha256(server_path)
        or str(build.get("client_manifest_sha256", "")).upper() != sha256(client_path)
        or str(build.get("server_bundle_sha256", "")).upper()
        != server["bundle_sha256"]
        or str(build.get("client_bundle_sha256", "")).upper()
        != client["bundle_sha256"]
        or str(build.get("bundle_pair_sha256", "")).upper() != pair
    ):
        raise ReleaseError("Candidate14 build report is not bound to this release")
    return {
        "root": str(release_root),
        "ready": {"path": str(ready_path), "sha256": expected_ready},
        "release_lock": {"path": str(lock_path), "sha256": expected_ready},
        "build_report": {"path": str(build_report.resolve()), "sha256": expected_build},
        "server_manifest": {
            "path": str(server_path),
            "sha256": sha256(server_path),
            **server,
            "rows": server_rows,
        },
        "client_manifest": {
            "path": str(client_path),
            "sha256": sha256(client_path),
            **client,
            "rows": client_rows,
        },
        "runtime_server_identity": {
            "files": runtime["files"],
            "bytes": runtime["bytes"],
            "bundle_sha256": str(runtime["bundle_sha256"]).upper(),
            "sanitized_jars": sorted(runtime["sanitized_jars"]),
        },
        "bundle_pair_sha256": pair,
        "required_mod_files": {
            mod_id: {"server": server_ids[mod_id], "client": client_ids[mod_id]}
            for mod_id in REQUIRED_MOD_IDS
        },
        "extension_policy": policy,
        "release_scoped_exactness": True,
        "permanent_mod_count_cap": False,
    }


def validate_runtime_bundles(
    binding: dict[str, Any],
    server_bundle: dict[str, Any],
    client_bundle: dict[str, Any],
) -> dict[str, Any]:
    expected_server = binding["runtime_server_identity"]
    expected_client = {
        key: binding["client_manifest"][key]
        for key in ("files", "bytes", "bundle_sha256")
    }
    observed_server = {
        key: server_bundle.get(key)
        for key in ("files", "bytes", "bundle_sha256")
    }
    observed_client = {key: client_bundle.get(key) for key in expected_client}
    expected_server_core = {
        key: expected_server[key] for key in ("files", "bytes", "bundle_sha256")
    }
    if observed_server != expected_server_core:
        raise ReleaseError(
            f"sanitized server runtime differs from locked release: {observed_server}"
        )
    if observed_client != expected_client:
        raise ReleaseError(f"client runtime differs from locked release: {observed_client}")
    return {
        "server": server_bundle,
        "client": client_bundle,
        "release_scoped_exact_bundles": True,
        "current_file_counts_are_not_production_caps": True,
    }
