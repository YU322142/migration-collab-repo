#!/usr/bin/env python3
"""Build a detached client overlay for dedicated-server gameplay parity.

The overlay is intentionally narrower than a server-to-client directory copy.
It carries gameplay data/scripts, reviewed server-only gameplay configuration,
the one missing world-generation mod, and the C6C integrated-server policy fix.
Authentication, identity, proxy, logging, backup, database, secret and remote
operations state is denied explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile


LOCKED_SERVER_ZIP_SHA256 = "ECCD0C6D28A9444DBBCEB3AAEDBBB882E3EEF82B4DDD2547C729571F21891A92"
LOCKED_C6C_BASE_SHA256 = "2666383E0E2C4C6F49494051FC2C3723D6B851DABD42D511F05712BAD2A529C4"
LOCKED_C6C_PATCH_SHA256 = "50107B1B03630939C10AF51E3BAD350EB299516FD17A03A05A89B2611B95485F"
C6C_BASE_NAME = "c6c-1.2.5.1-purified.jar"
C6C_PATCH_NAME = "c6c-1.2.5.1-purified-sp-parity.1.jar"
HOPORP_NAME = "HopoBetterRuinedPortals-[1.21.1-1.21.3]-1.4.4b.jar"

DENIED_CONFIG_PARTS = {
    "easyauth",
    "easybot",
    "floodgate",
    "geyser-fabric",
    "grieflogger",
    "hydraulic",
    "skinsrestorer",
    "trueuuid",
    "xiyuslogin",
}
DENIED_CONFIG_FILES = {
    "simplebackups-server.toml",
    "configured-developer.properties",
}
DENIED_SUFFIXES = {
    ".bak",
    ".db",
    ".key",
    ".pem",
    ".sqlite",
    ".zip",
}
AUTH_SCRIPT_MARKERS = (
    "xiyuslogin",
    "trueuuid",
    "easyauth",
    "/login",
    "/register",
)


class ParityError(RuntimeError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def safe_config_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    lower_parts = {part.lower() for part in path.parts}
    if lower_parts & DENIED_CONFIG_PARTS:
        return False
    lower_name = path.name.lower()
    if any(marker in lower_name for marker in DENIED_CONFIG_PARTS):
        return False
    if lower_name in DENIED_CONFIG_FILES:
        return False
    if path.suffix.lower() in DENIED_SUFFIXES:
        return False
    return True


def reviewed_server_only_configs(repo: Path) -> list[str]:
    server = repo / "pack" / "server-config"
    client = repo / "pack" / "client-config"
    if not server.is_dir() or not client.is_dir():
        raise ParityError("repository config snapshots are missing")
    client_paths = {
        file.relative_to(client).as_posix()
        for file in client.rglob("*")
        if file.is_file()
    }
    rows = []
    for file in server.rglob("*"):
        if not file.is_file():
            continue
        relative = file.relative_to(server).as_posix()
        if relative not in client_paths and safe_config_path(relative):
            rows.append(relative)
    return sorted(rows)


def detect_server_root(archive: zipfile.ZipFile) -> str:
    candidates = {
        name.split("/", 1)[0]
        for name in archive.namelist()
        if "/mods/" in name and name.endswith(".jar")
    }
    if len(candidates) != 1:
        raise ParityError(f"cannot determine unique server root: {sorted(candidates)}")
    return candidates.pop()


def validate_hoporp(payload: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as mod:
        metadata = mod.read("META-INF/neoforge.mods.toml").decode("utf-8")
    if 'modId = "hoporp"' not in metadata or 'displayTest = "IGNORE_SERVER_VERSION"' not in metadata:
        raise ParityError("Hopo Better Ruined Portals metadata contract failed")


def write_payload(root: Path, relative: str, payload: bytes) -> dict[str, object]:
    target = root / PurePosixPath(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return {
        "path": relative,
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }


def build(
    server_zip: Path,
    client_root: Path,
    c6c_patch: Path,
    output: Path,
    repo: Path,
    *,
    expected_server_sha256: str | None = LOCKED_SERVER_ZIP_SHA256,
) -> dict[str, object]:
    server_zip = server_zip.resolve()
    client_root = client_root.resolve()
    c6c_patch = c6c_patch.resolve()
    output = output.resolve()
    repo = repo.resolve()
    if not server_zip.is_file() or not zipfile.is_zipfile(server_zip):
        raise ParityError("server ZIP is missing or invalid")
    if not client_root.is_dir() or not (client_root / "mods").is_dir():
        raise ParityError("client root is invalid")
    server_sha = sha256_file(server_zip)
    if expected_server_sha256 and server_sha != expected_server_sha256.upper():
        raise ParityError(
            f"server ZIP SHA mismatch: expected {expected_server_sha256}, got {server_sha}"
        )
    if sha256_file(c6c_patch) != LOCKED_C6C_PATCH_SHA256:
        raise ParityError("C6C parity patch SHA mismatch")
    current_c6c = client_root / "mods" / C6C_BASE_NAME
    if not current_c6c.is_file() or sha256_file(current_c6c) != LOCKED_C6C_BASE_SHA256:
        raise ParityError("client C6C preimage is not the locked purified base")

    if output.exists():
        raise ParityError(f"output already exists: {output}")
    staging = output.with_name(output.name + ".building")
    if staging.exists():
        shutil.rmtree(staging)
    overlay = staging / "overlay"
    overlay.mkdir(parents=True)
    rows: list[dict[str, object]] = []
    categories: dict[str, int] = {}

    reviewed_configs = reviewed_server_only_configs(repo)
    with zipfile.ZipFile(server_zip, "r") as archive:
        root = detect_server_root(archive)
        names = set(archive.namelist())

        gameplay_entries = sorted(
            name
            for name in names
            if name.startswith(f"{root}/kubejs/data/")
            or name.startswith(f"{root}/kubejs/server_scripts/")
            if not name.endswith("/")
        )
        for name in gameplay_entries:
            relative = name[len(root) + 1 :]
            payload = archive.read(name)
            if relative.startswith("kubejs/server_scripts/"):
                text = payload.decode("utf-8", errors="ignore").lower()
                found = [marker for marker in AUTH_SCRIPT_MARKERS if marker in text]
                if found:
                    raise ParityError(f"auth marker in gameplay script {relative}: {found}")
            rows.append(write_payload(overlay, relative, payload))
        categories["kubejs_gameplay"] = len(gameplay_entries)

        hoporp_entry = f"{root}/mods/{HOPORP_NAME}"
        if hoporp_entry not in names:
            raise ParityError("Hopo Better Ruined Portals is missing from server ZIP")
        hoporp = archive.read(hoporp_entry)
        validate_hoporp(hoporp)
        rows.append(write_payload(overlay, f"mods/{HOPORP_NAME}", hoporp))
        categories["missing_gameplay_mods"] = 1

        config_count = 0
        fallback_count = 0
        for relative in reviewed_configs:
            archive_name = f"{root}/config/{relative}"
            if archive_name in names:
                payload = archive.read(archive_name)
            else:
                payload = (repo / "pack" / "server-config" / relative).read_bytes()
                fallback_count += 1
            rows.append(write_payload(overlay, f"config/{relative}", payload))
            config_count += 1
        categories["reviewed_server_gameplay_configs"] = config_count
        categories["config_repo_fallbacks"] = fallback_count

        world_config = f"{root}/world/serverconfig/create_cyber_goggles_locks.toml"
        if world_config in names:
            payload = archive.read(world_config)
            rows.append(
                write_payload(
                    overlay,
                    "defaultconfigs/create_cyber_goggles_locks.toml",
                    payload,
                )
            )
            categories["new_world_serverconfigs"] = 1

    rows.append(write_payload(overlay, f"mods/{C6C_PATCH_NAME}", c6c_patch.read_bytes()))
    categories["policy_patch_mods"] = 1

    rows.sort(key=lambda row: str(row["path"]).lower())
    delete_rows = [
        {
            "path": f"mods/{C6C_BASE_NAME}",
            "expected_sha256": LOCKED_C6C_BASE_SHA256,
            "reason": "replaced_by_singleplayer_parity_build",
        }
    ]
    excluded = {
        "login_and_identity": [
            "XiyusLogin",
            "TrueUUID",
            "EasyAuth",
            "SkinRestorer identity state",
        ],
        "proxy_and_crossplay": ["Geyser", "Floodgate", "Hydraulic"],
        "operations": ["GriefLogger", "SimpleBackups", "databases", "keys", "caches"],
        "client_preserved_newer_mods": [
            "Immersive Paintings",
            "MineAstr",
            "all existing client-only rendering/UI/performance mods",
        ],
    }
    report = {
        "schema": 1,
        "status": "READY_NOT_APPLIED",
        "server_zip": str(server_zip),
        "server_zip_sha256": server_sha,
        "client_root": str(client_root),
        "overlay_file_count": len(rows),
        "categories": categories,
        "files": rows,
        "delete": delete_rows,
        "excluded": excluded,
        "preserve_existing_client_files_unless_listed": True,
        "login_systems_enabled_in_singleplayer": False,
    }
    (staging / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    staging.replace(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-zip", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--c6c-patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--expected-server-sha256", default=LOCKED_SERVER_ZIP_SHA256)
    args = parser.parse_args()
    result = build(
        args.server_zip,
        args.client_root,
        args.c6c_patch,
        args.output,
        args.repo,
        expected_server_sha256=args.expected_server_sha256,
    )
    print(json.dumps({
        "status": result["status"],
        "files": result["overlay_file_count"],
        "categories": result["categories"],
    }, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
