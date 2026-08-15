#!/usr/bin/env python3
"""Prepare a fresh Candidate14 client from an explicit immutable release.

The selected release is exact and reproducible, but the validator deliberately
does not treat its current JAR count as a permanent production limit.  A later
additive mod release supplies a new READY/build-report pair to the same tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import uuid
import zipfile
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import candidate14_release_gate_common as release_common


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
ALLOWED_EXTERNAL_ROOT = Path(r"D:\Trans\migration-audit-work")
FORBIDDEN_SOURCE = Path(r"D:\Trans\20260807")
LOCAL_PACK_SHA256 = "614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364"
LOCAL_PACK_BYTES = 110_377_999
LOCAL_PACK_FORMAT = 34


class PrepareError(RuntimeError):
    pass


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def paths_overlap(first: Path, second: Path) -> bool:
    """Return true when either path contains the other."""
    return is_within(first, second) or is_within(second, first)


def is_reparse_point(path: Path) -> bool:
    """Detect Windows junctions/symlinks as well as ordinary symlinks."""
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) or path.is_symlink()


def validate_client_root_reparse_policy(
    source: Path, output: Path, protected_roots: tuple[Path, ...] = ()
) -> None:
    """Allow only the three immutable library junctions copied from the template.

    The client root itself and all mutable/runtime-owned directories must be
    ordinary directories.  ``assets``, ``libraries`` and ``versions`` may be
    junctions, but only when they resolve to the exact corresponding template
    target.  This keeps the D:-resident client small without allowing a hidden
    link into the source, staging, release, or runtime trees.
    """
    if is_reparse_point(output):
        raise PrepareError(f"client output root may not be a junction/reparse point: {output}")
    allowed_shared = {"assets", "libraries", "versions"}
    for item in output.iterdir():
        if not is_reparse_point(item):
            continue
        if item.name not in allowed_shared:
            raise PrepareError(f"client mutable path may not be linked: {item}")
        expected = (source / item.name).resolve()
        observed = item.resolve()
        if observed != expected:
            raise PrepareError(
                f"client shared directory target mismatch for {item.name}: "
                f"{observed} != {expected}"
            )
        if any(paths_overlap(observed, root.resolve()) for root in protected_roots):
            raise PrepareError(f"client shared directory resolves into a protected tree: {item}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)
    return sha256(path)


def validate_pack(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise PrepareError(f"local resource pack is missing or linked: {path}")
    if path.stat().st_size != LOCAL_PACK_BYTES or sha256(path) != LOCAL_PACK_SHA256:
        raise PrepareError("local resource pack byte/hash lock mismatch")
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise PrepareError(f"local resource pack CRC failure: {bad}")
            entries = archive.infolist()
            metadata = [row for row in entries if row.filename == "pack.mcmeta"]
            if len(metadata) != 1:
                raise PrepareError("local resource pack must contain one pack.mcmeta")
            value = json.loads(archive.read(metadata[0]).decode("utf-8-sig"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrepareError("local resource pack is not a valid audited ZIP") from exc
    if value.get("pack", {}).get("pack_format") != LOCAL_PACK_FORMAT:
        raise PrepareError("local resource pack format is not Minecraft 1.21.1")
    return {
        "path": str(path.resolve()),
        "sha256": LOCAL_PACK_SHA256,
        "bytes": LOCAL_PACK_BYTES,
        "pack_format": LOCAL_PACK_FORMAT,
        "entries": len(entries),
    }


def nbt_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def nbt_tag(tag_id: int, name: str, payload: bytes) -> bytes:
    return bytes((tag_id,)) + nbt_string(name) + payload


def servers_dat_payload(address: str) -> bytes:
    entry = b"".join(
        (
            nbt_tag(8, "name", nbt_string("Minecraft Server")),
            nbt_tag(8, "ip", nbt_string(address)),
            nbt_tag(1, "acceptTextures", b"\0"),
            nbt_tag(1, "hidden", b"\1"),
            b"\0",
        )
    )
    compound_list = bytes((10,)) + struct.pack(">i", 1) + entry
    return bytes((10, 0, 0)) + nbt_tag(9, "servers", compound_list) + b"\0"


def update_options(path: Path, pack_name: str, server_address: str) -> None:
    pack_id = "file/" + pack_name
    output: list[str] = []
    found_packs = False
    found_server = False
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if line.startswith("resourcePacks:"):
            if found_packs:
                continue
            found_packs = True
            try:
                values = json.loads(line.split(":", 1)[1])
            except json.JSONDecodeError as exc:
                raise PrepareError("client resourcePacks option is not valid JSON") from exc
            if not isinstance(values, list) or not all(
                isinstance(value, str) for value in values
            ):
                raise PrepareError("client resourcePacks option is not a string list")
            values = [value for value in values if value != pack_id]
            values.append(pack_id)
            output.append(
                "resourcePacks:"
                + json.dumps(values, ensure_ascii=False, separators=(",", ":"))
            )
        elif line.startswith("lastServer:"):
            if not found_server:
                output.append("lastServer:" + server_address)
                found_server = True
        else:
            output.append(line)
    if not found_packs:
        output.append(
            "resourcePacks:"
            + json.dumps(["fabric", pack_id], ensure_ascii=False, separators=(",", ":"))
        )
    if not found_server:
        output.append("lastServer:" + server_address)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def create_junction(source: Path, destination: Path) -> None:
    resolved = source.resolve()
    if is_within(resolved, FORBIDDEN_SOURCE):
        raise PrepareError(f"shared client input resolves into historical backup: {resolved}")
    if os.name != "nt":
        destination.symlink_to(resolved, target_is_directory=True)
        return
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(destination), str(resolved)],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        check=False,
    )
    if result.returncode != 0 or not destination.is_dir():
        raise PrepareError(
            f"failed to create client junction {destination}: "
            f"{result.stdout.strip()} {result.stderr.strip()}"
        )


def copy_release_mods(
    release: dict[str, Any], destination: Path
) -> dict[str, Any]:
    rows = release["client_manifest"]["rows"]
    source = Path(release["root"]) / "client-mods"
    destination.mkdir()
    actual_rows: list[dict[str, Any]] = []
    for row in rows:
        source_path = source / row["file"]
        output_path = destination / row["file"]
        shutil.copy2(source_path, output_path)
        observed = {
            "file": output_path.name,
            "bytes": output_path.stat().st_size,
            "sha256": sha256(output_path),
        }
        if observed != {key: row[key] for key in ("file", "bytes", "sha256")}:
            raise PrepareError(f"copied client JAR differs from manifest: {row['file']}")
        actual_rows.append({**observed, "mod_ids": row["mod_ids"]})
    bundle = release_common.bundle_digest(actual_rows)
    expected = release["client_manifest"]
    if (
        len(actual_rows) != expected["files"]
        or sum(row["bytes"] for row in actual_rows) != expected["bytes"]
        or bundle != expected["bundle_sha256"]
    ):
        raise PrepareError("prepared client bundle aggregate differs from manifest")
    return {
        "files": len(actual_rows),
        "bytes": sum(row["bytes"] for row in actual_rows),
        "bundle_sha256": bundle,
    }


def validate_args(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    source = args.source_minecraft_root.resolve()
    output = args.output_root.resolve()
    report = args.report.resolve()
    pack = args.local_resource_pack.resolve()
    if not is_within(source, OUTPUTS):
        raise PrepareError("client template must stay under workspace outputs")
    if not is_within(output, OUTPUTS) and not is_within(output, ALLOWED_EXTERNAL_ROOT):
        raise PrepareError("client output must stay under workspace outputs or D: migration-audit-work")
    if output in (OUTPUTS, ALLOWED_EXTERNAL_ROOT):
        raise PrepareError("client output must be an isolated directory")
    if not is_within(report, OUTPUTS):
        raise PrepareError("client report must stay under workspace outputs")
    if is_within(source, FORBIDDEN_SOURCE) or is_within(output, FORBIDDEN_SOURCE):
        raise PrepareError("historical backup is forbidden")
    if paths_overlap(output, source):
        raise PrepareError("client output may not overlap its template")
    if is_reparse_point(output):
        raise PrepareError("client output root may not already be a junction/reparse point")
    if not re.fullmatch(r"(?:\[[^]]+]|[^:]+):12341", args.server_address):
        raise PrepareError("server address must retain port 12341")
    return source, output, report, pack


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    source, output, report_path, pack_path = validate_args(args)
    release = release_common.validate_release(
        args.release_root,
        args.ready_sha256,
        args.build_report,
        args.build_report_sha256,
    )
    pack = validate_pack(pack_path)
    required = (
        source / "config",
        source / "data",
        source / "defaultconfigs",
        source / "options.txt",
        source / "assets",
        source / "libraries",
        source / "versions",
    )
    for path in required:
        if not path.exists():
            raise PrepareError(f"required client template input is missing: {path}")
    summary = {
        "schema": 1,
        "status": "PREFLIGHT_PASS" if args.preflight_only else "PREPARED",
        "candidate": 14,
        "purpose": "Dynamic Candidate14 release client root",
        "source_minecraft_root": str(source),
        "output_root": str(output),
        "source_unchanged": True,
        "release": {
            "root": release["root"],
            "ready_sha256": release["ready"]["sha256"],
            "release_lock_sha256": release["release_lock"]["sha256"],
            "client_manifest_sha256": release["client_manifest"]["sha256"],
            "client_bundle_sha256": release["client_manifest"]["bundle_sha256"],
            "file_count": release["client_manifest"]["files"],
            "release_scoped_exactness": True,
            "permanent_mod_count_cap": False,
        },
        "local_resource_pack": pack,
        "server": {
            "address": args.server_address,
            "port": 12341,
            "accept_remote_resource_pack": False,
            "servers_dat_acceptTextures": False,
            "server_properties_modified": False,
        },
        "mcmodsync": {
            "runtime_install": "NOT_INSTALLED",
            "audited_for_ota": True,
        },
        "java_started": False,
        "prism_started": False,
    }
    if args.preflight_only:
        summary["writes_performed"] = 0
        return summary
    if output.exists():
        raise PrepareError(f"refusing to overwrite client root: {output}")
    if report_path.exists():
        raise PrepareError(f"refusing to overwrite client report: {report_path}")
    temporary = output.with_name(output.name + ".candidate14." + uuid.uuid4().hex + ".tmp")
    published = False
    try:
        temporary.mkdir(parents=True)
        for name in ("assets", "libraries", "versions"):
            create_junction(source / name, temporary / name)
        for name in ("config", "defaultconfigs", "data"):
            shutil.copytree(source / name, temporary / name)
        for relative in (
            "config/voicechat/username-cache.json",
            "config/spark/tmp",
            "config/spark/tmp-client",
        ):
            cache = temporary / relative
            if cache.is_dir():
                shutil.rmtree(cache)
            elif cache.exists():
                cache.unlink()
        shutil.copy2(source / "options.txt", temporary / "options.txt")
        bundle = copy_release_mods(release, temporary / "mods")
        (temporary / "resourcepacks").mkdir()
        (temporary / "natives").mkdir()
        destination_pack = temporary / "resourcepacks" / pack_path.name
        shutil.copy2(pack_path, destination_pack)
        if sha256(destination_pack) != LOCAL_PACK_SHA256:
            raise PrepareError("copied local resource pack differs from lock")
        update_options(temporary / "options.txt", pack_path.name, args.server_address)
        (temporary / "servers.dat").write_bytes(servers_dat_payload(args.server_address))
        os.replace(temporary, output)
        published = True
        validate_client_root_reparse_policy(source, output)
        summary["client_bundle"] = bundle
        summary["local_resource_pack"] = {
            **pack,
            "path": str((output / "resourcepacks" / pack_path.name).resolve()),
            "enabled_exactly_once": True,
        }
        atomic_json(report_path, summary)
        return summary
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if published and output.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--ready-sha256", required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--build-report-sha256", required=True)
    parser.add_argument("--source-minecraft-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--local-resource-pack", type=Path, required=True)
    parser.add_argument("--server-address", default="play.example.invalid:12341")
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        value = prepare(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
