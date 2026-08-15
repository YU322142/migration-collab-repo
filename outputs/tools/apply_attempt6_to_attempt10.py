#!/usr/bin/env python3
"""Fail-closed application of the verified Attempt6 data fixes to a fresh attempt.

This tool is deliberately narrow.  It accepts only fresh, explicitly named
Mechanomania attempt roots on ``D:\\Trans\\migration-audit-work``, verifies
the frozen Mechanomania release
and the Attempt6 candidate by pinned SHA-256 values, computes side placement
from the frozen release manifests, preflights every destination, and only then
replaces the selected files transactionally.

It never starts Java/Minecraft, copies a world, edits server.properties, edits
the frozen release, or installs MCModSync.  Rerunning against an already
patched exact target is safe and produces no target writes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import uuid
import zipfile
from typing import Any


ALLOWED_ROOT = Path(r"D:\Trans\migration-audit-work")
LOCKED_RELEASE_ROOT = ALLOWED_ROOT / "mechanomania-matched-release-v2-20260813"
LOCKED_CANDIDATE_ROOT = ALLOWED_ROOT / "attempt6-data-resource-fixes-20260814"
INTEGRATION_ROOT = ALLOWED_ROOT / "attempt10-data-resource-integration-20260814"

LOCKED_READY_SHA256 = "AE84FE740B74D50A937284A7916E460ED55580EF1B4B794D8107562133D7F236"
LOCKED_CANDIDATE_MANIFEST_SHA256 = "FEF5D5A9CF91154207B0D9530209A1408EE4DA2D2AF103AB57E9F19572857930"
LOCKED_CANDIDATE_SUMS_SHA256 = "318AABEABDAF38858033466C55A4CD07ED2D04BD3809D4F45445F83C3ACE1AE1"
LOCKED_RELEASE_MANIFEST_SHA256 = {
    "server-mods.json": "AC66E9533652C71FBD74D228C33CFB4D6D5E50A6583FD9A7D9CA3A940888F0D2",
    "client-mods.json": "E33ABE9EB6568F7DAE2FF4E9F176D8C02575E7A4E56499CE2E9B1F2F05F71E98",
    "server-overlay.json": "838E6BEBA5166C8CF26E12061E7F1863AAFA55F857E29E42EEFF9A6042C54788",
    "client-overlay.json": "E3EEDBAC5D4E176BC75D06EAF7CB9BC7410C9852796E9F1AC458C8FA218A53BA",
}

EXPECTED_JAR_COUNT = 11
EXPECTED_LOOSE_COUNT = 7
EXPECTED_JAR_SIDE_SET = frozenset({"server", "client"})
EXPECTED_LOOSE_SIDE_SET = frozenset({"server"})
TARGET_ROOT_RE = re.compile(
    r"^mechanomania-matched-(runtime|client)-attempt([1-9][0-9]*)-20260814$"
)


class IntegrationError(RuntimeError):
    """A fail-closed identity, safety, or application error."""


@dataclass(frozen=True)
class PatchItem:
    kind: str
    relative: str
    source_sha256: str
    output_sha256: str
    candidate_path: Path
    sides: tuple[str, ...]


@dataclass(frozen=True)
class TargetOperation:
    side: str
    kind: str
    relative: str
    source_sha256: str
    output_sha256: str
    candidate_path: Path
    target_path: Path
    state: str


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    return bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ) or path.is_symlink()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def overlaps(first: Path, second: Path) -> bool:
    return is_within(first, second) or is_within(second, first)


def same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve())) == os.path.normcase(str(second.resolve()))


def regular_file(path: Path, label: str) -> None:
    if not path.is_file() or is_reparse(path):
        raise IntegrationError(f"{label} is missing, linked, or not a regular file: {path}")


def assert_regular_tree(root: Path, label: str) -> None:
    if not root.is_dir() or is_reparse(root):
        raise IntegrationError(f"{label} root is missing or linked: {root}")
    for entry in root.rglob("*"):
        if is_reparse(entry):
            raise IntegrationError(f"{label} contains a linked/reparse entry: {entry}")


def read_json(path: Path, label: str) -> dict[str, Any]:
    regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrationError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise IntegrationError(f"{label} must be a JSON object: {path}")
    return value


def safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise IntegrationError(f"invalid relative path for {label}: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise IntegrationError(f"unsafe relative path for {label}: {value!r}")
    return value


def bundle_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["file"]).casefold()):
        digest.update(
            (
                f"{row['file']}\0{int(row['bytes'])}\0"
                f"{str(row['sha256']).upper()}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def overlay_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: str(item["target_rel"]).casefold()):
        digest.update(
            (
                f"{row['target_rel']}\0{int(row['bytes'])}\0"
                f"{str(row['sha256']).upper()}\0{row['layer']}\0"
                f"{row['merge_mode']}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest().upper()


def parse_sha256s(path: Path) -> dict[str, str]:
    regular_file(path, "Attempt6 SHA256SUMS")
    rows: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9A-F]{64})  (.+)", line)
        if match is None:
            raise IntegrationError(f"invalid SHA256SUMS row {number}")
        digest, relative = match.groups()
        relative = safe_relative(relative, f"SHA256SUMS row {number}")
        key = relative.casefold()
        if key in rows:
            raise IntegrationError(f"duplicate SHA256SUMS path: {relative}")
        rows[key] = digest
        candidate = LOCKED_CANDIDATE_ROOT / Path(relative)
        regular_file(candidate, f"SHA256SUMS payload {relative}")
        if sha256(candidate) != digest:
            raise IntegrationError(f"SHA256SUMS payload differs: {relative}")
    return rows


def _validate_mod_manifest(side: str) -> dict[str, Any]:
    path = LOCKED_RELEASE_ROOT / "manifests" / f"{side}-mods.json"
    expected_manifest_hash = LOCKED_RELEASE_MANIFEST_SHA256[path.name]
    if sha256(path) != expected_manifest_hash:
        raise IntegrationError(f"locked release manifest hash differs: {path.name}")
    manifest = read_json(path, f"{side} mod manifest")
    raw_rows = manifest.get("files")
    if (
        manifest.get("schema") != 1
        or manifest.get("status") != "PASS_STATIC"
        or manifest.get("side") != side
        or not isinstance(raw_rows, list)
        or not raw_rows
    ):
        raise IntegrationError(f"invalid {side} mod manifest header")
    directory = LOCKED_RELEASE_ROOT / side / "mods"
    if not directory.is_dir() or is_reparse(directory):
        raise IntegrationError(f"locked {side} mod directory is missing or linked")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise IntegrationError(f"non-object row in {side} mod manifest")
        name = raw.get("file")
        size = raw.get("bytes")
        digest = str(raw.get("sha256", "")).upper()
        mod_ids = raw.get("mod_ids")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.casefold().endswith(".jar")
            or name.casefold() in seen
            or not isinstance(size, int)
            or size <= 0
            or re.fullmatch(r"[0-9A-F]{64}", digest) is None
            or not isinstance(mod_ids, list)
        ):
            raise IntegrationError(f"invalid {side} mod manifest row: {raw!r}")
        if "mcmodsync" in name.casefold() or any(
            str(mod_id).casefold() == "mcmodsync" for mod_id in mod_ids
        ):
            raise IntegrationError(f"MCModSync is selected in the {side} release")
        seen.add(name.casefold())
        source = directory / name
        regular_file(source, f"locked {side} JAR {name}")
        if source.stat().st_size != size or sha256(source) != digest:
            raise IntegrationError(f"locked {side} JAR differs: {name}")
        rows.append(
            {"file": name, "bytes": size, "sha256": digest, "mod_ids": mod_ids}
        )
    actual = {entry.name.casefold() for entry in directory.iterdir() if entry.is_file()}
    if actual != seen or len(actual) != len(list(directory.iterdir())):
        raise IntegrationError(f"locked {side} mod directory has extra/non-file entries")
    if (
        manifest.get("file_count") != len(rows)
        or manifest.get("bytes") != sum(row["bytes"] for row in rows)
        or str(manifest.get("bundle_sha256", "")).upper() != bundle_digest(rows)
    ):
        raise IntegrationError(f"locked {side} mod manifest aggregate differs")
    return {
        "path": str(path),
        "sha256": expected_manifest_hash,
        "rows": rows,
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "bundle_sha256": bundle_digest(rows),
    }


def _validate_overlay_manifest(side: str) -> dict[str, Any]:
    path = LOCKED_RELEASE_ROOT / "manifests" / f"{side}-overlay.json"
    expected_manifest_hash = LOCKED_RELEASE_MANIFEST_SHA256[path.name]
    if sha256(path) != expected_manifest_hash:
        raise IntegrationError(f"locked release manifest hash differs: {path.name}")
    manifest = read_json(path, f"{side} overlay manifest")
    raw_rows = manifest.get("files")
    if (
        manifest.get("schema") != 1
        or manifest.get("status") != "PASS_STATIC"
        or manifest.get("side") != side
        or not isinstance(raw_rows, list)
        or not raw_rows
    ):
        raise IntegrationError(f"invalid {side} overlay manifest header")
    directory = LOCKED_RELEASE_ROOT / side / "overlay"
    if not directory.is_dir() or is_reparse(directory):
        raise IntegrationError(f"locked {side} overlay directory is missing or linked")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise IntegrationError(f"non-object row in {side} overlay manifest")
        relative = safe_relative(raw.get("target_rel"), f"{side} overlay target")
        size = raw.get("bytes")
        digest = str(raw.get("sha256", "")).upper()
        merge_mode = raw.get("merge_mode")
        layer = raw.get("layer")
        if (
            relative.casefold() in seen
            or not isinstance(size, int)
            or size < 0
            or re.fullmatch(r"[0-9A-F]{64}", digest) is None
            or merge_mode not in {"replace", "copy_if_absent"}
            or not isinstance(layer, str)
            or not layer
        ):
            raise IntegrationError(f"invalid {side} overlay row: {raw!r}")
        seen.add(relative.casefold())
        source = directory / Path(relative)
        regular_file(source, f"locked {side} overlay {relative}")
        if source.stat().st_size != size or sha256(source) != digest:
            raise IntegrationError(f"locked {side} overlay differs: {relative}")
        rows.append(
            {
                "target_rel": relative,
                "bytes": size,
                "sha256": digest,
                "merge_mode": merge_mode,
                "layer": layer,
            }
        )
    actual = {
        entry.relative_to(directory).as_posix().casefold()
        for entry in directory.rglob("*")
        if entry.is_file()
    }
    if actual != seen:
        raise IntegrationError(f"locked {side} overlay directory differs from manifest")
    if (
        manifest.get("file_count") != len(rows)
        or manifest.get("bytes") != sum(row["bytes"] for row in rows)
        or str(manifest.get("overlay_sha256", "")).upper() != overlay_digest(rows)
    ):
        raise IntegrationError(f"locked {side} overlay manifest aggregate differs")
    return {
        "path": str(path),
        "sha256": expected_manifest_hash,
        "rows": rows,
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "overlay_sha256": overlay_digest(rows),
    }


def validate_release() -> dict[str, Any]:
    assert_regular_tree(LOCKED_RELEASE_ROOT, "locked Mechanomania release")
    ready_path = LOCKED_RELEASE_ROOT / "READY.json"
    lock_path = LOCKED_RELEASE_ROOT / "release-lock.json"
    regular_file(ready_path, "locked READY")
    regular_file(lock_path, "locked release-lock")
    if (
        sha256(ready_path) != LOCKED_READY_SHA256
        or sha256(lock_path) != LOCKED_READY_SHA256
        or ready_path.read_bytes() != lock_path.read_bytes()
    ):
        raise IntegrationError("locked READY/release-lock identity differs")
    ready = read_json(ready_path, "locked READY")
    if (
        ready.get("schema") != 1
        or ready.get("status") != "STATIC_RELEASE_READY_RUNTIME_BLOCKED"
        or ready.get("static_release_ready") is not True
        or ready.get("runtime_go") is not False
        or Path(str(ready.get("release_root", ""))).resolve()
        != LOCKED_RELEASE_ROOT.resolve()
    ):
        raise IntegrationError("locked READY content identity differs")
    policy = ready.get("extension_policy")
    if (
        not isinstance(policy, dict)
        or policy.get("permanent_file_count_cap") is not False
        or policy.get("permanent_mod_allowlist") is not False
        or policy.get("future_mods_allowed") is not True
        or policy.get("future_datapacks_allowed") is not True
    ):
        raise IntegrationError("locked release would restrict future extensions")
    server_mods = _validate_mod_manifest("server")
    client_mods = _validate_mod_manifest("client")
    server_overlay = _validate_overlay_manifest("server")
    client_overlay = _validate_overlay_manifest("client")
    for side, mods, overlay in (
        ("server", server_mods, server_overlay),
        ("client", client_mods, client_overlay),
    ):
        bound = ready.get(side)
        if (
            not isinstance(bound, dict)
            or bound.get("mod_file_count") != mods["file_count"]
            or bound.get("mod_bytes") != mods["bytes"]
            or str(bound.get("bundle_sha256", "")).upper()
            != mods["bundle_sha256"]
            or Path(str(bound.get("mod_manifest", ""))).resolve()
            != Path(mods["path"]).resolve()
            or bound.get("overlay_file_count") != overlay["file_count"]
            or bound.get("overlay_bytes") != overlay["bytes"]
            or str(bound.get("overlay_sha256", "")).upper()
            != overlay["overlay_sha256"]
            or Path(str(bound.get("overlay_manifest", ""))).resolve()
            != Path(overlay["path"]).resolve()
        ):
            raise IntegrationError(f"locked READY {side} binding differs")
    return {
        "root": str(LOCKED_RELEASE_ROOT),
        "ready_sha256": LOCKED_READY_SHA256,
        "server_mods": server_mods,
        "client_mods": client_mods,
        "server_overlay": server_overlay,
        "client_overlay": client_overlay,
        "extension_policy": policy,
        "mcmodsync_selected": False,
    }


def _relative_candidate_output(path_value: Any, directory: str) -> str:
    if not isinstance(path_value, str):
        raise IntegrationError("candidate output path is not a string")
    path = Path(path_value)
    try:
        relative = path.resolve().relative_to(
            (LOCKED_CANDIDATE_ROOT / directory).resolve()
        )
    except (OSError, ValueError) as exc:
        raise IntegrationError(f"candidate output escapes {directory}: {path}") from exc
    return safe_relative(relative.as_posix(), "candidate output")


def validate_candidate() -> dict[str, Any]:
    assert_regular_tree(LOCKED_CANDIDATE_ROOT, "Attempt6 candidate")
    manifest_path = LOCKED_CANDIDATE_ROOT / "manifest.json"
    sums_path = LOCKED_CANDIDATE_ROOT / "SHA256SUMS.txt"
    if sha256(manifest_path) != LOCKED_CANDIDATE_MANIFEST_SHA256:
        raise IntegrationError("Attempt6 manifest hash differs")
    if sha256(sums_path) != LOCKED_CANDIDATE_SUMS_SHA256:
        raise IntegrationError("Attempt6 SHA256SUMS hash differs")
    sums = parse_sha256s(sums_path)
    if sums.get("manifest.json") != LOCKED_CANDIDATE_MANIFEST_SHA256:
        raise IntegrationError("Attempt6 SHA256SUMS does not bind manifest.json")
    manifest = read_json(manifest_path, "Attempt6 manifest")
    if manifest.get("schema") != "attempt6-data-resource-fixes/v1":
        raise IntegrationError("Attempt6 manifest schema differs")
    scope = manifest.get("scope_guard")
    if scope != {
        "minecraft_started": False,
        "attempt6_modified": False,
        "frozen_staging_modified": False,
        "production_modified": False,
        "prism_modified": False,
    }:
        raise IntegrationError("Attempt6 scope guard differs")
    jar_changes = manifest.get("jar_changes")
    loose_changes = manifest.get("loose_changes")
    source_jars = manifest.get("source_jars")
    source_loose = manifest.get("source_loose")
    if (
        not isinstance(jar_changes, list)
        or len(jar_changes) != EXPECTED_JAR_COUNT
        or not isinstance(loose_changes, list)
        or len(loose_changes) != EXPECTED_LOOSE_COUNT
        or not isinstance(source_jars, dict)
        or not isinstance(source_loose, dict)
    ):
        raise IntegrationError("Attempt6 candidate counts/maps differ")
    jars: dict[str, dict[str, Any]] = {}
    for change in jar_changes:
        if not isinstance(change, dict):
            raise IntegrationError("Attempt6 JAR change is not an object")
        relative = _relative_candidate_output(change.get("output"), "jars")
        if Path(relative).name != relative or not relative.casefold().endswith(".jar"):
            raise IntegrationError(f"invalid Attempt6 JAR output: {relative}")
        key = relative.casefold()
        if key in jars:
            raise IntegrationError(f"duplicate Attempt6 JAR output: {relative}")
        source_hash = str(change.get("source_sha256", "")).upper()
        output_hash = str(change.get("output_sha256", "")).upper()
        if (
            re.fullmatch(r"[0-9A-F]{64}", source_hash) is None
            or re.fullmatch(r"[0-9A-F]{64}", output_hash) is None
            or str(source_jars.get(relative, "")).upper() != source_hash
        ):
            raise IntegrationError(f"Attempt6 JAR hash binding differs: {relative}")
        candidate_path = LOCKED_CANDIDATE_ROOT / "jars" / relative
        regular_file(candidate_path, f"Attempt6 JAR {relative}")
        if sha256(candidate_path) != output_hash:
            raise IntegrationError(f"Attempt6 JAR payload differs: {relative}")
        if sums.get(f"jars/{relative}".casefold()) != output_hash:
            raise IntegrationError(f"Attempt6 SHA256SUMS misses JAR: {relative}")
        try:
            with zipfile.ZipFile(candidate_path) as archive:
                names = archive.namelist()
                if archive.testzip() is not None or len(names) != len(set(names)):
                    raise IntegrationError(f"Attempt6 JAR CRC/duplicate failure: {relative}")
        except zipfile.BadZipFile as exc:
            raise IntegrationError(f"Attempt6 JAR is not a ZIP: {relative}") from exc
        jars[key] = {
            "relative": relative,
            "source_sha256": source_hash,
            "output_sha256": output_hash,
            "candidate_path": candidate_path,
        }
    if {name.casefold() for name in source_jars} != set(jars):
        raise IntegrationError("Attempt6 source_jars and JAR outputs differ")
    loose: dict[str, dict[str, Any]] = {}
    for change in loose_changes:
        if not isinstance(change, dict):
            raise IntegrationError("Attempt6 loose change is not an object")
        relative = _relative_candidate_output(change.get("output"), "overlay")
        key = relative.casefold()
        if key in loose:
            raise IntegrationError(f"duplicate Attempt6 loose output: {relative}")
        source_hash = str(change.get("source_sha256", "")).upper()
        output_hash = str(change.get("output_sha256", "")).upper()
        if (
            re.fullmatch(r"[0-9A-F]{64}", source_hash) is None
            or re.fullmatch(r"[0-9A-F]{64}", output_hash) is None
            or str(source_loose.get(relative, "")).upper() != source_hash
        ):
            raise IntegrationError(f"Attempt6 loose hash binding differs: {relative}")
        candidate_path = LOCKED_CANDIDATE_ROOT / "overlay" / Path(relative)
        regular_file(candidate_path, f"Attempt6 loose payload {relative}")
        if sha256(candidate_path) != output_hash:
            raise IntegrationError(f"Attempt6 loose payload differs: {relative}")
        if sums.get(f"overlay/{relative}".casefold()) != output_hash:
            raise IntegrationError(f"Attempt6 SHA256SUMS misses loose payload: {relative}")
        try:
            json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise IntegrationError(f"Attempt6 loose JSON is invalid: {relative}") from exc
        loose[key] = {
            "relative": relative,
            "source_sha256": source_hash,
            "output_sha256": output_hash,
            "candidate_path": candidate_path,
        }
    if {name.casefold() for name in source_loose} != set(loose):
        raise IntegrationError("Attempt6 source_loose and loose outputs differ")
    return {
        "root": str(LOCKED_CANDIDATE_ROOT),
        "manifest_sha256": LOCKED_CANDIDATE_MANIFEST_SHA256,
        "sha256s_sha256": LOCKED_CANDIDATE_SUMS_SHA256,
        "jars": jars,
        "loose": loose,
        "sha256sum_rows": len(sums),
    }


def build_patch_items(release: dict[str, Any], candidate: dict[str, Any]) -> list[PatchItem]:
    release_mods = {
        side: {row["file"].casefold(): row for row in release[f"{side}_mods"]["rows"]}
        for side in ("server", "client")
    }
    release_overlay = {
        side: {
            row["target_rel"].casefold(): row
            for row in release[f"{side}_overlay"]["rows"]
        }
        for side in ("server", "client")
    }
    items: list[PatchItem] = []
    for key, row in sorted(candidate["jars"].items()):
        sides = tuple(side for side in ("server", "client") if key in release_mods[side])
        if frozenset(sides) != EXPECTED_JAR_SIDE_SET:
            raise IntegrationError(f"unexpected side placement for JAR {row['relative']}: {sides}")
        for side in sides:
            if release_mods[side][key]["sha256"] != row["source_sha256"]:
                raise IntegrationError(
                    f"Attempt6 source hash is not the locked {side} JAR: {row['relative']}"
                )
        items.append(
            PatchItem(
                kind="jar",
                relative=row["relative"],
                source_sha256=row["source_sha256"],
                output_sha256=row["output_sha256"],
                candidate_path=row["candidate_path"],
                sides=sides,
            )
        )
    for key, row in sorted(candidate["loose"].items()):
        sides = tuple(side for side in ("server", "client") if key in release_overlay[side])
        if frozenset(sides) != EXPECTED_LOOSE_SIDE_SET:
            raise IntegrationError(
                f"unexpected side placement for loose file {row['relative']}: {sides}"
            )
        for side in sides:
            if release_overlay[side][key]["sha256"] != row["source_sha256"]:
                raise IntegrationError(
                    f"Attempt6 source hash is not the locked {side} overlay: {row['relative']}"
                )
        items.append(
            PatchItem(
                kind="loose",
                relative=row["relative"],
                source_sha256=row["source_sha256"],
                output_sha256=row["output_sha256"],
                candidate_path=row["candidate_path"],
                sides=sides,
            )
        )
    if sum(item.kind == "jar" for item in items) != EXPECTED_JAR_COUNT:
        raise IntegrationError("Attempt10 JAR patch plan count differs")
    if sum(item.kind == "loose" for item in items) != EXPECTED_LOOSE_COUNT:
        raise IntegrationError("Attempt10 loose patch plan count differs")
    return items


def _jar_declares_mcmodsync(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            for metadata in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                try:
                    text = archive.read(metadata).decode("utf-8", errors="replace")
                except KeyError:
                    continue
                if re.search(
                    r"(?im)^\s*modId\s*=\s*[\"']mcmodsync[\"']\s*$", text
                ):
                    return True
            try:
                fabric = json.loads(archive.read("fabric.mod.json"))
            except (KeyError, UnicodeError, json.JSONDecodeError):
                fabric = None
            if isinstance(fabric, dict) and str(fabric.get("id", "")).casefold() == "mcmodsync":
                return True
    except zipfile.BadZipFile as exc:
        raise IntegrationError(f"target mod is not a valid JAR: {path}") from exc
    return False


def assert_mcmodsync_absent(mods_dir: Path, label: str) -> None:
    if not mods_dir.is_dir() or is_reparse(mods_dir):
        raise IntegrationError(f"{label} mods directory is missing or linked: {mods_dir}")
    matches: list[str] = []
    for entry in mods_dir.iterdir():
        if not entry.is_file() or is_reparse(entry):
            raise IntegrationError(f"{label} mods contains a non-regular entry: {entry}")
        if entry.suffix.casefold() != ".jar":
            continue
        if "mcmodsync" in entry.name.casefold() or _jar_declares_mcmodsync(entry):
            matches.append(entry.name)
    if matches:
        raise IntegrationError(f"MCModSync must remain absent from {label}: {matches}")


def guard_target_root(root: Path, label: str) -> Path:
    resolved = root.resolve()
    if not resolved.is_dir() or is_reparse(resolved):
        raise IntegrationError(f"{label} target is missing, linked, or not a directory: {root}")
    if not is_within(resolved, ALLOWED_ROOT):
        raise IntegrationError(f"{label} target is outside D: migration-audit-work")
    if resolved.parent != ALLOWED_ROOT.resolve():
        raise IntegrationError(f"{label} target must be a direct child of D: migration-audit-work")
    identity = TARGET_ROOT_RE.fullmatch(resolved.name)
    if identity is None:
        raise IntegrationError(
            f"{label} target name is not an approved fresh-attempt root: {resolved.name}"
        )
    if label == "server" and identity.group(1) != "runtime":
        raise IntegrationError(f"server target has a client-shaped name: {resolved.name}")
    if label == "client" and identity.group(1) != "client":
        raise IntegrationError(f"client target has a server-shaped name: {resolved.name}")
    for protected in (LOCKED_RELEASE_ROOT, LOCKED_CANDIDATE_ROOT, INTEGRATION_ROOT):
        if overlaps(resolved, protected):
            raise IntegrationError(f"{label} target overlaps protected input/output: {protected}")
    mods = resolved / "mods"
    if not mods.is_dir() or is_reparse(mods):
        raise IntegrationError(f"{label} target mods directory is missing or linked")
    return resolved


def _assert_target_ancestors_regular(root: Path, target: Path) -> None:
    current = root
    relative = target.relative_to(root)
    for part in relative.parts[:-1]:
        current /= part
        if current.exists() and is_reparse(current):
            raise IntegrationError(f"target parent is linked/reparse: {current}")


def preflight_targets(
    items: list[PatchItem], server_root: Path, client_root: Path
) -> tuple[dict[str, Path], list[TargetOperation]]:
    roots = {
        "server": guard_target_root(server_root, "server"),
        "client": guard_target_root(client_root, "client"),
    }
    if overlaps(roots["server"], roots["client"]):
        raise IntegrationError("numbered Attempt server/client targets overlap")
    server_identity = TARGET_ROOT_RE.fullmatch(roots["server"].name)
    client_identity = TARGET_ROOT_RE.fullmatch(roots["client"].name)
    if server_identity is None or client_identity is None:
        raise IntegrationError("numbered Attempt identity was lost after target validation")
    if server_identity.group(2) != client_identity.group(2):
        raise IntegrationError(
            "server/client targets must use the same numbered Attempt identity"
        )
    for side, root in roots.items():
        assert_mcmodsync_absent(root / "mods", f"Attempt10 {side}")
    operations: list[TargetOperation] = []
    for item in items:
        for side in item.sides:
            root = roots[side]
            if item.kind == "jar":
                target = root / "mods" / item.relative
            else:
                target = root / Path(item.relative)
            _assert_target_ancestors_regular(root, target)
            regular_file(target, f"Attempt10 {side} {item.kind} target")
            observed = sha256(target)
            if observed == item.source_sha256:
                state = "SOURCE_EXACT"
            elif observed == item.output_sha256:
                state = "ALREADY_PATCHED_EXACT"
            else:
                raise IntegrationError(
                    f"Attempt10 {side} target has an unapproved hash: {target}: {observed}"
                )
            operations.append(
                TargetOperation(
                    side=side,
                    kind=item.kind,
                    relative=item.relative,
                    source_sha256=item.source_sha256,
                    output_sha256=item.output_sha256,
                    candidate_path=item.candidate_path,
                    target_path=target,
                    state=state,
                )
            )
    if len(operations) != EXPECTED_JAR_COUNT * 2 + EXPECTED_LOOSE_COUNT:
        raise IntegrationError("Attempt10 target operation count differs")
    return roots, operations


def apply_operations(operations: list[TargetOperation]) -> dict[str, Any]:
    changes = [operation for operation in operations if operation.state == "SOURCE_EXACT"]
    if not changes:
        return {"changed": 0, "already_patched": len(operations), "rolled_back": False}
    transaction = uuid.uuid4().hex
    staged: list[tuple[TargetOperation, Path, Path]] = []
    committed: list[tuple[TargetOperation, Path]] = []
    try:
        for operation in changes:
            stage = operation.target_path.with_name(
                operation.target_path.name + f".attempt10-stage-{transaction}"
            )
            backup = operation.target_path.with_name(
                operation.target_path.name + f".attempt10-backup-{transaction}"
            )
            if stage.exists() or backup.exists():
                raise IntegrationError(f"transaction scratch path already exists: {stage}")
            shutil.copy2(operation.candidate_path, stage)
            if sha256(stage) != operation.output_sha256:
                raise IntegrationError(f"staged payload hash differs: {stage}")
            staged.append((operation, stage, backup))
        for operation, stage, backup in staged:
            os.replace(operation.target_path, backup)
            try:
                os.replace(stage, operation.target_path)
            except Exception:
                os.replace(backup, operation.target_path)
                raise
            committed.append((operation, backup))
        for operation in operations:
            if sha256(operation.target_path) != operation.output_sha256:
                raise IntegrationError(f"post-apply hash differs: {operation.target_path}")
        for _, backup in committed:
            backup.unlink()
        return {
            "changed": len(changes),
            "already_patched": len(operations) - len(changes),
            "rolled_back": False,
        }
    except Exception:
        for operation, backup in reversed(committed):
            if backup.exists():
                if operation.target_path.exists():
                    operation.target_path.unlink()
                os.replace(backup, operation.target_path)
        for _, stage, backup in staged:
            if stage.exists():
                stage.unlink()
            if backup.exists():
                backup.unlink()
        raise
    finally:
        for _, stage, _ in staged:
            if stage.exists():
                stage.unlink()


def patch_plan_rows(items: list[PatchItem]) -> list[dict[str, Any]]:
    return [
        {
            "kind": item.kind,
            "relative": item.relative,
            "source_sha256": item.source_sha256,
            "output_sha256": item.output_sha256,
            "sides": list(item.sides),
        }
        for item in items
    ]


def base_report(
    release: dict[str, Any], candidate: dict[str, Any], items: list[PatchItem]
) -> dict[str, Any]:
    return {
        "schema": "attempt10-data-resource-integration/v1",
        "status": "PASS_INPUT_AUDIT",
        "release": {
            "root": release["root"],
            "ready_sha256": release["ready_sha256"],
            "manifest_sha256": dict(LOCKED_RELEASE_MANIFEST_SHA256),
            "server_mod_files": release["server_mods"]["file_count"],
            "client_mod_files": release["client_mods"]["file_count"],
            "server_overlay_files": release["server_overlay"]["file_count"],
            "client_overlay_files": release["client_overlay"]["file_count"],
            "source_hashes_verified": True,
            "future_extension_locked": False,
        },
        "candidate": {
            "root": candidate["root"],
            "manifest_sha256": candidate["manifest_sha256"],
            "sha256s_sha256": candidate["sha256s_sha256"],
            "sha256sum_rows": candidate["sha256sum_rows"],
            "patched_jars": EXPECTED_JAR_COUNT,
            "loose_files": EXPECTED_LOOSE_COUNT,
            "payload_hashes_verified": True,
        },
        "application": {
            "plan": patch_plan_rows(items),
            "jar_files_by_side": {"server": EXPECTED_JAR_COUNT, "client": EXPECTED_JAR_COUNT},
            "loose_files_by_side": {"server": EXPECTED_LOOSE_COUNT, "client": 0},
            "target_operations": EXPECTED_JAR_COUNT * 2 + EXPECTED_LOOSE_COUNT,
            "side_rule": "apply only where the exact frozen release manifest selected the source",
            "unknown_hash_rule": "abort before any target write",
            "transaction_rule": "stage all changed payloads, then replace with per-file rollback backups",
        },
        "mcmodsync": {
            "release_selected": False,
            "server_install_allowed": False,
            "client_install_currently_allowed": False,
            "policy": "globally absent for this Attempt10 integration",
        },
        "scope": {
            "minecraft_started": False,
            "java_started": False,
            "world_files_copied": 0,
            "world_files_modified": 0,
            "server_properties_modified": False,
            "production_modified": False,
            "release_modified": False,
            "attempt9_modified": False,
            "staging_modified": False,
            "prism_modified": False,
        },
    }


def stable_json(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def write_report(path: Path, report: dict[str, Any]) -> None:
    resolved = path.resolve()
    if not is_within(resolved, ALLOWED_ROOT):
        raise IntegrationError("report must be on D: migration-audit-work")
    payload = stable_json(report)
    if resolved.exists():
        regular_file(resolved, "existing report")
        if resolved.read_bytes() != payload:
            raise IntegrationError(f"report already exists with different bytes: {resolved}")
        return
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(resolved.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_bytes(payload)
    os.replace(temporary, resolved)


def run(args: argparse.Namespace) -> dict[str, Any]:
    release = validate_release()
    candidate = validate_candidate()
    items = build_patch_items(release, candidate)
    report = base_report(release, candidate, items)
    if args.audit_inputs_only:
        write_report(args.report, report)
        return report
    if args.server_root is None or args.client_root is None:
        raise IntegrationError("server-root and client-root are required outside input audit mode")
    roots, operations = preflight_targets(items, args.server_root, args.client_root)
    if overlaps(args.report.resolve(), roots["server"]) or overlaps(
        args.report.resolve(), roots["client"]
    ):
        raise IntegrationError("report must be outside both Attempt10 target roots")
    report["targets"] = {
        "server": str(roots["server"]),
        "client": str(roots["client"]),
        "mcmodsync_absent_before": True,
        "source_exact": sum(operation.state == "SOURCE_EXACT" for operation in operations),
        "already_patched_exact": sum(
            operation.state == "ALREADY_PATCHED_EXACT" for operation in operations
        ),
    }
    if not args.apply:
        report["status"] = "PASS_TARGET_PREFLIGHT"
        report["application_result"] = {
            "changed": 0,
            "target_writes": 0,
            "mode": "preflight_only",
        }
        write_report(args.report, report)
        return report
    result = apply_operations(operations)
    for side, root in roots.items():
        assert_mcmodsync_absent(root / "mods", f"Attempt10 {side}")
    report["status"] = "PASS_APPLIED"
    report["targets"]["mcmodsync_absent_after"] = True
    report["application_result"] = {**result, "mode": "apply"}
    write_report(args.report, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path)
    parser.add_argument("--client-root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--audit-inputs-only", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.audit_inputs_only and (
        args.apply or args.server_root is not None or args.client_root is not None
    ):
        print(
            json.dumps(
                {"status": "NO_GO", "error": "input audit mode does not accept targets/apply"},
                ensure_ascii=False,
            )
        )
        return 2
    try:
        report = run(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.report.resolve()),
                "minecraft_started": False,
                "java_started": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
