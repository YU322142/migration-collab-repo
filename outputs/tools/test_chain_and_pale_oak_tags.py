"""Static contract for chain mining and Create pale-oak stripping tags."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TAG_ROOT = ROOT / "pack" / "server-kubejs" / "data" / "minecraft" / "tags" / "block"


def read(relative: str) -> dict:
    path = TAG_ROOT / relative
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_chain_mining_tags() -> None:
    assert "minecraft:chain" in read("mineable/pickaxe.json")["values"]
    assert "minecraft:chain" in read("needs_stone_tool.json")["values"]


def test_pale_oak_log_family_tags() -> None:
    expected = {
        "minecraft:pale_oak_log",
        "minecraft:pale_oak_wood",
        "minecraft:stripped_pale_oak_log",
        "minecraft:stripped_pale_oak_wood",
    }
    assert expected <= set(read("logs.json")["values"])
    assert expected <= set(read("logs_that_burn.json")["values"])


if __name__ == "__main__":
    test_chain_mining_tags()
    test_pale_oak_log_family_tags()
    print("2/2 PASS")
