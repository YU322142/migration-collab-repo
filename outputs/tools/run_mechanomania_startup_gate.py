#!/usr/bin/env python3
"""One-round, fail-closed startup/join smoke for the matched Mechanomania build.

This gate is intentionally disposable.  It accepts a prepared D:-resident
runtime and client, requires the exact audited MineAstr, YACL, Content Backport,
Hot Bath, and CEI compatibility JARs on both sides, requires MCModSync to be
absent from active runtime paths, launches the client on a private desktop, and
performs the historically dangerous teleports plus the migrated Create
carriage location before stopping both processes cleanly.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from typing import Any


TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_candidate13_join_gate as legacy


ALLOWED = Path(r"<AUDIT_ROOT>").resolve()
FORBIDDEN = Path(r"<TRANS_ROOT>\20260807").resolve()
MINEASTR_NAME = "mineastr-neoforge-1.21.1-0.6.26.jar"
MINEASTR_SHA256 = "0264D729A3343BE1645B5AFE16C15A7A57C7E89A9405FA67EC80EE06D4A148D8"
MINEASTR_BYTES = 257_982
YACL_NAME = "yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar"
YACL_SHA256 = "673FECBFFAD26BB6D025FB5F60560CF6340E542BDF091D8D66074490515292F3"
YACL_BYTES = 1_111_051
CONTENT_BACKPORT_NAME = "backport-1.5-cat-serializer-fix.1.jar"
CONTENT_BACKPORT_SHA256 = "34291AF9D81B6AEE0780F5F511B2A9594664F36906AED40687DF1C7009E68B1D"
CONTENT_BACKPORT_BYTES = 15_336_561
HOTBATH_NAME = "hotbath-1.21.1-3.0.0-registry-fix.1.jar"
HOTBATH_SHA256 = "1B53A2B7B2C6476BBAD3ACE344316DA7ABE62854967DE322E9A25CA1D5C7681A"
HOTBATH_BYTES = 712_893
WORLD_EDIT_NAME = "worldedit-mod-7.3.8-direction-property-fix.1.jar"
WORLD_EDIT_SHA256 = "8EB5E39AA914EB1B09307B6C004478BD1263655FCCA880580673481EBFEF9283"
WORLD_EDIT_BYTES = 6_264_309
DATA_REPAIR_REPORT_SHA256 = "49CD94FA1A86DE94148EB028120C724BD9AE93DCB0C57B164F7414BD45FE33FC"
CONTENT_REPAIR_REPORT_SHA256 = "9F5C5CF15CC6F2DE1B33F7083D87A9AE519DFB77EC2E4044E7D43C843C9F1888"
FOLLOWUP_REPAIR_REPORT_SHA256 = "42B7F32D28EBFBA81497DA23294EDA9E386A68AFDC2CE94636EAC0F2CA17A49B"
FOLLOWUP_APPLY_REPORT_SHA256 = "C403DB5E7848D6356AE4B2E91B5ABB5C591C1E55926E9ADB77C5516E4FFA9B74"
FOLLOWUP_DNT_NAME = "DnT-ancient-city-overhaul-v2 [NeoForge].jar"
FOLLOWUP_DNT_SHA256 = "A7D3ABB6C39FB50C791D52E596C9D14C22D0287EAF6BA055A687C31C0A4C8A7E"
FOLLOWUP_DNT_BYTES = 945_155
FOLLOWUP_TRACKS_NAME = "tracks-neoforge-1.21.1-1.0.1.jar"
FOLLOWUP_TRACKS_SHA256 = "3119FA84955907FD734EF77F2296EC2E546F4442BC3AE13B04046C5D71F61CCF"
FOLLOWUP_TRACKS_BYTES = 165_818
FOLLOWUP_IRON_NAME = "irons_spellbooks-1.21.1-3.15.6.jar"
FOLLOWUP_IRON_SHA256 = "BD8235AEF2F7F4827D8005E9700C1C04E5F3A84C50E0F92685674CAC49E985DB"
FOLLOWUP_IRON_BYTES = 13_584_342
FOLLOWUP_RING_RELATIVE = Path(
    "kubejs/data/irons_spellbooks/loot_table/test/ring_gen_break_me.json"
)
FOLLOWUP_SUPERSEDED_RELATIVES = frozenset(
    {
        "DnT-ancient-city-overhaul-v2 [NeoForge].jar",
        "tracks-neoforge-1.21.1-1.0.1.jar",
    }
)
DATA_REPAIR_OUTPUT_BYTES = {
    "biomespy-neoforge-1.21.1-1.3.3.jar": 38_355,
    "cmpackagecouriers-neoforge-2.3.0.jar": 284_554,
    "create_compressed-2.2.0-neoforge-1.21.1.jar": 158_857,
    "create_connected-1.3.2-mc1.21.1.jar": 6_773_076,
    "createadditionallogistics-1.21.1-1.4.5.jar": 952_653,
    "createdeco-2.1.3.jar": 3_323_409,
    "creategearsandtavern-1.1.6.jar": 724_827,
    "DnT-ancient-city-overhaul-v2 [NeoForge].jar": 945_261,
    "irons_spellbooks-1.21.1-3.15.6.jar": 13_584_342,
    "railways-0.2.1+neoforge-mc1.21.1.jar": 12_120_869,
    "tracks-neoforge-1.21.1-1.0.1.jar": 165_882,
    "kubejs/data/c6c/worldgen/biome/end_cherry_grove.json": 3_044,
    "kubejs/data/minecraft/worldgen/biome/beach.json": 3_609,
    "kubejs/data/minecraft/worldgen/biome/desert.json": 5_421,
    "kubejs/data/minecraft/worldgen/biome/mangrove_swamp.json": 4_819,
    "kubejs/data/minecraft/worldgen/biome/swamp.json": 4_947,
    "kubejs/data/minecraft/worldgen/biome/wooded_badlands.json": 4_749,
    "kubejs/data/touhou_little_maid/curios/entities/curios.json": 188,
}
YUUSHYA_ORIGINAL_NAME = "yuushya-1.21.0-neoforge-2.3.0.jar"
YUUSHYA_ORIGINAL_SHA256 = "C410C51E1ECDD9D3FF55EB34B84D71DA761A8990EC0993A766C9BA40E8C360E8"
YUUSHYA_ORIGINAL_BYTES = 28_197_448
YUUSHYA_PATCHED_NAME = "yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.1.jar"
YUUSHYA_PATCHED_SHA256 = "31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D"
YUUSHYA_PATCHED_BYTES = 28_197_402
TLM_NAME = "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
TLM_SHA256 = "F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27"
TLM_BYTES = 24_408_776
MAID_JS_RELATIVE = "kubejs/server_scripts/maid.js"
MAID_JS_SHA256 = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
MAID_JS_BYTES = 119
TLM_MANIFEST_SHA256 = "FCCD33E1B0AE4B4EF7FBB5132D870504CC00F94880556FCE92E4518600B1A040"
TLM_OVERLAY_ARTIFACTS = {
    "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/maid/spawn_maid.json": {
        "bytes": 443,
        "sha256": "2904581BFC4704CAF6829ADE482959E766B1A2EDA76C03FF3F23945E4625BD9C",
    },
    "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json": {
        "bytes": 980,
        "sha256": "39CBE907D067E08C6FAD58FBB9601339D8A6141B236BD1F62FFEFB1603F25D3A",
    },
}
MC_MODSYNC_RE = re.compile(r"mcmodsync", re.I)
CEI_RE = re.compile(r"create-enchantment-industry", re.I)
CONTENT_BACKPORT_RE = re.compile(r"^backport-.*\.jar$", re.I)
HOTBATH_RE = re.compile(r"^hotbath(?:-|\.jar$)", re.I)
WORLD_EDIT_RE = re.compile(r"worldedit", re.I)
EXTRA_RISK_SITE = {
    "name": "create_carriage_orientation_crash",
    "x": -99,
    "y": 63,
    "z": -98,
}
CEI_FORGER_RISK_SITES = (
    {
        "name": "cei_blaze_forger_near",
        "x": -176,
        "y": 63,
        "z": -127,
    },
    {
        "name": "cei_blaze_forger_far",
        "x": 27319,
        "y": 72,
        "z": -12892,
    },
)
ATTEMPT_MARKER = ".mechanomania-startup-gate-attempt.json"
ERROR_LINE_RE = re.compile(r"^.*\[[^]\r\n]+/ERROR\] \[([^]\r\n]+)\]: (.*)$")
RUNTIME_DIST_CLEANER_LOGGER = "net.neoforged.fml.common.asm.RuntimeDistCleaner/DISTXFORM"
RUNTIME_DIST_CLEANER_MAX_COUNTS = {
    "Attempted to load class net/minecraft/client/Minecraft for invalid dist DEDICATED_SERVER": 1,
    "Attempted to load class net/minecraft/client/multiplayer/ClientLevel for invalid dist DEDICATED_SERVER": 12,
    "Attempted to load class net/minecraft/client/Options for invalid dist DEDICATED_SERVER": 1,
    "Attempted to load class net/minecraft/client/renderer/LevelRenderer for invalid dist DEDICATED_SERVER": 1,
}
REFMAP_LOGGER = "org.sinytra.connector.transformer.transform.RefmapRemapper/"
REFMAP_MESSAGE = "Error opening jar file"
REFMAP_CAUSE = r"java.nio.file.NoSuchFileException: \~nonexistent"
CONNECTION_LOGGER = "net.minecraft.network.Connection/"
CONNECTION_MESSAGE = "Exception caught in connection"
CONNECTION_CAUSE = "java.net.SocketException: Connection reset"


class GateError(RuntimeError):
    pass


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def artifact(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise GateError(f"missing or linked artifact: {path}")
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}


def normalized_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", value):
        raise GateError(f"{label} must contain exactly 64 hexadecimal characters")
    return value.upper()


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{label} must be a JSON object")
    return value


def load_locked_json(
    path: Path,
    supplied_sha256: str,
    locked_sha256: str,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    supplied = normalized_sha256(supplied_sha256, f"{label} command-line SHA-256")
    locked = normalized_sha256(locked_sha256, f"{label} built-in SHA-256 lock")
    if supplied != locked:
        raise GateError(f"{label} command-line SHA-256 is not the built-in audited lock")
    report_artifact = artifact(path)
    if report_artifact["sha256"] != locked:
        raise GateError(f"{label} file SHA-256 mismatch: {report_artifact}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read {label}: {exc}") from exc
    return require_mapping(payload, label), report_artifact


def safe_report_target(root: Path, relative: Any, kind: str, label: str) -> tuple[str, Path]:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise GateError(f"{label} has a non-canonical relative path: {relative!r}")
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or str(parsed) != relative or any(part in ("", ".", "..") for part in parsed.parts):
        raise GateError(f"{label} has an unsafe relative path: {relative!r}")
    if kind == "jar":
        if len(parsed.parts) != 1 or parsed.suffix.lower() != ".jar":
            raise GateError(f"{label} JAR target must be a single .jar filename: {relative!r}")
        target = root / "mods" / parsed.name
    elif kind == "loose":
        if parsed.parts[:2] != ("kubejs", "data") or parsed.suffix.lower() != ".json":
            raise GateError(f"{label} loose target must be a kubejs/data JSON: {relative!r}")
        target = root.joinpath(*parsed.parts)
    elif kind == "overlay":
        if parsed.parts[:2] != ("kubejs", "assets") or parsed.suffix.lower() != ".json":
            raise GateError(f"{label} overlay target must be a kubejs/assets JSON: {relative!r}")
        target = root.joinpath(*parsed.parts)
    else:
        raise GateError(f"{label} has unsupported target kind: {kind!r}")
    resolved = target.resolve()
    if not within(resolved, root):
        raise GateError(f"{label} target escapes its side root: {resolved}")
    return relative, resolved


def validate_reported_artifact(
    reported: Any,
    expected_path: Path,
    label: str,
    *,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    row = require_mapping(reported, label)
    if set(row) != {"path", "bytes", "sha256"}:
        raise GateError(f"{label} artifact fields drifted: {sorted(row)}")
    try:
        reported_path = Path(row["path"]).resolve()
    except (OSError, TypeError, ValueError) as exc:
        raise GateError(f"{label} has an invalid artifact path") from exc
    if reported_path != expected_path.resolve():
        raise GateError(f"{label} artifact path mismatch: {reported_path}")
    reported_sha = normalized_sha256(row["sha256"], f"{label} reported SHA-256")
    if not isinstance(row["bytes"], int) or isinstance(row["bytes"], bool) or row["bytes"] < 0:
        raise GateError(f"{label} reported byte count is invalid")
    if expected_bytes is not None and row["bytes"] != expected_bytes:
        raise GateError(f"{label} reported byte count drifted: {row['bytes']}")
    if expected_sha256 is not None and reported_sha != normalized_sha256(expected_sha256, label):
        raise GateError(f"{label} reported SHA-256 drifted: {reported_sha}")
    actual = artifact(expected_path)
    if actual["bytes"] != row["bytes"] or actual["sha256"] != reported_sha:
        raise GateError(f"{label} installed artifact does not match locked report: {actual}")
    return actual


def audit_mcmodsync_globally_absent(root: Path, side: str) -> dict[str, Any]:
    scanned = 0
    matches: list[str] = []
    try:
        for item in root.rglob("*"):
            scanned += 1
            if MC_MODSYNC_RE.search(item.name) or item.name.casefold() == "modsync.properties":
                matches.append(str(item.resolve()))
    except OSError as exc:
        raise GateError(f"cannot audit MCModSync absence in {side}: {exc}") from exc
    if matches:
        raise GateError(f"MCModSync must be globally absent from {side}: {matches[:10]}")
    return {"root": str(root.resolve()), "scanned_entries": scanned, "matches": [], "globally_disabled": True}


def validate_data_resource_repair_report(
    report_path: Path,
    expected_report_sha256: str,
    runtime: Path,
    client: Path,
    superseded_relatives: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    payload, locked_report = load_locked_json(
        report_path,
        expected_report_sha256,
        DATA_REPAIR_REPORT_SHA256,
        "Attempt10 data/resource apply report",
    )
    if payload.get("schema") != "attempt10-data-resource-integration/v1" or payload.get("status") != "PASS_APPLIED":
        raise GateError("Attempt10 data/resource apply report schema/status mismatch")
    targets = require_mapping(payload.get("targets"), "data/resource targets")
    if Path(targets.get("server", "")).resolve() != runtime or Path(targets.get("client", "")).resolve() != client:
        raise GateError("Attempt10 data/resource report target roots do not match this gate")
    expected_target_fields = {
        "source_exact": 29,
        "already_patched_exact": 0,
        "mcmodsync_absent_before": True,
        "mcmodsync_absent_after": True,
    }
    for key, expected in expected_target_fields.items():
        if targets.get(key) != expected:
            raise GateError(f"Attempt10 data/resource target field drifted: {key}")
    mcmodsync = require_mapping(payload.get("mcmodsync"), "data/resource MCModSync policy")
    if mcmodsync != {
        "client_install_currently_allowed": False,
        "policy": "globally absent for this Attempt10 integration",
        "release_selected": False,
        "server_install_allowed": False,
    }:
        raise GateError("Attempt10 data/resource MCModSync policy drifted")
    application = require_mapping(payload.get("application"), "data/resource application")
    if application.get("jar_files_by_side") != {"client": 11, "server": 11}:
        raise GateError("Attempt10 data/resource JAR side counts drifted")
    if application.get("loose_files_by_side") != {"client": 0, "server": 7}:
        raise GateError("Attempt10 data/resource loose-file side counts drifted")
    if application.get("target_operations") != 29:
        raise GateError("Attempt10 data/resource target operation count drifted")
    result = require_mapping(payload.get("application_result"), "data/resource application result")
    if result != {"already_patched": 0, "changed": 29, "mode": "apply", "rolled_back": False}:
        raise GateError("Attempt10 data/resource application result is not the exact successful apply state")
    plan = application.get("plan")
    if not isinstance(plan, list) or len(plan) != 18:
        raise GateError("Attempt10 data/resource plan must contain exactly 18 source rows")
    unknown_superseded = superseded_relatives - set(DATA_REPAIR_OUTPUT_BYTES)
    if unknown_superseded:
        raise GateError(f"unknown explicitly superseded data/resource targets: {sorted(unknown_superseded)}")
    rows: list[dict[str, Any]] = []
    seen_relatives: set[str] = set()
    seen_targets: set[Path] = set()
    kind_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    for index, raw in enumerate(plan):
        row = require_mapping(raw, f"data/resource plan row {index}")
        kind = row.get("kind")
        relative = row.get("relative")
        sides = row.get("sides")
        if kind == "jar":
            expected_sides = ["server", "client"]
        elif kind == "loose":
            expected_sides = ["server"]
        else:
            raise GateError(f"data/resource plan row {index} has invalid kind: {kind!r}")
        if sides != expected_sides:
            raise GateError(f"data/resource plan row {index} side rule drifted: {sides!r}")
        if relative in seen_relatives:
            raise GateError(f"duplicate data/resource plan relative path: {relative!r}")
        seen_relatives.add(relative)
        if relative not in DATA_REPAIR_OUTPUT_BYTES:
            raise GateError(f"unlocked data/resource target in plan: {relative!r}")
        output_sha = normalized_sha256(row.get("output_sha256"), f"data/resource row {index} output SHA-256")
        normalized_sha256(row.get("source_sha256"), f"data/resource row {index} source SHA-256")
        for side in sides:
            root = runtime if side == "server" else client
            canonical_relative, target = safe_report_target(root, relative, kind, f"data/resource row {index}")
            if target in seen_targets:
                raise GateError(f"duplicate expanded data/resource target: {target}")
            seen_targets.add(target)
            expected_bytes = DATA_REPAIR_OUTPUT_BYTES[canonical_relative]
            if canonical_relative in superseded_relatives:
                if kind != "jar":
                    raise GateError(f"only JAR targets may be explicitly superseded: {canonical_relative}")
                rows.append(
                    {
                        "kind": kind,
                        "side": side,
                        "relative": canonical_relative,
                        "base_artifact": {"bytes": expected_bytes, "sha256": output_sha},
                        "state": "SUPERSEDED_BY_LOCKED_FOLLOWUP",
                    }
                )
            else:
                actual = artifact(target)
                if actual["bytes"] != expected_bytes or actual["sha256"] != output_sha:
                    raise GateError(f"{side} data/resource target hash/size mismatch: {actual}")
                rows.append(
                    {
                        "kind": kind,
                        "side": side,
                        "relative": canonical_relative,
                        "artifact": actual,
                        "state": "INSTALLED_EXACT",
                    }
                )
            kind_counts[kind] += 1
            side_counts[side] += 1
    if seen_relatives != set(DATA_REPAIR_OUTPUT_BYTES):
        missing = sorted(set(DATA_REPAIR_OUTPUT_BYTES) - seen_relatives)
        raise GateError(f"locked data/resource targets are missing from plan: {missing}")
    if len(rows) != 29 or kind_counts != Counter({"jar": 22, "loose": 7}):
        raise GateError(f"expanded data/resource operation counts drifted: {dict(kind_counts)}")
    if side_counts != Counter({"server": 18, "client": 11}):
        raise GateError(f"expanded data/resource side counts drifted: {dict(side_counts)}")
    return {
        "status": (
            "PASS_LOCKED_WITH_EXPLICIT_SUPERSESSION"
            if superseded_relatives
            else "PASS_LOCKED_AND_REHASHED"
        ),
        "report": locked_report,
        "runtime": str(runtime),
        "client": str(client),
        "source_rows": len(plan),
        "target_operations": len(rows),
        "operations_by_kind": dict(sorted(kind_counts.items())),
        "operations_by_side": dict(sorted(side_counts.items())),
        "superseded_relatives": sorted(superseded_relatives),
        "installed_targets": rows,
    }


def validate_content_repair_report(
    report_path: Path,
    expected_report_sha256: str,
    runtime: Path,
    client: Path,
) -> dict[str, Any]:
    payload, locked_report = load_locked_json(
        report_path,
        expected_report_sha256,
        CONTENT_REPAIR_REPORT_SHA256,
        "Attempt10 content-repair apply report",
    )
    if payload.get("schema") != 1 or payload.get("status") != "PASS_APPLIED":
        raise GateError("Attempt10 content-repair apply report schema/status mismatch")
    if payload.get("expected_yuushya_state") != "patched":
        raise GateError("Attempt10 content-repair Yuushya expected state drifted")
    expected_policy = {
        "spawn_box_recipe_removed": True,
        "maid_js_unchanged": True,
        "tlm_patch_side": "CLIENT",
        "yuushya_patch_side": "BOTH",
        "mcmodsync_globally_disabled": True,
    }
    if payload.get("policy") != expected_policy:
        raise GateError("Attempt10 content-repair policy drifted")
    before = require_mapping(payload.get("before"), "content-repair before state")
    after = require_mapping(payload.get("after"), "content-repair after state")
    for state, label in ((before, "before"), (after, "after")):
        if Path(state.get("server", "")).resolve() != runtime or Path(state.get("client", "")).resolve() != client:
            raise GateError(f"Attempt10 content-repair {label} roots do not match this gate")
    installed: list[dict[str, Any]] = []
    before_yuushya = require_mapping(before.get("yuushya"), "content-repair before Yuushya")
    after_yuushya = require_mapping(after.get("yuushya"), "content-repair after Yuushya")
    for side, root in (("server", runtime), ("client", client)):
        original = require_mapping(before_yuushya.get(side), f"before Yuushya {side}")
        if original.get("state") != "original":
            raise GateError(f"before Yuushya {side} state drifted")
        original_artifact = require_mapping(original.get("artifact"), f"before Yuushya {side} artifact")
        if (
            Path(original_artifact.get("path", "")).resolve() != (root / "mods" / YUUSHYA_ORIGINAL_NAME).resolve()
            or original_artifact.get("bytes") != YUUSHYA_ORIGINAL_BYTES
            or normalized_sha256(original_artifact.get("sha256"), f"before Yuushya {side} SHA-256")
            != YUUSHYA_ORIGINAL_SHA256
        ):
            raise GateError(f"before Yuushya {side} identity drifted")
        patched = require_mapping(after_yuushya.get(side), f"after Yuushya {side}")
        if patched.get("state") != "patched":
            raise GateError(f"after Yuushya {side} state drifted")
        expected_path = root / "mods" / YUUSHYA_PATCHED_NAME
        actual = validate_reported_artifact(
            patched.get("artifact"),
            expected_path,
            f"after Yuushya {side}",
            expected_bytes=YUUSHYA_PATCHED_BYTES,
            expected_sha256=YUUSHYA_PATCHED_SHA256,
        )
        selections = sorted((root / "mods").glob("yuushya*.jar"), key=lambda item: item.name.casefold())
        if selections != [expected_path]:
            raise GateError(f"{side} Yuushya selection is not exactly the patched JAR: {[item.name for item in selections]}")
        installed.append({"kind": "jar", "side": side, "role": "yuushya_patch", "artifact": actual})
    before_tlm = require_mapping(before.get("tlm"), "content-repair before TLM")
    after_tlm = require_mapping(after.get("tlm"), "content-repair after TLM")
    for side, root in (("server", runtime), ("client", client)):
        expected_path = root / "mods" / TLM_NAME
        if before_tlm.get(side) != after_tlm.get(side):
            raise GateError(f"TLM {side} identity changed across content repair")
        actual = validate_reported_artifact(
            after_tlm.get(side),
            expected_path,
            f"unchanged TLM {side}",
            expected_bytes=TLM_BYTES,
            expected_sha256=TLM_SHA256,
        )
        selections = sorted((root / "mods").glob("touhoulittlemaid*.jar"), key=lambda item: item.name.casefold())
        if selections != [expected_path]:
            raise GateError(f"{side} TLM selection drifted: {[item.name for item in selections]}")
        installed.append({"kind": "jar", "side": side, "role": "tlm_unchanged", "artifact": actual})
    if before.get("maid_js") != after.get("maid_js"):
        raise GateError("server maid.js identity changed across content repair")
    maid_actual = validate_reported_artifact(
        after.get("maid_js"),
        runtime.joinpath(*PurePosixPath(MAID_JS_RELATIVE).parts),
        "unchanged server maid.js",
        expected_bytes=MAID_JS_BYTES,
        expected_sha256=MAID_JS_SHA256,
    )
    installed.append({"kind": "script", "side": "server", "role": "maid_js_unchanged", "artifact": maid_actual})
    tlm_manifest = require_mapping(after.get("tlm_manifest"), "content-repair TLM manifest")
    if normalized_sha256(tlm_manifest.get("sha256"), "content-repair TLM manifest SHA-256") != TLM_MANIFEST_SHA256:
        raise GateError("content-repair TLM manifest identity drifted")
    overlay_sources = after.get("tlm_overlay_sources")
    client_overlay = after.get("client_overlay")
    before_overlay = before.get("client_overlay")
    if not isinstance(overlay_sources, list) or not isinstance(client_overlay, list) or not isinstance(before_overlay, list):
        raise GateError("content-repair overlay lists are invalid")
    source_by_relative = {
        row.get("relative"): row
        for row in (require_mapping(item, "TLM overlay source") for item in overlay_sources)
    }
    after_by_relative = {
        row.get("relative"): row
        for row in (require_mapping(item, "installed TLM overlay") for item in client_overlay)
    }
    before_by_relative = {
        row.get("relative"): row
        for row in (require_mapping(item, "before TLM overlay") for item in before_overlay)
    }
    expected_relatives = set(TLM_OVERLAY_ARTIFACTS)
    if set(source_by_relative) != expected_relatives or set(after_by_relative) != expected_relatives or set(before_by_relative) != expected_relatives:
        raise GateError("content-repair TLM overlay target set drifted")
    for relative, expected in TLM_OVERLAY_ARTIFACTS.items():
        source = source_by_relative[relative]
        if source.get("bytes") != expected["bytes"] or normalized_sha256(source.get("sha256"), relative) != expected["sha256"]:
            raise GateError(f"TLM overlay source identity drifted: {relative}")
        if before_by_relative[relative] != {"relative": relative, "state": "absent"}:
            raise GateError(f"TLM overlay was not absent before apply: {relative}")
        installed_row = after_by_relative[relative]
        if installed_row.get("state") != "patched":
            raise GateError(f"TLM overlay installed state drifted: {relative}")
        _, client_target = safe_report_target(client, relative, "overlay", "TLM client overlay")
        actual = validate_reported_artifact(
            installed_row.get("artifact"),
            client_target,
            f"installed TLM client overlay {relative}",
            expected_bytes=expected["bytes"],
            expected_sha256=expected["sha256"],
        )
        _, server_target = safe_report_target(runtime, relative, "overlay", "TLM server overlay absence")
        if server_target.exists():
            raise GateError(f"CLIENT-only TLM overlay leaked onto server: {server_target}")
        installed.append({"kind": "overlay", "side": "client", "role": "tlm_patchouli_balance", "artifact": actual})
    if before.get("mcmodsync_active") is not False or after.get("mcmodsync_active") is not False:
        raise GateError("content-repair report does not keep MCModSync disabled")
    mcmodsync_audit = {
        "server": audit_mcmodsync_globally_absent(runtime, "server"),
        "client": audit_mcmodsync_globally_absent(client, "client"),
    }
    return {
        "status": "PASS_LOCKED_AND_REHASHED",
        "report": locked_report,
        "runtime": str(runtime),
        "client": str(client),
        "policy": expected_policy,
        "installed_target_count": len(installed),
        "installed_targets": installed,
        "mcmodsync": mcmodsync_audit,
    }


def validate_followup_repair_report(
    report_path: Path,
    expected_report_sha256: str,
    runtime: Path,
    client: Path,
) -> dict[str, Any]:
    payload, locked_report = load_locked_json(
        report_path,
        expected_report_sha256,
        FOLLOWUP_REPAIR_REPORT_SHA256,
        "Attempt11 follow-up postverify report",
    )
    if (
        payload.get("schema") != "mechanomania-attempt11-followup-transaction/v1"
        or payload.get("status") != "PASS"
        or payload.get("mode") != "postverify"
        or payload.get("java_started") is not False
    ):
        raise GateError("Attempt11 follow-up report schema/status/mode drifted")
    targets = require_mapping(payload.get("targets"), "Attempt11 follow-up targets")
    if Path(targets.get("server", "")).resolve() != runtime or Path(
        targets.get("client", "")
    ).resolve() != client:
        raise GateError("Attempt11 follow-up report target roots do not match this gate")
    expected_mutations = [
        f"server/mods/{FOLLOWUP_DNT_NAME}",
        f"client/mods/{FOLLOWUP_DNT_NAME}",
        f"server/mods/{FOLLOWUP_TRACKS_NAME}",
        f"client/mods/{FOLLOWUP_TRACKS_NAME}",
        f"server/{FOLLOWUP_RING_RELATIVE.as_posix()} (delete exact file)",
    ]
    if payload.get("allowed_mutations") != expected_mutations:
        raise GateError("Attempt11 follow-up mutation allowlist drifted")
    if payload.get("protected_paths") != [
        "server/world/**",
        "server/config/**",
        "client/config/**",
        "server/kubejs/server_scripts/maid.js",
    ]:
        raise GateError("Attempt11 follow-up protected-path contract drifted")
    detail = require_mapping(payload.get("detail"), "Attempt11 follow-up detail")
    apply_report = require_mapping(detail.get("apply_report"), "Attempt11 follow-up apply report")
    expected_apply_path = ALLOWED / "attempt11-followup-fixes-apply-20260814.json"
    if (
        Path(apply_report.get("path", "")).resolve() != expected_apply_path
        or apply_report.get("status") != "PASS"
        or normalized_sha256(
            apply_report.get("sha256"), "Attempt11 follow-up apply report SHA-256"
        )
        != FOLLOWUP_APPLY_REPORT_SHA256
    ):
        raise GateError("Attempt11 follow-up apply-report binding drifted")
    actual_apply_report = artifact(expected_apply_path)
    if actual_apply_report["sha256"] != FOLLOWUP_APPLY_REPORT_SHA256:
        raise GateError(f"Attempt11 follow-up apply report file drifted: {actual_apply_report}")
    if detail.get("protected_unchanged") is not True:
        raise GateError("Attempt11 follow-up did not preserve protected paths")
    if detail.get("mod_counts") != {"client": 247, "server": 236}:
        raise GateError("Attempt11 follow-up mod counts drifted")
    if detail.get("mcmodsync_active_hits") != {"client": [], "server": []}:
        raise GateError("Attempt11 follow-up did not keep MCModSync globally disabled")
    if detail.get("ring_after") != {"client": "ABSENT", "server": "ABSENT"}:
        raise GateError("Attempt11 follow-up debug-loot deletion state drifted")
    for side, root in (("server", runtime), ("client", client)):
        if (root / FOLLOWUP_RING_RELATIVE).exists():
            raise GateError(f"debug loot table remains installed on {side}")

    installed_after = require_mapping(
        detail.get("installed_after"), "Attempt11 follow-up installed artifacts"
    )
    dnt_semantics = {
        "empty_function_objects": 0,
        "entry_count": 197,
        "loot_and_item_modifier_json_parsed": 19,
        "target_entries": [
            "data/minecraft/loot_table/chests/illager_mansion/library_chest.json",
            "data/minecraft/loot_table/chests/illager_mansion/secret_room.json",
        ],
        "zip_crc": "PASS",
    }
    tracks_semantics = {
        "corrected_tags": {
            "data/create/tags/block/safe_nbt.json": ["tracks:track_mount"],
            "data/minecraft/tags/block/mineable/pickaxe.json": ["tracks:track_mount"],
        },
        "entry_count": 184,
        "zip_crc": "PASS",
    }
    installed: list[dict[str, Any]] = []
    for side, root in (("server", runtime), ("client", client)):
        for role, name, size, digest, semantics in (
            (
                "dnt",
                FOLLOWUP_DNT_NAME,
                FOLLOWUP_DNT_BYTES,
                FOLLOWUP_DNT_SHA256,
                dnt_semantics,
            ),
            (
                "tracks",
                FOLLOWUP_TRACKS_NAME,
                FOLLOWUP_TRACKS_BYTES,
                FOLLOWUP_TRACKS_SHA256,
                tracks_semantics,
            ),
        ):
            reported = require_mapping(
                installed_after.get(f"{side}_{role}"),
                f"Attempt11 follow-up {side} {role}",
            )
            if reported.get("semantics") != semantics:
                raise GateError(f"Attempt11 follow-up {side} {role} semantics drifted")
            actual = validate_reported_artifact(
                {key: reported.get(key) for key in ("path", "bytes", "sha256")},
                root / "mods" / name,
                f"Attempt11 follow-up {side} {role}",
                expected_bytes=size,
                expected_sha256=digest,
            )
            installed.append({"side": side, "role": role, "artifact": actual})

    iron = require_mapping(detail.get("irons_spellbooks"), "Attempt11 follow-up Iron's Spells")
    for side, root in (("server", runtime), ("client", client)):
        row = require_mapping(iron.get(side), f"Attempt11 follow-up Iron's Spells {side}")
        if row.get("debug_ring_entry") != "ABSENT":
            raise GateError(f"Iron's Spells debug entry was not removed on {side}")
        actual = validate_reported_artifact(
            {key: row.get(key) for key in ("path", "bytes", "sha256")},
            root / "mods" / FOLLOWUP_IRON_NAME,
            f"Attempt11 follow-up Iron's Spells {side}",
            expected_bytes=FOLLOWUP_IRON_BYTES,
            expected_sha256=FOLLOWUP_IRON_SHA256,
        )
        installed.append({"side": side, "role": "irons_spellbooks", "artifact": actual})

    protected = require_mapping(detail.get("protected"), "Attempt11 follow-up protected state")
    if protected.get("client_maid_js") != "ABSENT":
        raise GateError("Attempt11 follow-up unexpectedly installed client maid.js")
    maid = require_mapping(protected.get("server_maid_js"), "Attempt11 follow-up server maid.js")
    validate_reported_artifact(
        maid,
        runtime.joinpath(*PurePosixPath(MAID_JS_RELATIVE).parts),
        "Attempt11 follow-up unchanged server maid.js",
        expected_bytes=MAID_JS_BYTES,
        expected_sha256=MAID_JS_SHA256,
    )
    return {
        "status": "PASS_LOCKED_AND_REHASHED",
        "report": locked_report,
        "apply_report": actual_apply_report,
        "runtime": str(runtime),
        "client": str(client),
        "installed_target_count": len(installed),
        "installed_targets": installed,
        "debug_loot_absent": True,
        "mcmodsync_globally_disabled": True,
    }


def active_jars(root: Path) -> list[Path]:
    mods = root / "mods"
    if not mods.is_dir() or mods.is_symlink():
        raise GateError(f"unsafe or missing mods directory: {mods}")
    jars = sorted(mods.glob("*.jar"), key=lambda item: item.name.casefold())
    if not jars:
        raise GateError(f"empty mods directory: {mods}")
    return jars


def validate_cei_contract(name: str, expected_sha256: str, expected_bytes: int) -> tuple[str, str, int]:
    if Path(name).name != name or not name.lower().endswith(".jar") or not CEI_RE.search(name):
        raise GateError(f"invalid CEI compatibility JAR name: {name!r}")
    normalized_sha256 = expected_sha256.upper()
    if not re.fullmatch(r"[0-9A-F]{64}", normalized_sha256):
        raise GateError("CEI compatibility SHA-256 must contain exactly 64 hexadecimal characters")
    if expected_bytes <= 0:
        raise GateError("CEI compatibility byte count must be positive")
    return name, normalized_sha256, expected_bytes


def validate_side(
    root: Path,
    side: str,
    cei_name: str,
    cei_sha256: str,
    cei_bytes: int,
) -> dict[str, Any]:
    cei_name, cei_sha256, cei_bytes = validate_cei_contract(cei_name, cei_sha256, cei_bytes)
    jars = active_jars(root)
    mineastr = [item for item in jars if "mineastr" in item.name.casefold()]
    yacl = [item for item in jars if "yet_another_config_lib_v3" in item.name.casefold()]
    content_backport = [item for item in jars if CONTENT_BACKPORT_RE.fullmatch(item.name)]
    hotbath = [item for item in jars if HOTBATH_RE.search(item.name)]
    worldedit = [item for item in jars if WORLD_EDIT_RE.search(item.name)]
    cei = [item for item in jars if CEI_RE.search(item.name)]
    mcmodsync = [item.name for item in jars if MC_MODSYNC_RE.search(item.name)]
    if len(mineastr) != 1 or mineastr[0].name != MINEASTR_NAME:
        raise GateError(f"{side} MineAstr selection is not exactly {MINEASTR_NAME}: {[p.name for p in mineastr]}")
    mine = artifact(mineastr[0])
    if mine["bytes"] != MINEASTR_BYTES or mine["sha256"] != MINEASTR_SHA256:
        raise GateError(f"{side} MineAstr 0.6.26 hash/size mismatch: {mine}")
    if len(yacl) != 1 or yacl[0].name != YACL_NAME:
        raise GateError(f"{side} YACL selection is not exactly {YACL_NAME}: {[p.name for p in yacl]}")
    yacl_artifact = artifact(yacl[0])
    if yacl_artifact["bytes"] != YACL_BYTES or yacl_artifact["sha256"] != YACL_SHA256:
        raise GateError(f"{side} YACL hash/size mismatch: {yacl_artifact}")
    if len(content_backport) != 1 or content_backport[0].name != CONTENT_BACKPORT_NAME:
        raise GateError(
            f"{side} Content Backport selection is not exactly {CONTENT_BACKPORT_NAME}: "
            f"{[p.name for p in content_backport]}"
        )
    content_backport_artifact = artifact(content_backport[0])
    if (
        content_backport_artifact["bytes"] != CONTENT_BACKPORT_BYTES
        or content_backport_artifact["sha256"] != CONTENT_BACKPORT_SHA256
    ):
        raise GateError(f"{side} Content Backport hash/size mismatch: {content_backport_artifact}")
    if len(hotbath) != 1 or hotbath[0].name != HOTBATH_NAME:
        raise GateError(
            f"{side} Hot Bath selection is not exactly {HOTBATH_NAME}: "
            f"{[item.name for item in hotbath]}"
        )
    hotbath_artifact = artifact(hotbath[0])
    if hotbath_artifact["bytes"] != HOTBATH_BYTES or hotbath_artifact["sha256"] != HOTBATH_SHA256:
        raise GateError(f"{side} Hot Bath registry fix hash/size mismatch: {hotbath_artifact}")
    if len(worldedit) != 1 or worldedit[0].name != WORLD_EDIT_NAME:
        raise GateError(
            f"{side} WorldEdit direction-property fix selection is not exactly {WORLD_EDIT_NAME}: "
            f"{[item.name for item in worldedit]}"
        )
    worldedit_artifact = artifact(worldedit[0])
    if worldedit_artifact["bytes"] != WORLD_EDIT_BYTES or worldedit_artifact["sha256"] != WORLD_EDIT_SHA256:
        raise GateError(f"{side} WorldEdit direction-property fix hash/size mismatch: {worldedit_artifact}")
    if len(cei) != 1 or cei[0].name != cei_name:
        raise GateError(
            f"{side} CEI selection is not exactly {cei_name}: {[item.name for item in cei]}"
        )
    cei_artifact = artifact(cei[0])
    if cei_artifact["bytes"] != cei_bytes or cei_artifact["sha256"] != cei_sha256:
        raise GateError(f"{side} CEI compatibility JAR hash/size mismatch: {cei_artifact}")
    if mcmodsync:
        raise GateError(f"MCModSync must remain disabled in active {side} mods: {mcmodsync}")
    for forbidden in (root / "MCModSync-Config.jar", root / "modsync.properties"):
        if forbidden.exists():
            raise GateError(f"MCModSync active root configuration must be absent: {forbidden}")
    return {
        "root": str(root.resolve()),
        "active_jar_count": len(jars),
        "mineastr": mine,
        "yacl": yacl_artifact,
        "content_backport": content_backport_artifact,
        "hotbath_registry_fix": hotbath_artifact,
        "worldedit_direction_property_fix": worldedit_artifact,
        "cei_compatibility": cei_artifact,
        "mcmodsync_active": False,
    }


def read_properties(path: Path) -> dict[str, str]:
    return legacy.read_properties(path)


def configure_disposable_properties(path: Path) -> dict[str, Any]:
    before = artifact(path)
    updates = {
        "server-ip": "127.0.0.1",
        "server-port": "12341",
        "enable-rcon": "true",
        "rcon.port": "12342",
        "online-mode": "false",
        "white-list": "false",
        "enforce-whitelist": "false",
        "require-resource-pack": "false",
        "enable-query": "false",
        "level-name": "world",
    }
    seen: set[str] = set()
    output: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if "=" not in stripped or stripped.startswith("#"):
            output.append(raw)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key not in updates:
            output.append(raw)
        elif key not in seen:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    temporary = path.with_name(path.name + ".mechanomania-startup.tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    props = read_properties(path)
    legacy.validate_server_properties(props, 12341, 12342)
    return {"before": before, "after": artifact(path), "updates": updates}


def claim_attempt(runtime: Path) -> dict[str, Any]:
    marker = runtime / ATTEMPT_MARKER
    value = {
        "schema": 1,
        "status": "RUNTIME_ATTEMPT_CLAIMED",
        "runtime": str(runtime.resolve()),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reuse_allowed": False,
    }
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise GateError("runtime already has a startup-gate attempt marker") from exc
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return artifact(marker)


def command_plan() -> list[dict[str, Any]]:
    sites = [*legacy.RISK_SITES, EXTRA_RISK_SITE, *CEI_FORGER_RISK_SITES]
    commands: list[dict[str, Any]] = []
    for site in sites:
        commands.append(
            {"kind": "forceload", "site": site["name"], "command": f"forceload add {site['x']} {site['z']}"}
        )
    for site in sites:
        commands.append(
            {
                "kind": "teleport",
                "site": site["name"],
                "command": f"tp {legacy.SYNTHETIC_USERNAME} {site['x']} {site['y']} {site['z']}",
            }
        )
    commands.append({"kind": "save", "site": None, "command": "save-all flush"})
    return commands


def audit_server_errors(
    text: str,
    phase: str,
    *,
    allow_controlled_disconnect: bool = False,
) -> dict[str, Any]:
    """Reject every server ERROR except the exact, bounded diagnostics audited for this release."""
    try:
        legacy.assert_no_strict_markers(text, phase)
    except legacy.GateError as exc:
        raise GateError(str(exc)) from exc

    lines = text.splitlines()
    dist_counts: Counter[str] = Counter()
    refmap_count = 0
    controlled_disconnect_count = 0
    allowed_rows: list[str] = []
    rejected: list[str] = []
    for index, line in enumerate(lines):
        if "/ERROR]" not in line:
            continue
        match = ERROR_LINE_RE.match(line)
        if match is None:
            rejected.append(f"unparsed ERROR line: {line}")
            continue
        logger, message = match.groups()
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if logger == RUNTIME_DIST_CLEANER_LOGGER and message in RUNTIME_DIST_CLEANER_MAX_COUNTS:
            dist_counts[message] += 1
            if dist_counts[message] > RUNTIME_DIST_CLEANER_MAX_COUNTS[message]:
                rejected.append(f"RuntimeDistCleaner count exceeded audited maximum: {message}")
            else:
                allowed_rows.append(f"{logger}: {message}")
            continue
        if logger == REFMAP_LOGGER and message == REFMAP_MESSAGE:
            refmap_count += 1
            if refmap_count > 1 or next_line != REFMAP_CAUSE:
                rejected.append(f"RefmapRemapper diagnostic drift: {line} / next={next_line!r}")
            else:
                allowed_rows.append(f"{logger}: {message} / {next_line}")
            continue
        if (
            allow_controlled_disconnect
            and logger == CONNECTION_LOGGER
            and message == CONNECTION_MESSAGE
        ):
            controlled_disconnect_count += 1
            if controlled_disconnect_count > 1 or next_line != CONNECTION_CAUSE:
                rejected.append(f"controlled disconnect diagnostic drift: {line} / next={next_line!r}")
            else:
                allowed_rows.append(f"{logger}: {message} / {next_line}")
            continue
        rejected.append(f"{logger}: {message}")

    if rejected:
        sample = " | ".join(rejected[:5])
        raise GateError(f"{phase}: unreviewed server ERROR diagnostics ({len(rejected)}): {sample}")
    normalized = "\n".join(sorted(allowed_rows)).encode("utf-8")
    return {
        "phase": phase,
        "error_line_count": len(allowed_rows),
        "runtime_dist_cleaner": dict(sorted(dist_counts.items())),
        "refmap_nonexistent_probe": refmap_count,
        "controlled_disconnect": controlled_disconnect_count,
        "allowed_multiset_sha256": hashlib.sha256(normalized).hexdigest().upper(),
        "unreviewed_error_count": 0,
    }


def assert_server_clean_before_client(text: str) -> dict[str, Any]:
    """Fail before allocating the 4 GiB client when the ready server is already unsafe."""
    return audit_server_errors(text, "Mechanomania server pre-client")


def run(args: argparse.Namespace) -> dict[str, Any]:
    runtime = args.runtime.resolve()
    client = args.client.resolve()
    report_path = args.report.resolve()
    artifact_dir = args.artifacts.resolve()
    data_repair_report = args.data_repair_report.resolve()
    content_repair_report = args.content_repair_report.resolve()
    followup_repair_report = args.followup_repair_report.resolve()
    for path, label in (
        (runtime, "runtime"),
        (client, "client"),
        (report_path, "report"),
        (artifact_dir, "artifacts"),
        (data_repair_report, "data repair report"),
        (content_repair_report, "content repair report"),
        (followup_repair_report, "follow-up repair report"),
    ):
        if not within(path, ALLOWED) or within(path, FORBIDDEN):
            raise GateError(f"{label} must stay in D: migration-audit-work: {path}")
    if report_path.exists() or artifact_dir.exists():
        raise GateError("report/artifact path must be fresh")
    if not runtime.is_dir() or runtime.is_symlink() or not client.is_dir() or client.is_symlink():
        raise GateError("runtime/client must be regular D: directories")
    ports = legacy.check_ports_closed(12341, 12342, 26341)
    if not ports["all_closed"]:
        raise GateError(f"test ports are occupied: {ports}")
    java = args.java.resolve()
    powershell = args.powershell.resolve()
    helper = args.private_helper.resolve()
    launcher = args.client_launcher.resolve()
    win_args = legacy.validate_prerequisites(
        runtime, client, java, powershell, helper, launcher, args.win_args
    )
    artifact_dir.mkdir(parents=True)
    report: dict[str, Any] = {
        "schema": 1,
        "status": "NO_GO",
        "category": "mechanomania_mineastr_0626_startup_join_gate",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runtime": str(runtime),
        "client": str(client),
        "ports": {"server": 12341, "rcon": 12342, "voice": 26341},
        "blockers": [],
        "round": None,
        "cleanup": {},
    }
    server = None
    private_client = None
    try:
        report["base_data_resource_repairs"] = validate_data_resource_repair_report(
            data_repair_report,
            args.data_repair_report_sha256,
            runtime,
            client,
            superseded_relatives=FOLLOWUP_SUPERSEDED_RELATIVES,
        )
        report["content_repairs"] = validate_content_repair_report(
            content_repair_report,
            args.content_repair_report_sha256,
            runtime,
            client,
        )
        report["attempt11_followup_repairs"] = validate_followup_repair_report(
            followup_repair_report,
            args.followup_repair_report_sha256,
            runtime,
            client,
        )
        report["server_mods"] = validate_side(
            runtime, "server", args.cei_name, args.cei_sha256, args.cei_bytes
        )
        report["client_mods"] = validate_side(
            client, "client", args.cei_name, args.cei_sha256, args.cei_bytes
        )
        report["attempt_marker"] = claim_attempt(runtime)
        report["server_properties"] = configure_disposable_properties(runtime / "server.properties")
        props = read_properties(runtime / "server.properties")
        report["resource_pack_rejection"] = legacy.configure_disposable_resource_pack_rejection(
            client, 12341, props, runtime / "server.properties"
        )
        cache = runtime / "immersive_paintings_cache"
        cache_files = sorted(item for item in cache.rglob("*") if item.is_file()) if cache.is_dir() else []
        if len(cache_files) != 174 or sum(item.stat().st_size for item in cache_files) != 33_150_491:
            raise GateError("immersive_paintings_cache is incomplete")
        report["immersive_paintings_cache"] = {"files": 174, "bytes": 33_150_491}
        server = legacy.ServerSession(
            runtime, artifact_dir, 1, java, args.win_args, 12342,
            props["rcon.password"], args.server_memory_mb,
        )
        server.wait_ready(args.startup_timeout_seconds, args.bootstrap_timeout_seconds)
        before = server.current_log()
        report["server_error_audit_pre_client"] = assert_server_clean_before_client(before)
        joined_before = legacy.joined_count(before)
        lost_before = legacy.lost_count(before)
        private_client = legacy.PrivateClientSession(
            client, artifact_dir, 1, 12341, powershell, helper, launcher, java,
            args.client_memory_mb, args.client_launch_timeout_seconds,
            args.client_session_timeout_seconds,
        )

        def health() -> None:
            server.assert_alive()
            private_client.assert_running()

        legacy.wait_until(
            lambda: legacy.joined_count(server.current_log()) == joined_before + 1,
            args.join_timeout_seconds,
            "Mechanomania client join",
            health=health,
        )
        if legacy.lost_count(server.current_log()) != lost_before:
            raise GateError("client disconnected before risk-site validation")
        commands: list[dict[str, Any]] = []
        final_tp: float | None = None
        import time
        for planned in command_plan():
            if planned["kind"] == "save" and final_tp is not None:
                remaining = args.settle_seconds - (time.monotonic() - final_tp)
                if remaining > 0:
                    legacy.wait_settle(remaining, health)
            started = time.monotonic()
            response = server.command(planned["command"])
            commands.append({**planned, "response": response, "elapsed_seconds": round(time.monotonic() - started, 3)})
            if planned["kind"] == "teleport":
                final_tp = time.monotonic()
                legacy.wait_settle(args.teleport_pause_seconds, health)
        health()
        report["server_error_audit_pre_stop"] = audit_server_errors(
            server.current_log(), "Mechanomania server before controlled client stop"
        )
        startup_timing = dict(server.startup_timing)
        client_state = private_client.stop()
        private_client = None
        stop_response = server.stop()
        server = None
        client_log = client / "logs" / "latest.log"
        client_text = legacy.read_text(client_log)
        legacy.assert_no_strict_markers(client_text, "Mechanomania client latest.log", client=True)
        report["server_error_audit_final"] = audit_server_errors(
            legacy.read_text(runtime / "logs" / "latest.log"),
            "Mechanomania server final log",
            allow_controlled_disconnect=True,
        )
        report["round"] = {
            "status": "PASS",
            "startup": startup_timing,
            "join": {"new_join_lines": legacy.joined_count(legacy.read_text(runtime / "logs" / "latest.log")) - joined_before},
            "commands": commands,
            "client_state": {
                "status": client_state.get("status"),
                "exit_code": client_state.get("exit_code"),
                "private_desktop": client_state.get("private_desktop"),
                "processes_closed": client_state.get("processes_closed"),
            },
            "server_stop_response": stop_response,
            "client_latest_log": artifact(client_log),
        }
        report["status"] = "PASS"
    except Exception as exc:
        report["blockers"].append({"type": type(exc).__name__, "message": str(exc)})
        legacy.collect_failure_artifacts(runtime, artifact_dir)
    finally:
        if private_client is not None:
            private_client.abort()
        if server is not None:
            server.abort()
        try:
            cleanup = legacy.wait_ports_closed(12341, 12342, 26341, timeout=60)
        except Exception as exc:
            cleanup = legacy.check_ports_closed(12341, 12342, 26341)
            report["blockers"].append({"type": "PORT_CLEANUP", "message": str(exc)})
        report["cleanup"] = cleanup
        if report["blockers"] or not cleanup["all_closed"]:
            report["status"] = "NO_GO"
        report["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        report["artifacts"] = str(artifact_dir)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temp = report_path.with_name(report_path.name + ".tmp")
        temp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temp, report_path)
    return report


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--runtime", type=Path, required=True)
    value.add_argument("--client", type=Path, required=True)
    value.add_argument("--report", type=Path, required=True)
    value.add_argument("--artifacts", type=Path, required=True)
    value.add_argument("--data-repair-report", type=Path, required=True)
    value.add_argument("--data-repair-report-sha256", required=True)
    value.add_argument("--content-repair-report", type=Path, required=True)
    value.add_argument("--content-repair-report-sha256", required=True)
    value.add_argument("--followup-repair-report", type=Path, required=True)
    value.add_argument("--followup-repair-report-sha256", required=True)
    value.add_argument("--cei-name", required=True)
    value.add_argument("--cei-sha256", required=True)
    value.add_argument("--cei-bytes", type=int, required=True)
    value.add_argument("--java", type=Path, default=legacy.DEFAULT_JAVA)
    value.add_argument("--powershell", type=Path, default=legacy.DEFAULT_POWERSHELL)
    value.add_argument("--private-helper", type=Path, default=legacy.DEFAULT_PRIVATE_HELPER)
    value.add_argument("--client-launcher", type=Path, default=legacy.DEFAULT_CLIENT_LAUNCHER)
    value.add_argument("--win-args", default="@libraries/net/neoforged/neoforge/21.1.241/win_args.txt")
    value.add_argument("--server-memory-mb", type=int, default=4096)
    value.add_argument("--client-memory-mb", type=int, default=4096)
    value.add_argument("--bootstrap-timeout-seconds", type=int, default=180)
    value.add_argument("--startup-timeout-seconds", type=int, default=120)
    value.add_argument("--join-timeout-seconds", type=int, default=240)
    value.add_argument("--client-launch-timeout-seconds", type=int, default=210)
    value.add_argument("--client-session-timeout-seconds", type=int, default=420)
    value.add_argument("--teleport-pause-seconds", type=float, default=3.0)
    value.add_argument("--settle-seconds", type=float, default=20.0)
    return value


def main() -> int:
    args = parser().parse_args()
    report = run(args)
    print(json.dumps({"status": report["status"], "report": str(args.report.resolve()), "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
