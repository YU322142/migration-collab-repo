#!/usr/bin/env python3
"""Refresh a pre-converted staging server from a stopped source server.

The expensive whole-world audit is expected to have completed before downtime.
This tool records an exact SHA-256 baseline, then refreshes only files that
changed after that baseline.  Region changes are passed to the audited NBT
converter with --only-region; special SavedData and account formats use their
dedicated converters.  Unknown config changes and source-side deletions block
the refresh instead of guessing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


SOURCE_DEFAULT = Path(r"<TRANS_ROOT>\20260807")
STAGING_DEFAULT = Path(r"<AUDIT_ROOT>\cutover-staging-final")
WAYPOINT_JAR_DEFAULT = Path(
    r"<AUDIT_ROOT>\waypoint-fire-equivalence\build\libs\waypoint-fire-equivalence-0.1.0-draft+mc1.21.1.jar"
)
WAYPOINT_SHA256 = "5572EE1F196038071FB5D7B9D7FF271CCB0E19BA722B83BCC1A2B8C0C844F8EB"

COPY_DIRECTORIES = (
    "world",
    "config",
    "defaultconfigs",
    "schematics",
    # Authoritative player content, not a disposable runtime cache.
    "immersive_paintings_cache",
)
COPY_FILES = (
    "server.properties",
    "whitelist.json",
    "ops.json",
    "banned-players.json",
    "banned-ips.json",
    "usercache.json",
)
LEGACY_DIMENSIONS = ("world_nether", "world_the_end")
VOLATILE_NAMES = {
    "session.lock",
    "ledger.sqlite",
    "ledger.sqlite-shm",
    "ledger.sqlite-wal",
}
SPECIAL_CONFIGS = {"config/mineastr-common.json"}
SPECIAL_DATA = {
    "world/data/create_tracks.dat",
    "world/data/create_logistics.dat",
    "world/data/mineastr_sign_translations.dat",
}


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def ensure_d_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved.drive.upper() != "D:":
        raise ValueError(f"{label} must be on D: (got {resolved})")
    return resolved


def ensure_distinct(source: Path, staging: Path) -> None:
    if source == staging:
        raise ValueError("source and staging must be different directories")
    try:
        staging.relative_to(source)
    except ValueError:
        return
    raise ValueError("staging must not be inside the source directory")


def source_target_pairs(source: Path) -> Iterable[tuple[str, Path, str]]:
    for root_name in COPY_DIRECTORIES:
        root = source / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name not in VOLATILE_NAMES:
                relative = path.relative_to(source).as_posix()
                yield relative, path, relative
    for name in COPY_FILES:
        path = source / name
        if path.is_file():
            yield name, path, name
    for name in LEGACY_DIMENSIONS:
        root = source / name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name not in VOLATILE_NAMES:
                source_relative = path.relative_to(source).as_posix()
                target_relative = (
                    Path("migration-input") / "legacy-dimensions" / source_relative
                ).as_posix()
                yield source_relative, path, target_relative
    auth = source / "EasyAuth" / "easyauth.db"
    if auth.is_file():
        yield (
            "EasyAuth/easyauth.db",
            auth,
            "migration-input/EasyAuth/easyauth.db",
        )


def exact_snapshot(source: Path) -> dict:
    files = {}
    total_bytes = 0
    for source_relative, path, target_relative in source_target_pairs(source):
        stat = path.stat()
        total_bytes += stat.st_size
        files[source_relative] = {
            "target": target_relative,
            "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": sha256(path),
        }
    return {
        "schema": 1,
        "source": str(source),
        "created_unix_ns": time.time_ns(),
        "file_count": len(files),
        "bytes": total_bytes,
        "files": files,
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load_baseline(path: Path, source: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1 or not isinstance(value.get("files"), dict):
        raise ValueError("unsupported or malformed baseline manifest")
    if Path(value.get("source", "")).resolve() != source:
        raise ValueError("baseline source directory does not match --source-game-dir")
    return value


def snapshot_diff(baseline: dict, current: dict) -> dict:
    before = baseline["files"]
    after = current["files"]
    deleted = sorted(set(before) - set(after))
    added = sorted(set(after) - set(before))
    changed = sorted(
        path
        for path in set(before) & set(after)
        if before[path]["sha256"] != after[path]["sha256"]
    )
    unchanged = len(set(before) & set(after)) - len(changed)
    return {
        "added": added,
        "changed": changed,
        "deleted": deleted,
        "unchanged": unchanged,
        "changed_bytes": sum(after[path]["bytes"] for path in added + changed),
    }


def assert_source_stopped(source: Path) -> None:
    lock_path = source / "world" / "session.lock"
    if not lock_path.exists():
        return
    if os.name != "nt":
        raise RuntimeError("cannot prove source server is stopped on this platform")
    import msvcrt

    # A read-only handle is sufficient for the byte-range probe and preserves
    # the source directory's immutable contract.
    with lock_path.open("rb") as stream:
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("source world session.lock is held; stop the server first") from exc
        else:
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def validate_delta(diff: dict) -> None:
    if diff["deleted"]:
        raise RuntimeError(
            f"source files were deleted after baseline ({len(diff['deleted'])}); "
            "refresh is blocked pending explicit review"
        )
    unknown_configs = sorted(
        path
        for path in diff["added"] + diff["changed"]
        if path.startswith("config/") and path not in SPECIAL_CONFIGS
    )
    if unknown_configs:
        raise RuntimeError(
            "Fabric config files changed after baseline and have no audited automatic "
            f"mapping: {unknown_configs[:10]}"
        )
    unknown_saveddata = sorted(
        path
        for path in diff["added"] + diff["changed"]
        if path.startswith("world/data/") and path not in SPECIAL_DATA
    )
    if unknown_saveddata:
        raise RuntimeError(
            "SavedData files changed after baseline and have no audited downgrade "
            f"mapping: {unknown_saveddata[:10]}"
        )


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".cutover.tmp")
    shutil.copy2(source, temporary)
    if sha256(source) != sha256(temporary):
        temporary.unlink(missing_ok=True)
        raise IOError(f"copy hash mismatch for {source}")
    os.replace(temporary, target)


def run_tool(label: str, args: list[str], env: dict[str, str], records: list[dict]) -> None:
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=str(Path(__file__).resolve().parent),
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    record = {
        "label": label,
        "returncode": completed.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    records.append(record)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} failed with exit {completed.returncode}")


def build_environment(staging: Path) -> dict[str, str]:
    temp = staging.parent / "cutover-delta-temp"
    temp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "TEMP": str(temp),
            "TMP": str(temp),
            "PYTHONPYCACHEPREFIX": str(temp / "pycache"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(Path(r"<AUDIT_ROOT>\poi-nbtdeps")),
        }
    )
    return env


def copy_delta(source: Path, staging: Path, current: dict, paths: list[str]) -> None:
    for source_relative in paths:
        source_path = source / Path(source_relative)
        target_path = staging / Path(current["files"][source_relative]["target"])
        atomic_copy(source_path, target_path)


def transaction_targets(staging: Path, current: dict, changed: list[str]) -> list[Path]:
    targets = {
        staging / Path(current["files"][source_relative]["target"])
        for source_relative in changed
    }
    # The generic converter may update these even when the source-side file did
    # not change, and the dedicated converters produce these target-only files.
    targets.update(
        {
            staging / "server.properties",
            staging / "world" / "level.dat",
            staging / "config" / "mineastr-common.toml",
            staging / "world" / "xiyus_player_data.json",
        }
    )
    return sorted(targets, key=lambda path: str(path).lower())


def backup_targets(staging: Path, targets: list[Path], transaction: Path) -> dict:
    if transaction.exists():
        raise FileExistsError(f"transaction directory already exists: {transaction}")
    backup_root = transaction / "backup"
    backup_root.mkdir(parents=True)
    entries = []
    for target in targets:
        resolved = target.resolve()
        try:
            relative = resolved.relative_to(staging).as_posix()
        except ValueError as exc:
            raise ValueError(f"transaction target escapes staging: {resolved}") from exc
        entry = {"path": relative, "existed": resolved.is_file()}
        if resolved.is_file():
            backup = backup_root / Path(relative)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(resolved, backup)
            entry["sha256"] = sha256(resolved)
        entries.append(entry)
    manifest = {"schema": 1, "staging": str(staging), "entries": entries}
    atomic_json(transaction / "manifest.json", manifest)
    return manifest


def restore_targets(staging: Path, transaction: Path, manifest: dict) -> None:
    backup_root = transaction / "backup"
    for entry in manifest["entries"]:
        target = staging / Path(entry["path"])
        if entry["existed"]:
            backup = backup_root / Path(entry["path"])
            if not backup.is_file() or sha256(backup) != entry["sha256"]:
                raise IOError(f"transaction backup is missing or corrupt: {backup}")
            atomic_copy(backup, target)
        else:
            target.unlink(missing_ok=True)
    atomic_json(transaction / "rollback-complete.json", {"status": "ROLLED_BACK"})


def run_delta_converters(
    source: Path,
    staging: Path,
    changed: list[str],
    report_dir: Path,
    env: dict[str, str],
    records: list[dict],
    waypoint_jar: Path,
) -> None:
    tools = Path(__file__).resolve().parent
    world = staging / "world"
    changed_regions = sorted(
        path[len("world/") :]
        for path in changed
        if path.startswith("world/") and path.endswith(".mca")
    )
    generic_world_inputs = any(
        path == "world/level.dat"
        or path.startswith("world/playerdata/")
        or path.startswith("world/advancements/")
        or path.startswith("world/stats/")
        or path.endswith(".mca")
        for path in changed
    )
    if generic_world_inputs:
        region_args = []
        for relative in changed_regions or ["__no_changed_regions__"]:
            region_args.extend(("--only-region", relative))
        run_tool(
            "world-delta-convert",
            [
                str(tools / "convert_world_nbt.py"),
                "convert",
                "--world",
                str(world),
                "--report",
                str(report_dir / "world-delta-convert.json"),
                "--source-game-dir",
                str(source),
                "--target-game-dir",
                str(staging),
                "--waypoint-fire-compat-jar",
                str(waypoint_jar),
                "--waypoint-fire-compat-sha256",
                WAYPOINT_SHA256,
                *region_args,
            ],
            env,
            records,
        )

    for relative, kind in (
        ("world/data/create_tracks.dat", "tracks"),
        ("world/data/create_logistics.dat", "logistics"),
    ):
        if relative not in changed:
            continue
        target = staging / Path(relative)
        temporary = target.with_name(target.name + ".migration.tmp")
        run_tool(
            f"create-{kind}-delta",
            [
                str(tools / "convert_create_saveddata.py"),
                str(target),
                "--kind",
                kind,
                "--output",
                str(temporary),
                "--report",
                str(report_dir / f"create-{kind}-delta.json"),
                "--source-game-dir",
                str(source),
                "--target-game-dir",
                str(staging),
            ],
            env,
            records,
        )
        os.replace(temporary, target)

    if "config/mineastr-common.json" in changed:
        run_tool(
            "mineastr-config-delta",
            [
                str(tools / "migrate_mineastr_config.py"),
                str(source / "config" / "mineastr-common.json"),
                "--output",
                str(staging / "config" / "mineastr-common.toml"),
                "--report",
                str(report_dir / "mineastr-config-delta.json"),
            ],
            env,
            records,
        )
    if "world/data/mineastr_sign_translations.dat" in changed:
        run_tool(
            "mineastr-cache-delta",
            [
                str(tools / "migrate_mineastr_cache.py"),
                str(source / "world" / "data" / "mineastr_sign_translations.dat"),
                "--output",
                str(staging / "world" / "data" / "mineastr_sign_translations.dat"),
                "--report",
                str(report_dir / "mineastr-cache-delta.json"),
                "--promote-automatic",
            ],
            env,
            records,
        )
    if "EasyAuth/easyauth.db" in changed:
        run_tool(
            "xiyuslogin-delta",
            [
                str(
                    Path(
                        r"<AUDIT_ROOT>\XiyusLogin-migration\tools\migrate_easyauth.py"
                    )
                ),
                str(source / "EasyAuth" / "easyauth.db"),
                str(staging / "world" / "xiyus_player_data.json"),
                "--manifest",
                str(report_dir / "xiyuslogin-delta.json"),
                "--force",
            ],
            env,
            records,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Exact incremental cutover refresh")
    parser.add_argument("phase", choices=("snapshot", "diff", "refresh"))
    parser.add_argument("--source-game-dir", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--staging-game-dir", type=Path, default=STAGING_DEFAULT)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--waypoint-fire-jar", type=Path, default=WAYPOINT_JAR_DEFAULT)
    parser.add_argument("--skip-source-lock-check", action="store_true")
    args = parser.parse_args()

    source = ensure_d_path(args.source_game_dir, "source-game-dir")
    staging = ensure_d_path(args.staging_game_dir, "staging-game-dir")
    ensure_distinct(source, staging)
    baseline_path = ensure_d_path(args.baseline, "baseline")
    report_path = ensure_d_path(args.report, "report")

    if args.phase in {"snapshot", "refresh"} and not args.skip_source_lock_check:
        assert_source_stopped(source)
    current = exact_snapshot(source)
    if args.phase == "snapshot":
        atomic_json(baseline_path, current)
        atomic_json(
            report_path,
            {
                "status": "SNAPSHOT_CREATED",
                "baseline": str(baseline_path),
                "source": str(source),
                "file_count": current["file_count"],
                "bytes": current["bytes"],
            },
        )
        return 0

    baseline = load_baseline(baseline_path, source)
    diff = snapshot_diff(baseline, current)
    result = {
        "schema": 1,
        "phase": args.phase,
        "source": str(source),
        "staging": str(staging),
        "baseline": str(baseline_path),
        "diff": diff,
        "commands": [],
    }
    if args.phase == "diff":
        result["status"] = "NO_CHANGES" if not any(diff[key] for key in ("added", "changed", "deleted")) else "CHANGES_FOUND"
        atomic_json(report_path, result)
        return 0

    validate_delta(diff)
    changed = diff["added"] + diff["changed"]
    if not changed:
        result["status"] = "NO_CHANGES"
        atomic_json(report_path, result)
        return 0
    if not staging.is_dir():
        raise FileNotFoundError(f"staging directory does not exist: {staging}")
    waypoint_jar = args.waypoint_fire_jar.resolve()
    if sha256(waypoint_jar).upper() != WAYPOINT_SHA256:
        raise RuntimeError("waypoint/fire runtime hash does not match the locked candidate")

    report_dir = report_path.parent / "delta-details"
    env = build_environment(staging)
    transaction = report_path.parent / (
        "delta-transaction-" + str(current["created_unix_ns"])
    )
    manifest = backup_targets(
        staging, transaction_targets(staging, current, changed), transaction
    )
    result["transaction"] = str(transaction)
    try:
        copy_delta(source, staging, current, changed)
        run_delta_converters(
            source,
            staging,
            changed,
            report_dir,
            env,
            result["commands"],
            waypoint_jar,
        )
    except Exception as exc:
        restore_targets(staging, transaction, manifest)
        result["status"] = "ROLLED_BACK"
        result["error"] = f"{type(exc).__name__}: {exc}"
        atomic_json(report_path, result)
        raise
    atomic_json(transaction / "commit.json", {"status": "COMMITTED"})
    result["status"] = "REFRESHED"
    atomic_json(report_path, result)
    atomic_json(baseline_path, current)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"cutover delta failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
