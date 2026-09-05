#!/usr/bin/env python3
"""Prepare one disposable D:-resident runtime for the matched Mechanomania release.

The authoritative converted staging, published release, and production
``server.properties`` stay read-only. Only the fresh output receives the
locked server overlay, target-only resource normalization, loopback test
ports, and the 4 GiB test heap cap.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import mechanomania_release_runtime_common as release_common
import prepare_final_fullstack_smoke as smoke


ALLOWED_ROOT = Path(r"<AUDIT_ROOT>")
ALLOWED_TEMPLATE = Path(
    r"<HANDOFF_ROOT>\03-tools-and-source\d-projects\respawn-pitch-compat\smoke-server"
)
AUTHORITATIVE_SOURCE = Path(r"<AUDIT_ROOT>\incoming-20260811-raw\20260811")
AUTHORITATIVE_STAGING = Path(
    r"<HANDOFF_ROOT>\02-latest\converted-staging"
)
LOCKED_RELEASE_ROOT = Path(
    r"<AUDIT_ROOT>\mechanomania-matched-release-v2-20260813"
)
LOCKED_READY_SHA256 = "AE84FE740B74D50A937284A7916E460ED55580EF1B4B794D8107562133D7F236"
LOCKED_BUILD_REPORT = (
    Path(__file__).resolve().parents[1]
    / "mechanomania-matched-release-build-20260813.json"
)
LOCKED_BUILD_REPORT_SHA256 = (
    "2CA9D243353221B0B5437CBCE2EFBA935D4CB9E67B24B0388E2F3BA34C9DFC36"
)
EXPECTED_PORTS = (12341, 12342, 26341)
EXPECTED_SANITIZER_JARS = {
    "CreateDragonsPlus-1.11.4.jar",
    "kaleidoscope_nether-1.1.2-neoforge+mc1.21.1.jar",
}
JOURNEYMAP_LEGACY_PATHS = (
    "config/journeymap-server.json",
    "config/hydraulic/storage/journeymap",
    "config/hydraulic/storage/journeymap-api-fabric",
)
JOURNEYMAP_TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".js",
    ".json",
    ".json5",
    ".kjs",
    ".mcfunction",
    ".mcmeta",
    ".md",
    ".properties",
    ".snbt",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
    ".zs",
}


class PrepareError(RuntimeError):
    pass


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def overlaps(first: Path, second: Path) -> bool:
    return is_within(first, second) or is_within(second, first)


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve())) == os.path.normcase(str(second.resolve()))


def is_reparse(path: Path) -> bool:
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attrs = 0
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) or path.is_symlink()


def _assert_no_reparse_ancestors(path: Path, stop: Path, label: str) -> None:
    """Reject path redirection anywhere below the selected safety root."""
    resolved_stop = stop.resolve()
    current = path.absolute()
    if not is_within(current, resolved_stop):
        raise PrepareError(f"{label} is outside its safety root: {path}")
    while True:
        if current.exists() and is_reparse(current):
            raise PrepareError(f"{label} has a linked/reparse ancestor: {current}")
        if _same_path(current, resolved_stop):
            return
        parent = current.parent
        if parent == current:
            raise PrepareError(f"{label} is outside its safety root: {path}")
        current = parent


def _assert_regular_template(path: Path) -> None:
    if not path.is_dir() or is_reparse(path):
        raise PrepareError(f"runtime template is missing or linked: {path}")
    for required in (path / "libraries", path / "run.bat", path / "user_jvm_args.txt"):
        if not required.exists() or is_reparse(required):
            raise PrepareError(f"runtime template input is missing or linked: {required}")
    for entry in (path / "libraries").rglob("*"):
        if is_reparse(entry):
            raise PrepareError(f"runtime template libraries contain a reparse entry: {entry}")


def _regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise PrepareError(f"{label} must be a regular non-linked file: {path}")


def _load_json(path: Path, label: str) -> dict:
    _regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PrepareError(f"{label} is invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PrepareError(f"{label} must be a JSON object: {path}")
    return value


def _bind_final_datafix(
    staging: Path,
    marker_path: Path,
    marker_sha256: str,
    closure_path: Path,
    closure_sha256: str,
) -> dict:
    if marker_path.resolve() != (staging / "migration-reports" / "conversion-complete.json").resolve():
        raise PrepareError("conversion marker is not inside the selected staging")
    if release_common.sha256(marker_path) != marker_sha256.upper():
        raise PrepareError("conversion marker hash mismatch")
    marker = _load_json(marker_path, "conversion marker")
    if (
        marker.get("status") != "CONVERTED_STAGING"
        or Path(str(marker.get("staging_root", ""))).resolve() != staging
        or Path(str(marker.get("source_root", ""))).resolve() != AUTHORITATIVE_SOURCE.resolve()
    ):
        raise PrepareError("conversion marker identity/status mismatch")
    adoption = marker.get("adoption")
    if (
        not isinstance(adoption, dict)
        or adoption.get("never_rebaselined_from_converted_staging") is not True
        or str(adoption.get("closure_report_sha256", "")).upper() != closure_sha256.upper()
        or Path(str(adoption.get("closure_report", ""))).resolve() != closure_path.resolve()
    ):
        raise PrepareError("conversion marker is not bound to the hardened data-fix closure")
    if release_common.sha256(closure_path) != closure_sha256.upper():
        raise PrepareError("hardened data-fix closure hash mismatch")
    closure = _load_json(closure_path, "hardened data-fix closure")
    if (
        closure.get("status") != "PASS"
        or closure.get("source_scope_unchanged") is not True
        or Path(str(closure.get("staging_game_dir", ""))).resolve() != staging
        or closure.get("maps", {}).get("status") != "MATCH"
        or closure.get("advancements", {}).get("status") != "ALREADY_TARGET"
        or closure.get("schematics", {}).get("status") != "MATCH"
        or closure.get("schematic_references", {}).get("status") != "MATCH"
    ):
        raise PrepareError("hardened data-fix closure is incomplete")
    return {
        "conversion_marker": {"path": str(marker_path), "sha256": marker_sha256.upper()},
        "closure_report": {"path": str(closure_path), "sha256": closure_sha256.upper()},
        "maps": closure["maps"].get("maps"),
        "map_ledger_records": closure["maps"].get("ledger_records"),
        "advancement_files": closure["advancements"].get("source_files"),
        "advancement_occurrences": closure["advancements"].get("occurrences"),
        "schematic_files": closure["schematics"].get("files"),
    }


def _write_heap_cap(path: Path) -> None:
    path.write_text(
        "# Isolated migration validation heap.\n-Xms2G\n-Xmx4G\n",
        encoding="ascii",
    )


def _rewrite_published_paths(value: object, temporary: Path, output: Path) -> object:
    """Replace temporary native/POSIX prefixes without relying on JSON escaping."""
    if isinstance(value, str):
        return value.replace(str(temporary), str(output)).replace(
            temporary.as_posix(), output.as_posix()
        )
    if isinstance(value, list):
        return [_rewrite_published_paths(item, temporary, output) for item in value]
    if isinstance(value, dict):
        return {
            key: _rewrite_published_paths(item, temporary, output)
            for key, item in value.items()
        }
    return value


def _remove_legacy_journeymap_paths(runtime_root: Path) -> dict:
    """Remove only the audited legacy JourneyMap config/cache paths.

    These are copied from the authoritative staging into the disposable
    runtime.  The staging itself remains unchanged.  A full-tree path-name
    gate then prevents any unreviewed JourneyMap path from reaching runtime.
    """
    removed: list[dict] = []
    for relative in JOURNEYMAP_LEGACY_PATHS:
        target = runtime_root / Path(relative)
        if is_reparse(target):
            raise PrepareError(f"legacy JourneyMap target is linked/reparse: {target}")
        if not target.exists():
            continue
        if target.is_dir():
            files = [path for path in target.rglob("*") if path.is_file()]
            removed.append(
                {
                    "path": relative,
                    "kind": "directory",
                    "files": len(files),
                    "bytes": sum(path.stat().st_size for path in files),
                }
            )
            shutil.rmtree(target)
        elif target.is_file():
            removed.append(
                {
                    "path": relative,
                    "kind": "file",
                    "files": 1,
                    "bytes": target.stat().st_size,
                }
            )
            target.unlink()
        else:
            raise PrepareError(f"legacy JourneyMap target is not regular: {target}")
    paths = list(runtime_root.rglob("*"))
    reparses = [path for path in paths if is_reparse(path)]
    if reparses:
        raise PrepareError(f"runtime contains linked/reparse entries: {reparses[:20]}")
    remaining_paths = sorted(
        path.relative_to(runtime_root).as_posix()
        for path in paths
        if "journeymap" in path.name.casefold()
    )
    if remaining_paths:
        raise PrepareError(f"unreviewed JourneyMap paths remain: {remaining_paths[:20]}")
    text_matches: list[str] = []
    for path in paths:
        if (
            not path.is_file()
            or path.suffix.casefold() not in JOURNEYMAP_TEXT_SUFFIXES
            or path.stat().st_size > 4 * 1024 * 1024
            or "world" in path.relative_to(runtime_root).parts[:1]
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        if "journeymap" in text.casefold():
            text_matches.append(path.relative_to(runtime_root).as_posix())
    if text_matches:
        raise PrepareError(f"unreviewed JourneyMap text references remain: {text_matches[:20]}")
    return {
        "status": "PASS_ZERO_MATCH",
        "declared_paths": list(JOURNEYMAP_LEGACY_PATHS),
        "removed": removed,
        "removed_files": sum(row["files"] for row in removed),
        "removed_bytes": sum(row["bytes"] for row in removed),
        "remaining_path_matches": 0,
        "remaining_text_matches": 0,
        "remaining_mod_jar_matches": 0,
        "staging_written": False,
    }


def _strict_sanitization(result: dict, expected_file_count: int) -> dict:
    sanitization = result.get("resource_sanitization")
    if not isinstance(sanitization, dict):
        raise PrepareError("runtime resource sanitization report is missing")
    changes = sanitization.get("changes")
    manifest = sanitization.get("runtime_mod_manifest")
    if not isinstance(changes, list) or not isinstance(manifest, dict):
        raise PrepareError("runtime sanitizer evidence is incomplete")
    changed_jars = {
        Path(str(row.get("path", ""))).name
        for row in changes
        if isinstance(row, dict) and row.get("kind") == "jar-resource-sanitize"
    }
    if not changed_jars.issubset(EXPECTED_SANITIZER_JARS):
        raise PrepareError(f"runtime sanitizer changed unexpected JARs: {sorted(changed_jars)}")
    if manifest.get("file_count") != expected_file_count:
        # This is a selected-release snapshot check, not a permanent cap.
        raise PrepareError("runtime JAR count differs from the selected release snapshot")
    return {
        "changed_jars": sorted(changed_jars),
        "runtime_mod_manifest": {
            "file_count": manifest.get("file_count"),
            "bytes": manifest.get("bytes"),
            "bundle_sha256": str(manifest.get("bundle_sha256", "")).upper(),
        },
        "changed_files": sanitization.get("changed_files"),
    }


def prepare(args: argparse.Namespace) -> dict:
    release_root = args.release_root.resolve()
    runtime_template = args.runtime_template.resolve()
    staging = args.staging.resolve()
    output = args.output.resolve()
    report = args.report.resolve()
    marker_path = args.conversion_marker.resolve()
    closure_path = args.datafix_closure.resolve()
    if not _same_path(runtime_template, ALLOWED_TEMPLATE):
        raise PrepareError(f"runtime template must be the audited read-only skeleton: {ALLOWED_TEMPLATE}")
    if not _same_path(staging, AUTHORITATIVE_STAGING):
        raise PrepareError(f"staging must be the authoritative converted staging: {AUTHORITATIVE_STAGING}")
    if not _same_path(release_root, LOCKED_RELEASE_ROOT):
        raise PrepareError(f"release root must be the selected locked release: {LOCKED_RELEASE_ROOT}")
    if args.ready_sha256.upper() != LOCKED_READY_SHA256:
        raise PrepareError("READY hash is not the selected release lock")
    if not _same_path(args.build_report, LOCKED_BUILD_REPORT):
        raise PrepareError(f"build report must be the selected report: {LOCKED_BUILD_REPORT}")
    if args.build_report_sha256.upper() != LOCKED_BUILD_REPORT_SHA256:
        raise PrepareError("build report hash is not the selected release lock")
    _assert_regular_template(runtime_template)
    for path, label in ((output, "runtime output"), (report, "runtime report")):
        if not is_within(path, ALLOWED_ROOT):
            raise PrepareError(f"{label} must stay under {ALLOWED_ROOT}: {path}")
        _assert_no_reparse_ancestors(path, ALLOWED_ROOT, label)
    protected_inputs = (runtime_template, staging, release_root, AUTHORITATIVE_SOURCE)
    if any(overlaps(path, protected) for path in (output, report) for protected in protected_inputs):
        raise PrepareError("runtime output/report overlaps a protected input")
    if overlaps(output, report):
        raise PrepareError("runtime output and report overlap")
    if output.exists() or report.exists():
        raise PrepareError("runtime output/report already exists; refusing reuse")
    if (args.server_port, args.rcon_port, args.voice_port) != EXPECTED_PORTS:
        raise PrepareError("private runtime ports must be 12341/12342/26341")

    release = release_common.validate_release(
        release_root, args.ready_sha256, args.build_report.resolve(), args.build_report_sha256
    )
    datafix = _bind_final_datafix(
        staging,
        marker_path,
        args.conversion_marker_sha256,
        closure_path,
        args.datafix_closure_sha256,
    )
    temporary = output.with_name(output.name + ".mechanomania." + uuid.uuid4().hex + ".tmp")
    published = False
    try:
        result = smoke.prepare(
            smoke.ensure_d_path(runtime_template, "runtime template"),
            smoke.ensure_d_path(staging, "staging"),
            smoke.ensure_d_path(release_root / "server" / "mods", "server mods"),
            smoke.ensure_d_path(temporary, "temporary runtime"),
            args.server_port,
            args.rcon_port,
            args.voice_port,
            False,
        )
        overlay = release_common.apply_overlay(release, "server", temporary)
        journeymap_cleanup = _remove_legacy_journeymap_paths(temporary)
        # Runtime-only network settings must be applied after the pack overlay.
        smoke.replace_properties(
            temporary / "server.properties",
            {
                "server-ip": "127.0.0.1",
                "server-port": str(args.server_port),
                "query.port": str(args.server_port),
                "enable-rcon": "true",
                "rcon.port": str(args.rcon_port),
                "rcon.password": "migration-final-smoke",
                "online-mode": "false",
                "level-name": "world",
                "max-tick-time": "-1",
            },
        )
        voicechat = temporary / "config" / "voicechat" / "voicechat-server.properties"
        if voicechat.is_file():
            smoke.replace_properties(
                voicechat, {"port": str(args.voice_port), "bind_address": "127.0.0.1"}
            )
        smoke.disable_mineastr_network(temporary / "config" / "mineastr-common.toml")
        _write_heap_cap(temporary / "user_jvm_args.txt")
        sanitizer = smoke.sanitize_target_resources(
            temporary / "world", temporary / "server.properties", temporary / "mods"
        )
        result["resource_sanitization"] = sanitizer
        expected_mods = release["server_mods"]
        sanitized = _strict_sanitization(result, expected_mods["files"])
        if sanitized["runtime_mod_manifest"]["file_count"] != expected_mods["files"]:
            raise PrepareError("runtime JAR count differs from release manifest")
        result.update(
            {
                "output": str(output),
                "world": smoke.tree_metadata(temporary / "world"),
                "mods_manifest": smoke.tree_metadata(temporary / "mods"),
                "server_properties_sha256": smoke.sha256(temporary / "server.properties"),
                "mechanomania_release": {
                    "root": release["root"],
                    "ready_sha256": release["ready"]["sha256"],
                    "build_report_sha256": release["build_report"]["sha256"],
                    "server_mods": {
                        "files": expected_mods["files"],
                        "bytes": expected_mods["bytes"],
                        "bundle_sha256": expected_mods["bundle_sha256"],
                    },
                    "server_overlay": overlay,
                    "permanent_mod_count_cap": False,
                },
                "final_datafix": datafix,
                "journeymap_cleanup": journeymap_cleanup,
                "runtime_mods_after_sanitizer": sanitized,
                "heap": {"xms": "2G", "xmx": "4G"},
                "safety": {
                    "source_written": False,
                    "staging_written": False,
                    "release_written": False,
                    "production_server_properties_modified": False,
                    "loopback_only": True,
                    "java_started": False,
                    "single_world_copy": True,
                },
            }
        )
        # Sanitizer records POSIX-style paths while the preparation report also
        # contains native Windows paths. Rewrite actual string values before
        # serialization so JSON backslash escaping cannot hide native prefixes.
        result = _rewrite_published_paths(result, temporary, output)
        os.replace(temporary, output)
        published = True
        smoke.atomic_json(report, result)
        return result
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if published and output.exists() and not report.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--release-root", type=Path, required=True)
    value.add_argument("--ready-sha256", required=True)
    value.add_argument("--build-report", type=Path, required=True)
    value.add_argument("--build-report-sha256", required=True)
    value.add_argument("--runtime-template", type=Path, required=True)
    value.add_argument("--staging", type=Path, required=True)
    value.add_argument("--conversion-marker", type=Path, required=True)
    value.add_argument("--conversion-marker-sha256", required=True)
    value.add_argument("--datafix-closure", type=Path, required=True)
    value.add_argument("--datafix-closure-sha256", required=True)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--report", type=Path, required=True)
    value.add_argument("--server-port", type=int, default=12341)
    value.add_argument("--rcon-port", type=int, default=12342)
    value.add_argument("--voice-port", type=int, default=26341)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        result = prepare(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": result["output"],
                "world_files": result["world"]["files"],
                "heap_xmx": result["heap"]["xmx"],
                "java_started": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
