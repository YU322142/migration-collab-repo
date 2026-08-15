#!/usr/bin/env python3
"""Assemble immutable server/client mod directories from the audited inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tomllib
import zipfile
from pathlib import Path


DIAGNOSTIC_IDS = {"poi_migration_diagnostic"}


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def jar_mod_ids(path: Path) -> set[str]:
    result = set()
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "fabric.mod.json" in names:
            value = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
            if isinstance(value.get("id"), str):
                result.add(value["id"])
        for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
            if name not in names:
                continue
            value = tomllib.loads(archive.read(name).decode("utf-8"))
            for mod in value.get("mods", []):
                mod_id = mod.get("modId")
                if isinstance(mod_id, str) and "${" not in mod_id:
                    result.add(mod_id)
    return result


def side_matches(install_sides: str, side: str) -> bool:
    value = install_sides.lower()
    if "server+client" in value:
        return side in {"server", "client"}
    return f"{side}-only" in value


def canonical_rows(inventory: dict) -> list[dict]:
    return inventory["release_candidates"] + inventory["support_and_replacements"]


def validate_canonical(row: dict) -> tuple[Path, str, set[str]]:
    canonical = row["canonical"]
    path = Path(canonical["path"])
    expected = canonical["sha256"].upper()
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"canonical hash mismatch for {row['component']}: {actual}")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"canonical artifact is not a ZIP/JAR: {path}")
    expected_ids = {mod["id"] for mod in canonical.get("mods", [])}
    actual_ids = jar_mod_ids(path)
    if expected_ids and not expected_ids.issubset(actual_ids):
        raise ValueError(
            f"canonical mod IDs do not match inventory for {row['component']}: "
            f"expected {sorted(expected_ids)}, found {sorted(actual_ids)}"
        )
    return path, actual, actual_ids


def assemble(
    inventory_path: Path,
    baseline_mods: Path,
    output_dir: Path,
    side: str,
) -> dict:
    inventory = read_json(inventory_path)
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite bundle directory: {output_dir}")
    if not baseline_mods.is_dir():
        raise FileNotFoundError(baseline_mods)

    rows = canonical_rows(inventory)
    selected_rows = [row for row in rows if side_matches(row["install_sides"], side)]
    selected = []
    selected_ids = set()
    all_inventory_ids = set()
    all_inventory_hashes = set()
    for row in rows:
        canonical = row["canonical"]
        all_inventory_hashes.add(canonical["sha256"].upper())
        all_inventory_ids.update(mod["id"] for mod in canonical.get("mods", []))
    stale_hashes = set()
    for row in inventory.get("stale_or_rejected", []):
        digest = row.get("sha256")
        if digest is None and isinstance(row.get("metadata"), dict):
            digest = row["metadata"].get("sha256")
        if isinstance(digest, str):
            stale_hashes.add(digest.upper())
    for row in selected_rows:
        path, digest, mod_ids = validate_canonical(row)
        overlap = selected_ids & mod_ids
        if overlap:
            raise ValueError(f"duplicate selected canonical mod IDs: {sorted(overlap)}")
        selected_ids.update(mod_ids)
        selected.append((row, path, digest, mod_ids))

    output_dir.mkdir(parents=True)
    copied = []
    skipped = []
    output_ids: dict[str, str] = {}

    def copy_jar(path: Path, role: str, component: str, digest: str, mod_ids: set[str]) -> None:
        destination = output_dir / path.name
        if destination.exists():
            raise FileExistsError(f"bundle filename collision: {destination.name}")
        for mod_id in mod_ids:
            if mod_id in output_ids:
                raise ValueError(
                    f"duplicate mod ID {mod_id}: {output_ids[mod_id]} and {path.name}"
                )
        shutil.copy2(path, destination)
        if sha256(destination) != digest:
            raise IOError(f"bundle copy hash mismatch: {destination}")
        for mod_id in mod_ids:
            output_ids[mod_id] = destination.name
        copied.append(
            {
                "file": destination.name,
                "bytes": destination.stat().st_size,
                "sha256": digest,
                "mod_ids": sorted(mod_ids),
                "role": role,
                "component": component,
                "source": str(path),
            }
        )

    for path in sorted(baseline_mods.glob("*.jar"), key=lambda item: item.name.lower()):
        digest = sha256(path)
        mod_ids = jar_mod_ids(path)
        reason = None
        if digest in stale_hashes:
            reason = "stale-or-rejected-hash"
        elif mod_ids & DIAGNOSTIC_IDS:
            reason = "diagnostic-mod"
        elif mod_ids & all_inventory_ids:
            reason = "replaced-by-canonical-inventory"
        elif digest in all_inventory_hashes:
            reason = "canonical-inventory-copy"
        if reason:
            skipped.append(
                {
                    "file": path.name,
                    "sha256": digest,
                    "mod_ids": sorted(mod_ids),
                    "reason": reason,
                }
            )
            continue
        copy_jar(path, "baseline", path.stem, digest, mod_ids)

    for row, path, digest, mod_ids in selected:
        copy_jar(path, row["role"], row["component"], digest, mod_ids)

    copied.sort(key=lambda row: row["file"].lower())
    skipped.sort(key=lambda row: row["file"].lower())
    digest = hashlib.sha256()
    for row in copied:
        digest.update(row["file"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\n")
    return {
        "schema": 1,
        "side": side,
        "inventory": str(inventory_path.resolve()),
        "baseline_mods": str(baseline_mods.resolve()),
        "output": str(output_dir.resolve()),
        "file_count": len(copied),
        "bundle_sha256": digest.hexdigest().upper(),
        "files": copied,
        "skipped_baseline": skipped,
        "mod_ids": dict(sorted(output_ids.items())),
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble an audited mod bundle")
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--baseline-mods", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--side", choices=("server", "client"), required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = assemble(
        args.inventory.resolve(),
        args.baseline_mods.resolve(),
        args.output_dir.resolve(),
        args.side,
    )
    atomic_json(args.manifest.resolve(), result)
    print(
        json.dumps(
            {
                "side": result["side"],
                "files": result["file_count"],
                "bundle_sha256": result["bundle_sha256"],
                "manifest": str(args.manifest.resolve()),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
