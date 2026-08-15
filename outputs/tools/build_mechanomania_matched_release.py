#!/usr/bin/env python3
"""Build a fail-closed, matched Mechanomania server/client static release.

The builder never starts Java or Minecraft and never copies a world.  It
verifies all locked inputs, JAR CRC/metadata/side/dependency closure, the v2
gameplay overlay, UI/map exclusions, and the production configuration identity.
The completed tree is published by one atomic rename.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import tomllib
from typing import Any, Iterable
import uuid
import zipfile


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = WORKSPACE / "outputs/mechanomania-matched-release-input-lock-20260813.json"
DEFAULT_REPORT = WORKSPACE / "outputs/mechanomania-matched-release-build-20260813.json"
DEFAULT_MARKDOWN = WORKSPACE / "outputs/mechanomania-matched-release-build-20260813.md"
DEFAULT_OUTPUT = Path(r"D:\Trans\migration-audit-work\mechanomania-matched-release-v2-20260813")

TARGETS = {"SERVER", "CLIENT", "BOTH"}
SIDE_CLASSIFICATIONS = {"SERVER_ONLY", "CLIENT_ONLY", "BOTH"}
MERGE_MODES = {"replace", "copy_if_absent"}
SAFE_LIBRARY_CONTAINERS = {
    "connector-2.0.0-beta.16+1.21.1-full.jar",
    "kotlinforforge-5.12.0-all.jar",
}
SYSTEM_MODS = {"minecraft", "neoforge", "forge", "java"}
REQUIRED_OVERLAY_GUARANTEES = {
    "no_world_files",
    "no_production_server_properties",
    "no_journeymap",
    "no_pack_icon",
    "no_original_overworld_worldgen",
    "terrain_frontier_applied_last",
    "ui_sanitized_applied",
    "xaero_staging_only",
    "base_config_wins_on_collision",
    "old_world_regions_are_not_part_of_overlay",
    "mod_jars_are_not_part_of_overlay",
}
CRITICAL_UI_TARGETS = {
    "config/create-client.toml",
    "config/createtweakedcontrollers-client.toml",
    "config/modernfix-mixins.properties",
    "kubejs/config/client.json",
}
CRITICAL_TERRAIN_TARGETS = {
    "kubejs/data/minecraft/dimension/overworld.json",
    "kubejs/data/minecraft/dimension_type/overworld.json",
    "kubejs/data/minecraft/worldgen/noise_settings/overworld.json",
}


class ReleaseError(RuntimeError):
    pass


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ReleaseError(f"missing regular JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON root must be an object: {path}")
    return value


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _locked_path(entry: dict[str, Any], label: str, *, directory: bool = False) -> Path:
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise ReleaseError(f"invalid path lock for {label}")
    path = Path(entry["path"])
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise ReleaseError(f"missing locked {'directory' if directory else 'file'} for {label}: {path}")
    if not directory:
        expected = str(entry.get("sha256", "")).upper()
        actual = sha256(path)
        if not re.fullmatch(r"[0-9A-F]{64}", expected) or actual != expected:
            raise ReleaseError(f"hash lock mismatch for {label}: {actual} != {expected}")
        if "bytes" in entry and path.stat().st_size != int(entry["bytes"]):
            raise ReleaseError(f"size lock mismatch for {label}")
    return path.resolve()


def _safe_rel(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReleaseError(f"invalid relative path for {label}: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise ReleaseError(f"unsafe relative path for {label}: {value}")
    return value


def _copy_verified(source: Path, destination: Path, size: int, digest: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if destination.stat().st_size != size or sha256(destination) != digest:
        raise ReleaseError(f"copy verification failed: {destination}")


def _clean_toml(raw: bytes) -> bytes:
    return raw.lstrip(b"\xef\xbb\xbf")


def _version_from_manifest(archive: zipfile.ZipFile) -> str | None:
    try:
        raw = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except KeyError:
        return None
    for line in raw.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip()
    return None


def _parse_toml_metadata(raw: bytes, archive: zipfile.ZipFile) -> dict[str, Any]:
    data = tomllib.loads(_clean_toml(raw).decode("utf-8", errors="strict"))
    mods: list[dict[str, Any]] = []
    versions: dict[str, str] = {}
    for item in data.get("mods") or []:
        if not isinstance(item, dict) or not isinstance(item.get("modId"), str):
            continue
        mod_id = item["modId"].strip()
        if not mod_id or "${" in mod_id:
            continue
        version = item.get("version")
        if isinstance(version, str) and "${" not in version:
            versions[mod_id] = version.strip()
        mods.append({"mod_id": mod_id, "version": versions.get(mod_id)})
    fallback = _version_from_manifest(archive)
    if fallback and len(mods) == 1 and not mods[0]["version"]:
        mods[0]["version"] = fallback
        versions[mods[0]["mod_id"]] = fallback
    dependencies: list[dict[str, Any]] = []
    dep_table = data.get("dependencies") or {}
    if isinstance(dep_table, dict):
        for owner, values in dep_table.items():
            if not isinstance(values, list):
                continue
            for dep in values:
                if not isinstance(dep, dict) or not isinstance(dep.get("modId"), str):
                    continue
                dependencies.append(
                    {
                        "owner": str(owner),
                        "mod_id": dep["modId"].strip(),
                        "type": str(dep.get("type", "required")).lower(),
                        "mandatory": dep.get("mandatory"),
                        "side": str(dep.get("side", "BOTH")).upper(),
                        "version_range": dep.get("versionRange"),
                    }
                )
    return {
        "mod_ids": sorted({m["mod_id"] for m in mods}),
        "versions": versions,
        "dependencies": dependencies,
    }


def _parse_fabric_metadata(raw: bytes) -> dict[str, Any]:
    data = json.loads(raw.decode("utf-8"))
    mod_id = data.get("id") if isinstance(data, dict) else None
    version = data.get("version") if isinstance(data, dict) else None
    dependencies: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for kind, dep_type in (("depends", "required"), ("breaks", "incompatible")):
            values = data.get(kind)
            if isinstance(values, dict):
                for dep_id, dep_range in values.items():
                    dependencies.append(
                        {
                            "owner": str(mod_id or "fabric"),
                            "mod_id": str(dep_id),
                            "type": dep_type,
                            "mandatory": None,
                            "side": "BOTH",
                            "version_range": dep_range,
                        }
                    )
    versions = {str(mod_id): str(version)} if mod_id and version else {}
    return {"mod_ids": [str(mod_id)] if mod_id else [], "versions": versions, "dependencies": dependencies}


def _nested_metadata(archive: zipfile.ZipFile) -> tuple[set[str], dict[str, set[str]]]:
    ids: set[str] = set()
    versions: dict[str, set[str]] = {}
    names = archive.namelist()
    for name in names:
        if not name.lower().endswith(".jar"):
            continue
        try:
            with archive.open(name) as stream, zipfile.ZipFile(stream) as nested:
                lowered = {n.lower(): n for n in nested.namelist()}
                metadata = None
                for candidate in ("meta-inf/neoforge.mods.toml", "meta-inf/mods.toml", "fabric.mod.json"):
                    if candidate in lowered:
                        metadata = (candidate, lowered[candidate])
                        break
                if metadata is None:
                    continue
                key, actual = metadata
                if key.endswith(".toml"):
                    parsed = _parse_toml_metadata(nested.read(actual), nested)
                else:
                    parsed = _parse_fabric_metadata(nested.read(actual))
                ids.update(parsed["mod_ids"])
                for mod_id, version in parsed["versions"].items():
                    versions.setdefault(mod_id, set()).add(version)
        except (KeyError, OSError, ValueError, zipfile.BadZipFile, UnicodeError, tomllib.TOMLDecodeError, json.JSONDecodeError):
            continue
    return ids, versions


def _version_tokens(value: str) -> tuple[tuple[int, Any], ...]:
    tokens: list[tuple[int, Any]] = []
    for part in re.split(r"[._+\-]", value.casefold()):
        if not part:
            continue
        if part.isdigit():
            tokens.append((1, int(part)))
        else:
            for sub in re.findall(r"\d+|[a-z]+", part):
                tokens.append((1, int(sub)) if sub.isdigit() else (0, sub))
    return tuple(tokens)


def _compare_versions(left: str, right: str) -> int:
    a = list(_version_tokens(left))
    b = list(_version_tokens(right))
    size = max(len(a), len(b))
    a.extend([(1, 0)] * (size - len(a)))
    b.extend([(1, 0)] * (size - len(b)))
    return (a > b) - (a < b)


def _version_matches(version: str | None, expression: Any) -> bool:
    if not version:
        return True  # presence-only fallback when a provider has no exposed version
    if expression is None:
        return True
    spec = str(expression).strip()
    if not spec or spec == "*":
        return True
    if spec[0:1] in {"[", "("} and spec[-1:] in {"]", ")"}:
        body = spec[1:-1]
        if "," not in body:
            return _compare_versions(version, body) == 0
        low, high = (part.strip() for part in body.split(",", 1))
        if low:
            cmp = _compare_versions(version, low)
            if cmp < 0 or (cmp == 0 and spec[0] == "("):
                return False
        if high:
            cmp = _compare_versions(version, high)
            if cmp > 0 or (cmp == 0 and spec[-1] == ")"):
                return False
        return True
    clauses = re.findall(r"(>=|<=|>|<|=)?\s*([^\s]+)", spec)
    if clauses and any(op for op, _ in clauses):
        for op, bound in clauses:
            cmp = _compare_versions(version, bound)
            if op == ">=" and cmp < 0 or op == "<=" and cmp > 0 or op == ">" and cmp <= 0 or op == "<" and cmp >= 0 or op == "=" and cmp != 0:
                return False
        return True
    # Maven's bare recommendation does not restrict resolution; it expresses a
    # preferred version while the restriction set remains open.
    return True


def inspect_jar(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not zipfile.is_zipfile(path):
        raise ReleaseError(f"not a regular ZIP/JAR: {path}")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ReleaseError(f"JAR CRC failure {path.name}: {bad}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ReleaseError(f"duplicate ZIP entry in {path.name}")
        lowered = {name.lower(): name for name in names}
        parsed: dict[str, Any] = {"mod_ids": [], "versions": {}, "dependencies": []}
        kind = "library_container"
        for candidate in ("meta-inf/neoforge.mods.toml", "meta-inf/mods.toml", "fabric.mod.json"):
            if candidate not in lowered:
                continue
            actual = lowered[candidate]
            if candidate.endswith(".toml"):
                parsed = _parse_toml_metadata(archive.read(actual), archive)
                kind = "neoforge_toml"
            else:
                parsed = _parse_fabric_metadata(archive.read(actual))
                kind = "fabric_json"
            break
        if not parsed["mod_ids"] and path.name not in SAFE_LIBRARY_CONTAINERS:
            raise ReleaseError(f"no top-level mod ID in selected JAR: {path.name}")
        nested_ids, nested_versions = _nested_metadata(archive)
        return {
            "file": path.name,
            "path": str(path.resolve()),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "archive_crc": "PASS",
            "entry_count": len(names),
            "metadata_kind": kind,
            "mod_ids": parsed["mod_ids"],
            "versions": parsed["versions"],
            "dependencies": parsed["dependencies"],
            "nested_mod_ids": sorted(nested_ids),
            "nested_versions": {key: sorted(values) for key, values in sorted(nested_versions.items())},
        }


def _bundle_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["file"]).casefold()):
        digest.update(f"{row['file']}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8"))
    return digest.hexdigest().upper()


def _overlay_digest(rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: (str(item["target"]), str(item["target_rel"]).casefold())):
        digest.update(
            (
                f"{row['target']}\0{row['target_rel']}\0{row['bytes']}\0{row['sha256']}\0"
                f"{row['layer']}\0{row.get('merge_mode', 'replace')}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def _side_overlay_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["target_rel"]).casefold()):
        digest.update(
            (
                f"{row['target_rel']}\0{row['bytes']}\0{row['sha256']}\0{row['layer']}\0"
                f"{row['merge_mode']}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def _pair_digest(server_bundle: str, client_bundle: str, server_overlay: str, client_overlay: str) -> str:
    payload = (
        f"server_mods\0{server_bundle}\nclient_mods\0{client_bundle}\n"
        f"server_overlay\0{server_overlay}\nclient_overlay\0{client_overlay}\n"
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest().upper()


def _parse_properties(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig", errors="strict").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _artifact_row(row: Any, side: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ReleaseError(f"invalid {side} artifact selection row")
    for key in ("file", "path", "sha256", "bytes", "source"):
        if key not in row:
            raise ReleaseError(f"missing {key} in {side} artifact row")
    path = Path(str(row["path"]))
    if path.is_symlink() or not path.is_file() or path.name != str(row["file"]):
        raise ReleaseError(f"invalid selected artifact path: {path}")
    expected_sha = str(row["sha256"]).upper()
    expected_size = int(row["bytes"])
    if path.stat().st_size != expected_size or sha256(path) != expected_sha:
        raise ReleaseError(f"selected artifact byte/hash mismatch: {path}")
    return {**row, "path": str(path.resolve()), "sha256": expected_sha, "bytes": expected_size}


def _force_artifact(selections: dict[str, dict[str, Any]], entry: dict[str, Any], label: str) -> None:
    path = _locked_path(entry, label)
    filename = str(entry.get("file", path.name))
    if filename != path.name:
        raise ReleaseError(f"forced artifact filename mismatch for {label}")
    selections[filename.casefold()] = {
        "file": filename,
        "path": str(path),
        "sha256": str(entry["sha256"]).upper(),
        "bytes": path.stat().st_size,
        "source": str(entry.get("source", "LOCKED_ADDITION")),
    }


def _apply_side_classification(
    selections: dict[str, dict[str, dict[str, Any]]], side_report: dict[str, Any]
) -> dict[str, str]:
    if side_report.get("status") != "PASS_STATIC_SIDE_CLASSIFICATION" or side_report.get("unresolved_mod_ids") != []:
        raise ReleaseError("side classification is not a locked PASS with zero unknowns")
    policies: dict[str, str] = {}
    for row in side_report.get("classifications") or []:
        if not isinstance(row, dict):
            raise ReleaseError("invalid side classification row")
        filename = str(row.get("selected_file", ""))
        classification = str(row.get("classification", ""))
        if classification not in SIDE_CLASSIFICATIONS:
            raise ReleaseError(f"invalid classification {classification}: {filename}")
        inspection = row.get("inspection") or {}
        expected_sha = str(inspection.get("sha256", "")).upper()
        expected_size = int(inspection.get("bytes", -1))
        policies[filename.casefold()] = classification
        existing = selections["server"].get(filename.casefold()) or selections["client"].get(filename.casefold())
        if existing is None:
            raise ReleaseError(f"classified artifact absent from matrix: {filename}")
        if existing["sha256"] != expected_sha or existing["bytes"] != expected_size:
            raise ReleaseError(f"classified artifact lock mismatch: {filename}")
        for side in ("server", "client"):
            wanted = classification == "BOTH" or classification == f"{side.upper()}_ONLY"
            if wanted:
                selections[side][filename.casefold()] = dict(existing)
            else:
                selections[side].pop(filename.casefold(), None)
    return policies


def _apply_locked_side_overrides(
    selections: dict[str, dict[str, dict[str, Any]]], overrides: list[dict[str, Any]]
) -> dict[str, str]:
    policies: dict[str, str] = {}
    for row in overrides:
        filename = str(row.get("file", ""))
        classification = str(row.get("classification", ""))
        key = filename.casefold()
        if classification not in SIDE_CLASSIFICATIONS:
            raise ReleaseError(f"invalid locked side override: {filename}/{classification}")
        existing = selections["server"].get(key) or selections["client"].get(key)
        if existing is None:
            raise ReleaseError(f"locked side override artifact missing: {filename}")
        if existing["sha256"] != str(row.get("sha256", "")).upper():
            raise ReleaseError(f"locked side override hash mismatch: {filename}")
        for side in ("server", "client"):
            wanted = classification == "BOTH" or classification == f"{side.upper()}_ONLY"
            if wanted:
                selections[side][key] = dict(existing)
            else:
                selections[side].pop(key, None)
        policies[key] = classification
    return policies


def _apply_locked_exclusions(
    selections: dict[str, dict[str, dict[str, Any]]], exclusions: list[dict[str, Any]]
) -> list[str]:
    removed: list[str] = []
    for row in exclusions:
        filename = str(row.get("file", ""))
        key = filename.casefold()
        expected = str(row.get("sha256", "")).upper()
        found = False
        for side in ("server", "client"):
            existing = selections[side].get(key)
            if existing is None:
                continue
            found = True
            if existing["sha256"] != expected:
                raise ReleaseError(f"locked exclusion hash mismatch: {filename}")
            selections[side].pop(key)
        if not found:
            raise ReleaseError(f"locked exclusion artifact was not selected: {filename}")
        removed.append(filename)
    return removed


def _validate_dependency_closure(
    side: str, rows: list[dict[str, Any]], virtual_providers: dict[str, list[str]]
) -> dict[str, Any]:
    top_ids: dict[str, dict[str, Any]] = {}
    nested_ids: set[str] = set()
    nested_versions: dict[str, set[str]] = {}
    duplicates: list[dict[str, str]] = []
    for row in rows:
        nested_ids.update(row["nested_mod_ids"])
        for mod_id, versions in row.get("nested_versions", {}).items():
            nested_versions.setdefault(mod_id, set()).update(versions)
        for mod_id in row["mod_ids"]:
            if mod_id in top_ids and top_ids[mod_id]["file"] != row["file"]:
                duplicates.append({"mod_id": mod_id, "first": top_ids[mod_id]["file"], "second": row["file"]})
            top_ids[mod_id] = row
    if duplicates:
        raise ReleaseError(f"duplicate top-level mod IDs on {side}: {duplicates}")
    available = set(top_ids) | nested_ids | SYSTEM_MODS
    virtual: set[str] = set()
    for provider, supplied_ids in virtual_providers.items():
        if provider in available:
            virtual.update(supplied_ids)
    available.update(virtual)
    missing: list[dict[str, Any]] = []
    incompatible: list[dict[str, Any]] = []
    checked = 0
    for row in rows:
        for dep in row["dependencies"]:
            dep_id = str(dep.get("mod_id", ""))
            dep_type = str(dep.get("type", "required")).lower()
            required = dep_type == "required" or dep.get("mandatory") is True
            applies = str(dep.get("side", "BOTH")).upper() in {"BOTH", side.upper()}
            if not applies:
                continue
            checked += 1
            if required and dep_id not in available:
                missing.append({"file": row["file"], **dep})
            if dep_type == "incompatible" and dep_id in available:
                versions: list[str | None] = []
                if dep_id in top_ids:
                    versions.append(top_ids[dep_id]["versions"].get(dep_id))
                versions.extend(sorted(nested_versions.get(dep_id, set())))
                if not versions:
                    versions.append(None)
                if any(_version_matches(version, dep.get("version_range")) for version in versions):
                    incompatible.append({"file": row["file"], "provider_versions": versions, **dep})
    if missing:
        raise ReleaseError(f"missing required dependencies on {side}: {missing}")
    if incompatible:
        raise ReleaseError(f"incompatible selected dependencies on {side}: {incompatible}")
    return {
        "status": "PASS",
        "top_level_mod_ids": len(top_ids),
        "nested_mod_ids": len(nested_ids),
        "virtual_dependency_ids": sorted(virtual),
        "dependencies_checked": checked,
        "missing_required": 0,
        "incompatible_present": 0,
        "duplicate_top_level_mod_ids": 0,
    }


def _validate_special_contracts(
    spec: dict[str, Any], selections: dict[str, dict[str, dict[str, Any]]], inspected: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    rules = spec["artifact_contracts"]
    banned_exact = {str(name).casefold() for name in rules["banned_exact_files"]}
    banned_tokens = [str(token).casefold() for token in rules["banned_filename_tokens"]]
    required_both = rules["required_both"]
    required_client = rules["required_client"]
    results: dict[str, Any] = {}
    for side in ("server", "client"):
        names = set(selections[side])
        bad = sorted(name for name in names if name in banned_exact or any(token in name for token in banned_tokens))
        if bad:
            raise ReleaseError(f"banned artifacts selected on {side}: {bad}")
    for entry in required_both:
        filename = str(entry["file"])
        key = filename.casefold()
        expected = str(entry["sha256"]).upper()
        if any(selections[side].get(key, {}).get("sha256") != expected for side in ("server", "client")):
            raise ReleaseError(f"required BOTH artifact missing or mismatched: {filename}")
        results[filename] = "BOTH_SAME_HASH"
    for entry in required_client:
        filename = str(entry["file"])
        key = filename.casefold()
        expected = str(entry["sha256"]).upper()
        if selections["client"].get(key, {}).get("sha256") != expected:
            raise ReleaseError(f"required client artifact missing or mismatched: {filename}")
        results[filename] = "CLIENT_PRESENT"
    common = set(selections["server"]) & set(selections["client"])
    mismatched = [
        selections["server"][key]["file"]
        for key in common
        if selections["server"][key]["sha256"] != selections["client"][key]["sha256"]
    ]
    if mismatched:
        raise ReleaseError(f"BOTH filename hash mismatch: {mismatched}")

    by_side_ids = {
        side: {mod_id: row for row in inspected[side] for mod_id in row["mod_ids"]}
        for side in ("server", "client")
    }
    for side in ("server", "client"):
        spell = by_side_ids[side].get("irons_spellbooks")
        lib = by_side_ids[side].get("irons_lib")
        gecko = by_side_ids[side].get("geckolib")
        if not spell or not lib or not gecko:
            raise ReleaseError(f"Iron dependency set missing on {side}")
        spell_dep = [d for d in spell["dependencies"] if d["mod_id"] == "irons_lib" and d["type"] == "required"]
        lib_nf = [d for d in lib["dependencies"] if d["mod_id"] == "neoforge" and d["type"] == "required"]
        lib_gecko = [d for d in lib["dependencies"] if d["mod_id"] == "geckolib" and d["type"] == "required"]
        if not spell_dep or spell_dep[0]["version_range"] != "[1.21.1-1,1.21.1-2)":
            raise ReleaseError(f"unexpected irons_spellbooks -> irons_lib dependency on {side}")
        if not lib_nf or lib_nf[0]["version_range"] != "[21.1.200,)":
            raise ReleaseError(f"unexpected irons_lib NeoForge dependency on {side}")
        if not lib_gecko or lib_gecko[0]["version_range"] != "4.7.5.1":
            raise ReleaseError(f"unexpected irons_lib GeckoLib dependency on {side}")
        # NeoForge uses Maven VersionRange: a bare recommendation has an open
        # restriction set and accepts newer versions.  Lock the selected version
        # to the already-audited 4.9.1, which is >= the recommendation.
        if spec["target"]["neoforge"] < "21.1.200" or "4.9.1" not in gecko["file"]:
            raise ReleaseError(f"Iron runtime dependency version contract failed on {side}")
    return results


def _validate_overlay(spec: dict[str, Any]) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    overlay = spec["inputs"]["overlay_v2"]
    root = _locked_path({"path": overlay["root"]}, "overlay v2 root", directory=True)
    manifest_path = _locked_path(overlay["manifest"], "overlay v2 manifest")
    validation_path = _locked_path(overlay["validation"], "overlay v2 validation")
    if manifest_path.parent != root or validation_path.parent != root:
        raise ReleaseError("overlay v2 files are not rooted in the locked v2 directory")
    forbidden_v1 = str(overlay.get("forbidden_v1_manifest_sha256", "")).upper()
    if sha256(manifest_path) == forbidden_v1:
        raise ReleaseError("forbidden overlay v1 manifest selected")
    manifest = read_json(manifest_path)
    validation = read_json(validation_path)
    if manifest.get("schema") != 1 or manifest.get("status") != "PASS_STATIC_OVERLAY":
        raise ReleaseError("overlay manifest status/schema mismatch")
    if Path(str(manifest.get("root", ""))).resolve() != root:
        raise ReleaseError("overlay manifest root binding mismatch")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != int(overlay["file_count"]):
        raise ReleaseError("overlay row count mismatch")
    if validation.get("status") != "PASS" or validation.get("errors") != [] or validation.get("file_count") != len(rows):
        raise ReleaseError("overlay validation is not PASS")
    if manifest.get("content_digest_sha256") != overlay["content_digest_sha256"]:
        raise ReleaseError("overlay content digest lock mismatch")
    if _overlay_digest(rows) != overlay["content_digest_sha256"]:
        raise ReleaseError("overlay content digest recomputation failed")
    if validation.get("content_digest_sha256") != overlay["content_digest_sha256"]:
        raise ReleaseError("overlay validation digest mismatch")

    accounting = manifest.get("source_accounting")
    if not isinstance(accounting, dict):
        raise ReleaseError("overlay v2 source accounting missing")
    expected_accounting = overlay["source_accounting"]
    for key, expected in expected_accounting.items():
        if accounting.get(key) != expected:
            raise ReleaseError(f"overlay source accounting mismatch: {key}")
    if accounting["source_files"] != accounting["effective_pack_rows"] + accounting["exclusions"] + accounting["superseded_source_rows"]:
        raise ReleaseError("overlay source accounting conservation failed")
    if any(accounting.get(key) != 0 for key in ("missing", "extra", "duplicates")):
        raise ReleaseError("overlay source accounting reports unresolved paths")

    guarantees = manifest.get("guarantees") or {}
    if any(guarantees.get(key) is not True for key in REQUIRED_OVERLAY_GUARANTEES):
        raise ReleaseError("overlay guarantee gate failed")
    policy = manifest.get("production_config_policy") or {}
    for key, expected in spec["production_config"]["ports"].items():
        if policy.get(key) != expected:
            raise ReleaseError(f"overlay production port policy mismatch: {key}")
    if policy.get("server_properties_from_base_only") is not True:
        raise ReleaseError("overlay may not own production server.properties")
    for key, expected in overlay["bindings"].items():
        if (manifest.get("bindings") or {}).get(key) != expected:
            raise ReleaseError(f"overlay binding mismatch: {key}")

    seen: set[tuple[str, str]] = set()
    effective: dict[tuple[str, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ReleaseError(f"overlay row {index} is not an object")
        target = str(row.get("target", ""))
        if target not in TARGETS:
            raise ReleaseError(f"invalid overlay target: {target}")
        target_rel = _safe_rel(row.get("target_rel"), f"overlay target {index}")
        source_rel = _safe_rel(row.get("source_rel"), f"overlay source {index}")
        key = (target, target_rel.casefold())
        if key in seen:
            raise ReleaseError(f"duplicate overlay target row: {target}/{target_rel}")
        seen.add(key)
        merge_mode = str(row.get("merge_mode", "replace"))
        if merge_mode not in MERGE_MODES:
            raise ReleaseError(f"invalid merge mode: {merge_mode}")
        lower = target_rel.casefold()
        if lower == "server.properties" or lower.startswith(("world/", "saves/", "mods/")) or lower.endswith((".mca", ".mcr")):
            raise ReleaseError(f"world/config/mod leaked into overlay: {target_rel}")
        if "journeymap" in lower or lower in {"icon.png", "pack.png"}:
            raise ReleaseError(f"excluded UI/map payload leaked into overlay: {target_rel}")
        source = root / Path(source_rel)
        try:
            source.resolve().relative_to(root)
        except ValueError as exc:
            raise ReleaseError(f"overlay source escapes v2 root: {source_rel}") from exc
        if source.is_symlink() or not source.is_file():
            raise ReleaseError(f"missing overlay payload: {source_rel}")
        expected_size = int(row.get("bytes", -1))
        expected_hash = str(row.get("sha256", "")).upper()
        if source.stat().st_size != expected_size or sha256(source) != expected_hash:
            raise ReleaseError(f"overlay payload byte/hash mismatch: {source_rel}")
        normalized = dict(row)
        normalized["merge_mode"] = merge_mode
        normalized["source_path"] = str(source)
        effective[(target, target_rel)] = normalized
    for target_rel in CRITICAL_UI_TARGETS:
        row = effective.get(("CLIENT", target_rel))
        if not row or row["layer"] != "ui_sanitized" or row["merge_mode"] != "replace":
            raise ReleaseError(f"sanitized UI override missing: {target_rel}")
    for target_rel in CRITICAL_TERRAIN_TARGETS:
        row = effective.get(("SERVER", target_rel))
        if not row or row["layer"] != "terrain_frontier" or row["merge_mode"] != "replace":
            raise ReleaseError(f"terrain frontier replacement missing: {target_rel}")
    xaero = [row for row in effective.values() if row["layer"] == "xaero_converted"]
    if not xaero or any(row["target"] != "CLIENT" or row["merge_mode"] != "replace" for row in xaero):
        raise ReleaseError("Xaero conversion payload must be client-only replace rows")
    return root, manifest, validation


def _side_overlay_rows(manifest: dict[str, Any], side: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in manifest["files"]:
        if row["target"] not in {"BOTH", side.upper()}:
            continue
        result.append(
            {
                "target_rel": row["target_rel"],
                "source_rel": row["source_rel"],
                "bytes": int(row["bytes"]),
                "sha256": str(row["sha256"]).upper(),
                "layer": row["layer"],
                "layer_order": int(row["layer_order"]),
                "merge_mode": str(row.get("merge_mode", "replace")),
                "provenance": row.get("provenance"),
            }
        )
    if len({row["target_rel"].casefold() for row in result}) != len(result):
        raise ReleaseError(f"duplicate effective overlay target on {side}")
    return sorted(result, key=lambda row: row["target_rel"].casefold())


def _copy_side(
    side: str,
    selections: dict[str, dict[str, Any]],
    inspections: list[dict[str, Any]],
    overlay_root: Path,
    overlay_rows: list[dict[str, Any]],
    staging: Path,
    final_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mods_dir = staging / side / "mods"
    overlay_dir = staging / side / "overlay"
    mods_dir.mkdir(parents=True)
    overlay_dir.mkdir(parents=True)
    inspect_by_file = {row["file"].casefold(): row for row in inspections}
    mod_rows: list[dict[str, Any]] = []
    for key in sorted(selections):
        selected = selections[key]
        inspected = inspect_by_file[key]
        source = Path(selected["path"])
        destination = mods_dir / selected["file"]
        _copy_verified(source, destination, selected["bytes"], selected["sha256"])
        mod_rows.append(
            {
                "file": selected["file"],
                "bytes": selected["bytes"],
                "sha256": selected["sha256"],
                "mod_ids": inspected["mod_ids"],
                "versions": inspected["versions"],
                "metadata_kind": inspected["metadata_kind"],
                "archive_crc": "PASS",
                "entry_count": inspected["entry_count"],
                "nested_mod_ids": inspected["nested_mod_ids"],
                "source_kind": selected["source"],
                "source": selected["path"],
            }
        )
    published_overlay: list[dict[str, Any]] = []
    for row in overlay_rows:
        source = overlay_root / Path(row["source_rel"])
        destination = overlay_dir / Path(row["target_rel"])
        _copy_verified(source, destination, row["bytes"], row["sha256"])
        published_overlay.append(dict(row))
    mod_manifest = {
        "schema": 1,
        "status": "PASS_STATIC",
        "side": side,
        "mods_dir": str((final_root / side / "mods").resolve()),
        "file_count": len(mod_rows),
        "bytes": sum(row["bytes"] for row in mod_rows),
        "bundle_sha256": _bundle_digest(mod_rows),
        "files": mod_rows,
    }
    overlay_manifest = {
        "schema": 1,
        "status": "PASS_STATIC",
        "side": side,
        "overlay_dir": str((final_root / side / "overlay").resolve()),
        "file_count": len(published_overlay),
        "bytes": sum(row["bytes"] for row in published_overlay),
        "overlay_sha256": _side_overlay_digest(published_overlay),
        "merge_semantics": {
            "replace": "overwrite target when installing this locked layer",
            "copy_if_absent": "preserve an existing authoritative target; otherwise copy",
        },
        "files": published_overlay,
    }
    return mod_manifest, overlay_manifest


def _verify_published_side(root: Path, mod_manifest: dict[str, Any], overlay_manifest: dict[str, Any]) -> None:
    side = mod_manifest["side"]
    mods_dir = root / side / "mods"
    overlay_dir = root / side / "overlay"
    actual_mods = {path.name.casefold(): path for path in mods_dir.iterdir()}
    if len(actual_mods) != mod_manifest["file_count"] or set(actual_mods) != {row["file"].casefold() for row in mod_manifest["files"]}:
        raise ReleaseError(f"published mod set mismatch on {side}")
    for row in mod_manifest["files"]:
        path = actual_mods[row["file"].casefold()]
        if path.is_symlink() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise ReleaseError(f"published mod verification failed: {side}/{row['file']}")
    actual_overlay = [path for path in overlay_dir.rglob("*") if path.is_file()]
    if len(actual_overlay) != overlay_manifest["file_count"]:
        raise ReleaseError(f"published overlay count mismatch on {side}")
    for row in overlay_manifest["files"]:
        path = overlay_dir / Path(row["target_rel"])
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise ReleaseError(f"published overlay verification failed: {side}/{row['target_rel']}")
    if _bundle_digest(mod_manifest["files"]) != mod_manifest["bundle_sha256"]:
        raise ReleaseError(f"published bundle digest failed on {side}")
    if _side_overlay_digest(overlay_manifest["files"]) != overlay_manifest["overlay_sha256"]:
        raise ReleaseError(f"published overlay digest failed on {side}")


def build_release(spec_path: Path, output: Path, report_path: Path, markdown_path: Path, *, preflight_only: bool = False) -> dict[str, Any]:
    spec_path = spec_path.resolve()
    output = output.resolve()
    spec = read_json(spec_path)
    if spec.get("schema") != 1 or spec.get("release_kind") != "MECHANOMANIA_MATCHED_STATIC_RELEASE":
        raise ReleaseError("input lock schema/release kind mismatch")
    if output.exists():
        raise ReleaseError(f"output already exists; refusing reuse: {output}")

    inputs = spec["inputs"]
    baseline_root = _locked_path({"path": inputs["baseline"]["root"]}, "candidate14-r3 root", directory=True)
    baseline_locks = inputs["baseline"]
    baseline_files = {
        "ready": baseline_root / "READY.json",
        "server_manifest": baseline_root / "manifests/server.json",
        "client_manifest": baseline_root / "manifests/client.json",
    }
    for key, path in baseline_files.items():
        expected = str(baseline_locks[f"{key}_sha256"]).upper()
        if sha256(path) != expected:
            raise ReleaseError(f"candidate14-r3 {key} lock mismatch")
    ready = read_json(baseline_files["ready"])
    if ready.get("status") != "PASS" or ready.get("candidate") != 14:
        raise ReleaseError("candidate14-r3 baseline is not PASS")

    matrix_path = _locked_path(inputs["merge_matrix"], "Mechanomania merge matrix")
    matrix = read_json(matrix_path)
    if matrix.get("static_audit_status") != "PASS":
        raise ReleaseError("merge matrix static audit is not PASS")
    selections: dict[str, dict[str, dict[str, Any]]] = {"server": {}, "client": {}}
    artifact_selection = matrix.get("artifact_selection") or {}
    for side in ("server", "client"):
        rows = artifact_selection.get(side)
        if not isinstance(rows, list) or not rows:
            raise ReleaseError(f"merge matrix has no {side} artifact selection")
        for row in rows:
            normalized = _artifact_row(row, side)
            key = normalized["file"].casefold()
            if key in selections[side]:
                raise ReleaseError(f"duplicate selected filename on {side}: {normalized['file']}")
            selections[side][key] = normalized

    side_path = _locked_path(inputs["side_classification"], "side classification")
    side_report = read_json(side_path)
    side_policies = _apply_side_classification(selections, side_report)
    side_policies.update(
        _apply_locked_side_overrides(
            selections, spec["artifact_contracts"].get("side_overrides", [])
        )
    )
    locked_exclusions = _apply_locked_exclusions(
        selections, spec["artifact_contracts"].get("locked_exclusions", [])
    )
    for filename in locked_exclusions:
        side_policies.pop(filename.casefold(), None)
    for entry in spec["artifact_contracts"]["forced_both"]:
        for side in ("server", "client"):
            _force_artifact(selections[side], entry, f"forced BOTH {entry['file']}")
        side_policies[str(entry["file"]).casefold()] = "BOTH"

    # UI/Xaero/Terrain locks are validated independently of their overlay binding.
    ui_path = _locked_path(inputs["ui_release"], "UI purification release")
    ui = read_json(ui_path)
    if ui.get("selected_c6c") != "mods/c6c-1.2.5.1-purified.jar" or ui.get("selected_c6c_sha256") != spec["artifact_contracts"]["purified_c6c_sha256"]:
        raise ReleaseError("purified C6C release contract mismatch")
    xaero_report_path = _locked_path(inputs["xaero_report"], "Xaero conversion report")
    xaero_report = read_json(xaero_report_path)
    if xaero_report.get("status") != "STATIC_VALIDATION_PASSED":
        raise ReleaseError("Xaero conversion report is not STATIC_VALIDATION_PASSED")
    _locked_path(inputs["xaero_sums"], "Xaero SHA256SUMS")
    terrain_final_path = _locked_path(inputs["terrain_final"], "terrain final report")
    terrain_final = read_json(terrain_final_path)
    if terrain_final.get("status") != "READY_FOR_ISOLATED_RUNTIME_VALIDATION":
        raise ReleaseError("terrain static state mismatch")
    frontier_path = _locked_path(inputs["terrain_frontier_manifest"], "terrain frontier manifest")
    frontier = read_json(frontier_path)
    if frontier.get("status") != "STATIC_BLUEPRINT_ONLY" or frontier.get("tree_sha256") != inputs["terrain_frontier_tree_sha256"]:
        raise ReleaseError("terrain frontier manifest/tree lock mismatch")

    overlay_root, overlay_manifest, overlay_validation = _validate_overlay(spec)

    production = spec["production_config"]
    properties_path = _locked_path(production["server_properties"], "production server.properties")
    level_path = _locked_path(production["level_dat"], "production level.dat identity")
    properties = _parse_properties(properties_path)
    port_keys = {
        "server_port": "server-port",
        "rcon_port": "rcon.port",
        "query_port": "query.port",
    }
    for spec_key, property_key in port_keys.items():
        if properties.get(property_key) != str(production["ports"][spec_key]):
            raise ReleaseError(f"production port changed: {property_key}")

    inspected: dict[str, list[dict[str, Any]]] = {"server": [], "client": []}
    dependency_results: dict[str, Any] = {}
    for side in ("server", "client"):
        for key in sorted(selections[side]):
            row = selections[side][key]
            jar = inspect_jar(Path(row["path"]))
            if jar["file"] != row["file"] or jar["bytes"] != row["bytes"] or jar["sha256"] != row["sha256"]:
                raise ReleaseError(f"JAR inspection lock mismatch: {side}/{row['file']}")
            inspected[side].append(jar)
        dependency_results[side] = _validate_dependency_closure(
            side,
            inspected[side],
            spec["artifact_contracts"].get("virtual_dependency_providers", {}),
        )
    contract_results = _validate_special_contracts(spec, selections, inspected)

    for key, classification in side_policies.items():
        in_server = key in selections["server"]
        in_client = key in selections["client"]
        if classification == "BOTH" and not (in_server and in_client):
            raise ReleaseError(f"BOTH side placement failed: {key}")
        if classification == "SERVER_ONLY" and not (in_server and not in_client):
            raise ReleaseError(f"SERVER_ONLY placement failed: {key}")
        if classification == "CLIENT_ONLY" and not (in_client and not in_server):
            raise ReleaseError(f"CLIENT_ONLY placement failed: {key}")

    server_overlay_rows = _side_overlay_rows(overlay_manifest, "server")
    client_overlay_rows = _side_overlay_rows(overlay_manifest, "client")
    common_mods = set(selections["server"]) & set(selections["client"])
    static_summary = {
        "schema": 1,
        "status": "PASS_STATIC_PREFLIGHT",
        "runtime_go": False,
        "minecraft_started": False,
        "java_started": False,
        "inputs": {
            "spec": str(spec_path),
            "spec_sha256": sha256(spec_path),
            "overlay_v2_manifest_sha256": sha256(Path(inputs["overlay_v2"]["manifest"]["path"])),
            "overlay_v2_validation_sha256": sha256(Path(inputs["overlay_v2"]["validation"]["path"])),
        },
        "checks": {
            "selected_jars_crc": "PASS",
            "selected_jars_duplicate_entries": "PASS",
            "side_classification": "PASS",
            "both_same_hash": "PASS",
            "dependency_closure": dependency_results,
            "duplicate_top_level_mod_ids": "PASS",
            "journeymap_selected": 0,
            "original_c6c_selected": 0,
            "old_iron_spellbooks_selected": 0,
            "irons_patreon_lib_selected": 0,
            "special_contracts": contract_results,
            "locked_conflict_exclusions": locked_exclusions,
            "overlay_v2": "PASS",
            "overlay_source_accounting": overlay_manifest["source_accounting"],
            "production_ports_preserved": True,
            "world_files_copied": 0,
        },
        "selection": {
            "server_mod_files": len(selections["server"]),
            "client_mod_files": len(selections["client"]),
            "both_mod_files": len(common_mods),
            "server_only_mod_files": len(set(selections["server"]) - common_mods),
            "client_only_mod_files": len(set(selections["client"]) - common_mods),
            "server_overlay_files": len(server_overlay_rows),
            "client_overlay_files": len(client_overlay_rows),
        },
        "production_identity": {
            "server_properties_path": str(properties_path),
            "server_properties_sha256": sha256(properties_path),
            "level_dat_path": str(level_path),
            "level_dat_sha256": sha256(level_path),
            "ports": production["ports"],
            "configuration_copied_into_release": False,
        },
        "runtime_blockers": list(spec["runtime_blockers"]),
    }
    if preflight_only:
        write_atomic(report_path, stable_json(static_summary))
        return static_summary

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.building-{uuid.uuid4().hex}"
    if staging.exists():
        raise ReleaseError(f"unexpected staging collision: {staging}")
    staging.mkdir(parents=False)
    published = False
    try:
        (staging / "manifests").mkdir()
        server_mod_manifest, server_overlay_manifest = _copy_side(
            "server", selections["server"], inspected["server"], overlay_root, server_overlay_rows, staging, output
        )
        client_mod_manifest, client_overlay_manifest = _copy_side(
            "client", selections["client"], inspected["client"], overlay_root, client_overlay_rows, staging, output
        )
        pair = _pair_digest(
            server_mod_manifest["bundle_sha256"],
            client_mod_manifest["bundle_sha256"],
            server_overlay_manifest["overlay_sha256"],
            client_overlay_manifest["overlay_sha256"],
        )
        manifests = {
            "server-mods.json": server_mod_manifest,
            "client-mods.json": client_mod_manifest,
            "server-overlay.json": server_overlay_manifest,
            "client-overlay.json": client_overlay_manifest,
        }
        for name, value in manifests.items():
            write_atomic(staging / "manifests" / name, stable_json(value))
        release = {
            **static_summary,
            "status": "STATIC_RELEASE_READY_RUNTIME_BLOCKED",
            "static_release_ready": True,
            "release_root": str(output),
            "target": spec["target"],
            "server": {
                "mod_file_count": server_mod_manifest["file_count"],
                "mod_bytes": server_mod_manifest["bytes"],
                "bundle_sha256": server_mod_manifest["bundle_sha256"],
                "mod_manifest": str(output / "manifests/server-mods.json"),
                "overlay_file_count": server_overlay_manifest["file_count"],
                "overlay_bytes": server_overlay_manifest["bytes"],
                "overlay_sha256": server_overlay_manifest["overlay_sha256"],
                "overlay_manifest": str(output / "manifests/server-overlay.json"),
            },
            "client": {
                "mod_file_count": client_mod_manifest["file_count"],
                "mod_bytes": client_mod_manifest["bytes"],
                "bundle_sha256": client_mod_manifest["bundle_sha256"],
                "mod_manifest": str(output / "manifests/client-mods.json"),
                "overlay_file_count": client_overlay_manifest["file_count"],
                "overlay_bytes": client_overlay_manifest["bytes"],
                "overlay_sha256": client_overlay_manifest["overlay_sha256"],
                "overlay_manifest": str(output / "manifests/client-overlay.json"),
            },
            "bundle_pair_sha256": pair,
            "extension_policy": {
                "permanent_file_count_cap": False,
                "permanent_mod_allowlist": False,
                "future_mods_allowed": True,
                "future_datapacks_allowed": True,
                "mcmodsync_ota_layers_allowed": True,
                "future_change_gate": "regenerate signed/hash-locked manifests and rerun dependency/registry/runtime gates",
            },
            "installation_contract": {
                "world": "Use the authoritative converted world in place; this release contains no world files.",
                "server_properties": "Keep the authoritative production file unchanged; this release contains no server.properties.",
                "overlay_merge_modes": "Apply each side overlay manifest exactly; copy_if_absent preserves authoritative base config.",
            },
        }
        write_atomic(staging / "READY.json", stable_json(release))
        write_atomic(staging / "release-lock.json", stable_json(release))
        write_atomic(staging / "input-lock.json", spec_path.read_bytes())

        _verify_published_side(staging, server_mod_manifest, server_overlay_manifest)
        _verify_published_side(staging, client_mod_manifest, client_overlay_manifest)
        if (staging / "READY.json").read_bytes() != (staging / "release-lock.json").read_bytes():
            raise ReleaseError("READY/release-lock bytes differ")
        all_rel = [path.relative_to(staging).as_posix().casefold() for path in staging.rglob("*") if path.is_file()]
        if any(rel == "server.properties" or rel.endswith("/server.properties") or rel.endswith("/level.dat") or rel.endswith((".mca", ".mcr")) for rel in all_rel):
            raise ReleaseError("forbidden world/config file found in staged release")
        os.replace(staging, output)
        published = True

        ready_path = output / "READY.json"
        final_release = read_json(ready_path)
        final_release["ready_sha256"] = sha256(ready_path)
        final_release["release_lock_sha256"] = sha256(output / "release-lock.json")
        final_release["manifest_sha256"] = {
            name: sha256(output / "manifests" / name) for name in sorted(manifests)
        }
        write_atomic(report_path, stable_json(final_release))
        markdown = [
            "# Mechanomania matched static release",
            "",
            f"- Status: `{final_release['status']}`",
            f"- Release root: `{output}`",
            f"- Runtime GO: `{str(final_release['runtime_go']).lower()}`",
            f"- Server mods: `{server_mod_manifest['file_count']}` / `{server_mod_manifest['bundle_sha256']}`",
            f"- Client mods: `{client_mod_manifest['file_count']}` / `{client_mod_manifest['bundle_sha256']}`",
            f"- Pair: `{pair}`",
            f"- Server overlay: `{server_overlay_manifest['file_count']}` / `{server_overlay_manifest['overlay_sha256']}`",
            f"- Client overlay: `{client_overlay_manifest['file_count']}` / `{client_overlay_manifest['overlay_sha256']}`",
            "- No world, level.dat, or server.properties was copied.",
            "- Production ports remain 25566 / RCON 25575 / query 25565.",
            "- Minecraft/Java runtime was not started; runtime blockers remain explicit in READY.json.",
            "",
        ]
        write_atomic(markdown_path, "\n".join(markdown).encode("utf-8"))
        return final_release
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = build_release(args.spec, args.output, args.report, args.markdown, preflight_only=args.preflight_only)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
