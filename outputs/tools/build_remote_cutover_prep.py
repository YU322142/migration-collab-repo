#!/usr/bin/env python3
"""Build a deterministic, path-neutral candidate6 remote cutover prep package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
import zipfile
from typing import Any


SCHEMA = 1
BUFFER = 4 * 1024 * 1024
SOURCE_FILES = {
    "remote_cutover.py": "outputs/remote-cutover-prep-src/remote_cutover.py",
    "probe_cutover_chunks.py": "outputs/tools/probe_cutover_chunks.py",
    "README.md": "outputs/remote-cutover-prep-src/README.md",
    "requirements.txt": "outputs/remote-cutover-prep-src/requirements.txt",
}
SOURCE_MANIFESTS = {
    "server": "outputs/final-server-mods-candidate6-manifest-20260810.json",
    "client": "outputs/final-client-mods-candidate6-manifest-20260810.json",
}


class BuildError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(BUFFER):
            digest.update(block)
    return digest.hexdigest().upper()


def payload_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["path"]):
        digest.update(row["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["bytes"]).encode("ascii"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BuildError(f"JSON root must be an object: {path}")
    return value


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def portable_manifest(side: str, source: dict[str, Any], source_hash: str) -> dict[str, Any]:
    files = []
    for row in source.get("files", []):
        files.append(
            {
                key: row[key]
                for key in ("file", "bytes", "sha256", "mod_ids", "role", "component")
                if key in row
            }
        )
    files.sort(key=lambda row: row["file"].lower())
    result = {
        "schema": SCHEMA,
        "kind": "portable-candidate6-bundle-manifest",
        "side": side,
        "source_manifest": SOURCE_MANIFESTS[side],
        "source_manifest_sha256": source_hash,
        "file_count": source.get("file_count"),
        "bytes": source.get("bytes"),
        "bundle_sha256": source.get("bundle_sha256"),
        "files": files,
    }
    if result["file_count"] != len(files):
        raise BuildError(f"{side} manifest file count mismatch")
    if result["bytes"] != sum(int(row["bytes"]) for row in files):
        raise BuildError(f"{side} manifest byte count mismatch")
    digest = hashlib.sha256()
    for row in files:
        digest.update(row["file"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).upper().encode("ascii"))
        digest.update(b"\n")
    if digest.hexdigest().upper() != str(result["bundle_sha256"]).upper():
        raise BuildError(f"{side} bundle digest mismatch")
    return result


def package_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == "PACKAGE-MANIFEST.json":
            continue
        rows.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return rows


def write_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def build(workspace: Path, output_dir: Path, zip_path: Path, report_path: Path) -> dict[str, Any]:
    workspace = workspace.resolve()
    outputs = (workspace / "outputs").resolve()
    output_dir = output_dir.resolve()
    zip_path = zip_path.resolve()
    report_path = report_path.resolve()
    for path, label in ((output_dir, "output-dir"), (zip_path, "zip"), (report_path, "report")):
        if not under(path, outputs):
            raise BuildError(f"{label} must be inside workspace outputs")
    if output_dir.exists() or zip_path.exists() or report_path.exists():
        raise BuildError("output-dir, zip, and report must not already exist")
    sources = {name: workspace / relative for name, relative in SOURCE_FILES.items()}
    manifests = {side: workspace / relative for side, relative in SOURCE_MANIFESTS.items()}
    for path in [*sources.values(), *manifests.values()]:
        if path.is_symlink() or not path.is_file():
            raise BuildError(f"required source is missing or linked: {path}")

    temporary = output_dir.with_name("." + output_dir.name + ".tmp-" + uuid.uuid4().hex)
    temporary.mkdir(parents=True)
    (temporary / "manifests").mkdir()
    source_hashes: dict[str, str] = {}
    for name, source in sources.items():
        destination = temporary / name
        shutil.copyfile(source, destination)
        source_hashes[SOURCE_FILES[name]] = sha256(source)
    bundle_locks: dict[str, Any] = {}
    for side, source in manifests.items():
        source_hash = sha256(source)
        source_hashes[SOURCE_MANIFESTS[side]] = source_hash
        portable = portable_manifest(side, load(source), source_hash)
        destination = temporary / "manifests" / f"{side}-candidate6.json"
        atomic_json(destination, portable)
        bundle_locks[side] = {
            "manifest": f"manifests/{side}-candidate6.json",
            "source_manifest": SOURCE_MANIFESTS[side],
            "source_manifest_sha256": source_hash,
            "file_count": portable["file_count"],
            "bytes": portable["bytes"],
            "bundle_sha256": portable["bundle_sha256"],
        }
    release_lock = {
        "schema": SCHEMA,
        "candidate": "candidate6",
        "minecraft": "1.21.1",
        "loader": "NeoForge 21.1.241",
        "java": "21",
        "live_server_placeholder": "<LIVE_SERVER>",
        "live_snapshot_placeholder": "<LIVE_SNAPSHOT>",
        "historical_backups_are_live_source": False,
        "production_release_status": "NO_GO_UNTIL_EXTERNAL_GATES_PASS",
        "bundles": bundle_locks,
    }
    atomic_json(temporary / "release-lock.json", release_lock)
    rows = package_rows(temporary)
    package_manifest = {
        "schema": SCHEMA,
        "kind": "remote-cutover-prep-package",
        "candidate": "candidate6",
        "file_count": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "payload_sha256": payload_digest(rows),
        "files": rows,
    }
    atomic_json(temporary / "PACKAGE-MANIFEST.json", package_manifest)
    zip_temporary = zip_path.with_name("." + zip_path.name + ".tmp-" + uuid.uuid4().hex)
    write_zip(temporary, zip_temporary)
    os.rename(temporary, output_dir)
    os.rename(zip_temporary, zip_path)
    report = {
        "schema": SCHEMA,
        "status": "BUILT",
        "candidate": "candidate6",
        "package_dir": output_dir.relative_to(workspace).as_posix(),
        "package_manifest": {
            "path": output_dir.relative_to(workspace).as_posix() + "/PACKAGE-MANIFEST.json",
            "bytes": (output_dir / "PACKAGE-MANIFEST.json").stat().st_size,
            "sha256": sha256(output_dir / "PACKAGE-MANIFEST.json"),
            "payload_sha256": package_manifest["payload_sha256"],
        },
        "zip": {
            "path": zip_path.relative_to(workspace).as_posix(),
            "bytes": zip_path.stat().st_size,
            "sha256": sha256(zip_path),
        },
        "source_files": source_hashes,
        "writes_confined_to_workspace_outputs": True,
        "live_source_placeholders_only": True,
    }
    atomic_json(report_path, report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build(args.workspace, args.output_dir, args.zip, args.report)
    except (BuildError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "exit_code": 2, "error": str(exc)}))
        return 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
