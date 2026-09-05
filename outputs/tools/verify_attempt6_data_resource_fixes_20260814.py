#!/usr/bin/env python3
"""Static/unit verification for the isolated Attempt6 resource candidate."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


OUT = Path(r"<AUDIT_ROOT>\attempt6-data-resource-fixes-20260814")
RUNTIME = Path(r"<AUDIT_ROOT>\mechanomania-matched-runtime-attempt6-20260814")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    check(manifest["scope_guard"] == {"minecraft_started": False, "attempt6_modified": False, "frozen_staging_modified": False, "production_modified": False, "prism_modified": False}, "scope guard changed")
    check(len(manifest["jar_changes"]) == 11, "expected 11 patched JARs")
    check(len(manifest["loose_changes"]) == 7, "expected 7 loose overlay files")

    # Every output hash in the manifest must match the actual artifact.
    for item in manifest["jar_changes"]:
        out = Path(item["output"])
        check(out.is_file(), f"missing JAR output {out}")
        check(sha(out) == item["output_sha256"], f"JAR hash mismatch {out}")
        with zipfile.ZipFile(out) as z:
            check(z.testzip() is None, f"ZIP CRC failure {out}")
            names = z.namelist()
            check(len(names) == len(set(names)), f"duplicate ZIP names {out}")
    for item in manifest["loose_changes"]:
        out = Path(item["output"])
        check(out.is_file(), f"missing overlay output {out}")
        check(sha(out) == item["output_sha256"], f"overlay hash mismatch {out}")
        json.loads(out.read_text(encoding="utf-8"))

    def jar(name: str) -> zipfile.ZipFile:
        return zipfile.ZipFile(OUT / "jars" / name)

    with jar("createadditionallogistics-1.21.1-1.4.5.jar") as z:
        obj = json.loads(z.read("data/createadditionallogistics/data_maps/item/currency.json"))
        check("values" in obj and len(obj["values"]) == 6, "currency values")
        check(all("neoforge:conditions" in v and "neoforge:value" in v for v in obj["values"].values()), "currency per-value conditions")
        check("neoforge:conditions" not in obj, "currency root condition removed")

    with jar("create_compressed-2.2.0-neoforge-1.21.1.jar") as z:
        rose = json.loads(z.read("data/create_compressed/recipe/sandpaper_polishing/polished_rose_quartz_block.json"))
        dough = json.loads(z.read("data/create_compressed/recipe/mixing/dough_block.json"))
        check(rose["results"] == [{"id": "create_compressed:rose_quartz_polished_block"}], "rose result schema")
        check(dough["results"] == [{"id": "create_compressed:dough_block"}], "dough result schema")
        check(dough["ingredients"][1] == {"type": "neoforge:single", "amount": 1000, "fluid": "minecraft:water"}, "dough fluid schema")

    with jar("createdeco-2.1.3.jar") as z:
        placard = json.loads(z.read("data/createdeco/recipe/placard.json"))
        check(placard["ingredients"][1] == {"item": "minecraft:white_dye"}, "placard ingredient schema")

    with jar("cmpackagecouriers-neoforge-2.3.0.jar") as z:
        recipe = json.loads(z.read("data/cmpackagecouriers/recipe/deploying/jar_plane.json"))
        check(recipe["neoforge:conditions"] == [{"type": "neoforge:mod_loaded", "modid": "create_factory_logistics"}], "courier condition")

    with jar("railways-0.2.1+neoforge-mc1.21.1.jar") as z:
        optional = [n for n in z.namelist() if n.startswith("data/railways/loot_table/") and n.endswith(".json") and any(__import__("pathlib").Path(n).stem.startswith(p) for p in ("track_biomesoplenty_", "track_blue_skies_", "track_byg_", "track_create_dd_", "track_hexcasting_", "track_natures_spirit_", "track_quark_", "track_tfc_", "track_twilightforest_"))]
        check(len(optional) == 276, f"Railways optional count {len(optional)}")
        for n in optional:
            obj = json.loads(z.read(n))
            check("neoforge:conditions" in obj and "conditions" not in obj, f"Railways condition key {n}")
            check(len(obj["neoforge:conditions"]) == 1, f"Railways condition count {n}")
        byg = json.loads(z.read("data/railways/loot_table/blocks/track_byg_aspen.json"))
        check(byg["neoforge:conditions"][0]["type"] == "neoforge:or", "BYG OR condition")

    with jar("create_connected-1.3.2-mc1.21.1.jar") as z:
        dye = [n for n in z.namelist() if n.startswith("data/create_connected/loot_table/") and n.endswith(".json") and "dye_depot_" in __import__("pathlib").Path(n).stem]
        check(len(dye) == 16, f"Dye Depot loot count {len(dye)}")
        for n in dye:
            obj = json.loads(z.read(n))
            check(obj["neoforge:conditions"] == [{"type": "neoforge:mod_loaded", "modid": "dye_depot"}], f"Dye Depot condition {n}")
        # Existing optional tag entries remain explicitly required:false.
        for n in z.namelist():
            if "/tags/" in n and n.endswith(".json") and b"dye_depot" in z.read(n):
                obj = json.loads(z.read(n))
                for v in obj.get("values", []):
                    if isinstance(v, dict) and str(v.get("id", "")).startswith("create_connected:dye_depot_"):
                        check(v.get("required") is False, f"unguarded optional tag {n}")

    with jar("tracks-neoforge-1.21.1-1.0.1.jar") as z:
        affected = [n for n in z.namelist() if n.endswith(".json") and b"Tracks:" in z.read(n)]
        check(not affected, f"uppercase Tracks remains: {affected}")
        for n in z.namelist():
            if n.endswith(".json") and n.startswith("data/tracks/loot_table/"):
                json.loads(z.read(n))

    with jar("creategearsandtavern-1.1.6.jar") as z:
        tag = json.loads(z.read("data/create/tags/item/upright_on_belt.json"))
        tw = [v for v in tag["values"] if isinstance(v, dict) and v.get("id", "").startswith("kaleidoscope_twilight:")]
        check(len(tw) == 14 and all(v.get("required") is False for v in tw), "Kaleidoscope Twilight tag not fail-closed")

    with jar("biomespy-neoforge-1.21.1-1.3.3.jar") as z:
        names = z.namelist()
        check("data/biomespy/tags/worldgen/structure/uninit_safe.json" in names, "BiomeSpy normal path missing")
        check(not any("uninit_safe.json\u200e" == n for n in names), "BiomeSpy U+200E path remains")
        json.loads(z.read("data/biomespy/tags/worldgen/structure/uninit_safe.json"))

    with jar("DnT-ancient-city-overhaul-v2 [NeoForge].jar") as z:
        for n in ("data/minecraft/loot_table/chests/illager_mansion/library_chest.json", "data/minecraft/loot_table/chests/illager_mansion/secret_room.json"):
            obj = json.loads(z.read(n))
            raw = json.dumps(obj)
            check("nova_structures:illagers_bane" not in raw, f"invalid Nova option remains in {n}")
            check("nova_structures:loot_modifier" in raw, f"Nova modifier lost in {n}")

    with jar("irons_spellbooks-1.21.1-3.15.6.jar") as z:
        check("data/irons_spellbooks/loot_table/test/ring_gen_break_me.json" not in z.namelist(), "orphan Iron test table remains")

    # The source runtime must remain byte-for-byte unchanged for every guarded source.
    for item in manifest["jar_changes"]:
        src = Path(item["source"])
        check(sha(src) == item["source_sha256"], f"source JAR changed {src}")
    for item in manifest["loose_changes"]:
        src = Path(item["source"])
        check(sha(src) == item["source_sha256"], f"source overlay changed {src}")

    print("PASS: Attempt6 data/resource candidate static verification")
    print(f"  patched JARs: {len(manifest['jar_changes'])}; loose overlays: {len(manifest['loose_changes'])}")
    print("  Minecraft start: not performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
