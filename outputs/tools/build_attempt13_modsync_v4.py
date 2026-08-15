#!/usr/bin/env python3
"""Build a fail-closed MCModSync v4 catalog from an audited client snapshot.

This tool never edits the client, server, or the reference catalog.  It emits a
new, self-contained catalog directory and refuses to publish if the active JAR
set, classification locks, dependency closure, or MCModSync header contract
does not match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib
from typing import Any
from urllib.parse import urljoin
import zipfile

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from outputs.tools.build_mechanomania_matched_release import ReleaseError, inspect_jar


SYSTEM_MODS = {"minecraft", "neoforge", "forge", "java"}
COMPATIBILITY_PROVIDER_ALIASES = {
    # Connector supplies Fabric Loader semantics on NeoForge.  Forgified
    # Fabric API exposes the NeoForge mod id ``fabric_api`` while Fabric mods
    # declare the canonical dependency id ``fabric-api``.
    "fabricloader": "connector",
    "fabric-api": "fabric_api",
}
CATALOG_TYPES = {"required", "recommended"}
SAFETY_REQUIRED_OVERRIDES = {
    "create-carriage-orientation-guard-1.0.0+neoforge.1.21.1-p0.2.jar": (
        "必须保留：当前迁移存档中的 Create 列车曾在客户端渲染时触发 Direction.DOWN 崩溃；"
        "该双端保护模组是已验证的客户端防崩兜底。"
    ),
}
ALLOWED_MANAGED_KEYS = {
    "manifest",
    "mobileManifest",
    "syncResourcePacks",
    "resourcePackManifest",
    "mobileResourcePackManifest",
    "syncServerList",
    "serverListManifest",
    "strict",
    "requireManifest",
}
MANAGED_OUTPUT_ORDER = (
    "manifest",
    "mobileManifest",
    "syncResourcePacks",
    "resourcePackManifest",
    "mobileResourcePackManifest",
    "syncServerList",
    "serverListManifest",
    "strict",
    "requireManifest",
)


class CatalogError(RuntimeError):
    pass


def hash_file(path: Path, algorithm: str, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def sha256(path: Path) -> str:
    return hash_file(path, "sha256")


def md5(path: Path) -> str:
    return hash_file(path, "md5")


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CatalogError(f"missing regular JSON: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"JSON root must be an object: {path}")
    return value


def read_properties(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise CatalogError(f"missing regular properties file: {path}")
    result: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            raise CatalogError(f"invalid properties line {number}: {raw!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in result:
            raise CatalogError(f"duplicate/empty properties key at line {number}: {key!r}")
        result[key] = value.strip()
    return result


def manifest_headers(properties: dict[str, str]) -> list[str]:
    required = {
        "manifest",
        "syncResourcePacks",
        "resourcePackManifest",
        "mobileResourcePackManifest",
        "syncServerList",
        "serverListManifest",
        "strict",
        "requireManifest",
    }
    missing = sorted(required - properties.keys())
    if missing:
        raise CatalogError(f"modsync.properties missing managed keys: {missing}")
    unknown_managed = sorted(
        key for key in properties if key.startswith("client-config.") and key[14:] not in ALLOWED_MANAGED_KEYS
    )
    if unknown_managed:
        raise CatalogError(f"invalid client-config properties keys: {unknown_managed}")
    for key in ("syncResourcePacks", "syncServerList", "strict", "requireManifest"):
        if properties[key].lower() not in {"true", "false"}:
            raise CatalogError(f"managed boolean is not true/false: {key}={properties[key]!r}")
    manifest = properties["manifest"]
    if not manifest.startswith(("https://", "http://")) or not manifest.endswith("/mods-v4.txt"):
        raise CatalogError(f"invalid manifest URL: {manifest}")
    if "MODS%E8%87%AA%E5%8A%A8%E5%90%8C%E6%AD%A52.0" not in manifest:
        raise CatalogError("manifest URL is not bound to MODS自动同步2.0")
    headers: list[str] = []
    for key in MANAGED_OUTPUT_ORDER:
        if key in properties:
            headers.append(f"# client-config.{key}={properties[key]}")
    return headers


def _clean_toml(raw: bytes) -> dict[str, Any]:
    return tomllib.loads(raw.lstrip(b"\xef\xbb\xbf").decode("utf-8", errors="strict"))


def _manifest_version(archive: zipfile.ZipFile) -> str | None:
    try:
        value = archive.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except KeyError:
        return None
    for line in value.splitlines():
        if line.lower().startswith("implementation-version:"):
            version = line.split(":", 1)[1].strip()
            if version:
                return version
    return None


def display_metadata(path: Path, inspected: dict[str, Any]) -> dict[str, str]:
    fallback_id = (inspected.get("mod_ids") or inspected.get("nested_mod_ids") or [path.stem])[0]
    fallback_version = inspected.get("versions", {}).get(fallback_id) or _version_from_name(path.name)
    result = {
        "mod_id": str(fallback_id),
        "name": str(fallback_id),
        "version": str(fallback_version or "unknown"),
        "description": "",
    }
    with zipfile.ZipFile(path) as archive:
        lowered = {name.lower(): name for name in archive.namelist()}
        metadata_name = lowered.get("meta-inf/neoforge.mods.toml") or lowered.get("meta-inf/mods.toml")
        if metadata_name:
            data = _clean_toml(archive.read(metadata_name))
            mods = [row for row in (data.get("mods") or []) if isinstance(row, dict)]
            chosen = None
            for row in mods:
                if str(row.get("modId", "")).strip() == result["mod_id"]:
                    chosen = row
                    break
            if chosen is None and mods:
                chosen = mods[0]
            if chosen:
                mod_id = str(chosen.get("modId") or result["mod_id"]).strip()
                name = str(chosen.get("displayName") or mod_id).strip()
                version = chosen.get("version")
                if not isinstance(version, str) or not version.strip() or "${" in version:
                    version = inspected.get("versions", {}).get(mod_id) or _manifest_version(archive) or result["version"]
                description = str(chosen.get("description") or "").strip()
                result.update(mod_id=mod_id, name=name, version=str(version).strip(), description=description)
                return result
        fabric_name = lowered.get("fabric.mod.json")
        if fabric_name:
            data = json.loads(archive.read(fabric_name).decode("utf-8"))
            if isinstance(data, dict):
                result.update(
                    mod_id=str(data.get("id") or result["mod_id"]).strip(),
                    name=str(data.get("name") or data.get("id") or result["name"]).strip(),
                    version=str(data.get("version") or result["version"]).strip(),
                    description=str(data.get("description") or "").strip(),
                )
    return result


def _version_from_name(name: str) -> str:
    stem = name[:-4] if name.lower().endswith(".jar") else name
    match = re.search(r"(?<!\d)(\d+(?:[._+-]\d+)+(?:[-+._a-zA-Z0-9]*)?)", stem)
    return match.group(1) if match else "unknown"


def escape_field(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def normalize_classification(value: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    rows = value.get("classifications") or value.get("rows") or value.get("entries")
    if not isinstance(rows, list):
        raise CatalogError("classification JSON must contain classifications/rows array")
    mapping: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CatalogError(f"classification row {index} is not an object")
        file_name = row.get("file") or row.get("filename")
        kind = str(row.get("type") or row.get("classification") or "").lower()
        if not isinstance(file_name, str) or not file_name.lower().endswith(".jar"):
            raise CatalogError(f"invalid classification filename at row {index}: {file_name!r}")
        if kind not in CATALOG_TYPES:
            raise CatalogError(f"invalid classification type for {file_name}: {kind!r}")
        key = file_name.casefold()
        if key in mapping:
            raise CatalogError(f"duplicate classification filename: {file_name}")
        normalized = dict(row)
        normalized["file"] = file_name
        normalized["type"] = kind
        normalized["reason"] = str(row.get("reason") or row.get("rationale") or "").strip()
        if file_name in SAFETY_REQUIRED_OVERRIDES:
            normalized["source_type"] = kind
            normalized["type"] = "required"
            normalized["reason"] = SAFETY_REQUIRED_OVERRIDES[file_name]
        mapping[key] = normalized
    excluded = value.get("bootstrap_excluded") or value.get("bootstrapExcluded") or value.get("excluded") or []
    if not isinstance(excluded, list):
        raise CatalogError("classification bootstrap_excluded/excluded must be an array")
    normalized_excluded: list[dict[str, Any]] = []
    for row in excluded:
        if isinstance(row, str):
            row = {"file": row}
        if isinstance(row, dict) and "file" not in row and isinstance(row.get("filename"), str):
            row = {**row, "file": row["filename"]}
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise CatalogError(f"invalid excluded row: {row!r}")
        normalized_excluded.append(dict(row))
    return mapping, normalized_excluded


def validate_dependency_closure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    providers: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for mod_id in row["all_mod_ids"]:
            providers.setdefault(mod_id, []).append(row)
    checked = 0
    alias_edges: list[dict[str, str]] = []
    missing: list[dict[str, Any]] = []
    promoted_failures: list[dict[str, Any]] = []
    for row in rows:
        if row["type"] != "required":
            continue
        for dep in row["dependencies"]:
            dep_type = str(dep.get("type", "required")).lower()
            mandatory = dep.get("mandatory")
            side = str(dep.get("side", "BOTH")).upper()
            dep_id = str(dep.get("mod_id", "")).strip()
            if not dep_id or dep_id in SYSTEM_MODS or side == "SERVER":
                continue
            if dep_type != "required" and mandatory is not True:
                continue
            checked += 1
            provider_id = COMPATIBILITY_PROVIDER_ALIASES.get(dep_id, dep_id)
            choices = providers.get(provider_id, [])
            if provider_id != dep_id:
                alias_edges.append({"declared": dep_id, "provider": provider_id, "required_by": row["file"]})
            if not choices:
                missing.append({"file": row["file"], "dependency": dep_id, "side": side})
            elif all(choice["type"] != "required" for choice in choices):
                promoted_failures.append(
                    {
                        "file": row["file"],
                        "dependency": dep_id,
                        "providers": [choice["file"] for choice in choices],
                    }
                )
    if missing:
        raise CatalogError(f"required client dependency missing from catalog: {missing}")
    if promoted_failures:
        raise CatalogError(f"required dependency classified recommended: {promoted_failures}")
    return {
        "required_edges_checked": checked,
        "missing": 0,
        "recommended_provider_violations": 0,
        "compatibility_alias_edges": alias_edges,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    client_mods = args.client_mods.resolve()
    server_mods = args.server_mods.resolve()
    properties_path = args.properties.resolve()
    old_reference = args.old_reference.resolve()
    classification_path = args.classification.resolve()
    output = args.output.resolve()
    for path, label in ((client_mods, "client mods"), (server_mods, "server mods")):
        if path.is_symlink() or not path.is_dir():
            raise CatalogError(f"missing regular {label} directory: {path}")
    if output.exists():
        raise CatalogError(f"refusing to overwrite output directory: {output}")
    if old_reference.is_symlink() or not old_reference.is_file():
        raise CatalogError(f"missing old reference catalog: {old_reference}")

    classification_doc = read_json(classification_path)
    classification, excluded_spec = normalize_classification(classification_doc)
    properties = read_properties(properties_path)
    managed_headers = manifest_headers(properties)

    client_files = sorted(client_mods.glob("*.jar"), key=lambda path: path.name.casefold())
    server_files = sorted(server_mods.glob("*.jar"), key=lambda path: path.name.casefold())
    if any(path.is_symlink() or not path.is_file() for path in client_files + server_files):
        raise CatalogError("JAR roots must contain only regular non-symlink JAR files")
    live_by_name = {path.name.casefold(): path for path in client_files}
    if len(live_by_name) != len(client_files):
        raise CatalogError("duplicate case-insensitive client JAR filename")

    excluded_rows: list[dict[str, Any]] = []
    excluded_keys: set[str] = set()
    for spec in excluded_spec:
        key = spec["file"].casefold()
        if key in excluded_keys:
            raise CatalogError(f"duplicate excluded filename: {spec['file']}")
        path = live_by_name.get(key)
        if path is None:
            raise CatalogError(f"excluded bootstrap JAR missing from client: {spec['file']}")
        digest = sha256(path)
        expected = str(spec.get("sha256") or "").upper()
        if expected and digest != expected:
            raise CatalogError(f"excluded bootstrap hash drift: {path.name}: {digest} != {expected}")
        excluded_rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": digest,
                "reason": str(spec.get("reason") or "bootstrap component excluded from gameplay catalog"),
            }
        )
        excluded_keys.add(key)

    expected_keys = set(classification) | excluded_keys
    actual_keys = set(live_by_name)
    if actual_keys != expected_keys:
        raise CatalogError(
            "client snapshot/classification mismatch: "
            f"unclassified={sorted(actual_keys - expected_keys)}, missing={sorted(expected_keys - actual_keys)}"
        )

    rows: list[dict[str, Any]] = []
    for key, spec in sorted(classification.items(), key=lambda item: item[0]):
        path = live_by_name[key]
        before = (path.stat().st_size, path.stat().st_mtime_ns)
        try:
            inspected = inspect_jar(path)
        except ReleaseError as exc:
            raise CatalogError(str(exc)) from exc
        digest_md5 = md5(path)
        after = (path.stat().st_size, path.stat().st_mtime_ns)
        if before != after:
            raise CatalogError(f"client JAR changed while being audited: {path}")
        expected_sha = str(spec.get("sha256") or "").upper()
        if expected_sha and inspected["sha256"] != expected_sha:
            raise CatalogError(f"classification SHA drift for {path.name}")
        meta = display_metadata(path, inspected)
        mod_id = str(spec.get("mod_id") or meta["mod_id"]).strip()
        name = str(spec.get("name") or meta["name"] or mod_id).strip()
        version = str(spec.get("version") or meta["version"] or "unknown").strip()
        reason = spec["reason"] or (
            "服务端玩法、注册表、网络协议或必需依赖；缺少时不能可靠启动或进入服务器。"
            if spec["type"] == "required"
            else "纯客户端体验、显示或性能增强；移除后不影响启动和进入服务器。"
        )
        all_mod_ids = sorted(set(inspected["mod_ids"]) | set(inspected["nested_mod_ids"]))
        rows.append(
            {
                "file": path.name,
                "path": str(path),
                "bytes": inspected["bytes"],
                "sha256": inspected["sha256"],
                "md5": digest_md5,
                "mod_id": mod_id,
                "all_mod_ids": all_mod_ids,
                "name": name,
                "version": version,
                "type": spec["type"],
                "incompatible_platforms": str(spec.get("incompatible_platforms") or "-"),
                "reason": reason,
                "description": str(spec.get("description") or meta["description"] or "").strip(),
                "dependencies": inspected["dependencies"],
                "archive_crc": inspected["archive_crc"],
                "entry_count": inspected["entry_count"],
                "metadata_kind": inspected["metadata_kind"],
            }
        )

    closure = validate_dependency_closure(rows)
    ordered = sorted(rows, key=lambda row: (0 if row["type"] == "required" else 1, row["file"].casefold()))
    catalog_version = args.catalog_version
    if not re.fullmatch(r"\d{8}-\d{6}", catalog_version):
        raise CatalogError(f"invalid catalog version: {catalog_version!r}")
    header = [
        "# mcmod-sync-v4",
        f"# catalog-version={catalog_version}",
        "# minecraft=1.21.1",
        "# loader=neoforge",
        *managed_headers,
        r"# SHA256\tMD5\tMod ID\t文件名\t类型\t不兼容平台\t名称\t版本\t中文描述\tEnglish description",
    ]
    data_lines: list[str] = []
    for row in ordered:
        fields = (
            row["sha256"],
            row["md5"],
            row["mod_id"],
            row["file"],
            row["type"],
            row["incompatible_platforms"],
            row["name"],
            row["version"],
            row["reason"],
            row["description"],
        )
        escaped = [escape_field(value) for value in fields]
        if len(escaped) != 10 or any("\t" in value for value in escaped):
            raise CatalogError(f"invalid rendered fields for {row['file']}")
        data_lines.append("\t".join(escaped))
    catalog_payload = ("\n".join(header + data_lines) + "\n").encode("utf-8")
    if catalog_payload.startswith(b"\xef\xbb\xbf") or b"\r" in catalog_payload:
        raise CatalogError("catalog must be UTF-8 without BOM and LF-only")

    base_url = urljoin(properties["manifest"], "./")
    server_names = {path.name.casefold() for path in server_files}
    report = {
        "schema": 1,
        "status": "PASS_STATIC_CATALOG_NOT_ENABLED",
        "generated_at_local": args.generated_at_local,
        "catalog_version": catalog_version,
        "scope": {
            "client_mods": str(client_mods),
            "server_mods": str(server_mods),
            "properties": str(properties_path),
            "old_reference": str(old_reference),
            "classification": str(classification_path),
            "output": str(output),
        },
        "source_locks": {
            "modsync_properties_sha256": sha256(properties_path),
            "old_reference_sha256": sha256(old_reference),
            "classification_sha256": sha256(classification_path),
        },
        "counts": {
            "active_client_jars": len(client_files),
            "catalog_rows": len(ordered),
            "required": sum(row["type"] == "required" for row in ordered),
            "recommended": sum(row["type"] == "recommended" for row in ordered),
            "bootstrap_excluded": len(excluded_rows),
            "server_jars_reference_only": len(server_files),
            "catalog_files_also_present_on_server_by_filename": sum(row["file"].casefold() in server_names for row in ordered),
        },
        "download": {
            "manifest": properties["manifest"],
            "base_url": base_url,
            "minecraft": "1.21.1",
            "loader": "neoforge",
            "managed_headers": managed_headers,
        },
        "policy": {
            "required": "Removing it prevents reliable client startup, protocol/registry compatibility, successful join, or safe operation of migrated server content.",
            "recommended": "Removing it does not affect client startup or ability to join; only client UX, visuals, maps, diagnostics, or performance change.",
            "mcmodsync_client_only": True,
            "mcmodsync_server_install": False,
            "catalog_enabled_by_this_build": False,
            "active_client_modified_by_this_build": False,
            "server_modified_by_this_build": False,
            "safety_required_overrides": [
                {
                    "file": file_name,
                    "reason": reason,
                }
                for file_name, reason in sorted(SAFETY_REQUIRED_OVERRIDES.items())
            ],
        },
        "dependency_closure": closure,
        "bootstrap_excluded": excluded_rows,
        "rows": ordered,
    }

    markdown = [
        "# Attempt13 MCModSync v4 模组分类",
        "",
        f"状态：`{report['status']}`。本目录只生成发布候选，未启用 MCModSync、未修改客户端或服务端。",
        "",
        f"- 活动客户端 JAR：{len(client_files)}",
        f"- 清单玩法/依赖行：{len(ordered)}",
        f"- 必须：{report['counts']['required']}",
        f"- 推荐：{report['counts']['recommended']}",
        f"- 引导组件排除：{len(excluded_rows)}（MCModSync 本体与 Config.jar）",
        f"- Manifest：`{properties['manifest']}`",
        f"- 下载基址：`{base_url}`",
        "",
        "## 分类口径",
        "",
        "- `required`：缺少会导致客户端不能启动、依赖不闭合、协议/注册表不匹配、不能入服，或进入迁移存档后触发已知恶性崩溃/数据风险。",
        "- `recommended`：只影响客户端界面、地图、显示、诊断或性能；移除后仍可启动并进入服务器。",
        "- 保守项按 `required` 处理；未来只有通过“删模组启动 + 真入服”负载门禁后才可降为推荐。",
        "",
        "## 推荐模组",
        "",
    ]
    for row in ordered:
        if row["type"] == "recommended":
            markdown.append(f"- `{row['file']}` — {row['name']}：{row['reason']}")
    markdown.extend(["", "## 引导组件（不进入玩法清单）", ""])
    for row in excluded_rows:
        markdown.append(f"- `{row['file']}` `{row['sha256']}`：{row['reason']}")
    markdown.extend(
        [
            "",
            "## 发布前仍需完成",
            "",
            "1. 将本目录中的 247 个清单目标 JAR 按原文件名上传到下载基址。",
            "2. 对远端逐文件做 SHA-256/MD5/重定向/Content-Length 审计。",
            "3. 仅在远端内容完全就绪后，将经审计的 MCModSync 与 Config.jar 放入客户端并做两次金丝雀启动。",
            "4. 服务端永远不安装 MCModSync。",
            "",
        ]
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        (temp / "mods-v4.txt").write_bytes(catalog_payload)
        (temp / "mods-v4-classification.json").write_bytes(stable_json(report))
        (temp / "MODS-V4-CLASSIFICATION.md").write_text("\n".join(markdown), encoding="utf-8", newline="\n")
        shutil.copy2(classification_path, temp / "classification-source.json")
        shutil.copy2(properties_path, temp / "modsync-properties-reference.txt")
        artifacts = [
            "MODS-V4-CLASSIFICATION.md",
            "classification-source.json",
            "mods-v4-classification.json",
            "mods-v4.txt",
            "modsync-properties-reference.txt",
        ]
        sums = [f"{sha256(temp / name)}  {name}" for name in artifacts]
        (temp / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii", newline="\n")
        for line in (temp / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
            digest, name = line.split("  ", 1)
            if sha256(temp / name) != digest:
                raise CatalogError(f"output digest self-check failed: {name}")
        os.replace(temp, output)
    finally:
        if temp.exists():
            shutil.rmtree(temp, ignore_errors=True)

    return {
        "status": report["status"],
        "output": str(output),
        "catalog_sha256": sha256(output / "mods-v4.txt"),
        "report_sha256": sha256(output / "mods-v4-classification.json"),
        "counts": report["counts"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-mods", required=True, type=Path)
    parser.add_argument("--server-mods", required=True, type=Path)
    parser.add_argument("--properties", required=True, type=Path)
    parser.add_argument("--old-reference", required=True, type=Path)
    parser.add_argument("--classification", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--generated-at-local", required=True)
    return parser.parse_args()


def main() -> int:
    try:
        result = build(parse_args())
    except (CatalogError, OSError, UnicodeError, ValueError, zipfile.BadZipFile, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
