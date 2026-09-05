#!/usr/bin/env python3
"""Build an isolated, fail-closed resource/data repair candidate for Attempt6.

The script is deliberately source-hash guarded and never writes to the Attempt6
runtime, frozen staging, production, or Prism directories.  It emits a patched
JAR set plus a loose KubeJS overlay under <AUDIT_ROOT>.
No Minecraft process is started by this tool.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


RUNTIME = Path(r"<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814")
AUDIT_LOG = Path(r"<AUDIT_ROOT>\attempt6-server-errors-by-logger-20260814.txt")
OUT = Path(r"<AUDIT_ROOT>\attempt6-data-resource-fixes-20260814")


JAR_HASHES = {
    "createadditionallogistics-1.21.1-1.4.5.jar": "F7BF95504C3BF293464B883C989354DD643D559DE5BFCAD4A23FED4144592D6A",
    "create_compressed-2.2.0-neoforge-1.21.1.jar": "8C0C86A75AA082FD603EB61DFDC72D028B01B1A7BDAD377ED2DE64ACE95B5622",
    "createdeco-2.1.3.jar": "EDACF1AD0BD6B9F1667D711650DC0CDE604356D91CACA7CA1EC428C2F9400C6E",
    "cmpackagecouriers-neoforge-2.3.0.jar": "76E728A765EE04A53E566EDA6B302A05FF855965DCF0230CC33F3DD2C1836E8B",
    "railways-0.2.1+neoforge-mc1.21.1.jar": "B7636C8B1B0352ED1A130DFE67F8BB574E2FC08803ED1CDA4D3EA00505193914",
    "create_connected-1.3.2-mc1.21.1.jar": "90BDCEAC63CB0EBD5E51351E22136182B996512EDEF937D0635D2857B0A3F24B",
    "tracks-neoforge-1.21.1-1.0.1.jar": "B126B2522A129C13EBEC6491B8602726BAD9A3DF201CF906468BA583796125C8",
    "creategearsandtavern-1.1.6.jar": "6BBB610BEDD6B6FF35523FD65BA83C6EBCA398FDF47440F27A20FA626AB6F5F0",
    "biomespy-neoforge-1.21.1-1.3.3.jar": "2207CCFF37F0631EBFAF692CF5AED9304835298C34DF31C39B8558FD8C568ACB",
    "DnT-ancient-city-overhaul-v2 [NeoForge].jar": "890882EC1239FFF1CD5CC5F1DA1FE4BE98A31E748D418220BEE5F2B9F3D8FD91",
    "irons_spellbooks-1.21.1-3.15.6.jar": "BA1F1986CA706AE348CB6FCE6E383AB7CC61C375826CCF0E4D3A88ED2F9FCD3D",
}


LOOSE_HASHES = {
    "kubejs/data/c6c/worldgen/biome/end_cherry_grove.json": "87C3E72AE63047B7A198FE4AF2FEDB51A137B25621195F82E7FAB414BA0D6D4C",
    "kubejs/data/minecraft/worldgen/biome/beach.json": "876AF5DE277457AA00CF9868D3EDF7A3B302340769491DAC073169AF0D9125AF",
    "kubejs/data/minecraft/worldgen/biome/desert.json": "C1DA157957E9086ACE3CA8EB97D60BED3B05E9450F236EC7F99597C57236ADE4",
    "kubejs/data/minecraft/worldgen/biome/mangrove_swamp.json": "71BA9FD6535F21361594AE33D3D3B49DF2C957202646727E2E1DE83B13DAA0C4",
    "kubejs/data/minecraft/worldgen/biome/swamp.json": "B5AB5B9C4EAD760D7062EBC3717E7D934ECDBF231019DB6900EB40376F6470E1",
    "kubejs/data/minecraft/worldgen/biome/wooded_badlands.json": "FA1ADDA7DB1E9E50BBE93E201F850D862E8BB06739559C5ECC46419AF9E09F8E",
    "kubejs/data/touhou_little_maid/curios/entities/curios.json": "D6A2DBB01906713B97295AE4545656E84018793D353AC16BA776CE832BA72F0E",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def fail(message: str) -> None:
    raise RuntimeError(message)


def verify_file(path: Path, expected: str) -> bytes:
    if not path.is_file():
        fail(f"missing source: {path}")
    actual = sha256_file(path)
    if actual != expected.upper():
        fail(f"source hash changed: {path} expected={expected} actual={actual}")
    return path.read_bytes()


def exact_replace(data: bytes, old: bytes, new: bytes, expected_count: int, label: str) -> bytes:
    count = data.count(old)
    if count != expected_count:
        fail(f"{label}: expected {expected_count} occurrences, found {count}")
    return data.replace(old, new)


def zipinfo_for(info: zipfile.ZipInfo, name: str) -> zipfile.ZipInfo:
    # Copy metadata while changing only the entry name.  This keeps executable
    # bits, compression method, and extra fields of untouched resources.
    out = copy.copy(info)
    out.filename = name
    return out


def patch_jar(
    jar_name: str,
    replacements: dict[str, bytes] | None = None,
    renames: dict[str, str] | None = None,
    removals: set[str] | None = None,
) -> tuple[Path, dict[str, Any]]:
    replacements = replacements or {}
    renames = renames or {}
    removals = removals or set()
    src = RUNTIME / "mods" / jar_name
    src_bytes = verify_file(src, JAR_HASHES[jar_name])
    del src_bytes  # verification is the purpose; ZipFile streams entries below.
    out = OUT / "jars" / jar_name
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    changes: list[dict[str, Any]] = []
    seen: set[str] = set()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for info in zin.infolist():
            old_name = info.filename
            if old_name in removals:
                changes.append({"entry": old_name, "action": "remove", "old_sha256": sha256_bytes(zin.read(info))})
                continue
            new_name = renames.get(old_name, old_name)
            if new_name in seen:
                fail(f"duplicate output ZIP entry: {new_name}")
            seen.add(new_name)
            raw = zin.read(info)
            new_data = replacements.get(old_name, raw)
            if new_data != raw or new_name != old_name:
                changes.append(
                    {
                        "entry": old_name,
                        "output_entry": new_name,
                        "action": "replace" if new_data != raw else "rename",
                        "old_sha256": sha256_bytes(raw),
                        "new_sha256": sha256_bytes(new_data),
                    }
                )
            zout.writestr(zipinfo_for(info, new_name), new_data)
    tmp.replace(out)
    return out, {
        "source": str(src),
        "source_sha256": JAR_HASHES[jar_name],
        "output": str(out),
        "output_sha256": sha256_file(out),
        "changes": changes,
    }


def prepare_loose_overlay(manifest: list[dict[str, Any]]) -> None:
    for rel, expected in LOOSE_HASHES.items():
        src = RUNTIME / rel.replace("/", "\\")
        raw = verify_file(src, expected)
        fixed = raw
        reason = ""
        if rel.endswith("end_cherry_grove.json"):
            fixed = exact_replace(
                raw,
                b'      "wythers:vegetation/local/patch/elephant_bamboo_cherry",\n',
                b'      "wythers:vegetation/local/patch/elephant_bamboo_cherry"\n',
                1,
                rel,
            )
            reason = "remove trailing feature comma"
        elif rel.endswith("beach.json"):
            fixed = exact_replace(raw, b"\n,\n", b"\n", 1, rel)
            reason = "remove standalone comma in feature array"
        elif rel.endswith("desert.json"):
            fixed = exact_replace(raw, b"\n,\n", b"\n", 1, rel)
            reason = "remove standalone comma in feature array"
        elif rel.endswith("mangrove_swamp.json"):
            fixed = exact_replace(raw, b'      "minecraft:fossil_lower",\n', b'      "minecraft:fossil_lower"\n', 1, rel)
            reason = "remove trailing feature comma"
        elif rel.endswith("swamp.json"):
            fixed = exact_replace(raw, b'      "minecraft:fossil_lower",\n', b'      "minecraft:fossil_lower"\n', 1, rel)
            reason = "remove trailing feature comma"
        elif rel.endswith("wooded_badlands.json"):
            fixed = exact_replace(raw, b"\n,\n", b"\n", 1, rel)
            reason = "remove standalone comma in feature array"
        elif rel.endswith("touhou_little_maid/curios/entities/curios.json"):
            fixed = exact_replace(raw, b'    "scroll",\n', b"", 1, rel)
            reason = "remove unregistered optional Curios slot scroll"
        else:
            fail(f"unhandled loose resource: {rel}")
        try:
            json.loads(fixed.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - fail-closed guard
            fail(f"fixed loose JSON still invalid: {rel}: {exc}")
        dest = OUT / "overlay" / rel.replace("/", "\\")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fixed)
        manifest.append(
            {
                "kind": "loose_overlay",
                "source": str(src),
                "source_sha256": expected,
                "output": str(dest),
                "output_sha256": sha256_bytes(fixed),
                "reason": reason,
            }
        )


def build_replacements() -> tuple[dict[str, dict[str, bytes]], dict[str, dict[str, str]], dict[str, set[str]], list[dict[str, Any]]]:
    replacements: dict[str, dict[str, bytes]] = {}
    renames: dict[str, dict[str, str]] = {}
    removals: dict[str, set[str]] = {}
    notes: list[dict[str, Any]] = []

    def add_replace(jar: str, entry: str, fn: Callable[[bytes], bytes], reason: str) -> None:
        src = RUNTIME / "mods" / jar
        with zipfile.ZipFile(src) as z:
            if entry not in z.namelist():
                fail(f"missing JAR entry: {jar}!{entry}")
            old = z.read(entry)
        new = fn(old)
        replacements.setdefault(jar, {})[entry] = new
        notes.append({"kind": "jar_entry", "jar": jar, "entry": entry, "old_sha256": sha256_bytes(old), "new_sha256": sha256_bytes(new), "reason": reason})

    # NeoForge data-map conditions belong on each value object, not at the root.
    cal = "createadditionallogistics-1.21.1-1.4.5.jar"
    cal_entry = "data/createadditionallogistics/data_maps/item/currency.json"
    def fix_currency(raw: bytes) -> bytes:
        obj = json.loads(raw)
        if set(obj) != {"neoforge:conditions", "values"}:
            fail("currency data map shape changed")
        cond = obj["neoforge:conditions"]
        values = obj["values"]
        if len(values) != 6 or any(not k.startswith("numismatics:") for k in values):
            fail("currency data map values changed")
        out = {"values": {}}
        for key, value in values.items():
            out["values"][key] = {"neoforge:conditions": cond, "neoforge:value": value}
        return json_bytes(out)
    add_replace(cal, cal_entry, fix_currency, "move optional numismatics condition to each data-map value")

    cc = "create_compressed-2.2.0-neoforge-1.21.1.jar"
    add_replace(
        cc,
        "data/create_compressed/recipe/sandpaper_polishing/polished_rose_quartz_block.json",
        lambda raw: exact_replace(raw, b'"item": "create_compressed:rose_quartz_polished_block"', b'"id": "create_compressed:rose_quartz_polished_block"', 1, "rose quartz result"),
        "Create 6 recipe result uses id",
    )
    def fix_dough(raw: bytes) -> bytes:
        raw = exact_replace(raw, b'"item": "create_compressed:dough_block"', b'"id": "create_compressed:dough_block"', 1, "dough result")
        raw = exact_replace(raw, b'      "amount": 1000,\n      "fluid": "minecraft:water",\n      "nbt": {}', b'      "type": "neoforge:single",\n      "amount": 1000,\n      "fluid": "minecraft:water"', 1, "dough fluid ingredient")
        return raw
    add_replace(cc, "data/create_compressed/recipe/mixing/dough_block.json", fix_dough, "Create 6 fluid ingredient/result schema")

    deco = "createdeco-2.1.3.jar"
    add_replace(deco, "data/createdeco/recipe/placard.json", lambda raw: exact_replace(raw, b'"id": "minecraft:white_dye"', b'"item": "minecraft:white_dye"', 1, "placard ingredient"), "crafting ingredient uses item")

    couriers = "cmpackagecouriers-neoforge-2.3.0.jar"
    def fix_jar_plane(raw: bytes) -> bytes:
        obj = json.loads(raw.decode("utf-8-sig"))
        if obj.get("type") != "create:deploying" or len(obj.get("ingredients", [])) != 2:
            fail("jar_plane recipe shape changed")
        obj["neoforge:conditions"] = [{"type": "neoforge:mod_loaded", "modid": "create_factory_logistics"}]
        # Keep the original order as much as possible; condition is intentionally
        # top-level and the recipe remains available when the optional mod is OTA-added.
        ordered = {"neoforge:conditions": obj.pop("neoforge:conditions"), **obj}
        return json_bytes(ordered)
    add_replace(couriers, "data/cmpackagecouriers/recipe/deploying/jar_plane.json", fix_jar_plane, "gate missing Create Factory Logistics ingredient")

    rail = "railways-0.2.1+neoforge-mc1.21.1.jar"
    family_mod = {
        "track_biomesoplenty_": "biomesoplenty",
        "track_blue_skies_": "blue_skies",
        "track_byg_": "byg",
        "track_create_dd_": "create_dd",
        "track_hexcasting_": "hexcasting",
        "track_natures_spirit_": "natures_spirit",
        "track_quark_": "quark",
        "track_tfc_": "tfc",
        "track_twilightforest_": "twilightforest",
    }
    with zipfile.ZipFile(RUNTIME / "mods" / rail) as z:
        rail_entries = [n for n in z.namelist() if n.startswith("data/railways/loot_table/") and n.endswith(".json")]
        optional = [n for n in rail_entries if any(Path(n).stem.startswith(prefix) for prefix in family_mod)]
        if len(optional) != 276:
            fail(f"Railways optional loot count changed: {len(optional)}")
        for entry in optional:
            raw = z.read(entry)
            obj = json.loads(raw)
            stem = Path(entry).stem
            modid = next(mod for prefix, mod in family_mod.items() if stem.startswith(prefix))
            if "conditions" in obj:
                if "neoforge:conditions" in obj:
                    fail(f"Railways entry already has both condition keys: {entry}")
                conds = obj.pop("conditions")
                if not isinstance(conds, list) or len(conds) != 1 or conds[0].get("condition") != "neoforge:mod_loaded":
                    fail(f"unexpected Railways legacy condition: {entry}")
                if modid == "byg":
                    cond = {"type": "neoforge:or", "values": [{"type": "neoforge:mod_loaded", "modid": "byg"}, {"type": "neoforge:mod_loaded", "modid": "biomeswevegone"}]}
                else:
                    cond = {"type": "neoforge:mod_loaded", "modid": modid}
            else:
                cond = {"type": "neoforge:mod_loaded", "modid": modid}
            obj["neoforge:conditions"] = [cond]
            # Keep a stable, readable output.  Loot semantics are untouched apart
            # from fail-closed optional loading.
            replacements.setdefault(rail, {})[entry] = json_bytes(obj)
            notes.append({"kind": "jar_entry", "jar": rail, "entry": entry, "reason": f"gate optional Railways {modid} loot; convert legacy conditions"})

    # Create Connected's extended-colour blocks are supplied by the optional
    # Dye Depot mod.  Their recipes are already gated, but the 16 block loot
    # tables were not; add the same fail-closed condition without deleting any
    # future OTA content.
    connected = "create_connected-1.3.2-mc1.21.1.jar"
    with zipfile.ZipFile(RUNTIME / "mods" / connected) as z:
        dye_entries = [
            n for n in z.namelist()
            if n.startswith("data/create_connected/loot_table/")
            and n.endswith(".json")
            and "dye_depot_" in Path(n).stem
        ]
        if len(dye_entries) != 16:
            fail(f"Create Connected Dye Depot loot count changed: {len(dye_entries)}")
        for entry in dye_entries:
            raw = z.read(entry)
            obj = json.loads(raw)
            if "neoforge:conditions" in obj:
                fail(f"Create Connected entry already conditioned: {entry}")
            obj["neoforge:conditions"] = [{"type": "neoforge:mod_loaded", "modid": "dye_depot"}]
            replacements.setdefault(connected, {})[entry] = json_bytes(obj)
            notes.append({"kind": "jar_entry", "jar": connected, "entry": entry, "reason": "gate optional Dye Depot loot"})

    tracks = "tracks-neoforge-1.21.1-1.0.1.jar"
    with zipfile.ZipFile(RUNTIME / "mods" / tracks) as z:
        for entry in z.namelist():
            if entry.endswith(".json"):
                raw = z.read(entry)
                if b"Tracks:" in raw:
                    replacements.setdefault(tracks, {})[entry] = exact_replace(raw, b"Tracks:", b"tracks:", raw.count(b"Tracks:"), f"Tracks namespace {entry}")
                    notes.append({"kind": "jar_entry", "jar": tracks, "entry": entry, "reason": "lowercase invalid Tracks namespace"})

    tavern = "creategearsandtavern-1.1.6.jar"
    tavern_entry = "data/create/tags/item/upright_on_belt.json"
    def fix_tavern_tag(raw: bytes) -> bytes:
        obj = json.loads(raw)
        vals = obj.get("values")
        if not isinstance(vals, list) or sum(isinstance(v, str) and v.startswith("kaleidoscope_twilight:") for v in vals) != 14:
            fail("tavern tag shape/count changed")
        obj["values"] = [({"id": v, "required": False} if isinstance(v, str) and v.startswith("kaleidoscope_twilight:") else v) for v in vals]
        return json_bytes(obj)
    add_replace(tavern, tavern_entry, fix_tavern_tag, "mark absent Kaleidoscope Twilight items optional in tag")

    bio = "biomespy-neoforge-1.21.1-1.3.3.jar"
    weird = "data/biomespy/tags/worldgen/structure/uninit_safe.json\u200e"
    normal = "data/biomespy/tags/worldgen/structure/uninit_safe.json"
    with zipfile.ZipFile(RUNTIME / "mods" / bio) as z:
        if weird not in z.namelist() or normal in z.namelist():
            fail("BiomeSpy malformed entry shape changed")
    renames.setdefault(bio, {})[weird] = normal
    notes.append({"kind": "jar_entry", "jar": bio, "entry": weird, "output_entry": normal, "reason": "remove U+200E from resource path"})

    dnt = "DnT-ancient-city-overhaul-v2 [NeoForge].jar"
    dnt_targets = [
        "data/minecraft/loot_table/chests/illager_mansion/library_chest.json",
        "data/minecraft/loot_table/chests/illager_mansion/secret_room.json",
    ]
    for entry in dnt_targets:
        def fix_dnt(raw: bytes, _entry: str = entry) -> bytes:
            obj = json.loads(raw.decode("utf-8-sig"))
            found = 0
            def walk(x: Any) -> None:
                nonlocal found
                if isinstance(x, dict):
                    if x.get("function") == "minecraft:enchant_randomly" and x.get("options") == "nova_structures:illagers_bane":
                        # Keep the book/weight entry but remove only the invalid
                        # function.  This is the smallest fail-closed semantic
                        # delta; an exact Nova enchant replacement remains a blocker.
                        x.pop("function", None)
                        x.pop("options", None)
                        found += 1
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)
            walk(obj)
            if found != 1:
                fail(f"DnT target {_entry}: expected one invalid enchant function, found {found}")
            return json_bytes(obj)
        add_replace(dnt, entry, fix_dnt, "remove only absent nova_structures:illagers_bane function; preserve chest loot")

    iron = "irons_spellbooks-1.21.1-3.15.6.jar"
    iron_entry = "data/irons_spellbooks/loot_table/test/ring_gen_break_me.json"
    with zipfile.ZipFile(RUNTIME / "mods" / iron) as z:
        if iron_entry not in z.namelist():
            fail("Iron test loot entry missing")
        all_bytes = b"".join(z.read(n) for n in z.namelist() if n.endswith(".json") and n != iron_entry)
        if b"ring_gen_break_me" in all_bytes:
            fail("Iron test table is referenced by another JSON; refusing removal")
    removals.setdefault(iron, set()).add(iron_entry)
    notes.append({"kind": "jar_entry", "jar": iron, "entry": iron_entry, "reason": "remove orphan test loot table with minecraft:none spell"})

    return replacements, renames, removals, notes


def write_reports(manifest: dict[str, Any]) -> None:
    (OUT / "reports").mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums: list[str] = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name not in {"SHA256SUMS.txt"}:
            sums.append(f"{sha256_file(p)}  {p.relative_to(OUT).as_posix()}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    report = OUT / "reports" / "ATTEMPT6-DATA-RESOURCE-FIXES.md"
    report.write_text(
        "# Attempt6 data/resource repair candidate (2026-08-14)\n\n"
        "Scope: read-only audit-derived candidate. Minecraft was not started and the Attempt6 runtime, frozen staging, production, and Prism were not modified.\n\n"
        "## Applied candidate changes\n\n"
        "- Six malformed KubeJS biome JSONs: comma-only syntax repairs.\n"
        "- KubeJS Touhou Little Maid Curios override: remove unregistered `scroll` slot.\n"
        "- Create Additional Logistics data map: move `numismatics` condition to each value.\n"
        "- Create Compressed/Create Deco recipes: 1.21 schema fixes.\n"
        "- Package Couriers recipe: fail-closed `create_factory_logistics` condition.\n"
        "- Railways: 276 optional loot tables gated with NeoForge conditions; legacy conditions converted; BYG accepts `byg` or `biomeswevegone`.\n"
        "- Create Connected: 16 Dye Depot loot tables gated with `dye_depot`. Existing 35 related tag files were audited; their optional entries are already `required:false`, so no unnecessary tag rewrite was made.\n"
        "- Tracks: lowercase `Tracks:` in all six affected JSON entries (3 loot + 3 tags).\n"
        "- Create Gears & Tavern: mark 14 absent Kaleidoscope Twilight tag entries `required:false`.\n"
        "- BiomeSpy: rename malformed U+200E-suffixed resource path.\n"
        "- DnT/Nova: remove only the invalid `nova_structures:illagers_bane` enchant function from two mansion chest entries; book loot and Nova modifier remain. Exact replacement enchantment remains a semantic review blocker.\n"
        "- Iron's Spells: remove orphan `test/ring_gen_break_me.json` only after reference scan.\n\n"
        "See `manifest.json` for source/output hashes and every changed entry. Candidate JARs are under `jars/`; loose overlay files are under `overlay/`.\n",
        encoding="utf-8",
    )
    (OUT / "reports" / "ATTEMPT6-ERROR-CLASSIFICATION.md").write_text(
        "# Attempt6 error classification (WorldEdit excluded)\n\n"
        "Evidence: `attempt6-server-errors-by-logger-20260814.txt` (SHA-256 `7C5F3B598FD7E9DA2E6B9956F115800365A1E11C4DE85DA993109AFA7288BD90`). No Minecraft process was started.\n\n"
        "| Logger group | Count | Classification | Candidate status |\n"
        "|---|---:|---|---|\n"
        "| LootDataType | 298 | Optional Railways/Create Connected assets, Tracks namespace typo, DnT invalid Nova option, orphan Iron test table | 298 statically repaired; DnT replacement is a documented semantic-risk delta |\n"
        "| BiomeGenerationSettings | 6 | Six malformed loose KubeJS biome JSONs (comma syntax) | Fixed in 7-file loose overlay (six biome files plus Curios) |\n"
        "| DataMapLoader | 6 | Root-level optional condition uses wrong data-map schema | Fixed per-value `neoforge:conditions` + `neoforge:value` |\n"
        "| RecipeManager | 4 | Four 1.21 recipe schema/optional dependency issues | Fixed in four JAR entries |\n"
        "| TagLoader | 4 | Three Tracks namespace typos; one missing optional Kaleidoscope Twilight tag set | Fixed in Tracks and Tavern JAR entries |\n"
        "| KubeJS | 1 | Duplicate symptom of the Tavern `create:upright_on_belt` missing references | Cleared by the same `required:false` tag repair |\n"
        "| Curios API | 1 | Loose Touhou Little Maid override requests unregistered `scroll` slot | Removed only `scroll`; other current slots preserved |\n"
        "| net.minecraft.Util | 1 | BiomeSpy path ends in U+200E | Renamed entry to valid path |\n"
        "| RuntimeDistCleaner | 15 | Client-only class probes during dedicated-server transform; caught and startup proceeds | Benign/no safe resource patch; retain client code |\n"
        "| RefmapRemapper | 1 | Connector bootstrap dummy `\\~nonexistent` refmap open | Benign/no gameplay patch; accepted baseline |\n"
        "| WorldEdit | 1 | Explicitly excluded per task; handled by another agent | Not included here |\n\n"
        "## Remaining blockers / review items\n\n"
        "1. The DnT/Nova candidate removes only the invalid `nova_structures:illagers_bane` function from two book entries. It preserves the book, weight, chest pools, and `nova_structures:loot_modifier`, but an exact replacement enchantment is not proven from the current dependency set.\n"
        "2. Curios behavior depends on the corrected loose KubeJS file winning the resource-pack merge over the base Touhou Little Maid entry; a later isolated reload/startup gate must verify slot ordering.\n"
        "3. RuntimeDistCleaner and RefmapRemapper lines are expected noisy diagnostics, not evidence of a data-loss path.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="replace an existing candidate directory only if it contains this tool's marker")
    args = parser.parse_args()
    if OUT.exists():
        marker = OUT / "manifest.json"
        if not args.replace or not marker.exists():
            fail(f"output exists; use --replace only for a prior candidate: {OUT}")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "reports").mkdir(parents=True, exist_ok=True)
    if AUDIT_LOG.is_file():
        shutil.copy2(AUDIT_LOG, OUT / "reports" / AUDIT_LOG.name)
    child = Path(r"<AUDIT_ROOT>\loot298-audit-20260814")
    if child.is_dir():
        shutil.copy2(child / "loot298-audit.json", OUT / "reports" / "loot298-audit.json")
        shutil.copy2(child / "LOOT298-AUDIT.md", OUT / "reports" / "LOOT298-AUDIT.md")
        shutil.copy2(child / "HANDOFF.md", OUT / "reports" / "LOOT298-HANDOFF.md")

    manifest: dict[str, Any] = {
        "schema": "attempt6-data-resource-fixes/v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "runtime": str(RUNTIME),
        "scope_guard": {"minecraft_started": False, "attempt6_modified": False, "frozen_staging_modified": False, "production_modified": False, "prism_modified": False},
        "source_jars": JAR_HASHES,
        "source_loose": LOOSE_HASHES,
        "jar_changes": [],
        "loose_changes": [],
        "notes": [],
    }
    prepare_loose_overlay(manifest["loose_changes"])
    replacements, renames, removals, notes = build_replacements()
    manifest["notes"] = notes
    for jar in sorted(set(replacements) | set(renames) | set(removals)):
        out, info = patch_jar(jar, replacements.get(jar), renames.get(jar), removals.get(jar))
        manifest["jar_changes"].append(info)
    write_reports(manifest)
    print(json.dumps({"output": str(OUT), "jars": len(manifest["jar_changes"]), "loose": len(manifest["loose_changes"]), "notes": len(notes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
