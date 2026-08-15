#!/usr/bin/env python3
"""Fail-closed dual-side verifier for the TLM Patchouli balance fix."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterable

from build_tlm_patchouli_balance_overlay import (
    ENTRY_SPECS,
    EXPECTED_JAR_SHA256,
    JAR_NAME,
    OVERLAY_ASSET_ROOT,
    RECIPE_ID,
    remove_stale_recipe_page,
)


EXPECTED_MAID_JS_SHA256 = (
    "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
)
EXPECTED_PACK_SHA256 = (
    "2B9C39579EA82A3D9C8C1A22029C7379D1BD240A1F4A08ABD70B03374E55617A"
)
PACK_MAID_JS = "overrides/kubejs/server_scripts/maid.js"
PACK_MULTIBLOCKS = (
    "overrides/kubejs/data/touhou_little_maid/patchouli_books/"
    "memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json"
)
JAR_RECIPE_ENTRY = "data/touhou_little_maid/recipe/altar_recipe/spawn_box.json"
JAR_ADVANCEMENT_ENTRY = "data/touhou_little_maid/advancement/base/spawn_maid.json"
EXPECTED_JAR_RECIPE_SHA256 = (
    "0D8BAB9F3AC09A5CAA7AB78AAC7BA0607D831C4453F8C149C97BCC8C14E5A97A"
)
EXPECTED_RECIPE_ID_JSON_OCCURRENCES = {
    str(spec["jar_entry"]) for spec in ENTRY_SPECS.values()
} | {JAR_ADVANCEMENT_ENTRY}
OVERLAY_CLIENT_ASSET_ROOT = Path(*OVERLAY_ASSET_ROOT.parts[1:])


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def has_exact_remove_rule(source: str) -> bool:
    recipe = re.escape(RECIPE_ID)
    pattern = (
        r"event\s*\.\s*remove\s*\(\s*\{.*?"
        r"id\s*:\s*['\"]" + recipe + r"['\"].*?\}\s*\)"
    )
    return re.search(pattern, source, flags=re.DOTALL) is not None


def iter_json_values(value: object) -> Iterable[object]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_values(child)


def count_json_value(value: object, target: object) -> int:
    return sum(1 for item in iter_json_values(value) if item == target)


def verify(
    server_root: Path,
    client_root: Path,
    pack_zip: Path,
    overlay_root: Path,
) -> dict[str, object]:
    server_root = server_root.resolve()
    client_root = client_root.resolve()
    pack_zip = pack_zip.resolve()
    overlay_root = overlay_root.resolve()
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("server_root_exists", server_root.is_dir(), str(server_root))
    add("client_root_exists", client_root.is_dir(), str(client_root))
    add("official_pack_exists", pack_zip.is_file(), str(pack_zip))
    add("overlay_root_exists", overlay_root.is_dir(), str(overlay_root))

    server_maid = server_root / "kubejs" / "server_scripts" / "maid.js"
    add("server_maid_js_exists", server_maid.is_file(), str(server_maid))
    if server_maid.is_file():
        server_maid_sha = sha256_file(server_maid)
        server_maid_text = server_maid.read_text(encoding="utf-8-sig")
        add(
            "server_balance_script_provenance",
            server_maid_sha == EXPECTED_MAID_JS_SHA256,
            f"expected={EXPECTED_MAID_JS_SHA256} actual={server_maid_sha}",
        )
        add(
            "server_balance_removal_preserved",
            has_exact_remove_rule(server_maid_text),
            f"{RECIPE_ID} remains intentionally removed",
        )

    pack_names: set[str] = set()
    pack_multiblocks: dict[str, object] | None = None
    if pack_zip.is_file():
        pack_sha = sha256_file(pack_zip)
        add(
            "official_pack_provenance",
            pack_sha == EXPECTED_PACK_SHA256,
            f"expected={EXPECTED_PACK_SHA256} actual={pack_sha}",
        )
        try:
            with zipfile.ZipFile(pack_zip) as archive:
                pack_names = set(archive.namelist())
                add("official_pack_maid_js_exists", PACK_MAID_JS in pack_names, PACK_MAID_JS)
                if PACK_MAID_JS in pack_names:
                    pack_maid = archive.read(PACK_MAID_JS)
                    add(
                        "official_pack_maid_js_provenance",
                        sha256_bytes(pack_maid) == EXPECTED_MAID_JS_SHA256,
                        sha256_bytes(pack_maid),
                    )
                    add(
                        "official_pack_intentional_removal",
                        has_exact_remove_rule(pack_maid.decode("utf-8-sig")),
                        RECIPE_ID,
                    )
                add(
                    "official_pack_existing_multiblocks_override",
                    PACK_MULTIBLOCKS in pack_names,
                    PACK_MULTIBLOCKS,
                )
                if PACK_MULTIBLOCKS in pack_names:
                    pack_multiblocks = json.loads(
                        archive.read(PACK_MULTIBLOCKS).decode("utf-8-sig")
                    )
                pack_spawn_override = (
                    "overrides/kubejs/data/touhou_little_maid/patchouli_books/"
                    "memorizable_gensokyo/en_us/entries/maid/spawn_maid.json"
                )
                add(
                    "official_pack_spawn_maid_override_is_missing",
                    pack_spawn_override not in pack_names,
                    pack_spawn_override,
                )
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            add("official_pack_readable", False, f"{type(exc).__name__}: {exc}")

    client_jar = client_root / "mods" / JAR_NAME
    add("client_tlm_jar_exists", client_jar.is_file(), str(client_jar))
    expected_patched_entries: dict[str, dict[str, object]] = {}
    if client_jar.is_file():
        jar_sha = sha256_file(client_jar)
        add(
            "client_tlm_jar_provenance",
            jar_sha == EXPECTED_JAR_SHA256,
            f"expected={EXPECTED_JAR_SHA256} actual={jar_sha}",
        )
        try:
            with zipfile.ZipFile(client_jar) as archive:
                names = set(archive.namelist())
                json_occurrences = {
                    name
                    for name in names
                    if name.endswith(".json") and RECIPE_ID.encode() in archive.read(name)
                }
                add(
                    "jar_recipe_id_occurrence_scope",
                    json_occurrences == EXPECTED_RECIPE_ID_JSON_OCCURRENCES,
                    "actual=" + ",".join(sorted(json_occurrences)),
                )
                add("upstream_recipe_still_exists", JAR_RECIPE_ENTRY in names, JAR_RECIPE_ENTRY)
                if JAR_RECIPE_ENTRY in names:
                    recipe_sha = sha256_bytes(archive.read(JAR_RECIPE_ENTRY))
                    add(
                        "upstream_recipe_provenance",
                        recipe_sha == EXPECTED_JAR_RECIPE_SHA256,
                        f"expected={EXPECTED_JAR_RECIPE_SHA256} actual={recipe_sha}",
                    )
                add(
                    "advancement_reference_preserved",
                    JAR_ADVANCEMENT_ENTRY in names
                    and RECIPE_ID.encode() in archive.read(JAR_ADVANCEMENT_ENTRY),
                    JAR_ADVANCEMENT_ENTRY,
                )

                for relative, spec in ENTRY_SPECS.items():
                    jar_entry = str(spec["jar_entry"])
                    source_bytes = archive.read(jar_entry)
                    source_sha = sha256_bytes(source_bytes)
                    source = json.loads(source_bytes.decode("utf-8"))
                    expected, removed_index, removed_page = remove_stale_recipe_page(source)
                    expected_patched_entries[relative] = expected
                    add(
                        f"{relative}:source_provenance",
                        source_sha == spec["source_sha256"],
                        f"expected={spec['source_sha256']} actual={source_sha}",
                    )
                    add(
                        f"{relative}:single_exact_page_selected",
                        removed_index == spec["removed_page_index"]
                        and removed_page
                        == {"type": "altar_recipe", "recipe_id": RECIPE_ID},
                        f"index={removed_index} page={json.dumps(removed_page, sort_keys=True)}",
                    )

                    overlay_path = overlay_root / OVERLAY_CLIENT_ASSET_ROOT / relative
                    add(f"{relative}:overlay_exists", overlay_path.is_file(), str(overlay_path))
                    if overlay_path.is_file():
                        patched = json.loads(overlay_path.read_text(encoding="utf-8-sig"))
                        add(
                            f"{relative}:exact_structural_diff",
                            patched == expected,
                            "only the selected stale page may differ",
                        )
                        source_without_pages = copy.deepcopy(source)
                        patched_without_pages = copy.deepcopy(patched)
                        source_without_pages.pop("pages", None)
                        patched_without_pages.pop("pages", None)
                        add(
                            f"{relative}:metadata_unchanged",
                            source_without_pages == patched_without_pages,
                            "all non-page fields are byte-semantically unchanged",
                        )
                        add(
                            f"{relative}:one_page_removed",
                            len(source["pages"]) == len(patched.get("pages", [])) + 1,
                            f"before={len(source['pages'])} after={len(patched.get('pages', []))}",
                        )
                        add(
                            f"{relative}:no_stale_recipe_reference",
                            count_json_value(patched, RECIPE_ID) == 0,
                            RECIPE_ID,
                        )
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            add("client_tlm_jar_readable", False, f"{type(exc).__name__}: {exc}")

    expected_overlay_files = {
        (OVERLAY_CLIENT_ASSET_ROOT / relative).as_posix()
        for relative in ENTRY_SPECS
    }
    actual_overlay_files = (
        {
            path.relative_to(overlay_root).as_posix()
            for path in overlay_root.rglob("*")
            if path.is_file()
        }
        if overlay_root.is_dir()
        else set()
    )
    add(
        "client_overlay_scope_exactly_two_assets",
        actual_overlay_files == expected_overlay_files,
        "actual=" + ",".join(sorted(actual_overlay_files)),
    )
    add(
        "server_projection_unchanged",
        not any(
            part in {"server_scripts", "data", "mods"}
            for path in actual_overlay_files
            for part in Path(path).parts
        ),
        "server changes=[]",
    )

    multiblocks_expected = expected_patched_entries.get(
        "overview/multiblocks_altar.json"
    )
    if pack_multiblocks is not None and multiblocks_expected is not None:
        add(
            "official_multiblocks_intent_preserved",
            pack_multiblocks == multiblocks_expected,
            "client asset overlay mirrors the official semantic edit",
        )
    if multiblocks_expected is not None:
        add(
            "reborn_maid_page_preserved",
            count_json_value(
                multiblocks_expected,
                "touhou_little_maid:altar_recipe/reborn_maid",
            )
            == 1,
            "reborn_maid remains visible",
        )

    client_target_root = (
        client_root
        / "kubejs"
        / "assets"
        / "touhou_little_maid"
        / "patchouli_books"
        / "memorizable_gensokyo"
        / "en_us"
        / "entries"
    )
    preexisting_targets = [
        str(client_target_root / relative)
        for relative in ENTRY_SPECS
        if (client_target_root / relative).exists()
    ]
    add(
        "attempt9_client_not_modified",
        not preexisting_targets,
        "preexisting_targets=" + ",".join(preexisting_targets)
        if preexisting_targets
        else "none",
    )
    add(
        "client_kubejs_asset_layer_exists",
        (client_root / "kubejs" / "assets").is_dir(),
        str(client_root / "kubejs" / "assets"),
    )
    add(
        "client_has_no_server_maid_script",
        not (client_root / "kubejs" / "server_scripts" / "maid.js").exists(),
        "client remains free of dedicated-server scripts",
    )

    log_path = client_root / "logs" / "latest.log"
    add("attempt9_client_log_exists", log_path.is_file(), str(log_path))
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        needle = f"Altar recipe not found: {RECIPE_ID}"
        error_count = log_text.count(needle)
        add(
            "attempt9_two_render_errors_reproduced",
            error_count == 2,
            f"expected=2 actual={error_count}",
        )

    passed = all(bool(check["passed"]) for check in checks)
    return {
        "schema": 1,
        "verdict": "PASS" if passed else "FAIL",
        "policy": "preserve_mechanomania_balance",
        "side_projection": {
            "server": {"action": "UNCHANGED", "maid_js_removal": "PRESERVED"},
            "client": {
                "action": "OVERLAY",
                "files": sorted(expected_overlay_files),
            },
        },
        "server_root": str(server_root),
        "client_root": str(client_root),
        "official_pack": str(pack_zip),
        "overlay_root": str(overlay_root),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-root", required=True, type=Path)
    parser.add_argument("--client-root", required=True, type=Path)
    parser.add_argument("--pack-zip", required=True, type=Path)
    parser.add_argument(
        "--overlay-root",
        type=Path,
        default=Path(__file__).resolve().parent / "overlay",
    )
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    report = verify(
        args.server_root,
        args.client_root,
        args.pack_zip,
        args.overlay_root,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
