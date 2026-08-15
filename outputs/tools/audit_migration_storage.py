from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import stat
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
WORLD_MARKERS = {
    "level.dat",
    "server.properties",
    "session.lock",
}
WORLD_DIR_MARKERS = {"region", "entities", "playerdata", "DIM-1", "DIM1"}
RUNTIME_MARKERS = {"logs", "crash-reports", "mods", "config", "user_jvm_args.txt"}


def is_reparse(path: Path) -> bool:
    try:
        st = os.stat(path, follow_symlinks=False)
        return path.is_symlink() or bool(getattr(st, "st_file_attributes", 0) & REPARSE_POINT)
    except OSError:
        return False


def safe_sha256(path: Path, limit: int = 16 * 1024 * 1024) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest().upper()
    except OSError:
        return None


def scan_tree(root: Path) -> dict[str, object]:
    started = time.monotonic()
    total_bytes = 0
    file_count = 0
    dir_count = 0
    errors: list[str] = []
    reparse_paths: list[str] = []
    marker_hits: Counter[str] = Counter()
    largest: list[tuple[int, str]] = []
    stack = [root]

    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if is_reparse(path):
                                reparse_paths.append(path.as_posix())
                                continue
                            dir_count += 1
                            if entry.name in WORLD_DIR_MARKERS:
                                marker_hits[f"dir:{entry.name}"] += 1
                            stack.append(path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        if is_reparse(path):
                            reparse_paths.append(path.as_posix())
                            continue
                        size = entry.stat(follow_symlinks=False).st_size
                        file_count += 1
                        total_bytes += size
                        if entry.name in WORLD_MARKERS or entry.name in RUNTIME_MARKERS:
                            marker_hits[f"file:{entry.name}"] += 1
                        largest.append((size, path.as_posix()))
                    except OSError as exc:
                        errors.append(f"{path}: {exc}")
        except OSError as exc:
            errors.append(f"{current}: {exc}")

    largest.sort(reverse=True)
    key_hashes: dict[str, str] = {}
    for name in ("level.dat", "server.properties", "READY.json", "release-lock.json", "PACKAGE-STATUS.json"):
        candidate = root / name
        if candidate.is_file():
            digest = safe_sha256(candidate)
            if digest:
                key_hashes[name] = digest
    world_like = bool(marker_hits.get("file:level.dat") or marker_hits.get("dir:region"))
    runtime_like = bool(marker_hits.get("file:server.properties") or marker_hits.get("dir:logs"))
    return {
        "path": root.as_posix(),
        "bytes": total_bytes,
        "file_count": file_count,
        "directory_count": dir_count,
        "world_like": world_like,
        "runtime_like": runtime_like,
        "marker_hits": dict(sorted(marker_hits.items())),
        "reparse_skipped": len(reparse_paths),
        "reparse_examples": sorted(reparse_paths)[:20],
        "errors": errors[:50],
        "error_count": len(errors),
        "key_hashes": key_hashes,
        "largest_files": [
            {"bytes": size, "path": path}
            for size, path in largest[-50:][::-1]
        ],
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def classify(path: Path, root_name: str) -> tuple[str, str]:
    text = path.as_posix().lower()
    name = path.name.lower()
    if "migration-handoff-20260812" in text:
        return "KEEP_AUTHORITY", "最终交接目录/归档及其校验文件"
    if name == "20260811.zip" or name == "世界指定资源包喵.zip":
        return "KEEP_SOURCE", "用户原始输入，必须只读保留"
    if "cutover-staging-incoming-20260811-candidate13" in text:
        return "KEEP_FROZEN_REFERENCE", "冻结基线；交接包已有副本，删除前需人工确认"
    if "final-mod-bundles-candidate14-r3" in text:
        return "KEEP_RELEASE_REFERENCE", "当前唯一发布快照，非永久模组数量上限"
    if "outputs/projects" in text or "outputs/tools" in text or "d-trans-1-21-11-1" in text:
        if any(token in text for token in ("manual-test", "client-gate", "runtime-attempt", "fullstack-smoke")):
            return "DELETE_AFTER_REVIEW", "运行后测试副本；交接包仅保留摘要和证据"
        return "KEEP_ENGINEERING", "源码、工具、测试或关键文档"
    if any(token in name for token in ("manual-test", "client-gate", "runtime-attempt", "fullstack-smoke", "smoke", "attempt")):
        return "DELETE_AFTER_REVIEW", "启动/保存过的候选运行副本，不可作为转换输入"
    if any(token in name for token in ("cutover-staging", "final-server-mods", "final-client-mods", "final-mod-bundles")):
        return "DELETE_AFTER_REVIEW", "被后续版本淘汰的 staging/release"
    if any(token in name for token in ("gradle-cache", "gradle-home", "decompiled", "unpacked", "jar-inspect", "anvildeps", "converter-temp", "test-temp", "pycache")):
        return "DELETE_AFTER_REVIEW", "构建/反编译/测试缓存，不是业务数据"
    if root_name.lower() in {"downloads", "resourcepacks", "instances"}:
        return "MANUAL_REVIEW", "外部工具或用户目录，需按实例/文件逐项确认"
    return "MANUAL_REVIEW", "未能安全归类；保留并交人工审核"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only C/D migration storage inventory")
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.workers <= 24:
        raise SystemExit("workers must be 1..24")
    roots = []
    for raw in args.root:
        path = raw.resolve()
        if not path.exists():
            continue
        roots.append(path)
    if not roots:
        raise SystemExit("no roots exist")

    started = time.monotonic()
    top_jobs: list[tuple[Path, str]] = []
    root_files: list[dict[str, object]] = []
    for root in roots:
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False) and not is_reparse(path):
                        top_jobs.append((path, root.name))
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            root_files.append({
                                "path": path.as_posix(),
                                "bytes": entry.stat(follow_symlinks=False).st_size,
                                "sha256_if_small": safe_sha256(path),
                                "category": classify(path, root.name)[0],
                            })
                        except OSError:
                            pass
        except OSError:
            continue

    def run(job: tuple[Path, str]) -> dict[str, object]:
        path, root_name = job
        record = scan_tree(path)
        category, reason = classify(path, root_name)
        record["root"] = root_name
        record["name"] = path.name
        record["category"] = category
        record["category_reason"] = reason
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.workers, max(1, len(top_jobs)))) as pool:
        records = list(pool.map(run, sorted(top_jobs, key=lambda item: item[0].as_posix().lower())))
    records.sort(key=lambda item: str(item["path"]).lower())

    category_totals: dict[str, dict[str, int]] = {}
    for record in records:
        category = str(record["category"])
        row = category_totals.setdefault(category, {"directories": 0, "bytes": 0, "files": 0})
        row["directories"] += 1
        row["bytes"] += int(record["bytes"])
        row["files"] += int(record["file_count"])
    largest = sorted(
        (
            {"bytes": int(record["bytes"]), "file_count": int(record["file_count"]), "path": str(record["path"]), "category": record["category"]}
            for record in records
        ),
        key=lambda row: row["bytes"],
        reverse=True,
    )[:100]

    report = {
        "schema": 1,
        "status": "PASS_READ_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "roots": [path.as_posix() for path in roots],
        "workers": args.workers,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "policy": {
            "writes_to_scanned_roots": False,
            "deletions": False,
            "java_started": False,
            "reparse_points_followed": False,
            "recommendation_is_not_authorization": True,
        },
        "root_files": sorted(root_files, key=lambda row: str(row["path"]).lower()),
        "top_level_directories": records,
        "category_totals": dict(sorted(category_totals.items())),
        "largest_top_level_directories": largest,
        "summary": {
            "top_level_directory_count": len(records),
            "root_file_count": len(root_files),
            "total_bytes": sum(int(record["bytes"]) for record in records) + sum(int(row["bytes"]) for row in root_files),
            "total_files": sum(int(record["file_count"]) for record in records) + len(root_files),
            "world_like_directories": sum(bool(record["world_like"]) for record in records),
            "runtime_like_directories": sum(bool(record["runtime_like"]) for record in records),
            "scan_errors": sum(int(record["error_count"]) for record in records),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, args.report)
    print(json.dumps({"status": report["status"], "directories": len(records), "bytes": report["summary"]["total_bytes"], "report": args.report.as_posix()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
