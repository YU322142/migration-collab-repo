from __future__ import annotations

import copy
import math
import unittest

import nbtlib

import create_storage_object_ota as ota


MASK64 = (1 << 64) - 1


def signed_long(value: int) -> int:
    value &= MASK64
    return value - (1 << 64) if value >= (1 << 63) else value


def state(name: str, **properties: str) -> nbtlib.Compound:
    value = nbtlib.Compound({"Name": nbtlib.String(name)})
    if properties:
        value["Properties"] = nbtlib.Compound(
            {key: nbtlib.String(child) for key, child in properties.items()}
        )
    return value


def packed_padded(indices: list[int], bits: int) -> nbtlib.LongArray:
    values_per_long = 64 // bits
    longs = [0] * math.ceil(len(indices) / values_per_long)
    for index, value in enumerate(indices):
        long_index = index // values_per_long
        shift = (index % values_per_long) * bits
        longs[long_index] |= value << shift
    return nbtlib.LongArray([signed_long(value) for value in longs])


def packed_dense(indices: list[int], bits: int) -> nbtlib.LongArray:
    longs = [0] * math.ceil(len(indices) * bits / 64)
    mask = (1 << bits) - 1
    for index, value in enumerate(indices):
        value &= mask
        bit_index = index * bits
        long_index = bit_index // 64
        shift = bit_index % 64
        longs[long_index] |= (value << shift) & MASK64
        if shift + bits > 64:
            longs[long_index + 1] |= value >> (64 - shift)
    return nbtlib.LongArray([signed_long(value) for value in longs])


def chunk_with_states(palette: list[nbtlib.Compound], data: nbtlib.LongArray | None = None) -> nbtlib.File:
    block_states = nbtlib.Compound(
        {"palette": nbtlib.List[nbtlib.Compound](palette)}
    )
    if data is not None:
        block_states["data"] = data
    section = nbtlib.Compound({"Y": nbtlib.Byte(0), "block_states": block_states})
    return nbtlib.File(
        {
            "xPos": nbtlib.Int(0),
            "zPos": nbtlib.Int(0),
            "sections": nbtlib.List[nbtlib.Compound]([section]),
            "block_entities": nbtlib.List[nbtlib.Compound]([]),
        },
        gzipped=False,
        byteorder="big",
        root_name="",
    )


def member(
    *,
    identifier: str,
    content_path: str,
    content_schema: str,
    legacy_schema: str,
    target_max_capacity: int | None = None,
) -> ota.MemberSpec:
    value = {
        "dimension": "minecraft:overworld",
        "pos": [0, 0, 0],
        "block_entity_id": identifier,
        "region_path": "region/r.0.0.mca",
        "chunk": [0, 0],
        "stable_fields": {},
        "stable_absent": [],
        "expected_block_state": {
            "Name": identifier,
            "Properties": {},
            "property_match": "subset",
        },
        "content_path": content_path,
        "content_schema": content_schema,
        "legacy_schema": legacy_schema,
        "target_max_capacity": target_max_capacity,
    }
    return ota.normalize_member(value)


class BlockStateDecoderTests(unittest.TestCase):
    def test_single_palette(self) -> None:
        chunk = chunk_with_states([state("create:item_vault", axis="x")])
        self.assertEqual(
            ota.block_state_at(chunk, (15, 15, 15)),
            {"Name": "create:item_vault", "Properties": {"axis": "x"}},
        )

    def test_padded_palette_boundary(self) -> None:
        palette = [state(f"test:block_{index}") for index in range(17)]
        indices = [0] * 4096
        # With five bits there are 12 values per padded long.  Check the last
        # value in long zero and the first value in long one.
        indices[11] = 15
        indices[12] = 16
        chunk = chunk_with_states(palette, packed_padded(indices, 5))
        self.assertEqual(ota.block_state_at(chunk, (11, 0, 0))["Name"], "test:block_15")
        self.assertEqual(ota.block_state_at(chunk, (12, 0, 0))["Name"], "test:block_16")

    def test_dense_palette_crosses_long_boundary(self) -> None:
        palette = [state(f"test:block_{index}") for index in range(17)]
        indices = [0] * 4096
        # index 12 starts at bit 60 for five-bit dense packing and crosses from
        # one signed long into the next.
        indices[12] = 16
        chunk = chunk_with_states(palette, packed_dense(indices, 5))
        self.assertEqual(ota.block_state_at(chunk, (12, 0, 0))["Name"], "test:block_16")


class CompareAndSetTests(unittest.TestCase):
    def test_indexed_tank_path_roundtrip(self) -> None:
        spec = member(
            identifier="create:basin",
            content_path="InputTanks[0].TankContent",
            content_schema="neoforge_fluid_tank",
            legacy_schema=None,
            target_max_capacity=1000,
        )
        block_entity = nbtlib.Compound(
            {
                "InputTanks": nbtlib.List[nbtlib.Compound]([
                    nbtlib.Compound({"TankContent": nbtlib.Compound()})
                ])
            }
        )
        snapshot = copy.deepcopy(block_entity)
        payload = nbtlib.Compound(
            {
                "Fluid": nbtlib.Compound(
                    {"id": nbtlib.String("minecraft:lava"), "amount": nbtlib.Int(1000)}
                )
            }
        )
        self.assertEqual(ota.content_state(spec.content_schema, ota.dotted_get(block_entity, spec.content_path))[0], "empty")
        ota.apply_payload(block_entity, spec, payload)
        self.assertEqual(
            ota.plain(block_entity["InputTanks"][0]["TankContent"]["Fluid"]["amount"]),
            1000,
        )
        ota.restore_snapshot_fields(block_entity, spec, snapshot, ())
        self.assertEqual(ota.plain(block_entity["InputTanks"][0]["TankContent"]), {})

    def test_indexed_path_out_of_range_is_missing(self) -> None:
        value = nbtlib.Compound({"Tanks": nbtlib.List[nbtlib.Compound]([])})
        self.assertIs(ota.dotted_get(value, "Tanks[0].TankContent"), ota.MISSING)
        with self.assertRaises(ota.OtaError):
            ota.dotted_parent(value, "Tanks[0].TankContent")

    def test_dense_vault_conversion_preserves_live_items(self) -> None:
        spec = member(
            identifier="create:item_vault",
            content_path="Inventory",
            content_schema="neoforge_item_stack_handler",
            legacy_schema="create_fly_dense_item_list",
        )
        live_items = nbtlib.List[nbtlib.Compound](
            [
                nbtlib.Compound({"id": nbtlib.String("minecraft:diamond"), "count": nbtlib.Int(3)}),
                nbtlib.Compound({"id": nbtlib.String("minecraft:gold_ingot"), "count": nbtlib.Int(7)}),
            ]
        )
        block_entity = nbtlib.Compound({"Inventory": live_items})
        authoritative = nbtlib.Compound(
            {
                "Size": nbtlib.Int(20),
                "Items": nbtlib.List[nbtlib.Compound](
                    [nbtlib.Compound({"id": nbtlib.String("minecraft:dirt"), "count": nbtlib.Int(1), "Slot": nbtlib.Int(0)})]
                ),
            }
        )
        decision = ota.decide_member(spec, block_entity, authoritative)
        self.assertEqual(decision.action, "convert_legacy")
        self.assertEqual(ota.plain(decision.proposed_content["Size"]), 20)
        converted = decision.proposed_content["Items"]
        self.assertEqual([ota.plain(item["id"]) for item in converted], ["minecraft:diamond", "minecraft:gold_ingot"])
        self.assertEqual([ota.plain(item["Slot"]) for item in converted], [0, 1])

    def test_nonempty_target_is_never_overwritten(self) -> None:
        spec = member(
            identifier="create:item_vault",
            content_path="Inventory",
            content_schema="neoforge_item_stack_handler",
            legacy_schema="create_fly_dense_item_list",
        )
        live = nbtlib.Compound(
            {
                "Size": nbtlib.Int(20),
                "Items": nbtlib.List[nbtlib.Compound](
                    [nbtlib.Compound({"id": nbtlib.String("minecraft:diamond"), "count": nbtlib.Int(1), "Slot": nbtlib.Int(0)})]
                ),
            }
        )
        authoritative = copy.deepcopy(live)
        authoritative["Items"][0]["id"] = nbtlib.String("minecraft:dirt")
        decision = ota.decide_member(spec, nbtlib.Compound({"Inventory": live}), authoritative)
        self.assertEqual(decision.action, "conflict")
        self.assertIsNone(decision.proposed_content)

    def test_root_fluid_is_removed_and_rollback_restores_it(self) -> None:
        spec = member(
            identifier="create:fluid_tank",
            content_path="TankContent",
            content_schema="neoforge_fluid_tank",
            legacy_schema="create_fly_root_or_direct_fluid",
            target_max_capacity=8000,
        )
        block_entity = nbtlib.Compound(
            {
                "id": nbtlib.String("create:fluid_tank"),
                "Fluid": nbtlib.Compound(
                    {"id": nbtlib.String("minecraft:water"), "amount": nbtlib.Int(4000)}
                ),
            }
        )
        snapshot = copy.deepcopy(block_entity)
        decision = ota.decide_member(spec, block_entity, None)
        self.assertEqual(decision.action, "convert_legacy")
        self.assertEqual(decision.remove_paths, ("Fluid",))
        ota.apply_payload(block_entity, spec, decision.proposed_content, decision.remove_paths)
        self.assertNotIn("Fluid", block_entity)
        self.assertEqual(ota.plain(block_entity["TankContent"]["Fluid"]["amount"]), 4000)
        ota.restore_snapshot_fields(block_entity, spec, snapshot, decision.remove_paths)
        self.assertNotIn("TankContent", block_entity)
        self.assertEqual(ota.plain(block_entity["Fluid"]["amount"]), 4000)

    def test_root_and_target_fluid_conflict(self) -> None:
        spec = member(
            identifier="create:fluid_tank",
            content_path="TankContent",
            content_schema="neoforge_fluid_tank",
            legacy_schema="create_fly_root_or_direct_fluid",
            target_max_capacity=8000,
        )
        fluid = nbtlib.Compound(
            {"id": nbtlib.String("minecraft:water"), "amount": nbtlib.Int(1000)}
        )
        block_entity = nbtlib.Compound(
            {"Fluid": copy.deepcopy(fluid), "TankContent": nbtlib.Compound({"Fluid": copy.deepcopy(fluid)})}
        )
        decision = ota.decide_member(spec, block_entity, None)
        self.assertEqual(decision.action, "conflict")
        self.assertIn("both legacy root Fluid", decision.reason)


if __name__ == "__main__":
    unittest.main()
