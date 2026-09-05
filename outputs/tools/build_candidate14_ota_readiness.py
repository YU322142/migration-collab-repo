#!/usr/bin/env python3
"""Build local-only Candidate14-r3 MCModSync readiness and mod policy artifacts.

The generated templates are intentionally non-deployable.  They contain no
real manifest URL, no MCModSync-Config.jar and no parser-valid mods-v4.txt.
Production, Prism and the frozen Candidate14-r3 bundle are read-only inputs.
"""

from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib
from typing import Any
import zipfile


WORKSPACE = Path(__file__).resolve().parents[2]
BUNDLE_REVISION = "candidate14-r3"
CANDIDATE14_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate14-r3-20260812"
)
SERVER_PROPERTIES = Path(
    r"<AUDIT_ROOT>\incoming-20260811-raw\20260811\server.properties"
)
MCMODSYNC_ROOT = WORKSPACE / "outputs/tmp/mcmodsync-audit-20260812-r2"
MCMODSYNC_JAR = WORKSPACE / "outputs/outputs/MCModSync-1.9.1.jar"
MCMODSYNC_SOURCE_ZIP = WORKSPACE / "outputs/outputs/MCModSync-1.9.1-source.zip"
MCMODSYNC_README = WORKSPACE / "outputs/outputs/MCModSync-README-zh-CN.md"
MCMODSYNC_PROPERTIES_EXAMPLE = WORKSPACE / "outputs/outputs/modsync.properties.example"

MOD_POLICY_JSON = WORKSPACE / "outputs/candidate14-first-release-mod-policy-20260812.json"
MOD_POLICY_MD = WORKSPACE / "outputs/candidate14-first-release-mod-policy-20260812.md"
OTA_JSON = WORKSPACE / "outputs/candidate14-mcmodsync-ota-readiness-20260812.json"
OTA_MD = WORKSPACE / "outputs/candidate14-mcmodsync-ota-readiness-20260812.md"
TEMPLATE_ROOT = WORKSPACE / "outputs/candidate14-mcmodsync-local-template-20260812"
DIGEST_JSON = WORKSPACE / "outputs/candidate14-ota-artifacts-digests-20260812.json"
SUPERSESSION_JSON = WORKSPACE / "outputs/candidate14-r2-superseded-by-r3-20260812.json"

CANDIDATE14_LOCK = {
    "ready_sha256": "66778B3F91842D0AB6CC291D03AD9538AB12447F63340E6144747C4DAE819C24",
    "server_manifest_sha256": "8D6CE2F0B95ED70CCC983519EE9D683A91FDA39BD1410423BDB0755E8048DB20",
    "client_manifest_sha256": "020352BA39C8FAAF511AFF02FD0F9A92451697F51A1C8E4D1E0B9BEFE0398AAC",
    "server_bundle_sha256": "32EE13FBECD61CF8B04EA390D409D7F0B2D5FD3CB1AA37D180A75141E0FFEC28",
    "client_bundle_sha256": "FCBEFE432E802CA8834ADFEA8D360764F33697D84B690C53D085CBD3DCDE0E76",
    "bundle_pair_sha256": "D1B98FA225DD9DBE27499C36A8761A72449C50A43A250DBDCA32A348C21959C7",
    "server_files": 54,
    "client_files": 54,
}

SUPERSEDED_R2 = {
    "bundle_revision": "candidate14-r2",
    "ready_sha256": "EEFAEA250148B566A733B18EE222A32CA282CD28B705E484FDE0EA7B5797D727",
    "server_manifest_sha256": "0CBB013D306C601BAB67C536BF96C5037CA19A6A09F514AE4860F96DC0814445",
    "client_manifest_sha256": "2E14DBE03F5410C6CA2C503B187420DF805FB9BA59615A69A523092AE6E1660F",
    "server_bundle_sha256": CANDIDATE14_LOCK["server_bundle_sha256"],
    "client_bundle_sha256": CANDIDATE14_LOCK["client_bundle_sha256"],
    "bundle_pair_sha256": CANDIDATE14_LOCK["bundle_pair_sha256"],
}


def derived_catalog_version() -> str:
    return f"{BUNDLE_REVISION}-20260812-{CANDIDATE14_LOCK['ready_sha256'][:16].lower()}"

MCMODSYNC_LOCK = {
    "file": "MCModSync-1.9.1.jar",
    "bytes": 242657,
    "sha256": "2DD2BEC977B8669D0EF6C90FC54A06021DC0998E903B583517052B1B5CDA25AA",
    "source_zip_bytes": 185547,
    "source_zip_sha256": "ED710BB1C88C35DB7208467353E2C310A89609D3153B01B5124C90392FA73242",
    "readme_sha256": "0B0193B63B4A355C536C9C055D9E6336AFE5213929233D23A032EE3E58D163D6",
    "properties_example_sha256": "DD21FD4AC301F46268CAA3F4A2F1EEA5F62F892D200394D0FD7C4CB61203F44D",
    "repository_commit": "9c1e8b13f5662eb389e73adc94a9a71fcb542bc9",
    "repository": "https://github.com/YU322142/MCModSync.git",
}

SERVER_PROPERTIES_LOCK = {
    "sha256": "A71887512304BB526A125BD4F2CC835502456A3C8CB407AE73C8D02F1442552C",
    "server-port": "25566",
    "rcon.port": "25575",
    "query.port": "25565",
    "server-ip": "",
    "enable-query": "false",
    "enable-rcon": "true",
    "require-resource-pack": "false",
}

SERVER_ONLY_FILE = "grieflogger-1.2.10-1.21.1-neoforge.jar"
CLIENT_ONLY_FILE = "chest-colorizer-1.6.1-equivalence.2+mc1.21.1-neoforge.jar"

# These are useful/operational additions rather than world-schema providers.
# They remain REQUIRED in the first OTA catalog until an omit-one matrix passes.
FUTURE_OPTIONALIZATION = {
    "appleskin-neoforge-mc1.21-3.0.9.jar": "client food/HUD convenience",
    CLIENT_ONLY_FILE: "client chest-color display convenience",
    "ferritecore-7.0.3-neoforge.jar": "memory optimization",
    "ftb-ultimine-neoforge-2101.1.15.jar": "player convenience feature",
    "Jade-1.21.1-NeoForge-15.10.6.jar": "client information overlay",
    "jei-1.21.1-neoforge-19.43.0.393.jar": "client recipe viewer",
    "journeymap-neoforge-1.21.1-6.0.3.jar": "client map interface",
    "lithium-neoforge-0.15.4+mc1.21.1.jar": "performance optimization",
    "noisium-neoforge-2.3.0+mc1.21-1.21.1.jar": "world-generation performance optimization",
    "spark-1.10.124-neoforge.jar": "profiling and operations utility",
}


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def dual_hash(path: Path, chunk_size: int = 4 * 1024 * 1024) -> tuple[str, str]:
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            sha.update(block)
            md5.update(block)
    return sha.hexdigest().upper(), md5.hexdigest().lower()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.candidate14-ota.tmp")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
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


def _manifest(root: Path, side: str) -> dict[str, Any]:
    path = root / "manifests" / f"{side}.json"
    expected_hash = CANDIDATE14_LOCK[f"{side}_manifest_sha256"]
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise ValueError(f"Candidate14 {side} manifest lock mismatch: {actual_hash}")
    value = read_object(path)
    rows = value.get("files")
    expected_count = CANDIDATE14_LOCK[f"{side}_files"]
    if (
        value.get("schema") != 1
        or value.get("candidate") != 14
        or value.get("status") != "PASS"
        or value.get("side") != side
        or value.get("file_count") != expected_count
        or not isinstance(rows, list)
        or len(rows) != expected_count
    ):
        raise ValueError(f"Candidate14 {side} manifest header/count mismatch")
    names = [str(row.get("file", "")) for row in rows]
    if names != sorted(names, key=str.casefold) or len({name.casefold() for name in names}) != len(names):
        raise ValueError(f"Candidate14 {side} manifest is not a unique sorted flat set")
    if any(not name or Path(name).name != name or not name.lower().endswith(".jar") for name in names):
        raise ValueError(f"Candidate14 {side} manifest contains unsafe filename")
    computed = bundle_digest(rows)
    expected_bundle = CANDIDATE14_LOCK[f"{side}_bundle_sha256"]
    if computed != expected_bundle or str(value.get("bundle_sha256", "")).upper() != expected_bundle:
        raise ValueError(f"Candidate14 {side} bundle lock mismatch")
    return value


def _metadata(path: Path, declared_ids: list[str]) -> dict[str, str]:
    result = {"mod_id": declared_ids[0] if declared_ids else "", "version": "", "name": "", "description": ""}
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"CRC failure: {path}")
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate ZIP entries: {path}")
            if "fabric.mod.json" in names:
                value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                if isinstance(value, dict):
                    for source, target in (("id", "mod_id"), ("version", "version"), ("name", "name"), ("description", "description")):
                        if isinstance(value.get(source), str) and value[source].strip():
                            result[target] = value[source].strip()
                    return result
            for entry in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if entry not in names:
                    continue
                value = tomllib.loads(archive.read(entry).decode("utf-8"))
                mods = value.get("mods")
                if isinstance(mods, list) and mods and isinstance(mods[0], dict):
                    first = mods[0]
                    for source, target in (("modId", "mod_id"), ("version", "version"), ("displayName", "name"), ("description", "description")):
                        if isinstance(first.get(source), str) and first[source].strip() and "${" not in first[source]:
                            result[target] = first[source].strip()
                    return result
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid JAR metadata: {path}: {exc}") from exc
    return result


def _validate_candidate14(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    ready = root / "READY.json"
    release = root / "release-lock.json"
    if sha256(ready) != CANDIDATE14_LOCK["ready_sha256"] or ready.read_bytes() != release.read_bytes():
        raise ValueError("Candidate14 READY/release-lock mismatch")
    ready_value = read_object(ready)
    if ready_value.get("candidate") != 14 or ready_value.get("status") != "PASS":
        raise ValueError("Candidate14 is not a PASS release lock")
    expected_extension_policy = {
        "release_lock_semantics": "acceptance_snapshot_not_permanent_allowlist",
        "current_file_counts_are_not_production_caps": True,
        "additive_server_mods_allowed": True,
        "additive_client_mods_allowed": True,
        "ota_additions_allowed": True,
        "runtime_global_mod_denylist": False,
        "permanent_exact_mod_count_enforcement": False,
        "existing_release_snapshot_remains_immutable": True,
    }
    extension_policy = ready_value.get("extension_policy")
    if not isinstance(extension_policy, dict) or any(
        extension_policy.get(key) != expected for key, expected in expected_extension_policy.items()
    ):
        raise ValueError("Candidate14-r3 extension policy mismatch")
    extension_requirements = extension_policy.get("requirements_for_extension")
    if not isinstance(extension_requirements, list) or len(extension_requirements) < 5:
        raise ValueError("Candidate14-r3 extension requirements missing")
    server = _manifest(root, "server")
    client = _manifest(root, "client")
    if pair_digest(server["bundle_sha256"], client["bundle_sha256"]) != CANDIDATE14_LOCK["bundle_pair_sha256"]:
        raise ValueError("Candidate14 pair lock mismatch")

    server_rows = {str(row["file"]).casefold(): row for row in server["files"]}
    client_rows = {str(row["file"]).casefold(): row for row in client["files"]}
    server_only = set(server_rows) - set(client_rows)
    client_only = set(client_rows) - set(server_rows)
    if server_only != {SERVER_ONLY_FILE.casefold()} or client_only != {CLIENT_ONLY_FILE.casefold()}:
        raise ValueError(f"Candidate14 side policy changed: {server_only=} {client_only=}")
    for key in set(server_rows) & set(client_rows):
        for field in ("file", "bytes", "sha256", "mod_ids"):
            if server_rows[key].get(field) != client_rows[key].get(field):
                raise ValueError(f"Candidate14 shared row differs across sides: {key} {field}")

    inventory: list[dict[str, Any]] = []
    all_keys = sorted(set(server_rows) | set(client_rows))
    for key in all_keys:
        row = client_rows.get(key) or server_rows[key]
        side = "both" if key in server_rows and key in client_rows else "client" if key in client_rows else "server"
        ids = row.get("mod_ids")
        if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
            raise ValueError(f"Candidate14 invalid mod_ids: {row['file']}")
        copies: list[Path] = []
        if key in server_rows:
            copies.append(root / "server-mods" / str(row["file"]))
        if key in client_rows:
            copies.append(root / "client-mods" / str(row["file"]))
        verified: list[tuple[str, str, dict[str, str]]] = []
        for path in copies:
            actual_sha, actual_md5 = dual_hash(path)
            if path.stat().st_size != row["bytes"] or actual_sha != str(row["sha256"]).upper():
                raise ValueError(f"Candidate14 JAR size/hash mismatch: {path}")
            verified.append((actual_sha, actual_md5, _metadata(path, ids)))
        if len({(item[0], item[1]) for item in verified}) != 1:
            raise ValueError(f"Candidate14 physical copies differ: {row['file']}")
        actual_sha, actual_md5, metadata = verified[0]
        inventory.append(
            {
                "file": row["file"],
                "bytes": row["bytes"],
                "sha256": actual_sha,
                "md5": actual_md5,
                "mod_ids": ids,
                "catalog_mod_id_hint": metadata["mod_id"] or (ids[0] if ids else ""),
                "version_hint": metadata["version"],
                "display_name_hint": metadata["name"] or str(row.get("component") or row["file"]),
                "component": row.get("component"),
                "bundle_role": row.get("role"),
                "side": side,
                "first_release_deployment": f"required_exact_{BUNDLE_REVISION.replace('-', '_')}",
                "first_ota_kind": "required",
                "operational_tier": (
                    "recommended_but_locked_required_for_first_release"
                    if row["file"] in FUTURE_OPTIONALIZATION
                    else "must"
                ),
                "operational_note": FUTURE_OPTIONALIZATION.get(
                    row["file"],
                    "part of the locked first-release runtime or its dependency/data-safety closure",
                ),
            }
        )
    return server, client, inventory


def _validate_mcmodsync() -> dict[str, Any]:
    jar_sha, jar_md5 = dual_hash(MCMODSYNC_JAR)
    if MCMODSYNC_JAR.stat().st_size != MCMODSYNC_LOCK["bytes"] or jar_sha != MCMODSYNC_LOCK["sha256"]:
        raise ValueError("MCModSync JAR lock mismatch")
    if MCMODSYNC_SOURCE_ZIP.stat().st_size != MCMODSYNC_LOCK["source_zip_bytes"] or sha256(MCMODSYNC_SOURCE_ZIP) != MCMODSYNC_LOCK["source_zip_sha256"]:
        raise ValueError("MCModSync source ZIP lock mismatch")
    if sha256(MCMODSYNC_README) != MCMODSYNC_LOCK["readme_sha256"]:
        raise ValueError("MCModSync README lock mismatch")
    if sha256(MCMODSYNC_PROPERTIES_EXAMPLE) != MCMODSYNC_LOCK["properties_example_sha256"]:
        raise ValueError("MCModSync properties example lock mismatch")

    with zipfile.ZipFile(MCMODSYNC_JAR) as archive:
        if archive.testzip() is not None:
            raise ValueError("MCModSync JAR CRC failure")
        fabric = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
        neo = tomllib.loads(archive.read("META-INF/neoforge.mods.toml").decode("utf-8"))
    neo_mods = neo.get("mods")
    if (
        fabric.get("id") != "mcmodsync"
        or fabric.get("version") != "1.9.1"
        or fabric.get("environment") != "client"
        or not isinstance(neo_mods, list)
        or not neo_mods
        or neo_mods[0].get("modId") != "mcmodsync"
        or neo_mods[0].get("version") != "1.9.1"
    ):
        raise ValueError("MCModSync dual metadata mismatch")

    git_head = (MCMODSYNC_ROOT / ".git/HEAD").read_text(encoding="utf-8").strip()
    if not git_head.startswith("ref: "):
        raise ValueError("MCModSync audit checkout is detached/unexpected")
    git_ref = MCMODSYNC_ROOT / ".git" / git_head.removeprefix("ref: ")
    commit = git_ref.read_text(encoding="ascii").strip()
    if commit != MCMODSYNC_LOCK["repository_commit"]:
        raise ValueError(f"MCModSync repository commit mismatch: {commit}")
    config = configparser.ConfigParser()
    config.read(MCMODSYNC_ROOT / ".git/config", encoding="utf-8")
    origin = config.get('remote "origin"', "url", fallback="")
    if origin != MCMODSYNC_LOCK["repository"]:
        raise ValueError(f"MCModSync repository origin mismatch: {origin}")
    return {
        "file": MCMODSYNC_LOCK["file"],
        "bytes": MCMODSYNC_LOCK["bytes"],
        "sha256": jar_sha,
        "md5": jar_md5,
        "mod_id": "mcmodsync",
        "version": "1.9.1",
        "declared_side": "client",
        "repository": origin,
        "repository_commit": commit,
        "source_zip": {
            "path": str(MCMODSYNC_SOURCE_ZIP.relative_to(WORKSPACE)).replace("\\", "/"),
            "bytes": MCMODSYNC_LOCK["source_zip_bytes"],
            "sha256": MCMODSYNC_LOCK["source_zip_sha256"],
        },
        "readme_sha256": MCMODSYNC_LOCK["readme_sha256"],
        "properties_example_sha256": MCMODSYNC_LOCK["properties_example_sha256"],
    }


def _read_server_properties() -> dict[str, Any]:
    actual_sha = sha256(SERVER_PROPERTIES)
    if actual_sha != SERVER_PROPERTIES_LOCK["sha256"]:
        raise ValueError(f"production server.properties lock mismatch: {actual_sha}")
    values: dict[str, str] = {}
    for raw in SERVER_PROPERTIES.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key] = value
    for key, expected in SERVER_PROPERTIES_LOCK.items():
        if key == "sha256":
            continue
        if values.get(key) != expected:
            raise ValueError(f"production server.properties changed: {key}={values.get(key)!r}")
    return {
        "path": str(SERVER_PROPERTIES),
        "sha256": actual_sha,
        "must_remain_byte_identical": True,
        "locked_fields": {key: value for key, value in SERVER_PROPERTIES_LOCK.items() if key != "sha256"},
        "test_only_loopback_ports_never_write_to_production": [12341, 12342, 26341],
    }


def _deferred_features() -> list[dict[str, Any]]:
    return [
        {
            "id": "minecraft:netherite_horse_armor_full_gameplay",
            "state": "deferred_after_first_release",
            "first_release_guard": "deferred_content_protection",
            "rule": "replace the carrier with the full implementation under the same registry ID; never load both implementations",
        },
        {
            "id": "mcmodsync_runtime_enablement",
            "state": "prepared_not_installed",
            "rule": "enable only after a controlled immutable HTTPS origin, Config.jar, complete v4 catalog and canary are locked",
        },
        {
            "id": "resource_pack_and_server_list_ota",
            "state": "disabled",
            "rule": "keep syncResourcePacks=false and syncServerList=false; preserve the user-selected local resource pack and original server list",
        },
        {
            "id": "recommended_mod_optionalization",
            "state": "deferred",
            "rule": "the first OTA catalog marks every Candidate14-r3 client JAR required; optionalize only after omit-one client/server/restart tests",
        },
        {
            "id": "mineastr_astrbot_live_integration",
            "state": "deferred_acceptance",
            "rule": "keep the current MineAstr JAR/data, but do not claim live AstrBot protocol, account or permission equivalence until controlled integration tests pass",
        },
        {
            "id": "geyser_floodgate_bedrock_auth",
            "state": "not_in_first_release_bundle",
            "rule": "do not add untested Geyser/Floodgate or change authentication/proxy topology during the P0 cutover",
        },
        {
            "id": "remaining_non_p0_item_gameplay_texture_equivalence",
            "state": "deferred_to_followup_ota",
            "rule": "publish only exact-ID, ledgered, runtime-tested replacements; never delete unknown payloads to silence warnings",
        },
    ]


def _policy(
    server: dict[str, Any],
    client: dict[str, Any],
    inventory: list[dict[str, Any]],
    extension_policy: dict[str, Any],
) -> dict[str, Any]:
    must = [row for row in inventory if row["operational_tier"] == "must"]
    recommended = [row for row in inventory if row["operational_tier"] != "must"]
    return {
        "schema": 1,
        "status": "PASS_LOCKED_FIRST_RELEASE_POLICY",
        "generated_date": "2026-08-12",
        "candidate": 14,
        "bundle_revision": BUNDLE_REVISION,
        "authoritative_rule": "deploy the complete locked Candidate14-r3 side; this file count is a release snapshot, not a permanent cap; future versioned catalogs derive their add/upgrade/remove set from their own READY/manifests",
        "first_release_ota_rule": "all Candidate14-r3 client JARs are required in the first catalog; recommended is an operational annotation only",
        "bundle": {
            "ready_sha256": CANDIDATE14_LOCK["ready_sha256"],
            "server": {
                "file_count": server["file_count"],
                "bytes": server["bytes"],
                "bundle_sha256": server["bundle_sha256"],
                "manifest_sha256": CANDIDATE14_LOCK["server_manifest_sha256"],
            },
            "client": {
                "file_count": client["file_count"],
                "bytes": client["bytes"],
                "bundle_sha256": client["bundle_sha256"],
                "manifest_sha256": CANDIDATE14_LOCK["client_manifest_sha256"],
            },
            "bundle_pair_sha256": CANDIDATE14_LOCK["bundle_pair_sha256"],
        },
        "side_policy": {
            "server_only": [SERVER_ONLY_FILE],
            "client_only": [CLIENT_ONLY_FILE],
            "mcmodsync": "client_only_when_enabled; forbidden on dedicated server",
            "shared_files_must_have_identical_sha256": True,
        },
        "counts": {
            "inventory_rows": len(inventory),
            "validated_physical_jar_copies": server["file_count"] + client["file_count"],
            "must_operational_rows": len(must),
            "recommended_but_first_release_locked_rows": len(recommended),
            "first_ota_required_candidate14_rows": client["file_count"],
            "first_ota_recommended_rows": 0,
            "release_snapshot_not_permanent_cap": True,
        },
        "ota_scope": {
            "this_first_catalog": "all rows required; exact Candidate14-r3 client snapshot plus MCModSync and URL-bound Config.jar",
            "later_catalog_versions": "may add, upgrade or remove business mods only from the new release READY/manifests and immutable hashes",
            "catalog_integrity": "SHA-256 plus MD5 per object and independently pinned catalog SHA-256 are mandatory; a later configured signature is additional, not currently present",
        },
        "extension_policy": extension_policy,
        "inventory": inventory,
        "recommended_after_separate_optionalization_gate": [row["file"] for row in recommended],
        "deferred": _deferred_features(),
        "production_or_prism_modified": False,
    }


def _ota(
    server: dict[str, Any],
    client: dict[str, Any],
    inventory: list[dict[str, Any]],
    mcmodsync: dict[str, Any],
    server_properties: dict[str, Any],
    extension_policy: dict[str, Any],
) -> dict[str, Any]:
    client_files = {row["file"] for row in inventory if row["side"] in {"both", "client"}}
    if mcmodsync["file"] in client_files or mcmodsync["file"] in {row["file"] for row in inventory if row["side"] in {"both", "server"}}:
        raise ValueError("MCModSync unexpectedly installed in Candidate14")
    return {
        "schema": 1,
        "status": "LOCAL_PREPARATION_PASS_REMOTE_ENABLEMENT_BLOCKED",
        "generated_date": "2026-08-12",
        "publish_allowed": False,
        "runtime_install_allowed": False,
        "reason": "no controlled production HTTPS manifest URL or URL-bound MCModSync-Config.jar has been supplied",
        "remote_manifest_url": None,
        "production_or_prism_modified": False,
        "candidate14": {
            "bundle_revision": BUNDLE_REVISION,
            "root": str(CANDIDATE14_ROOT),
            "ready_sha256": CANDIDATE14_LOCK["ready_sha256"],
            "server_manifest_sha256": CANDIDATE14_LOCK["server_manifest_sha256"],
            "client_manifest_sha256": CANDIDATE14_LOCK["client_manifest_sha256"],
            "server_bundle_sha256": server["bundle_sha256"],
            "client_bundle_sha256": client["bundle_sha256"],
            "bundle_pair_sha256": CANDIDATE14_LOCK["bundle_pair_sha256"],
            "server_files": server["file_count"],
            "client_files": client["file_count"],
            "mcmodsync_present_server": False,
            "mcmodsync_present_client": False,
        },
        "mcmodsync": mcmodsync,
        "catalog_plan": {
            "minecraft": "1.21.1",
            "loader": "NeoForge 21.1.241",
            "catalog_format": "mcmod-sync-v4",
            "candidate14_client_rows": client["file_count"],
            "resolved_control_plane_rows": 1,
            "resolved_rows_before_config": client["file_count"] + 1,
            "unresolved_rows": ["MCModSync-Config.jar"],
            "expected_final_rows_after_config_generation": client["file_count"] + 2,
            "required_rows_first_catalog": client["file_count"] + 2,
            "recommended_rows_first_catalog": 0,
            "catalog_version": None,
            "derived_catalog_version": derived_catalog_version(),
            "catalog_version_derivation": "{bundle_revision}-{yyyymmdd}-{first16(lowercase authoritative READY SHA-256)}",
            "catalog_sha256": None,
            "config_jar_sha256": None,
            "future_catalog_set_rule": "for each new catalog-version, recompute the complete set from that release's READY/manifests; permit additions, upgrades and removals only with explicit versioned hashes and rollback lock",
            "catalog_version_source": "derive from each release's authoritative READY/release lock; never reuse an older release's catalog-version",
        },
        "client_config_policy": {
            "manifest": None,
            "language": "zh_cn",
            "syncResourcePacks": False,
            "syncServerList": False,
            "strict": True,
            "requireManifest": True,
            "connectTimeoutSeconds": 15,
            "requestTimeoutSeconds": 300,
            "fileOperationRetries": 12,
            "maxFileBytes": 67108864,
            "mobileManifest": "omitted; desktop/mobile share only the same 1.21.1 NeoForge catalog after a mobile gate",
        },
        "side_policy": {
            "server_forbidden": [MCMODSYNC_LOCK["file"], CLIENT_ONLY_FILE, "MCModSync-Config.jar"],
            "ota_forbidden": [SERVER_ONLY_FILE],
            "resource_pack_ota": "disabled",
            "server_list_ota": "disabled",
        },
        "network_and_supply_chain_policy": {
            "scheme": "HTTPS only",
            "origin": None,
            "immutable_version_directory": True,
            "object_upload_order": "all JARs and Config.jar first; mods-v4.txt last",
            "redirect_policy": "publication gateway must reject HTTP and cross-origin redirects",
            "important_implementation_boundary": "MCModSync 1.9.1 itself accepts HTTP and normal redirects; infrastructure and prepublish tests must enforce the stricter policy",
            "remote_verification": [
                "external GET for every object",
                "exact Content-Length or downloaded length",
                "SHA-256 and MD5 match local lock",
                "reject HTML/error bodies and cross-origin redirects",
                "publish catalog SHA-256 through a second controlled channel",
            ],
            "manifest_hashes_are_not_a_signature": True,
            "catalog_authenticity_policy": "each immutable catalog-version requires per-object SHA-256/MD5 plus an independently pinned catalog SHA-256; if a signing key is configured later, its signature must verify before activation",
            "no_signing_key_or_signature_in_current_local_template": True,
        },
        "extension_policy": extension_policy,
        "fail_closed": {
            "required_manifest_unreachable": "STARTUP_BLOCKED; do not launch Minecraft",
            "invalid_or_empty_manifest": "STARTUP_BLOCKED",
            "required_download_or_hash_failure": "STARTUP_BLOCKED",
            "directory_write_or_transaction_failure": "STARTUP_BLOCKED; retain backups/recovery marker",
            "monitor_signal": "parse [MCModSync] STARTUP_BLOCKED; process exit code 0 is not proof of launch",
            "first_catalog_all_runtime_rows_required": True,
        },
        "rollback": {
            "keep_mcmodsync_version": "1.9.1",
            "keep_all_prior_immutable_objects_and_catalogs": True,
            "never_reuse_catalog_version": True,
            "method": "publish the previous business JAR set under a new catalog-version, objects first and catalog last",
            "canary_two_launches_required": True,
            "halt_on": [".modsync/RECOVERY_REQUIRED.txt", "stale transaction", "hash mismatch", "STARTUP_BLOCKED"],
            "server": "short stop, snapshot and ledger; server Java mods are not hot-unloaded by MCModSync",
        },
        "production_configuration": server_properties,
        "release_gates": [
            {"id": "candidate14_runtime_join_restart", "state": "pending_parent_runtime_gate"},
            {"id": "deferred_item_two_round_ledger", "state": "pending_parent_runtime_gate"},
            {"id": "controlled_https_origin", "state": "blocked_missing_value"},
            {"id": "url_bound_config_jar", "state": "blocked_until_https_origin"},
            {
                "id": f"complete_{client['file_count'] + 2}_row_v4_catalog",
                "state": "blocked_until_config_jar",
            },
            {"id": "external_remote_hash_and_redirect_audit", "state": "blocked_until_upload"},
            {"id": "isolated_prism_first_exit_second_launch_join_render_restart_canary", "state": "not_run"},
        ],
        "local_templates": {
            "root": str(TEMPLATE_ROOT.relative_to(WORKSPACE)).replace("\\", "/"),
            "intentionally_non_deployable": True,
            "contains_real_url": False,
            "contains_config_jar": False,
            "contains_parser_valid_mods_v4": False,
        },
    }


def _escape_tsv(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


def _catalog_row(row: dict[str, Any]) -> str:
    mod_id = row.get("catalog_mod_id_hint") or "-"
    return "\t".join(
        _escape_tsv(value)
        for value in (
            str(row["sha256"]).lower(),
            row["md5"],
            mod_id,
            row["file"],
            "required",
            "",
            row.get("display_name_hint") or row["file"],
            row.get("version_hint") or "",
            f"{BUNDLE_REVISION} 首发锁定项；未经省略矩阵不得改为推荐项",
            f"{BUNDLE_REVISION} first-release locked entry; do not optionalize without an omit-one matrix",
        )
    )


def _write_templates(inventory: list[dict[str, Any]], mcmodsync: dict[str, Any], ota: dict[str, Any]) -> list[Path]:
    client_rows = [row for row in inventory if row["side"] in {"both", "client"}]
    if len(client_rows) != CANDIDATE14_LOCK["client_files"]:
        raise ValueError("client template row count mismatch")
    sync_row = {
        "file": mcmodsync["file"],
        "sha256": mcmodsync["sha256"],
        "md5": mcmodsync["md5"],
        "catalog_mod_id_hint": "mcmodsync",
        "display_name_hint": "MCModSync",
        "version_hint": "1.9.1",
    }
    resolved = sorted([*client_rows, sync_row], key=lambda row: str(row["file"]).casefold())

    final_rows = len(client_rows) + 2
    release_jar_count = len(client_rows)
    readme = f"""# Candidate14-r3 MCModSync local template (UNPUBLISHED)

This directory is deliberately not deployable. It contains no real URL, no
`MCModSync-Config.jar`, no formal `mods-v4.txt`, and no formal legacy
`mods.txt`. Do not rename or upload the draft TSV files.

To enable OTA later:

1. Freeze a controlled immutable HTTPS origin for Minecraft 1.21.1 / NeoForge.
2. Replace the placeholder in `modsync.properties.template` in an isolated
   publication workspace, then generate `MCModSync-Config.jar` with the locked
   MCModSync 1.9.1 publisher.
3. Generate a complete {final_rows}-row v4 catalog: {release_jar_count} Candidate14-r3 client JARs,
   MCModSync 1.9.1, and the generated Config.jar. Keep every row `required` in
   the first catalog. Derive the catalog-version from this release's
   authoritative READY lock (`{derived_catalog_version()}` for this snapshot),
   never from a previous release.
4. Treat the {release_jar_count}-file count as this release snapshot only. Future
   catalog versions must derive their complete add/upgrade/remove set from their
   own READY/manifests and immutable hashes; never assume this count is permanent.
5. Authenticate every versioned catalog. The current design requires per-object
   SHA-256/MD5 plus an independently pinned catalog SHA-256. No signing key is
   present in this template; if signing is introduced later, verify it as an
   additional activation gate and never claim an unsigned catalog is signed.
6. Verify every remote object from an external network. Upload the catalog
   last, then run a two-launch Prism canary before broad release.

MCModSync is client-only. Never place it or Config.jar on the dedicated server.
The resource-pack and server-list sync switches remain false.
"""
    properties = f"""# NON-DEPLOYABLE TEMPLATE: the placeholder is intentionally not a valid URL.
# Binding: {BUNDLE_REVISION}; derived catalog-version: {derived_catalog_version()}.
# Do not copy this file into Prism until a controlled immutable HTTPS origin is frozen.
manifest=${{CONTROLLED_HTTPS_MANIFEST_URL}}/minecraft/1.21.1/neoforge/mods-v4.txt
language=zh_cn
syncResourcePacks=false
syncServerList=false
strict=true
requireManifest=true
connectTimeoutSeconds=15
requestTimeoutSeconds=300
fileOperationRetries=12
maxFileBytes=67108864
"""
    header = (
        "# DRAFT_NOT_A_VALID_MCMODSYNC_CATALOG\n"
        f"# Binding: {BUNDLE_REVISION}; derived catalog-version: {derived_catalog_version()}.\n"
        "# Missing # mcmod-sync-v4 magic, catalog-version, real URL and Config.jar hash by design.\n"
        "# SHA256\tMD5\tMod ID\tFilename\tKind\tIncompatible platforms\tName\tVersion\tChinese description\tEnglish description\n"
    )
    v4_draft = header + "\n".join(_catalog_row(row) for row in resolved) + "\n"
    v4_draft += "<UNRESOLVED_SHA256>\t<UNRESOLVED_MD5>\tmcmodsync_config\tMCModSync-Config.jar\trequired\t\tMCModSync Client Configuration\t1.0.0\t等待真实 URL 生成\tGenerate only after the real URL is frozen\n"
    v2_draft = (
        "# DRAFT_NOT_A_VALID_MCMODSYNC_LEGACY_GATEWAY\n"
        f"# Binding: {BUNDLE_REVISION}; derived catalog-version: {derived_catalog_version()}.\n"
        "# Only MCModSync and Config.jar belong in the final v2 gateway.\n"
        f"{mcmodsync['md5']}\tmcmodsync\t{mcmodsync['file']}\n"
        "<UNRESOLVED_MD5>\tmcmodsync_config\tMCModSync-Config.jar\n"
    )
    draft_json = {
        "schema": 1,
        "status": "UNPUBLISHED_NONDEPLOYABLE_DRAFT",
        "bundle_revision": BUNDLE_REVISION,
        "manifest_url": None,
        "catalog_version": None,
        "derived_catalog_version": derived_catalog_version(),
        "resolved_entries": resolved,
        "unresolved_entries": [
            {
                "file": "MCModSync-Config.jar",
                "mod_id": "mcmodsync_config",
                "reason": "content and hashes depend on the not-yet-supplied production HTTPS manifest URL",
            }
        ],
        "expected_final_entries": ota["catalog_plan"]["expected_final_rows_after_config_generation"],
        "first_catalog_kind": "required_for_every_entry",
    }
    release_lock = {
        "schema": 1,
        "status": "TEMPLATE_NOT_RELEASE_LOCK",
        "publish_allowed": False,
        "bundle_revision": BUNDLE_REVISION,
        "candidate14_ready_sha256": CANDIDATE14_LOCK["ready_sha256"],
        "candidate14_client_manifest_sha256": CANDIDATE14_LOCK["client_manifest_sha256"],
        "candidate14_client_bundle_sha256": CANDIDATE14_LOCK["client_bundle_sha256"],
        "mcmodsync_sha256": mcmodsync["sha256"],
        "manifest_url": None,
        "catalog_version": None,
        "derived_catalog_version": derived_catalog_version(),
        "config_jar_sha256": None,
        "mods_v4_sha256": None,
        "external_verification": None,
        "prism_canary": None,
    }
    files = {
        TEMPLATE_ROOT / "README.md": readme.encode("utf-8"),
        TEMPLATE_ROOT / "modsync.properties.template": properties.encode("utf-8"),
        TEMPLATE_ROOT / "mods-v4.UNPUBLISHED.tsv": v4_draft.encode("utf-8"),
        TEMPLATE_ROOT / "mods-v2.UNPUBLISHED.tsv": v2_draft.encode("utf-8"),
        TEMPLATE_ROOT / "catalog-draft.json": stable_json(draft_json),
        TEMPLATE_ROOT / "release-lock.template.json": stable_json(release_lock),
    }
    for path, payload in files.items():
        write_atomic(path, payload)
    forbidden = [TEMPLATE_ROOT / "mods-v4.txt", TEMPLATE_ROOT / "mods.txt", TEMPLATE_ROOT / "modsync.properties", TEMPLATE_ROOT / "MCModSync-Config.jar"]
    if any(path.exists() for path in forbidden):
        raise ValueError(f"deployable/unsafe artifact exists in local template: {forbidden}")
    if "# mcmod-sync-v4\n" in v4_draft or re.search(r"https?://", properties):
        raise ValueError("local template accidentally became deployable")
    return list(files)


def _policy_markdown(policy: dict[str, Any]) -> str:
    recommended = policy["recommended_after_separate_optionalization_gate"]
    deferred = policy["deferred"]
    server_count = policy["bundle"]["server"]["file_count"]
    client_count = policy["bundle"]["client"]["file_count"]
    return "\n".join(
        [
            "# Candidate14-r3 首发必须 / 推荐 / 延后清单",
            "",
            "状态：`PASS_LOCKED_FIRST_RELEASE_POLICY`。首发部署以冻结的 Candidate14-r3 两侧完整目录为准，不能在开服前逐个删包。",
            "",
            f"- 服务端：{server_count} JAR，bundle `{policy['bundle']['server']['bundle_sha256']}`",
            f"- 客户端：{client_count} JAR，bundle `{policy['bundle']['client']['bundle_sha256']}`",
            f"- 配对：`{policy['bundle']['bundle_pair_sha256']}`",
            f"- 服务端专用：`{SERVER_ONLY_FILE}`；严禁进入客户端 OTA。",
            f"- 客户端专用：`{CLIENT_ONLY_FILE}`；严禁装进专用服务端。",
            f"- 数量边界：{client_count} 是本次发布快照，不是永久上限；以后每个版本必须从自己的 READY/manifests 动态计算完整的新增、升级、删除集合。",
            "- 扩展规则：服务端/客户端可以在后续新发布中新增模组，运行时没有全局模组拒绝表，也不永久强制精确包数；但每次扩展都必须有新的发布锁、侧兼容/依赖/重复 ID/CRC/摘要审计和相应回归门禁。",
            "- 清单认证：当前要求逐对象 SHA-256/MD5 与独立固定的 catalog SHA-256；本地模板没有签名密钥，未来若引入签名，必须在激活前额外验签，不能把未签名清单描述为已签名。",
            "",
            "## 必须",
            "",
            f"Candidate14-r3 当前服务端 {server_count} JAR 与客户端 {client_count} JAR 全部属于首发必须集合。首个 OTA v4 也必须把客户端 {client_count} 项全部标为 `required`；MCModSync 和以后生成的 Config.jar 同样为 `required`。详细逐文件 SHA-256/MD5 见同名 JSON。",
            "",
            "## 推荐（首发仍锁为 required）",
            "",
            "这些属于界面、便利、性能或运维工具，可在日后逐项做省略矩阵后改为 recommended；首发不要移除：",
            "",
            *[f"- `{name}`" for name in recommended],
            "",
            "## 延后 / 不在首发临时加装",
            "",
            *[f"- `{item['id']}`：{item['state']}；{item['rule']}" for item in deferred],
            "",
            "边界：MCModSync 是客户端更新器，不能热更新服务端 Java 模组；完整玩法替换仍需要短暂停服、账本核验与客户端 OTA 协同切换。",
            "",
        ]
    )


def _ota_markdown(ota: dict[str, Any]) -> str:
    client_count = ota["candidate14"]["client_files"]
    final_rows = ota["catalog_plan"]["expected_final_rows_after_config_generation"]
    return "\n".join(
        [
            "# Candidate14-r3 MCModSync OTA 准备状态",
            "",
            "状态：`LOCAL_PREPARATION_PASS_REMOTE_ENABLEMENT_BLOCKED`。本地制品和策略已锁定，但现在**不能发布或装入 Prism**。缺少真实受控 HTTPS 地址，因此 Config.jar 与完整 v4 清单无法定稿。",
            "",
            f"- Candidate14-r3 client：{client_count} JAR，`{ota['candidate14']['client_bundle_sha256']}`",
            f"- MCModSync 1.9.1：242657 bytes，`{ota['mcmodsync']['sha256']}`",
            "- 当前 Candidate14-r3 服务端和客户端都未安装 MCModSync；这是刻意的防自锁设计。",
            f"- 最终首个 v4 应为 {final_rows} 项：{client_count} 个客户端运行 JAR + MCModSync + URL 绑定的 Config.jar；全部 required。",
            f"- 本版 catalog-version 推导值为 `{ota['catalog_plan']['derived_catalog_version']}`，来源是 authoritative r3 READY SHA-256；正式发布仍需真实 HTTPS/Config.jar 后锁定，绝不能沿用旧版 catalog-version。",
            f"- {client_count} 只是本次发布快照，不是永久上限；未来每个 catalog-version 都从对应 READY/manifests 动态推导新增、升级、删除及其不可变哈希。",
            "- Candidate14-r3 的扩展策略明确允许后续受审计的服务端/客户端/OTA 新增项，不设置全局模组拒绝表，也不把精确包数变成生产永久门禁；已有发布快照仍保持不可变。",
            "- 当前版本化清单用逐对象 SHA-256/MD5 + 独立固定的 catalog SHA-256 做认证；模板中没有签名密钥，未来若加签名，验签必须成为额外激活门禁。",
            "- 资源包 OTA 与服务器列表 OTA 均关闭；不接受远程资源包，不改服务器地址/端口。",
            "",
            "## 启用门禁",
            "",
            *[f"- `{gate['id']}`：{gate['state']}" for gate in ota["release_gates"]],
            "",
            "## 失败关闭与回滚",
            "",
            "清单不可达、内容无效、必需 JAR 下载/双哈希失败、目录事务失败都必须 `STARTUP_BLOCKED`，不能带着半套模组启动。监控要解析该文本，不能只看退出码 0。回滚不降级 MCModSync；用新的 catalog-version 重新发布上一套业务 JAR，仍按对象先、清单最后，并跑两次启动金丝雀。",
            "",
            "## 原生产配置",
            "",
            f"`server.properties` 必须逐字节保持 `{ota['production_configuration']['sha256']}`。生产端口仍为 server 25566 / RCON 25575 / query 25565；12341、12342、26341 仅为本机测试端口，禁止写回生产。",
            "",
            "本地模板位于 `outputs/candidate14-mcmodsync-local-template-20260812`。它故意没有真实 URL、正式文件名或 Config.jar，不能误当发布目录。",
            "",
        ]
    )


def build() -> dict[str, Any]:
    server, client, inventory = _validate_candidate14(CANDIDATE14_ROOT)
    ready_value = read_object(CANDIDATE14_ROOT / "READY.json")
    extension_policy = ready_value["extension_policy"]
    mcmodsync = _validate_mcmodsync()
    server_properties = _read_server_properties()
    policy = _policy(server, client, inventory, extension_policy)
    ota = _ota(server, client, inventory, mcmodsync, server_properties, extension_policy)
    write_atomic(MOD_POLICY_JSON, stable_json(policy))
    write_atomic(MOD_POLICY_MD, _policy_markdown(policy).encode("utf-8"))
    write_atomic(OTA_JSON, stable_json(ota))
    write_atomic(OTA_MD, _ota_markdown(ota).encode("utf-8"))
    template_files = _write_templates(inventory, mcmodsync, ota)
    supersession = {
        "schema": 1,
        "status": "STALE_SUPERSEDED",
        "generated_date": "2026-08-12",
        "superseded": SUPERSEDED_R2,
        "authoritative": {
            "bundle_revision": BUNDLE_REVISION,
            "root": str(CANDIDATE14_ROOT),
            **CANDIDATE14_LOCK,
        },
        "same_business_jar_bytes": True,
        "reason": "Candidate14-r3 adds the authoritative acceptance-snapshot extension policy; identical business bundle hashes do not make the r2 READY/manifests publishable",
        "rule": "all release/OTA decisions must bind READY and both manifest hashes, not bundle hashes alone",
        "production_or_prism_modified": False,
    }
    write_atomic(SUPERSESSION_JSON, stable_json(supersession))
    generated = [
        MOD_POLICY_JSON,
        MOD_POLICY_MD,
        OTA_JSON,
        OTA_MD,
        SUPERSESSION_JSON,
        *template_files,
    ]
    digest_report = {
        "schema": 1,
        "status": "PASS",
        "generated_date": "2026-08-12",
        "bundle_revision": BUNDLE_REVISION,
        "locked_inputs": {
            "candidate_ready_sha256": CANDIDATE14_LOCK["ready_sha256"],
            "mcmodsync_sha256": MCMODSYNC_LOCK["sha256"],
            "production_server_properties_sha256": SERVER_PROPERTIES_LOCK["sha256"],
        },
        "generator": {
            "path": str(Path(__file__).resolve().relative_to(WORKSPACE)).replace("\\", "/"),
            "bytes": Path(__file__).resolve().stat().st_size,
            "sha256": sha256(Path(__file__).resolve()),
        },
        "test_source": {
            "path": "outputs/tools/test_candidate14_ota_readiness.py",
            "bytes": (WORKSPACE / "outputs/tools/test_candidate14_ota_readiness.py").stat().st_size,
            "sha256": sha256(WORKSPACE / "outputs/tools/test_candidate14_ota_readiness.py"),
        },
        "artifacts": [
            {
                "path": str(path.relative_to(WORKSPACE)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in sorted(generated, key=lambda item: str(item).casefold())
        ],
        "production_or_prism_modified": False,
    }
    write_atomic(DIGEST_JSON, stable_json(digest_report))
    return {
        "status": "PASS",
        "policy_json": str(MOD_POLICY_JSON),
        "ota_json": str(OTA_JSON),
        "template_root": str(TEMPLATE_ROOT),
        "digest_json": str(DIGEST_JSON),
        "inventory_rows": len(inventory),
        "resolved_ota_rows": client["file_count"] + 1,
        "expected_final_ota_rows": client["file_count"] + 2,
    }


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
