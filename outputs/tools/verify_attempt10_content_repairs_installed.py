#!/usr/bin/env python3
"""Read-only installed-state validator for Attempt10 content repairs.

This validator is intentionally different from the TLM source/overlay verifier:
the latter proves an overlay is minimal before installation, while this file
proves the expected artifacts are actually installed in a concrete client and
server pair.  It never starts Java and never writes below either runtime root.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping
import zipfile


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import apply_attempt10_content_repairs as repair_spec  # noqa: E402


ALLOWED = Path(r"D:\Trans\migration-audit-work").resolve()
SPAWN_BOX_RECIPE = "touhou_little_maid:altar_recipe/spawn_box"
REBORN_MAID_RECIPE = "touhou_little_maid:altar_recipe/reborn_maid"

DEFAULT_SPEC: dict[str, Any] = {
    "yuushya": {
        "name": repair_spec.YUUSHYA_PATCHED_NAME,
        "bytes": repair_spec.YUUSHYA_PATCHED_BYTES,
        "sha256": repair_spec.YUUSHYA_PATCHED_SHA256,
        "original_name": repair_spec.YUUSHYA_ORIGINAL_NAME,
    },
    "tlm": {
        "name": repair_spec.TLM_NAME,
        "bytes": repair_spec.TLM_BYTES,
        "sha256": repair_spec.TLM_SHA256,
    },
    "maid_js": {
        "relative": repair_spec.MAID_JS_REL.as_posix(),
        "bytes": repair_spec.MAID_JS_BYTES,
        "sha256": repair_spec.MAID_JS_SHA256,
    },
    "overlays": {
        relative.as_posix(): {"bytes": size, "sha256": digest}
        for relative, (size, digest) in repair_spec.TLM_OVERLAY_FILES.items()
    },
}


class ValidationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def require_safe_root(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if (
        not is_within(resolved, ALLOWED)
        or resolved == ALLOWED
        or not resolved.is_dir()
        or resolved.is_symlink()
    ):
        raise ValidationError(f"unsafe or missing {label}: {resolved}")
    return resolved


def require_fresh_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not is_within(resolved, ALLOWED) or resolved == ALLOWED or resolved.exists():
        raise ValidationError(f"{label} must be a fresh path below {ALLOWED}: {resolved}")
    return resolved


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise ValidationError(f"temporary output already exists: {temporary}")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def add_check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
    **extra: Any,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail, **extra})


def inspect_artifact(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "is_symlink": path.is_symlink(),
    }
    if result["exists"] and not result["is_symlink"]:
        result["bytes"] = path.stat().st_size
        result["sha256"] = sha256_file(path)
    return result


def check_artifact(
    checks: list[dict[str, Any]],
    artifacts: dict[str, Any],
    name: str,
    path: Path,
    expected: Mapping[str, Any],
) -> None:
    actual = inspect_artifact(path)
    artifacts[name] = actual
    passed = (
        actual.get("exists") is True
        and actual.get("is_symlink") is False
        and actual.get("bytes") == expected["bytes"]
        and actual.get("sha256") == str(expected["sha256"]).upper()
    )
    add_check(
        checks,
        f"{name}:exact_artifact",
        passed,
        (
            f"expected bytes={expected['bytes']} sha256={str(expected['sha256']).upper()}; "
            f"actual exists={actual.get('exists')} symlink={actual.get('is_symlink')} "
            f"bytes={actual.get('bytes')} sha256={actual.get('sha256')}"
        ),
        path=str(path.resolve()),
    )


def list_relative_files(root: Path) -> list[str]:
    if not root.is_dir() or root.is_symlink():
        return []
    return sorted(
        (
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() or path.is_symlink()
        ),
        key=str.casefold,
    )


def find_mcmodsync(root: Path) -> dict[str, Any]:
    """Find filename/config indicators and renamed JAR metadata references."""

    path_matches: list[str] = []
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in directories + files:
            folded = name.casefold()
            if "mcmodsync" in folded or folded == "modsync.properties":
                path_matches.append(str((current_path / name).resolve()))

    metadata_matches: list[dict[str, str]] = []
    metadata_scan_errors: list[dict[str, str]] = []
    metadata_names = {
        "meta-inf/neoforge.mods.toml",
        "meta-inf/mods.toml",
        "fabric.mod.json",
        "quilt.mod.json",
        "meta-inf/manifest.mf",
    }
    mods = root / "mods"
    if mods.is_dir():
        for jar in sorted(mods.glob("*.jar"), key=lambda item: item.name.casefold()):
            try:
                with zipfile.ZipFile(jar) as archive:
                    entries = {name.casefold(): name for name in archive.namelist()}
                    for folded_name in sorted(metadata_names):
                        actual_name = entries.get(folded_name)
                        if actual_name is None:
                            continue
                        payload = archive.read(actual_name)
                        if b"mcmodsync" in payload.lower():
                            metadata_matches.append(
                                {"jar": str(jar.resolve()), "entry": actual_name}
                            )
            except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
                metadata_scan_errors.append({"jar": str(jar.resolve()), "error": str(exc)})
    return {
        "path_matches": sorted(set(path_matches), key=str.casefold),
        "metadata_matches": metadata_matches,
        "metadata_scan_errors": metadata_scan_errors,
    }


def inspect_application_report(
    path: Path,
    expected_sha256: str,
    server: Path,
    client: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"path": str(path.resolve())}
    if not path.is_file() or path.is_symlink():
        add_check(checks, "application_report:exists", False, str(path.resolve()))
        return evidence, checks
    actual_sha256 = sha256_file(path)
    evidence.update({"bytes": path.stat().st_size, "sha256": actual_sha256})
    add_check(
        checks,
        "application_report:locked_sha256",
        actual_sha256 == expected_sha256.upper(),
        f"expected={expected_sha256.upper()} actual={actual_sha256}",
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        add_check(checks, "application_report:valid_json", False, str(exc))
        return evidence, checks
    add_check(checks, "application_report:valid_json", True, "JSON parsed")
    add_check(
        checks,
        "application_report:pass_applied",
        payload.get("status") == "PASS_APPLIED",
        f"status={payload.get('status')}",
    )
    policy = payload.get("policy", {})
    expected_policy = {
        "spawn_box_recipe_removed": True,
        "maid_js_unchanged": True,
        "tlm_patch_side": "CLIENT",
        "yuushya_patch_side": "BOTH",
        "mcmodsync_globally_disabled": True,
    }
    add_check(
        checks,
        "application_report:policy_exact",
        policy == expected_policy,
        f"expected={expected_policy!r} actual={policy!r}",
    )
    after = payload.get("after", {})
    try:
        roots_match = (
            Path(after.get("server", "")).resolve() == server.resolve()
            and Path(after.get("client", "")).resolve() == client.resolve()
        )
    except (OSError, TypeError, ValueError):
        roots_match = False
    add_check(
        checks,
        "application_report:target_roots_exact",
        roots_match,
        f"server={after.get('server')} client={after.get('client')}",
    )
    changed = payload.get("application", {}).get("changed", [])
    changed_projection = sorted(
        (
            str(row.get("side")),
            str(row.get("kind")),
            Path(str(row.get("target", ""))).name,
        )
        for row in changed
        if isinstance(row, dict)
    )
    expected_projection = sorted(
        [
            ("server", "jar", repair_spec.YUUSHYA_PATCHED_NAME),
            ("client", "jar", repair_spec.YUUSHYA_PATCHED_NAME),
            ("client", "overlay", "spawn_maid.json"),
            ("client", "overlay", "multiblocks_altar.json"),
        ]
    )
    add_check(
        checks,
        "application_report:four_expected_changes",
        changed_projection == expected_projection,
        f"expected={expected_projection!r} actual={changed_projection!r}",
    )
    evidence["status"] = payload.get("status")
    evidence["policy"] = policy
    evidence["changed_projection"] = changed_projection
    return evidence, checks


def classify_prior_static_report(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "authoritative_for_installed_state": False,
        "classification": "NON_AUTHORITATIVE_FOR_INSTALLED_STATE",
        "reason": (
            "This was a source/minimal-overlay verifier. Its Attempt9 immutability and "
            "post-launch-log assertions are not valid acceptance criteria after installing "
            "the overlay into a fresh, not-yet-launched Attempt10 client."
        ),
    }
    if not path.is_file() or path.is_symlink():
        result["classification"] = "MISSING_PRIOR_REPORT"
        return result
    result["bytes"] = path.stat().st_size
    result["sha256"] = sha256_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result["classification"] = "UNREADABLE_PRIOR_REPORT"
        result["error"] = str(exc)
        return result
    failed = sorted(
        str(check.get("name"))
        for check in payload.get("checks", [])
        if isinstance(check, dict) and not check.get("passed")
    )
    result["prior_verdict"] = payload.get("verdict")
    result["failed_checks"] = failed
    result["expected_scope_mismatch_confirmed"] = failed == [
        "attempt9_client_log_exists",
        "attempt9_client_not_modified",
    ]
    return result


def validate_installed(
    server: Path,
    client: Path,
    spec: Mapping[str, Any] = DEFAULT_SPEC,
) -> dict[str, Any]:
    server = server.resolve()
    client = client.resolve()
    checks: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    add_check(checks, "server_root:directory", server.is_dir(), str(server))
    add_check(checks, "client_root:directory", client.is_dir(), str(client))
    add_check(checks, "roots:distinct", server != client, f"server={server} client={client}")
    if not server.is_dir() or not client.is_dir() or server == client:
        return {
            "server_root": str(server),
            "client_root": str(client),
            "checks": checks,
            "artifacts": artifacts,
            "mcmodsync": {},
        }

    yuushya = spec["yuushya"]
    for side, root in (("server", server), ("client", client)):
        candidates = sorted(
            (path.name for path in (root / "mods").glob("yuushya*.jar")),
            key=str.casefold,
        )
        expected_names = [str(yuushya["name"])]
        add_check(
            checks,
            f"{side}:yuushya_selection_exact",
            candidates == expected_names,
            f"expected={expected_names!r} actual={candidates!r}",
        )
        check_artifact(
            checks,
            artifacts,
            f"{side}:yuushya_patched",
            root / "mods" / str(yuushya["name"]),
            yuushya,
        )

    tlm = spec["tlm"]
    for side, root in (("server", server), ("client", client)):
        candidates = sorted(
            (path.name for path in (root / "mods").glob("touhoulittlemaid*.jar")),
            key=str.casefold,
        )
        expected_names = [str(tlm["name"])]
        add_check(
            checks,
            f"{side}:tlm_selection_exact",
            candidates == expected_names,
            f"expected={expected_names!r} actual={candidates!r}",
        )
        check_artifact(
            checks,
            artifacts,
            f"{side}:tlm_unchanged",
            root / "mods" / str(tlm["name"]),
            tlm,
        )

    maid_js = spec["maid_js"]
    maid_path = server / str(maid_js["relative"])
    check_artifact(checks, artifacts, "server:maid_js_unchanged", maid_path, maid_js)
    client_maid = client / str(maid_js["relative"])
    add_check(
        checks,
        "client:no_dedicated_maid_js",
        not client_maid.exists() and not client_maid.is_symlink(),
        str(client_maid),
    )
    if maid_path.is_file() and not maid_path.is_symlink():
        try:
            maid_text = maid_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            add_check(checks, "server:maid_js_remove_rule", False, str(exc))
        else:
            exact_rule = (
                'id: "touhou_little_maid:altar_recipe/spawn_box"' in maid_text
                and "event.remove" in maid_text
            )
            add_check(
                checks,
                "server:maid_js_remove_rule",
                exact_rule,
                "intentional spawn-box recipe removal remains present",
            )

    overlays: Mapping[str, Any] = spec["overlays"]
    entry_relative = Path(
        "kubejs/assets/touhou_little_maid/patchouli_books/"
        "memorizable_gensokyo/en_us/entries"
    )
    client_entry_root = client / entry_relative
    server_entry_root = server / entry_relative
    expected_under_entry = sorted(
        (
            Path(relative).relative_to(entry_relative).as_posix()
            for relative in overlays
        ),
        key=str.casefold,
    )
    actual_client_entries = list_relative_files(client_entry_root)
    add_check(
        checks,
        "client:tlm_patchouli_overlay_scope_exactly_two_jsons",
        actual_client_entries == expected_under_entry and len(actual_client_entries) == 2,
        f"expected={expected_under_entry!r} actual={actual_client_entries!r}",
    )
    actual_server_entries = list_relative_files(server_entry_root)
    add_check(
        checks,
        "server:no_client_tlm_patchouli_overlay",
        actual_server_entries == [],
        f"actual={actual_server_entries!r}",
    )
    overlay_payloads: dict[str, Any] = {}
    for relative, expected in overlays.items():
        target = client / relative
        check_artifact(
            checks,
            artifacts,
            f"client:overlay:{relative}",
            target,
            expected,
        )
        if target.is_file() and not target.is_symlink():
            try:
                overlay_payloads[relative] = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                add_check(checks, f"client:overlay:{relative}:valid_json", False, str(exc))
            else:
                add_check(checks, f"client:overlay:{relative}:valid_json", True, "JSON parsed")
                serialized = json.dumps(overlay_payloads[relative], ensure_ascii=False)
                add_check(
                    checks,
                    f"client:overlay:{relative}:stale_recipe_absent",
                    SPAWN_BOX_RECIPE not in serialized,
                    SPAWN_BOX_RECIPE,
                )
    multiblocks_relative = next(
        (relative for relative in overlays if relative.endswith("overview/multiblocks_altar.json")),
        None,
    )
    if multiblocks_relative in overlay_payloads:
        serialized = json.dumps(overlay_payloads[multiblocks_relative], ensure_ascii=False)
        add_check(
            checks,
            "client:multiblocks_overlay:reborn_maid_preserved",
            REBORN_MAID_RECIPE in serialized,
            REBORN_MAID_RECIPE,
        )

    mcmodsync: dict[str, Any] = {}
    for side, root in (("server", server), ("client", client)):
        result = find_mcmodsync(root)
        mcmodsync[side] = result
        absent = not result["path_matches"] and not result["metadata_matches"]
        add_check(
            checks,
            f"{side}:mcmodsync_absent",
            absent,
            (
                f"path_matches={result['path_matches']!r} "
                f"metadata_matches={result['metadata_matches']!r}"
            ),
        )
        add_check(
            checks,
            f"{side}:mcmodsync_metadata_scan_complete",
            not result["metadata_scan_errors"],
            f"errors={result['metadata_scan_errors']!r}",
        )

    return {
        "server_root": str(server),
        "client_root": str(client),
        "checks": checks,
        "artifacts": artifacts,
        "mcmodsync": mcmodsync,
    }


def build_notice(prior: Mapping[str, Any], report_path: Path, report_sha256: str) -> str:
    failed = ", ".join(str(item) for item in prior.get("failed_checks", [])) or "unknown"
    return (
        "# Attempt10 TLM verification scope notice\n\n"
        "Status: **NON-AUTHORITATIVE FOR INSTALLED STATE**\n\n"
        f"The preserved report `{prior.get('path')}` is source/static-verifier evidence only. "
        "It was run against an already-installed, fresh Attempt10 client, so its checks "
        "`attempt9_client_not_modified` and `attempt9_client_log_exists` do not describe "
        "whether the installed repair is correct. The old JSON is retained unchanged as "
        "audit history; it must not be used as the Attempt10 release verdict.\n\n"
        f"Observed failed checks: `{failed}`.\n\n"
        f"Authoritative installed-state report: `{report_path.resolve()}`  \n"
        f"SHA-256: `{report_sha256}`\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--application-report", type=Path)
    parser.add_argument("--application-report-sha256")
    parser.add_argument("--prior-static-report", type=Path)
    parser.add_argument("--non-authoritative-notice", type=Path)
    args = parser.parse_args()

    if bool(args.application_report) != bool(args.application_report_sha256):
        raise ValidationError(
            "--application-report and --application-report-sha256 must be supplied together"
        )
    if bool(args.prior_static_report) != bool(args.non_authoritative_notice):
        raise ValidationError(
            "--prior-static-report and --non-authoritative-notice must be supplied together"
        )

    server = require_safe_root(args.server_root, "server root")
    client = require_safe_root(args.client_root, "client root")
    if server == client:
        raise ValidationError("server and client roots must be distinct")
    report_path = require_fresh_output(args.report, "report")
    notice_path = (
        require_fresh_output(args.non_authoritative_notice, "notice")
        if args.non_authoritative_notice
        else None
    )

    validation = validate_installed(server, client)
    checks = validation["checks"]
    application_evidence: dict[str, Any] | None = None
    if args.application_report:
        application_evidence, application_checks = inspect_application_report(
            args.application_report.resolve(),
            args.application_report_sha256,
            server,
            client,
        )
        checks.extend(application_checks)

    prior = (
        classify_prior_static_report(args.prior_static_report.resolve())
        if args.prior_static_report
        else None
    )
    verdict = "PASS" if all(check["passed"] for check in checks) else "FAIL"
    report = {
        "schema": 1,
        "status": f"{verdict}_INSTALLED_STATE",
        "verdict": verdict,
        "authoritative_for_installed_state": verdict == "PASS",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "scope": {
            "description": "Attempt10 Yuushya and TLM content repairs after installation",
            "java_or_minecraft_started": False,
            "world_content_modified": False,
            "requirements": [
                "patched Yuushya is the sole Yuushya JAR on BOTH sides",
                "the exact original TLM JAR remains unchanged on BOTH sides",
                "the official server maid.js remains unchanged",
                "the client TLM Patchouli entry overlay contains exactly two JSON files",
                "the server receives no client Patchouli overlay",
                "MCModSync is absent by path and JAR metadata on BOTH sides",
            ],
        },
        "server_root": validation["server_root"],
        "client_root": validation["client_root"],
        "checks": checks,
        "summary": {
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": sum(1 for check in checks if not check["passed"]),
            "failed_checks": [check["name"] for check in checks if not check["passed"]],
        },
        "artifacts": validation["artifacts"],
        "mcmodsync": validation["mcmodsync"],
        "application_report": application_evidence,
        "prior_static_report": prior,
    }
    atomic_write_text(
        report_path,
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
    )
    report_sha256 = sha256_file(report_path)
    if notice_path is not None and prior is not None:
        atomic_write_text(notice_path, build_notice(prior, report_path, report_sha256))

    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(report_path),
                "sha256": report_sha256,
                "notice": str(notice_path) if notice_path else None,
                "passed": report["summary"]["passed"],
                "failed": report["summary"]["failed"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
