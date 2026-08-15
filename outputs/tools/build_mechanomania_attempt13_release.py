#!/usr/bin/env python3
"""Freeze the exact audited Attempt13 mod/overlay state as an immutable release.

This builder is intentionally static and fail-closed.  It never starts Java,
never touches Prism, never copies a world, and never copies runtime/log/cache
trees.  The destination is published with one same-volume atomic rename.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import Any
import uuid
import zipfile

import build_mechanomania_matched_release as legacy


ALLOWED_PARENT = Path(r"D:\Trans\migration-audit-work")
DEFAULT_SERVER = ALLOWED_PARENT / "mechanomania-matched-runtime-attempt13-20260814"
DEFAULT_CLIENT = ALLOWED_PARENT / "mechanomania-matched-client-attempt13-20260814"
DEFAULT_GATE = ALLOWED_PARENT / "mechanomania-startup-gate-attempt13-20260814.json"
DEFAULT_BASE = ALLOWED_PARENT / "mechanomania-matched-release-v2-20260813"
DEFAULT_OUTPUT = ALLOWED_PARENT / "mechanomania-matched-release-v3-20260814"
DEFAULT_REPORT = ALLOWED_PARENT / "mechanomania-matched-release-v3-build-20260814.json"
DEFAULT_MARKDOWN = ALLOWED_PARENT / "mechanomania-matched-release-v3-build-20260814.md"

GATE_SHA256 = "22E4BEE1EB6B3DE909650D02A980C9591679FC144E49D82828822EA7C7FAE425"
BASE_READY_SHA256 = "AE84FE740B74D50A937284A7916E460ED55580EF1B4B794D8107562133D7F236"
MAID_JS_SHA256 = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
MAID_JS_BYTES = 119
LOCAL_PACK_NAME = "migration-local-resources-mc1.21.1.zip"
LOCAL_PACK_SHA256 = "614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364"
LOCAL_PACK_BYTES = 110_377_999

TLM_GUIDE_OVERLAYS = (
    "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/maid/spawn_maid.json",
    "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/overview/multiblocks_altar.json",
)
TLM_GUIDE_ENTRIES = (
    "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/maid/spawn_maid.json",
    "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/overview/multiblocks_altar.json",
)
TLM_RECIPE_ENTRY = "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json"
TLM_ADVANCEMENT_ENTRY = "data/touhou_little_maid/advancement/base/spawn_maid.json"
TLM_STALE_RECIPE_ID = b"touhou_little_maid:altar_recipe/spawn_box"
DEBUG_RING = "kubejs/data/irons_spellbooks/loot_table/test/ring_gen_break_me.json"

# These are per-release repair contracts, never a permanent mod allowlist.
KNOWN_FIXED_JARS: dict[str, str] = {
    "mineastr-neoforge-1.21.1-0.6.26.jar": "0264D729A3343BE1645B5AFE16C15A7A57C7E89A9405FA67EC80EE06D4A148D8",
    "yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar": "673FECBFFAD26BB6D025FB5F60560CF6340E542BDF091D8D66074490515292F3",
    "backport-1.5-cat-serializer-fix.1.jar": "34291AF9D81B6AEE0780F5F511B2A9594664F36906AED40687DF1C7009E68B1D",
    "hotbath-1.21.1-3.0.0-registry-fix.1.jar": "1B53A2B7B2C6476BBAD3ACE344316DA7ABE62854967DE322E9A25CA1D5C7681A",
    "worldedit-mod-7.3.8-direction-property-fix.1.jar": "8EB5E39AA914EB1B09307B6C004478BD1263655FCCA880580673481EBFEF9283",
    "create-enchantment-industry-2.4.2-cei251-backport.1.jar": "5B2C3BE95385DBF93000759DB604AB4C71224D7455C437C1B4650D91FAC669EB",
    "create-carriage-orientation-guard-1.0.0+neoforge.1.21.1-p0.2.jar": "805D6841BD30B514A059B21BEE4B6C70E183CB379CA286032975DCB961D6D74E",
    "yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.1.jar": "31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D",
    "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar": "32BE64DD058B7A91F90107972D104BDC0946D858E690D4C72032F64873F9B15B",
    "DnT-ancient-city-overhaul-v2 [NeoForge].jar": "A7D3ABB6C39FB50C791D52E596C9D14C22D0287EAF6BA055A687C31C0A4C8A7E",
    "tracks-neoforge-1.21.1-1.0.1.jar": "3119FA84955907FD734EF77F2296EC2E546F4442BC3AE13B04046C5D71F61CCF",
    "irons_spellbooks-1.21.1-3.15.6.jar": "BD8235AEF2F7F4827D8005E9700C1C04E5F3A84C50E0F92685674CAC49E985DB",
}

# The disposable dedicated-server preparation intentionally sanitizes these
# two resource archives only on the server side.  The PASS client retained the
# immutable v2 bytes.  This is a locked, audited side divergence, not drift.
SIDE_SPECIFIC_JARS: dict[str, dict[str, str]] = {
    "CreateDragonsPlus-1.11.4.jar": {
        "server": "123A7636377C64B9A92C3712D6572C6D69BE69FD892FEFF44034AB5B738F972B",
        "client": "80687F22DAA95FA6240631097688F1E0295A5D31473D9AA56A14D360D863E98B",
    },
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar": {
        "server": "490D90CCACA95F97C469D55136AC0F231681BC9DC6C335A5B20BAEF704C191FE",
        "client": "4698B09F9A3EDD84AB37A9506C3B88C7B59E947B21AE894C477998421335FFB6",
    },
}

EXPECTED_REPLACED_BASE_FILES = {
    "backport-1.5.jar",
    "create-enchantment-industry-2.5.1.jar",
    "hotbath-1.21.1-3.0.0.jar",
    "mineastr-0.6.25.jar",
    "worldedit-mod-7.3.8.jar",
    "yuushya-1.21.0-neoforge-2.3.0.jar",
}

FORBIDDEN_COMPONENTS = {
    "world",
    "world_nether",
    "world_the_end",
    "logs",
    "crash-reports",
    "crash_reports",
    "saves",
    "natives",
    "cache",
    ".cache",
    "runtime-cache",
    "runtime_cache",
    "immersive_paintings_cache",
    "simplebackups",
    "libraries",
    "versions",
    "downloads",
}


class FreezeError(RuntimeError):
    pass


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    if is_reparse(path) or not path.is_file():
        raise FreezeError(f"missing regular JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FreezeError(f"JSON root must be an object: {path}")
    return value


def is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attrs = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def require_source_root(path: Path, label: str) -> Path:
    path = path.resolve()
    if not is_within(path, ALLOWED_PARENT) or path == ALLOWED_PARENT.resolve():
        raise FreezeError(f"{label} must be a child of {ALLOWED_PARENT}: {path}")
    if is_reparse(path) or not path.is_dir():
        raise FreezeError(f"{label} must be a regular directory: {path}")
    return path


def require_fresh_output(path: Path) -> Path:
    path = path.resolve()
    if path.parent != ALLOWED_PARENT.resolve() or not path.name.startswith("mechanomania-matched-release-v3-"):
        raise FreezeError(f"output must be a fresh v3 directory directly under {ALLOWED_PARENT}: {path}")
    if path.exists() or is_reparse(path):
        raise FreezeError(f"output already exists; refusing reuse: {path}")
    return path


def locked_json(path: Path, expected_sha256: str, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    actual = sha256(path)
    if actual != expected_sha256.upper():
        raise FreezeError(f"{label} SHA-256 mismatch: {actual} != {expected_sha256.upper()}")
    value = read_json(path)
    return value, {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": actual}


def verify_gate_report(gate_path: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    gate, gate_lock = locked_json(gate_path, GATE_SHA256, "Attempt13 PASS gate")
    if gate.get("status") != "PASS" or gate.get("blockers") != []:
        raise FreezeError("Attempt13 gate is not PASS with zero blockers")
    cleanup = gate.get("cleanup") or {}
    if cleanup.get("all_closed") is not True:
        raise FreezeError("Attempt13 gate did not prove all test ports/processes closed")
    report_nodes = (
        ("data_resource", gate.get("base_data_resource_repairs", {}).get("report")),
        ("content", gate.get("content_repairs", {}).get("report")),
        ("core", gate.get("content_repairs", {}).get("core_repairs", {}).get("report")),
        ("tlm", gate.get("content_repairs", {}).get("tlm_patch", {}).get("report")),
        ("happyghast", gate.get("content_repairs", {}).get("happyghast_repair", {}).get("report")),
        ("followup_postverify", gate.get("attempt11_followup_repairs", {}).get("report")),
        ("followup_apply", gate.get("attempt11_followup_repairs", {}).get("apply_report")),
    )
    evidence: list[dict[str, Any]] = []
    for name, row in report_nodes:
        if not isinstance(row, dict):
            raise FreezeError(f"gate is missing {name} report lock")
        path = Path(str(row.get("path", ""))).resolve()
        expected = str(row.get("sha256", "")).upper()
        expected_bytes = int(row.get("bytes", -1))
        if not is_within(path, ALLOWED_PARENT) or not path.is_file() or is_reparse(path):
            raise FreezeError(f"invalid {name} report path: {path}")
        actual = sha256(path)
        if actual != expected or path.stat().st_size != expected_bytes:
            raise FreezeError(f"{name} report lock drifted")
        evidence.append({"name": name, "path": str(path), "bytes": expected_bytes, "sha256": actual})
    return gate, gate_lock, evidence


def verify_base_release(base: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    ready = base / "READY.json"
    lock = base / "release-lock.json"
    if sha256(ready) != BASE_READY_SHA256 or sha256(lock) != BASE_READY_SHA256:
        raise FreezeError("immutable v2 READY/release-lock hash mismatch")
    if ready.read_bytes() != lock.read_bytes():
        raise FreezeError("immutable v2 READY/release-lock bytes differ")
    value = read_json(ready)
    if value.get("status") != "STATIC_RELEASE_READY_RUNTIME_BLOCKED":
        raise FreezeError("immutable v2 base status drifted")
    return value, {
        "root": str(base),
        "ready_sha256": BASE_READY_SHA256,
        "release_lock_sha256": BASE_READY_SHA256,
    }


def scan_mcmodsync_paths(root: Path) -> list[str]:
    hits: list[str] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in directories:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if "mcmodsync" in relative.casefold():
                hits.append(relative)
            if not is_reparse(path):
                retained.append(name)
        directories[:] = retained
        for name in files:
            relative = (current_path / name).relative_to(root).as_posix()
            if "mcmodsync" in relative.casefold():
                hits.append(relative)
    return sorted(set(hits), key=str.casefold)


def enumerate_mods(root: Path, side: str) -> list[Path]:
    mods = root / "mods"
    if not mods.is_dir() or is_reparse(mods):
        raise FreezeError(f"{side} mods directory is missing or reparse-backed")
    entries = list(mods.iterdir())
    bad = [path.name for path in entries if not path.is_file() or is_reparse(path) or path.suffix.casefold() != ".jar"]
    if bad:
        raise FreezeError(f"{side} mods contains non-regular-JAR entries: {bad[:20]}")
    names = [path.name.casefold() for path in entries]
    if len(names) != len(set(names)):
        raise FreezeError(f"{side} mods contains duplicate case-insensitive filenames")
    return sorted(entries, key=lambda path: path.name.casefold())


def inspect_mods(paths: list[Path]) -> list[dict[str, Any]]:
    workers = min(8, max(1, len(paths)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        rows = list(executor.map(legacy.inspect_jar, paths))
    return sorted(rows, key=lambda row: str(row["file"]).casefold())


def data_patch_contract(evidence: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    report_path = Path(next(row["path"] for row in evidence if row["name"] == "data_resource"))
    report = read_json(report_path)
    if report.get("status") != "PASS_APPLIED":
        raise FreezeError("data/resource transaction is not PASS_APPLIED")
    contract: dict[str, dict[str, str]] = {"server": {}, "client": {}}
    for row in report.get("application", {}).get("plan", []):
        if not isinstance(row, dict) or row.get("kind") != "jar":
            continue
        filename = Path(str(row.get("relative", ""))).name
        digest = str(row.get("output_sha256", "")).upper()
        for side in row.get("sides", []):
            if side in contract:
                contract[side][filename.casefold()] = digest
    return contract


def validate_mod_lineage(
    side: str,
    current: list[dict[str, Any]],
    base_manifest: dict[str, Any],
    data_contract: dict[str, dict[str, str]],
) -> dict[str, Any]:
    base = {str(row["file"]).casefold(): row for row in base_manifest.get("files", [])}
    now = {str(row["file"]).casefold(): row for row in current}
    allowed = dict(data_contract[side])
    allowed.update({name.casefold(): digest for name, digest in KNOWN_FIXED_JARS.items()})
    allowed.update({name.casefold(): hashes[side] for name, hashes in SIDE_SPECIFIC_JARS.items()})
    unchanged: list[str] = []
    fixed: list[str] = []
    for key, row in now.items():
        if key in base and row["sha256"] == str(base[key]["sha256"]).upper():
            unchanged.append(row["file"])
        elif allowed.get(key) == row["sha256"]:
            fixed.append(row["file"])
        else:
            old = base.get(key, {}).get("sha256")
            raise FreezeError(f"unaccounted {side} JAR delta: {row['file']} {old} -> {row['sha256']}")
    removed = sorted((set(base) - set(now)), key=str.casefold)
    unexpected_removed = [base[key]["file"] for key in removed if base[key]["file"] not in EXPECTED_REPLACED_BASE_FILES]
    if unexpected_removed:
        raise FreezeError(f"unaccounted {side} base JAR removals: {unexpected_removed}")
    return {
        "base_unchanged": len(unchanged),
        "controlled_fixed_or_added": len(fixed),
        "controlled_fixed_or_added_files": sorted(fixed, key=str.casefold),
        "replaced_base_files": sorted((base[key]["file"] for key in removed), key=str.casefold),
        "unknown_deltas": 0,
    }


def verify_known_fixed(rows_by_side: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for filename, expected in KNOWN_FIXED_JARS.items():
        sides: dict[str, Any] = {}
        for side in ("server", "client"):
            matches = [row for row in rows_by_side[side] if row["file"].casefold() == filename.casefold()]
            if len(matches) != 1 or matches[0]["sha256"] != expected:
                raise FreezeError(f"known fixed JAR missing/mismatched on {side}: {filename}")
            sides[side] = {"bytes": matches[0]["bytes"], "sha256": matches[0]["sha256"]}
        result[filename] = {"expected_sha256": expected, "sides": sides, "status": "BOTH_EXACT"}
    for filename, expected_by_side in SIDE_SPECIFIC_JARS.items():
        sides: dict[str, Any] = {}
        for side in ("server", "client"):
            matches = [row for row in rows_by_side[side] if row["file"].casefold() == filename.casefold()]
            expected = expected_by_side[side]
            if len(matches) != 1 or matches[0]["sha256"] != expected:
                raise FreezeError(f"side-specific JAR missing/mismatched on {side}: {filename}")
            sides[side] = {"bytes": matches[0]["bytes"], "sha256": matches[0]["sha256"]}
        result[filename] = {
            "expected_sha256_by_side": expected_by_side,
            "sides": sides,
            "status": "LOCKED_SERVER_RESOURCE_SANITIZATION_DIVERGENCE",
        }
    return result


def verify_tlm_content(roots: dict[str, Path]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for side, root in roots.items():
        jar = root / "mods" / "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
        with zipfile.ZipFile(jar) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.testzip() is not None:
                raise FreezeError(f"patched TLM archive integrity failed on {side}")
            for required in (TLM_RECIPE_ENTRY, TLM_ADVANCEMENT_ENTRY, *TLM_GUIDE_ENTRIES):
                if required not in names:
                    raise FreezeError(f"patched TLM {side} is missing {required}")
            for entry in TLM_GUIDE_ENTRIES:
                if TLM_STALE_RECIPE_ID in archive.read(entry):
                    raise FreezeError(f"stale spawn_box Patchouli reference survives on {side}: {entry}")
            if not archive.read(TLM_RECIPE_ENTRY) or not archive.read(TLM_ADVANCEMENT_ENTRY):
                raise FreezeError(f"patched TLM {side} recipe/advancement resource is empty")
        for relative in TLM_GUIDE_OVERLAYS:
            if (root / Path(relative)).exists():
                raise FreezeError(f"redundant loose TLM overlay survives on {side}: {relative}")
        result[side] = {"jar_sha256": sha256(jar), "loose_overlay_count": 0}
    return {
        "status": "PASS_BALANCE_RULE_PRESERVED",
        "sides": result,
        "spawn_box_recipe_removed_by_maid_js": True,
        "recipe_resource_preserved_in_jar": True,
        "advancement_resource_preserved_in_jar": True,
        "stale_patchouli_reference_count": 0,
    }


def safe_overlay_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FreezeError(f"invalid overlay relative path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != value:
        raise FreezeError(f"unsafe overlay path: {value}")
    folded = [part.casefold() for part in pure.parts]
    if any(part in FORBIDDEN_COMPONENTS for part in folded):
        raise FreezeError(f"forbidden runtime/cache component in overlay: {value}")
    if pure.name.casefold() == "server.properties" or pure.suffix.casefold() in {".mca", ".mcr", ".log"}:
        raise FreezeError(f"forbidden runtime/world file in overlay: {value}")
    return value


def audit_zip(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            names = archive.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise FreezeError(f"invalid overlay ZIP {path}: {exc}") from exc
    if bad is not None or len(names) != len(set(names)):
        raise FreezeError(f"overlay ZIP CRC/duplicate-entry failure: {path}")
    return {"entries": len(names), "crc": "PASS", "duplicate_entries": 0}


def prepare_overlay_rows(
    side: str,
    root: Path,
    base_manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    changed: list[str] = []
    removed: list[str] = []
    policy_excluded: list[str] = []
    zip_files = 0
    zip_entries = 0
    seen: set[str] = set()
    for baseline in base_manifest.get("files", []):
        raw_relative = str(baseline.get("target_rel", ""))
        raw_pure = PurePosixPath(raw_relative)
        raw_parts = [part.casefold() for part in raw_pure.parts]
        if any(part in FORBIDDEN_COMPONENTS for part in raw_parts):
            policy_excluded.append(raw_relative)
            continue
        relative = safe_overlay_relative(raw_relative)
        key = relative.casefold()
        if key in seen:
            raise FreezeError(f"duplicate base overlay target on {side}: {relative}")
        seen.add(key)
        source = root / Path(relative)
        if not source.is_file():
            if side == "server" and relative == DEBUG_RING:
                removed.append(relative)
                continue
            raise FreezeError(f"Attempt13 {side} overlay source is missing: {relative}")
        if is_reparse(source):
            raise FreezeError(f"Attempt13 {side} overlay source is reparse-backed: {relative}")
        digest = sha256(source)
        if digest != str(baseline.get("sha256", "")).upper():
            changed.append(relative)
        zip_audit = None
        if source.suffix.casefold() == ".zip":
            zip_audit = audit_zip(source)
            zip_files += 1
            zip_entries += int(zip_audit["entries"])
        row = {
            "target_rel": relative,
            "bytes": source.stat().st_size,
            "sha256": digest,
            "layer": baseline.get("layer"),
            "merge_mode": baseline.get("merge_mode", "replace"),
            "source_kind": "ATTEMPT13_PASS_EFFECTIVE_OVERLAY",
            "source": str(source),
            "base_sha256": str(baseline.get("sha256", "")).upper(),
            "changed_from_v2": digest != str(baseline.get("sha256", "")).upper(),
        }
        if zip_audit is not None:
            row["zip_audit"] = zip_audit
        rows.append(row)
    if side == "client":
        relative = f"resourcepacks/{LOCAL_PACK_NAME}"
        source = root / Path(relative)
        if not source.is_file() or is_reparse(source):
            raise FreezeError("Attempt13 local migration resource pack is missing")
        if source.stat().st_size != LOCAL_PACK_BYTES or sha256(source) != LOCAL_PACK_SHA256:
            raise FreezeError("Attempt13 local migration resource pack lock mismatch")
        zip_audit = audit_zip(source)
        zip_files += 1
        zip_entries += int(zip_audit["entries"])
        if relative.casefold() in seen:
            raise FreezeError("local migration resource pack duplicates a base overlay target")
        rows.append(
            {
                "target_rel": relative,
                "bytes": LOCAL_PACK_BYTES,
                "sha256": LOCAL_PACK_SHA256,
                "layer": "attempt13_local_resources",
                "merge_mode": "replace",
                "source_kind": "ATTEMPT13_PASS_LOCAL_RESOURCE_PACK",
                "source": str(source),
                "base_sha256": None,
                "changed_from_v2": True,
                "zip_audit": zip_audit,
            }
        )
    rows.sort(key=lambda row: str(row["target_rel"]).casefold())
    return rows, {
        "base_rows": int(base_manifest.get("file_count", len(base_manifest.get("files", [])))),
        "published_rows": len(rows),
        "changed_from_v2": len(changed),
        "changed_paths": sorted(changed, key=str.casefold),
        "removed_paths": removed,
        "policy_excluded_paths": sorted(policy_excluded, key=str.casefold),
        "added_paths": [f"resourcepacks/{LOCAL_PACK_NAME}"] if side == "client" else [],
        "zip_files_crc_checked": zip_files,
        "zip_entries_checked": zip_entries,
        "zip_duplicate_entries": 0,
    }


def mod_manifest(side: str, rows: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for row in rows:
        files.append(
            {
                "file": row["file"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "mod_ids": row["mod_ids"],
                "versions": row["versions"],
                "metadata_kind": row["metadata_kind"],
                "archive_crc": row["archive_crc"],
                "entry_count": row["entry_count"],
                "nested_mod_ids": row["nested_mod_ids"],
                "nested_versions": row.get("nested_versions", {}),
                "dependencies": row["dependencies"],
                "source_kind": "ATTEMPT13_PASS_ROOT",
                "source": row["path"],
                "published_path": str(output / side / "mods" / row["file"]),
            }
        )
    return {
        "schema": 2,
        "status": "PASS_LOCKED",
        "side": side,
        "mods_dir": str(output / side / "mods"),
        "file_count": len(files),
        "bytes": sum(int(row["bytes"]) for row in files),
        "bundle_sha256": legacy._bundle_digest(files),
        "files": files,
    }


def overlay_manifest(side: str, rows: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"source"}
            }
            | {"published_path": str(output / side / "overlay" / Path(row["target_rel"]))}
        )
    return {
        "schema": 2,
        "status": "PASS_LOCKED",
        "side": side,
        "overlay_dir": str(output / side / "overlay"),
        "file_count": len(normalized),
        "bytes": sum(int(row["bytes"]) for row in normalized),
        "overlay_sha256": legacy._side_overlay_digest(normalized),
        "files": normalized,
    }


def copy_side(
    side: str,
    mod_rows: list[dict[str, Any]],
    overlay_rows: list[dict[str, Any]],
    staging: Path,
) -> None:
    mods_dir = staging / side / "mods"
    overlay_dir = staging / side / "overlay"
    mods_dir.mkdir(parents=True)
    overlay_dir.mkdir(parents=True)
    for row in mod_rows:
        source = Path(row["path"])
        target = mods_dir / row["file"]
        shutil.copy2(source, target)
        if target.stat().st_size != row["bytes"] or sha256(target) != row["sha256"]:
            raise FreezeError(f"copied {side} JAR verification failed: {row['file']}")
    for row in overlay_rows:
        source = Path(row["source"])
        target = overlay_dir / Path(row["target_rel"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if target.stat().st_size != row["bytes"] or sha256(target) != row["sha256"]:
            raise FreezeError(f"copied {side} overlay verification failed: {row['target_rel']}")


def forbidden_release_paths(root: Path) -> list[str]:
    bad: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts = [part.casefold() for part in PurePosixPath(relative).parts]
        name = PurePosixPath(relative).name.casefold()
        if (
            any(part in FORBIDDEN_COMPONENTS for part in parts)
            or name == "server.properties"
            or name == "level.dat"
            or name == "session.lock"
            or PurePosixPath(relative).suffix.casefold() in {".mca", ".mcr", ".log"}
        ):
            bad.append(relative)
    return sorted(bad, key=str.casefold)


def tree_manifest(root: Path) -> tuple[list[dict[str, Any]], str]:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda p: p.relative_to(root).as_posix().casefold())
    ]
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8"))
    return rows, digest.hexdigest().upper()


def freeze(args: argparse.Namespace) -> dict[str, Any]:
    server = require_source_root(args.server, "Attempt13 server")
    client = require_source_root(args.client, "Attempt13 client")
    base = require_source_root(args.base, "immutable v2 base")
    output = require_fresh_output(args.output)
    report_path = args.report.resolve()
    markdown_path = args.markdown.resolve()
    for path, label in ((report_path, "report"), (markdown_path, "markdown")):
        if path.parent != ALLOWED_PARENT.resolve() or path.exists():
            raise FreezeError(f"{label} must be a fresh file directly under {ALLOWED_PARENT}: {path}")
    gate_path = args.gate.resolve()
    if not is_within(gate_path, ALLOWED_PARENT):
        raise FreezeError("gate report must stay under D: migration-audit-work")

    gate, gate_lock, evidence = verify_gate_report(gate_path)
    base_ready, base_lock = verify_base_release(base)
    roots = {"server": server, "client": client}
    mcmodsync_source = {side: scan_mcmodsync_paths(root) for side, root in roots.items()}
    if any(mcmodsync_source.values()):
        raise FreezeError(f"MCModSync path hits survive in Attempt13 roots: {mcmodsync_source}")
    for side, root in roots.items():
        if (root / DEBUG_RING).exists():
            raise FreezeError(f"debug Iron loot override survives on {side}")
    maid = server / "kubejs" / "server_scripts" / "maid.js"
    if not maid.is_file() or maid.stat().st_size != MAID_JS_BYTES or sha256(maid) != MAID_JS_SHA256:
        raise FreezeError("server maid.js balance rule drifted")
    if (client / "kubejs" / "server_scripts" / "maid.js").exists():
        raise FreezeError("unexpected client maid.js exists")

    source_mod_paths = {side: enumerate_mods(root, side) for side, root in roots.items()}
    expected_counts = {
        "server": int(gate.get("server_mods", {}).get("active_jar_count", -1)),
        "client": int(gate.get("client_mods", {}).get("active_jar_count", -1)),
    }
    for side in ("server", "client"):
        if len(source_mod_paths[side]) != expected_counts[side]:
            raise FreezeError(f"{side} current JAR count differs from the PASS gate snapshot")
    inspected = {side: inspect_mods(paths) for side, paths in source_mod_paths.items()}

    common = {row["file"].casefold(): row for row in inspected["server"]}
    client_by_name = {row["file"].casefold(): row for row in inspected["client"]}
    mismatched_common = []
    locked_side_divergence = []
    for key, row in common.items():
        if key not in client_by_name or row["sha256"] == client_by_name[key]["sha256"]:
            continue
        filename = row["file"]
        expected = SIDE_SPECIFIC_JARS.get(filename)
        if (
            expected
            and row["sha256"] == expected["server"]
            and client_by_name[key]["sha256"] == expected["client"]
        ):
            locked_side_divergence.append(filename)
        else:
            mismatched_common.append(filename)
    if mismatched_common:
        raise FreezeError(f"unreviewed server/client common filename hash mismatch: {mismatched_common}")

    spec = read_json(base / "input-lock.json")
    virtual = spec.get("artifact_contracts", {}).get("virtual_dependency_providers", {})
    dependency = {
        side: legacy._validate_dependency_closure(side, inspected[side], virtual)
        for side in ("server", "client")
    }
    for side in ("server", "client"):
        modsync_ids = sorted(
            {
                mod_id
                for row in inspected[side]
                for mod_id in row["mod_ids"]
                if "mcmodsync" in mod_id.casefold()
            }
        )
        if modsync_ids:
            raise FreezeError(f"MCModSync mod IDs survive on {side}: {modsync_ids}")

    fixed = verify_known_fixed(inspected)
    tlm = verify_tlm_content(roots)
    data_contract = data_patch_contract(evidence)
    base_mod_manifests = {
        side: read_json(base / "manifests" / f"{side}-mods.json")
        for side in ("server", "client")
    }
    lineage = {
        side: validate_mod_lineage(side, inspected[side], base_mod_manifests[side], data_contract)
        for side in ("server", "client")
    }

    base_overlay_manifests = {
        side: read_json(base / "manifests" / f"{side}-overlay.json")
        for side in ("server", "client")
    }
    overlay_rows: dict[str, list[dict[str, Any]]] = {}
    overlay_delta: dict[str, Any] = {}
    for side in ("server", "client"):
        overlay_rows[side], overlay_delta[side] = prepare_overlay_rows(
            side, roots[side], base_overlay_manifests[side]
        )

    summary: dict[str, Any] = {
        "schema": 2,
        "status": "PASS_PREFLIGHT" if args.preflight_only else "PASS_ATTEMPT13_RELEASE_LOCKED",
        "release_kind": "MECHANOMANIA_ATTEMPT13_IMMUTABLE_RELEASE",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runtime_go": True,
        "builder_started_java": False,
        "builder_started_minecraft": False,
        "builder_touched_prism": False,
        "source_gate": gate_lock | {"status": "PASS", "blockers": []},
        "base_release": base_lock,
        "evidence_reports": evidence,
        "source_roots": {"server": str(server), "client": str(client)},
        "target": base_ready.get("target"),
        "checks": {
            "jar_crc": "PASS",
            "jar_duplicate_zip_entries": 0,
            "duplicate_top_level_mod_ids": 0,
            "dependency_closure": dependency,
            "both_filename_hash_identity": {
                "status": "PASS_WITH_LOCKED_SERVER_RESOURCE_SANITIZATION",
                "locked_side_divergent_files": sorted(locked_side_divergence, key=str.casefold),
                "unreviewed_mismatches": [],
            },
            "known_fixed_jars": fixed,
            "mod_lineage": lineage,
            "maid_js": {"bytes": MAID_JS_BYTES, "sha256": MAID_JS_SHA256, "unchanged": True},
            "tlm_balance_and_patchouli": tlm,
            "tlm_loose_overlays": 0,
            "debug_iron_loot_override": "ABSENT",
            "mcmodsync": {
                "server_path_hits": mcmodsync_source["server"],
                "client_path_hits": mcmodsync_source["client"],
                "mod_id_hits": 0,
                "globally_absent": True,
            },
            "overlay_delta_from_v2": overlay_delta,
            "world_files_copied": 0,
            "server_properties_copied": 0,
            "logs_crash_saves_natives_cache_copied": 0,
            "title_ui": "PRESERVE_CURRENT_ATTEMPT13_CUSTOM_STATE_NO_FURTHER_PURIFICATION",
        },
        "selection": {
            "server_mod_files": len(inspected["server"]),
            "client_mod_files": len(inspected["client"]),
            "server_overlay_files": len(overlay_rows["server"]),
            "client_overlay_files": len(overlay_rows["client"]),
            "counts_are_snapshot_observations_not_permanent_caps": True,
        },
        "extension_policy": {
            "permanent_file_count_cap": False,
            "permanent_mod_allowlist": False,
            "future_mods_allowed": True,
            "future_datapacks_allowed": True,
            "future_client_only_ota_allowed": True,
            "future_release_rule": "regenerate new manifests/release-lock and rerun dependency, registry, startup, join, and gameplay gates",
            "current_mcmodsync_installation": "ABSENT_BOTH_SIDES",
            "server_mcmodsync_policy": "DO_NOT_INSTALL",
        },
        "external_state_contract": {
            "world": {
                "copied": False,
                "rule": "Use the authoritative Attempt13-repaired converted world in place.",
                "happyghast_report": next(row for row in evidence if row["name"] == "happyghast"),
                "gate_region_sha256": gate.get("content_repairs", {}).get("happyghast_repair", {}).get("region", {}).get("sha256"),
            },
            "server_properties": {
                "copied": False,
                "production_identity": base_ready.get("production_identity"),
                "rule": "Keep the authoritative production server.properties and port values unchanged.",
            },
            "immersive_paintings_cache": {
                "copied": False,
                "gate_observed": gate.get("immersive_paintings_cache"),
                "rule": "Runtime cache is intentionally external to this immutable release.",
            },
        },
        "installation_contract": {
            "mods": "Install each side's complete manifest; counts are versioned snapshot facts only.",
            "overlay": "Apply each side's overlay manifest exactly, respecting merge_mode.",
            "world": "Never replace the authoritative converted world with this release.",
            "server_properties": "Never replace the production server.properties with this release.",
            "mcmodsync": "Do not install on either side for this release.",
        },
    }
    if args.preflight_only:
        write_atomic(report_path, stable_json(summary))
        markdown = [
            "# Attempt13 immutable release preflight",
            "",
            "- Status: `PASS_PREFLIGHT`",
            f"- Gate: `{GATE_SHA256}`",
            f"- Server JARs: `{len(inspected['server'])}`",
            f"- Client JARs: `{len(inspected['client'])}`",
            "- MCModSync: absent on both sides.",
            "- No Java/Minecraft/Prism action was performed.",
            "",
        ]
        write_atomic(markdown_path, "\n".join(markdown).encode("utf-8"))
        return summary

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.building-{uuid.uuid4().hex}"
    if staging.exists():
        raise FreezeError(f"unexpected staging collision: {staging}")
    staging.mkdir()
    published = False
    try:
        copy_side("server", inspected["server"], overlay_rows["server"], staging)
        copy_side("client", inspected["client"], overlay_rows["client"], staging)
        (staging / "manifests").mkdir()
        manifests = {
            "server-mods.json": mod_manifest("server", inspected["server"], output),
            "client-mods.json": mod_manifest("client", inspected["client"], output),
            "server-overlay.json": overlay_manifest("server", overlay_rows["server"], output),
            "client-overlay.json": overlay_manifest("client", overlay_rows["client"], output),
        }
        for name, value in manifests.items():
            write_atomic(staging / "manifests" / name, stable_json(value))
        pair = legacy._pair_digest(
            manifests["server-mods.json"]["bundle_sha256"],
            manifests["client-mods.json"]["bundle_sha256"],
            manifests["server-overlay.json"]["overlay_sha256"],
            manifests["client-overlay.json"]["overlay_sha256"],
        )
        release = summary | {
            "release_root": str(output),
            "bundle_pair_sha256": pair,
            "server": {
                "mod_file_count": manifests["server-mods.json"]["file_count"],
                "mod_bytes": manifests["server-mods.json"]["bytes"],
                "bundle_sha256": manifests["server-mods.json"]["bundle_sha256"],
                "overlay_file_count": manifests["server-overlay.json"]["file_count"],
                "overlay_bytes": manifests["server-overlay.json"]["bytes"],
                "overlay_sha256": manifests["server-overlay.json"]["overlay_sha256"],
            },
            "client": {
                "mod_file_count": manifests["client-mods.json"]["file_count"],
                "mod_bytes": manifests["client-mods.json"]["bytes"],
                "bundle_sha256": manifests["client-mods.json"]["bundle_sha256"],
                "overlay_file_count": manifests["client-overlay.json"]["file_count"],
                "overlay_bytes": manifests["client-overlay.json"]["bytes"],
                "overlay_sha256": manifests["client-overlay.json"]["overlay_sha256"],
            },
            "manifest_sha256": {
                name: sha256(staging / "manifests" / name) for name in sorted(manifests)
            },
        }
        write_atomic(staging / "READY.json", stable_json(release))
        write_atomic(staging / "release-lock.json", stable_json(release))
        if (staging / "READY.json").read_bytes() != (staging / "release-lock.json").read_bytes():
            raise FreezeError("READY/release-lock bytes differ")
        forbidden = forbidden_release_paths(staging)
        if forbidden:
            raise FreezeError(f"forbidden world/runtime/cache paths entered release: {forbidden[:20]}")
        if scan_mcmodsync_paths(staging):
            raise FreezeError("MCModSync path entered staged release")
        os.replace(staging, output)
        published = True
        final_forbidden = forbidden_release_paths(output)
        if final_forbidden or scan_mcmodsync_paths(output):
            raise FreezeError("post-publish forbidden-path verification failed")
        if (output / "READY.json").read_bytes() != (output / "release-lock.json").read_bytes():
            raise FreezeError("post-publish READY/release-lock bytes differ")
        tree_rows, tree_digest = tree_manifest(output)
        final = release | {
            "ready_sha256": sha256(output / "READY.json"),
            "release_lock_sha256": sha256(output / "release-lock.json"),
            "release_tree": {
                "file_count": len(tree_rows),
                "bytes": sum(row["bytes"] for row in tree_rows),
                "manifest_sha256": tree_digest,
            },
            "post_publish_verification": "PASS",
        }
        write_atomic(report_path, stable_json(final))
        markdown = [
            "# Mechanomania Attempt13 immutable release v3",
            "",
            f"- Status: `{final['status']}`",
            f"- Release: `{output}`",
            f"- Gate SHA-256: `{GATE_SHA256}`",
            f"- READY/release-lock SHA-256: `{final['ready_sha256']}`",
            f"- Server JARs: `{final['server']['mod_file_count']}` / `{final['server']['bundle_sha256']}`",
            f"- Client JARs: `{final['client']['mod_file_count']}` / `{final['client']['bundle_sha256']}`",
            f"- Pair SHA-256: `{pair}`",
            "- MCModSync is absent on both sides.",
            "- The current Attempt13 custom title UI was preserved without further purification.",
            "- No world, server.properties, logs, crash reports, saves, natives, or caches were copied.",
            "- Counts are this release's snapshot facts, not permanent extension limits.",
            "- This builder did not start Java/Minecraft and did not touch Prism.",
            "",
        ]
        write_atomic(markdown_path, "\n".join(markdown).encode("utf-8"))
        return final
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, default=DEFAULT_SERVER)
    parser.add_argument("--client", type=Path, default=DEFAULT_CLIENT)
    parser.add_argument("--gate", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        result = freeze(args)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": result["status"],
        "release_root": result.get("release_root"),
        "server_mods": result["selection"]["server_mod_files"],
        "client_mods": result["selection"]["client_mod_files"],
        "server_overlay": result["selection"]["server_overlay_files"],
        "client_overlay": result["selection"]["client_overlay_files"],
        "ready_sha256": result.get("ready_sha256"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
