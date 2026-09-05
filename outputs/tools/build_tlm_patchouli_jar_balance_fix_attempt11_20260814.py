#!/usr/bin/env python3
"""Build a minimal BOTH-side TLM Patchouli resource fix for Attempt11.

The server-side ``kubejs/server_scripts/maid.js`` balance rule remains the
source of truth: this tool never edits recipes or maid.js.  It only removes the
two stale Patchouli ``altar_recipe/spawn_box`` page objects from the original
TLM JAR.  The JAR is built twice from the same immutable bytes, compared
byte-for-byte, CRC-tested, and emitted with a fail-closed integration and
rollback plan.  No Java or Minecraft process is started.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUT = Path(r"<AUDIT_ROOT>\tlm-patchouli-jar-balance-fix-attempt11-20260814")
SERVER_ROOT = Path(r"<AUDIT_ROOT>\mechanomania-matched-runtime-attempt11-20260814")
CLIENT_ROOT = Path(r"<AUDIT_ROOT>\mechanomania-matched-client-attempt11-20260814")
REFERENCE_JAR = (
    Path(r"<AUDIT_ROOT>\mechanomania-matched-client-attempt9-20260814")
    / "mods"
    / "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
)
JAR_NAME = "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
TLM_SHA256 = "F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27"
TLM_BYTES = 24_408_776
RECIPE_ID = "touhou_little_maid:altar_recipe/spawn_box"
MAID_REL = "kubejs/server_scripts/maid.js"
MAID_SHA256 = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
LOG_PATH = (
    Path(r"<AUDIT_ROOT>\mechanomania-startup-gate-attempt11-artifacts-20260814")
    / "failure-client-round1.state.stdout.log"
)
LOG_SHA256 = "89C85AB19048938C5C9282D97E8C66FC3FF968FB2AE7FA0315A6BD0CA417516F"

ENTRY_SPECS: dict[str, dict[str, Any]] = {
    "maid/spawn_maid.json": {
        "jar_entry": (
            "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
            "en_us/entries/maid/spawn_maid.json"
        ),
        "source_sha256": "F536A1BB528B4F7A8458C88985601F06E5225D33B34ACDA6F7A061E6B47AF2B3",
        "output_sha256": "2904581BFC4704CAF6829ADE482959E766B1A2EDA76C03FF3F23945E4625BD9C",
        "removed_page_index": 2,
    },
    "overview/multiblocks_altar.json": {
        "jar_entry": (
            "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
            "en_us/entries/overview/multiblocks_altar.json"
        ),
        "source_sha256": "6DB3EA530DC9B745D5A31CDBB4CE34C3711B105F48F449E18AC69D692AF4F98E",
        "output_sha256": "39CBE907D067E08C6FAD58FBB9601339D8A6141B236BD1F62FFEFB1603F25D3A",
        "removed_page_index": 4,
    },
}


class AuditError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise AuditError(message)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def require_file(path: Path, expected_sha256: str, expected_bytes: int | None = None) -> None:
    if not path.is_file():
        fail(f"missing guarded input: {path}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        fail(f"byte length mismatch: {path} expected={expected_bytes} actual={path.stat().st_size}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        fail(f"hash mismatch: {path} expected={expected_sha256} actual={actual}")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        fail(f"invalid JSON in {label}: {exc}")


def copy_zipinfo(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    out = copy.copy(info)
    out.filename = info.filename
    return out


def signed_entries(names: list[str]) -> list[str]:
    return [
        name
        for name in names
        if name.upper().startswith("META-INF/")
        and name.upper().endswith((".SF", ".RSA", ".DSA"))
    ]


def patch_entry(raw: bytes, spec: dict[str, Any], label: str) -> tuple[bytes, dict[str, Any]]:
    source = parse_json(raw, label)
    if not isinstance(source, dict) or not isinstance(source.get("pages"), list):
        fail(f"{label}: Patchouli entry shape is not an object with pages")
    matches = [
        (index, page)
        for index, page in enumerate(source["pages"])
        if isinstance(page, dict)
        and page.get("type") == "altar_recipe"
        and page.get("recipe_id") == RECIPE_ID
    ]
    if len(matches) != 1:
        fail(f"{label}: expected exactly one stale page, found {len(matches)}")
    index, removed = matches[0]
    if index != spec["removed_page_index"]:
        fail(f"{label}: removed page index changed: expected={spec['removed_page_index']} actual={index}")
    patched = copy.deepcopy(source)
    del patched["pages"][index]
    output = json_bytes(patched)
    if sha256_bytes(output) != spec["output_sha256"]:
        fail(f"{label}: canonical patched bytes changed")
    if RECIPE_ID in output.decode("utf-8"):
        fail(f"{label}: stale recipe reference survived patched entry")
    # Metadata and all remaining page objects must be byte/structure-equivalent
    # to the source apart from this single list deletion.
    expected = copy.deepcopy(source)
    del expected["pages"][index]
    if parse_json(output, label + " output") != expected:
        fail(f"{label}: output differs beyond one page deletion")
    return output, {
        "source_bytes": len(raw),
        "source_sha256": sha256_bytes(raw),
        "output_bytes": len(output),
        "output_sha256": sha256_bytes(output),
        "pages_before": len(source["pages"]),
        "pages_after": len(patched["pages"]),
        "removed_page_index": index,
        "removed_page": copy.deepcopy(removed),
        "recipe_id": RECIPE_ID,
    }


def audit_load_order() -> dict[str, Any]:
    require_file(LOG_PATH, LOG_SHA256)
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    if text.count("Altar recipe not found: " + RECIPE_ID) != 2:
        fail("Attempt11 client evidence no longer has exactly two TLM stale-page errors")
    reload_lines = [line for line in text.splitlines() if "Reloading ResourceManager:" in line]
    if len(reload_lines) != 1:
        fail(f"expected one client resource-stack line, found {len(reload_lines)}")
    stack = reload_lines[0].split("Reloading ResourceManager:", 1)[1].strip()
    # Resource-pack labels themselves contain commas (for example
    # ``[Last, assets]``), so a naive ``split(',')`` would fragment labels
    # and falsely report that the required packs are missing.  Treat the
    # logger's stack as an ordered string and locate the exact labels.
    required = [
        "KubeJS File Resource Pack [assets]",
        "mod/touhou_little_maid",
        "KubeJS Virtual Resource Pack [Last, assets]",
    ]
    positions = {token: stack.find(token) for token in required}
    missing = [token for token, position in positions.items() if position < 0]
    if missing:
        fail(f"resource stack missing required tokens: {missing} / {stack}")
    if not (positions[required[0]] < positions[required[1]] < positions[required[2]]):
        fail(f"unexpected KubeJS/TLM resource ordering: {positions}")

    overlay_specs = {
        "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/maid/spawn_maid.json": "2904581BFC4704CAF6829ADE482959E766B1A2EDA76C03FF3F23945E4625BD9C",
        "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json": "39CBE907D067E08C6FAD58FBB9601339D8A6141B236BD1F62FFEFB1603F25D3A",
    }
    overlay_rows: list[dict[str, Any]] = []
    for relative, expected in overlay_specs.items():
        path = CLIENT_ROOT / Path(relative)
        require_file(path, expected)
        raw = path.read_bytes()
        if RECIPE_ID in raw.decode("utf-8"):
            fail(f"Attempt11 overlay still references stale recipe: {path}")
        overlay_rows.append({"relative": relative, "sha256": expected, "bytes": len(raw)})

    return {
        "log": {"path": str(LOG_PATH), "sha256": LOG_SHA256, "stale_error_count": 2},
        "resource_stack_tokens": {
            "kubejs_file_assets": positions[required[0]],
            "tlm_mod": positions[required[1]],
            "kubejs_last_assets": positions[required[2]],
        },
        "observed_reason_overlay_did_not_win": "the corrected KubeJS file assets are listed before mod/touhou_little_maid; runtime still reports the JAR's stale recipe pages; the Last virtual pack does not contain these files",
        "attempt11_overlay_files": overlay_rows,
    }


def audit_balance_invariant() -> dict[str, Any]:
    maid = SERVER_ROOT / Path(MAID_REL)
    require_file(maid, MAID_SHA256, 119)
    maid_text = maid.read_text(encoding="utf-8")
    if maid_text.count(RECIPE_ID) != 1:
        fail("maid.js no longer removes exactly one spawn_box recipe")
    if "ServerEvents.recipes" not in maid_text or "event.remove" not in maid_text:
        fail("maid.js balance guard shape changed")
    return {
        "path": str(maid),
        "sha256": MAID_SHA256,
        "bytes": 119,
        "spawn_box_recipe_removed_by_server_script": True,
        "recipe_resource_not_deleted_by_this_patch": True,
    }


def audit_source_jar(source_path: Path) -> dict[str, Any]:
    require_file(source_path, TLM_SHA256, TLM_BYTES)
    require_file(REFERENCE_JAR, TLM_SHA256, TLM_BYTES)
    if source_path.read_bytes() != REFERENCE_JAR.read_bytes():
        fail("Attempt11 TLM source and immutable reference JAR differ")
    with zipfile.ZipFile(source_path, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            fail("source TLM JAR has duplicate entries")
        if signed_entries(names):
            fail(f"source TLM JAR is signed; refusing resource rewrite: {signed_entries(names)}")
        required = [
            "data/touhou_little_maid/patchouli_books/memorizable_gensokyo/book.json",
            "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json",
            "data/touhou_little_maid/advancement/base/spawn_maid.json",
        ] + [spec["jar_entry"] for spec in ENTRY_SPECS.values()]
        missing = [entry for entry in required if entry not in names]
        if missing:
            fail(f"source TLM JAR missing required resource entries: {missing}")
        source_entries: list[dict[str, Any]] = []
        spawn_refs: list[str] = []
        for name in names:
            raw = archive.read(name)
            if RECIPE_ID.encode("utf-8") in raw:
                spawn_refs.append(name)
        for label, spec in ENTRY_SPECS.items():
            raw = archive.read(spec["jar_entry"])
            actual = sha256_bytes(raw)
            if actual != spec["source_sha256"]:
                fail(f"source entry hash changed: {spec['jar_entry']}")
            source_entries.append(
                {
                    "label": label,
                    "path": spec["jar_entry"],
                    "bytes": len(raw),
                    "sha256": actual,
                    "pages": len(parse_json(raw, spec["jar_entry"])["pages"]),
                }
            )
        recipe_raw = archive.read("data/touhou_little_maid/recipe/altar_recipe/spawn_box.json")
        advancement_raw = archive.read("data/touhou_little_maid/advancement/base/spawn_maid.json")
        if not recipe_raw or not advancement_raw:
            fail("source recipe/advancement resources are unexpectedly empty")
        if "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json" not in names:
            fail("source spawn_box recipe entry missing")
        if sorted(spawn_refs) != sorted(
            [spec["jar_entry"] for spec in ENTRY_SPECS.values()]
            + ["data/touhou_little_maid/advancement/base/spawn_maid.json"]
        ):
            fail(f"unexpected source spawn_box references: {spawn_refs}")
        return {
            "path": str(source_path),
            "sha256": TLM_SHA256,
            "bytes": TLM_BYTES,
            "entry_count": len(names),
            "required_resource_paths": required,
            "source_patchouli_entries": source_entries,
            "spawn_box_reference_entries": sorted(spawn_refs),
            "recipe_entry_preserved": True,
            "advancement_entry_preserved": True,
            "book_definition_path": "data/touhou_little_maid/patchouli_books/memorizable_gensokyo/book.json",
            "content_path_root": "assets/touhou_little_maid/patchouli_books/.../en_us/entries/",
        }


def build_jar(source_path: Path, destination: Path) -> dict[str, Any]:
    replacements: dict[str, bytes] = {}
    diffs: list[dict[str, Any]] = []
    with zipfile.ZipFile(source_path, "r") as source:
        names = source.namelist()
        if len(names) != len(set(names)):
            fail("source JAR duplicate entries during build")
        for label, spec in ENTRY_SPECS.items():
            raw = source.read(spec["jar_entry"])
            patched, diff = patch_entry(raw, spec, label)
            replacements[spec["jar_entry"]] = patched
            diff["label"] = label
            diff["path"] = spec["jar_entry"]
            diffs.append(diff)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w") as output:
            for info in source.infolist():
                output.writestr(copy_zipinfo(info), replacements.get(info.filename, source.read(info)))
    return {"source_entry_count": len(names), "diffs": diffs}


def validate_output(source_path: Path, output_path: Path, build_meta: dict[str, Any]) -> dict[str, Any]:
    if sha256_file(output_path) == TLM_SHA256:
        fail("output JAR unexpectedly equals unpatched source")
    with zipfile.ZipFile(source_path, "r") as source, zipfile.ZipFile(output_path, "r") as output:
        if output.testzip() is not None:
            fail(f"output ZIP CRC failure: {output.testzip()}")
        source_names = source.namelist()
        output_names = output.namelist()
        if source_names != output_names:
            fail("output JAR entry set/order changed")
        if len(output_names) != len(set(output_names)):
            fail("output JAR duplicate entries")
        if signed_entries(output_names):
            fail(f"output JAR unexpectedly signed: {signed_entries(output_names)}")
        changed = [name for name in output_names if source.read(name) != output.read(name)]
        expected_changed = sorted(spec["jar_entry"] for spec in ENTRY_SPECS.values())
        if sorted(changed) != expected_changed:
            fail(f"unexpected changed JAR entries: {changed}")
        for label, spec in ENTRY_SPECS.items():
            source_obj = parse_json(source.read(spec["jar_entry"]), spec["jar_entry"] + " source")
            out_raw = output.read(spec["jar_entry"])
            if sha256_bytes(out_raw) != spec["output_sha256"]:
                fail(f"output entry hash mismatch: {spec['jar_entry']}")
            obj = parse_json(out_raw, spec["jar_entry"])
            if RECIPE_ID in out_raw.decode("utf-8"):
                fail(f"output entry still references spawn_box: {spec['jar_entry']}")
            if len(obj.get("pages", [])) != len(source_obj.get("pages", [])) - 1:
                fail(f"output page count changed unexpectedly: {spec['jar_entry']}")
        for preserved in [
            "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json",
            "data/touhou_little_maid/advancement/base/spawn_maid.json",
            "data/touhou_little_maid/patchouli_books/memorizable_gensokyo/book.json",
        ]:
            if source.read(preserved) != output.read(preserved):
                fail(f"non-target resource changed: {preserved}")
    return {
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "bytes": output_path.stat().st_size,
        "entry_count": len(output_names),
        "changed_entries": expected_changed,
        "unchanged_entries": len(output_names) - len(expected_changed),
        "zip_crc": "PASS",
        "duplicate_entries": False,
        "signed_jar": False,
        "recipe_resource_preserved": True,
        "advancement_resource_preserved": True,
    }


def integration_plan(output_path: Path, output_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "attempt11-tlm-patchouli-jar-integration/v1",
        "status": "STATIC_CANDIDATE",
        "side_recommendation": "BOTH",
        "reason_both": "TLM is a required shared mod; using the same patched JAR on server and client keeps mod hashes/resource provenance identical. The changed entries are client-facing assets, but a BOTH-side replacement avoids side drift.",
        "required_operations": [
            {
                "side": "server",
                "action": "replace_file_atomically",
                "relative_path": f"mods/{JAR_NAME}",
                "expected_source_sha256": TLM_SHA256,
                "artifact": str(output_path),
                "artifact_sha256": output_meta["sha256"],
                "artifact_bytes": output_meta["bytes"],
            },
            {
                "side": "client",
                "action": "replace_file_atomically",
                "relative_path": f"mods/{JAR_NAME}",
                "expected_source_sha256": TLM_SHA256,
                "artifact": str(output_path),
                "artifact_sha256": output_meta["sha256"],
                "artifact_bytes": output_meta["bytes"],
            },
        ],
        "optional_cleanup_after_replacement": [
            {
                "side": "client",
                "action": "delete_exact_redundant_overlay",
                "relative_path": "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/maid/spawn_maid.json",
                "expected_sha256": "2904581BFC4704CAF6829ADE482959E766B1A2EDA76C03FF3F23945E4625BD9C",
            },
            {
                "side": "client",
                "action": "delete_exact_redundant_overlay",
                "relative_path": "kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json",
                "expected_sha256": "39CBE907D067E08C6FAD58FBB9601339D8A6141B236BD1F62FFEFB1603F25D3A",
            },
        ],
        "must_not_change": [
            MAID_REL,
            "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json",
            "data/touhou_little_maid/advancement/base/spawn_maid.json",
            "world",
            "config",
            "MCModSync state",
        ],
        "postconditions": {
            "changed_mod_paths": [f"server/mods/{JAR_NAME}", f"client/mods/{JAR_NAME}"],
            "changed_jar_entries": sorted(spec["jar_entry"] for spec in ENTRY_SPECS.values()),
            "world_changes": 0,
            "recipe_changes": 0,
            "maid_js_changes": 0,
            "mcmodsync_changes": 0,
            "spawn_box_patchouli_references_in_output_jar": 0,
            "spawn_box_recipe_resource_in_output_jar": 1,
        },
        "next_gate": "fresh client reload/startup and strict error audit; this package is static-only",
    }


def write_rollback(out: Path) -> dict[str, Any]:
    rollback = {
        "schema": "attempt11-tlm-patchouli-rollback/v1",
        "status": "READY_NOT_EXECUTED",
        "source_original_sha256": TLM_SHA256,
        "source_original_bytes": TLM_BYTES,
        "patched_sha256": None,
        "target_relative_path": f"mods/{JAR_NAME}",
        "restore_source": str(REFERENCE_JAR),
        "preconditions": [
            "target JAR hash equals the patched artifact hash",
            "Minecraft/Prism process is stopped",
            "target is a fresh Attempt11 clone, not an authoritative source",
        ],
        "action": "atomically restore the original TLM JAR from restore_source; do not alter maid.js",
    }
    path = out / "rollback" / "rollback-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rollback, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script = out / "rollback" / "restore_tlm_patch_attempt11.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "$TargetRoot = $args[0]\n"
        f"$Source = '{REFERENCE_JAR}'\n"
        f"$Relative = 'mods\\{JAR_NAME}'\n"
        "$Target = Join-Path $TargetRoot $Relative\n"
        "if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw 'target JAR missing' }\n"
        f"$ExpectedPatched = '__PATCHED_SHA256__'\n"
        "$Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash\n"
        "if ($Actual -ne $ExpectedPatched) { throw \"refusing rollback: target hash is $Actual\" }\n"
        f"$ExpectedOriginal = '{TLM_SHA256}'\n"
        "$tmp = $Target + '.rollback.tmp'\n"
        "Copy-Item -LiteralPath $Source -Destination $tmp -Force\n"
        "Move-Item -LiteralPath $tmp -Destination $Target -Force\n"
        "Write-Output 'TLM JAR restored; maid.js was not touched.'\n",
        encoding="utf-8",
    )
    return {"plan": str(path), "script": str(script)}


def build(out: Path) -> dict[str, Any]:
    if out.exists():
        fail(f"refusing to overwrite existing output: {out}")
    if not SERVER_ROOT.is_dir() or not CLIENT_ROOT.is_dir():
        fail("Attempt11 roots are missing")
    source = CLIENT_ROOT / "mods" / JAR_NAME
    server_jar = SERVER_ROOT / "mods" / JAR_NAME
    audit = {
        "source_jar": audit_source_jar(source),
        "server_jar_sha256": sha256_file(server_jar),
        "server_jar_matches_client": server_jar.read_bytes() == source.read_bytes(),
        "load_order": audit_load_order(),
        "balance_invariant": audit_balance_invariant(),
    }
    if audit["server_jar_sha256"] != TLM_SHA256 or not audit["server_jar_matches_client"]:
        fail("Attempt11 server/client TLM source JARs are not identical")

    out.mkdir(parents=True)
    temp1 = out / ".build1" / JAR_NAME
    temp2 = out / ".build2" / JAR_NAME
    final = out / "jars" / JAR_NAME
    try:
        meta1 = build_jar(source, temp1)
        meta2 = build_jar(source, temp2)
        if meta1 != meta2 or temp1.read_bytes() != temp2.read_bytes():
            fail("two independent clean builds differ")
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temp1, final)
        output_meta = validate_output(source, final, meta1)
        plan = integration_plan(final, output_meta)
        rollback = write_rollback(out)
        rollback_obj = json.loads((out / "rollback" / "rollback-plan.json").read_text(encoding="utf-8"))
        rollback_obj["patched_sha256"] = output_meta["sha256"]
        (out / "rollback" / "rollback-plan.json").write_text(
            json.dumps(rollback_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # Fill the guarded hash into the generated rollback script.
        rollback_script = out / "rollback" / "restore_tlm_patch_attempt11.ps1"
        rollback_script.write_text(
            rollback_script.read_text(encoding="utf-8").replace("__PATCHED_SHA256__", output_meta["sha256"]),
            encoding="utf-8",
        )
        report = {
            "schema": "attempt11-tlm-patchouli-jar-balance-fix/v1",
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "status": "PASS_STATIC_CANDIDATE",
            "scope": {
                "java_started": False,
                "minecraft_started": False,
                "attempt11_modified": False,
                "world_modified": False,
                "release_modified": False,
                "prism_modified": False,
            },
            "diagnosis": {
                "jar_content_root": "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/",
                "book_definition_root": "data/touhou_little_maid/patchouli_books/memorizable_gensokyo/book.json",
                "why_old_overlay_failed": audit["load_order"]["observed_reason_overlay_did_not_win"],
                "recipe_balance_rule": "server maid.js removes altar_recipe/spawn_box; this JAR patch does not restore or delete that recipe resource",
            },
            "audit": audit,
            "build": {
                "clean_builds": 2,
                "byte_identical": True,
                "entry_diffs": meta1["diffs"],
                "output": output_meta,
            },
            "integration_plan": plan,
            "rollback": rollback,
            "limitations": [
                "No Minecraft runtime reload was run by this static task.",
                "The final gate must confirm the two TLM altar-recipe errors disappear and no other client regression appears.",
            ],
        }
        reports = out / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        report_json = reports / "attempt11-tlm-patchouli-jar-static-audit.json"
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_md = reports / "ATTEMPT11-TLM-PATCHOULI-JAR-FIX.md"
        report_md.write_text(
            "# Attempt11 TLM Patchouli JAR resource fix\n\n"
            "Status: `PASS_STATIC_CANDIDATE`; no Java/Minecraft process was started and Attempt11 was not modified.\n\n"
            "## Why the previous overlay did not work\n\n"
            "The TLM book is declared at `data/touhou_little_maid/patchouli_books/memorizable_gensokyo/book.json`, while its entry JSON files are under `assets/touhou_little_maid/patchouli_books/.../en_us/entries/`. Attempt11's reload stack lists `KubeJS File Resource Pack [assets]` before `mod/touhou_little_maid`, and the runtime still reports the two stale `spawn_box` pages. The corrected files therefore need to be in the TLM JAR (or a true higher-priority last pack), not only the ordinary KubeJS file pack.\n\n"
            "## Exact patch\n\n"
            "Only the `altar_recipe/spawn_box` page is removed from `maid/spawn_maid.json` and `overview/multiblocks_altar.json`. The spawn_box recipe JSON, advancement, book definition, maid.js, and every other JAR entry remain unchanged.\n\n"
            f"Output JAR: `{output_meta['bytes']}` bytes; SHA-256 `{output_meta['sha256']}`. Two clean builds are byte-identical, ZIP CRC passes, and exactly two entries differ.\n\n"
            "## Integration\n\n"
            "Replace the same TLM JAR on both server and client. The BOTH-side recommendation keeps the required shared mod hash identical; the content change is client-facing. The existing two KubeJS overlay JSONs may then be deleted as redundant, guarded by their exact hashes, but deleting them is optional.\n",
            encoding="utf-8",
        )
        manifest = {
            "schema": "attempt11-tlm-patchouli-jar-artifacts/v1",
            "status": "PASS_STATIC_CANDIDATE",
            "artifact": {"path": str(final), "sha256": output_meta["sha256"], "bytes": output_meta["bytes"]},
            "report": {"path": str(report_json), "sha256": sha256_file(report_json), "bytes": report_json.stat().st_size},
            "integration_plan": {"path": str(out / "integration-plan-attempt11.json")},
            "rollback": rollback,
        }
        (out / "integration-plan-attempt11.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest["integration_plan"]["sha256"] = sha256_file(out / "integration-plan-attempt11.json")
        manifest["integration_plan"]["bytes"] = (out / "integration-plan-attempt11.json").stat().st_size
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sums: list[str] = []
        for path in sorted((p for p in out.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
            if path.name == "SHA256SUMS.txt":
                continue
            sums.append(f"{sha256_file(path)}  {path.relative_to(out).as_posix()}")
        (out / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
        return {
            "status": "PASS_STATIC_CANDIDATE",
            "output": str(out),
            "jar": output_meta,
            "changed_entries": len(output_meta["changed_entries"]),
            "side": "BOTH",
        }
    except Exception:
        if out.exists():
            shutil.rmtree(out)
        raise
    finally:
        for temp in (out / ".build1", out / ".build2"):
            if temp.exists():
                shutil.rmtree(temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = build(args.out.resolve())
    except (AuditError, OSError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
