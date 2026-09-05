#!/usr/bin/env python3
"""Attempt12 startup gate wrapper with the final, non-legacy repair contract.

The generic startup gate was written while Attempt11 was still using the
ordinary KubeJS Patchouli overlays.  Attempt12 intentionally supersedes those
overlays with a patched TLM JAR on *both* sides and repairs the source-world
Happy Ghast UUID collision.  This wrapper reuses the process/join smoke gate,
but replaces the stale Attempt11 content/follow-up validators and adds locked
checks for the Attempt12 core, TLM-JAR, and entity-repair transactions.

``--validate-only`` performs all filesystem/report checks and never starts
Java.  Without it, the same checks are followed by the inherited one-round
server/client startup smoke.  All large roots remain under <TRANS_ROOT>.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import zipfile
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import run_mechanomania_startup_gate as gate


ALLOWED = Path(r"<AUDIT_ROOT>").resolve()
ATTEMPT12_RUNTIME = ALLOWED / "mechanomania-matched-runtime-attempt12-20260814"
ATTEMPT12_CLIENT = ALLOWED / "mechanomania-matched-client-attempt12-20260814"
ATTEMPT12_DATA_REPORT = ALLOWED / "attempt12-data-resource-apply-20260814.json"
ATTEMPT12_CONTENT_REPORT = ALLOWED / "attempt12-content-repairs-apply-20260814.json"
ATTEMPT12_CORE_REPORT = ALLOWED / "attempt12-core-fixes-apply-20260814.json"
ATTEMPT12_FOLLOWUP_REPORT = ALLOWED / "attempt12-followup-fixes-postverify-20260814.json"
ATTEMPT12_FOLLOWUP_APPLY_REPORT = ALLOWED / "attempt12-followup-fixes-apply-20260814.json"
ATTEMPT12_TLM_REPORT = ALLOWED / "attempt12-tlm-patchouli-jar-apply-20260814.json"
ATTEMPT12_HAPPYGHAST_REPORT = ALLOWED / "attempt12-happyghast-duplicate-repair-20260814.json"

DATA_REPORT_SHA256 = "FB0810892CF022E109A04B0B8FF0346A0038B0E4E2790BAAB000D0784A7EFEA8"
CONTENT_REPORT_SHA256 = "3DCF05D06B85A21D47B4FA9F4B111E197FD507463F323C07B7963A623E5A5FFF"
CORE_REPORT_SHA256 = "C69F3D23EB2C0869CB9CA5B9AF08B4766A6EAF6CACDC39E527F53B26B0945104"
FOLLOWUP_REPORT_SHA256 = "DB0305E4C1D61BD48CA0373DFED9FB6A7A3B06D23CDDD3EDF57C05B89542051F"
FOLLOWUP_APPLY_REPORT_SHA256 = "F6C85A7846D0D250BAE79CD6487F57D512128F102D387E539BD3F0366B698BD7"
TLM_REPORT_SHA256 = "255D7FF67BB8C191B034FAC0964F476F3880815BE19F38930B1D2F099022D4BE"
HAPPYGHAST_REPORT_SHA256 = "70A3F860AE72E0FF065B0A37FA779DB5EF90117EECEC9350F176D89CEFAD9F43"

TLM_NAME = "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
TLM_ORIGINAL_SHA256 = "F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27"
TLM_ORIGINAL_BYTES = 24_408_776
TLM_PATCHED_SHA256 = "32BE64DD058B7A91F90107972D104BDC0946D858E690D4C72032F64873F9B15B"
TLM_PATCHED_BYTES = 24_411_246
YUUSHYA_PATCHED_NAME = "yuushya-1.21.0-neoforge-2.3.0-patchouli-safe.1.jar"
YUUSHYA_PATCHED_SHA256 = "31DFFD39D1FED94F2088405AF3B8DC862E363BA389015780355571ECCA4A813D"
YUUSHYA_PATCHED_BYTES = 28_197_402
MAID_JS_RELATIVE = Path("kubejs/server_scripts/maid.js")
MAID_JS_SHA256 = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
MAID_JS_BYTES = 119
RECIPE_ID = "touhou_little_maid:altar_recipe/spawn_box"
TLM_RECIPE_ENTRY = "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json"
TLM_ADVANCEMENT_ENTRY = "data/touhou_little_maid/advancement/base/spawn_maid.json"
TLM_PATCHED_ENTRY_NAMES = (
    "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/maid/spawn_maid.json",
    "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/overview/multiblocks_altar.json",
)
TLM_OVERLAY_RELATIVES = (
    "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/maid/spawn_maid.json",
    "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
    "en_us/entries/overview/multiblocks_altar.json",
)
RING_RELATIVE = Path("kubejs/data/irons_spellbooks/loot_table/test/ring_gen_break_me.json")
HAPPY_REGION_RELATIVE = Path("world/entities/r.-1.-1.mca")

_REPORT_CONTEXT: dict[str, Path] = {
    "core": ATTEMPT12_CORE_REPORT,
    "tlm": ATTEMPT12_TLM_REPORT,
    "happyghast": ATTEMPT12_HAPPYGHAST_REPORT,
}


def _fail(message: str) -> None:
    raise gate.GateError(message)


def _locked(path: Path, supplied_sha: str, expected_sha: str, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return gate.load_locked_json(path, supplied_sha, expected_sha, label)


def _require_roots(payload: dict[str, Any], runtime: Path, client: Path, label: str) -> None:
    targets = payload.get("targets")
    if not isinstance(targets, dict):
        _fail(f"{label} targets must be an object")
    if Path(str(targets.get("server", ""))).resolve() != runtime or Path(str(targets.get("client", ""))).resolve() != client:
        _fail(f"{label} target roots do not match this gate")


def _check_current_artifact(path: Path, expected_sha: str, expected_bytes: int, label: str) -> dict[str, Any]:
    actual = gate.artifact(path)
    if actual["sha256"] != expected_sha or actual["bytes"] != expected_bytes:
        _fail(f"{label} hash/size mismatch: {actual}")
    return actual


def _check_no_mcmodsync(root: Path, side: str) -> dict[str, Any]:
    return gate.audit_mcmodsync_globally_absent(root, side)


def _validate_core_report(runtime: Path, client: Path) -> dict[str, Any]:
    path = _REPORT_CONTEXT["core"]
    digest = gate.sha256(path)
    payload, locked = _locked(path, digest, digest, "current-attempt core-fixes apply report")
    if payload.get("schema") != 1 or payload.get("status") != "PASS_APPLIED":
        _fail("Attempt12 core-fixes report schema/status mismatch")
    _require_roots(payload, runtime, client, "Attempt12 core-fixes")
    policy = payload.get("policy")
    if not isinstance(policy, dict) or policy.get("java_started") is not False or policy.get("minecraft_started") is not False:
        _fail("Attempt12 core-fixes report permits a Java/Minecraft mutation")
    if policy.get("mcmodsync_globally_disabled") is not True or policy.get("world_modified") is not False:
        _fail("Attempt12 core-fixes MCModSync/world policy drifted")
    installed = payload.get("installed")
    if not isinstance(installed, dict) or installed.get("status") != "PASS_INSTALLED":
        _fail("Attempt12 core-fixes installed state is not PASS_INSTALLED")
    if installed.get("counts") != {"server_jars": 236, "client_jars": 247}:
        _fail(f"Attempt12 core-fixes mod counts drifted: {installed.get('counts')!r}")
    if installed.get("mcmodsync") != {"server_hits": [], "client_hits": [], "globally_disabled": True}:
        _fail("Attempt12 core-fixes MCModSync state drifted")
    return {"status": "PASS_LOCKED_AND_REHASHED", "report": locked, "policy": policy, "installed": installed}


def _validate_tlm_transaction(runtime: Path, client: Path) -> dict[str, Any]:
    path = _REPORT_CONTEXT["tlm"]
    digest = gate.sha256(path)
    payload, locked = _locked(path, digest, digest, "current-attempt TLM JAR transaction report")
    if payload.get("schema") not in {
        "attempt12-tlm-patchouli-jar-transaction/v1",
        "attempt13-tlm-patchouli-jar-transaction/v1",
    } or payload.get("status") != "PASS_APPLIED":
        _fail("current-attempt TLM transaction schema/status mismatch")
    if Path(str(payload.get("server", ""))).resolve() != runtime or Path(str(payload.get("client", ""))).resolve() != client:
        _fail("Attempt12 TLM transaction target roots do not match this gate")
    if payload.get("patched_jar_sha256") != TLM_PATCHED_SHA256 or payload.get("maid_js_sha256") != MAID_JS_SHA256:
        _fail("Attempt12 TLM transaction locked hashes drifted")
    if payload.get("world_changes") != 0 or payload.get("config_changes") != 0 or payload.get("mcmodsync_active") is not False:
        _fail("Attempt12 TLM transaction scope/policy drifted")
    rows = payload.get("jar_rows")
    if not isinstance(rows, list) or len(rows) != 2 or {row.get("side") for row in rows if isinstance(row, dict)} != {"server", "client"}:
        _fail("Attempt12 TLM transaction must contain exactly one server and one client row")
    for side, root in (("server", runtime), ("client", client)):
        expected = root / "mods" / TLM_NAME
        _check_current_artifact(expected, TLM_PATCHED_SHA256, TLM_PATCHED_BYTES, f"patched TLM {side}")
        selected = sorted((root / "mods").glob("touhoulittlemaid*.jar"), key=lambda p: p.name.casefold())
        if selected != [expected]:
            _fail(f"{side} TLM selection is not exactly the patched JAR: {[p.name for p in selected]}")
        for relative in TLM_OVERLAY_RELATIVES:
            overlay = root / Path(relative)
            if overlay.exists():
                _fail(f"superseded TLM loose overlay remains on {side}: {overlay}")
    # Validate the resource-level invariant, not just the outer JAR hash.
    jar_checks: list[dict[str, Any]] = []
    for side, root in (("server", runtime), ("client", client)):
        jar = root / "mods" / TLM_NAME
        try:
            with zipfile.ZipFile(jar, "r") as archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    _fail(f"patched TLM {side} JAR contains duplicate ZIP entries")
                for required in (TLM_RECIPE_ENTRY, TLM_ADVANCEMENT_ENTRY, *TLM_PATCHED_ENTRY_NAMES):
                    if required not in names:
                        _fail(f"patched TLM {side} JAR is missing {required}")
                for entry in TLM_PATCHED_ENTRY_NAMES:
                    raw = archive.read(entry)
                    if RECIPE_ID.encode("utf-8") in raw:
                        _fail(f"stale Patchouli spawn_box page survives in {side}: {entry}")
                if not archive.read(TLM_RECIPE_ENTRY) or not archive.read(TLM_ADVANCEMENT_ENTRY):
                    _fail(f"patched TLM {side} recipe/advancement resource is empty")
        except (OSError, zipfile.BadZipFile) as exc:
            _fail(f"cannot inspect patched TLM {side} JAR: {exc}")
        jar_checks.append({"side": side, "artifact": gate.artifact(jar), "duplicate_entries": False})
    return {
        "status": "PASS_LOCKED_AND_REHASHED",
        "report": locked,
        "patched_jar_sha256": TLM_PATCHED_SHA256,
        "loose_overlays": "ABSENT_BOTH_SIDES",
        "recipe_resource_preserved": True,
        "advancement_resource_preserved": True,
        "jar_checks": jar_checks,
    }


def _validate_happyghast_transaction(runtime: Path) -> dict[str, Any]:
    path = _REPORT_CONTEXT["happyghast"]
    digest = gate.sha256(path)
    payload, locked = _locked(path, digest, digest, "current-attempt Happy Ghast UUID repair report")
    if payload.get("schema") != "attempt12-duplicate-entity-uuid-repair/v1" or payload.get("status") != "PASS_APPLIED":
        _fail("Attempt12 Happy Ghast repair schema/status mismatch")
    expected_world = runtime / "world"
    if Path(str(payload.get("world", ""))).resolve() != expected_world:
        _fail("Attempt12 Happy Ghast repair world target drifted")
    expected_region = runtime / HAPPY_REGION_RELATIVE
    if Path(str(payload.get("region", ""))).resolve() != expected_region:
        _fail("Attempt12 Happy Ghast repair region target drifted")
    post = payload.get("post_scan")
    if not isinstance(post, dict) or post.get("duplicate_count") != 0 or post.get("parse_errors") != []:
        _fail("Attempt12 Happy Ghast post-scan is not duplicate-free")
    if payload.get("world_files_modified") != 1 or payload.get("unknown_uuid_policy") != "fail_closed":
        _fail("Attempt12 Happy Ghast mutation policy drifted")
    current = _check_current_artifact(expected_region, str(payload.get("output_sha256", "")), expected_region.stat().st_size, "repaired Happy Ghast entity region")
    backup = Path(str(payload.get("backup", "")))
    if not backup.is_file() or backup.is_symlink():
        _fail(f"Happy Ghast rollback backup is missing: {backup}")
    return {"status": "PASS_LOCKED_AND_REHASHED", "report": locked, "post_scan": post, "region": current, "rollback_backup": str(backup.resolve())}


def validate_content_repair_report(
    report_path: Path,
    expected_report_sha256: str,
    runtime: Path,
    client: Path,
) -> dict[str, Any]:
    payload, locked = _locked(
        report_path,
        expected_report_sha256,
        str(gate.CONTENT_REPAIR_REPORT_SHA256),
        "current-attempt content-repair apply report",
    )
    if payload.get("schema") != 1 or payload.get("status") != "PASS_APPLIED":
        _fail("Attempt12 content-repair report schema/status mismatch")
    expected_policy = {
        "spawn_box_recipe_removed": True,
        "maid_js_unchanged": True,
        "tlm_patch_side": "CLIENT",
        "yuushya_patch_side": "BOTH",
        "mcmodsync_globally_disabled": True,
    }
    if payload.get("policy") != expected_policy or payload.get("expected_yuushya_state") != "patched":
        _fail("Attempt12 content-repair policy drifted")
    after = payload.get("after")
    before = payload.get("before")
    if not isinstance(after, dict) or not isinstance(before, dict):
        _fail("Attempt12 content-repair before/after state is malformed")
    for state, label in ((before, "before"), (after, "after")):
        if Path(str(state.get("server", ""))).resolve() != runtime or Path(str(state.get("client", ""))).resolve() != client:
            _fail(f"Attempt12 content-repair {label} roots do not match this gate")
    # Yuushya transaction provenance remains part of the content report.
    for side, root in (("server", runtime), ("client", client)):
        row = ((after.get("yuushya") or {}).get(side) if isinstance(after.get("yuushya"), dict) else None)
        if not isinstance(row, dict) or row.get("state") != "patched":
            _fail(f"Attempt12 Yuushya {side} report state drifted")
        artifact_row = row.get("artifact")
        gate.validate_reported_artifact(
            artifact_row,
            root / "mods" / YUUSHYA_PATCHED_NAME,
            f"Attempt12 Yuushya {side}",
            expected_bytes=YUUSHYA_PATCHED_BYTES,
            expected_sha256=YUUSHYA_PATCHED_SHA256,
        )
        selected = sorted((root / "mods").glob("yuushya*.jar"), key=lambda p: p.name.casefold())
        if selected != [root / "mods" / YUUSHYA_PATCHED_NAME]:
            _fail(f"Attempt12 Yuushya {side} selection drifted: {[p.name for p in selected]}")
    maid = runtime / MAID_JS_RELATIVE
    _check_current_artifact(maid, MAID_JS_SHA256, MAID_JS_BYTES, "Attempt12 unchanged server maid.js")
    before_maid = before.get("maid_js")
    after_maid = after.get("maid_js")
    if before_maid != after_maid:
        _fail("Attempt12 content repair changed maid.js according to report")
    if payload.get("after", {}).get("mcmodsync_active") is not False:
        _fail("Attempt12 content-repair report does not keep MCModSync disabled")
    core = _validate_core_report(runtime, client)
    tlm = _validate_tlm_transaction(runtime, client)
    happy = _validate_happyghast_transaction(runtime)
    mcmodsync = {"server": _check_no_mcmodsync(runtime, "server"), "client": _check_no_mcmodsync(client, "client")}
    return {
        "status": "PASS_LOCKED_AND_REHASHED",
        "report": locked,
        "policy": expected_policy,
        "yuushya": YUUSHYA_PATCHED_NAME,
        "maid_js": gate.artifact(maid),
        "core_repairs": core,
        "tlm_patch": tlm,
        "happyghast_repair": happy,
        "mcmodsync": mcmodsync,
    }


def validate_followup_repair_report(
    report_path: Path,
    expected_report_sha256: str,
    runtime: Path,
    client: Path,
) -> dict[str, Any]:
    payload, locked = _locked(
        report_path,
        expected_report_sha256,
        str(gate.FOLLOWUP_REPAIR_REPORT_SHA256),
        "current-attempt follow-up postverify report",
    )
    if payload.get("schema") != "mechanomania-attempt11-followup-transaction/v1" or payload.get("status") != "PASS" or payload.get("mode") != "postverify" or payload.get("java_started") is not False:
        _fail("Attempt12 follow-up report schema/status/mode drifted")
    _require_roots(payload, runtime, client, "Attempt12 follow-up")
    detail = payload.get("detail")
    if not isinstance(detail, dict) or detail.get("protected_unchanged") is not True:
        _fail("Attempt12 follow-up protected state is not unchanged")
    if detail.get("mod_counts") != {"client": 247, "server": 236}:
        _fail(f"Attempt12 follow-up mod counts drifted: {detail.get('mod_counts')!r}")
    if detail.get("mcmodsync_active_hits") != {"client": [], "server": []}:
        _fail("Attempt12 follow-up MCModSync state drifted")
    if detail.get("ring_after") != {"client": "ABSENT", "server": "ABSENT"}:
        _fail("Attempt12 follow-up debug-loot state drifted")
    apply_row = detail.get("apply_report")
    if not isinstance(apply_row, dict):
        _fail("Attempt12 follow-up apply_report binding is missing")
    apply_path = Path(str(apply_row.get("path", ""))).resolve()
    apply_digest = str(apply_row.get("sha256", "")).upper()
    if not apply_path.is_file() or len(apply_digest) != 64:
        _fail("Attempt12 follow-up apply report path/hash is invalid")
    apply_artifact = _check_current_artifact(apply_path, apply_digest, apply_path.stat().st_size, "Attempt12 follow-up apply report")
    apply_payload, _ = _locked(apply_path, apply_digest, apply_digest, "Attempt12 follow-up apply report")
    if apply_payload.get("status") != "PASS" or not apply_payload.get("targets"):
        _fail("Attempt12 follow-up apply report status/targets drifted")
    _require_roots(apply_payload, runtime, client, "Attempt12 follow-up apply")
    installed_after = detail.get("installed_after")
    if not isinstance(installed_after, dict):
        _fail("Attempt12 follow-up installed_after is malformed")
    expected = {
        "client_dnt": (client / "mods" / gate.FOLLOWUP_DNT_NAME, gate.FOLLOWUP_DNT_BYTES, gate.FOLLOWUP_DNT_SHA256),
        "server_dnt": (runtime / "mods" / gate.FOLLOWUP_DNT_NAME, gate.FOLLOWUP_DNT_BYTES, gate.FOLLOWUP_DNT_SHA256),
        "client_tracks": (client / "mods" / gate.FOLLOWUP_TRACKS_NAME, gate.FOLLOWUP_TRACKS_BYTES, gate.FOLLOWUP_TRACKS_SHA256),
        "server_tracks": (runtime / "mods" / gate.FOLLOWUP_TRACKS_NAME, gate.FOLLOWUP_TRACKS_BYTES, gate.FOLLOWUP_TRACKS_SHA256),
        "client_irons_spellbooks": (client / "mods" / gate.FOLLOWUP_IRON_NAME, gate.FOLLOWUP_IRON_BYTES, gate.FOLLOWUP_IRON_SHA256),
        "server_irons_spellbooks": (runtime / "mods" / gate.FOLLOWUP_IRON_NAME, gate.FOLLOWUP_IRON_BYTES, gate.FOLLOWUP_IRON_SHA256),
    }
    checked: list[dict[str, Any]] = []
    for key, (path, size, digest) in expected.items():
        row = installed_after.get(key)
        if not isinstance(row, dict):
            # Iron's Spells is represented under detail.irons_spellbooks.
            if key.endswith("irons_spellbooks"):
                iron = detail.get("irons_spellbooks") or {}
                row = iron.get("client" if key.startswith("client") else "server")
            if not isinstance(row, dict):
                _fail(f"Attempt12 follow-up report missing {key}")
        if key.endswith("irons_spellbooks"):
            if row.get("debug_ring_entry") != "ABSENT":
                _fail(f"Attempt12 Iron's Spells debug entry remains for {key}")
        semantics = row.get("semantics")
        if key.endswith("dnt") and semantics != {
            "empty_function_objects": 0,
            "entry_count": 197,
            "loot_and_item_modifier_json_parsed": 19,
            "target_entries": [
                "data/minecraft/loot_table/chests/illager_mansion/library_chest.json",
                "data/minecraft/loot_table/chests/illager_mansion/secret_room.json",
            ],
            "zip_crc": "PASS",
        }:
            _fail(f"Attempt12 DnT semantics drifted for {key}")
        if key.endswith("tracks") and semantics != {
            "corrected_tags": {
                "data/create/tags/block/safe_nbt.json": ["tracks:track_mount"],
                "data/minecraft/tags/block/mineable/pickaxe.json": ["tracks:track_mount"],
            },
            "entry_count": 184,
            "zip_crc": "PASS",
        }:
            _fail(f"Attempt12 Tracks semantics drifted for {key}")
        checked.append({"key": key, "artifact": _check_current_artifact(path, digest, size, key)})
    for side, root in (("server", runtime), ("client", client)):
        ring = root / RING_RELATIVE
        if ring.exists():
            _fail(f"Attempt12 debug loot table remains on {side}: {ring}")
    maid = runtime / MAID_JS_RELATIVE
    _check_current_artifact(maid, MAID_JS_SHA256, MAID_JS_BYTES, "Attempt12 follow-up maid.js")
    return {
        "status": "PASS_LOCKED_AND_REHASHED",
        "report": locked,
        "apply_report": apply_artifact,
        "installed_targets": checked,
        "debug_loot_absent": True,
        "mcmodsync_globally_disabled": True,
    }


def _configure_attempt12_locks(args: argparse.Namespace) -> None:
    # The generic data validator is structurally reusable once its old hash
    # lock is rebound.  Content/follow-up validators are replaced above.
    gate.DATA_REPAIR_REPORT_SHA256 = str(args.data_repair_report_sha256).upper()
    gate.CONTENT_REPAIR_REPORT_SHA256 = str(args.content_repair_report_sha256).upper()
    gate.FOLLOWUP_REPAIR_REPORT_SHA256 = str(args.followup_repair_report_sha256).upper()
    _REPORT_CONTEXT["core"] = Path(args.core_repair_report).resolve()
    _REPORT_CONTEXT["tlm"] = Path(args.tlm_apply_report).resolve()
    _REPORT_CONTEXT["happyghast"] = Path(args.happyghast_repair_report).resolve()


def _install_save_aware_stop() -> None:
    """Treat a slow JVM teardown as safe only after the save-complete marker.

    The common gate used to turn a clean, fully-saved server into NO_GO when a
    non-daemon auxiliary thread kept the JVM alive past its fixed 120-second
    wait.  This adapter keeps the strict behavior for every other case.  If
    the server log proves ``All dimensions are saved`` and all test ports close,
    it performs a final bounded process cleanup and records a controlled-stop
    response instead of calling the run unsafe.
    """
    original = gate.legacy.ServerSession.stop

    def stop(self):  # type: ignore[no-untyped-def]
        response = ""
        forced_after_save = False
        if self.process.poll() is None:
            try:
                response = self.command("stop")
            except (OSError, ConnectionError, TimeoutError):
                response = "RCON listener closed during controlled stop"
            deadline = time.monotonic() + 240.0
            while self.process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            if self.process.poll() is None:
                saved = "All dimensions are saved" in self.current_log()
                ports = gate.legacy.check_ports_closed(12341, 12342, 26341)
                if not saved or not ports.get("all_closed"):
                    self.process.kill()
                    self.process.wait(timeout=30)
                    self._close_streams()
                    raise gate.GateError("server did not stop within save-aware 240 seconds")
                forced_after_save = True
                self.process.kill()
                self.process.wait(timeout=30)
        self._close_streams()
        if self.process.returncode not in (0, None) and not forced_after_save:
            raise gate.GateError(f"server round {self.round_number} exited with {self.process.returncode}")
        self.stopped_cleanly = True
        if forced_after_save:
            response = (response + "; " if response else "") + "forced cleanup after save-complete marker"
        return response

    gate.legacy.ServerSession.stop = stop


def _validate_only(args: argparse.Namespace) -> dict[str, Any]:
    runtime = args.runtime.resolve()
    client = args.client.resolve()
    result: dict[str, Any] = {"schema": 1, "status": "NO_GO", "mode": "validate-only", "runtime": str(runtime), "client": str(client), "blockers": []}
    try:
        result["data"] = gate.validate_data_resource_repair_report(
            args.data_repair_report.resolve(), args.data_repair_report_sha256, runtime, client,
            superseded_relatives=gate.FOLLOWUP_SUPERSEDED_RELATIVES,
        )
        result["content"] = validate_content_repair_report(
            args.content_repair_report.resolve(), args.content_repair_report_sha256, runtime, client,
        )
        result["followup"] = validate_followup_repair_report(
            args.followup_repair_report.resolve(), args.followup_repair_report_sha256, runtime, client,
        )
        result["server_mods"] = gate.validate_side(runtime, "server", args.cei_name, args.cei_sha256, args.cei_bytes)
        result["client_mods"] = gate.validate_side(client, "client", args.cei_name, args.cei_sha256, args.cei_bytes)
        result["status"] = "PASS_STATIC"
    except Exception as exc:
        result["blockers"].append({"type": type(exc).__name__, "message": str(exc)})
    return result


def _write_validation_report(path: Path, result: dict[str, Any]) -> None:
    resolved = path.resolve()
    if not gate.within(resolved, ALLOWED):
        _fail(f"static validation report must stay under D: migration-audit-work: {resolved}")
    if resolved.exists() or resolved.is_symlink():
        _fail(f"static validation report must be fresh: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(resolved.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, resolved)


def _parser() -> argparse.ArgumentParser:
    parser = gate.parser()
    parser.add_argument("--validate-only", action="store_true", help="validate Attempt12 state without starting Java")
    parser.add_argument("--validate-report", type=Path, help="write the validate-only JSON evidence under <TRANS_ROOT>")
    parser.add_argument("--core-repair-report", type=Path, default=ATTEMPT12_CORE_REPORT)
    parser.add_argument("--tlm-apply-report", type=Path, default=ATTEMPT12_TLM_REPORT)
    parser.add_argument("--happyghast-repair-report", type=Path, default=ATTEMPT12_HAPPYGHAST_REPORT)
    return parser


def main() -> int:
    args = _parser().parse_args()
    _configure_attempt12_locks(args)
    _install_save_aware_stop()
    gate.validate_content_repair_report = validate_content_repair_report
    gate.validate_followup_repair_report = validate_followup_repair_report
    if args.validate_only:
        result = _validate_only(args)
        if args.validate_report is not None:
            try:
                _write_validation_report(args.validate_report, result)
                result["validation_report"] = str(args.validate_report.resolve())
            except Exception as exc:
                result["status"] = "NO_GO"
                result["blockers"].append({"type": type(exc).__name__, "message": str(exc)})
        print(json.dumps({"status": result["status"], "mode": result["mode"], "blockers": result["blockers"], "validation_report": result.get("validation_report")}, ensure_ascii=False))
        return 0 if result["status"] == "PASS_STATIC" else 1
    result = gate.run(args)
    print(json.dumps({"status": result["status"], "report": str(args.report.resolve()), "blockers": result["blockers"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
