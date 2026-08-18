#!/usr/bin/env python3
"""Apply a previously built singleplayer gameplay parity overlay atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


class ApplyError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def safe_target(root: Path, relative: str) -> Path:
    rel = PurePosixPath(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ApplyError(f"unsafe overlay path: {relative}")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ApplyError(f"overlay escapes client root: {relative}")
    return target


def apply(overlay: Path, client_root: Path, backup: Path) -> dict[str, object]:
    overlay = overlay.resolve()
    client_root = client_root.resolve()
    backup = backup.resolve()
    manifest_path = overlay / "manifest.json"
    if not manifest_path.is_file():
        raise ApplyError("overlay manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "READY_NOT_APPLIED":
        raise ApplyError("overlay is not in READY_NOT_APPLIED state")
    files = manifest.get("files")
    deletes = manifest.get("delete")
    if not isinstance(files, list) or not isinstance(deletes, list):
        raise ApplyError("overlay manifest schema is invalid")
    if backup.exists():
        raise ApplyError(f"backup already exists: {backup}")
    backup.mkdir(parents=True)
    backup_manifest: dict[str, object] = {"files": [], "deletes": deletes}
    try:
        for row in files:
            relative = str(row["path"])
            mode = str(row.get("mode", "replace"))
            source = safe_target(overlay / "overlay", relative)
            target = safe_target(client_root, relative)
            if not source.is_file():
                raise ApplyError(f"overlay payload missing: {relative}")
            if mode == "preserve_or_add" and target.exists():
                if not target.is_file() or sha256_file(target) != str(row["sha256"]).upper():
                    raise ApplyError(f"protected client file conflict: {relative}")
                backup_manifest["files"].append(
                    {"path": relative, "existed": True, "unchanged": True}
                )
                continue
            if mode not in {"replace", "preserve_or_add"}:
                raise ApplyError(f"unknown overlay mode for {relative}: {mode}")
            if target.exists():
                backup_target = safe_target(backup, relative)
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_target)
                backup_manifest["files"].append({"path": relative, "existed": True})
            else:
                backup_manifest["files"].append({"path": relative, "existed": False})
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for row in deletes:
            relative = str(row["path"])
            target = safe_target(client_root, relative)
            expected = str(row["expected_sha256"]).upper()
            if not target.is_file() or sha256_file(target) != expected:
                raise ApplyError(f"delete preimage mismatch: {relative}")
            backup_target = safe_target(backup, relative)
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
            target.unlink()
        backup_manifest["status"] = "APPLIED"
        backup_manifest["overlay"] = str(overlay)
        (backup / "manifest.json").write_text(
            json.dumps(backup_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        applied = dict(manifest)
        applied["status"] = "APPLIED"
        applied["backup"] = str(backup)
        manifest_path.write_text(
            json.dumps(applied, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"status": "APPLIED", "files": len(files), "backup": str(backup)}
    except Exception:
        # The backup is intentionally retained for manual recovery; callers can
        # restore it with the normal filesystem or a future rollback tool.
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.overlay, args.client_root, args.backup), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
