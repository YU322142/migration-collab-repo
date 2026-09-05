#!/usr/bin/env python3
"""Candidate14 two-round join gate with a release-scoped dynamic mod lock.

This adapter reuses the mature Candidate13 desktop/server orchestration while
replacing every Candidate13 package assumption with an explicit Candidate14
READY/build-report binding.  It also audits the protected deferred item after
each graceful stop and refuses PASS unless the source/staging/runtime ledger is
semantically identical through both rounds.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

# Allow both direct-script execution and package-style unittest imports.
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import audit_deferred_item_checkpoint as checkpoint_audit
import candidate14_release_gate_common as release_common
import verify_deferred_item_ledger as ledger_verify


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
BASELINE_LEDGER = OUTPUTS / "candidate14-netherite-horse-armor-ledger-baseline-20260812.json"
FORBIDDEN_SOURCE = Path(r"<TRANS_ROOT>\20260807")
ALLOWED_EXTERNAL_ROOT = Path(r"<AUDIT_ROOT>")
ATTEMPT_MARKER = ".candidate14-release-gate-attempt.json"
SANITIZER_JARS = set(release_common.SANITIZER_JARS)
RECIPE_BOOK_ALLOWLIST = OUTPUTS / "candidate14-server-recipe-book-stale-allowlist-20260812.json"

# Compatibility exception for legacy recipe-book unlocks.  This is deliberately
# a reviewed, finite sidecar rather than a broad ``ServerRecipeBook`` allowlist:
# the line shape, logger, resource-location grammar and ID set are all checked.
RECIPE_BOOK_LINE_RE = re.compile(
    r"^.*\[Server thread/ERROR\] \[[^\]]*ServerRecipeBook[^\]]*\]: "
    r"Tried to load unrecognized recipe: (?P<recipe>[a-z0-9_.-]+:[a-z0-9_./-]+) removed now\.$",
    re.I,
)
RECIPE_BOOK_ERROR_RE = re.compile(
    r"^.*\[Server thread/ERROR\] \[[^\]]*ServerRecipeBook[^\]]*\]:.*$",
    re.I | re.M,
)


def _recipe_book_allowlist() -> dict[str, Any]:
    """Read the immutable, reviewed stale-recipe sidecar."""
    value = _read_json(RECIPE_BOOK_ALLOWLIST, "Candidate14 ServerRecipeBook allowlist")
    if value.get("schema") != 1 or value.get("status") != "REVIEWED_STALE_ONLY":
        raise GateError("ServerRecipeBook allowlist is not a reviewed stale-only schema")
    ids = value.get("recipe_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids):
        raise GateError("ServerRecipeBook allowlist recipe_ids is invalid")
    if ids != sorted(set(ids)):
        raise GateError("ServerRecipeBook allowlist IDs must be sorted and unique")
    if any(RECIPE_BOOK_LINE_RE.fullmatch(
        "[Server thread/ERROR] [minecraft/ServerRecipeBook]: Tried to load unrecognized recipe: "
        + item + " removed now."
    ) is None for item in ids):
        raise GateError("ServerRecipeBook allowlist contains an invalid resource location")
    expected = value.get("expected_fresh_runtime_first_round_counts")
    if (
        not isinstance(expected, dict)
        or sorted(expected) != ids
        or any(not isinstance(count, int) or isinstance(count, bool) or count <= 0 for count in expected.values())
    ):
        raise GateError("ServerRecipeBook expected first-round multiset is invalid")
    return value


def recipe_book_audit(text: str, allowlist: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify every ServerRecipeBook ERROR line, fail-closed on drift."""
    allowlist = allowlist or _recipe_book_allowlist()
    allowed = set(allowlist["recipe_ids"])
    observed: list[str] = []
    malformed: list[str] = []
    for line in text.splitlines():
        if not RECIPE_BOOK_ERROR_RE.match(line):
            continue
        match = RECIPE_BOOK_LINE_RE.fullmatch(line)
        if match is None or match.group("recipe") not in allowed:
            malformed.append(line[:500])
        else:
            observed.append(match.group("recipe"))
    counts: dict[str, int] = {}
    for recipe in observed:
        counts[recipe] = counts.get(recipe, 0) + 1
    canonical = "\n".join(f"{recipe}={counts[recipe]}" for recipe in sorted(counts)) + (
        "\n" if counts else ""
    )
    return {
        "status": "PASS" if not malformed else "NO_GO",
        "line_count": len(observed) + len(malformed),
        "accepted_count": len(observed),
        "accepted_unique_ids": sorted(counts),
        "counts": {key: counts[key] for key in sorted(counts)},
        "counts_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper(),
        "malformed_or_unreviewed_count": len(malformed),
        "malformed_or_unreviewed_samples": malformed[:10],
        "allowlist_sha256": _sha256(RECIPE_BOOK_ALLOWLIST),
    }


def assert_no_strict_markers_candidate14(text: str, scope: str, *, client: bool = False) -> None:
    """Candidate14 strict gate with the reviewed stale-recipe exception only."""
    recipe = recipe_book_audit(text)
    if recipe["malformed_or_unreviewed_count"]:
        raise GateError(f"strict {scope} ServerRecipeBook marker(s): {recipe}")
    filtered = RECIPE_BOOK_ERROR_RE.sub("", text)
    hits = legacy.strict_marker_hits(filtered, client=client)
    if hits:
        raise GateError(f"strict {scope} marker(s): {hits}")


def validate_round_recipe_book(
    round_number: int,
    latest_log: Path,
    allowlist: dict[str, Any],
) -> dict[str, Any]:
    """Bind native recipe-book cleanup to round-specific on-disk evidence."""
    if not latest_log.is_file() or latest_log.is_symlink():
        raise GateError(f"round {round_number} server latest log is missing or linked")
    audit = recipe_book_audit(
        latest_log.read_text(encoding="utf-8", errors="replace"), allowlist
    )
    if audit["status"] != "PASS":
        raise GateError(f"round {round_number} ServerRecipeBook audit failed: {audit}")
    expected = (
        allowlist["expected_fresh_runtime_first_round_counts"]
        if round_number == 1
        else {}
    )
    if audit["counts"] != expected:
        raise GateError(
            f"round {round_number} ServerRecipeBook multiset mismatch: "
            f"{audit['counts']} != {expected}"
        )
    return {
        **audit,
        "round": round_number,
        "expected_counts": expected,
        "expected_line_count": sum(expected.values()),
        "native_cleanup_expectation": (
            "reviewed stale entries removed during load/save"
            if round_number == 1
            else "zero stale entries after first graceful save"
        ),
        "latest_log": legacy.file_artifact(latest_log),
    }

LEGACY_SPEC = importlib.util.spec_from_file_location(
    "candidate13_gate_engine", Path(__file__).with_name("run_candidate13_join_gate.py")
)
if LEGACY_SPEC is None or LEGACY_SPEC.loader is None:
    raise ImportError("cannot load Candidate13 gate engine")
legacy = importlib.util.module_from_spec(LEGACY_SPEC)
LEGACY_SPEC.loader.exec_module(legacy)


class GateError(legacy.GateError):
    pass


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _is_reparse(path: Path) -> bool:
    try:
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        attrs = 0
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) or path.is_symlink()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _atomic_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)
    return _sha256(path)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateError(f"{label} must be an object: {path}")
    return value


def configure_legacy_engine(args: argparse.Namespace) -> None:
    """Narrowly configure paths/patterns; do not hard-code a JAR cardinality."""
    legacy.FORBIDDEN_SOURCE = FORBIDDEN_SOURCE
    legacy.PIPELINE_PREPARED_TARGET = args.target.resolve()
    legacy.CANDIDATE13_CLIENT_ROOT = args.client_root.resolve()
    legacy.CANDIDATE13_CLIENT_PREPARE_REPORT = args.client_prepare_report.resolve()
    legacy.ATTEMPT_MARKER_NAME = ATTEMPT_MARKER
    # The engine resolves these globals at call time.  Candidate14 keeps the
    # same battle-tested orchestration but reports Candidate14 terminology.
    legacy.GateError = GateError
    extra_patterns = (
        (
            "SCARECROW_CODEC_FAILURE",
            legacy.re.compile(
                r"(?:kaleidoscope_cookery:scarecrow|ScarecrowEntity)"
                r"[^\r\n]*(?:codec|exception|failed|Slot \d+ not in valid range)|"
                r"(?:codec|exception|failed|Slot \d+ not in valid range)"
                r"[^\r\n]*(?:kaleidoscope_cookery:scarecrow|ScarecrowEntity)",
                legacy.re.I,
            ),
        ),
        (
            "SCARECROW_SLOT_RANGE_FAILURE",
            legacy.re.compile(r"Slot \d+ not in valid range\s*-\s*\[[^\]]+\)", legacy.re.I),
        ),
        (
            "TRIAL_SPAWNER_NOT_A_MAP",
            legacy.re.compile(
                r"(?:TrialSpawnerBlockEntity[^\r\n]*Not a map|"
                r"Not a map[^\r\n]*minecraft:trial_chamber/)",
                legacy.re.I,
            ),
        ),
    )
    existing = {name for name, _ in legacy.STRICT_COMMON_PATTERNS}
    legacy.STRICT_COMMON_PATTERNS = legacy.STRICT_COMMON_PATTERNS + tuple(
        row for row in extra_patterns if row[0] not in existing
    )
    # The legacy round engine resolves this function from its module globals.
    # Replace that single hook with Candidate14's narrow classifier.  It still
    # runs every existing strict marker, but removes only reviewed stale recipe
    # lines before doing so; all other ServerRecipeBook errors remain NO_GO.
    legacy.assert_no_strict_markers = assert_no_strict_markers_candidate14


def validate_paths(args: argparse.Namespace) -> None:
    target = args.target.resolve()
    client = args.client_root.resolve()
    report = args.report.resolve()
    prepare = args.prepare_report.resolve()
    if not _is_within(target, ALLOWED_EXTERNAL_ROOT) or _is_within(target, FORBIDDEN_SOURCE):
        raise GateError("target must be a disposable runtime under migration-audit-work")
    if not _is_within(prepare, ALLOWED_EXTERNAL_ROOT) or _is_within(prepare, FORBIDDEN_SOURCE):
        raise GateError("prepare report must be a disposable external report")
    if not _is_within(client, OUTPUTS) and not _is_within(client, ALLOWED_EXTERNAL_ROOT):
        raise GateError("client root must stay under workspace outputs or D: migration-audit-work")
    # Runtime logs and artifacts are large; allow them under the isolated D:\
    # migration area so a long gate does not consume the system drive.  The
    # release tree/source remain separately protected and the report still
    # must be an ordinary path (not a link) inside one audited root.
    if not (_is_within(report, OUTPUTS) or _is_within(report, ALLOWED_EXTERNAL_ROOT)):
        raise GateError("gate report must stay under workspace outputs or migration-audit-work")
    if report.is_symlink():
        raise GateError("gate report may not be a symlink")
    if client in (OUTPUTS, ALLOWED_EXTERNAL_ROOT):
        raise GateError("client root must be a disposable isolated directory")
    if _is_reparse(client):
        raise GateError("client root may not be a symlink")
    # The preparer permits only immutable assets/libraries/versions junctions.
    # Keep the gate fail-closed for mutable roots and reject links into any
    # protected migration/release/runtime tree.
    for name in ("mods", "resourcepacks", "natives"):
        item = client / name
        if not item.is_dir() or _is_reparse(item):
            raise GateError(f"client mutable directory is missing or linked: {item}")
    for name in ("assets", "libraries", "versions"):
        item = client / name
        if not item.is_dir():
            raise GateError(f"client shared directory is missing: {item}")
        try:
            attrs = getattr(os.lstat(item), "st_file_attributes", 0)
        except OSError as exc:
            raise GateError(f"cannot inspect client shared directory: {item}") from exc
        if attrs & 0x400:
            resolved = item.resolve()
            # A shared library cache is intentionally allowed to live in the
            # migration-audit area.  Only reject links into the historical
            # backup, frozen staging, published release, or this disposable
            # runtime target; the preparer's exact source-target check handles
            # the immutable cache identity.
            protected = (
                FORBIDDEN_SOURCE,
                args.target.resolve(),
                args.release_root.resolve(),
                ALLOWED_EXTERNAL_ROOT / "cutover-staging-incoming-20260811-candidate13-20260812",
            )
            if any(_is_within(resolved, root) or _is_within(root, resolved) for root in protected):
                raise GateError(f"client shared directory resolves into protected tree: {item}")
    if args.target == args.release_root or _is_within(target, args.release_root.resolve()):
        raise GateError("published release tree may never be used as a runtime target")
    if args.server_port != 12341 or args.rcon_port != 12342 or args.voice_port != 26341:
        raise GateError("Candidate14 private gate ports are locked to 12341/12342/26341")


def validate_prepare_report(
    path: Path,
    target: Path,
    server_port: int,
    rcon_port: int,
    voice_port: int,
    release: dict[str, Any],
) -> dict[str, Any]:
    value = _read_json(path, "Candidate14 runtime prepare report")
    if value.get("schema") != 1 or value.get("status") != "PREPARED":
        raise GateError("runtime prepare report is not PREPARED")
    if Path(str(value.get("output", ""))).resolve() != target.resolve():
        raise GateError("runtime prepare report is bound to another target")
    if Path(str(value.get("mods", ""))).resolve() != (
        Path(release["root"]) / "server-mods"
    ).resolve():
        raise GateError("runtime prepare report is bound to another release mod set")
    ports = value.get("ports")
    if ports != {"server": server_port, "rcon": rcon_port, "voice": voice_port}:
        raise GateError("runtime prepare report port binding mismatch")
    network = value.get("network_safety")
    if (
        not isinstance(network, dict)
        or network.get("server_bind") != "127.0.0.1"
        or network.get("online_mode") is not False
        or network.get("mineastr_enabled") is not False
    ):
        raise GateError("runtime prepare report is not loopback/offline safe")
    resource = value.get("resource_sanitization")
    if not isinstance(resource, dict):
        raise GateError("runtime prepare report lacks sanitizer evidence")
    manifest = resource.get("runtime_mod_manifest")
    expected = release["runtime_server_identity"]
    observed = {
        "files": manifest.get("file_count") if isinstance(manifest, dict) else None,
        "bytes": manifest.get("bytes") if isinstance(manifest, dict) else None,
        "bundle_sha256": str(
            manifest.get("bundle_sha256", "") if isinstance(manifest, dict) else ""
        ).upper(),
    }
    expected_core = {key: expected[key] for key in ("files", "bytes", "bundle_sha256")}
    if observed != expected_core:
        raise GateError(f"sanitized runtime bundle mismatch: {observed} != {expected_core}")
    changes = resource.get("changes")
    jars = {
        Path(str(row.get("path", ""))).name
        for row in changes or []
        if isinstance(row, dict) and row.get("kind") == "jar-resource-sanitize"
    }
    if jars != SANITIZER_JARS:
        raise GateError(f"runtime sanitizer changed an unexpected JAR set: {sorted(jars)}")
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "runtime_server_bundle": observed,
        "sanitized_jars": sorted(jars),
        "production_server_properties_modified": False,
    }


def validate_client_prepare_report(
    path: Path,
    client_root: Path,
    client_bundle: dict[str, Any],
    release: dict[str, Any],
) -> dict[str, Any]:
    value = _read_json(path, "Candidate14 client prepare report")
    if (
        value.get("schema") != 1
        or value.get("status") != "PREPARED"
        or value.get("candidate") != 14
        or Path(str(value.get("output_root", ""))).resolve() != client_root.resolve()
        or value.get("source_unchanged") is not True
        or value.get("java_started") is not False
        or value.get("prism_started") is not False
    ):
        raise GateError("Candidate14 client prepare report identity mismatch")
    bound = value.get("release")
    expected_client = release["client_manifest"]
    if (
        not isinstance(bound, dict)
        or Path(str(bound.get("root", ""))).resolve() != Path(release["root"]).resolve()
        or str(bound.get("ready_sha256", "")).upper()
        != release["ready"]["sha256"]
        or str(bound.get("release_lock_sha256", "")).upper()
        != release["ready"]["sha256"]
        or str(bound.get("client_manifest_sha256", "")).upper()
        != expected_client["sha256"]
        or str(bound.get("client_bundle_sha256", "")).upper()
        != expected_client["bundle_sha256"]
        or bound.get("file_count") != expected_client["files"]
    ):
        raise GateError("client preparation is bound to another Candidate14 release")
    server = value.get("server")
    if (
        not isinstance(server, dict)
        or server.get("port") != 12341
        or server.get("accept_remote_resource_pack") is not False
        or server.get("servers_dat_acceptTextures") is not False
        or server.get("server_properties_modified") is not False
    ):
        raise GateError("client preparation remote-resource-pack policy mismatch")
    actual = legacy.bundle_binding(client_root / "mods")
    expected = {
        key: expected_client[key] for key in ("files", "bytes", "bundle_sha256")
    }
    release_common.validate_runtime_bundles(
        release,
        release["runtime_server_identity"],
        actual,
    )
    if {key: actual[key] for key in expected} != expected:
        raise GateError("prepared client mod set differs from release manifest")
    if value.get("mcmodsync", {}).get("runtime_install") != "NOT_INSTALLED":
        raise GateError("unconfigured MCModSync must not be present in first release")
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "client_bundle": actual,
        "remote_resource_pack_declined": True,
    }


def claim_attempt(target: Path, release: dict[str, Any]) -> dict[str, Any]:
    marker = target / ATTEMPT_MARKER
    payload = (
        json.dumps(
            {
                "schema": 1,
                "candidate": 14,
                "status": "RUNTIME_ATTEMPT_CLAIMED",
                "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "target": str(target.resolve()),
                "release_ready_sha256": release["ready"]["sha256"],
                "release_scoped_exactness": True,
                "permanent_mod_count_cap": False,
                "reuse_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise GateError("Candidate14 runtime was already attempted and must not be reused") from exc
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return legacy.file_artifact(marker)


def run_checkpoint(
    world: Path, label: str, workers: int, artifact_dir: Path
) -> dict[str, Any]:
    json_path = artifact_dir / f"deferred-item-{label}.json"
    md_path = artifact_dir / f"deferred-item-{label}.md"
    value = checkpoint_audit.audit(world, label, workers)
    _atomic_json(json_path, value)
    if value.get("status") != "PASS":
        raise GateError(f"deferred-item checkpoint {label} contains parse errors")
    checkpoint_audit.scanner.write_markdown(value, md_path)
    return {
        "label": label,
        "report": legacy.file_artifact(json_path),
        "markdown": legacy.file_artifact(md_path),
        "matches": value.get("totals", {}).get("matches"),
        "errors": value.get("totals", {}).get("errors"),
    }


def execute(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    validate_paths(args)
    release = release_common.validate_release(
        args.release_root,
        args.ready_sha256,
        args.build_report,
        args.build_report_sha256,
    )
    configure_legacy_engine(args)
    recipe_allowlist = _recipe_book_allowlist()
    target = args.target.resolve()
    client_root = args.client_root.resolve()
    report_path = args.report.resolve()
    artifact_dir = report_path.parent / (
        report_path.stem
        + "-artifacts-"
        + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    if args.artifact_root is not None:
        artifact_root = args.artifact_root.resolve()
        if not _is_within(artifact_root, ALLOWED_EXTERNAL_ROOT) or _is_within(
            artifact_root, FORBIDDEN_SOURCE
        ):
            raise GateError("artifact root must stay under D: migration-audit-work")
        if artifact_root == ALLOWED_EXTERNAL_ROOT:
            raise GateError("artifact root must be an isolated directory")
        artifact_dir = artifact_root
    if artifact_dir.exists():
        raise GateError(f"refusing to reuse artifact directory: {artifact_dir}")
    artifact_dir.mkdir(parents=True)
    report: dict[str, Any] = {
        "schema": 1,
        "status": "NO_GO",
        "category": "candidate14_dynamic_release_private_desktop_join_gate",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "target": str(target),
        "client_root": str(client_root),
        "release": release,
        "ports": {"server": 12341, "rcon": 12342, "voice": 26341},
        "rounds": [],
        "deferred_item_checkpoints": [],
        "recipe_book_audits": [],
        "recipe_book_policy": {
            "allowlist_path": str(RECIPE_BOOK_ALLOWLIST.resolve()),
            "allowlist_sha256": _sha256(RECIPE_BOOK_ALLOWLIST),
            "reviewed_unique_ids": len(recipe_allowlist["recipe_ids"]),
            "reviewed_first_round_lines": sum(
                recipe_allowlist["expected_fresh_runtime_first_round_counts"].values()
            ),
            "second_round_expected_lines": 0,
            "other_server_recipe_book_errors_block": True,
        },
        "blockers": [],
        "cleanup": {"attempted": False, "ports_closed": False},
        "safety": {
            "loopback_only": True,
            "source_and_staging_read_only": True,
            "production_server_properties_modified": False,
            "published_release_modified": False,
            "release_lock_is_not_permanent_mod_allowlist": True,
        },
    }
    runtime_attempted = False
    try:
        ports = legacy.check_ports_closed(12341, 12342, 26341)
        if not ports["all_closed"]:
            raise GateError(f"private gate ports are occupied: {ports}")
        win_args = legacy.validate_prerequisites(
            target,
            client_root,
            args.java.resolve(),
            args.powershell.resolve(),
            args.private_helper.resolve(),
            args.client_launcher.resolve(),
            args.win_args,
        )
        prepare = validate_prepare_report(
            args.prepare_report.resolve(), target, 12341, 12342, 26341, release
        )
        server_bundle = legacy.bundle_binding(target / "mods")
        client_bundle = legacy.bundle_binding(client_root / "mods")
        runtime_bundles = release_common.validate_runtime_bundles(
            release, server_bundle, client_bundle
        )
        client_prepare = validate_client_prepare_report(
            args.client_prepare_report.resolve(), client_root, client_bundle, release
        )
        properties_path = target / "server.properties"
        whitelist = legacy.normalize_disposable_whitelist(properties_path)
        properties = legacy.read_properties(properties_path)
        legacy.validate_server_properties(properties, 12341, 12342)
        local_pack = legacy.configure_local_world_resource_pack(client_root)
        remote_pack = legacy.configure_disposable_resource_pack_rejection(
            client_root, 12341, properties, properties_path
        )
        initial_world = legacy.critical_world_binding(target / "world")
        initial_computer = legacy.computer_11_on_evidence(target / "world", "before_round_1")
        report["bindings"] = {
            "runtime_prepare": prepare,
            "client_prepare": client_prepare,
            "runtime_bundles": runtime_bundles,
            "win_args": legacy.file_artifact(win_args),
            "world_before": initial_world,
        }
        report["disposable_setup"] = {
            "whitelist": whitelist,
            "local_resource_pack": local_pack,
            "remote_resource_pack": remote_pack,
        }
        report["cc_computer_on_checks"] = [initial_computer]
        report["attempt_marker"] = claim_attempt(target, release)
        # Do not let the legacy helper create a second Candidate13 marker.
        legacy.claim_fresh_gate_attempt = lambda _target: report["attempt_marker"]
        rcon_password = properties["rcon.password"]
        local_expect = {
            "expected_sha256": local_pack["destination"]["after"]["sha256"],
            "expected_bytes": local_pack["destination"]["after"]["bytes"],
        }
        remote_expect = {
            "expected_properties_sha256": remote_pack["server_properties"]["after_sha256"],
            "expected_properties_fingerprint": remote_pack["server_properties"]["semantic_fingerprint"],
        }
        for round_number in (1, 2):
            legacy.validate_local_world_resource_pack(client_root, **local_expect)
            legacy.validate_disposable_resource_pack_rejection(
                client_root, 12341, properties_path, **remote_expect
            )
            runtime_attempted = True
            round_report = legacy.run_round(
                target=target,
                artifact_dir=artifact_dir,
                round_number=round_number,
                java=args.java.resolve(),
                powershell=args.powershell.resolve(),
                helper=args.private_helper.resolve(),
                launcher=args.client_launcher.resolve(),
                client_root=client_root,
                win_args=args.win_args,
                server_port=12341,
                rcon_port=12342,
                rcon_password=rcon_password,
                server_memory_mb=args.server_memory_mb,
                client_memory_mb=args.client_memory_mb,
                startup_timeout=args.startup_timeout_seconds,
                bootstrap_timeout=args.bootstrap_timeout_seconds,
                join_timeout=args.join_timeout_seconds,
                client_launch_timeout=args.client_launch_timeout_seconds,
                client_session_timeout=args.client_session_timeout_seconds,
                teleport_pause=args.teleport_pause_seconds,
                settle_seconds=args.settle_seconds,
            )
            recipe_audit = validate_round_recipe_book(
                round_number, target / "logs" / "latest.log", recipe_allowlist
            )
            round_report["recipe_book"] = recipe_audit
            report["rounds"].append(round_report)
            report["recipe_book_audits"].append(recipe_audit)
            legacy.wait_ports_closed(12341, 12342, 26341)
            checkpoint_label = f"runtime_round_{round_number}_after_stop"
            checkpoint = run_checkpoint(
                target / "world", checkpoint_label, args.ledger_workers, artifact_dir
            )
            report["deferred_item_checkpoints"].append(checkpoint)
            report["cc_computer_on_checks"].append(
                legacy.computer_11_on_evidence(
                    target / "world", f"after_round_{round_number}"
                )
            )
        checkpoint_bindings = [
            (
                row["label"],
                Path(row["report"]["path"]),
                row["label"],
            )
            for row in report["deferred_item_checkpoints"]
        ]
        ledger = ledger_verify.verify(args.baseline_ledger.resolve(), checkpoint_bindings)
        ledger_path = artifact_dir / "deferred-item-semantic-ledger.json"
        _atomic_json(ledger_path, ledger)
        report["deferred_item_ledger"] = {
            "status": ledger.get("status"),
            "report": legacy.file_artifact(ledger_path),
            "protected_owner_uuid": ledger.get("protected_owner_uuid"),
            "checkpoints": sorted(ledger.get("checkpoints", {})),
        }
        if ledger.get("status") != "PASS":
            raise GateError(f"deferred-item semantic ledger is not PASS: {ledger.get('status')}")
        report["bindings"]["world_after"] = legacy.critical_world_binding(target / "world")
        assertions = {
            "round_count": len(report["rounds"]),
            "round_sequence": [row.get("round") for row in report["rounds"]],
            "each_round_clean": all(
                row.get("status") == "PASS"
                and row.get("server_exit_code") == 0
                and row.get("join", {}).get("new_join_lines") == 1
                and legacy.valid_clean_private_client_state(row.get("client_state"))
                for row in report["rounds"]
            ),
            "ledger_pass": ledger.get("status") == "PASS",
            "checkpoint_count": len(report["deferred_item_checkpoints"]),
            "computer_11_on_preserved": all(
                row.get("on_preserved") is True for row in report["cc_computer_on_checks"]
            ),
            "release_scoped_exact_bundles": runtime_bundles[
                "release_scoped_exact_bundles"
            ],
            "current_file_counts_are_not_production_caps": runtime_bundles[
                "current_file_counts_are_not_production_caps"
            ],
        }
        report["strict_assertions"] = assertions
        if (
            assertions["round_count"] != 2
            or assertions["round_sequence"] != [1, 2]
            or assertions["checkpoint_count"] != 2
            or not all(
                assertions[key]
                for key in (
                    "each_round_clean",
                    "ledger_pass",
                    "computer_11_on_preserved",
                    "release_scoped_exact_bundles",
                    "current_file_counts_are_not_production_caps",
                )
            )
        ):
            raise GateError(f"Candidate14 final strict assertion failed: {assertions}")
        report["status"] = "PASS"
    except Exception as exc:
        report["blockers"].append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        report["cleanup"]["attempted"] = True
        try:
            cleanup = (
                legacy.wait_ports_closed(12341, 12342, 26341, timeout=45)
                if runtime_attempted
                else legacy.check_ports_closed(12341, 12342, 26341)
            )
        except Exception as exc:
            cleanup = legacy.check_ports_closed(12341, 12342, 26341)
            report["blockers"].append(
                {"type": "PORT_CLEANUP_FAILURE", "message": str(exc)}
            )
        report["cleanup"]["port_state"] = cleanup
        report["cleanup"]["ports_closed"] = cleanup["all_closed"]
        if report["blockers"] or not cleanup["all_closed"]:
            report["status"] = "NO_GO"
        report["artifact_directory"] = str(artifact_dir.resolve())
        report["generated_at_utc_completed"] = dt.datetime.now(
            dt.timezone.utc
        ).isoformat(timespec="seconds")
    return report, _atomic_json(report_path, report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a dynamic Candidate14 two-round join/data-safety gate"
    )
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--ready-sha256", required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--build-report-sha256", required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--prepare-report", type=Path, required=True)
    parser.add_argument("--client-prepare-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="fresh D:-resident directory for large gate logs/artifacts",
    )
    parser.add_argument("--baseline-ledger", type=Path, default=BASELINE_LEDGER)
    parser.add_argument("--server-port", type=int, default=12341)
    parser.add_argument("--rcon-port", type=int, default=12342)
    parser.add_argument("--voice-port", type=int, default=26341)
    parser.add_argument("--ledger-workers", type=int, default=20)
    parser.add_argument("--java", type=Path, default=legacy.DEFAULT_JAVA)
    parser.add_argument("--powershell", type=Path, default=legacy.DEFAULT_POWERSHELL)
    parser.add_argument("--private-helper", type=Path, default=legacy.DEFAULT_PRIVATE_HELPER)
    parser.add_argument("--client-launcher", type=Path, default=legacy.DEFAULT_CLIENT_LAUNCHER)
    parser.add_argument(
        "--win-args", default="@libraries/net/neoforged/neoforge/21.1.241/win_args.txt"
    )
    parser.add_argument("--server-memory-mb", type=int, default=4096)
    parser.add_argument("--client-memory-mb", type=int, default=2048)
    parser.add_argument("--bootstrap-timeout-seconds", type=int, default=120)
    parser.add_argument("--startup-timeout-seconds", type=int, default=20)
    parser.add_argument("--join-timeout-seconds", type=int, default=180)
    parser.add_argument("--client-launch-timeout-seconds", type=int, default=150)
    parser.add_argument("--client-session-timeout-seconds", type=int, default=300)
    parser.add_argument("--teleport-pause-seconds", type=float, default=10.0)
    parser.add_argument("--settle-seconds", type=float, default=15.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.ledger_workers <= 20:
        raise SystemExit("--ledger-workers must be in [1,20]")
    try:
        report, digest = execute(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.report.resolve()),
                "report_sha256": digest,
                "ports_closed": report["cleanup"]["ports_closed"],
                "permanent_mod_count_cap": False,
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
