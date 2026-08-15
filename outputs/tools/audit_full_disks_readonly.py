from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPARSE_POINT = 0x400
GIB = 1024**3
LARGE_FILE = 1 * GIB
LARGE_DIR = 1 * GIB

NAME_KEYWORDS = (
    "migration",
    "candidate",
    "staging",
    "smoke",
    "runtime",
    "world",
    "backup",
    "handoff",
    "server",
    "client-gate",
    "fullstack",
    "gradle-cache",
    "gradle-home",
    "decompile",
    "unpacked",
    "validation",
    "audit",
    "archive",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_reparse(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & REPARSE_POINT) or stat.S_ISLNK(st.st_mode)


def safe_stat(path: str, follow_symlinks: bool = False):
    try:
        return os.stat(path, follow_symlinks=follow_symlinks)
    except (OSError, ValueError):
        return None


def classify(path: str, name: str, marker_hits: Counter[str], bytes_value: int) -> tuple[str, int]:
    lowered = (path + "\\" + name).lower()
    score = 0
    reasons: list[str] = []
    for keyword in NAME_KEYWORDS:
        if keyword in lowered:
            score += 1
            reasons.append(f"name:{keyword}")
    if marker_hits.get("level.dat", 0):
        score += 4
        reasons.append("level.dat")
    if marker_hits.get("region", 0):
        score += 4
        reasons.append("region")
    if marker_hits.get("session.lock", 0):
        score += 3
        reasons.append("session.lock")
    if marker_hits.get("server.properties", 0):
        score += 2
        reasons.append("server.properties")
    if marker_hits.get("mods", 0):
        score += 1
        reasons.append("mods")
    if bytes_value >= LARGE_DIR:
        score += 1
        reasons.append("large")
    if score >= 7:
        category = "LIKELY_RUNTIME_OR_WORLD"
    elif score >= 4:
        category = "POSSIBLE_MIGRATION_OR_GAME_DATA"
    elif score >= 2:
        category = "NAMED_OR_LARGE_REVIEW"
    else:
        category = "OTHER"
    return category, score


def scan_root(root: Path, progress_path: Path, progress_every: int) -> dict:
    started = time.monotonic()
    root = root.resolve()
    totals = {"files": 0, "bytes": 0, "directories": 0, "errors": 0, "reparse_skipped": 0}
    top: dict[str, dict] = {}
    stack: list[tuple[str, str | None]] = [(str(root), None)]
    largest_files: list[dict] = []
    candidate_dirs: dict[str, dict] = {}
    archives: list[dict] = []
    extension_bytes: Counter[str] = Counter()
    extension_files: Counter[str] = Counter()
    progress_files = 0

    def push_progress(event: str, current: str | None = None) -> None:
        record = {
            "time_utc": utc_now(),
            "event": event,
            "root": str(root),
            "files": totals["files"],
            "bytes": totals["bytes"],
            "directories": totals["directories"],
            "errors": totals["errors"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        if current:
            record["current"] = current
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    push_progress("ROOT_START")
    while stack:
        current, top_name = stack.pop()
        try:
            entries = list(os.scandir(current))
        except (OSError, PermissionError) as exc:
            totals["errors"] += 1
            push_progress("SCAN_ERROR", current)
            continue
        totals["directories"] += 1
        if top_name is not None and top_name not in top:
            top[top_name] = {
                "path": str(Path(root) / top_name),
                "bytes": 0,
                "files": 0,
                "directories": 0,
                "errors": 0,
                "marker_hits": Counter(),
                "largest_files": [],
            }
        local = top.get(top_name) if top_name is not None else None
        local_marker_hits = local["marker_hits"] if local is not None else Counter()
        for entry in entries:
            entry_path = entry.path
            try:
                st = entry.stat(follow_symlinks=False)
            except (OSError, ValueError):
                totals["errors"] += 1
                if local is not None:
                    local["errors"] += 1
                continue
            if is_reparse(st):
                totals["reparse_skipped"] += 1
                continue
            if entry.is_dir(follow_symlinks=False):
                child_top = entry.name if top_name is None else top_name
                stack.append((entry_path, child_top))
                if local is not None:
                    local["directories"] += 1
                continue
            size = int(st.st_size)
            totals["files"] += 1
            totals["bytes"] += size
            if local is not None:
                local["files"] += 1
                local["bytes"] += size
            suffix = Path(entry.name).suffix.lower() or "<none>"
            extension_bytes[suffix] += size
            extension_files[suffix] += 1
            name_lower = entry.name.lower()
            if name_lower in ("level.dat", "session.lock", "server.properties", "ops.json", "whitelist.json"):
                local_marker_hits[name_lower] += 1
            if name_lower in ("region", "entities", "poi"):
                local_marker_hits[name_lower] += 1
            if entry.name.lower() == "mods":
                local_marker_hits["mods"] += 1
            if size >= LARGE_FILE:
                largest_files.append({"path": entry_path, "bytes": size, "mtime": st.st_mtime})
                largest_files.sort(key=lambda x: x["bytes"], reverse=True)
                del largest_files[1000:]
            if suffix in (".zip", ".7z", ".tar", ".gz", ".rar", ".zst"):
                archives.append({"path": entry_path, "bytes": size, "mtime": st.st_mtime})
            progress_files += 1
            if progress_files % progress_every == 0:
                push_progress("PROGRESS", entry_path)

    for name, row in top.items():
        markers = dict(row.pop("marker_hits"))
        category, score = classify(row["path"], name, Counter(markers), row["bytes"])
        row["marker_hits"] = markers
        row["category"] = category
        row["score"] = score
        row["gib"] = round(row["bytes"] / GIB, 3)
        if score >= 4 or row["bytes"] >= LARGE_DIR:
            candidate_dirs[name] = row.copy()
    archives.sort(key=lambda x: x["bytes"], reverse=True)
    push_progress("ROOT_DONE")
    return {
        "root": str(root),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "summary": {
            **totals,
            "gib": round(totals["bytes"] / GIB, 3),
            "extension_count": len(extension_files),
        },
        "top_level_directories": sorted(top.values(), key=lambda x: x["bytes"], reverse=True),
        "candidate_or_large_directories": sorted(candidate_dirs.values(), key=lambda x: x["bytes"], reverse=True),
        "largest_files_over_1gib": largest_files,
        "largest_archives": archives[:500],
        "extension_totals": [
            {"extension": ext, "files": extension_files[ext], "bytes": extension_bytes[ext], "gib": round(extension_bytes[ext] / GIB, 3)}
            for ext in sorted(extension_bytes, key=extension_bytes.get, reverse=True)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", nargs="+", default=["C:\\", "D:\\"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--progress-every", type=int, default=100_000)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.progress.parent.mkdir(parents=True, exist_ok=True)
    args.progress.write_text("", encoding="utf-8")
    started = time.monotonic()
    report = {
        "schema": 1,
        "status": "RUNNING",
        "started_at_utc": utc_now(),
        "roots": [str(Path(root).resolve()) for root in args.roots],
        "policy": {
            "read_only": True,
            "follow_reparse_points": False,
            "content_hashing": False,
            "large_file_threshold_bytes": LARGE_FILE,
            "large_directory_threshold_bytes": LARGE_DIR,
        },
        "root_reports": [],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for root in args.roots:
        result = scan_root(Path(root), args.progress, args.progress_every)
        report["root_reports"].append(result)
        report["last_completed_root"] = str(Path(root).resolve())
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["status"] = "PASS_READ_ONLY"
    report["finished_at_utc"] = utc_now()
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output), "elapsed_seconds": report["elapsed_seconds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
