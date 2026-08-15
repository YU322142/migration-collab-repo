#!/usr/bin/env python3
"""Build a fresh, network-isolated full-stack server smoke directory."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
from pathlib import Path



def _load_resource_sanitizer():
    try:
        from sanitize_target_resources import sanitize
        return sanitize
    except ModuleNotFoundError:
        module_path = Path(__file__).with_name("sanitize_target_resources.py")
        spec = importlib.util.spec_from_file_location(
            "migration_target_resource_sanitizer", module_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load resource sanitizer: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.sanitize


sanitize_target_resources = _load_resource_sanitizer()

try:
    from sanitize_target_resources import sanitize as sanitize_target_resources
except ImportError:  # pragma: no cover - direct library use outside this folder
    sanitize_target_resources = None


RUNTIME_FILES = ("run.bat", "run.sh", "user_jvm_args.txt")
STAGING_FILES = (
    "server.properties",
    "whitelist.json",
    "ops.json",
    "banned-players.json",
    "banned-ips.json",
    "usercache.json",
)
STAGING_DIRECTORIES = (
    "world",
    "config",
    "defaultconfigs",
    "schematics",
    # Authoritative player content, not a disposable runtime cache.
    "immersive_paintings_cache",
)


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def ensure_d_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved.drive.upper() != "D:":
        raise ValueError(f"{label} must be on D: (got {resolved})")
    return resolved


def replace_properties(path: Path, replacements: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    output = []
    for line in lines:
        if line.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0]
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key in sorted(set(replacements) - seen):
        output.append(f"{key}={replacements[key]}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def disable_mineastr_network(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r"(?m)^\s*enabled\s*=\s*(?:true|false)\s*$", "enabled = false", text, count=1
    )
    if count != 1:
        raise ValueError("MineAstr enabled setting was not found exactly once")
    path.write_text(updated, encoding="utf-8")


def copy_fresh(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, target, copy_function=shutil.copy2)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def tree_metadata(root: Path) -> dict:
    files = 0
    bytes_total = 0
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        files += 1
        bytes_total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\n")
    return {
        "files": files,
        "bytes": bytes_total,
        "metadata_sha256": digest.hexdigest().upper(),
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def prepare(
    runtime_template: Path,
    staging: Path,
    mods: Path,
    output: Path,
    server_port: int,
    rcon_port: int,
    voice_port: int,
    sanitize_resources: bool = False,
) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite smoke directory: {output}")
    for required in (runtime_template / "libraries", staging / "world", mods):
        if not required.exists():
            raise FileNotFoundError(required)
    output.mkdir(parents=True)

    copy_fresh(runtime_template / "libraries", output / "libraries")
    for name in RUNTIME_FILES:
        copy_fresh(runtime_template / name, output / name)
    for name in STAGING_DIRECTORIES:
        copy_fresh(staging / name, output / name)
    for name in STAGING_FILES:
        copy_fresh(staging / name, output / name)
    copy_fresh(mods, output / "mods")
    (output / "eula.txt").write_text("eula=true\n", encoding="ascii")

    replace_properties(
        output / "server.properties",
        {
            "server-ip": "127.0.0.1",
            "server-port": str(server_port),
            "query.port": str(server_port),
            "enable-rcon": "true",
            "rcon.port": str(rcon_port),
            "rcon.password": "migration-final-smoke",
            "online-mode": "false",
            "spawn-npcs": "true",
            "max-tick-time": "-1",
            "level-name": "world",
        },
    )
    voicechat = output / "config" / "voicechat" / "voicechat-server.properties"
    if voicechat.is_file():
        replace_properties(voicechat, {"port": str(voice_port), "bind_address": "127.0.0.1"})
    disable_mineastr_network(output / "config" / "mineastr-common.toml")
    resource_sanitization = None
    if sanitize_resources:
        if sanitize_target_resources is None:
            raise RuntimeError(
                "--sanitize-resources requires sanitize_target_resources.py"
            )
        resource_sanitization = sanitize_target_resources(
            output / "world",
            output / "server.properties",
            output / "mods",
        )

    return {
        "schema": 1,
        "status": "PREPARED",
        "runtime_template": str(runtime_template),
        "staging": str(staging),
        "mods": str(mods),
        "output": str(output),
        "ports": {"server": server_port, "rcon": rcon_port, "voice": voice_port},
        "network_safety": {
            "server_bind": "127.0.0.1",
            "online_mode": False,
            "mineastr_enabled": False,
        },
        "world": tree_metadata(output / "world"),
        "mods_manifest": tree_metadata(output / "mods"),
        "server_properties_sha256": sha256(output / "server.properties"),
        "resource_sanitization": resource_sanitization,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare final full-stack server smoke")
    parser.add_argument("--runtime-template", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--mods", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--server-port", type=int, default=11821)
    parser.add_argument("--rcon-port", type=int, default=11822)
    parser.add_argument("--voice-port", type=int, default=25821)
    parser.add_argument(
        "--sanitize-resources",
        action="store_true",
        help=(
            "normalize target-only Bukkit/transfer/optional integration resources "
            "in this disposable smoke copy"
        ),
    )
    args = parser.parse_args()
    result = prepare(
        ensure_d_path(args.runtime_template, "runtime-template"),
        ensure_d_path(args.staging, "staging"),
        ensure_d_path(args.mods, "mods"),
        ensure_d_path(args.output, "output"),
        args.server_port,
        args.rcon_port,
        args.voice_port,
        args.sanitize_resources,
    )
    atomic_json(ensure_d_path(args.report, "report"), result)
    print(json.dumps({"status": result["status"], "output": result["output"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
