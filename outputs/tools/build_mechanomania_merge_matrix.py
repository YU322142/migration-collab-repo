from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(r"D:\Trans\migration-audit-work\mechanomania-merge-matrix-20260813")
DEFAULT_UI_RELEASE = Path(
    r"D:\Trans\migration-audit-work\outputs\mechanomania-ui-sanitized-20260813"
    r"\manifests\release.json"
)
DEFAULT_MAP_REPORT = Path(
    r"D:\Trans\migration-audit-work\journeymap-xaero-conversion-20260813"
    r"\conversion-report.json"
)
DEFAULT_PACK_DATA = Path(
    r"D:\Trans\migration-audit-work\integration-pack-audit-20260813\overrides\kubejs\data"
)
DEFAULT_VANILLA_CLIENT = Path(
    r"D:\D\Tools\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\libraries"
    r"\com\mojang\minecraft\1.21.1\minecraft-1.21.1-client.jar"
)

JOURNEYMAP_ID = "journeymap"
XAERO_IDS = {"xaerominimap", "xaeroworldmap"}
MIGRATION_SENSITIVE_IDS = {
    "computercraft",
    "create_dragons_plus",
    "create_enchantment_industry",
    "kaleidoscope_cookery",
    "kaleidoscope_tavern",
}


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    merge_audit: Path
    pack_input: Path
    ui_release: Path
    map_report: Path
    terrain_plan: Path
    terrain_empty_audit: Path
    pack_data_root: Path
    vanilla_client_jar: Path
    generated_at_utc: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AuditError(f"Missing required JSON input: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Invalid JSON input {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuditError(f"JSON root must be an object: {path}")
    return data


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def normalized_hash(value: Any) -> str:
    return str(value or "").strip().upper()


def row_index(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("file") or "")
        if name:
            output[name] = row
    return output


def collect_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from collect_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from collect_strings(child)


def artifact(
    file_name: str,
    source: str,
    indexes: dict[str, dict[str, dict[str, Any]]],
    *,
    external_path: Path | None = None,
) -> dict[str, Any]:
    if source == "UI_SANITIZED":
        if external_path is None or not external_path.is_file():
            raise AuditError(f"Missing sanitized UI artifact: {external_path}")
        return {
            "file": file_name,
            "source": source,
            "path": str(external_path),
            "bytes": external_path.stat().st_size,
            "sha256": sha256(external_path),
        }
    row = indexes.get(source, {}).get(file_name)
    if row is None:
        raise AuditError(f"No {source} metadata row for selected artifact {file_name}")
    return {
        "file": file_name,
        "source": source,
        "path": row.get("path"),
        "bytes": row.get("bytes"),
        "sha256": normalized_hash(row.get("sha256")),
    }


def placement_for_pack_files(
    files: list[str], pack_rows: dict[str, dict[str, Any]]
) -> tuple[str, bool]:
    sides: set[str] = set()
    metadata_unknown = False
    for file_name in files:
        row = pack_rows.get(file_name)
        if row is None:
            metadata_unknown = True
            continue
        declared = {str(value).upper() for value in row.get("declared_dependency_sides") or []}
        fabric_environment = str(row.get("fabric_environment") or "").lower()
        if fabric_environment == "client":
            declared.add("CLIENT")
        if not declared:
            metadata_unknown = True
        sides.update(declared)
    if sides and sides <= {"CLIENT"} and not metadata_unknown:
        return "CLIENT_ONLY", False
    if metadata_unknown:
        return "BOTH_PROVISIONAL", True
    return "BOTH", False


def build_worldgen_evidence(inputs: Inputs) -> dict[str, Any]:
    target_noise = (
        inputs.pack_data_root
        / "minecraft/worldgen/noise_settings/overworld.json"
    )
    target_dimension = inputs.pack_data_root / "minecraft/dimension/overworld.json"
    density_root = (
        inputs.pack_data_root
        / "minecraft/worldgen/density_function/overworld/noise_router"
    )
    for required in (target_noise, target_dimension):
        if not required.is_file():
            raise AuditError(f"Missing Mechanomania world-generation input: {required}")
    if not inputs.vanilla_client_jar.is_file():
        raise AuditError(f"Missing vanilla 1.21.1 client JAR: {inputs.vanilla_client_jar}")

    with zipfile.ZipFile(inputs.vanilla_client_jar) as archive:
        vanilla_raw = archive.read("data/minecraft/worldgen/noise_settings/overworld.json")
    vanilla = json.loads(vanilla_raw)
    target = read_json(target_noise)
    dimension = read_json(target_dimension)

    tectonic_references: set[str] = set()
    density_files = 0
    if density_root.is_dir():
        for path in sorted(density_root.glob("*.json")):
            density_files += 1
            density = read_json(path)
            tectonic_references.update(
                value for value in collect_strings(density) if value.startswith("tectonic:")
            )

    biome_rows = (
        dimension.get("generator", {})
        .get("biome_source", {})
        .get("biomes", [])
    )
    unique_biomes = sorted(
        {
            str(row.get("biome"))
            for row in biome_rows
            if isinstance(row, dict) and row.get("biome")
        }
    )
    vanilla_noise = vanilla.get("noise") or {}
    target_noise_shape = target.get("noise") or {}
    material_difference = bool(
        vanilla_noise != target_noise_shape
        or vanilla.get("surface_rule") != target.get("surface_rule")
        or tectonic_references
    )
    return {
        "vanilla_1_21_1": {
            "client_jar": str(inputs.vanilla_client_jar),
            "client_jar_sha256": sha256(inputs.vanilla_client_jar),
            "noise_settings_entry": "data/minecraft/worldgen/noise_settings/overworld.json",
            "noise_settings_bytes": len(vanilla_raw),
            "noise_settings_sha256": hashlib.sha256(vanilla_raw).hexdigest().upper(),
            "noise": vanilla_noise,
        },
        "mechanomania": {
            "noise_settings": str(target_noise),
            "noise_settings_bytes": target_noise.stat().st_size,
            "noise_settings_sha256": sha256(target_noise),
            "noise": target_noise_shape,
            "default_block_equal_to_vanilla": target.get("default_block")
            == vanilla.get("default_block"),
            "default_fluid_equal_to_vanilla": target.get("default_fluid")
            == vanilla.get("default_fluid"),
            "surface_rule_equal_to_vanilla": target.get("surface_rule")
            == vanilla.get("surface_rule"),
            "overworld_dimension": str(target_dimension),
            "overworld_dimension_bytes": target_dimension.stat().st_size,
            "overworld_dimension_sha256": sha256(target_dimension),
            "multi_noise_biome_rows": len(biome_rows),
            "unique_biomes": unique_biomes,
            "noise_router_density_files_scanned": density_files,
            "tectonic_density_references": sorted(tectonic_references),
        },
        "material_generator_difference": material_difference,
        "conclusion": (
            "The old 1.21.1 generator and the Mechanomania/Tectonic generator are "
            "materially different; a larger vanilla pre-generation radius alone does not "
            "prove a continuous boundary."
            if material_difference
            else "No material generator difference was detected by this static comparison."
        ),
    }


def build_report(inputs: Inputs) -> dict[str, Any]:
    merge = read_json(inputs.merge_audit)
    pack_input = read_json(inputs.pack_input)
    ui_release = read_json(inputs.ui_release)
    map_report = read_json(inputs.map_report)
    terrain_plan = read_json(inputs.terrain_plan)
    terrain_empty = read_json(inputs.terrain_empty_audit)

    if merge.get("status") != "PASS":
        raise AuditError("Upstream mod merge audit is not PASS")
    if map_report.get("status") != "STATIC_VALIDATION_PASSED":
        raise AuditError("JourneyMap to Xaero report is not STATIC_VALIDATION_PASSED")
    if terrain_empty.get("status") != "PASS":
        raise AuditError("Protected terrain emptiness audit is not PASS")
    if terrain_plan.get("status") not in {"READY_TO_PREGENERATE", "PASS"}:
        raise AuditError("Vanilla terrain protection plan is not ready")

    source_zip = Path(str(pack_input.get("source_zip") or ""))
    if not source_zip.is_file():
        raise AuditError(f"Mechanomania source ZIP is missing: {source_zip}")
    actual_pack_sha = sha256(source_zip)
    if actual_pack_sha != normalized_hash(pack_input.get("source_sha256")):
        raise AuditError("Mechanomania source ZIP hash does not match the source lock")

    pack_rows = row_index(merge.get("pack_rows") or [])
    base_server_rows = row_index(merge.get("base_server_rows") or [])
    base_client_rows = row_index(merge.get("base_client_rows") or [])
    indexes = {
        "PACK": pack_rows,
        "BASE_SERVER": base_server_rows,
        "BASE_CLIENT": base_client_rows,
    }

    ui_manifest_dir = inputs.ui_release.parent
    selected_c6c_rel = str(ui_release.get("selected_c6c") or "")
    selected_c6c_path = ui_manifest_dir.parent / selected_c6c_rel
    selected_c6c_hash = sha256(selected_c6c_path)
    if selected_c6c_hash != normalized_hash(ui_release.get("selected_c6c_sha256")):
        raise AuditError("Sanitized C6C hash does not match UI release manifest")
    if any(
        ui_release.get(flag) is not False
        for flag in (
            "runtime_started",
            "production_modified",
            "staging_modified",
            "prism_modified",
        )
    ):
        raise AuditError("UI sanitization manifest reports an out-of-scope mutation")

    matrix: list[dict[str, Any]] = []
    side_unknown_ids: list[str] = []
    selected_server: dict[tuple[str, str, str], dict[str, Any]] = {}
    selected_client: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add_selected(side: str, record: dict[str, Any]) -> None:
        key = (record["source"], record["file"], record["sha256"])
        target = selected_server if side == "server" else selected_client
        target[key] = record

    for upstream in merge.get("matrix") or []:
        mod_id = str(upstream.get("mod_id") or "")
        classification = str(upstream.get("classification") or "")
        pack_files = list(upstream.get("pack_files") or [])
        base_server_files = list(upstream.get("base_server_files") or [])
        base_client_files = list(upstream.get("base_client_files") or [])
        selected_server_files: list[str] = []
        selected_client_files: list[str] = []
        excluded_files: list[str] = []
        source = ""
        reason = ""
        runtime_gate: str | None = None

        if mod_id == JOURNEYMAP_ID:
            source = "EXCLUDED"
            excluded_files = sorted(set(base_server_files + base_client_files + pack_files))
            reason = "Replaced by Xaero Minimap + Xaero World Map; stale JourneyMap config must also be removed."
        elif mod_id == "c6c":
            source = "UI_SANITIZED"
            selected_server_files = [selected_c6c_path.name]
            selected_client_files = [selected_c6c_path.name]
            excluded_files = sorted(set(pack_files))
            reason = (
                "Keep full C6C gameplay through the purified full JAR; exclude the original "
                "full and lite duplicates because both contain title/branding/hosting hooks."
            )
            record = artifact(
                selected_c6c_path.name,
                "UI_SANITIZED",
                indexes,
                external_path=selected_c6c_path,
            )
            add_selected("server", record)
            add_selected("client", record)
        elif mod_id == "byepregen":
            chosen = [name for name in pack_files if "1.0.7" in name]
            if len(chosen) != 1:
                raise AuditError("Expected exactly one byepregen 1.0.7 candidate")
            source = "PACK"
            selected_server_files = chosen
            selected_client_files = chosen
            excluded_files = sorted(set(pack_files) - set(chosen))
            reason = "Resolve duplicate mod ID by selecting pack version 1.0.7 and excluding 1.0.0."
            runtime_gate = "Confirm dedicated-server side compatibility during the runtime gate."
            side_unknown_ids.append(mod_id)
            record = artifact(chosen[0], "PACK", indexes)
            add_selected("server", record)
            add_selected("client", record)
        elif classification == "PACK_AND_BASE":
            source = "BASE"
            selected_server_files = base_server_files
            selected_client_files = base_client_files
            excluded_files = pack_files
            reason = (
                "Keep byte-identical base artifact as the single canonical copy."
                if upstream.get("same_bytes_as_base")
                else "Keep the current migration baseline artifact; it is newer and/or carries migration compatibility work."
            )
            if mod_id in MIGRATION_SENSITIVE_IDS:
                reason += " This mod ID is migration-sensitive and must not be downgraded to the pack copy."
            for name in selected_server_files:
                add_selected("server", artifact(name, "BASE_SERVER", indexes))
            for name in selected_client_files:
                add_selected("client", artifact(name, "BASE_CLIENT", indexes))
        elif classification == "BASE_ONLY":
            source = "BASE"
            selected_server_files = base_server_files
            selected_client_files = base_client_files
            reason = "Retain existing migration/backport gameplay and safety compatibility."
            for name in selected_server_files:
                add_selected("server", artifact(name, "BASE_SERVER", indexes))
            for name in selected_client_files:
                add_selected("client", artifact(name, "BASE_CLIENT", indexes))
        elif classification == "PACK_NEW":
            source = "PACK"
            placement, unresolved = placement_for_pack_files(pack_files, pack_rows)
            selected_client_files = pack_files
            if placement != "CLIENT_ONLY":
                selected_server_files = pack_files
            reason = (
                "Add new Mechanomania gameplay/content."
                if placement != "CLIENT_ONLY"
                else "Add the pack's explicitly client-side feature."
            )
            if unresolved:
                runtime_gate = (
                    "Side metadata is incomplete; provisional BOTH placement must pass the "
                    "dedicated-server classloading/dependency gate before release."
                )
                side_unknown_ids.append(mod_id)
            for name in selected_server_files:
                add_selected("server", artifact(name, "PACK", indexes))
            for name in selected_client_files:
                add_selected("client", artifact(name, "PACK", indexes))
        else:
            raise AuditError(f"Unknown matrix classification {classification!r} for {mod_id}")

        matrix.append(
            {
                "mod_id": mod_id,
                "upstream_classification": classification,
                "selected_source": source,
                "selected_server_files": selected_server_files,
                "selected_client_files": selected_client_files,
                "excluded_files": excluded_files,
                "reason": reason,
                "runtime_gate": runtime_gate,
            }
        )

    # Connector and KotlinForForge are loader/runtime artifacts without normal mod IDs in the
    # upstream metadata view, so they are resolved explicitly instead of silently disappearing.
    special_specs = (
        ("loader:connector", "connector-", "beta.16", "beta.14"),
        ("loader:kotlinforforge", "kotlinforforge-", "5.12.0", "5.11.0"),
    )
    for synthetic_id, prefix, selected_marker, excluded_marker in special_specs:
        selected_s = [name for name in base_server_rows if name.lower().startswith(prefix)]
        selected_c = [name for name in base_client_rows if name.lower().startswith(prefix)]
        excluded = [name for name in pack_rows if name.lower().startswith(prefix)]
        if len(selected_s) != 1 or len(selected_c) != 1 or len(excluded) != 1:
            raise AuditError(f"Cannot uniquely resolve metadata-less runtime artifact {synthetic_id}")
        if selected_marker not in selected_s[0] or excluded_marker not in excluded[0]:
            raise AuditError(f"Unexpected version candidates for {synthetic_id}")
        matrix.append(
            {
                "mod_id": synthetic_id,
                "upstream_classification": "METADATA_LESS_RUNTIME",
                "selected_source": "BASE",
                "selected_server_files": selected_s,
                "selected_client_files": selected_c,
                "excluded_files": excluded,
                "reason": "Keep the newer current migration baseline runtime artifact.",
                "runtime_gate": None,
            }
        )
        add_selected("server", artifact(selected_s[0], "BASE_SERVER", indexes))
        add_selected("client", artifact(selected_c[0], "BASE_CLIENT", indexes))

    worldgen = build_worldgen_evidence(inputs)
    terrain_policy = terrain_plan.get("policy") or {}
    center = terrain_empty.get("center") or {}
    audited_radius = int(terrain_empty.get("radius_blocks") or 0)
    core_radius = int(terrain_policy.get("core_radius_blocks") or 0)
    frozen_radius = int(terrain_policy.get("frozen_radius_blocks") or 0)
    if (int(center.get("x") or 0), int(center.get("z") or 0), core_radius) != (
        10192,
        -1574,
        1000,
    ):
        raise AuditError("Protected terrain core does not match x=10192 z=-1574 r=1000")
    if audited_radius != frozen_radius or audited_radius < core_radius:
        raise AuditError(
            "Protected terrain emptiness audit does not cover the planned freeze radius"
        )

    map_execution = map_report.get("execution") or {}
    if any(
        map_execution.get(flag) is not False
        for flag in ("minecraft_launched", "prism_instance_modified", "release_modified")
    ):
        raise AuditError("Map conversion report records an out-of-scope mutation")
    map_source_hash = normalized_hash(
        (map_report.get("source") or {}).get("zip_sha256")
    )
    expected_map_hash = normalized_hash(
        (pack_input.get("map_policy") or {}).get("journeymap_export_sha256")
    )
    if map_source_hash != expected_map_hash:
        raise AuditError("JourneyMap source hash does not match the pack integration lock")

    selected_server_records = sorted(
        selected_server.values(), key=lambda row: (row["file"].lower(), row["source"])
    )
    selected_client_records = sorted(
        selected_client.values(), key=lambda row: (row["file"].lower(), row["source"])
    )
    all_selected_files = {
        row["file"] for row in selected_server_records + selected_client_records
    }
    if any("journeymap" in name.lower() for name in all_selected_files):
        raise AuditError("JourneyMap leaked into the selected artifact plan")
    for xaero_id in XAERO_IDS:
        xaero_row = next((row for row in matrix if row["mod_id"] == xaero_id), None)
        if not xaero_row or not xaero_row["selected_client_files"]:
            raise AuditError(f"Required map mod was not selected: {xaero_id}")

    static_checks = [
        {"id": "UPSTREAM_MOD_AUDIT", "status": "PASS"},
        {"id": "SOURCE_ZIP_HASH", "status": "PASS", "sha256": actual_pack_sha},
        {"id": "UI_SANITIZATION_LOCK", "status": "PASS", "sha256": selected_c6c_hash},
        {"id": "JOURNEYMAP_TO_XAERO_STATIC", "status": "PASS"},
        {"id": "PROTECTED_AREA_EMPTY_AUDIT", "status": "PASS"},
        {"id": "NO_SOURCE_STAGING_RELEASE_MUTATION", "status": "PASS"},
    ]
    blockers = [
        {
            "id": "VANILLA_PROTECTED_AREA_NOT_PREGENERATED",
            "severity": "RELEASE_BLOCKER",
            "reason": (
                "The isolated vanilla-compatible freeze is planned but the upstream terrain "
                "plan is still READY_TO_PREGENERATE, not an imported and verified result."
            ),
        },
        {
            "id": "TECTONIC_BOUNDARY_CONTINUITY_NOT_PROVEN",
            "severity": "RELEASE_BLOCKER",
            "reason": worldgen["conclusion"],
        },
        {
            "id": "PROVISIONAL_MOD_SIDES_NOT_RUNTIME_VALIDATED",
            "severity": "RELEASE_BLOCKER",
            "reason": (
                f"{len(set(side_unknown_ids))} mod IDs have incomplete side metadata and require "
                "dedicated-server/client dependency validation."
            ),
        },
        {
            "id": "FULL_RUNTIME_AND_JOIN_GATES_NOT_RUN",
            "severity": "RELEASE_BLOCKER",
            "reason": "This task intentionally performed no Java/Minecraft launch.",
        },
    ]

    report = {
        "schema": 1,
        "generated_at_utc": inputs.generated_at_utc,
        "scope": "Mechanomania full-gameplay static merge matrix; no Java launch and no source/staging/release mutation",
        "static_audit_status": "PASS",
        "release_decision": "BLOCKED_FAIL_CLOSED",
        "source_locks": {
            "mechanomania_zip": {
                "path": str(source_zip),
                "bytes": source_zip.stat().st_size,
                "sha256": actual_pack_sha,
                "name": pack_input.get("pack_name"),
                "version": pack_input.get("pack_version"),
                "minecraft": pack_input.get("minecraft"),
                "loader": pack_input.get("loader"),
            },
            "inputs": [
                {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in (
                    inputs.merge_audit,
                    inputs.pack_input,
                    inputs.ui_release,
                    inputs.map_report,
                    inputs.terrain_plan,
                    inputs.terrain_empty_audit,
                )
            ],
        },
        "invariants": {
            "old_world_terrain": (
                "Every already-existing server chunk is authoritative and immutable: no deletion, "
                "replacement, retrogen, re-seeding, region reset, or new-generator rewrite."
            ),
            "protected_area": {
                "dimension": "minecraft:overworld",
                "center_x": 10192,
                "center_z": -1574,
                "core_radius_blocks": 1000,
                "planned_vanilla_freeze_radius_blocks": terrain_policy.get(
                    "frozen_radius_blocks"
                ),
                "semantics": terrain_policy.get("core_semantics"),
            },
            "full_gameplay": (
                "Keep the Mechanomania gameplay/data/resource/KubeJS/worldgen layers except the "
                "explicit title/branding/main-menu hosting exclusions and resolved duplicates."
            ),
            "server_configuration": (
                "Do not change production server.properties, ports, RCON, query, seed, or world identity."
            ),
            "future_extensibility": (
                "The matrix is a provenance/selection manifest, not a permanent allowlist. Future "
                "mods and OTA layers remain additive after dependency/registry/runtime gates."
            ),
        },
        "selection_policy": {
            "pack_new": "include; explicit client-only stays client-only; incomplete side metadata is provisional and gated",
            "overlap_same_bytes": "retain one canonical base copy",
            "overlap_different": "retain current migration baseline; never downgrade migration-sensitive artifacts",
            "base_only": "retain migration/backport/safety gameplay except JourneyMap",
            "duplicate_byepregen": "select 1.0.7; exclude 1.0.0",
            "duplicate_c6c": "select sanitized full 1.2.5.1; exclude original full and lite",
            "maps": "remove JourneyMap and stale config; select Xaero Minimap + Xaero World Map and converted data",
            "title_and_hosting": "exclude pack title/icon/branding and main-menu hosting/server-opening entry only",
            "extension_model": {
                "hard_mod_allowlist": False,
                "registry_stripping": False,
                "future_mods_allowed": True,
                "future_datapacks_allowed": True,
                "mcmodsync_ota_layers_allowed": True,
                "requirements": [
                    "dependency closure",
                    "server/client side classification",
                    "registry compatibility",
                    "two-round runtime/join validation",
                ],
            },
        },
        "ui_sanitization": {
            "status": "PASS_STATIC",
            "selected_c6c": str(selected_c6c_path),
            "selected_c6c_sha256": selected_c6c_hash,
            "policy": ui_release.get("policy"),
            "overlays": ui_release.get("files"),
        },
        "map_migration": {
            "status": map_report.get("status"),
            "source": map_report.get("source"),
            "target": map_report.get("target"),
            "journeymap": map_report.get("journeymap"),
            "waypoints": map_report.get("waypoints"),
            "tiles": map_report.get("tiles"),
            "server_identity": map_report.get("server"),
            "note": (
                "The conversion report's port is identity evidence only; no production server "
                "configuration is changed by this matrix."
            ),
        },
        "terrain_and_worldgen": {
            "status": "BLOCKED_FAIL_CLOSED",
            "old_existing_chunks_policy": "PRESERVE_ALL",
            "protected_area_empty_audit": {
                "status": terrain_empty.get("status"),
                "selected_chunk_count": terrain_empty.get("selected_chunk_count"),
                "selected_region_count": terrain_empty.get("selected_region_count"),
            },
            "vanilla_freeze_plan_status": terrain_plan.get("status"),
            "worldgen_evidence": worldgen,
            "release_gate": [
                "Generate the protected vanilla-compatible chunks in an isolated disposable world with the original seed.",
                "Import only the explicitly selected new chunks; prove every pre-existing chunk remains unchanged.",
                "Test every old/new and vanilla/Tectonic boundary segment for heightmap, fluids, structures, and visible seams.",
                "If continuity is not demonstrated, keep the old terrain and prevent generation across the unsafe boundary.",
                "Only genuinely ungenerated chunks outside the accepted boundary may use the full Mechanomania worldgen stack.",
            ],
        },
        "counts": {
            "upstream_matrix_mod_ids": len(merge.get("matrix") or []),
            "resolved_matrix_rows": len(matrix),
            "overlap_mod_ids": sum(
                row.get("upstream_classification") == "PACK_AND_BASE" for row in matrix
            ),
            "pack_new_mod_ids": sum(
                row.get("upstream_classification") == "PACK_NEW" for row in matrix
            ),
            "base_only_mod_ids": sum(
                row.get("upstream_classification") == "BASE_ONLY" for row in matrix
            ),
            "side_metadata_runtime_gate_mod_ids": len(set(side_unknown_ids)),
            "selected_server_artifacts": len(selected_server_records),
            "selected_client_artifacts": len(selected_client_records),
        },
        "side_metadata_runtime_gate_mod_ids": sorted(set(side_unknown_ids)),
        "matrix": sorted(matrix, key=lambda row: row["mod_id"]),
        "artifact_selection": {
            "server": selected_server_records,
            "client": selected_client_records,
            "remove_from_both": sorted(
                {
                    name
                    for row in matrix
                    if row["mod_id"] == JOURNEYMAP_ID
                    for name in row["excluded_files"]
                }
            ),
            "remove_paths": ["overrides/config/journeymap-server.toml"],
        },
        "static_checks": static_checks,
        "release_blockers": blockers,
        "execution": {
            "java_started": False,
            "minecraft_started": False,
            "source_modified": False,
            "staging_modified": False,
            "release_modified": False,
            "artifacts_copied": False,
            "output_is_manifest_only": True,
        },
    }
    return report


def markdown_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    blockers = report["release_blockers"]
    overlaps = [
        row for row in report["matrix"] if row["upstream_classification"] == "PACK_AND_BASE"
    ]
    exceptions = [
        row
        for row in report["matrix"]
        if row["mod_id"] in {"byepregen", "c6c", "journeymap", *XAERO_IDS}
        or row["mod_id"].startswith("loader:")
    ]
    worldgen = report["terrain_and_worldgen"]["worldgen_evidence"]
    vanilla_noise = worldgen["vanilla_1_21_1"]["noise"]
    target_noise = worldgen["mechanomania"]["noise"]

    lines = [
        "# Mechanomania Ultimate Aeronautics 合并矩阵（静态审计）",
        "",
        f"- 静态审计：**{report['static_audit_status']}**",
        f"- 生产放行：**{report['release_decision']}**",
        "- 本次没有启动 Java/Minecraft，也没有修改 source、converted-staging 或现有 release。",
        "- 这个 `PASS` 只代表合并矩阵自洽，不代表可以直接开服。",
        "",
        "## 不可破坏的约束",
        "",
        f"- 旧地形：{report['invariants']['old_world_terrain']}",
        "- 保护区：主世界 `(10192, -1574)` 半径 `1000` 格必须保持原版兼容地形；计划冻结半径为 "
        f"`{report['invariants']['protected_area']['planned_vanilla_freeze_radius_blocks']}` 格。",
        f"- 原服务器配置：{report['invariants']['server_configuration']}",
        f"- 扩展性：{report['invariants']['future_extensibility']}",
        "",
        "## 当前结论",
        "",
        f"- 上游模组 ID：{counts['upstream_matrix_mod_ids']}；矩阵行：{counts['resolved_matrix_rows']}。",
        f"- 重叠模组：{counts['overlap_mod_ids']}；整合包新增：{counts['pack_new_mod_ids']}；原迁移包独有：{counts['base_only_mod_ids']}。",
        f"- 最终静态选择：服务端 {counts['selected_server_artifacts']} 个唯一工件；客户端 {counts['selected_client_artifacts']} 个唯一工件。",
        f"- {counts['side_metadata_runtime_gate_mod_ids']} 个模组 ID 的 side 元数据不完整，已按 provisional BOTH 记录，但生产门禁保持关闭。",
        "",
        "## 明确取舍",
        "",
        "| ID | 选择 | 排除 | 原因 |",
        "|---|---|---|---|",
    ]
    for row in exceptions:
        chosen = ", ".join(
            sorted(set(row["selected_server_files"] + row["selected_client_files"]))
        ) or "—"
        excluded = ", ".join(row["excluded_files"]) or "—"
        lines.append(f"| `{row['mod_id']}` | {chosen} | {excluded} | {row['reason']} |")

    lines.extend(
        [
            "",
            "## 19 项重叠模组策略",
            "",
            "重叠项统一保留当前迁移基线：字节相同则只留一个基线副本；字节不同则不降级，尤其不覆盖已做迁移兼容的 Create、CC、Cookery/Tavern 等工件。",
            "",
            "| ID | 基线选择 | 整合包副本 |",
            "|---|---|---|",
        ]
    )
    for row in overlaps:
        selected = ", ".join(
            sorted(set(row["selected_server_files"] + row["selected_client_files"]))
        )
        lines.append(f"| `{row['mod_id']}` | {selected} | {', '.join(row['excluded_files'])} |")

    lines.extend(
        [
            "",
            "## UI 与地图",
            "",
            "- C6C 使用净化后的完整 1.2.5.1 JAR；玩法/数据保留，原始 full 与 lite 均排除。",
            "- 排除整合包标题、图标、品牌和主菜单“开服/服务器托管”入口；Iris 初始化钩子等非 UI 玩法依赖保留。",
            "- JourneyMap 从客户端与服务端选择中移除，并删除陈旧的 `overrides/config/journeymap-server.toml`。",
            "- 选择 Xaero Minimap + Xaero World Map；地图和 waypoint 转换静态报告已通过，但仍需要真实客户端加载验收。",
            "- 转换报告里的端口仅用于 Xaero 身份证据，本矩阵不修改生产端口或 `server.properties`。",
            "",
            "## 为什么地形门禁仍然关闭",
            "",
            f"- 原版 1.21.1 Overworld noise：`min_y={vanilla_noise.get('min_y')}`、`height={vanilla_noise.get('height')}`。",
            f"- Mechanomania/Tectonic noise：`min_y={target_noise.get('min_y')}`、`height={target_noise.get('height')}`。",
            f"- surface rule 相同：`{worldgen['mechanomania']['surface_rule_equal_to_vanilla']}`；Tectonic density 引用数：`{len(worldgen['mechanomania']['tectonic_density_references'])}`。",
            "- 因此“多预生成一圈”只能保护圈内，不能证明旧生成器与 Tectonic 在边界处没有断崖、液体切面或结构截断。",
            "- 所有已有服务器区块先逐块保留；保护区只允许从隔离原版生成结果导入此前不存在的区块；连续性证据不足时阻止跨边界生成。",
            "",
            "## 发布阻断项",
            "",
        ]
    )
    for blocker in blockers:
        lines.append(f"- `{blocker['id']}`：{blocker['reason']}")

    lines.extend(
        [
            "",
            "## 未来扩展与 OTA",
            "",
            "- 该矩阵不是永久模组白名单，不会锁死后续添加模组、数据包或资源包。",
            "- MCModSync OTA 可以追加/替换独立兼容层；每一层仍需依赖闭包、注册表、side 和双轮进服门禁。",
            "- 不做 registry stripping，不用“未知模组一律拒绝”的硬编码；新工件只需新增带哈希和来源的矩阵行。",
            "",
            "详细的逐 ID 选择、哈希、来源、世界生成证据和门禁见 `merge-matrix.json`。",
            "",
        ]
    )
    return "\n".join(lines)


def readme(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Mechanomania merge-matrix audit package",
            "",
            "This directory is manifest-only. It contains no copied world, JAR, cache, or candidate server.",
            "",
            "- `merge-matrix.json`: machine-readable full selection and fail-closed gates.",
            "- `merge-matrix.md`: concise Chinese review document.",
            "- `SHA256SUMS.txt`: package file hashes.",
            "",
            f"Static audit: {report['static_audit_status']}",
            f"Release decision: {report['release_decision']}",
            "",
            "Exit code 0 from the builder means the static report was generated and validated. It does not override release blockers.",
            "",
        ]
    )


def write_package(output_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "merge-matrix.json"
    markdown_path = output_dir / "merge-matrix.md"
    readme_path = output_dir / "README.md"
    atomic_write_json(report_path, report)
    atomic_write_text(markdown_path, markdown_report(report))
    atomic_write_text(readme_path, readme(report))
    files = [report_path, markdown_path, readme_path]
    sums = "".join(f"{sha256(path)} *{path.name}\n" for path in sorted(files))
    sums_path = output_dir / "SHA256SUMS.txt"
    atomic_write_text(sums_path, sums)
    return {
        "output_dir": str(output_dir),
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in [*files, sums_path]
        },
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--merge-audit",
        type=Path,
        default=WORKSPACE / "outputs/mechanomania-mod-merge-audit-20260813.json",
    )
    cli.add_argument(
        "--pack-input",
        type=Path,
        default=WORKSPACE / "outputs/mechanomania-pack-audit-input-20260813.json",
    )
    cli.add_argument("--ui-release", type=Path, default=DEFAULT_UI_RELEASE)
    cli.add_argument("--map-report", type=Path, default=DEFAULT_MAP_REPORT)
    cli.add_argument(
        "--terrain-plan",
        type=Path,
        default=WORKSPACE / "outputs/vanilla-terrain-protection-plan-20260813.json",
    )
    cli.add_argument(
        "--terrain-empty-audit",
        type=Path,
        default=WORKSPACE / "outputs/vanilla-terrain-protection-empty-audit-20260813.json",
    )
    cli.add_argument("--pack-data-root", type=Path, default=DEFAULT_PACK_DATA)
    cli.add_argument("--vanilla-client-jar", type=Path, default=DEFAULT_VANILLA_CLIENT)
    cli.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    cli.add_argument(
        "--generated-at-utc",
        default=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    inputs = Inputs(
        merge_audit=args.merge_audit,
        pack_input=args.pack_input,
        ui_release=args.ui_release,
        map_report=args.map_report,
        terrain_plan=args.terrain_plan,
        terrain_empty_audit=args.terrain_empty_audit,
        pack_data_root=args.pack_data_root,
        vanilla_client_jar=args.vanilla_client_jar,
        generated_at_utc=args.generated_at_utc,
    )
    try:
        report = build_report(inputs)
        package = write_package(args.output_dir, report)
    except AuditError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {
                "status": report["static_audit_status"],
                "release_decision": report["release_decision"],
                "package": package,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
