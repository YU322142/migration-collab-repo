#!/usr/bin/env python3
"""Read-only audit of the Cookery migration.3 -> migration.4 rebuilds.

The only writes are the requested JSON/Markdown audit reports.  No JAR is
installed and no Java, Gradle, Minecraft, or Prism process is started.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile


ROOT = Path(r"D:\Trans\migration-audit-work\kaleidoscope-cookery-chopping-board-fix-20260814")
BASELINE_SERVER = (
    Path(r"D:\Trans\migration-audit-work\mechanomania-matched-release-v3-20260814\server\mods")
    / "kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar"
)
BASELINE_CLIENT = (
    Path(r"D:\Trans\migration-audit-work\mechanomania-matched-release-v3-20260814\client\mods")
    / "kaleidoscopecookery-1.4.1.7-migration.3-neoforge+mc1.21.1.jar"
)
BUILD1 = ROOT / "final-build1-kaleidoscopecookery-1.4.1.7-migration.4-neoforge+mc1.21.1.jar"
BUILD2 = ROOT / "final-build2-kaleidoscopecookery-1.4.1.7-migration.4-neoforge+mc1.21.1.jar"
BUILD1_STDOUT = ROOT / "final-build1.stdout.log"
BUILD1_STDERR = ROOT / "final-build1.stderr.log"
BUILD2_STDOUT = ROOT / "final-build2.stdout.log"
BUILD2_STDERR = ROOT / "final-build2.stderr.log"
FINAL_SELF_AUDIT = ROOT / "kaleidoscope-cookery-chopping-board-fix-final-build-audit.json"
PROJECT = Path(r"D:\Trans\migration-audit-work\KaleidoscopeCookery-1.21.1-neoforge")
DEFAULT_REPORT = ROOT / "independent-final-build-audit-20260814.json"
DEFAULT_MARKDOWN = ROOT / "independent-final-build-audit-20260814.md"

EXPECTED_OUTER_SHA256 = {
    "migration3": "A061FB1E953AD815144304F7567B30876DBBC07B8565069871771F0AAEB63D3F",
    "build1": "9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17",
    "build2": "9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17",
}
EXPECTED_SELF_AUDIT_SHA256 = "47194657EE629D8EB51BF79269CFAD4BF74C6E5B6987297F225C42D110B7CBAD"
EXPECTED_CLASSES = {
    "com/github/ysbbbbbb/kaleidoscopecookery/blockentity/kitchen/ChoppingBoardBlockEntity.class",
    "com/github/ysbbbbbb/kaleidoscopecookery/client/render/block/ChoppingBoardBlockEntityRender.class",
}
EXPECTED_VERSION_METADATA = {
    "META-INF/MANIFEST.MF",
    "META-INF/neoforge.mods.toml",
}
EXPECTED_CHANGED = EXPECTED_CLASSES | EXPECTED_VERSION_METADATA
OLD_VERSION = "1.4.1.7-migration.3-neoforge+mc1.21.1"
NEW_VERSION = "1.4.1.7-migration.4-neoforge+mc1.21.1"


class AuditError(RuntimeError):
    pass


def sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def file_lock(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise AuditError(f"missing regular file: {path}")
    digest = sha256(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise AuditError(f"SHA-256 drift: {path}: {digest} != {expected_sha256}")
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest}


def entry_content_digest(entries: dict[str, dict[str, Any]], prefix: str | None = None) -> str:
    digest = hashlib.sha256()
    for name in sorted(entries, key=str.casefold):
        if prefix is not None and not name.startswith(prefix):
            continue
        row = entries[name]
        digest.update(f"{name}\0{row['size']}\0{row['sha256']}\n".encode("utf-8"))
    return digest.hexdigest().upper()


def resource_digest(entries: dict[str, dict[str, Any]]) -> tuple[int, str]:
    names = sorted(
        (name for name in entries if name.startswith(("assets/", "data/"))),
        key=str.casefold,
    )
    digest = hashlib.sha256()
    for name in names:
        row = entries[name]
        digest.update(f"{name}\0{row['size']}\0{row['sha256']}\n".encode("utf-8"))
    return len(names), digest.hexdigest().upper()


def inspect_jar(path: Path, expected_sha256: str) -> dict[str, Any]:
    lock = file_lock(path, expected_sha256)
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            infos = archive.infolist()
            names = [info.filename for info in infos]
            exact_duplicates = sorted({name for name in names if names.count(name) > 1}, key=str.casefold)
            folded: dict[str, list[str]] = {}
            for name in names:
                folded.setdefault(name.casefold(), []).append(name)
            case_duplicates = sorted(
                {variant for variants in folded.values() if len(variants) > 1 for variant in variants},
                key=str.casefold,
            )
            if bad is not None or exact_duplicates or case_duplicates:
                raise AuditError(
                    f"ZIP integrity failure {path}: bad={bad}, exact={exact_duplicates}, case={case_duplicates}"
                )
            entries: dict[str, dict[str, Any]] = {}
            for info in infos:
                raw = archive.read(info.filename)
                entries[info.filename] = {
                    "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest().upper(),
                    "crc32": f"{info.CRC:08X}",
                    "compressed_size": info.compress_size,
                    "compress_type": info.compress_type,
                    "date_time": list(info.date_time),
                    "flag_bits": info.flag_bits,
                    "external_attr": info.external_attr,
                    "internal_attr": info.internal_attr,
                    "create_system": info.create_system,
                    "create_version": info.create_version,
                    "extract_version": info.extract_version,
                    "volume": info.volume,
                    "extra_sha256": hashlib.sha256(info.extra).hexdigest().upper(),
                    "comment_sha256": hashlib.sha256(info.comment).hexdigest().upper(),
                }
            resource_count, resources = resource_digest(entries)
            return {
                "artifact": lock,
                "zip_crc": "PASS",
                "entry_count": len(names),
                "duplicate_entries": 0,
                "case_insensitive_duplicate_entries": 0,
                "entry_order_sha256": hashlib.sha256(("\n".join(names) + "\n").encode("utf-8")).hexdigest().upper(),
                "content_tree_sha256": entry_content_digest(entries),
                "gameplay_resource_entries": resource_count,
                "gameplay_resource_tree_sha256": resources,
                "archive_comment_sha256": hashlib.sha256(archive.comment).hexdigest().upper(),
                "names": names,
                "entries": entries,
            }
    except (OSError, zipfile.BadZipFile) as exc:
        raise AuditError(f"cannot inspect JAR {path}: {exc}") from exc


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    a = left["entries"]
    b = right["entries"]
    added = sorted(set(b) - set(a), key=str.casefold)
    removed = sorted(set(a) - set(b), key=str.casefold)
    common = set(a) & set(b)
    content_changed = sorted((name for name in common if a[name]["sha256"] != b[name]["sha256"]), key=str.casefold)
    metadata_fields = (
        "date_time",
        "compressed_size",
        "compress_type",
        "flag_bits",
        "external_attr",
        "internal_attr",
        "create_system",
        "create_version",
        "extract_version",
        "volume",
        "extra_sha256",
        "comment_sha256",
    )
    metadata_field_change_counts = {
        field: sum(a[name][field] != b[name][field] for name in common)
        for field in metadata_fields
    }
    resources_changed = sorted(
        name for name in content_changed if name.startswith(("assets/", "data/"))
    )
    return {
        "outer_sha256_equal": left["artifact"]["sha256"] == right["artifact"]["sha256"],
        "entry_order_equal": left["names"] == right["names"],
        "entry_sets_equal": not added and not removed,
        "added_entries": added,
        "removed_entries": removed,
        "content_changed_count": len(content_changed),
        "content_changed_entries": content_changed,
        "unchanged_content_entries": len(common) - len(content_changed),
        "metadata_field_change_counts": metadata_field_change_counts,
        "content_tree_sha256_equal": left["content_tree_sha256"] == right["content_tree_sha256"],
        "gameplay_resource_tree_sha256_equal": (
            left["gameplay_resource_tree_sha256"] == right["gameplay_resource_tree_sha256"]
        ),
        "gameplay_resource_changed_entries": resources_changed,
    }


def metadata_diff(baseline: dict[str, Any], target: dict[str, Any], name: str) -> list[str]:
    # Re-open only the two tiny text metadata files to retain a clear audit trail.
    with zipfile.ZipFile(Path(baseline["artifact"]["path"])) as left, zipfile.ZipFile(
        Path(target["artifact"]["path"])
    ) as right:
        before = left.read(name).decode("utf-8", errors="strict").splitlines()
        after = right.read(name).decode("utf-8", errors="strict").splitlines()
    return list(difflib.unified_diff(before, after, fromfile="migration.3", tofile="migration.4", lineterm=""))


def class_markers(jar: Path) -> dict[str, Any]:
    markers = {
        "com/github/ysbbbbbb/kaleidoscopecookery/blockentity/kitchen/ChoppingBoardBlockEntity.class": (
            b"EMPTY_MODEL_ID",
            b"fromNamespaceAndPath",
        ),
        "com/github/ysbbbbbb/kaleidoscopecookery/client/render/block/ChoppingBoardBlockEntityRender.class": (
            b"EMPTY_MODEL_ID",
            b"fromNamespaceAndPath",
            b"getMissingModel",
        ),
    }
    result: dict[str, Any] = {}
    with zipfile.ZipFile(jar) as archive:
        for name, expected in markers.items():
            raw = archive.read(name)
            states = {marker.decode("ascii"): marker in raw for marker in expected}
            if not all(states.values()):
                raise AuditError(f"expected fix markers are absent from {name}: {states}")
            result[name] = states
    return result


def log_lock(path: Path) -> dict[str, Any]:
    lock = file_lock(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lock.update(
        {
            "build_successful": "BUILD SUCCESSFUL" in text,
            "build_failed": "BUILD FAILED" in text,
        }
    )
    return lock


def audit(report_path: Path, markdown_path: Path) -> dict[str, Any]:
    if report_path.exists() or markdown_path.exists():
        raise AuditError("report paths must be fresh")
    if report_path.parent.resolve() != ROOT.resolve() or markdown_path.parent.resolve() != ROOT.resolve():
        raise AuditError(f"reports must remain in {ROOT}")

    logs = {
        "build1_stdout": log_lock(BUILD1_STDOUT),
        "build1_stderr": log_lock(BUILD1_STDERR),
        "build2_stdout": log_lock(BUILD2_STDOUT),
        "build2_stderr": log_lock(BUILD2_STDERR),
    }
    for name in ("build1_stdout", "build2_stdout"):
        if not logs[name]["build_successful"] or logs[name]["build_failed"]:
            raise AuditError(f"{name} is not a successful completed build log")

    baseline_server_lock = file_lock(BASELINE_SERVER, EXPECTED_OUTER_SHA256["migration3"])
    baseline_client_lock = file_lock(BASELINE_CLIENT, EXPECTED_OUTER_SHA256["migration3"])
    upstream_self_audit_lock = file_lock(FINAL_SELF_AUDIT, EXPECTED_SELF_AUDIT_SHA256)
    if baseline_server_lock["bytes"] != baseline_client_lock["bytes"]:
        raise AuditError("server/client migration.3 baselines differ")

    jars = {
        "migration3": inspect_jar(BASELINE_SERVER, EXPECTED_OUTER_SHA256["migration3"]),
        "build1": inspect_jar(BUILD1, EXPECTED_OUTER_SHA256["build1"]),
        "build2": inspect_jar(BUILD2, EXPECTED_OUTER_SHA256["build2"]),
    }
    reproducibility = compare(jars["build1"], jars["build2"])
    if (
        reproducibility["outer_sha256_equal"] is not True
        or
        reproducibility["entry_sets_equal"] is not True
        or reproducibility["entry_order_equal"] is not True
        or reproducibility["content_changed_entries"] != []
        or reproducibility["content_tree_sha256_equal"] is not True
    ):
        raise AuditError("build1/build2 content is not reproducible")
    zip_metadata_changes = {
        key: value
        for key, value in reproducibility["metadata_field_change_counts"].items()
        if value != 0
    }
    if zip_metadata_changes:
        raise AuditError(f"build1/build2 differ in ZIP metadata: {zip_metadata_changes}")

    migration_diffs = {
        "build1": compare(jars["migration3"], jars["build1"]),
        "build2": compare(jars["migration3"], jars["build2"]),
    }
    for name, comparison in migration_diffs.items():
        if set(comparison["content_changed_entries"]) != EXPECTED_CHANGED:
            raise AuditError(f"migration.3 -> {name} changed unexpected entries: {comparison['content_changed_entries']}")
        if comparison["added_entries"] or comparison["removed_entries"]:
            raise AuditError(f"migration.3 -> {name} changed the entry set")
        if comparison["gameplay_resource_changed_entries"]:
            raise AuditError(f"migration.3 -> {name} changed gameplay resources")

    manifest_diff = metadata_diff(jars["migration3"], jars["build1"], "META-INF/MANIFEST.MF")
    mods_toml_diff = metadata_diff(jars["migration3"], jars["build1"], "META-INF/neoforge.mods.toml")
    joined_metadata = "\n".join((*manifest_diff, *mods_toml_diff))
    if OLD_VERSION not in joined_metadata or NEW_VERSION not in joined_metadata:
        raise AuditError("version metadata diff is not the exact migration.3 -> migration.4 transition")

    class_evidence = {
        "build1": class_markers(BUILD1),
        "build2": class_markers(BUILD2),
    }
    source_files = {
        "block_entity": file_lock(
            PROJECT
            / "src/main/java/com/github/ysbbbbbb/kaleidoscopecookery/blockentity/kitchen/ChoppingBoardBlockEntity.java"
        ),
        "renderer": file_lock(
            PROJECT
            / "src/main/java/com/github/ysbbbbbb/kaleidoscopecookery/client/render/block/ChoppingBoardBlockEntityRender.java"
        ),
        "gradle_properties": file_lock(PROJECT / "gradle.properties"),
    }

    status = "PASS_BYTE_REPRODUCIBLE_SCOPE_AND_RESOURCE_PRESERVED"
    result: dict[str, Any] = {
        "schema": "kaleidoscope-cookery-migration4-independent-audit/v1",
        "status": status,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "read_only_jar_audit": True,
            "jar_installed": False,
            "java_started": False,
            "minecraft_started": False,
            "prism_touched": False,
        },
        "build_logs": logs,
        "upstream_self_audit": upstream_self_audit_lock,
        "artifacts": {
            "migration3_server": baseline_server_lock,
            "migration3_client": baseline_client_lock,
            "build1": jars["build1"]["artifact"],
            "build2": jars["build2"]["artifact"],
        },
        "zip_integrity": {
            name: {
                key: value
                for key, value in row.items()
                if key
                in {
                    "zip_crc",
                    "entry_count",
                    "duplicate_entries",
                    "case_insensitive_duplicate_entries",
                    "entry_order_sha256",
                    "content_tree_sha256",
                    "gameplay_resource_entries",
                    "gameplay_resource_tree_sha256",
                }
            }
            for name, row in jars.items()
        },
        "build1_vs_build2": {
            **reproducibility,
            "byte_identical": reproducibility["outer_sha256_equal"],
            "content_identical": reproducibility["content_tree_sha256_equal"],
            "all_zip_metadata_identical": not zip_metadata_changes,
            "strict_byte_reproducibility": "PASS",
            "semantic_content_reproducibility": "PASS",
        },
        "migration3_to_migration4": {
            "expected_changed_classes": sorted(EXPECTED_CLASSES),
            "expected_version_metadata": sorted(EXPECTED_VERSION_METADATA),
            "build1": migration_diffs["build1"],
            "build2": migration_diffs["build2"],
            "unreviewed_changed_entries": [],
            "all_other_entries_byte_identical": True,
            "all_assets_and_data_resources_byte_identical": True,
            "gameplay_resource_changed_entries": [],
            "manifest_diff": manifest_diff,
            "neoforge_mods_toml_diff": mods_toml_diff,
            "class_fix_markers": class_evidence,
        },
        "source_evidence": source_files,
        "conclusion": {
            "scope_correct": True,
            "gameplay_resources_preserved": True,
            "changed_classes_exactly_expected": True,
            "version_metadata_change_exactly_expected": True,
            "archive_crc_and_duplicate_entry_checks": "PASS",
            "byte_reproducible": True,
            "byte_difference_cause": None,
            "release_guidance": (
                "The two frozen final builds are byte-identical. The migration.4 release input may be pinned to "
                "SHA-256 9113FD81FABED5B2E8FB969AC858F1FE5707E0FF6ADC7C037D407B3D80633C17."
            ),
        },
    }
    write_atomic(report_path, stable_json(result))
    markdown = [
        "# Kaleidoscope Cookery migration.4 independent audit",
        "",
        f"- Status: `{status}`",
        f"- migration.3: `{EXPECTED_OUTER_SHA256['migration3']}`",
        f"- build1: `{EXPECTED_OUTER_SHA256['build1']}`",
        f"- build2: `{EXPECTED_OUTER_SHA256['build2']}`",
        "- final-build1/final-build2 are byte-identical, including all ZIP entry metadata.",
        "- migration.3 -> migration.4 changes exactly two class entries and two version metadata entries.",
        "- All other entries, including every assets/ and data/ gameplay resource, are byte-identical.",
        "- ZIP CRC passes and duplicate entry count is zero for all three JARs.",
        "- No JAR was installed; Java/Minecraft/Prism was not started or touched by this audit.",
        "",
    ]
    write_atomic(markdown_path, "\n".join(markdown).encode("utf-8"))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    try:
        result = audit(args.report.resolve(), args.markdown.resolve())
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "build1_sha256": result["artifacts"]["build1"]["sha256"],
                "build2_sha256": result["artifacts"]["build2"]["sha256"],
                "build_content_identical": result["build1_vs_build2"]["content_identical"],
                "gameplay_resources_preserved": result["conclusion"]["gameplay_resources_preserved"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
