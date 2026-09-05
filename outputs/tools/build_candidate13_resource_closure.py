#!/usr/bin/env python3
"""Build the Candidate13 client resource closure without mutating locked inputs.

The builder is deliberately fail-closed: every source artifact is pinned by SHA-256,
every expected JSON shape is asserted, and both ZIP outputs use fixed timestamps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile


WORKSPACE = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_OVERLAY = WORKSPACE / "outputs/projects/resource-error-overlay-1.21.1"
DEFAULT_TARGET_YUUSHYA = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate12-20260812"
    r"\client-mods\yuushya-1.21.0-neoforge-2.3.0.jar"
)
DEFAULT_SOURCE_YUUSHYA = Path(
    r"<INSTANCE_ROOT>\动静交映-1.4.2-BakaXL\instances\动静交映客户端"
    r"\.minecraft\mods\yuushya-1.21.11-fabric-2.3.1.jar"
)
DEFAULT_LOCAL_PACK = Path(
    r"<INSTANCE_ROOT>\动静交映-1.4.2-PCL2\.minecraft\versions\动静交映客户端"
    r"\resourcepacks\世界指定资源包喵.zip"
)
DEFAULT_OUTPUT_DIR = WORKSPACE / "outputs/candidate13-resource-closure-20260812"

EXPECTED_SHA256 = {
    "target_yuushya": "C410C51E1ECDD9D3FF55EB34B84D71DA761A8990EC0993A766C9BA40E8C360E8",
    "source_yuushya": "5680662C67323A994FFB45B5EF727B9802D16830E18D32F2E8F3D8454998A2BB",
    "local_pack": "BF88450FF0EED414657DC75CC1F0FD6689109A654DEEC8CF5306A13C3900CCCC",
}

OVERLAY_VERSION = "1.2.0+mc1.21.1-candidate13"

FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
MATERIALS = (
    "acacia", "bamboo", "birch", "black", "blue", "brown", "cherry",
    "crimson", "cyan", "dark_oak", "gray", "green", "jungle",
    "light_blue", "light_gray", "lime", "magenta", "mangrove", "oak",
    "orange", "pink", "purple", "red", "spruce", "warped", "white",
    "yellow",
)
FACINGS = {"east": 90, "north": None, "south": 180, "west": 270}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def require_sha(path: Path, expected: str, label: str) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"missing {label}: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{label} SHA-256 mismatch: {actual} != {expected}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def load_json(archive: zipfile.ZipFile, entry: str) -> object:
    return json.loads(archive.read(entry).decode("utf-8-sig"))


def write_tree_file(root: Path, relative: str, data: bytes) -> None:
    destination = root / Path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def patch_texture(model: object, slot: str, old: str, new: str, entry: str) -> bytes:
    if not isinstance(model, dict) or not isinstance(model.get("textures"), dict):
        raise RuntimeError(f"unexpected model shape: {entry}")
    textures = model["textures"]
    if textures.get(slot) != old:
        raise RuntimeError(f"unexpected texture {entry}#{slot}: {textures.get(slot)!r}")
    textures[slot] = new
    return canonical_json(model)


def audio_blockstate(kind: str, material: str) -> dict[str, object]:
    if kind == "audio":
        models = (
            f"yuushya:template/audio_a_{material}_blindwall",
            f"yuushya:template/audio_single_a_{material}_blindwall",
        )
    elif kind == "audio_large":
        models = (
            f"yuushya:template/audio_large_a_{material}_blindwall",
            f"yuushya:template/audio_large_covered_a_{material}_blindwall",
        )
    else:
        raise ValueError(kind)
    variants: dict[str, dict[str, object]] = {}
    for facing, rotation in FACINGS.items():
        for form, model in enumerate(models):
            value: dict[str, object] = {"model": model}
            if rotation is not None:
                value["y"] = rotation
            variants[f"facing={facing},form={form}"] = value
        # The inherited Yuushya template loader registers three values for two
        # visual forms (outer list size two -> FORM3). FORM3's third value has no
        # authored model in either 2.3.1 source or 2.3.0 target. Alias only that
        # impossible authored state to the documented default/full form 0.
        fallback = dict(variants[f"facing={facing},form=0"])
        variants[f"facing={facing},form=2"] = fallback
    return {"variants": variants}


def validate_original_audio_state(value: object, kind: str, material: str, entry: str) -> None:
    if value != {"variants": {
        key: val
        for key, val in audio_blockstate(kind, material)["variants"].items()
        if not key.endswith("form=2")
    }}:
        raise RuntimeError(f"unexpected authored audio blockstate: {entry}")


def build_overlay(
    project_root: Path,
    target_yuushya: Path,
    source_yuushya: Path,
    output_dir: Path,
) -> tuple[Path, list[dict[str, object]]]:
    source_resources = project_root / "src/main/resources"
    if not source_resources.is_dir():
        raise RuntimeError(f"overlay resources missing: {source_resources}")
    staged = output_dir / "staging/overlay"
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(source_resources, staged)
    metadata_path = staged / "META-INF/neoforge.mods.toml"
    metadata = metadata_path.read_text(encoding="utf-8")
    old_version = 'version = "1.1.0+mc1.21.1"'
    if metadata.count(old_version) != 1:
        raise RuntimeError("overlay metadata version source marker mismatch")
    metadata = metadata.replace(old_version, f'version = "{OVERLAY_VERSION}"')
    metadata_path.write_text(metadata, encoding="utf-8", newline="\n")
    transformations: list[dict[str, object]] = []

    with zipfile.ZipFile(target_yuushya) as target, zipfile.ZipFile(source_yuushya) as source:
        target_names = set(target.namelist())
        source_names = set(source.namelist())

        for kind in ("audio", "audio_large"):
            for material in MATERIALS:
                entry = f"assets/yuushya/blockstates/{kind}_a_{material}_blindwall.json"
                validate_original_audio_state(load_json(target, entry), kind, material, entry)
                validate_original_audio_state(load_json(source, entry), kind, material, entry)
                write_tree_file(staged, entry, canonical_json(audio_blockstate(kind, material)))
        transformations.append({
            "id": "yuushya_audio_form2_default_alias",
            "entries": 54,
            "variants_added": 216,
            "runtime_warnings_closed": 432,
            "method": "alias form=2 to authored form=0 for each facing",
            "confidence": "bounded_fallback",
        })

        flooring = "assets/yuushya/models/extra_building_material/flooring_water_half.json"
        expected_target_flooring = {
            "credit": "Yuushya",
            "textures": {"0": "yuushya:block/machine", "particle": "yuushya:block/machine"},
            "elements": [{
                "from": [-16, 0, 0], "to": [40, 1, 40],
                "faces": {
                    "north": {"uv": [0, 0, 16, 1], "texture": "#0"},
                    "east": {"uv": [0, 0, 16, 1], "texture": "#0"},
                    "south": {"uv": [0, 0, 16, 1], "texture": "#0"},
                    "west": {"uv": [0, 0, 16, 1], "texture": "#0"},
                    "up": {"uv": [0, 0, 16, 16], "texture": "#0"},
                    "down": {"uv": [0, 0, 16, 16], "texture": "#0"},
                },
            }],
        }
        if load_json(target, flooring) != expected_target_flooring:
            raise RuntimeError("unexpected target flooring_water_half model")
        source_flooring = source.read(flooring)
        source_flooring_json = json.loads(source_flooring.decode("utf-8-sig"))
        coords = source_flooring_json["elements"][0]
        if coords.get("from") != [-16, 0, 0] or coords.get("to") != [32, 1, 32]:
            raise RuntimeError("unexpected source flooring_water_half coordinates")
        write_tree_file(staged, flooring, source_flooring)
        transformations.append({
            "id": "yuushya_flooring_water_half_source_restore",
            "entries": 1,
            "method": "copy exact 2.3.1 source JSON; target coordinate 40 exceeds 1.21.1 max 32",
            "confidence": "high",
        })

        refrigerator = "assets/yuushya/models/extra_building_material/refrigerator_decorated_open.json"
        patched = patch_texture(
            load_json(target, refrigerator), "17", "block/black_concrete_",
            "yuushya:block/black_concrete_", refrigerator,
        )
        if "assets/yuushya/textures/block/black_concrete_.png" not in target_names:
            raise RuntimeError("refrigerator replacement texture missing")
        write_tree_file(staged, refrigerator, patched)
        transformations.append({
            "id": "yuushya_refrigerator_texture_namespace",
            "entries": 1,
            "warnings_closed": 4,
            "confidence": "high",
        })

        knife = "assets/yuushya/models/extra_building_material/knife_rest.json"
        patched = patch_texture(
            load_json(target, knife), "2", "block/dark_concrete",
            "yuushya:block/dark_concrete", knife,
        )
        if "assets/yuushya/textures/block/dark_concrete.png" not in target_names:
            raise RuntimeError("knife replacement texture missing")
        write_tree_file(staged, knife, patched)
        transformations.append({
            "id": "yuushya_knife_texture_namespace",
            "entries": 1,
            "warnings_closed": 5,
            "confidence": "high",
        })

        butterfly = "assets/yuushya/models/item/butterfly.json"
        butterfly_value = load_json(target, butterfly)
        patched = patch_texture(
            butterfly_value, "particle",
            "yuushya:0extra_building_material/preview/character_black_blur",
            "yuushya:block/azure/butterfly2_s_p", butterfly,
        )
        if "assets/yuushya/textures/block/azure/butterfly2_s_p.png" not in target_names:
            raise RuntimeError("butterfly main/particle texture missing")
        write_tree_file(staged, butterfly, patched)
        transformations.append({
            "id": "yuushya_butterfly_particle_fallback",
            "entries": 1,
            "warnings_closed": 1,
            "confidence": "high",
        })

        sign_parent = "assets/yuushya/models/extra_building_material/sign/sign_14.json"
        sign_value = load_json(target, sign_parent)
        patched = patch_texture(
            sign_value, "particle",
            "yuushya:0extra_building_material/preview/poster/poster_large",
            "yuushya:0extra_building_material/preview/randomized_poster/1", sign_parent,
        )
        if "assets/yuushya/textures/0extra_building_material/preview/randomized_poster/1.png" not in target_names:
            raise RuntimeError("sign particle fallback texture missing")
        write_tree_file(staged, sign_parent, patched)
        transformations.append({
            "id": "yuushya_sign14_particle_fallback",
            "entries": 1,
            "warnings_closed": 13,
            "method": "replace only inherited missing particle slot; child models retain their 1..5 visible poster textures",
            "confidence": "high",
        })

        blank = "assets/yuushya/models/extra_building_material/blank.json"
        blank_value = load_json(target, blank)
        if blank_value.get("elements"):
            raise RuntimeError("Yuushya blank model unexpectedly has visible elements")
        blank_bytes = canonical_json(blank_value)
        hitboxes = (
            "assets/yuushya/models/extra_building_material/easel_hitbox.json",
            "assets/yuushya/models/extra_building_material/easel_hitbox_rotated.json",
            "assets/yuushya/models/extra_building_material/roof/roof/tile1_lp_none_hitbox.json",
            "assets/yuushya/models/extra_building_material/tanghulu_bunch_hitbox.json",
        )
        for entry in hitboxes:
            value = load_json(target, entry)
            faces = [face for element in value.get("elements", []) for face in element.get("faces", {}).values()]
            if not faces or not all(face == {} for face in faces):
                raise RuntimeError(f"hitbox model no longer consists only of empty faces: {entry}")
            write_tree_file(staged, entry, blank_bytes)
        transformations.append({
            "id": "yuushya_collision_only_client_models_blank",
            "entries": len(hitboxes),
            "method": "replace all-empty-face client model with Yuushya's authored invisible blank model",
            "confidence": "high",
        })

        for entry in (flooring, refrigerator, knife, butterfly, sign_parent, blank, *hitboxes):
            if entry not in target_names:
                raise RuntimeError(f"target entry missing: {entry}")
        if flooring not in source_names:
            raise RuntimeError(f"source entry missing: {flooring}")

    jar_path = output_dir / f"migration-resource-overlay-{OVERLAY_VERSION}.jar"
    build_deterministic_zip(staged, jar_path)
    return jar_path, transformations


def build_deterministic_zip(root: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(destination)


def build_local_pack(source_pack: Path, output_dir: Path) -> tuple[Path, dict[str, object]]:
    destination = output_dir / "世界指定资源包喵-mc1.21.1-candidate13.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    changed: list[str] = []
    with zipfile.ZipFile(source_pack) as source, zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True
    ) as derived:
        names = source.namelist()
        if names.count("pack.mcmeta") != 1:
            raise RuntimeError("local pack must contain exactly one root pack.mcmeta")
        state_entry = "assets/minecraft/blockstates/creaking_heart.json"
        if names.count(state_entry) != 1:
            raise RuntimeError("local pack creaking_heart blockstate entry mismatch")
        for info in source.infolist():
            data = source.read(info)
            if info.filename == "pack.mcmeta":
                value = json.loads(data.decode("utf-8-sig"))
                pack = value.get("pack")
                if not isinstance(pack, dict):
                    raise RuntimeError("local pack pack.mcmeta lacks pack object")
                if pack.get("pack_format") not in (None, 34):
                    raise RuntimeError("local pack has unexpected pack_format")
                pack["pack_format"] = 34
                data = canonical_json(value)
                changed.append(info.filename)
            elif info.filename == state_entry:
                value = json.loads(data.decode("utf-8-sig"))
                variants = value.get("variants")
                if not isinstance(variants, dict):
                    raise RuntimeError("creaking_heart variants missing")
                active = sorted(k for k in variants if k.startswith("active="))
                current = sorted(k for k in variants if "creaking_heart_state=" in k)
                if len(active) != 6 or len(current) != 9 or len(variants) != 15:
                    raise RuntimeError("unexpected creaking_heart multi-version state set")
                for key in active:
                    del variants[key]
                data = canonical_json(value)
                changed.append(info.filename)
            cloned = zipfile.ZipInfo(info.filename, FIXED_ZIP_TIME)
            cloned.compress_type = zipfile.ZIP_DEFLATED
            cloned.external_attr = info.external_attr or (0o100644 << 16)
            derived.writestr(cloned, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(destination)
    if sorted(changed) != sorted(["pack.mcmeta", "assets/minecraft/blockstates/creaking_heart.json"]):
        raise RuntimeError(f"unexpected local pack changed entries: {changed}")
    return destination, {
        "id": "local_pack_1_21_1_compatibility",
        "changed_entries": sorted(changed),
        "creaking_active_variants_removed": 6,
        "current_creaking_heart_state_variants_retained": 9,
        "pack_format": 34,
        "confidence": "high",
    }


def zip_inventory(path: Path) -> dict[str, object]:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "entries": len(infos),
            "uncompressed_bytes": sum(info.file_size for info in infos),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=DEFAULT_SOURCE_OVERLAY)
    parser.add_argument("--target-yuushya", type=Path, default=DEFAULT_TARGET_YUUSHYA)
    parser.add_argument("--source-yuushya", type=Path, default=DEFAULT_SOURCE_YUUSHYA)
    parser.add_argument("--local-pack", type=Path, default=DEFAULT_LOCAL_PACK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs = {
        "target_yuushya": require_sha(args.target_yuushya, EXPECTED_SHA256["target_yuushya"], "target Yuushya"),
        "source_yuushya": require_sha(args.source_yuushya, EXPECTED_SHA256["source_yuushya"], "source Yuushya"),
        "local_pack": require_sha(args.local_pack, EXPECTED_SHA256["local_pack"], "local resource pack"),
    }
    jar_path, transformations = build_overlay(
        args.project_root.resolve(), args.target_yuushya.resolve(),
        args.source_yuushya.resolve(), output_dir,
    )
    pack_path, pack_transform = build_local_pack(args.local_pack.resolve(), output_dir)
    report = {
        "schema": 1,
        "status": "PASS",
        "category": "candidate13_resource_closure_build",
        "inputs": inputs,
        "outputs": {
            "overlay": zip_inventory(jar_path),
            "local_resource_pack": zip_inventory(pack_path),
        },
        "transformations": transformations + [pack_transform],
        "locked_candidate12_modified": False,
        "original_jars_modified": False,
        "user_resource_pack_modified": False,
    }
    report_path = output_dir / "build-report.json"
    report_path.write_bytes(canonical_json(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
