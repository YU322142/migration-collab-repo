#!/usr/bin/env python3
"""Build and verify fail-closed integration acceptance evidence.

The eight check names emitted by this tool are the fixed contract consumed by
``final_release_gate.py``.  A check becomes PASS only after this process has
re-read its machine evidence, rebound it to the exact target and physical
runtime JAR set, and written an external evidence capsule.  Missing, stale,
conditional, target-mismatched, or hash-mismatched inputs produce NO_GO.

This tool never starts a server and never writes source, staging, or target.
It writes only the requested report and capsule directory, both of which must
be outside those protected trees.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Callable
import zipfile


SCHEMA_VERSION = 1
PASS = "PASS"
NO_GO = "NO_GO"
CHECK_NAMES = (
    "fullstack_cold_start",
    "reload_save_stop_restart",
    "semantic_world_compare",
    "villager_poi_gate",
    "create_saveddata_gate",
    "resource_sanitizer_gate",
    "mineastr_data_gate",
    "source_read_only_gate",
)
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
ALLOWED_DATA_VERSIONS = {3839, 3955, 4556, 4671}


class GateError(RuntimeError):
    """An expected, fail-closed validation error."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def stable_file(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if path.is_symlink() or not path.is_file():
        raise GateError("ARTIFACT_MISSING", f"{label}: missing regular file: {path}")
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise GateError("ARTIFACT_CHANGED_DURING_HASH", f"{label}: {path}")
    return {"label": label, "path": str(path), "bytes": after.st_size, "sha256": digest}


def read_json(path: Path, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = stable_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("JSON_INVALID", f"{label}: invalid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateError("JSON_ROOT_INVALID", f"{label}: root is not an object")
    return value, summary


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise GateError(code, detail)


def require_path(value: object, expected: Path, code: str, label: str) -> None:
    require(isinstance(value, str) and bool(value), code, f"{label}: path is missing")
    require(Path(str(value)).resolve() == expected.resolve(), code, f"{label}: belongs to {value!r}, expected {expected}")


def require_hex(value: object, code: str, label: str) -> str:
    require(isinstance(value, str) and bool(HEX64.fullmatch(value)), code, f"{label}: invalid SHA-256")
    return str(value).upper()


def atomic_json(path: Path, value: object) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load_local_tool(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise GateError("TOOL_IMPORT_FAILED", f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_config_path(value: object, base: Path, label: str) -> Path:
    if not isinstance(value, str) or not value.strip() or value.startswith("<"):
        raise GateError("CONFIG_PATH_MISSING", f"{label}: path is missing")
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


class Context:
    def __init__(
        self,
        config_path: Path,
        source: Path,
        staging: Path,
        target: Path,
        mods: Path,
        runtime_manifest_path: Path,
        evidence_dir: Path,
        artifacts: dict[str, Any],
        expected_mineastr_jar_sha256: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.source = source
        self.staging = staging
        self.target = target
        self.mods = mods
        self.runtime_manifest_path = runtime_manifest_path
        self.evidence_dir = evidence_dir
        self.artifacts = artifacts
        self.expected_mineastr_jar_sha256 = expected_mineastr_jar_sha256
        self.runtime: dict[str, Any] | None = None
        self.runtime_input: dict[str, Any] | None = None
        self.runtime_error: GateError | None = None

    @property
    def config_base(self) -> Path:
        return self.config_path.parent

    def artifact(self, name: str) -> Path:
        return resolve_config_path(self.artifacts.get(name), self.config_base, f"artifacts.{name}")

    def artifact_list(self, name: str) -> list[Path]:
        value = self.artifacts.get(name)
        if not isinstance(value, list) or not value:
            raise GateError("CONFIG_PATH_LIST_MISSING", f"artifacts.{name}: non-empty list required")
        return [resolve_config_path(item, self.config_base, f"artifacts.{name}") for item in value]


class CheckState:
    def __init__(self, name: str) -> None:
        self.name = name
        self.inputs: list[dict[str, Any]] = []
        self.observations: dict[str, Any] = {}
        self.blockers: list[dict[str, str]] = []

    def add_input(self, path: Path, label: str) -> dict[str, Any]:
        summary = stable_file(path, label)
        self.inputs.append(summary)
        return summary

    def fail(self, error: GateError) -> None:
        self.blockers.append({"code": error.code, "detail": error.detail})

    def attempt(self, function: Callable[[], None]) -> None:
        try:
            function()
        except GateError as exc:
            self.fail(exc)
        except Exception as exc:  # fail closed without aborting the remaining matrix
            self.fail(GateError("UNEXPECTED_VALIDATION_ERROR", f"{type(exc).__name__}: {exc}"))


def normalized_manifest(value: dict[str, Any], label: str) -> dict[str, Any]:
    if isinstance(value.get("runtime_mod_manifest"), dict):
        value = value["runtime_mod_manifest"]
    elif isinstance(value.get("resource_sanitization"), dict):
        nested = value["resource_sanitization"].get("runtime_mod_manifest")
        require(isinstance(nested, dict), "RUNTIME_MANIFEST_MISSING", f"{label}: nested runtime manifest missing")
        value = nested
    rows = value.get("files")
    require(isinstance(rows, list) and bool(rows), "RUNTIME_MANIFEST_FILES_INVALID", f"{label}: files missing")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    bundle = hashlib.sha256()
    for index, row in enumerate(rows):
        require(isinstance(row, dict), "RUNTIME_MANIFEST_ROW_INVALID", f"{label}.files[{index}]")
        name = row.get("file")
        require(isinstance(name, str) and Path(name).name == name and name not in seen, "RUNTIME_MANIFEST_ROW_INVALID", f"{label}.files[{index}].file")
        size = row.get("bytes")
        require(type(size) is int and size >= 1, "RUNTIME_MANIFEST_ROW_INVALID", f"{label}.{name}.bytes")
        digest = require_hex(row.get("sha256"), "RUNTIME_MANIFEST_ROW_INVALID", f"{label}.{name}.sha256")
        seen.add(name)
        result.append({"file": name, "bytes": size, "sha256": digest})
        bundle.update(name.encode("utf-8"))
        bundle.update(b"\0")
        bundle.update(digest.encode("ascii"))
        bundle.update(b"\n")
    require(result == sorted(result, key=lambda row: row["file"].lower()), "RUNTIME_MANIFEST_ORDER_INVALID", f"{label}: files are not sorted")
    require(value.get("file_count") == len(result), "RUNTIME_MANIFEST_COUNT_MISMATCH", label)
    require(value.get("bytes") == sum(row["bytes"] for row in result), "RUNTIME_MANIFEST_BYTES_MISMATCH", label)
    expected_bundle = require_hex(value.get("bundle_sha256"), "RUNTIME_BUNDLE_HASH_INVALID", label)
    require(bundle.hexdigest().upper() == expected_bundle, "RUNTIME_BUNDLE_HASH_MISMATCH", label)
    return {"file_count": len(result), "bytes": sum(row["bytes"] for row in result), "bundle_sha256": expected_bundle, "files": result}


def scan_runtime_mods(mods: Path) -> dict[str, Any]:
    require(mods.is_dir() and not mods.is_symlink(), "TARGET_MODS_INVALID", f"target mods directory invalid: {mods}")
    entries = list(mods.iterdir())
    require(all(item.is_file() and not item.is_symlink() for item in entries), "TARGET_MODS_NONFILE", f"target mods contains linked/non-file entry: {mods}")
    rows: list[dict[str, Any]] = []
    for path in sorted(entries, key=lambda item: item.name.lower()):
        require(path.suffix.lower() == ".jar" and zipfile.is_zipfile(path), "TARGET_MOD_INVALID", f"not a valid JAR: {path}")
        rows.append({"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    bundle = hashlib.sha256()
    for row in rows:
        bundle.update(row["file"].encode("utf-8"))
        bundle.update(b"\0")
        bundle.update(row["sha256"].encode("ascii"))
        bundle.update(b"\n")
    return {"file_count": len(rows), "bytes": sum(row["bytes"] for row in rows), "bundle_sha256": bundle.hexdigest().upper(), "files": rows}


def validate_runtime(ctx: Context) -> None:
    value, summary = read_json(ctx.runtime_manifest_path, "runtime manifest")
    if "mods" in value:
        require_path(value.get("mods"), ctx.mods, "RUNTIME_TARGET_MISMATCH", "runtime manifest mods")
    if "world" in value:
        require_path(value.get("world"), ctx.target / "world", "RUNTIME_TARGET_MISMATCH", "runtime manifest world")
    expected = normalized_manifest(value, "runtime manifest")
    actual = scan_runtime_mods(ctx.mods)
    require(expected == actual, "RUNTIME_JAR_DRIFT", "physical target JAR set differs from runtime manifest")
    ctx.runtime = actual
    ctx.runtime_input = summary


def add_runtime_binding(ctx: Context, state: CheckState) -> None:
    if ctx.runtime_error is not None:
        state.fail(ctx.runtime_error)
        return
    assert ctx.runtime is not None and ctx.runtime_input is not None
    state.inputs.append(dict(ctx.runtime_input))
    state.observations["runtime"] = {key: ctx.runtime[key] for key in ("file_count", "bytes", "bundle_sha256")}


def read_text_artifact(state: CheckState, path: Path, label: str) -> str:
    state.add_input(path, label)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GateError("LOG_READ_FAILED", f"{label}: {path}") from exc


def hard_log_diagnostics(text: str, allow_bootstrap_nonexistent: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    allowed: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
        hard = "/error]" in lower or "[error]" in lower or "fatal" in lower or "reported exception" in lower
        if not hard:
            continue
        if allow_bootstrap_nonexistent and "refmapremapper" in lower and "nosuchfileexception" in lower and "~nonexistent" in lower:
            allowed.append("CONNECTOR_REFMAP_NONEXISTENT_BOOTSTRAP")
        else:
            errors.append(line[:240])
    return errors, sorted(set(allowed))


def validate_fullstack(ctx: Context, state: CheckState) -> None:
    prepare_path = ctx.artifact("candidate_prepare_report")
    prepare, prepare_summary = read_json(prepare_path, "candidate prepare report")
    state.inputs.append(prepare_summary)
    require(prepare.get("schema") == 1 and prepare.get("status") == "PREPARED", "CANDIDATE_PREPARE_NOT_PASS", f"candidate prepare status={prepare.get('status')!r}")
    require_path(prepare.get("output"), ctx.target, "CANDIDATE_TARGET_MISMATCH", "candidate prepare output")
    require_path(prepare.get("staging"), ctx.staging, "CANDIDATE_STAGING_MISMATCH", "candidate prepare staging")
    log_path = ctx.artifact("cold_start_log")
    text = read_text_artifact(state, log_path, "cold-start log")
    require("Done (" in text, "COLD_START_NOT_DONE", "cold-start log has no Done marker")
    errors, allowed = hard_log_diagnostics(text, allow_bootstrap_nonexistent=True)
    require(not errors, "COLD_START_HARD_DIAGNOSTIC", f"cold-start hard diagnostics={len(errors)}")
    state.observations.update({"done_markers": text.count("Done ("), "allowed_diagnostics": allowed, "prepare_status": prepare["status"]})


def validate_reload_restart(ctx: Context, state: CheckState) -> None:
    cold = read_text_artifact(state, ctx.artifact("cold_start_log"), "cold-start log")
    restart = read_text_artifact(state, ctx.artifact("restart_log"), "restart log")
    for marker in ("Reloading!", "Saved the game", "Stopping server", "All dimensions are saved"):
        require(marker in cold, "RELOAD_SAVE_STOP_INCOMPLETE", f"cold-start log missing {marker!r}")
    for marker in ("Done (", "Saved the game", "Stopping server", "minecraft:overworld", "minecraft:the_nether", "minecraft:the_end"):
        require(marker in restart, "RESTART_INCOMPLETE", f"restart log missing {marker!r}")
    errors, allowed = hard_log_diagnostics(restart, allow_bootstrap_nonexistent=False)
    require(not errors, "RESTART_HARD_DIAGNOSTIC", f"restart hard diagnostics={len(errors)}")
    state.observations.update({"reload": True, "save_all": True, "normal_stop": True, "restart_done": True, "allowed_diagnostics": allowed})


def validate_loaded_region_report(value: dict[str, Any], ctx: Context, label: str) -> dict[str, int]:
    require(value.get("schema") == 1, "WORLD_COMPARE_SCHEMA_INVALID", label)
    require_path(value.get("source"), ctx.staging, "WORLD_COMPARE_STAGING_MISMATCH", label)
    require_path(value.get("target"), ctx.target, "WORLD_COMPARE_TARGET_MISMATCH", label)
    counts = value.get("counts")
    require(isinstance(counts, dict), "WORLD_COMPARE_COUNTS_MISSING", label)
    source_be = counts.get("source_block_entities")
    target_be = counts.get("target_block_entities")
    source_attached = counts.get("source_attached_entities")
    target_attached = counts.get("target_attached_entities")
    require(type(source_be) is int and source_be > 0 and source_be == target_be, "WORLD_BLOCK_ENTITY_COUNT_MISMATCH", label)
    require(type(source_attached) is int and source_attached >= 0 and source_attached == target_attached, "WORLD_ATTACHED_ENTITY_COUNT_MISMATCH", label)
    for key in ("missing_block_entities", "missing_attached_entities", "changed_attached_entities", "suspicious_attached_entities"):
        require(value.get(key) == [], "WORLD_COMPARE_DIFFERENCES", f"{label}.{key} is not empty")
    return {"block_entities": source_be, "attached_entities": source_attached}


def validate_semantic_world(ctx: Context, state: CheckState) -> None:
    paths = ctx.artifact_list("loaded_region_reports")
    require(len(paths) >= 2, "WORLD_COMPARE_ROUNDS_MISSING", "at least two loaded-region reports required")
    rounds = []
    for index, path in enumerate(paths):
        value, summary = read_json(path, f"loaded-region report {index + 1}")
        state.inputs.append(summary)
        rounds.append(validate_loaded_region_report(value, ctx, f"loaded-region report {index + 1}"))
    require(all(row == rounds[0] for row in rounds[1:]), "WORLD_COMPARE_ROUND_DRIFT", "loaded-region counts differ between rounds")
    state.observations["rounds"] = rounds


def validate_villager_report(value: dict[str, Any], ctx: Context) -> dict[str, Any]:
    require(value.get("status") == "PASS", "VILLAGER_REPORT_NOT_PASS", f"villager status={value.get('status')!r}")
    require_path(value.get("source_root"), ctx.source, "VILLAGER_SOURCE_MISMATCH", "villager source_root")
    require_path(value.get("target_game_dir"), ctx.target, "VILLAGER_TARGET_MISMATCH", "villager target_game_dir")
    summary = value.get("summary")
    require(isinstance(summary, dict), "VILLAGER_SUMMARY_MISSING", "villager summary missing")
    expected = summary.get("expected")
    require(type(expected) is int and expected >= 1193, "VILLAGER_COUNT_TOO_LOW", f"villager expected={expected!r}")
    require(summary.get("compared") == expected and summary.get("passed") == expected and summary.get("failed") == 0, "VILLAGER_COUNT_MISMATCH", "villager comparison counts do not close")
    require(summary.get("section_failures") == {}, "VILLAGER_SECTION_FAILURE", "villager section failures are not empty")
    source = value.get("source")
    target = value.get("target")
    require(isinstance(source, dict) and isinstance(target, dict), "VILLAGER_DETAIL_MISSING", "villager source/target summary missing")
    for key in ("missing_slots", "missing_entities", "baseline_mismatches"):
        require(source.get(key) == [], "VILLAGER_SOURCE_GAP", f"villager source.{key} is not empty")
    for key in ("duplicate_uuids", "missing", "extra"):
        require(target.get(key) == [], "VILLAGER_TARGET_GAP", f"villager target.{key} is not empty")
    comparisons = value.get("comparisons")
    require(isinstance(comparisons, dict) and len(comparisons) == expected, "VILLAGER_COMPARISON_SET_MISMATCH", "villager UUID comparison set incomplete")
    for uuid, row in comparisons.items():
        require(isinstance(row, dict) and row.get("status") == "PASS", "VILLAGER_UUID_NOT_PASS", f"villager {uuid} is not PASS")
        sections = row.get("checks", row.get("sections"))
        require(isinstance(sections, dict) and sections.get("offers") is True and sections.get("attributes") is True and all(value is True for value in sections.values()), "VILLAGER_SECTION_NOT_EQUAL", f"villager {uuid} section mismatch")
    return {"expected": expected, "passed": expected, "uuid_comparisons": len(comparisons)}


def validate_poi_runtime(value: dict[str, Any], ctx: Context) -> dict[str, Any]:
    require(value.get("schema") == 1 and value.get("status") == "PASS", "POI_RUNTIME_NOT_PASS", f"POI runtime status={value.get('status')!r}")
    require_path(value.get("world"), ctx.target / "world", "POI_TARGET_MISMATCH", "POI runtime world")
    records = value.get("records")
    require(type(records) is int and records >= 17606, "POI_RECORD_COUNT_TOO_LOW", f"POI records={records!r}")
    require(value.get("errors") == [] and value.get("duplicates") == [], "POI_RUNTIME_ERRORS", "POI runtime errors/duplicates are not empty")
    versions = {int(key) for key in value.get("data_versions", {})}
    allowed = set(value.get("allowed_data_versions", []))
    require(bool(versions) and versions <= ALLOWED_DATA_VERSIONS and versions <= allowed, "POI_DATA_VERSION_UNSUPPORTED", f"POI versions={sorted(versions)}")
    return {"records": records, "data_versions": sorted(versions)}


def validate_poi_compare(value: dict[str, Any]) -> dict[str, Any]:
    require(value.get("status") == "PASS", "POI_COMPARE_NOT_PASS", f"POI compare status={value.get('status')!r}")
    source = value.get("source_records")
    target = value.get("target_records")
    require(type(source) is int and source >= 17606 and target == source, "POI_COMPARE_COUNT_MISMATCH", f"POI source={source!r}, target={target!r}")
    for key in ("missing_count", "extra_count", "changed_count"):
        require(value.get(key) == 0, "POI_COMPARE_DIFFERENCES", f"POI {key}={value.get(key)!r}")
    for key in ("missing", "extra", "changed"):
        require(value.get(key) == [], "POI_COMPARE_DIFFERENCES", f"POI {key} is not empty")
    return {"source_records": source, "target_records": target, "differences": 0}


def validate_villager_poi(ctx: Context, state: CheckState) -> None:
    def villagers() -> None:
        villager, summary = read_json(ctx.artifact("villager_report"), "villager deep report")
        state.inputs.append(summary)
        state.observations["villagers"] = validate_villager_report(villager, ctx)

    def poi_runtime() -> None:
        value, summary = read_json(ctx.artifact("poi_runtime_report"), "POI runtime report")
        state.inputs.append(summary)
        state.observations["poi_runtime"] = validate_poi_runtime(value, ctx)

    def poi_compare() -> None:
        value, summary = read_json(ctx.artifact("poi_compare_report"), "POI semantic comparison")
        state.inputs.append(summary)
        state.observations["poi_compare"] = validate_poi_compare(value)

    state.attempt(villagers)
    state.attempt(poi_runtime)
    state.attempt(poi_compare)


def validate_create_conversion(value: dict[str, Any], kind: str) -> dict[str, Any]:
    require(value.get("status") in {"CONVERTED", "ALREADY_1_21_1"}, "CREATE_CONVERSION_NOT_PASS", f"{kind} status={value.get('status')!r}")
    require(value.get("blockers") == [], "CREATE_CONVERSION_BLOCKERS", f"{kind} blockers are not empty")
    if kind == "tracks":
        expected = {"rail_graphs": 4, "signal_groups": 79, "trains": 4, "dimensions": 2, "item_stacks_scanned": 1670}
        for key, count in expected.items():
            require(value.get(key) == count, "CREATE_TRACKS_COUNT_MISMATCH", f"tracks {key}={value.get(key)!r}, expected {count}")
        schema_counts = value.get("schema_counts", {})
        require(isinstance(schema_counts, dict) and schema_counts.get("conditions") == 6, "CREATE_TRACKS_SCHEMA_MISMATCH", "tracks condition count is not 6")
    else:
        expected = {"networks": 1, "links": 1, "promises": 41, "item_stacks_scanned": 41}
        for key, count in expected.items():
            require(value.get(key) == count, "CREATE_LOGISTICS_COUNT_MISMATCH", f"logistics {key}={value.get(key)!r}, expected {count}")
    return expected


def validate_create_saveddata(ctx: Context, state: CheckState) -> None:
    def create_conversion_and_runtime() -> None:
        tracks, summary = read_json(ctx.artifact("create_tracks_conversion_report"), "Create tracks conversion")
        state.inputs.append(summary)
        state.observations["tracks_conversion"] = validate_create_conversion(tracks, "tracks")
        logistics, summary = read_json(ctx.artifact("create_logistics_conversion_report"), "Create logistics conversion")
        state.inputs.append(summary)
        state.observations["logistics_conversion"] = validate_create_conversion(logistics, "logistics")

        runtime, summary = read_json(ctx.artifact("create_tracks_runtime_report"), "Create tracks runtime comparison")
        state.inputs.append(summary)
        require_path(runtime.get("left"), ctx.staging / "world/data/create_tracks.dat", "CREATE_RUNTIME_STAGING_MISMATCH", "Create tracks left")
        require_path(runtime.get("right"), ctx.target / "world/data/create_tracks.dat", "CREATE_RUNTIME_TARGET_MISMATCH", "Create tracks right")
        require(runtime.get("equivalent") is True and runtime.get("differences") == [], "CREATE_RUNTIME_NOT_EQUIVALENT", "Create tracks runtime comparison is not equivalent")
        require(runtime.get("left_semantic_sha256") == runtime.get("right_semantic_sha256"), "CREATE_RUNTIME_HASH_MISMATCH", "Create tracks semantic hashes differ")
        state.observations["tracks_runtime"] = runtime.get("counts")

        staging_logistics = ctx.staging / "world/data/create_logistics.dat"
        target_logistics = ctx.target / "world/data/create_logistics.dat"
        left = state.add_input(staging_logistics, "staging Create logistics")
        right = state.add_input(target_logistics, "target Create logistics")
        require(left["bytes"] == right["bytes"] and left["sha256"] == right["sha256"], "CREATE_LOGISTICS_RUNTIME_MISMATCH", "Create logistics changed after runtime")
        state.observations["logistics_runtime"] = {"bytes": right["bytes"], "sha256": right["sha256"]}

    def saveddata_verify() -> None:
        verify, summary = read_json(ctx.artifact("saveddata_verify_report"), "SavedData final verify")
        state.inputs.append(summary)
        require(verify.get("schema") == 1 and verify.get("phase") == "verify", "SAVEDDATA_VERIFY_SCHEMA_INVALID", "SavedData verify schema/phase invalid")
        status = verify.get("status")
        pending = verify.get("pending_saveddata")
        require(status == "VERIFIED_READ_ONLY", "SAVEDDATA_VERIFY_NOT_PASS", f"SavedData verify status={status!r}, pending_saveddata={pending!r}")
        require(pending == [], "SAVEDDATA_PENDING", f"pending_saveddata={pending!r}")
        state.observations["saveddata_verify"] = {"status": status, "pending_saveddata": pending}

    def target_chunks() -> None:
        chunks, summary = read_json(ctx.artifact("target_chunks_report"), "target chunks probe")
        state.inputs.append(summary)
        totals = chunks.get("totals")
        status = chunks.get("status")
        exit_code = chunks.get("exit_code")
        require(chunks.get("schema") == 1 and status == "READY_PORTAL_ZERO" and exit_code == 0, "TARGET_CHUNKS_NOT_READY", f"target chunks status={status!r}, exit={exit_code!r}, totals={totals!r}")
        require_path(chunks.get("source_world"), ctx.target / "world", "TARGET_CHUNKS_WORLD_MISMATCH", "target chunks source_world")
        require(chunks.get("blockers") == [], "TARGET_CHUNKS_BLOCKERS", "target chunks blockers are not empty")
        require(isinstance(totals, dict) and totals.get("portal_count") == 0, "TARGET_PORTAL_TICKETS_PRESENT", f"target chunks totals={totals!r}")
        state.observations["target_chunks"] = totals

    state.attempt(create_conversion_and_runtime)
    state.attempt(saveddata_verify)
    state.attempt(target_chunks)


def validate_sanitizer_report(value: dict[str, Any], ctx: Context, actual_runtime: dict[str, Any]) -> dict[str, Any]:
    require(value.get("schema") == 1 and value.get("status") == "SANITIZED_TARGET_COPY", "SANITIZER_NOT_PASS", f"sanitizer status={value.get('status')!r}")
    require_path(value.get("target_game_dir"), ctx.target, "SANITIZER_TARGET_MISMATCH", "sanitizer target_game_dir")
    require_path(value.get("target_mods_dir"), ctx.mods, "SANITIZER_MODS_MISMATCH", "sanitizer target_mods_dir")
    require(value.get("protected_tree_unchanged") is True, "SANITIZER_PROTECTED_TREE_UNPROVEN", "protected_tree_unchanged is not true")
    require(value.get("source_guard_before") == value.get("source_guard_after"), "SANITIZER_SOURCE_GUARD_DRIFT", "source guard changed")
    require(value.get("staging_guard_before") == value.get("staging_guard_after"), "SANITIZER_STAGING_GUARD_DRIFT", "staging guard changed")
    inner = value.get("resource_sanitization")
    require(isinstance(inner, dict) and inner.get("schema") == 1 and inner.get("status") in {"SANITIZED", "ALREADY_CLEAN"}, "SANITIZER_INNER_NOT_PASS", "nested sanitizer is not successful")
    require_path(inner.get("world"), ctx.target / "world", "SANITIZER_TARGET_MISMATCH", "sanitizer inner world")
    require_path(inner.get("mods"), ctx.mods, "SANITIZER_MODS_MISMATCH", "sanitizer inner mods")
    require_path(inner.get("server_properties"), ctx.target / "server.properties", "SANITIZER_TARGET_MISMATCH", "sanitizer server.properties")
    changes = inner.get("changes")
    require(isinstance(changes, list) and inner.get("changed_files") == len(changes), "SANITIZER_CHANGE_COUNT_MISMATCH", "sanitizer change count mismatch")
    for row in changes:
        require(isinstance(row, dict) and isinstance(row.get("path"), str) and path_is_within(Path(row["path"]), ctx.target), "SANITIZER_CHANGE_OUTSIDE_TARGET", f"invalid sanitizer change={row!r}")
    recorded = normalized_manifest(inner, "sanitizer runtime manifest")
    require(recorded == actual_runtime, "SANITIZER_RUNTIME_DRIFT", "sanitizer runtime manifest differs from physical target")
    return {"outer_status": value["status"], "inner_status": inner["status"], "changed_files": len(changes), "protected_tree_unchanged": True}


def validate_resource_sanitizer(ctx: Context, state: CheckState) -> None:
    assert ctx.runtime is not None
    report, summary = read_json(ctx.artifact("sanitizer_report"), "target sanitizer report")
    state.inputs.append(summary)
    state.observations.update(validate_sanitizer_report(report, ctx, ctx.runtime))


def load_nbt_cache_semantics(path: Path) -> tuple[str, int, int]:
    tool = load_local_tool("migrate_mineastr_cache.py", "integration_mineastr_cache")
    try:
        root = tool.NBTFile(filename=str(path))
        semantic = tool.semantic_hash(root).upper()
        version = int(root["version"].value)
        entries = len(root["entries"])
    except Exception as exc:
        raise GateError("MINEASTR_CACHE_PARSE_FAILED", f"cannot parse MineAstr cache: {path}: {exc}") from exc
    return semantic, version, entries


def validate_mineastr(ctx: Context, state: CheckState) -> None:
    config_report, summary = read_json(ctx.artifact("mineastr_config_report"), "MineAstr config migration report")
    state.inputs.append(summary)
    require(config_report.get("status") in {"CHANGED", "ALREADY_TARGET"}, "MINEASTR_CONFIG_NOT_PASS", f"config status={config_report.get('status')!r}")
    require(config_report.get("source_key_count") == 32 and config_report.get("target_key_count") == 34, "MINEASTR_CONFIG_COUNT_MISMATCH", "MineAstr config key counts are not 32 -> 34")
    require(len(config_report.get("preserved_keys", [])) == 32, "MINEASTR_CONFIG_PRESERVATION_MISMATCH", "MineAstr preserved key count is not 32")
    require(set(config_report.get("defaulted_keys", [])) == {"commandApprovalTimeoutSeconds", "commandMaxPendingApprovals"}, "MINEASTR_CONFIG_DEFAULTS_MISMATCH", "MineAstr explicit defaults differ")
    require(config_report.get("sensitive_values_redacted") is True, "MINEASTR_CONFIG_REPORT_NOT_REDACTED", "MineAstr report is not redacted")
    source_config = ctx.source / "config/mineastr-common.json"
    source_summary = state.add_input(source_config, "source MineAstr config")
    require(source_summary["sha256"] == require_hex(config_report.get("source_sha256"), "MINEASTR_CONFIG_SOURCE_HASH_INVALID", "MineAstr config source_sha256"), "MINEASTR_CONFIG_SOURCE_DRIFT", "source MineAstr config hash changed")
    staged_config = ctx.staging / "config/mineastr-common.toml"
    staged_summary = state.add_input(staged_config, "staged MineAstr config")
    require(staged_summary["sha256"] == require_hex(config_report.get("target_sha256"), "MINEASTR_CONFIG_TARGET_HASH_INVALID", "MineAstr config target_sha256"), "MINEASTR_CONFIG_STAGING_DRIFT", "staged MineAstr config hash differs from migration report")
    target_config = ctx.target / "config/mineastr-common.toml"
    state.add_input(target_config, "target MineAstr config")
    try:
        staged_values = tomllib.loads(staged_config.read_text(encoding="utf-8"))
        target_values = tomllib.loads(target_config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise GateError("MINEASTR_CONFIG_PARSE_FAILED", f"MineAstr TOML parse failed: {exc}") from exc
    changed_keys = sorted(key for key in set(staged_values) | set(target_values) if staged_values.get(key) != target_values.get(key))
    isolated_disable = changed_keys == ["enabled"] and staged_values.get("enabled") is True and target_values.get("enabled") is False
    require(not changed_keys or isolated_disable, "MINEASTR_CONFIG_RUNTIME_DRIFT", f"target MineAstr config changed keys={changed_keys}")

    cache_report, summary = read_json(ctx.artifact("mineastr_cache_report"), "MineAstr cache migration report")
    state.inputs.append(summary)
    expected_cache = {"target_version": 2, "entries": 40, "automatic_entries": 40, "manual_entries": 0, "skipped_entries": 0, "output_usable_entries": 40, "translation_value_count": 40}
    for key, expected in expected_cache.items():
        require(cache_report.get(key) == expected, "MINEASTR_CACHE_COUNT_MISMATCH", f"MineAstr cache {key}={cache_report.get(key)!r}, expected {expected}")
    require(cache_report.get("deterministic_gzip") is True and cache_report.get("entry_identifiers_redacted") is True and cache_report.get("content_values_redacted") is True, "MINEASTR_CACHE_REPORT_NOT_REDACTED", "MineAstr cache report lacks deterministic/redaction flags")
    source_cache = ctx.source / "world/data/mineastr_sign_translations.dat"
    source_cache_summary = state.add_input(source_cache, "source MineAstr cache")
    require(source_cache_summary["sha256"] == require_hex(cache_report.get("source_file_sha256"), "MINEASTR_CACHE_SOURCE_HASH_INVALID", "MineAstr source cache hash"), "MINEASTR_CACHE_SOURCE_DRIFT", "source MineAstr cache hash changed")
    staged_cache = ctx.staging / "world/data/mineastr_sign_translations.dat"
    staged_cache_summary = state.add_input(staged_cache, "staged MineAstr cache")
    require(staged_cache_summary["sha256"] == require_hex(cache_report.get("target_file_sha256"), "MINEASTR_CACHE_TARGET_HASH_INVALID", "MineAstr target cache hash"), "MINEASTR_CACHE_STAGING_DRIFT", "staged MineAstr cache hash differs from report")
    target_cache = ctx.target / "world/data/mineastr_sign_translations.dat"
    state.add_input(target_cache, "target MineAstr cache")
    semantic, version, entries = load_nbt_cache_semantics(target_cache)
    require(semantic == require_hex(cache_report.get("target_semantic_sha256"), "MINEASTR_CACHE_SEMANTIC_HASH_INVALID", "MineAstr target semantic hash"), "MINEASTR_CACHE_RUNTIME_DRIFT", "runtime MineAstr cache semantic hash differs")
    require(version == 2 and entries == 40, "MINEASTR_CACHE_RUNTIME_COUNT_MISMATCH", f"runtime MineAstr cache version={version}, entries={entries}")

    assert ctx.runtime is not None
    mineastr_rows = [row for row in ctx.runtime["files"] if row["file"].lower().startswith("mineastr-")]
    require(len(mineastr_rows) == 1, "MINEASTR_RUNTIME_JAR_AMBIGUOUS", f"MineAstr runtime JAR count={len(mineastr_rows)}")
    jar = ctx.mods / mineastr_rows[0]["file"]
    state.add_input(jar, "MineAstr runtime JAR")
    if ctx.expected_mineastr_jar_sha256 is not None:
        expected_jar = require_hex(ctx.expected_mineastr_jar_sha256, "MINEASTR_EXPECTED_JAR_HASH_INVALID", "expected MineAstr JAR")
        require(mineastr_rows[0]["sha256"] == expected_jar, "MINEASTR_RUNTIME_JAR_DRIFT", "MineAstr runtime JAR hash differs from locked candidate")
    state.observations.update({"config_keys": 34, "runtime_config_isolated_disable_only": isolated_disable, "cache_entries": entries, "cache_semantic_sha256": semantic, "jar": mineastr_rows[0]})


def validate_source_read_only(ctx: Context, state: CheckState) -> None:
    require(not any(path_is_within(left, right) or path_is_within(right, left) for index, left in enumerate((ctx.source, ctx.staging, ctx.target)) for right in (ctx.source, ctx.staging, ctx.target)[index + 1:]), "PROTECTED_TREE_OVERLAP", "source, staging, and target overlap")
    baseline_path = ctx.artifact("source_baseline")
    baseline, summary = read_json(baseline_path, "source baseline")
    state.inputs.append(summary)
    migration = load_local_tool("prepare_fast_migration.py", "integration_fast_migration")
    try:
        migration.validate_baseline_manifest(baseline, ctx.source, ctx.staging)
    except Exception as exc:
        raise GateError("SOURCE_BASELINE_INVALID", f"source baseline validation failed: {exc}") from exc
    sanitizer, summary = read_json(ctx.artifact("sanitizer_report"), "target sanitizer report")
    state.inputs.append(summary)
    require(sanitizer.get("protected_tree_unchanged") is True, "SOURCE_READ_ONLY_UNPROVEN", "sanitizer protected_tree_unchanged is not true")
    require(sanitizer.get("source_guard_before") == sanitizer.get("source_guard_after"), "SOURCE_GUARD_DRIFT", "source changed during target sanitization")
    require(sanitizer.get("staging_guard_before") == sanitizer.get("staging_guard_after"), "STAGING_GUARD_DRIFT", "staging changed during target sanitization")
    source_guard = sanitizer.get("source_guard_before")
    staging_guard = sanitizer.get("staging_guard_before")
    require(isinstance(source_guard, dict) and Path(str(source_guard.get("root", ""))).resolve() == ctx.source, "SOURCE_GUARD_TARGET_MISMATCH", "sanitizer source guard root mismatch")
    require(isinstance(staging_guard, dict) and Path(str(staging_guard.get("root", ""))).resolve() == ctx.staging, "STAGING_GUARD_TARGET_MISMATCH", "sanitizer staging guard root mismatch")
    try:
        lock = migration.probe_session_lock(ctx.source / "world")
    except Exception as exc:
        raise GateError("SOURCE_SESSION_LOCK_HELD", f"source session lock probe failed: {exc}") from exc
    require(lock.get("status") in {"ABSENT", "UNLOCKED_READ_ONLY_PROBE"}, "SOURCE_SESSION_LOCK_HELD", f"source lock status={lock.get('status')!r}")
    state.observations.update({"baseline_snapshot_sha256": baseline.get("snapshot_sha256"), "source_guard_unchanged": True, "staging_guard_unchanged": True, "session_lock": lock})


VALIDATORS: dict[str, Callable[[Context, CheckState], None]] = {
    "fullstack_cold_start": validate_fullstack,
    "reload_save_stop_restart": validate_reload_restart,
    "semantic_world_compare": validate_semantic_world,
    "villager_poi_gate": validate_villager_poi,
    "create_saveddata_gate": validate_create_saveddata,
    "resource_sanitizer_gate": validate_resource_sanitizer,
    "mineastr_data_gate": validate_mineastr,
    "source_read_only_gate": validate_source_read_only,
}


def load_context(config_path: Path, evidence_dir_override: Path | None = None) -> Context:
    config_path = config_path.resolve()
    value, _ = read_json(config_path, "integration input config")
    require(value.get("schema") == 1, "CONFIG_SCHEMA_INVALID", "integration config schema must be 1")
    base = config_path.parent
    source = resolve_config_path(value.get("source_game_dir"), base, "source_game_dir")
    staging = resolve_config_path(value.get("staging_game_dir"), base, "staging_game_dir")
    target = resolve_config_path(value.get("target_game_dir"), base, "target_game_dir")
    mods = resolve_config_path(value.get("target_mods_dir"), base, "target_mods_dir")
    runtime_manifest = resolve_config_path(value.get("runtime_manifest"), base, "runtime_manifest")
    evidence_dir = evidence_dir_override.resolve() if evidence_dir_override else resolve_config_path(value.get("evidence_dir"), base, "evidence_dir")
    artifacts = value.get("artifacts")
    require(isinstance(artifacts, dict), "CONFIG_ARTIFACTS_INVALID", "config.artifacts must be an object")
    expected_jar = value.get("expected_mineastr_jar_sha256")
    if expected_jar is not None:
        require_hex(expected_jar, "MINEASTR_EXPECTED_JAR_HASH_INVALID", "expected_mineastr_jar_sha256")
    return Context(config_path, source, staging, target, mods, runtime_manifest, evidence_dir, artifacts, expected_jar)


def ensure_output_safe(ctx: Context, path: Path, label: str) -> None:
    resolved = path.resolve()
    require(not any(path_is_within(resolved, root) for root in (ctx.source, ctx.staging, ctx.target)), "OUTPUT_INSIDE_PROTECTED_TREE", f"{label} must be outside source, staging, and target: {resolved}")


def evaluate(ctx: Context) -> list[CheckState]:
    try:
        validate_runtime(ctx)
    except GateError as exc:
        ctx.runtime_error = exc
    except Exception as exc:
        ctx.runtime_error = GateError("RUNTIME_VALIDATION_ERROR", f"{type(exc).__name__}: {exc}")
    states: list[CheckState] = []
    for name in CHECK_NAMES:
        state = CheckState(name)
        add_runtime_binding(ctx, state)
        if ctx.runtime_error is None:
            state.attempt(lambda name=name, state=state: VALIDATORS[name](ctx, state))
        states.append(state)
    return states


def capsule_payload(ctx: Context, state: CheckState, checked_at: str) -> dict[str, Any]:
    bundle = ctx.runtime["bundle_sha256"] if ctx.runtime is not None else None
    return {
        "schema": 1,
        "category": "integration-check",
        "name": state.name,
        "status": PASS if not state.blockers else "FAIL",
        "checked_at_utc": checked_at,
        "read_only": True,
        "target_game_dir": str(ctx.target),
        "runtime_bundle_sha256": bundle,
        "inputs": state.inputs,
        "observations": state.observations,
        "blockers": state.blockers,
    }


def build_report(ctx: Context, report_path: Path) -> tuple[dict[str, Any], int]:
    ensure_output_safe(ctx, report_path, "report")
    ensure_output_safe(ctx, ctx.evidence_dir, "evidence_dir")
    states = evaluate(ctx)
    checked_at = utc_now()
    checks: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    for state in states:
        capsule = ctx.evidence_dir / f"{state.name}.json"
        ensure_output_safe(ctx, capsule, f"capsule {state.name}")
        atomic_json(capsule, capsule_payload(ctx, state, checked_at))
        artifact = stable_file(capsule, f"integration capsule {state.name}")
        row = {
            "name": state.name,
            "status": PASS if not state.blockers else "FAIL",
            "target_game_dir": str(ctx.target),
            "runtime_bundle_sha256": ctx.runtime["bundle_sha256"] if ctx.runtime is not None else None,
            "artifact": {key: artifact[key] for key in ("path", "bytes", "sha256")},
            "blockers": state.blockers,
        }
        checks.append(row)
        blockers.extend({"check": state.name, **item} for item in state.blockers)
    status = PASS if not blockers and ctx.runtime is not None else NO_GO
    report = {
        "schema": SCHEMA_VERSION,
        "status": status,
        "exit_code": 0 if status == PASS else 2,
        "category": "integration",
        "checked_at_utc": checked_at,
        "read_only": True,
        "source_game_dir": str(ctx.source),
        "staging_game_dir": str(ctx.staging),
        "target_game_dir": str(ctx.target),
        "target_mods_dir": str(ctx.mods),
        "runtime_bundle_sha256": ctx.runtime["bundle_sha256"] if ctx.runtime is not None else None,
        "input_config": stable_file(ctx.config_path, "integration input config"),
        "runtime_manifest": stable_file(ctx.runtime_manifest_path, "runtime manifest") if ctx.runtime_manifest_path.is_file() else None,
        "validator": stable_file(Path(__file__), "integration verifier"),
        "blockers": blockers,
        "checks": checks,
    }
    atomic_json(report_path, report)
    return report, report["exit_code"]


def validate_existing_report(ctx: Context, report_path: Path) -> tuple[dict[str, Any], int]:
    recorded, report_summary = read_json(report_path, "integration acceptance report")
    require(recorded.get("schema") == 1 and recorded.get("category") == "integration", "INTEGRATION_REPORT_SCHEMA_INVALID", "integration report schema/category invalid")
    require_path(recorded.get("source_game_dir"), ctx.source, "INTEGRATION_REPORT_SOURCE_MISMATCH", "integration source")
    require_path(recorded.get("staging_game_dir"), ctx.staging, "INTEGRATION_REPORT_STAGING_MISMATCH", "integration staging")
    require_path(recorded.get("target_game_dir"), ctx.target, "INTEGRATION_REPORT_TARGET_MISMATCH", "integration target")
    states = evaluate(ctx)
    expected_by_name = {state.name: state for state in states}
    checks = recorded.get("checks")
    require(isinstance(checks, list) and {row.get("name") for row in checks if isinstance(row, dict)} == set(CHECK_NAMES), "INTEGRATION_CHECK_SET_INVALID", "integration check set is incomplete")
    for row in checks:
        require(isinstance(row, dict), "INTEGRATION_CHECK_ROW_INVALID", "integration check row is not an object")
        name = row["name"]
        state = expected_by_name[name]
        expected_status = PASS if not state.blockers else "FAIL"
        require(row.get("status") == expected_status, "INTEGRATION_CHECK_STATUS_STALE", f"{name}: recorded={row.get('status')!r}, current={expected_status!r}")
        require(row.get("blockers") == state.blockers, "INTEGRATION_CHECK_BLOCKERS_STALE", f"{name}: recorded blockers differ from current validation")
        require_path(row.get("target_game_dir"), ctx.target, "INTEGRATION_CHECK_TARGET_MISMATCH", name)
        require(row.get("runtime_bundle_sha256") == (ctx.runtime["bundle_sha256"] if ctx.runtime else None), "INTEGRATION_CHECK_RUNTIME_MISMATCH", name)
        artifact = row.get("artifact")
        require(isinstance(artifact, dict), "INTEGRATION_CAPSULE_MISSING", name)
        capsule_path = Path(str(artifact.get("path", ""))).resolve()
        ensure_output_safe(ctx, capsule_path, f"capsule {name}")
        current = stable_file(capsule_path, f"integration capsule {name}")
        require(current["bytes"] == artifact.get("bytes") and current["sha256"] == str(artifact.get("sha256", "")).upper(), "INTEGRATION_CAPSULE_DRIFT", name)
        capsule, _ = read_json(capsule_path, f"integration capsule {name}")
        require(capsule.get("name") == name and capsule.get("status") == expected_status, "INTEGRATION_CAPSULE_STATUS_STALE", name)
        require_path(capsule.get("target_game_dir"), ctx.target, "INTEGRATION_CAPSULE_TARGET_MISMATCH", name)
        require(capsule.get("runtime_bundle_sha256") == (ctx.runtime["bundle_sha256"] if ctx.runtime else None), "INTEGRATION_CAPSULE_RUNTIME_MISMATCH", name)
        require(capsule.get("blockers") == state.blockers, "INTEGRATION_CAPSULE_BLOCKERS_STALE", name)
        require(capsule.get("observations") == state.observations, "INTEGRATION_CAPSULE_OBSERVATIONS_STALE", name)
        for input_row in capsule.get("inputs", []):
            require(isinstance(input_row, dict), "INTEGRATION_INPUT_BINDING_INVALID", name)
            current_input = stable_file(Path(str(input_row.get("path", ""))), str(input_row.get("label", name)))
            require(current_input["bytes"] == input_row.get("bytes") and current_input["sha256"] == str(input_row.get("sha256", "")).upper(), "INTEGRATION_INPUT_DRIFT", f"{name}: {input_row.get('path')}")
        require(capsule.get("inputs") == state.inputs, "INTEGRATION_CAPSULE_INPUT_SET_STALE", name)
    blockers = [item for state in states for item in ({"check": state.name, **row} for row in state.blockers)]
    expected_status = PASS if not blockers and ctx.runtime is not None else NO_GO
    require(recorded.get("status") == expected_status, "INTEGRATION_REPORT_STATUS_STALE", f"recorded={recorded.get('status')!r}, current={expected_status!r}")
    require(recorded.get("exit_code") == (0 if expected_status == PASS else 2), "INTEGRATION_REPORT_EXIT_STALE", "integration report exit_code is stale")
    require(recorded.get("blockers") == blockers, "INTEGRATION_REPORT_BLOCKERS_STALE", "aggregate integration blockers differ from current validation")
    input_config = recorded.get("input_config")
    require(isinstance(input_config, dict), "INTEGRATION_CONFIG_BINDING_MISSING", "integration input config binding missing")
    current_config = stable_file(ctx.config_path, "integration input config")
    require(input_config == current_config, "INTEGRATION_CONFIG_BINDING_DRIFT", "integration input config changed after report generation")
    validator = recorded.get("validator")
    require(isinstance(validator, dict), "INTEGRATION_VALIDATOR_BINDING_MISSING", "integration validator binding missing")
    current_validator = stable_file(Path(__file__), "integration verifier")
    require(validator == current_validator, "INTEGRATION_VALIDATOR_DRIFT", "integration verifier changed after report generation")
    runtime_manifest = recorded.get("runtime_manifest")
    require(isinstance(runtime_manifest, dict), "INTEGRATION_RUNTIME_BINDING_MISSING", "runtime manifest binding missing")
    current_runtime_manifest = stable_file(ctx.runtime_manifest_path, "runtime manifest")
    require(runtime_manifest == current_runtime_manifest, "INTEGRATION_RUNTIME_BINDING_DRIFT", "runtime manifest changed after report generation")
    return {
        "schema": 1,
        "status": "VERIFIED_" + expected_status,
        "exit_code": 0 if expected_status == PASS else 2,
        "read_only": True,
        "report": report_summary,
        "target_game_dir": str(ctx.target),
        "runtime_bundle_sha256": ctx.runtime["bundle_sha256"] if ctx.runtime else None,
        "blockers": blockers,
        "checks": [{"name": state.name, "status": PASS if not state.blockers else "FAIL"} for state in states],
    }, 0 if expected_status == PASS else 2


def validate_bound_report(
    report_path: Path,
    expected_source: Path | None = None,
    expected_staging: Path | None = None,
    expected_target: Path | None = None,
    expected_bundle_sha256: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Revalidate a report using its hash-bound input config.

    This entry point lets the final release gate reject a hand-written PASS
    aggregate without adding another command-line path.  The config itself is
    treated as evidence and must still have the exact recorded byte length and
    SHA-256 before any of its artifact paths are trusted.
    """

    recorded, _ = read_json(report_path.resolve(), "integration acceptance report")
    binding = recorded.get("input_config")
    require(isinstance(binding, dict), "INTEGRATION_CONFIG_BINDING_MISSING", "integration input config binding missing")
    config_path = Path(str(binding.get("path", ""))).resolve()
    current = stable_file(config_path, "integration input config")
    require(current == binding, "INTEGRATION_CONFIG_BINDING_DRIFT", "bound integration input config changed")
    ctx = load_context(config_path)
    if expected_source is not None:
        require(ctx.source == expected_source.resolve(), "INTEGRATION_REPORT_SOURCE_MISMATCH", "bound integration source differs from release gate")
    if expected_staging is not None:
        require(ctx.staging == expected_staging.resolve(), "INTEGRATION_REPORT_STAGING_MISMATCH", "bound integration staging differs from release gate")
    if expected_target is not None:
        require(ctx.target == expected_target.resolve(), "INTEGRATION_REPORT_TARGET_MISMATCH", "bound integration target differs from release gate")
    result, code = validate_existing_report(ctx, report_path.resolve())
    if expected_bundle_sha256 is not None:
        expected = require_hex(expected_bundle_sha256, "INTEGRATION_EXPECTED_BUNDLE_INVALID", "release-gate runtime bundle")
        require(result.get("runtime_bundle_sha256") == expected, "INTEGRATION_REPORT_RUNTIME_MISMATCH", "bound integration runtime differs from release gate")
    return result, code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="input artifact map; contains paths only, never credentials")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", type=Path, help="write a freshly evaluated report")
    mode.add_argument("--verify-report", type=Path, help="revalidate an existing report and every bound input")
    parser.add_argument("--evidence-dir", type=Path, help="override capsule directory from config")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        ctx = load_context(args.config, args.evidence_dir)
        if args.report is not None:
            report, code = build_report(ctx, args.report.resolve())
        else:
            report, code = validate_existing_report(ctx, args.verify_report.resolve())
    except GateError as exc:
        report = {
            "schema": 1,
            "status": NO_GO,
            "exit_code": 1,
            "read_only": True,
            "blockers": [{"code": exc.code, "detail": exc.detail}],
        }
        code = 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
