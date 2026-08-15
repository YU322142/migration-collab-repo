from __future__ import annotations

import argparse
import json
from pathlib import Path


FACINGS = {
    "east": 90,
    "north": None,
    "south": 180,
    "west": 270,
}


def ender_dragon_tea_variants() -> dict[str, dict[str, object]]:
    variants: dict[str, dict[str, object]] = {}
    for cup_count in range(1, 7):
        rendered_cups = min(cup_count, 4)
        for facing, rotation in FACINGS.items():
            for tea_count in range(1, 7):
                rendered_tea = min(tea_count, rendered_cups)
                value: dict[str, object] = {
                    "model": (
                        "kaleidoscope_end:block/teacup/ender_dragon_tea/"
                        f"count{rendered_cups}_{rendered_tea}"
                    )
                }
                if rotation is not None:
                    value["y"] = rotation
                key = (
                    f"cup_count={cup_count},facing={facing},"
                    f"tea_count={tea_count}"
                )
                variants[key] = value
    return variants


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def generate(project_root: Path) -> list[Path]:
    resources = project_root / "src" / "main" / "resources"
    outputs = [
        resources
        / "assets"
        / "kaleidoscope_end"
        / "blockstates"
        / "ender_dragon_tea.json"
    ]
    write_json(outputs[0], {"variants": ender_dragon_tea_variants()})

    blowgun_model = {
        "parent": "item/handheld",
        "textures": {"layer0": "kaleidoscope_nether:item/blowgun"},
    }
    model_dir = (
        resources / "assets" / "kaleidoscope_nether" / "models" / "item"
    )
    for index in range(3):
        path = model_dir / f"blowgun_pulling_{index}.json"
        write_json(path, blowgun_model)
        outputs.append(path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic client render fixes for the resource overlay."
    )
    parser.add_argument("project_root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for path in generate(args.project_root.resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
