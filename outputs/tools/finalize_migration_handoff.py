from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE = Path(r"D:\Trans\migration-handoff-20260812.building")
WORKSPACE = Path(__file__).resolve().parents[2]
OUTPUTS = WORKSPACE / "outputs"

KEEP_LARGE_REPORTS = {
    "incoming-20260811-world-dryrun-candidate13-20260812.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    if not PACKAGE.is_dir():
        raise SystemExit(f"package directory missing: {PACKAGE}")

    # Unicode-safe duplicate cleanup: keep only the ASCII-named copies.
    duplicate_rows: list[dict[str, object]] = []
    for directory, keep_name, expected_sha in (
        (PACKAGE / "01-original", "resource-pack-original.zip", "BF88450FF0EED414657DC75CC1F0FD6689109A654DEEC8CF5306A13C3900CCCC"),
        (PACKAGE / "02-latest", "resource-pack-mc1.21.1-candidate13.zip", "614ABDF34F7CFDB7974474A645BFA71CC4CA2E67F609983616E61474A57E3364"),
    ):
        keep = directory / keep_name
        if not keep.is_file() or sha256(keep) != expected_sha:
            raise SystemExit(f"locked resource pack missing or hash mismatch: {keep}")
        protected_names = {keep_name}
        if directory.name == "01-original":
            protected_names.add("20260811.zip")
        for candidate in directory.glob("*.zip"):
            if candidate.name in protected_names:
                continue
            row = {"path": str(candidate), "bytes": candidate.stat().st_size, "sha256": sha256(candidate), "action": "removed_package_duplicate"}
            duplicate_rows.append(row)
            candidate.unlink()

    report_root = PACKAGE / "04-reports-and-docs" / "outputs-root"
    omitted_reports: list[dict[str, object]] = []
    if report_root.is_dir():
        for candidate in sorted(report_root.glob("*.json")):
            if candidate.stat().st_size <= 5 * 1024 * 1024 or candidate.name in KEEP_LARGE_REPORTS:
                continue
            source = OUTPUTS / candidate.name
            row = {
                "package_copy": str(candidate),
                "original_path": str(source),
                "bytes": candidate.stat().st_size,
                "sha256": sha256(candidate),
                "reason": "repeated full-world audit; representative report retained",
            }
            omitted_reports.append(row)
            candidate.unlink()

    # Make the handoff docs available at the package root with ASCII filenames.
    handoff_docs = WORKSPACE / "outputs" / "handoff-20260812"
    readmes = sorted(handoff_docs.glob("README-*.md"))
    if not readmes:
        raise SystemExit("handoff README missing")
    shutil.copy2(readmes[0], PACKAGE / "README-handoff.md")
    for name in ("TODO.md", "AUTHORITATIVE-INPUTS.json", "P0-STATUS.md", "HISTORY-POLICY.md"):
        source = handoff_docs / name
        if not source.is_file():
            raise SystemExit(f"handoff document missing: {source}")
        shutil.copy2(source, PACKAGE / name)

    index_dir = PACKAGE / "05-superseded-index"
    write_json(index_dir / "large-reports-not-packed.json", {
        "schema": 1,
        "status": "INDEX_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kept_representative_reports": sorted(KEEP_LARGE_REPORTS),
        "omitted_reports": omitted_reports,
        "duplicate_package_files_removed": duplicate_rows,
    })

    status = {
        "schema": 3,
        "status": "FINALIZING",
        "package": str(PACKAGE),
        "large_reports_omitted": len(omitted_reports),
        "package_duplicates_removed": len(duplicate_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(PACKAGE / "PACKAGE-STATUS.json", status)
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
