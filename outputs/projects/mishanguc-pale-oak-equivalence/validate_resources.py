import argparse
import json
import zipfile
from pathlib import Path


def resource_parts(value: str, default_namespace: str) -> tuple[str, str]:
    if ":" in value:
        return tuple(value.split(":", 1))
    return default_namespace, value


def walk_models(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "model" and isinstance(child, str):
                yield child
            else:
                yield from walk_models(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_models(child)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--target-unpacked", required=True, type=Path)
    parser.add_argument("--source-unpacked", required=True, type=Path)
    parser.add_argument("--content-backport", required=True, type=Path)
    args = parser.parse_args()

    mishang_roots = [args.resources, args.target_unpacked]
    with zipfile.ZipFile(args.content_backport) as archive:
        backport_entries = set(archive.namelist())

    def model_exists(reference: str, default_namespace: str = "minecraft") -> bool:
        namespace, path = resource_parts(reference, default_namespace)
        relative = Path("assets") / namespace / "models" / f"{path}.json"
        if any((root / relative).is_file() for root in mishang_roots):
            return True
        return relative.as_posix() in backport_entries

    def texture_exists(reference: str) -> bool:
        namespace, path = resource_parts(reference, "minecraft")
        relative = Path("assets") / namespace / "textures" / f"{path}.png"
        if any((root / relative).is_file() for root in mishang_roots):
            return True
        return relative.as_posix() in backport_entries

    asset_root = args.resources / "assets" / "mishanguc"
    blockstates = sorted((asset_root / "blockstates").glob("*.json"))
    item_models = sorted((asset_root / "models" / "item").glob("*.json"))
    block_models = sorted((asset_root / "models" / "block").glob("*.json"))
    recipes = sorted((args.resources / "data" / "mishanguc" / "recipe").glob("*.json"))

    source_states = {
        path.name
        for path in (args.source_unpacked / "assets" / "mishanguc" / "blockstates").glob("*pale_oak*.json")
    }
    generated_states = {path.name for path in blockstates}
    failures = []
    if len(blockstates) != 37 or generated_states != source_states:
        failures.append(
            f"blockstates mismatch: generated={len(blockstates)} source={len(source_states)} "
            f"missing={sorted(source_states - generated_states)} extra={sorted(generated_states - source_states)}"
        )
    if len(item_models) != 17:
        failures.append(f"expected 17 item models, found {len(item_models)}")
    if len(recipes) != 16:
        failures.append(f"expected 16 recipes, found {len(recipes)}")

    for state_path in blockstates:
        document = json.loads(state_path.read_text(encoding="utf-8"))
        for reference in walk_models(document):
            if not model_exists(reference, "mishanguc"):
                failures.append(f"missing blockstate model {reference} referenced by {state_path.name}")

    for model_path in block_models + item_models:
        document = json.loads(model_path.read_text(encoding="utf-8"))
        parent = document.get("parent")
        if isinstance(parent, str):
            parent_namespace, parent_path = resource_parts(parent, "minecraft")
            if (parent_namespace == "mishanguc" or "pale_oak" in parent_path) and not model_exists(parent):
                failures.append(f"missing parent model {parent} referenced by {model_path.name}")
        textures = document.get("textures", {})
        if isinstance(textures, dict):
            for reference in textures.values():
                if not isinstance(reference, str) or reference.startswith("#"):
                    continue
                namespace, path = resource_parts(reference, "minecraft")
                if namespace == "mishanguc" or "pale_oak" in path:
                    if not texture_exists(reference):
                        failures.append(f"missing texture {reference} referenced by {model_path.name}")

    for recipe_path in recipes:
        document = json.loads(recipe_path.read_text(encoding="utf-8"))
        ingredient = document.get("ingredient")
        if isinstance(ingredient, str):
            failures.append(f"1.21.11 string ingredient remains in {recipe_path.name}")
        key = document.get("key", {})
        if isinstance(key, dict):
            for symbol, value in key.items():
                if isinstance(value, str):
                    failures.append(f"1.21.11 string key {symbol} remains in {recipe_path.name}")

    source_data = args.source_unpacked / "data"
    expected_tags = {}
    for source_tag in source_data.rglob("*.json"):
        if "tags" not in source_tag.parts:
            continue
        document = json.loads(source_tag.read_text(encoding="utf-8"))
        values = [
            value
            for value in document.get("values", [])
            if "pale_oak" in (value if isinstance(value, str) else str(value.get("id", "")))
        ]
        if values:
            expected_tags[source_tag.relative_to(source_data).as_posix()] = values
    generated_tags = {
        path.relative_to(args.resources / "data").as_posix(): json.loads(path.read_text(encoding="utf-8"))
        for path in (args.resources / "data").rglob("*.json")
        if "tags" in path.parts
    }
    if set(generated_tags) != set(expected_tags):
        failures.append(
            "tag file mismatch: "
            f"missing={sorted(set(expected_tags) - set(generated_tags))} "
            f"extra={sorted(set(generated_tags) - set(expected_tags))}"
        )
    for relative, expected_values in expected_tags.items():
        generated = generated_tags.get(relative)
        if generated is None:
            continue
        if generated.get("replace") is not False or generated.get("values") != expected_values:
            failures.append(f"tag projection mismatch in {relative}")

    if failures:
        raise SystemExit("RESOURCE_VALIDATION=FAIL\n" + "\n".join(failures))
    print(
        "RESOURCE_VALIDATION=PASS "
        f"blockstates={len(blockstates)} blockModels={len(block_models)} "
        f"itemModels={len(item_models)} recipes={len(recipes)} tags={len(expected_tags)}"
    )


if __name__ == "__main__":
    main()
