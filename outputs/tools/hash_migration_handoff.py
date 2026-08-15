from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


EXCLUDED_NAMES = {"MANIFEST-SHA256.json", "MANIFEST-SHA256.txt", "PACKAGE-STATUS.json"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def record(root: Path, path: Path) -> dict[str, object]:
    stat_before = path.stat()
    digest = sha256(path)
    stat_after = path.stat()
    if stat_before.st_size != stat_after.st_size or stat_before.st_mtime_ns != stat_after.st_mtime_ns:
        raise RuntimeError(f"file changed while hashing: {path}")
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": stat_after.st_size,
        "sha256": digest,
    }


def atomic_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.drive.upper() != "D:":
        raise SystemExit(f"handoff must be on D: {root}")
    if not root.is_dir():
        raise SystemExit(f"handoff directory missing: {root}")
    if not 1 <= args.workers <= 20:
        raise SystemExit("workers must be 1..20")

    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name not in EXCLUDED_NAMES
    )
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda path: record(root, path), files))
    rows.sort(key=lambda row: str(row["path"]))

    sections: Counter[str] = Counter()
    section_files: Counter[str] = Counter()
    total_bytes = 0
    aggregate = hashlib.sha256()
    for row in rows:
        section = str(row["path"]).split("/", 1)[0]
        sections[section] += int(row["bytes"])
        section_files[section] += 1
        total_bytes += int(row["bytes"])
        aggregate.update(f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8"))

    value = {
        "schema": 1,
        "status": "PASS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_name": root.name,
        "file_count": len(rows),
        "bytes": total_bytes,
        "aggregate_sha256": aggregate.hexdigest().upper(),
        "workers": args.workers,
        "sections": [
            {"name": name, "file_count": section_files[name], "bytes": sections[name]}
            for name in sorted(sections)
        ],
        "files": rows,
    }
    atomic_text(root / "MANIFEST-SHA256.json", json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(
        root / "MANIFEST-SHA256.txt",
        "".join(f"{row['sha256']}  {row['path']}\n" for row in rows),
    )
    status_path = root / "PACKAGE-STATUS.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
    status.update({
        "status": "READY_TO_ARCHIVE",
        "manifest_file_count": len(rows),
        "manifest_bytes": total_bytes,
        "manifest_aggregate_sha256": value["aggregate_sha256"],
        "manifest_workers": args.workers,
        "manifest_generated_at": value["generated_at"],
    })
    atomic_text(status_path, json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value[key] for key in ("status", "file_count", "bytes", "aggregate_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
