#!/usr/bin/env python3
"""Prepare one D:-resident client root matching the Mechanomania release.

This is intentionally separate from Prism import. It creates a fresh client
root, copies only the selected client JARs/overlay and local resource pack,
then leaves Prism launch to the human test step.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import uuid

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import mechanomania_release_runtime_common as release_common


ALLOWED_ROOT = Path(r"<AUDIT_ROOT>")
FORBIDDEN_SOURCE = Path(r"<TRANS_ROOT>\20260807")
PACK_SHA = "614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364"
PACK_BYTES = 110_377_999
PACK_RUNTIME_NAME = "migration-local-resources-mc1.21.1.zip"


class ClientPrepareError(RuntimeError):
    pass


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def overlap(a: Path, b: Path) -> bool:
    return is_within(a, b) or is_within(b, a)


def is_reparse(path: Path) -> bool:
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attrs = 0
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) or path.is_symlink()


def sha256(path: Path) -> str:
    return release_common.sha256(path)


def junction(source: Path, target: Path) -> None:
    if is_within(source, FORBIDDEN_SOURCE):
        raise ClientPrepareError(f"client shared input is forbidden: {source}")
    if os.name != "nt":
        target.symlink_to(source.resolve(), target_is_directory=True)
        return
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(target), str(source.resolve())],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        check=False,
    )
    if result.returncode != 0 or not target.is_dir():
        raise ClientPrepareError(f"junction failed: {result.stdout} {result.stderr}")


def update_options(path: Path, pack_name: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    packs_seen = False
    server_seen = False
    for line in lines:
        if line.startswith("resourcePacks:") and not packs_seen:
            packs_seen = True
            output.append('resourcePacks:' + json.dumps(["fabric", "file/" + pack_name], ensure_ascii=False, separators=(",", ":")))
        elif line.startswith("resourcePacks:"):
            continue
        elif line.startswith("lastServer:") and not server_seen:
            server_seen = True
            output.append("lastServer:127.0.0.1:12341")
        elif line.startswith("lastServer:"):
            continue
        else:
            output.append(line)
    if not packs_seen:
        output.append('resourcePacks:' + json.dumps(["fabric", "file/" + pack_name], ensure_ascii=False, separators=(",", ":")))
    if not server_seen:
        output.append("lastServer:127.0.0.1:12341")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def set_cfg_value(path: Path, key: str, value: str) -> None:
    """Set one Xaero-style ``key = value`` entry deterministically.

    The generated client must not depend on online update metadata being
    reachable or fresh.  Xaero logs an expired online-data cache as a render
    thread ERROR, so update checks are disabled without changing map, waypoint
    or multiplayer identity settings.
    """

    if not path.is_file():
        raise ClientPrepareError(f"required client config is missing: {path}")
    prefix = key + " ="
    lines = path.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.strip().startswith(prefix):
            if not replaced:
                output.append(f"{key} = {value}")
                replaced = True
            continue
        output.append(line)
    if not replaced:
        raise ClientPrepareError(f"required client config key is missing: {path}: {key}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _nbt_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def _nbt_tag(tag_id: int, name: str, payload: bytes) -> bytes:
    return bytes((tag_id,)) + _nbt_string(name) + payload


def servers_dat() -> bytes:
    entry = b"".join(
        (
            _nbt_tag(8, "name", _nbt_string("Migration Test")),
            _nbt_tag(8, "ip", _nbt_string("127.0.0.1:12341")),
            _nbt_tag(1, "acceptTextures", b"\0"),
            _nbt_tag(1, "hidden", b"\1"),
            b"\0",
        )
    )
    return bytes((10, 0, 0)) + _nbt_tag(9, "servers", bytes((10,)) + struct.pack(">i", 1) + entry) + b"\0"


def prepare(args: argparse.Namespace) -> dict:
    source = args.source_minecraft_root.resolve()
    output = args.output_root.resolve()
    pack = args.local_resource_pack.resolve()
    report = args.report.resolve()
    if not is_within(output, ALLOWED_ROOT) or is_within(output, FORBIDDEN_SOURCE):
        raise ClientPrepareError("client output must be a fresh D: migration-audit-work directory")
    if not is_within(report, ALLOWED_ROOT):
        raise ClientPrepareError("client report must be on D:")
    if overlap(output, source) or is_reparse(output) or output.exists() or report.exists():
        raise ClientPrepareError("client output/report already exists or overlaps template")
    if not source.is_dir() or source.is_symlink():
        raise ClientPrepareError("client skeleton must be a regular directory")
    if not pack.is_file() or pack.stat().st_size != PACK_BYTES or sha256(pack) != PACK_SHA:
        raise ClientPrepareError("local resource pack hash/size mismatch")
    release = release_common.validate_release(
        args.release_root.resolve(), args.ready_sha256, args.build_report.resolve(), args.build_report_sha256
    )
    for name in ("config", "data", "defaultconfigs", "options.txt"):
        if not (source / name).exists():
            raise ClientPrepareError(f"client skeleton missing {name}")
    temporary = output.with_name(output.name + ".client." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.mkdir(parents=True)
        # The old Prism instance may contain broken junctions.  Use the
        # portable Prism global stores as immutable shared inputs instead.
        portable_root = Path(r"<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3")
        versions_source = Path(
            r"<INSTANCE_ROOT>\PrismLauncher-Windows-MinGW-w64-Portable-11.0.3\instances\1.21.11\minecraft\versions"
        )
        shared = {
            "assets": portable_root / "assets",
            "libraries": portable_root / "libraries",
            "versions": versions_source,
        }
        for name, shared_source in shared.items():
            if not shared_source.is_dir():
                raise ClientPrepareError(f"client shared store missing: {shared_source}")
            junction(shared_source, temporary / name)
        for name in ("config", "data", "defaultconfigs"):
            shutil.copytree(source / name, temporary / name)
        for stale in (
            temporary / "config" / "journeymap-server.toml",
            temporary / "config" / "journeymap",
            temporary / "journeymap",
        ):
            if stale.is_dir():
                shutil.rmtree(stale)
            elif stale.exists():
                stale.unlink()
        shutil.copy2(source / "options.txt", temporary / "options.txt")
        bundle = release_common.install_mods(release, "client", temporary / "mods")
        overlay = release_common.apply_overlay(release, "client", temporary)
        set_cfg_value(temporary / "config" / "xaero" / "world-map" / "client.cfg", "update_notifications", "false")
        set_cfg_value(temporary / "config" / "xaero" / "lib" / "common.cfg", "allow_internet_access", "false")
        if (temporary / "config" / "journeymap-server.toml").exists() or (temporary / "journeymap").exists():
            raise ClientPrepareError("JourneyMap runtime remnants survived client assembly")
        (temporary / "resourcepacks").mkdir(exist_ok=True)
        # Use a stable ASCII runtime name.  The source filename is Chinese and
        # must remain untouched, but older PowerShell/Python hand-offs can
        # otherwise materialize replacement characters in the copied name.
        target_pack = temporary / "resourcepacks" / PACK_RUNTIME_NAME
        shutil.copy2(pack, target_pack)
        update_options(temporary / "options.txt", PACK_RUNTIME_NAME)
        (temporary / "natives").mkdir(exist_ok=True)
        (temporary / "servers.dat").write_bytes(servers_dat())
        (temporary / "user_jvm_args.txt").write_text("# isolated client test\n-Xms2G\n-Xmx4G\n", encoding="ascii")
        result = {
            "schema": 1,
            "status": "PREPARED",
            "source_skeleton": str(source),
            "output_root": str(output),
            "release": {
                "root": release["root"],
                "ready_sha256": release["ready"]["sha256"],
                "build_report_sha256": release["build_report"]["sha256"],
                "client_mods": bundle,
                "client_overlay": overlay,
                "permanent_mod_count_cap": False,
            },
            "resource_pack": {
                "source_path": str(pack),
                "path": str(output / "resourcepacks" / PACK_RUNTIME_NAME),
                "runtime_name": PACK_RUNTIME_NAME,
                "bytes": PACK_BYTES,
                "sha256": PACK_SHA,
                "enabled_exactly_once": True,
            },
            "server": {"address": "127.0.0.1:12341", "acceptTextures": False, "remote_pack": "REJECT"},
            "heap": {"xms": "2G", "xmx": "4G"},
            "safety": {"java_started": False, "prism_started": False, "source_written": False, "release_written": False},
        }
        result["output_root"] = str(output)
        os.replace(temporary, output)
        release_common.read_json(output / "mods" / "nonexistent.json", "never") if False else None
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if output.exists() and not report.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--release-root", type=Path, required=True)
    p.add_argument("--ready-sha256", required=True)
    p.add_argument("--build-report", type=Path, required=True)
    p.add_argument("--build-report-sha256", required=True)
    p.add_argument("--source-minecraft-root", type=Path, required=True)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--local-resource-pack", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    try:
        result = prepare(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": result["status"], "output_root": result["output_root"], "java_started": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
