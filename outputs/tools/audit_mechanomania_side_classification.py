from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_UPSTREAM = WORKSPACE / "outputs/mechanomania-mod-merge-audit-20260813.json"
DEFAULT_JSON = WORKSPACE / "outputs/mechanomania-side-classification-20260813.json"
DEFAULT_MD = WORKSPACE / "outputs/mechanomania-side-classification-20260813.md"
VALIDATOR = WORKSPACE / "outputs/tools/validate_mechanomania_side_classification.py"
TESTS = WORKSPACE / "outputs/tools/test_audit_mechanomania_side_classification.py"

TARGET_IDS = (
    "byepregen",
    "efficient_hashing",
    "fastrecipesearch",
    "hoporp",
    "jecharacters",
    "mousetweaks",
    "mr_dungeons_andtavernsancientcityoverhaul",
    "mr_epic_structuresvillages",
    "mr_lukis_crazychambers",
    "rhino",
    "yet_another_config_lib_v3",
)

EXPECTED_FILES = {
    "byepregen": "byepregen-1.0.7.jar",
    "efficient_hashing": "efficient_hashing-neoforge-1.0.0+1.21.1-mod.jar",
    "fastrecipesearch": "fastrecipesearch-1.21.1-26.2-neoforge.jar",
    "hoporp": "HopoBetterRuinedPortals-[1.21.1-1.21.3]-1.4.4b.jar",
    "jecharacters": "jecharacters-1.21-neoforge-4.5.24.jar",
    "mousetweaks": "MouseTweaks-neoforge-mc1.21-2.26.1.jar",
    "mr_dungeons_andtavernsancientcityoverhaul": "DnT-ancient-city-overhaul-v2 [NeoForge].jar",
    "mr_epic_structuresvillages": "Epic Villages 1.3.0 (1.21+).jar",
    "mr_lukis_crazychambers": "lukis-crazy-chambers-1.0.2.jar",
    "rhino": "rhino-2101.2.7-build.85.jar",
    "yet_another_config_lib_v3": "yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar",
}

PURE_DATA_IDS = {
    "hoporp",
    "mr_dungeons_andtavernsancientcityoverhaul",
    "mr_epic_structuresvillages",
    "mr_lukis_crazychambers",
}

EXPECTED_CLASSIFICATIONS = {
    "byepregen": "BOTH",
    "efficient_hashing": "BOTH",
    "fastrecipesearch": "BOTH",
    "hoporp": "SERVER_ONLY",
    "jecharacters": "CLIENT_ONLY",
    "mousetweaks": "CLIENT_ONLY",
    "mr_dungeons_andtavernsancientcityoverhaul": "BOTH",
    "mr_epic_structuresvillages": "BOTH",
    "mr_lukis_crazychambers": "BOTH",
    "rhino": "BOTH",
    "yet_another_config_lib_v3": "CLIENT_ONLY",
}

CLIENT_SYMBOL_PREFIXES = (
    "net/minecraft/client/",
    "net/neoforged/neoforge/client/",
    "net/neoforged/fml/event/lifecycle/FMLClient",
    "com/mojang/blaze3d/",
    "org/lwjgl/",
)
SERVER_SYMBOL_PREFIXES = (
    # `net.minecraft.server.packs.resources` is shared resource-reload API used by
    # clients too. Keep this list to dedicated/server execution symbols instead
    # of treating the whole historical package name as a physical-side marker.
    "net/minecraft/server/MinecraftServer",
    "net/minecraft/server/ServerResources",
    "net/minecraft/server/commands/",
    "net/minecraft/server/dedicated/",
    "net/minecraft/server/level/",
    "net/minecraft/server/network/",
    "net/minecraft/server/players/",
    "net/neoforged/neoforge/server/",
    "net/neoforged/fml/event/lifecycle/FMLDedicatedServer",
)
SHARED_GAME_SYMBOL_PREFIXES = (
    "net/minecraft/core/",
    "net/minecraft/world/",
    "net/minecraft/resources/",
    "net/minecraft/network/",
    "net/minecraft/commands/",
    "net/neoforged/neoforge/event/",
)


class AuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    upstream: Path = DEFAULT_UPSTREAM
    generated_at_utc: str | None = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise AuditError(f"Cannot read JSON {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"Expected a JSON object: {path}")
    return value


def clean_toml(raw: bytes) -> dict[str, Any]:
    return tomllib.loads(raw.lstrip(b"\xef\xbb\xbf").decode("utf-8"))


def class_utf8_constants(raw: bytes) -> list[str]:
    """Return class-file CONSTANT_Utf8 values without loading Java bytecode."""
    if len(raw) < 10 or raw[:4] != b"\xca\xfe\xba\xbe":
        raise AuditError("Invalid class-file magic")
    count = struct.unpack_from(">H", raw, 8)[0]
    offset = 10
    index = 1
    values: list[str] = []
    while index < count:
        if offset >= len(raw):
            raise AuditError("Truncated class constant pool")
        tag = raw[offset]
        offset += 1
        if tag == 1:
            if offset + 2 > len(raw):
                raise AuditError("Truncated CONSTANT_Utf8 length")
            length = struct.unpack_from(">H", raw, offset)[0]
            offset += 2
            end = offset + length
            if end > len(raw):
                raise AuditError("Truncated CONSTANT_Utf8 payload")
            values.append(raw[offset:end].decode("utf-8", errors="replace"))
            offset = end
        elif tag in {3, 4}:
            offset += 4
        elif tag in {5, 6}:
            offset += 8
            index += 1
        elif tag in {7, 8, 16, 19, 20}:
            offset += 2
        elif tag in {9, 10, 11, 12, 17, 18}:
            offset += 4
        elif tag == 15:
            offset += 3
        else:
            raise AuditError(f"Unsupported class constant-pool tag {tag}")
        if offset > len(raw):
            raise AuditError("Truncated class constant-pool entry")
        index += 1
    return values


def matching_symbols(values: Iterable[str], prefixes: tuple[str, ...]) -> list[str]:
    found: set[str] = set()
    for value in values:
        normalized = value.replace(".", "/")
        for prefix in prefixes:
            start = 0
            while True:
                index = normalized.find(prefix, start)
                if index < 0:
                    break
                tail = normalized[index:]
                stop = len(tail)
                for marker in (";", "<", "(", ")", "[", " "):
                    marker_index = tail.find(marker)
                    if marker_index >= 0:
                        stop = min(stop, marker_index)
                found.add(tail[:stop])
                start = index + len(prefix)
    return sorted(found)


def metadata_from_archive(archive: zipfile.ZipFile) -> dict[str, Any]:
    names = archive.namelist()
    lower_to_name = {name.lower(): name for name in names}
    metadata_name = None
    for candidate in ("meta-inf/neoforge.mods.toml", "meta-inf/mods.toml"):
        if candidate in lower_to_name:
            metadata_name = lower_to_name[candidate]
            break
    result: dict[str, Any] = {
        "kind": "NONE",
        "file": None,
        "mod_loader": None,
        "mod_ids": [],
        "dependencies": [],
        "fabric_environment": None,
        "display_test": None,
    }
    if metadata_name is not None:
        parsed = clean_toml(archive.read(metadata_name))
        dependencies: list[dict[str, Any]] = []
        dep_table = parsed.get("dependencies") or {}
        if isinstance(dep_table, dict):
            for owner, entries in dep_table.items():
                if not isinstance(entries, list):
                    continue
                for dep in entries:
                    if not isinstance(dep, dict):
                        continue
                    dependencies.append(
                        {
                            "owner": str(owner),
                            "mod_id": str(dep.get("modId") or ""),
                            "type": str(dep.get("type") or ("required" if dep.get("mandatory") else "optional")),
                            "mandatory": dep.get("mandatory"),
                            "side": str(dep.get("side") or "BOTH").upper(),
                            "version_range": dep.get("versionRange"),
                        }
                    )
        mods = parsed.get("mods") or []
        result.update(
            {
                "kind": "NEOFORGE_TOML",
                "file": metadata_name,
                "mod_loader": parsed.get("modLoader"),
                "mod_ids": sorted(
                    str(mod.get("modId")) for mod in mods if isinstance(mod, dict) and mod.get("modId")
                ),
                "dependencies": dependencies,
                "display_test": next(
                    (mod.get("displayTest") for mod in mods if isinstance(mod, dict) and mod.get("displayTest")),
                    None,
                ),
            }
        )
    fabric_name = lower_to_name.get("fabric.mod.json")
    if fabric_name:
        fabric = json.loads(archive.read(fabric_name).decode("utf-8-sig"))
        result["fabric_environment"] = fabric.get("environment")
        result["fabric_id"] = fabric.get("id")
    return result


def mixins_from_archive(archive: zipfile.ZipFile, metadata: dict[str, Any]) -> dict[str, Any]:
    names = archive.namelist()
    candidates = sorted(
        name
        for name in names
        if name.lower().endswith("mixins.json") or name.lower().endswith(".mixins.json")
    )
    rows: list[dict[str, Any]] = []
    for name in candidates:
        try:
            value = json.loads(archive.read(name).decode("utf-8-sig"))
        except Exception as exc:
            rows.append({"file": name, "parse_error": f"{type(exc).__name__}: {exc}"})
            continue
        if not isinstance(value, dict):
            rows.append({"file": name, "parse_error": "root is not an object"})
            continue
        rows.append(
            {
                "file": name,
                "package": value.get("package"),
                "plugin": value.get("plugin"),
                "common": list(value.get("mixins") or []),
                "client": list(value.get("client") or []),
                "server": list(value.get("server") or []),
                "parse_error": None,
            }
        )
    return {
        "configs": rows,
        "common_count": sum(len(row.get("common") or []) for row in rows),
        "client_count": sum(len(row.get("client") or []) for row in rows),
        "server_count": sum(len(row.get("server") or []) for row in rows),
        "parse_errors": [row for row in rows if row.get("parse_error")],
    }


def inspect_jar(row: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(row.get("path") or ""))
    if not path.is_file():
        raise AuditError(f"Selected JAR is missing: {path}")
    actual_hash = sha256(path)
    upstream_hash = str(row.get("sha256") or "").upper()
    if actual_hash != upstream_hash:
        raise AuditError(f"Selected JAR hash drift for {path.name}")
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise AuditError(f"CRC failure in {path.name}: {bad}")
        names = archive.namelist()
        class_names = sorted(name for name in names if name.endswith(".class"))
        data_files = sorted(name for name in names if name.startswith("data/") and not name.endswith("/"))
        asset_files = sorted(name for name in names if name.startswith("assets/") and not name.endswith("/"))
        metadata = metadata_from_archive(archive)
        mixins = mixins_from_archive(archive, metadata)
        utf8_values: list[str] = []
        class_parse_errors: list[str] = []
        for name in class_names:
            try:
                utf8_values.extend(class_utf8_constants(archive.read(name)))
            except Exception as exc:
                class_parse_errors.append(f"{name}: {type(exc).__name__}: {exc}")
        client_symbols = matching_symbols(utf8_values, CLIENT_SYMBOL_PREFIXES)
        server_symbols = matching_symbols(utf8_values, SERVER_SYMBOL_PREFIXES)
        shared_symbols = matching_symbols(utf8_values, SHARED_GAME_SYMBOL_PREFIXES)
    return {
        "file": path.name,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": actual_hash,
        "archive_crc": "PASS",
        "entry_count": len(names),
        "class_count": len(class_names),
        "data_file_count": len(data_files),
        "asset_file_count": len(asset_files),
        "pure_data_pack": len(class_names) == 0 and len(data_files) > 0,
        "metadata": metadata,
        "mixins": mixins,
        "bytecode": {
            "class_parse_errors": class_parse_errors,
            "client_symbol_count": len(client_symbols),
            "client_symbols_sample": client_symbols[:40],
            "server_symbol_count": len(server_symbols),
            "server_symbols_sample": server_symbols[:40],
            "shared_game_symbol_count": len(shared_symbols),
            "shared_game_symbols_sample": shared_symbols[:40],
        },
        "data_files_sample": data_files[:30],
        "asset_files_sample": asset_files[:20],
    }


def reverse_dependencies(pack_rows: list[dict[str, Any]], target_id: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in pack_rows:
        for dependency in row.get("dependencies") or []:
            if str(dependency.get("mod_id") or "") != target_id:
                continue
            output.append(
                {
                    "dependent_file": row.get("file"),
                    "dependent_mod_ids": list(row.get("mod_ids") or []),
                    "type": dependency.get("type"),
                    "mandatory": dependency.get("mandatory"),
                    "side": str(dependency.get("side") or "BOTH").upper(),
                    "version_range": dependency.get("version_range"),
                }
            )
    return sorted(output, key=lambda item: (str(item["dependent_file"]).lower(), str(item["side"])))


def class_name_evidence(inspection: dict[str, Any], fragment: str) -> bool:
    fragment_lower = fragment.lower()
    samples = (
        inspection["bytecode"]["client_symbols_sample"]
        + inspection["bytecode"]["server_symbols_sample"]
        + inspection["bytecode"]["shared_game_symbols_sample"]
    )
    if any(fragment_lower in value.lower() for value in samples):
        return True
    for config in inspection["mixins"]["configs"]:
        values = list(config.get("common") or []) + list(config.get("client") or []) + list(config.get("server") or [])
        if any(fragment_lower in str(value).lower() for value in values):
            return True
    return False


def assert_evidence(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def decide(mod_id: str, inspection: dict[str, Any], reverse: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    mixins = inspection["mixins"]
    bytecode = inspection["bytecode"]
    metadata = inspection["metadata"]

    assert_evidence(not mixins["parse_errors"], "mixin metadata must parse", failures)
    assert_evidence(not bytecode["class_parse_errors"], "all class constant pools must parse", failures)

    if mod_id in PURE_DATA_IDS:
        assert_evidence(inspection["pure_data_pack"], "must remain a class-free data pack", failures)
        assert_evidence(inspection["data_file_count"] > 0, "must contain data/ gameplay files", failures)
        assert_evidence(inspection["asset_file_count"] == 0, "must not require client assets", failures)
        if metadata.get("display_test") == "IGNORE_SERVER_VERSION":
            classification = "SERVER_ONLY"
            rationale = (
                "Pure data/world-generation pack with explicit IGNORE_SERVER_VERSION: "
                "the server consumes the gameplay data and the client copy may be omitted."
            )
        else:
            classification = "BOTH"
            rationale = (
                "Pure server-consumed gameplay data, but its NeoForge wrapper has no explicit "
                "missing-client/display-test exemption. Fail-closed bundle placement is BOTH "
                "until a dedicated-server/client handshake proves client omission safe."
            )
    elif mod_id == "byepregen":
        classification = "BOTH"
        rationale = "Selected 1.0.7 has shared/server chunk-generation mixins and separately declared client resource/lighting mixins."
        assert_evidence(inspection["file"] == EXPECTED_FILES[mod_id], "must select ByePregen 1.0.7", failures)
        assert_evidence(mixins["common_count"] > 0, "must retain shared/server mixins", failures)
        assert_evidence(mixins["client_count"] > 0, "must retain client mixins", failures)
        assert_evidence(bytecode["client_symbol_count"] > 0, "must expose client-side bytecode evidence", failures)
        assert_evidence(bytecode["server_symbol_count"] > 0, "must expose server-side bytecode evidence", failures)
    elif mod_id == "efficient_hashing":
        classification = "BOTH"
        rationale = "The sole common mixin targets shared Vec3i/BlockPos hashing code used independently on client and server."
        assert_evidence(mixins["common_count"] > 0, "must have a common mixin", failures)
        assert_evidence(mixins["client_count"] == 0, "must not be a client-only mixin set", failures)
        assert_evidence(bytecode["shared_game_symbol_count"] > 0, "must reference shared game classes", failures)
        assert_evidence(bytecode["client_symbol_count"] == 0, "must not hard-link client-only classes", failures)
        assert_evidence(class_name_evidence(inspection, "Vec3i"), "must retain Vec3i target evidence", failures)
    elif mod_id == "fastrecipesearch":
        classification = "BOTH"
        rationale = "Recipe indexing/synchronization patches common/server resource handling and a separate client packet listener."
        assert_evidence(mixins["common_count"] > 0, "must retain common/server recipe mixins", failures)
        assert_evidence(mixins["client_count"] > 0, "must retain client packet-listener mixin", failures)
        assert_evidence(bytecode["client_symbol_count"] > 0, "must expose client bytecode evidence", failures)
        assert_evidence(class_name_evidence(inspection, "ServerResources"), "must retain ServerResources mixin", failures)
        assert_evidence(class_name_evidence(inspection, "ClientPacketListener"), "must retain ClientPacketListener mixin", failures)
    elif mod_id == "jecharacters":
        classification = "CLIENT_ONLY"
        rationale = "JEI/pinyin search integration hard-links client UI/search classes and has no server mixin or required server dependent."
        required_server = [row for row in reverse if str(row.get("type")).lower() == "required" and row.get("side") in {"SERVER", "BOTH"}]
        assert_evidence(bytecode["client_symbol_count"] > 0, "must reference client UI/search classes", failures)
        assert_evidence(bytecode["server_symbol_count"] == 0, "must not hard-link dedicated-server classes", failures)
        assert_evidence(mixins["common_count"] == 0 and mixins["server_count"] == 0, "must not declare common/server mixins", failures)
        assert_evidence(not required_server, "must have no required server/BOTH reverse dependency", failures)
    elif mod_id == "mousetweaks":
        classification = "CLIENT_ONLY"
        rationale = "Inventory screen input behavior is implemented entirely through client classes and a client-only screen mixin."
        assert_evidence(mixins["common_count"] == 0, "must have no common mixins", failures)
        assert_evidence(mixins["client_count"] > 0, "must retain client screen mixin", failures)
        assert_evidence(bytecode["client_symbol_count"] > 0, "must reference client screen/input classes", failures)
        assert_evidence(bytecode["server_symbol_count"] == 0, "must not hard-link dedicated-server classes", failures)
    elif mod_id == "rhino":
        classification = "BOTH"
        rationale = "Rhino is the script runtime required by KubeJS on side BOTH; the library itself is side-neutral."
        required_both = [row for row in reverse if str(row.get("type")).lower() == "required" and row.get("side") == "BOTH"]
        assert_evidence(any("kubejs" in row.get("dependent_mod_ids", []) for row in required_both), "KubeJS must require Rhino on BOTH", failures)
        assert_evidence(bytecode["client_symbol_count"] == 0, "Rhino core must not hard-link client classes", failures)
        assert_evidence(bytecode["server_symbol_count"] == 0, "Rhino core must not hard-link server classes", failures)
        assert_evidence(str(metadata.get("fabric_environment") or "*") == "*", "Rhino environment must remain side-neutral", failures)
    elif mod_id == "yet_another_config_lib_v3":
        classification = "CLIENT_ONLY"
        rationale = "YACL supplies configuration GUI/API code; all declared mixins are client-only and its only required reverse dependency is client-scoped."
        required = [row for row in reverse if str(row.get("type")).lower() == "required"]
        assert_evidence(mixins["common_count"] == 0 and mixins["server_count"] == 0, "YACL must have no common/server mixins", failures)
        assert_evidence(mixins["client_count"] > 0, "YACL must retain client GUI mixins", failures)
        assert_evidence(bytecode["client_symbol_count"] > 0, "YACL must reference client GUI classes", failures)
        assert_evidence(bytecode["server_symbol_count"] == 0, "YACL must not hard-link dedicated-server classes", failures)
        assert_evidence(bool(required), "YACL must have at least one required reverse dependency", failures)
        assert_evidence(all(row.get("side") == "CLIENT" for row in required), "all required YACL reverse dependencies must be CLIENT", failures)
    else:
        classification = "UNKNOWN"
        rationale = "No audited decision rule exists."
        failures.append("target has no decision rule")

    expected = EXPECTED_CLASSIFICATIONS[mod_id]
    assert_evidence(classification == expected, f"classification must remain {expected}", failures)
    if failures:
        classification = "UNKNOWN_FAIL_CLOSED"

    return {
        "classification": classification,
        "expected_classification": expected,
        "server_bundle": classification in {"SERVER_ONLY", "BOTH"},
        "client_bundle": classification in {"CLIENT_ONLY", "BOTH"},
        "rationale": rationale,
        "evidence_gate": "PASS" if not failures else "FAIL",
        "evidence_failures": failures,
    }


def build_report(inputs: Inputs = Inputs()) -> dict[str, Any]:
    upstream = read_json(inputs.upstream)
    if upstream.get("status") != "PASS":
        raise AuditError("Upstream Mechanomania mod audit is not PASS")
    pack_rows = list(upstream.get("pack_rows") or [])
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in pack_rows:
        for mod_id in row.get("mod_ids") or []:
            by_id.setdefault(str(mod_id), []).append(row)

    actual_ids = {mod_id for mod_id in TARGET_IDS if mod_id in by_id}
    if actual_ids != set(TARGET_IDS):
        raise AuditError(f"Target ID set mismatch; missing={sorted(set(TARGET_IDS) - actual_ids)}")

    classifications: list[dict[str, Any]] = []
    for mod_id in TARGET_IDS:
        candidates = by_id[mod_id]
        expected_file = EXPECTED_FILES[mod_id]
        selected = [row for row in candidates if row.get("file") == expected_file]
        if len(selected) != 1:
            raise AuditError(f"Cannot uniquely select {mod_id}: expected {expected_file}")
        inspection = inspect_jar(selected[0])
        reverse = reverse_dependencies(pack_rows, mod_id)
        decision = decide(mod_id, inspection, reverse)
        classifications.append(
            {
                "mod_id": mod_id,
                "candidate_files": sorted(str(row.get("file")) for row in candidates),
                "selected_file": expected_file,
                "excluded_candidate_files": sorted(
                    str(row.get("file")) for row in candidates if row.get("file") != expected_file
                ),
                **decision,
                "reverse_dependencies": reverse,
                "inspection": inspection,
            }
        )

    unresolved = [row["mod_id"] for row in classifications if row["classification"] == "UNKNOWN_FAIL_CLOSED"]
    generated_at = inputs.generated_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    tool_rows = []
    for label, path in (("generator", Path(__file__).resolve()), ("validator", VALIDATOR), ("tests", TESTS)):
        tool_rows.append(
            {
                "name": label,
                "path": str(path),
                "exists": path.is_file(),
                "sha256": sha256(path) if path.is_file() else None,
            }
        )
    counts = {
        "target_mod_ids": len(classifications),
        "both": sum(row["classification"] == "BOTH" for row in classifications),
        "server_only": sum(row["classification"] == "SERVER_ONLY" for row in classifications),
        "client_only": sum(row["classification"] == "CLIENT_ONLY" for row in classifications),
        "unknown_fail_closed": len(unresolved),
    }
    return {
        "schema": 1,
        "generated_at_utc": generated_at,
        "status": "PASS_STATIC_SIDE_CLASSIFICATION" if not unresolved else "BLOCKED_FAIL_CLOSED",
        "scope": {
            "target_mod_ids": list(TARGET_IDS),
            "method": "Local JAR metadata, CRC/SHA, mixin side lists, class-file constant pools, data/assets shape, and reverse dependencies.",
            "java_or_minecraft_started": False,
            "release_modified": False,
            "world_modified": False,
            "network_used": False,
        },
        "policy": {
            "unknown_is_release_blocker": True,
            "static_classification_does_not_replace_runtime_smoke": True,
            "pure_data_worldgen_goes_server_only": True,
            "client_only_gui_mods_are_excluded_from_dedicated_server": True,
            "both_means_ship_the_same_selected_sha_to_server_and_client": True,
        },
        "upstream": {
            "path": str(inputs.upstream.resolve()),
            "sha256": sha256(inputs.upstream),
            "status": upstream.get("status"),
            "pack_instance": upstream.get("pack_instance"),
        },
        "counts": counts,
        "unresolved_mod_ids": unresolved,
        "classifications": classifications,
        "tools": tool_rows,
        "integration_contract": {
            "merge_matrix_action": "Replace provisional side placement for these 11 IDs with this report only after validator PASS.",
            "runtime_gate_still_required": "Dedicated-server boot plus two real client joins remain required before production release.",
            "server_mod_ids": [row["mod_id"] for row in classifications if row["server_bundle"]],
            "client_mod_ids": [row["mod_id"] for row in classifications if row["client_bundle"]],
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Mechanomania side 分类静态审计（2026-08-13）",
        "",
        f"状态：`{report['status']}`。未知项数量：`{report['counts']['unknown_fail_closed']}`。",
        "",
        "这份报告只解决原合并矩阵中 11 个 side 元数据不完整的模组。它没有启动 Java/Minecraft、没有修改 release 或世界；结论来自本地 JAR 的 CRC/SHA、metadata、mixin 分区、class 常量池和反向依赖。静态通过后仍需专服启动和双轮真实客户端进服测试。",
        "",
        "## 结论",
        "",
        "| mod ID | 放置 | 服务端 | 客户端 | 选中 JAR | 证据门禁 |",
        "|---|---:|:---:|:---:|---|:---:|",
    ]
    for row in report["classifications"]:
        lines.append(
            f"| `{row['mod_id']}` | `{row['classification']}` | "
            f"{'是' if row['server_bundle'] else '否'} | {'是' if row['client_bundle'] else '否'} | "
            f"`{row['selected_file']}` | `{row['evidence_gate']}` |"
        )
    lines += [
        "",
        "汇总：",
        "",
        f"- BOTH：{report['counts']['both']} 个。",
        f"- SERVER_ONLY：{report['counts']['server_only']} 个。",
        f"- CLIENT_ONLY：{report['counts']['client_only']} 个。",
        f"- UNKNOWN_FAIL_CLOSED：{report['counts']['unknown_fail_closed']} 个。",
        "",
        "## 逐项依据",
        "",
    ]
    for row in report["classifications"]:
        inspection = row["inspection"]
        mixins = inspection["mixins"]
        bytecode = inspection["bytecode"]
        lines += [
            f"### `{row['mod_id']}` — `{row['classification']}`",
            "",
            row["rationale"],
            "",
            f"- JAR：`{row['selected_file']}`，SHA256 `{inspection['sha256']}`，CRC `{inspection['archive_crc']}`。",
            f"- 形态：class {inspection['class_count']}，data {inspection['data_file_count']}，assets {inspection['asset_file_count']}，pure-data `{inspection['pure_data_pack']}`。",
            f"- mixin：common {mixins['common_count']}，client {mixins['client_count']}，server {mixins['server_count']}。",
            f"- 字节码符号：client {bytecode['client_symbol_count']}，server {bytecode['server_symbol_count']}，shared-game {bytecode['shared_game_symbol_count']}。",
            f"- 反向依赖：{len(row['reverse_dependencies'])} 条；证据门禁 `{row['evidence_gate']}`。",
            "",
        ]
        if row["excluded_candidate_files"]:
            lines.append(f"排除重复候选：{', '.join(f'`{name}`' for name in row['excluded_candidate_files'])}。")
            lines.append("")
        if row["evidence_failures"]:
            lines.append("失败证据：" + "；".join(row["evidence_failures"]) + "。")
            lines.append("")
    lines += [
        "## 合并约束",
        "",
        "- `SERVER_ONLY` 不进入客户端 bundle；`CLIENT_ONLY` 不进入专用服务端 bundle。",
        "- `BOTH` 的服务端和客户端必须使用报告锁定的同一 SHA。",
        "- 任一 JAR、mixin、依赖 side 或类引用漂移时，validator 必须失败，回到 `BLOCKED_FAIL_CLOSED`。",
        "- 本报告不是永久模组白名单，不锁死后续 MCModSync OTA 扩展；新增/替换模组仍走同一 side、依赖和运行时门禁。",
        "",
        "## 未执行事项",
        "",
        "- 未启动 Java 或 Minecraft。",
        "- 未修改原服务器配置、世界、当前 staging 或 release。",
        "- 静态分类不替代专服启动、注册表核对和双轮真实客户端进服测试。",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    md_tmp = md_path.with_suffix(md_path.suffix + ".tmp")
    json_tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_tmp.write_text(markdown_report(report), encoding="utf-8")
    json_tmp.replace(json_path)
    md_tmp.replace(md_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    parser.add_argument("--generated-at-utc")
    args = parser.parse_args(argv)
    try:
        report = build_report(Inputs(upstream=args.upstream, generated_at_utc=args.generated_at_utc))
        write_reports(report, args.json, args.markdown)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED_FAIL_CLOSED", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "json": str(args.json),
                "markdown": str(args.markdown),
                "counts": report["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "PASS_STATIC_SIDE_CLASSIFICATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
