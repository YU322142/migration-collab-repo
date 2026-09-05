from __future__ import annotations

import gzip
import hashlib
import io
import json
import unittest
import os
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from nbt import nbt

import convert_world_nbt as converter


def compound(**values):
    result = nbt.TAG_Compound()
    for key, value in values.items():
        result[key] = value
    return result


def tag_list(tag_type, *values):
    result = nbt.TAG_List(type=tag_type)
    result.extend(values)
    return result


def int_array(*values):
    result = nbt.TAG_Int_Array()
    result.value = list(values)
    result.update_fmt(len(result.value))
    return result


def item(identifier, count=1):
    return compound(id=nbt.TAG_String(identifier), count=nbt.TAG_Int(count))


def generated_assembly_lore(step=1, total=15):
    ingredients = (
        "create:cogwheel",
        "create:large_cogwheel",
        "#c:nuggets/iron",
    )

    def description(index):
        return compound(
            translate=nbt.TAG_String("create.recipe.assembly.deploying_item"),
            **{
                "with": tag_list(
                    nbt.TAG_Compound,
                    compound(ingredient=nbt.TAG_String(ingredients[index % 3])),
                )
            },
        )

    previews = [description(step + offset) for offset in range(min(3, total - step))]
    values = [
        compound(**{"": nbt.TAG_String("")}),
        compound(
            italic=nbt.TAG_Byte(0),
            translate=nbt.TAG_String("create.recipe.sequenced_assembly"),
            color=nbt.TAG_String("gray"),
        ),
        compound(
            italic=nbt.TAG_Byte(0),
            translate=nbt.TAG_String("create.recipe.assembly.progress"),
            **{
                "with": tag_list(
                    nbt.TAG_Byte,
                    nbt.TAG_Byte(step),
                    nbt.TAG_Byte(total),
                )
            },
            color=nbt.TAG_String("dark_gray"),
        ),
        compound(
            italic=nbt.TAG_Byte(0),
            translate=nbt.TAG_String("create.recipe.assembly.next"),
            **{"with": tag_list(nbt.TAG_Compound, previews[0])},
            color=nbt.TAG_String("aqua"),
        ),
    ]
    for description_value in previews[1:]:
        values.append(
            compound(
                italic=nbt.TAG_Byte(0),
                extra=tag_list(nbt.TAG_Compound, description_value),
                text=nbt.TAG_String("-> "),
                color=nbt.TAG_String("dark_aqua"),
            )
        )
    return tag_list(nbt.TAG_Compound, *values)


def entity(identifier):
    return compound(
        id=nbt.TAG_String(identifier),
        UUID=int_array(1, 2, 3, 4),
        Pos=tag_list(nbt.TAG_Double, nbt.TAG_Double(1), nbt.TAG_Double(2), nbt.TAG_Double(3)),
    )


def write_entity_region(path, identifier="minecraft:oak_boat"):
    chunk = nbt.NBTFile()
    chunk["Entities"] = tag_list(nbt.TAG_Compound, entity(identifier))
    raw = converter.serialize_chunk(chunk)
    compressed = zlib.compress(raw, 6)
    record = struct.pack(">I", len(compressed) + 1) + b"\x02" + compressed
    sectors = (len(record) + 4095) // 4096
    data = bytearray(8192)
    data[0:3] = (2).to_bytes(3, "big")
    data[3] = sectors
    data.extend(record)
    data.extend(b"\x00" * (sectors * 4096 - len(record)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def first_region_entity(path):
    _, _, _, compression, payload = next(converter.read_slots(path))
    chunk = nbt.NBTFile(
        buffer=io.BytesIO(converter.decode(payload, compression))
    )
    return chunk["Entities"][0]


def plain_tag(value):
    if isinstance(value, nbt.TAG_Compound):
        return {key: plain_tag(child) for key, child in value.items()}
    if isinstance(value, nbt.TAG_List):
        return [plain_tag(child) for child in value]
    if isinstance(value, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)):
        return [int(child) for child in value.value]
    return value.value


def target_trial_spawner_template_configs(jar, template):
    entry = f"data/minecraft/structure/{template}"
    with zipfile.ZipFile(jar) as archive:
        root = nbt.NBTFile(buffer=io.BytesIO(gzip.decompress(archive.read(entry))))
    trial_states = {
        index
        for index, state in enumerate(root["palette"])
        if str(state["Name"]) == "minecraft:trial_spawner"
    }
    matches = [
        block["nbt"]
        for block in root["blocks"]
        if int(block["state"].value) in trial_states and "nbt" in block
    ]
    if len(matches) != 1:
        raise AssertionError(f"{entry} has {len(matches)} trial spawner payloads")
    return matches[0]["normal_config"], matches[0]["ominous_config"]


class TextConversionTests(unittest.TestCase):
    def test_plain_and_existing_json_text(self):
        self.assertEqual(converter.canonical_component_text(nbt.TAG_String("Grumm")), '"Grumm"')
        self.assertEqual(converter.canonical_component_text(nbt.TAG_String("\u547d\u540d\u724cJHHG")), '"\u547d\u540d\u724cJHHG"')
        self.assertEqual(converter.canonical_component_text(nbt.TAG_String('{"text":"Home"}')), '{"text":"Home"}')
        self.assertEqual(converter.canonical_component_text(nbt.TAG_String('"Home"')), '"Home"')
        self.assertEqual(converter.canonical_component_text(nbt.TAG_String("")), '""')

    def test_sign_messages_are_json_encoded(self):
        block = compound(
            id=nbt.TAG_String("minecraft:sign"),
            x=nbt.TAG_Int(1),
            y=nbt.TAG_Int(64),
            z=nbt.TAG_Int(2),
            front_text=compound(messages=tag_list(
                nbt.TAG_String,
                nbt.TAG_String("Home"),
                nbt.TAG_String('{"text":"kept"}'),
                nbt.TAG_String(""),
                nbt.TAG_String("123"),
            )),
        )
        audit = {}
        self.assertTrue(converter.convert_sign_text(block, audit))
        self.assertEqual([str(value) for value in block["front_text"]["messages"]], [
            '"Home"', '{"text":"kept"}', '""', '"123"',
        ])
        self.assertEqual(len(audit["signs"]), 1)


class EntityConversionTests(unittest.TestCase):
    def setUp(self):
        self.audit = converter.new_audit(Path("fixture"), 100)

    def test_all_split_boat_forms(self):
        expected = {
            "minecraft:cherry_boat": ("minecraft:boat", "cherry"),
            "minecraft:jungle_chest_boat": ("minecraft:chest_boat", "jungle"),
            "minecraft:bamboo_raft": ("minecraft:boat", "bamboo"),
            "minecraft:bamboo_chest_raft": ("minecraft:chest_boat", "bamboo"),
            "minecraft:pale_oak_boat": ("minecraft:boat", "backport:pale_oak"),
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(converter.split_boat_type(source), target)

    def _source_gantry_entity(self):
        result = entity("create:gantry_contraption")
        # Create 1.21.11 persists the oriented contraption facing on the
        # entity, and the target converter now fail-closes when it is absent.
        result["InitialOrientation"] = nbt.TAG_String("south")
        glue_box = tag_list(
            nbt.TAG_Double,
            *(nbt.TAG_Double(value) for value in (0, 1, 2, 3, 4, 5)),
        )
        result["Contraption"] = compound(
            BoundsFront=tag_list(
                nbt.TAG_Double,
                *(nbt.TAG_Double(value) for value in (-1, 0, -1, 2, 3, 2)),
            ),
            Superglue=tag_list(nbt.TAG_List, glue_box),
            Seats=tag_list(nbt.TAG_Int_Array),
            Interactors=tag_list(nbt.TAG_Int_Array, int_array(1, 2, 3)),
            SubContraptions=compound(),
            Anchor=int_array(0, 0, 0),
            Actors=tag_list(nbt.TAG_Compound),
            CapturedMultiblocks=tag_list(nbt.TAG_Compound),
            DisabledActors=tag_list(nbt.TAG_Compound),
            Blocks=compound(Palette=compound(), BlockList=tag_list(nbt.TAG_Compound)),
            Type=nbt.TAG_String("create:gantry"),
            Facing=nbt.TAG_String("south"),
            Stalled=nbt.TAG_Byte(0),
            BottomlessSupply=nbt.TAG_Byte(0),
            items=tag_list(
                nbt.TAG_Compound,
                compound(
                    pos=int_array(0, 0, 9),
                    storage=compound(
                        type=nbt.TAG_String("create:chest"),
                        value=compound(size=nbt.TAG_Int(27), items=compound()),
                    ),
                ),
            ),
            fluids=tag_list(
                nbt.TAG_Compound,
                compound(
                    pos=int_array(0, 1, 9),
                    storage=compound(
                        type=nbt.TAG_String("create:fluid_tank"),
                        capacity=nbt.TAG_Int(1_296_000),
                        fluid=compound(),
                    ),
                ),
            ),
        )
        return result

    def test_nested_create_gantry_contraption_is_transactionally_converted(self):
        gantry = self._source_gantry_entity()

        self.assertTrue(converter.convert_entity(gantry, 100, self.audit))
        contraption = gantry["Contraption"]
        self.assertTrue(all(isinstance(value, nbt.TAG_Float) for value in contraption["BoundsFront"]))
        self.assertEqual(int(contraption["Facing"].value), 3)
        self.assertEqual(set(contraption["Interactors"][0].keys()), {"Pos"})
        self.assertEqual(set(contraption["Superglue"][0].keys()), {"From", "To"})
        self.assertIsInstance(contraption["SubContraptions"], nbt.TAG_List)
        self.assertEqual(
            [int(contraption["items"][0]["pos"][axis].value) for axis in ("X", "Y", "Z")],
            [0, 0, 9],
        )
        self.assertEqual(
            [int(contraption["fluids"][0]["pos"][axis].value) for axis in ("X", "Y", "Z")],
            [0, 1, 9],
        )
        self.assertEqual(int(contraption["fluids"][0]["storage"]["capacity"].value), 16_000)
        self.assertEqual(len(self.audit["contraption_entities"]), 1)
        self.assertEqual(self.audit["unsupported_contraptions"], [])

        first = converter.comparable_tag(gantry)
        self.assertFalse(converter.convert_entity(gantry, 100, self.audit))
        self.assertEqual(converter.comparable_tag(gantry), first)
        self.assertEqual(len(self.audit["contraption_entities"]), 1)

    def test_malformed_nested_create_contraption_is_fail_closed(self):
        gantry = self._source_gantry_entity()
        gantry["Contraption"]["BoundsFront"].tags.pop()
        before = converter.comparable_tag(gantry)

        self.assertFalse(converter.convert_entity(gantry, 100, self.audit))
        self.assertEqual(converter.comparable_tag(gantry), before)
        self.assertEqual(len(self.audit["unsupported_contraptions"]), 1)
        self.assertEqual(self.audit["contraption_entities"], [])

    def test_boat_and_passenger_convert_recursively(self):
        boat = entity("minecraft:cherry_boat")
        passenger = entity("minecraft:ocelot")
        passenger["CustomName"] = nbt.TAG_String("Grumm")
        boat["Passengers"] = tag_list(nbt.TAG_Compound, passenger)

        self.assertTrue(converter.convert_entity(boat, 100, self.audit))
        self.assertEqual(str(boat["id"]), "minecraft:boat")
        self.assertEqual(str(boat["Type"]), "cherry")
        self.assertEqual(str(boat["Passengers"][0]["CustomName"]), '"Grumm"')

    def test_modern_equipment_maps_to_legacy_slots_and_body(self):
        mob = entity("minecraft:zombie")
        mob["equipment"] = compound(
            mainhand=item("minecraft:egg"),
            body=item("minecraft:blue_harness"),
        )
        mob["drop_chances"] = compound(
            mainhand=nbt.TAG_Float(2.0),
            body=nbt.TAG_Float(2.0),
        )

        self.assertTrue(converter.convert_entity(mob, 100, self.audit))
        self.assertNotIn("equipment", mob)
        self.assertEqual(str(mob["HandItems"][0]["id"]), "minecraft:egg")
        self.assertEqual(float(mob["HandDropChances"][0].value), 2.0)
        self.assertEqual(str(mob["body_armor_item"]["id"]), "minecraft:blue_harness")
        self.assertEqual(float(mob["body_armor_drop_chance"].value), 2.0)

    def test_unknown_saddle_schema_is_fail_closed(self):
        mob = entity("example:mount")
        mob["equipment"] = compound(saddle=item("minecraft:saddle"))
        self.assertFalse(converter.convert_entity(mob, 100, self.audit))
        self.assertIn("equipment", mob)
        self.assertEqual(len(self.audit["unsupported_equipment"]), 1)

    def test_villager_offer_component_shapes_are_normalized(self):
        villager = entity("minecraft:villager")
        offer = compound(
            buy=item("minecraft:emerald", 16),
            buyB=item("minecraft:book"),
            sell=item("minecraft:enchanted_book"),
            maxUses=nbt.TAG_Int(12),
        )
        offer["buy"]["components"] = compound(
            **{
                "minecraft:dyed_color": nbt.TAG_Int(1908001),
                "minecraft:enchantments": compound(
                    **{"minecraft:sharpness": nbt.TAG_Int(3)}
                ),
            }
        )
        offer["sell"]["components"] = compound(
            **{
                "minecraft:stored_enchantments": compound(
                    **{"minecraft:fortune": nbt.TAG_Int(2)}
                )
            }
        )
        villager["Offers"] = compound(
            Recipes=tag_list(nbt.TAG_Compound, offer),
        )

        self.assertTrue(converter.convert_entity(villager, 100, self.audit))
        buy_components = villager["Offers"]["Recipes"][0]["buy"]["components"]
        sell_components = villager["Offers"]["Recipes"][0]["sell"]["components"]
        self.assertEqual(
            set(buy_components),
            {"minecraft:dyed_color", "minecraft:enchantments"},
        )
        self.assertEqual(
            set(sell_components),
            {"minecraft:stored_enchantments"},
        )
        self.assertEqual(int(buy_components["minecraft:dyed_color"]["rgb"].value), 1908001)
        self.assertEqual(
            int(buy_components["minecraft:enchantments"]["levels"]["minecraft:sharpness"].value),
            3,
        )
        self.assertEqual(
            int(sell_components["minecraft:stored_enchantments"]["levels"]["minecraft:fortune"].value),
            2,
        )
        self.assertEqual(len(self.audit["item_component_schema_aliases"]), 3)

    def test_malformed_villager_offer_component_is_fail_closed(self):
        villager = entity("minecraft:villager")
        offer = compound(sell=item("minecraft:enchanted_book"))
        offer["sell"]["components"] = compound(
            **{
                "minecraft:stored_enchantments": compound(
                    **{"minecraft:sharpness": nbt.TAG_String("three")}
                )
            }
        )
        villager["Offers"] = compound(Recipes=tag_list(nbt.TAG_Compound, offer))
        before = converter.comparable_tag(villager)

        self.assertFalse(converter.convert_entity(villager, 100, self.audit))
        self.assertEqual(converter.comparable_tag(villager), before)
        self.assertEqual(len(self.audit["unsupported_entity_items"]), 1)

    def test_modern_anger_uses_world_game_time_and_preserves_target(self):
        mob = entity("minecraft:wolf")
        mob["anger_end_time"] = nbt.TAG_Long(175)
        mob["angry_at"] = int_array(9, 8, 7, 6)
        self.assertTrue(converter.convert_entity(mob, 100, self.audit))
        self.assertEqual(int(mob["AngerTime"].value), 75)
        self.assertEqual(list(mob["AngryAt"].value), [9, 8, 7, 6])
        self.assertNotIn("anger_end_time", mob)
        self.assertNotIn("angry_at", mob)

        old = entity("minecraft:wolf")
        old["AngerTime"] = nbt.TAG_Int(12)
        old["AngryAt"] = int_array(4, 3, 2, 1)
        old["anger_end_time"] = nbt.TAG_Long(999)
        old["angry_at"] = int_array(1, 2, 3, 4)
        converter.convert_entity(old, 100, self.audit)
        self.assertEqual(int(old["AngerTime"].value), 12)
        self.assertEqual(list(old["AngryAt"].value), [4, 3, 2, 1])

    def test_only_proven_default_attributes_are_consumed(self):
        sheep = entity("minecraft:sheep")
        sheep["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(id=nbt.TAG_String("minecraft:camera_distance"), base=nbt.TAG_Double(4.0)),
            compound(id=nbt.TAG_String("minecraft:tempt_range"), base=nbt.TAG_Double(10.0)),
            compound(
                id=nbt.TAG_String("minecraft:waypoint_transmit_range"),
                base=nbt.TAG_Double(0.0),
                modifiers=tag_list(
                    nbt.TAG_Compound,
                    compound(
                        id=nbt.TAG_String("minecraft:effect.waypoint_transmit_range_hide"),
                        amount=nbt.TAG_Double(-1.0),
                        operation=nbt.TAG_String("add_multiplied_total"),
                    ),
                ),
            ),
        )
        self.assertTrue(converter.convert_entity(sheep, 100, self.audit))
        self.assertEqual(len(sheep["attributes"]), 0)
        self.assertEqual(len(self.audit["consumed_default_attributes"]), 3)

        happy_ghast = entity("minecraft:happy_ghast")
        happy_ghast["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(id=nbt.TAG_String("minecraft:camera_distance"), base=nbt.TAG_Double(8.0)),
            compound(id=nbt.TAG_String("minecraft:tempt_range"), base=nbt.TAG_Double(16.0)),
        )
        self.assertTrue(converter.convert_entity(happy_ghast, 100, self.audit))
        self.assertEqual(len(happy_ghast["attributes"]), 0)

        modified = entity("minecraft:cow")
        modified["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                id=nbt.TAG_String("minecraft:tempt_range"),
                base=nbt.TAG_Double(10.0),
                modifiers=tag_list(
                    nbt.TAG_Compound,
                    compound(
                        id=nbt.TAG_String("example:range_bonus"),
                        amount=nbt.TAG_Double(2.0),
                        operation=nbt.TAG_String("add_value"),
                    ),
                ),
            ),
        )
        self.assertFalse(converter.convert_entity(modified, 100, self.audit))
        self.assertEqual(len(modified["attributes"]), 1)
        self.assertEqual(len(self.audit["unsupported_attributes"]), 1)

    def test_1_21_11_attribute_aliases_preserve_villager_values_and_modifiers(self):
        villager = entity("minecraft:villager")
        villager["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(id=nbt.TAG_String("minecraft:movement_speed"), base=nbt.TAG_Double(0.5)),
            compound(
                id=nbt.TAG_String("minecraft:follow_range"),
                base=nbt.TAG_Double(16.0),
                modifiers=tag_list(
                    nbt.TAG_Compound,
                    compound(
                        id=nbt.TAG_String("minecraft:random_spawn_bonus"),
                        amount=nbt.TAG_Double(0.06351944832424627),
                        operation=nbt.TAG_String("add_multiplied_base"),
                    ),
                ),
            ),
        )

        self.assertTrue(converter.convert_attributes(villager, self.audit))
        self.assertEqual(
            [str(attribute["id"]) for attribute in villager["attributes"]],
            ["minecraft:generic.movement_speed", "minecraft:generic.follow_range"],
        )
        self.assertEqual(float(villager["attributes"][0]["base"].value), 0.5)
        modifier = villager["attributes"][1]["modifiers"][0]
        self.assertEqual(str(modifier["id"]), "minecraft:random_spawn_bonus")
        self.assertEqual(str(modifier["operation"]), "add_multiplied_base")
        self.assertEqual(float(modifier["amount"].value), 0.06351944832424627)
        self.assertEqual(len(self.audit["attribute_aliases"]), 2)
        self.assertEqual(self.audit["unsupported_attributes"], [])

    def test_legacy_uppercase_attributes_are_migrated_without_losing_modifier_values(self):
        villager = entity("minecraft:villager")
        modifier = compound(
            Name=nbt.TAG_String("Random spawn bonus"),
            Amount=nbt.TAG_Double(-0.0375),
            Operation=nbt.TAG_Int(1),
            UUID=int_array(1, 2, 3, 4),
        )
        villager["Attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                Name=nbt.TAG_String("minecraft:generic.follow_range"),
                Base=nbt.TAG_Double(48.0),
                Modifiers=tag_list(nbt.TAG_Compound, modifier),
            ),
            compound(
                Name=nbt.TAG_String("minecraft:generic.movement_speed"),
                Base=nbt.TAG_Double(0.5),
            ),
        )

        self.assertTrue(converter.convert_attributes(villager, self.audit))
        self.assertNotIn("Attributes", villager)
        self.assertEqual(
            [str(attribute["id"]) for attribute in villager["attributes"]],
            ["minecraft:generic.follow_range", "minecraft:generic.movement_speed"],
        )
        converted_modifier = villager["attributes"][0]["modifiers"][0]
        self.assertEqual(str(converted_modifier["id"]), "minecraft:random_spawn_bonus")
        self.assertEqual(str(converted_modifier["operation"]), "add_multiplied_base")
        self.assertEqual(float(converted_modifier["amount"].value), -0.0375)
        self.assertEqual(len(self.audit["legacy_attribute_containers"]), 1)
        self.assertEqual(self.audit["unsupported_attributes"], [])

    def test_malformed_legacy_attributes_are_fail_closed(self):
        villager = entity("minecraft:villager")
        villager["Attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                Name=nbt.TAG_String("minecraft:generic.follow_range"),
                Base=nbt.TAG_Double(48.0),
                Modifiers=tag_list(
                    nbt.TAG_Compound,
                    compound(
                        Name=nbt.TAG_String("future bonus"),
                        Amount=nbt.TAG_Double(1.0),
                        Operation=nbt.TAG_Int(1),
                    ),
                ),
            ),
        )
        before = converter.comparable_tag(villager)

        self.assertFalse(converter.convert_attributes(villager, self.audit))
        self.assertEqual(converter.comparable_tag(villager), before)
        self.assertNotIn("attributes", villager)
        self.assertEqual(len(self.audit["unsupported_attributes"]), 1)

    def test_legacy_duplicate_random_spawn_modifiers_are_folded_by_sum(self):
        golem = entity("minecraft:iron_golem")
        golem["Attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                Name=nbt.TAG_String("minecraft:generic.follow_range"),
                Base=nbt.TAG_Double(16.0),
                Modifiers=tag_list(
                    nbt.TAG_Compound,
                    compound(
                        Name=nbt.TAG_String("Random spawn bonus"),
                        Amount=nbt.TAG_Double(0.04),
                        Operation=nbt.TAG_Int(1),
                        UUID=int_array(1, 2, 3, 4),
                    ),
                    compound(
                        Name=nbt.TAG_String("Random spawn bonus"),
                        Amount=nbt.TAG_Double(0.01),
                        Operation=nbt.TAG_Int(1),
                        UUID=int_array(5, 6, 7, 8),
                    ),
                ),
            ),
        )
        self.assertTrue(converter.convert_attributes(golem, self.audit))
        modifier = golem["attributes"][0]["modifiers"][0]
        self.assertAlmostEqual(float(modifier["amount"].value), 0.05)
        self.assertEqual(len(self.audit["legacy_attribute_modifier_merges"]), 1)

    def test_legacy_player_attribute_names_use_player_registry_aliases(self):
        player = entity("minecraft:player")
        player["Attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                Name=nbt.TAG_String("minecraft:player.block_interaction_range"),
                Base=nbt.TAG_Double(5.0),
            ),
            compound(
                Name=nbt.TAG_String("minecraft:player.entity_interaction_range"),
                Base=nbt.TAG_Double(3.0),
            ),
        )
        self.assertTrue(converter.convert_attributes(player, self.audit))
        self.assertEqual(
            [str(attribute["id"]) for attribute in player["attributes"]],
            [
                "minecraft:player.block_interaction_range",
                "minecraft:player.entity_interaction_range",
            ],
        )

    def test_player_only_attributes_use_1_21_1_player_registry_and_repair_old_generic_ids(self):
        player = entity("minecraft:player")
        ids = (
            "block_break_speed",
            "block_interaction_range",
            "entity_interaction_range",
            "mining_efficiency",
            "sneaking_speed",
            "submerged_mining_speed",
            "sweeping_damage_ratio",
        )
        player["attributes"] = tag_list(
            nbt.TAG_Compound,
            *(
                compound(
                    id=nbt.TAG_String(f"minecraft:{name}"),
                    base=nbt.TAG_Double(1.0),
                )
                for name in ids[:4]
            ),
            *(
                compound(
                    id=nbt.TAG_String(f"minecraft:generic.{name}"),
                    base=nbt.TAG_Double(1.0),
                )
                for name in ids[4:]
            ),
        )

        self.assertTrue(converter.convert_attributes(player, self.audit))
        self.assertEqual(
            [str(attribute["id"]) for attribute in player["attributes"]],
            [f"minecraft:player.{name}" for name in ids],
        )
        self.assertEqual(len(self.audit["attribute_aliases"]), len(ids))
        self.assertEqual(self.audit["unsupported_attributes"], [])

    def test_malformed_1_21_11_attribute_aliases_are_fail_closed(self):
        cases = {
            "attributes_not_list": compound(value=nbt.TAG_Int(1)),
            "entry_not_compound": tag_list(nbt.TAG_String, nbt.TAG_String("bad")),
            "missing_id": tag_list(nbt.TAG_Compound, compound(base=nbt.TAG_Double(0.5))),
            "non_numeric_base": tag_list(
                nbt.TAG_Compound,
                compound(id=nbt.TAG_String("minecraft:movement_speed"), base=nbt.TAG_String("0.5")),
            ),
            "non_finite_base": tag_list(
                nbt.TAG_Compound,
                compound(id=nbt.TAG_String("minecraft:movement_speed"), base=nbt.TAG_Double(float("nan"))),
            ),
            "malformed_modifier": tag_list(
                nbt.TAG_Compound,
                compound(
                    id=nbt.TAG_String("minecraft:follow_range"),
                    base=nbt.TAG_Double(16.0),
                    modifiers=tag_list(
                        nbt.TAG_Compound,
                        compound(
                            id=nbt.TAG_String("minecraft:random_spawn_bonus"),
                            amount=nbt.TAG_Double(0.1),
                            operation=nbt.TAG_String("multiply_magic"),
                        ),
                    ),
                ),
            ),
        }
        for name, attributes in cases.items():
            with self.subTest(name=name):
                villager = entity("minecraft:villager")
                villager["attributes"] = attributes
                before = converter.comparable_tag(villager["attributes"])
                audit = converter.new_audit(Path("fixture"), 100)

                self.assertFalse(converter.convert_attributes(villager, audit))
                self.assertEqual(converter.comparable_tag(villager["attributes"]), before)
                self.assertEqual(len(audit["unsupported_attributes"]), 1)
                self.assertEqual(audit["attribute_aliases"], [])

    def test_waypoint_attributes_and_modifiers_are_retained_with_declared_runtime(self):
        audit = converter.new_audit(
            Path("fixture"),
            100,
            runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
        )
        player = entity("minecraft:player")
        player["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                id=nbt.TAG_String("minecraft:waypoint_transmit_range"),
                base=nbt.TAG_Double(60_000_000.0),
                modifiers=tag_list(
                    nbt.TAG_Compound,
                    compound(
                        id=nbt.TAG_String("example:range_scale"),
                        amount=nbt.TAG_Double(-0.25),
                        operation=nbt.TAG_String("add_multiplied_total"),
                    ),
                ),
            ),
            compound(
                id=nbt.TAG_String("minecraft:waypoint_receive_range"),
                base=nbt.TAG_Double(60_000_000.0),
            ),
        )
        before = converter.comparable_tag(player["attributes"])

        self.assertFalse(converter.convert_attributes(player, audit))
        self.assertEqual(converter.comparable_tag(player["attributes"]), before)
        self.assertEqual(audit["unsupported_attributes"], [])
        self.assertEqual(len(audit["retained_compatibility_attributes"]), 2)
        self.assertEqual(
            audit["retained_compatibility_attributes"][0]["modifiers"][0]["id"],
            "example:range_scale",
        )

    def test_positive_waypoint_receive_range_requires_declared_runtime(self):
        player = entity("minecraft:player")
        player["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(
                id=nbt.TAG_String("minecraft:waypoint_receive_range"),
                base=nbt.TAG_Double(60_000_000.0),
            ),
        )
        self.assertFalse(converter.convert_attributes(player, self.audit))
        self.assertEqual(len(player["attributes"]), 1)
        self.assertEqual(
            self.audit["unsupported_attributes"][0]["attributes"][0]["id"],
            "minecraft:waypoint_receive_range",
        )

    def test_malformed_waypoint_modifiers_are_fail_closed(self):
        valid = lambda identifier="example:bonus", amount=1.0, operation="add_value": compound(
            id=nbt.TAG_String(identifier),
            amount=nbt.TAG_Double(amount),
            operation=nbt.TAG_String(operation),
        )
        cases = {
            "not_list": compound(value=nbt.TAG_Int(1)),
            "invalid_id": tag_list(nbt.TAG_Compound, valid("Invalid ID")),
            "non_finite": tag_list(nbt.TAG_Compound, valid(amount=float("nan"))),
            "invalid_operation": tag_list(nbt.TAG_Compound, valid(operation="multiply_magic")),
            "duplicate_id": tag_list(
                nbt.TAG_Compound,
                valid("example:duplicate"),
                valid("example:duplicate", amount=2.0),
            ),
        }
        for name, modifiers in cases.items():
            with self.subTest(name=name):
                audit = converter.new_audit(
                    Path("fixture"),
                    100,
                    runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
                )
                mob = entity("minecraft:cow")
                waypoint = compound(
                    id=nbt.TAG_String("minecraft:waypoint_transmit_range"),
                    base=nbt.TAG_Double(1.0),
                )
                waypoint["modifiers"] = modifiers
                mob["attributes"] = tag_list(nbt.TAG_Compound, waypoint)
                before = converter.comparable_tag(mob["attributes"])
                self.assertFalse(converter.convert_attributes(mob, audit))
                self.assertEqual(converter.comparable_tag(mob["attributes"]), before)
                self.assertEqual(len(audit["unsupported_attributes"]), 1)
                self.assertEqual(audit["retained_compatibility_attributes"], [])

    def test_nautilus_equipment_leash_and_passenger_are_converted(self):
        mob = entity("minecraft:nautilus")
        mob["Owner"] = int_array(11, 12, 13, 14)
        mob["home_pos"] = int_array(5, 60, 5)
        mob["home_radius"] = nbt.TAG_Int(32)
        mob["leash"] = int_array(-226, 63, -37)
        mob["equipment"] = compound(
            saddle=item("minecraft:saddle"),
            body=item("minecraft:copper_nautilus_armor"),
        )
        mob["drop_chances"] = compound(saddle=nbt.TAG_Float(2.0), body=nbt.TAG_Float(2.0))
        passenger = entity("minecraft:drowned")
        passenger["attributes"] = tag_list(
            nbt.TAG_Compound,
            compound(id=nbt.TAG_String("minecraft:movement_speed"), base=nbt.TAG_Double(0.23)),
        )
        mob["Passengers"] = tag_list(nbt.TAG_Compound, passenger)

        self.assertTrue(converter.convert_entity(mob, 100, self.audit))
        self.assertEqual(str(mob["id"]), "minecraft:nautilus")
        self.assertNotIn("equipment", mob)
        self.assertEqual(str(mob["SaddleItem"]["id"]), "minecraft:saddle")
        self.assertEqual(str(mob["body_armor_item"]["id"]), "minecraft:copper_nautilus_armor")
        self.assertEqual(float(mob["body_armor_drop_chance"].value), 2.0)
        self.assertNotIn("leash", mob)
        self.assertEqual([int(mob["Leash"][key].value) for key in ("X", "Y", "Z")], [-226, 63, -37])
        self.assertEqual(list(mob["Owner"].value), [11, 12, 13, 14])
        self.assertEqual(list(mob["home_pos"].value), [5, 60, 5])
        self.assertEqual(str(mob["Passengers"][0]["attributes"][0]["id"]), "minecraft:generic.movement_speed")
        self.assertEqual(self.audit["unsupported_entities"], [])
        self.assertEqual(self.audit["unsupported_leashes"], [])

    def test_passenger_equipment_components_are_converted_before_slot_mapping(self):
        mount = entity("minecraft:zombie_nautilus")
        drowned = entity("minecraft:drowned")
        trident = item("minecraft:trident")
        trident["components"] = compound(
            **{
                "minecraft:custom_name": nbt.TAG_String("Jockey trident"),
                "minecraft:enchantments": compound(**{"minecraft:impaling": nbt.TAG_Int(1)}),
            }
        )
        drowned["equipment"] = compound(mainhand=trident)
        mount["Passengers"] = tag_list(nbt.TAG_Compound, drowned)

        self.assertTrue(converter.convert_entity(mount, 100, self.audit))
        converted = mount["Passengers"][0]["HandItems"][0]
        self.assertEqual(str(converted["components"]["minecraft:custom_name"]), '"Jockey trident"')
        self.assertEqual(
            int(converted["components"]["minecraft:enchantments"]["levels"]["minecraft:impaling"].value),
            1,
        )
        self.assertEqual(self.audit["unsupported_entity_items"], [])

    def test_entity_item_tooltip_display_maps_to_legacy_banner_hide(self):
        frame = entity("minecraft:item_frame")
        banner = item("minecraft:white_banner")
        banner["components"] = compound(
            **{
                "minecraft:banner_patterns": tag_list(
                    nbt.TAG_Compound,
                    compound(pattern=nbt.TAG_String("minecraft:flower"), color=nbt.TAG_String("red")),
                ),
                "minecraft:item_name": compound(translate=nbt.TAG_String("block.minecraft.white_banner")),
                "minecraft:tooltip_display": compound(
                    hidden_components=tag_list(nbt.TAG_String, nbt.TAG_String("minecraft:banner_patterns")),
                ),
            }
        )
        frame["Item"] = banner

        self.assertTrue(converter.convert_entity(frame, 100, self.audit))
        components = frame["Item"]["components"]
        self.assertNotIn("minecraft:tooltip_display", components)
        self.assertIn("minecraft:hide_additional_tooltip", components)
        self.assertEqual(len(components["minecraft:hide_additional_tooltip"]), 0)
        self.assertEqual(str(components["minecraft:item_name"]), '{"translate":"block.minecraft.white_banner"}')
        self.assertFalse(converter.convert_entity(frame, 100, self.audit))

    def test_unknown_entity_item_component_blocks_without_deleting_equipment(self):
        mob = entity("minecraft:zombie")
        future = item("minecraft:iron_sword")
        future["components"] = compound(**{"example:future": compound(value=nbt.TAG_Int(1))})
        mob["equipment"] = compound(mainhand=future)

        self.assertFalse(converter.convert_entity(mob, 100, self.audit))
        self.assertIn("equipment", mob)
        self.assertNotIn("HandItems", mob)
        self.assertEqual(len(self.audit["unsupported_entity_items"]), 1)

    def test_create_package_contents_are_traversed(self):
        package = entity("create:package")
        outer = item("create:cardboard_package_10x8")
        nested = item("minecraft:paper")
        nested["components"] = compound(**{"minecraft:custom_name": nbt.TAG_String("Manifest")})
        outer["components"] = compound(
            **{
                "create:package_address": nbt.TAG_String("Depot"),
                "create:package_contents": tag_list(
                    nbt.TAG_Compound,
                    compound(slot=nbt.TAG_Int(0), item=nested),
                ),
            }
        )
        package["Package"] = outer

        self.assertTrue(converter.convert_entity(package, 100, self.audit))
        converted = package["Package"]["components"]["create:package_contents"][0]["item"]
        self.assertEqual(str(converted["components"]["minecraft:custom_name"]), '"Manifest"')
        self.assertEqual(self.audit["unsupported_entity_items"], [])

    def test_unrepresentable_selective_tooltip_hide_is_fail_closed(self):
        frame = entity("minecraft:item_frame")
        stack = item("minecraft:enchanted_book")
        stack["components"] = compound(
            **{
                "minecraft:tooltip_display": compound(
                    hidden_components=tag_list(nbt.TAG_String, nbt.TAG_String("minecraft:stored_enchantments")),
                ),
            }
        )
        frame["Item"] = stack

        self.assertFalse(converter.convert_entity(frame, 100, self.audit))
        self.assertIn("minecraft:tooltip_display", frame["Item"]["components"])
        self.assertEqual(len(self.audit["unsupported_entity_items"]), 1)

    def test_unknown_or_conflicting_leash_is_fail_closed(self):
        malformed = entity("minecraft:nautilus")
        malformed["leash"] = nbt.TAG_String("future")
        self.assertFalse(converter.convert_leash(malformed, self.audit))
        self.assertIn("leash", malformed)

        conflict = entity("minecraft:nautilus")
        conflict["leash"] = int_array(1, 2, 3)
        conflict["Leash"] = compound(X=nbt.TAG_Int(9), Y=nbt.TAG_Int(8), Z=nbt.TAG_Int(7))
        self.assertFalse(converter.convert_leash(conflict, self.audit))
        self.assertIn("leash", conflict)
        self.assertEqual(len(self.audit["unsupported_leashes"]), 2)

    def test_modern_block_attached_anchor_maps_and_is_idempotent(self):
        frame = entity("minecraft:item_frame")
        frame["block_pos"] = int_array(-6, 64, 9)

        self.assertTrue(converter.convert_entity(frame, 100, self.audit))
        self.assertEqual(
            [int(frame[key].value) for key in ("TileX", "TileY", "TileZ")],
            [-6, 64, 9],
        )
        self.assertNotIn("block_pos", frame)
        self.assertEqual(len(self.audit["block_positions"]), 1)
        self.assertFalse(converter.convert_entity(frame, 100, self.audit))
        self.assertEqual(len(self.audit["block_positions"]), 1)

    def test_immersive_graffiti_anchor_uses_hanging_entity_schema(self):
        graffiti = entity("immersive_paintings:graffiti")
        graffiti["block_pos"] = int_array(12, 70, -4)

        self.assertTrue(converter.convert_entity(graffiti, 100, self.audit))
        self.assertEqual(
            [int(graffiti[key].value) for key in ("TileX", "TileY", "TileZ")],
            [12, 70, -4],
        )
        self.assertNotIn("block_pos", graffiti)

    def test_block_attached_anchor_malformed_or_unknown_is_fail_closed(self):
        malformed = entity("minecraft:painting")
        malformed["block_pos"] = tag_list(nbt.TAG_Int, nbt.TAG_Int(1), nbt.TAG_Int(2))
        self.assertFalse(converter.convert_entity(malformed, 100, self.audit))
        self.assertIn("block_pos", malformed)
        self.assertEqual(len(self.audit["unsupported_entities"]), 1)

        unknown = entity("example:block_attached")
        unknown["block_pos"] = int_array(1, 2, 3)
        self.assertFalse(converter.convert_entity(unknown, 100, self.audit))
        self.assertIn("block_pos", unknown)
        self.assertEqual(len(self.audit["unsupported_entities"]), 2)

    def test_create_block_entity_id_and_schematicannon_state_aliases(self):
        kinetic = compound(
            id=nbt.TAG_String("create:bracketed_kinetic"),
            x=nbt.TAG_Int(1), y=nbt.TAG_Int(64), z=nbt.TAG_Int(2),
        )
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            x=nbt.TAG_Int(3), y=nbt.TAG_Int(64), z=nbt.TAG_Int(4),
            State=nbt.TAG_String("stopped"),
            Inventory=tag_list(
                nbt.TAG_Compound,
                compound(), compound(), compound(), compound(), compound(),
            ),
        )
        self.assertTrue(converter.convert_block_entity(kinetic, self.audit))
        self.assertEqual(str(kinetic["id"]), "create:simple_kinetic")
        self.assertTrue(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(str(cannon["State"]), "STOPPED")
        self.assertEqual(len(self.audit["block_entity_id_aliases"]), 1)
        self.assertEqual(len(self.audit["block_entity_state_aliases"]), 1)
        self.assertFalse(converter.convert_block_entity(kinetic, self.audit))
        self.assertFalse(converter.convert_block_entity(cannon, self.audit))

    def test_all_trial_spawner_registry_pairs_match_official_target_templates(self):
        outputs = Path(__file__).resolve().parents[1]
        target_jar = (
            outputs
            / "tmp"
            / "client-gate-candidate10"
            / ".minecraft"
            / "versions"
            / "1.21.1"
            / "1.21.1.jar"
        )
        if not target_jar.exists():
            target_jar = Path(
                r"<AUDIT_ROOT>\mechanomania-matched-client-20260813"
            ) / "versions" / "1.21.1" / "1.21.1.jar"
        if not target_jar.exists():
            self.skipTest("audited Minecraft 1.21.1 fixture JAR is not available")
        self.assertEqual(
            hashlib.sha256(target_jar.read_bytes()).hexdigest().upper(),
            "499F6897D1837516680F3114072D8106E11C9ADCD933FE5CF051B551089B0C99",
        )

        source_root = (
            outputs
            / "tmp"
            / "mc2111-intermediary"
            / "data"
            / "minecraft"
            / "trial_spawner"
        )
        source_files = sorted(source_root.rglob("*.json"), key=lambda path: path.as_posix())
        if not source_files:
            self.skipTest(
                "private Minecraft 1.21.11 trial-spawner fixture is not committed"
            )
        source_hash = hashlib.sha256()
        for path in source_files:
            source_hash.update(path.relative_to(source_root).as_posix().encode("utf-8"))
            source_hash.update(b"\0")
            source_hash.update(path.read_bytes())
            source_hash.update(b"\0")
        self.assertEqual(len(source_files), 28)
        self.assertEqual(
            source_hash.hexdigest().upper(),
            "DCA82016E2B5C733269C05D2350866ED97E95DF8054BF9D3173B89355C84F456",
        )

        codec_defaults = {
            "spawn_range": 4,
            "total_mobs": 6.0,
            "simultaneous_mobs": 2.0,
            "total_mobs_added_per_player": 2.0,
            "simultaneous_mobs_added_per_player": 1.0,
            "ticks_between_spawn": 40,
            "spawn_potentials": [],
            "loot_tables_to_eject": [
                {
                    "data": "minecraft:spawners/trial_chamber/consumables",
                    "weight": 1,
                },
                {"data": "minecraft:spawners/trial_chamber/key", "weight": 1},
            ],
            "items_to_drop_when_ominous": (
                "minecraft:spawners/trial_chamber/items_to_drop_when_ominous"
            ),
        }

        def resolved(config):
            result = dict(codec_defaults)
            result.update(config)
            return result

        expected_source_files = set()
        for index, (base_identifier, spec) in enumerate(
            converter.TRIAL_SPAWNER_VARIANTS.items()
        ):
            with self.subTest(base_identifier=base_identifier):
                source_path = base_identifier.removeprefix("minecraft:")
                expected_source_files.update(
                    {f"{source_path}/normal.json", f"{source_path}/ominous.json"}
                )
                block = compound(
                    id=nbt.TAG_String("minecraft:trial_spawner"),
                    x=nbt.TAG_Int(100 + index),
                    y=nbt.TAG_Int(-20),
                    z=nbt.TAG_Int(-100 - index),
                    normal_config=nbt.TAG_String(f"{base_identifier}/normal"),
                    ominous_config=nbt.TAG_String(f"{base_identifier}/ominous"),
                    spawn_data=compound(
                        entity=compound(id=nbt.TAG_String("minecraft:pig"))
                    ),
                )
                spawn_data_before = converter.comparable_tag(block["spawn_data"])
                self.assertTrue(converter.convert_block_entity(block, self.audit))
                expected_normal, expected_ominous = target_trial_spawner_template_configs(
                    target_jar, spec["target_template"]
                )
                self.assertEqual(
                    converter.comparable_tag(block["normal_config"]),
                    converter.comparable_tag(expected_normal),
                )
                self.assertEqual(
                    converter.comparable_tag(block["ominous_config"]),
                    converter.comparable_tag(expected_ominous),
                )
                self.assertEqual(
                    converter.comparable_tag(block["spawn_data"]), spawn_data_before
                )

                source_normal = json.loads(
                    (source_root / f"{source_path}/normal.json").read_text(
                        encoding="utf-8"
                    )
                )
                source_ominous = json.loads(
                    (source_root / f"{source_path}/ominous.json").read_text(
                        encoding="utf-8"
                    )
                )
                target_normal = plain_tag(expected_normal)
                target_ominous = dict(target_normal)
                target_ominous.update(plain_tag(expected_ominous))
                self.assertEqual(resolved(source_normal), resolved(target_normal))
                self.assertEqual(resolved(source_ominous), resolved(target_ominous))

                after = converter.comparable_tag(block)
                self.assertFalse(converter.convert_block_entity(block, self.audit))
                self.assertEqual(converter.comparable_tag(block), after)

        self.assertEqual(
            {path.relative_to(source_root).as_posix() for path in source_files},
            expected_source_files,
        )
        self.assertEqual(len(self.audit["trial_spawner_config_conversions"]), 14)
        self.assertEqual(self.audit["unsupported_block_entities"], [])

    def test_trial_spawner_unknown_mismatched_and_malformed_pairs_fail_closed(self):
        husk_normal, husk_ominous = converter.build_trial_spawner_target_configs(
            "minecraft:trial_chamber/melee/husk"
        )
        malformed_inline_normal = converter.clone_tag(husk_normal)
        malformed_inline_normal["future_field"] = nbt.TAG_Int(1)
        cases = {
            "unknown": compound(
                normal_config=nbt.TAG_String("example:trial_chamber/future/normal"),
                ominous_config=nbt.TAG_String("example:trial_chamber/future/ominous"),
            ),
            "mismatched": compound(
                normal_config=nbt.TAG_String(
                    "minecraft:trial_chamber/melee/husk/normal"
                ),
                ominous_config=nbt.TAG_String(
                    "minecraft:trial_chamber/small_melee/silverfish/ominous"
                ),
            ),
            "missing_ominous": compound(
                normal_config=nbt.TAG_String(
                    "minecraft:trial_chamber/melee/husk/normal"
                )
            ),
            "mixed_source_target": compound(
                normal_config=nbt.TAG_String(
                    "minecraft:trial_chamber/melee/husk/normal"
                ),
                ominous_config=husk_ominous,
            ),
            "noncanonical_inline": compound(
                normal_config=malformed_inline_normal,
                ominous_config=husk_ominous,
            ),
        }
        for name, fields in cases.items():
            with self.subTest(name=name):
                block = compound(
                    id=nbt.TAG_String("minecraft:trial_spawner"),
                    x=nbt.TAG_Int(1),
                    y=nbt.TAG_Int(2),
                    z=nbt.TAG_Int(3),
                )
                for key, value in fields.items():
                    block[key] = converter.clone_tag(value)
                before = converter.comparable_tag(block)
                audit = converter.new_audit(Path("fixture"), 100)

                self.assertFalse(converter.convert_block_entity(block, audit))
                self.assertEqual(converter.comparable_tag(block), before)
                self.assertEqual(len(audit["unsupported_block_entities"]), 1)
                self.assertEqual(audit["trial_spawner_config_conversions"], [])

    def test_create_basin_direction_enums_are_uppercased_idempotently(self):
        basin = compound(
            id=nbt.TAG_String("create:basin"),
            x=nbt.TAG_Int(27281), y=nbt.TAG_Int(74), z=nbt.TAG_Int(-12881),
            PreferredSpoutput=nbt.TAG_String("east"),
            DisabledSpoutput=tag_list(
                nbt.TAG_String,
                nbt.TAG_String("west"),
                nbt.TAG_String("NORTH"),
            ),
        )

        self.assertTrue(converter.convert_block_entity(basin, self.audit))
        self.assertEqual(str(basin["PreferredSpoutput"]), "EAST")
        self.assertEqual(
            [str(value) for value in basin["DisabledSpoutput"]],
            ["WEST", "NORTH"],
        )
        self.assertEqual(len(self.audit["basin_direction_conversions"]), 1)
        after = converter.comparable_tag(basin)
        self.assertFalse(converter.convert_block_entity(basin, self.audit))
        self.assertEqual(converter.comparable_tag(basin), after)

    def test_create_basin_unknown_direction_is_fail_closed(self):
        basin = compound(
            id=nbt.TAG_String("create:basin"),
            PreferredSpoutput=nbt.TAG_String("west"),
            DisabledSpoutput=tag_list(nbt.TAG_String, nbt.TAG_String("sideways")),
        )
        before = converter.comparable_tag(basin)

        self.assertFalse(converter.convert_block_entity(basin, self.audit))
        self.assertEqual(converter.comparable_tag(basin), before)
        self.assertIn("unknown direction", self.audit["unsupported_block_entities"][0]["reason"])

    def test_blaze_forger_source_inventory_expands_internal_result_slots(self):
        stored = item("minecraft:enchanted_book")
        stored["Slot"] = nbt.TAG_Byte(1)
        forger = compound(
            id=nbt.TAG_String("create_enchantment_industry:blaze_forger"),
            x=nbt.TAG_Int(27319), y=nbt.TAG_Int(72), z=nbt.TAG_Int(-12892),
            Inventory=compound(
                Size=nbt.TAG_Int(4),
                Items=tag_list(nbt.TAG_Compound, stored),
                Cost=nbt.TAG_Int(7),
                Mode=nbt.TAG_Int(1),
                Conflicting=nbt.TAG_Byte(0),
                OverCap=nbt.TAG_Byte(1),
            ),
        )

        self.assertTrue(converter.convert_block_entity(forger, self.audit))
        self.assertEqual(int(forger["Inventory"]["Size"].value), 6)
        self.assertNotIn("Mode", forger["Inventory"])
        self.assertEqual(int(forger["Inventory"]["Operation"].value), 1)
        self.assertEqual(int(forger["ForgingMode"].value), 1)
        self.assertEqual(int(forger["Inventory"]["Items"][0]["Slot"].value), 1)
        self.assertEqual(str(forger["Inventory"]["Items"][0]["id"]), "minecraft:enchanted_book")
        record = self.audit["blaze_forger_inventory_conversions"][0]
        self.assertEqual(record["preserved_slots"], [1])
        self.assertEqual(record["derived_result_slots"], [4, 5])
        after = converter.comparable_tag(forger)
        self.assertFalse(converter.convert_block_entity(forger, self.audit))
        self.assertEqual(converter.comparable_tag(forger), after)

    def test_blaze_forger_source_result_slot_is_fail_closed(self):
        invalid = item("minecraft:enchanted_book")
        invalid["Slot"] = nbt.TAG_Byte(4)
        forger = compound(
            id=nbt.TAG_String("create_enchantment_industry:blaze_forger"),
            Inventory=compound(
                Size=nbt.TAG_Int(4),
                Items=tag_list(nbt.TAG_Compound, invalid),
                Cost=nbt.TAG_Int(0),
                Mode=nbt.TAG_Int(0),
                Conflicting=nbt.TAG_Byte(0),
                OverCap=nbt.TAG_Byte(0),
            ),
        )
        before = converter.comparable_tag(forger)

        self.assertFalse(converter.convert_block_entity(forger, self.audit))
        self.assertEqual(converter.comparable_tag(forger), before)
        self.assertIn("outside 0..3", self.audit["unsupported_block_entities"][0]["reason"])

    def test_create_filter_nested_sequenced_assembly_converts_without_item_loss(self):
        transitional = item("create:incomplete_precision_mechanism")
        transitional["components"] = compound(
            **{
                "minecraft:lore": generated_assembly_lore(),
                "create:sequenced_assembly_progress": nbt.TAG_Float(
                    converter._expected_float32(1, 15)
                ),
            }
        )
        filter_stack = item("create:filter")
        filter_stack["components"] = compound(
            **{
                "!minecraft:attribute_modifiers": compound(),
                "!minecraft:enchantments": compound(),
                "create:filter_items": tag_list(
                    nbt.TAG_Compound,
                    compound(slot=nbt.TAG_Int(0), item=transitional),
                    compound(
                        slot=nbt.TAG_Int(1),
                        item=item("create:golden_sheet"),
                    ),
                ),
                "create:filter_items_respect_nbt": nbt.TAG_Byte(0),
                "create:filter_items_blacklist": nbt.TAG_Byte(0),
            }
        )
        funnel = compound(
            id=nbt.TAG_String("create:funnel"),
            x=nbt.TAG_Int(27305), y=nbt.TAG_Int(61), z=nbt.TAG_Int(-12893),
            components=compound(),
            Filter=filter_stack,
        )

        self.assertTrue(converter.convert_block_entity(funnel, self.audit))
        entries = funnel["Filter"]["components"]["create:filter_items"]
        self.assertEqual([int(entry["slot"].value) for entry in entries], [0, 1])
        self.assertEqual(str(entries[1]["item"]["id"]), "create:golden_sheet")
        converted = entries[0]["item"]["components"]
        self.assertNotIn("create:sequenced_assembly_progress", converted)
        self.assertNotIn("minecraft:lore", converted)
        assembly = converted["create:sequenced_assembly"]
        self.assertEqual(str(assembly["id"]), "create:sequenced_assembly/precision_mechanism")
        self.assertEqual(int(assembly["step"].value), 1)
        self.assertEqual(
            float(assembly["progress"].value),
            converter._expected_float32(1, 15),
        )
        self.assertEqual(len(self.audit["sequenced_assembly_conversions"]), 1)
        after = converter.comparable_tag(funnel)
        self.assertFalse(converter.convert_block_entity(funnel, self.audit))
        self.assertEqual(converter.comparable_tag(funnel), after)
        self.assertEqual(len(self.audit["sequenced_assembly_conversions"]), 1)

    def test_create_sequenced_assembly_progress_conflict_is_fail_closed(self):
        transitional = item("create:incomplete_precision_mechanism")
        transitional["components"] = compound(
            **{
                "minecraft:lore": generated_assembly_lore(step=1, total=15),
                "create:sequenced_assembly_progress": nbt.TAG_Float(
                    converter._expected_float32(2, 15)
                ),
            }
        )
        funnel = compound(
            id=nbt.TAG_String("create:funnel"),
            components=compound(),
            Filter=transitional,
        )
        before = converter.comparable_tag(funnel)

        self.assertFalse(converter.convert_block_entity(funnel, self.audit))
        self.assertEqual(converter.comparable_tag(funnel), before)
        self.assertEqual(len(self.audit["unsupported_block_entity_items"]), 1)
        self.assertIn(
            "disagree",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )

    def test_create_sequenced_assembly_custom_lore_is_not_deleted(self):
        transitional = item("create:incomplete_precision_mechanism")
        lore = generated_assembly_lore(step=1, total=15)
        lore[3]["with"][0]["with"][0]["ingredient"] = nbt.TAG_String(
            "create:golden_sheet"
        )
        transitional["components"] = compound(
            **{
                "minecraft:lore": lore,
                "create:sequenced_assembly_progress": nbt.TAG_Float(
                    converter._expected_float32(1, 15)
                ),
            }
        )
        funnel = compound(
            id=nbt.TAG_String("create:funnel"),
            components=compound(),
            Filter=transitional,
        )
        before = converter.comparable_tag(funnel)

        self.assertFalse(converter.convert_block_entity(funnel, self.audit))
        self.assertEqual(converter.comparable_tag(funnel), before)
        self.assertIn(
            "next-step line is malformed",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )

    def test_create_filter_non_boolean_flags_are_fail_closed(self):
        filter_stack = item("create:filter")
        filter_stack["components"] = compound(
            **{
                "create:filter_items": tag_list(nbt.TAG_Compound),
                "create:filter_items_respect_nbt": nbt.TAG_Byte(0),
                "create:filter_items_blacklist": nbt.TAG_String("false"),
            }
        )
        funnel = compound(
            id=nbt.TAG_String("create:funnel"),
            components=compound(),
            Filter=filter_stack,
        )
        before = converter.comparable_tag(funnel)

        self.assertFalse(converter.convert_block_entity(funnel, self.audit))
        self.assertEqual(converter.comparable_tag(funnel), before)
        self.assertIn(
            "not a byte boolean",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )

    def test_create_filter_malformed_carrier_is_fail_closed(self):
        filter_stack = item("create:filter")
        filter_stack["components"] = compound(
            **{
                "create:filter_items": tag_list(
                    nbt.TAG_Compound,
                    compound(
                        slot=nbt.TAG_Int(0),
                        future=nbt.TAG_Int(1),
                        item=item("create:golden_sheet"),
                    ),
                ),
                "create:filter_items_respect_nbt": nbt.TAG_Byte(0),
                "create:filter_items_blacklist": nbt.TAG_Byte(0),
            }
        )
        funnel = compound(
            id=nbt.TAG_String("create:funnel"),
            components=compound(),
            Filter=filter_stack,
        )
        before = converter.comparable_tag(funnel)

        self.assertFalse(converter.convert_block_entity(funnel, self.audit))
        self.assertEqual(converter.comparable_tag(funnel), before)
        self.assertIn(
            "unknown fields",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )

    def test_create_item_vault_positional_inventory_converts_to_item_handler(self):
        vault = compound(
            id=nbt.TAG_String("create:item_vault"),
            x=nbt.TAG_Int(-82), y=nbt.TAG_Int(46), z=nbt.TAG_Int(-68),
            Inventory=tag_list(
                nbt.TAG_Compound,
                item("minecraft:iron_ingot", 32),
                item("create:brass_sheet", 7),
            ),
        )

        self.assertTrue(converter.convert_block_entity(vault, self.audit))
        inventory = vault["Inventory"]
        self.assertIsInstance(inventory, nbt.TAG_Compound)
        self.assertEqual(20, int(inventory["Size"].value))
        self.assertEqual(2, len(inventory["Items"]))
        self.assertEqual([0, 1], [int(stack["Slot"].value) for stack in inventory["Items"]])
        self.assertEqual(
            ["minecraft:iron_ingot", "create:brass_sheet"],
            [str(stack["id"]) for stack in inventory["Items"]],
        )
        self.assertEqual(1, len(self.audit["item_vault_inventory_conversions"]))

        after = converter.comparable_tag(vault)
        self.assertFalse(converter.convert_block_entity(vault, self.audit))
        self.assertEqual(after, converter.comparable_tag(vault))

    def test_create_item_vault_over_capacity_is_fail_closed(self):
        source_items = [item("minecraft:stone") for _ in range(21)]
        vault = compound(
            id=nbt.TAG_String("create:item_vault"),
            Inventory=tag_list(nbt.TAG_Compound, *source_items),
        )
        before = converter.comparable_tag(vault)

        self.assertFalse(converter.convert_block_entity(vault, self.audit))
        self.assertEqual(before, converter.comparable_tag(vault))
        self.assertIn("exceeding target capacity", self.audit["unsupported_block_entities"][0]["reason"])

    def test_create_fluid_stack_and_mounted_capacity_convert_exactly(self):
        fluid = compound(
            id=nbt.TAG_String("create:milk"),
            amount=nbt.TAG_Int(81_000),
            components=compound(**{
                "create:fluid_max_capacity": nbt.TAG_Int(81_000),
            }),
        )
        tank = compound(
            id=nbt.TAG_String("create:fluid_tank"),
            x=nbt.TAG_Int(8), y=nbt.TAG_Int(64), z=nbt.TAG_Int(9),
            Fluid=fluid,
            Mounted=compound(
                type=nbt.TAG_String("create:fluid_tank"),
                capacity=nbt.TAG_Int(1_296_000),
                fluid=compound(),
            ),
        )

        self.assertTrue(converter.convert_block_entity(tank, self.audit))
        self.assertNotIn("Fluid", tank)
        target_fluid = tank["TankContent"]["Fluid"]
        self.assertEqual(str(target_fluid["id"]), "minecraft:milk")
        self.assertEqual(int(target_fluid["amount"].value), 1_000)
        self.assertNotIn("components", target_fluid)
        self.assertEqual(int(tank["Mounted"]["capacity"].value), 16_000)
        self.assertEqual(len(self.audit["create_fluid_conversions"]), 1)
        self.assertEqual(len(self.audit["fluid_tank_storage_conversions"]), 1)
        after = converter.comparable_tag(tank)
        self.assertFalse(converter.convert_block_entity(tank, self.audit))
        self.assertEqual(converter.comparable_tag(tank), after)

    def test_create_fluid_tank_direct_tank_content_is_wrapped(self):
        tank = compound(
            id=nbt.TAG_String("create:fluid_tank"),
            TankContent=compound(
                id=nbt.TAG_String("minecraft:water"),
                amount=nbt.TAG_Int(1_000),
            ),
        )
        self.assertTrue(converter.convert_block_entity(tank, self.audit))
        self.assertEqual("minecraft:water", str(tank["TankContent"]["Fluid"]["id"]))
        self.assertEqual(1_000, int(tank["TankContent"]["Fluid"]["amount"].value))
        self.assertEqual(1, len(self.audit["fluid_tank_storage_conversions"]))
        after = converter.comparable_tag(tank)
        self.assertFalse(converter.convert_block_entity(tank, self.audit))
        self.assertEqual(after, converter.comparable_tag(tank))

    def test_create_hose_pulley_root_fluid_is_wrapped(self):
        hose = compound(
            id=nbt.TAG_String("create:hose_pulley"),
            Fluid=compound(
                id=nbt.TAG_String("minecraft:lava"),
                amount=nbt.TAG_Int(50_220),
                components=compound(**{
                    "create:fluid_max_capacity": nbt.TAG_Int(121_500),
                }),
            ),
        )
        self.assertTrue(converter.convert_block_entity(hose, self.audit))
        self.assertNotIn("Fluid", hose)
        self.assertEqual("minecraft:lava", str(hose["Tank"]["Fluid"]["id"]))
        self.assertEqual(620, int(hose["Tank"]["Fluid"]["amount"].value))
        self.assertEqual(1, len(self.audit["internal_fluid_storage_conversions"]))
        after = converter.comparable_tag(hose)
        self.assertFalse(converter.convert_block_entity(hose, self.audit))
        self.assertEqual(after, converter.comparable_tag(hose))

    def test_create_smart_fluid_tank_behaviour_payloads_are_wrapped(self):
        cases = (
            ("create:basin", "InputTanks"),
            ("create:item_drain", "Tanks"),
            ("create:spout", "Tanks"),
            ("create_enchantment_industry:blaze_enchanter", "Tanks"),
            ("create_enchantment_industry:blaze_forger", "Tanks"),
            ("create_enchantment_industry:experience_lantern", "Tanks"),
        )
        for identifier, field in cases:
            with self.subTest(identifier=identifier, field=field):
                audit = converter.new_audit(Path("fixture"), 100)
                extra = {}
                if identifier == "create_enchantment_industry:blaze_forger":
                    extra = {
                        "Inventory": compound(
                            Size=nbt.TAG_Int(6),
                            Items=tag_list(nbt.TAG_Compound),
                            Cost=nbt.TAG_Int(0),
                            Operation=nbt.TAG_Int(0),
                            Conflicting=nbt.TAG_Byte(0),
                            OverCap=nbt.TAG_Byte(0),
                        ),
                        "ForgingMode": nbt.TAG_Int(0),
                    }
                block = compound(
                    id=nbt.TAG_String(identifier),
                    **extra,
                    **{
                        field: tag_list(
                            nbt.TAG_Compound,
                            compound(
                                TankContent=compound(
                                    id=nbt.TAG_String("minecraft:water"),
                                    amount=nbt.TAG_Int(81_000),
                                    components=compound(**{
                                        "create:fluid_max_capacity": nbt.TAG_Int(81_000),
                                    }),
                                ),
                            ),
                        )
                    },
                )
                self.assertTrue(converter.convert_block_entity(block, audit))
                fluid = block[field][0]["TankContent"]["Fluid"]
                self.assertEqual("minecraft:water", str(fluid["id"]))
                self.assertEqual(1_000, int(fluid["amount"].value))
                self.assertEqual(1, len(audit["internal_fluid_storage_conversions"]))
                after = converter.comparable_tag(block)
                self.assertFalse(converter.convert_block_entity(block, audit))
                self.assertEqual(after, converter.comparable_tag(block))

    def test_create_smart_fluid_tank_late_blocker_rolls_back_whole_block_entity(self):
        block = compound(
            id=nbt.TAG_String("create:spout"),
            Tanks=tag_list(
                nbt.TAG_Compound,
                compound(
                    TankContent=compound(
                        id=nbt.TAG_String("minecraft:water"),
                        amount=nbt.TAG_Int(81_000),
                        components=compound(**{
                            "create:fluid_max_capacity": nbt.TAG_Int(81_000),
                        }),
                    ),
                ),
                compound(TankContent=compound(Unknown=nbt.TAG_Int(1))),
            ),
        )
        before = converter.comparable_tag(block)

        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(before, converter.comparable_tag(block))
        self.assertEqual([], self.audit["create_fluid_conversions"])
        self.assertEqual([], self.audit["internal_fluid_storage_conversions"])
        self.assertEqual(1, len(self.audit["unsupported_block_entities"]))
        self.assertIn(
            "unaudited fields",
            self.audit["unsupported_block_entities"][0]["reason"],
        )

    def test_inexact_create_fluid_quantity_is_fail_closed(self):
        tank = compound(
            id=nbt.TAG_String("create:fluid_tank"),
            TankContent=compound(
                id=nbt.TAG_String("minecraft:water"),
                amount=nbt.TAG_Int(81_001),
                components=compound(**{
                    "create:fluid_max_capacity": nbt.TAG_Int(81_000),
                }),
            ),
        )
        before = converter.comparable_tag(tank)

        self.assertFalse(converter.convert_block_entity(tank, self.audit))
        self.assertEqual(converter.comparable_tag(tank), before)
        self.assertEqual(len(self.audit["unsupported_create_fluids"]), 1)
        self.assertIn(
            "cannot be represented exactly",
            self.audit["unsupported_create_fluids"][0]["blockers"][0]["reason"],
        )

    def test_potion_fluid_uses_exact_bottle_scale(self):
        tank = compound(
            id=nbt.TAG_String("create:fluid_tank"),
            x=nbt.TAG_Int(-207), y=nbt.TAG_Int(63), z=nbt.TAG_Int(-122),
            Fluid=compound(
                id=nbt.TAG_String("create:potion"),
                amount=nbt.TAG_Int(896_400),
                components=compound(**{
                    "create:fluid_max_capacity": nbt.TAG_Int(2_592_000),
                    "create:potion_fluid_bottle_type": nbt.TAG_String("regular"),
                    "minecraft:potion_contents": compound(
                        potion=nbt.TAG_String("minecraft:harming"),
                    ),
                }),
            ),
        )

        self.assertTrue(converter.convert_block_entity(tank, self.audit))
        self.assertEqual(8_300, int(tank["TankContent"]["Fluid"]["amount"].value))
        self.assertEqual([], self.audit["unsupported_create_fluids"])
        self.assertEqual(1, len(self.audit["create_fluid_exact_potion_scale_conversions"]))
        exact = self.audit["create_fluid_exact_potion_scale_conversions"][0]
        self.assertEqual(108, exact["divisor"])
        self.assertEqual(24_000, exact["target_max_capacity"])

    def test_potion_fluid_inexact_for_108_uses_explicit_nearest_policy(self):
        tank = compound(
            id=nbt.TAG_String("create:spout"),
            Tanks=tag_list(
                nbt.TAG_Compound,
                compound(TankContent=compound(
                    id=nbt.TAG_String("create:potion"),
                    amount=nbt.TAG_Int(810),
                    components=compound(**{
                        "create:fluid_max_capacity": nbt.TAG_Int(81_000),
                    }),
                )),
            ),
        )
        self.assertTrue(converter.convert_block_entity(tank, self.audit))
        self.assertEqual(8, int(tank["Tanks"][0]["TankContent"]["Fluid"]["amount"].value))
        self.assertEqual([], self.audit["unsupported_create_fluids"])
        self.assertEqual(1, len(self.audit["create_fluid_nearest_potion_scale_conversions"]))
        conversion = self.audit["create_fluid_nearest_potion_scale_conversions"][0]
        self.assertEqual(54, conversion["source_remainder"])
        self.assertEqual(0.5, conversion["target_error_millibuckets"])

    def test_elevator_assembly_exception_codec_is_idempotent(self):
        pulley = compound(
            id=nbt.TAG_String("create:elevator_pulley"),
            x=nbt.TAG_Int(-159), y=nbt.TAG_Int(57), z=nbt.TAG_Int(-42),
            LastException=compound(
                Component=compound(
                    translate=nbt.TAG_String("create.gui.assembly.exception.no_poles"),
                ),
                Position=int_array(-159, 57, -42),
            ),
        )

        self.assertTrue(converter.convert_block_entity(pulley, self.audit))
        exception = pulley["LastException"]
        self.assertEqual(
            str(exception["Component"]),
            '{"translate":"create.gui.assembly.exception.no_poles"}',
        )
        self.assertIsInstance(exception["Position"], nbt.TAG_Long)
        self.assertEqual(len(self.audit["assembly_exception_conversions"]), 1)
        after = converter.comparable_tag(pulley)
        self.assertFalse(converter.convert_block_entity(pulley, self.audit))
        self.assertEqual(converter.comparable_tag(pulley), after)

    def test_elevator_assembly_exception_missing_component_is_fail_closed(self):
        pulley = compound(
            id=nbt.TAG_String("create:elevator_pulley"),
            x=nbt.TAG_Int(-159), y=nbt.TAG_Int(57), z=nbt.TAG_Int(-42),
            LastException=compound(Position=int_array(-159, 57, -42)),
        )
        before = converter.comparable_tag(pulley)

        self.assertFalse(converter.convert_block_entity(pulley, self.audit))
        self.assertEqual(converter.comparable_tag(pulley), before)
        self.assertEqual(len(self.audit["unsupported_block_entities"]), 1)
        self.assertIn(
            "LastException.Component is missing",
            self.audit["unsupported_block_entities"][0]["reason"],
        )

    def test_cookery_millstone_uuid_string_converts_exactly(self):
        millstone = compound(
            id=nbt.TAG_String("kaleidoscope_cookery:millstone"),
            x=nbt.TAG_Int(-165), y=nbt.TAG_Int(64), z=nbt.TAG_Int(-92),
            EntityId=nbt.TAG_String("7fa85cd1-927c-4f29-ac47-f8b2b09a533c"),
        )

        self.assertTrue(converter.convert_block_entity(millstone, self.audit))
        self.assertEqual(
            [int(value) for value in millstone["EntityId"].value],
            [2141740241, -1837347031, -1404569422, -1332063428],
        )
        self.assertEqual(len(self.audit["millstone_uuid_conversions"]), 1)
        after = converter.comparable_tag(millstone)
        self.assertFalse(converter.convert_block_entity(millstone, self.audit))
        self.assertEqual(converter.comparable_tag(millstone), after)

    def test_schematicannon_nested_print_stage_alias_is_idempotent(self):
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            x=nbt.TAG_Int(3), y=nbt.TAG_Int(64), z=nbt.TAG_Int(4),
            State=nbt.TAG_String("STOPPED"),
            Inventory=compound(Size=nbt.TAG_Int(5), Items=tag_list(nbt.TAG_Compound)),
            Printer=compound(
                PrintStage=nbt.TAG_String("blocks"),
                DeferredBlocks=tag_list(nbt.TAG_Compound),
            ),
        )
        self.assertTrue(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(str(cannon["Printer"]["PrintStage"]), "BLOCKS")
        self.assertEqual(len(self.audit["block_entity_print_stage_aliases"]), 1)
        self.assertFalse(converter.convert_block_entity(cannon, self.audit))

    def test_unknown_schematicannon_print_stage_is_fail_closed(self):
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            x=nbt.TAG_Int(3), y=nbt.TAG_Int(64), z=nbt.TAG_Int(4),
            Inventory=compound(Size=nbt.TAG_Int(5), Items=tag_list(nbt.TAG_Compound)),
            Printer=compound(PrintStage=nbt.TAG_String("future_stage")),
        )
        self.assertFalse(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(str(cannon["Printer"]["PrintStage"]), "future_stage")
        self.assertEqual(len(self.audit["unsupported_block_entities"]), 1)

    def test_unknown_schematicannon_state_is_fail_closed(self):
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            x=nbt.TAG_Int(3), y=nbt.TAG_Int(64), z=nbt.TAG_Int(4),
            State=nbt.TAG_String("future_state"),
            Inventory=compound(Size=nbt.TAG_Int(5), Items=tag_list(nbt.TAG_Compound)),
        )
        self.assertFalse(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(str(cannon["State"]), "future_state")
        self.assertEqual(len(self.audit["unsupported_block_entities"]), 1)

    def test_schematicannon_inventory_list_converts_without_item_loss(self):
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            x=nbt.TAG_Int(-12), y=nbt.TAG_Int(64), z=nbt.TAG_Int(9),
            State=nbt.TAG_String("STOPPED"),
            Status=nbt.TAG_String("finished"),
            Inventory=tag_list(
                nbt.TAG_Compound,
                compound(),
                item("create:empty_schematic"),
                compound(),
                compound(),
                item("minecraft:gunpowder", 23),
            ),
        )

        self.assertTrue(converter.convert_block_entity(cannon, self.audit))
        inventory = cannon["Inventory"]
        self.assertIsInstance(inventory, nbt.TAG_Compound)
        self.assertEqual(int(inventory["Size"].value), 5)
        self.assertEqual(str(cannon["Status"]), "finished")
        by_slot = {int(stack["Slot"].value): stack for stack in inventory["Items"]}
        self.assertEqual(set(by_slot), {1, 4})
        self.assertEqual(str(by_slot[1]["id"]), "create:empty_schematic")
        self.assertEqual(int(by_slot[1]["count"].value), 1)
        self.assertEqual(str(by_slot[4]["id"]), "minecraft:gunpowder")
        self.assertEqual(int(by_slot[4]["count"].value), 23)
        self.assertEqual(
            self.audit["schematicannon_inventory_conversions"][0]["items"],
            [
                {"slot": 1, "id": "create:empty_schematic", "count": 1},
                {"slot": 4, "id": "minecraft:gunpowder", "count": 23},
            ],
        )

        after_first = converter.comparable_tag(cannon)
        self.assertFalse(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(converter.comparable_tag(cannon), after_first)
        self.assertEqual(len(self.audit["schematicannon_inventory_conversions"]), 1)

    def test_schematicannon_inventory_target_container_is_validated_idempotently(self):
        stored = item("minecraft:gunpowder", 9)
        stored["Slot"] = nbt.TAG_Int(4)
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            Inventory=compound(
                Size=nbt.TAG_Int(5),
                Items=tag_list(nbt.TAG_Compound, stored),
            ),
        )
        before = converter.comparable_tag(cannon)

        self.assertFalse(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(converter.comparable_tag(cannon), before)
        self.assertFalse(self.audit["unsupported_block_entities"])

    def test_schematicannon_inventory_unknown_source_shape_is_fail_closed(self):
        malformed = item("minecraft:gunpowder", 9)
        malformed["future_field"] = nbt.TAG_Int(1)
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            Inventory=tag_list(
                nbt.TAG_Compound,
                compound(), compound(), compound(), compound(), malformed,
            ),
        )
        before = converter.comparable_tag(cannon)

        self.assertFalse(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(converter.comparable_tag(cannon), before)
        self.assertIn("unknown fields", self.audit["unsupported_block_entities"][0]["reason"])

    def test_schematicannon_inventory_bad_target_slot_is_fail_closed(self):
        first = item("minecraft:gunpowder", 9)
        first["Slot"] = nbt.TAG_Int(4)
        duplicate = item("minecraft:gunpowder", 1)
        duplicate["Slot"] = nbt.TAG_Int(4)
        cannon = compound(
            id=nbt.TAG_String("create:schematicannon"),
            Inventory=compound(
                Size=nbt.TAG_Int(5),
                Items=tag_list(nbt.TAG_Compound, first, duplicate),
            ),
        )
        before = converter.comparable_tag(cannon)

        self.assertFalse(converter.convert_block_entity(cannon, self.audit))
        self.assertEqual(converter.comparable_tag(cannon), before)
        self.assertIn("duplicates Slot 4", self.audit["unsupported_block_entities"][0]["reason"])

    def test_block_entity_item_back_pocket_upgrade_reverses_official_rename(self):
        stack = item("computercraft:pocket_computer_normal")
        stack["components"] = compound(
            **{
                "computercraft:back_pocket_upgrade": compound(
                    id=nbt.TAG_String("computercraft:speaker"),
                )
            }
        )
        block = compound(
            id=nbt.TAG_String("minecraft:chest"),
            x=nbt.TAG_Int(12),
            y=nbt.TAG_Int(64),
            z=nbt.TAG_Int(-8),
            Inventory=compound(Items=tag_list(nbt.TAG_Compound, stack)),
        )

        self.assertTrue(converter.convert_block_entity(block, self.audit))
        converted = block["Inventory"]["Items"][0]["components"]
        self.assertNotIn("computercraft:back_pocket_upgrade", converted)
        self.assertEqual(
            str(converted["computercraft:pocket_upgrade"]["id"]),
            "computercraft:speaker",
        )
        self.assertEqual(
            len(self.audit["computercraft_pocket_upgrade_conversions"]), 1
        )
        self.assertEqual(self.audit["unsupported_block_entity_items"], [])
        after = converter.comparable_tag(block)
        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), after)

    def test_bottom_pocket_upgrade_is_unrepresentable_and_rolls_back_block(self):
        stack = item("computercraft:pocket_computer_normal")
        stack["components"] = compound(
            **{
                "computercraft:bottom_pocket_upgrade": compound(
                    id=nbt.TAG_String("computercraft:speaker"),
                ),
                "minecraft:item_name": compound(
                    translate=nbt.TAG_String("item.computercraft.pocket_computer_normal")
                ),
            }
        )
        block = compound(
            id=nbt.TAG_String("minecraft:chest"),
            Inventory=compound(Items=tag_list(nbt.TAG_Compound, stack)),
        )
        before = converter.comparable_tag(block)

        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), before)
        self.assertIn(
            "bottom pocket upgrade",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )
        # The item_name canonicalization was planned on the clone but must not
        # leak when the unrepresentable second upgrade blocks the carrier.
        self.assertIsInstance(
            block["Inventory"]["Items"][0]["components"]["minecraft:item_name"],
            nbt.TAG_Compound,
        )

    def test_block_entity_components_tooltip_display_uses_separate_audit(self):
        block = compound(
            id=nbt.TAG_String("minecraft:banner"),
            x=nbt.TAG_Int(4),
            y=nbt.TAG_Int(70),
            z=nbt.TAG_Int(5),
            components=compound(
                **{
                    "minecraft:banner_patterns": tag_list(nbt.TAG_Compound),
                    "minecraft:item_name": compound(
                        translate=nbt.TAG_String("block.minecraft.ominous_banner")
                    ),
                    "minecraft:tooltip_display": compound(
                        hidden_components=tag_list(
                            nbt.TAG_String,
                            nbt.TAG_String("minecraft:banner_patterns"),
                        )
                    ),
                }
            ),
        )

        self.assertTrue(converter.convert_block_entity(block, self.audit))
        components = block["components"]
        self.assertNotIn("minecraft:tooltip_display", components)
        self.assertIn("minecraft:hide_additional_tooltip", components)
        self.assertEqual(
            str(components["minecraft:item_name"]),
            '{"translate":"block.minecraft.ominous_banner"}',
        )
        self.assertEqual(len(self.audit["block_entity_component_maps"]), 1)
        self.assertEqual(len(self.audit["block_entity_tooltip_displays"]), 1)
        self.assertEqual(self.audit["item_tooltip_displays"], [])

    def test_block_entity_walker_ignores_arbitrary_id_count_mod_state(self):
        state = compound(
            id=nbt.TAG_String("example:recipe_state"),
            count=nbt.TAG_Int(1),
            mode=nbt.TAG_String("future"),
            components=compound(
                **{
                    "minecraft:tooltip_display": compound(
                        hidden_components=tag_list(nbt.TAG_String)
                    )
                }
            ),
        )
        block = compound(id=nbt.TAG_String("example:machine"), State=state)
        before = converter.comparable_tag(block)

        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), before)
        self.assertEqual(self.audit["unsupported_block_entity_items"], [])
        self.assertEqual(self.audit["block_entity_item_stacks"], [])

    def test_block_entity_item_with_malformed_components_is_fail_closed(self):
        stack = item("minecraft:white_banner")
        stack["components"] = nbt.TAG_String("not-a-component-map")
        block = compound(
            id=nbt.TAG_String("minecraft:chest"),
            Inventory=compound(Items=tag_list(nbt.TAG_Compound, stack)),
        )
        before = converter.comparable_tag(block)

        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), before)
        self.assertIn(
            "components is not a compound",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )

    def test_written_book_pages_convert_to_target_flat_codec_idempotently(self):
        hover = compound(
            action=nbt.TAG_String("show_item"),
            id=nbt.TAG_String("minecraft:diamond"),
            count=nbt.TAG_Int(2),
        )
        raw = compound(
            text=nbt.TAG_String(""),
            extra=tag_list(
                nbt.TAG_Compound,
                compound(**{"": nbt.TAG_String("checked")}),
                compound(
                    translate=nbt.TAG_String("item.minecraft.diamond"),
                    hover_event=hover,
                ),
            ),
        )
        book = item("minecraft:written_book")
        book["components"] = compound(
            **{
                "minecraft:written_book_content": compound(
                    title=compound(raw=nbt.TAG_String("audit")),
                    author=nbt.TAG_String("Codex"),
                    pages=tag_list(
                        nbt.TAG_Compound,
                        compound(raw=raw),
                    ),
                    resolved=nbt.TAG_Byte(1),
                )
            }
        )
        block = compound(
            id=nbt.TAG_String("minecraft:chest"),
            Items=tag_list(nbt.TAG_Compound, book),
        )

        self.assertTrue(converter.convert_block_entity(block, self.audit))
        encoded = str(
            block["Items"][0]["components"]["minecraft:written_book_content"]
            ["pages"][0]["raw"]
        )
        parsed = json.loads(encoded)
        self.assertEqual(parsed["extra"][0], {"text": "checked"})
        self.assertEqual(
            parsed["extra"][1]["hoverEvent"],
            {
                "action": "show_item",
                "contents": {"id": "minecraft:diamond", "count": 2},
            },
        )
        self.assertEqual(self.audit["unsupported_block_entity_items"], [])
        after = converter.comparable_tag(block)
        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), after)

    def test_cookery_recipe_record_adds_required_flex_flag_and_recurses_items(self):
        ingredient = item("minecraft:chorus_fruit")
        ingredient["components"] = compound(
            **{
                "minecraft:custom_name": compound(
                    text=nbt.TAG_String("ingredient")
                )
            }
        )
        recipe = item("kaleidoscope_cookery:recipe_item")
        recipe["components"] = compound(
            **{
                "kaleidoscope_cookery:recipe_record": compound(
                    input=tag_list(nbt.TAG_Compound, ingredient, compound()),
                    output=item("kaleidoscope_cookery:end_style_sashimi"),
                    type=nbt.TAG_String("kaleidoscope_cookery:pot"),
                )
            }
        )
        block = compound(
            id=nbt.TAG_String("minecraft:chest"),
            Items=tag_list(nbt.TAG_Compound, recipe),
        )

        self.assertTrue(converter.convert_block_entity(block, self.audit))
        record = block["Items"][0]["components"]["kaleidoscope_cookery:recipe_record"]
        self.assertEqual(int(record["flex_recipe"].value), 0)
        self.assertEqual(
            str(record["input"][0]["components"]["minecraft:custom_name"]),
            '{"text":"ingredient"}',
        )
        self.assertEqual(self.audit["unsupported_block_entity_items"], [])
        after = converter.comparable_tag(block)
        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), after)

    def test_audited_cc_tom_and_create_component_codecs_pass_exact_shapes(self):
        computer = item("computercraft:pocket_computer_advanced")
        computer["components"] = compound(
            **{
                "computercraft:computer_id": nbt.TAG_Int(9),
                "computercraft:on": nbt.TAG_Byte(1),
                "computercraft:computer": compound(
                    session=nbt.TAG_Int(123),
                    instance=int_array(1, 2, 3, 4),
                ),
            }
        )
        simple_filter = item("toms_storage:item_filter")
        simple_filter["components"] = compound(
            **{
                "toms_storage:simple_item_filter": compound(
                    stacks=tag_list(
                        nbt.TAG_Compound,
                        compound(),
                        item("minecraft:diamond"),
                    ),
                    match_component=nbt.TAG_Byte(1),
                    allow_list=nbt.TAG_Byte(0),
                )
            }
        )
        block = compound(
            id=nbt.TAG_String("create:display_link"),
            components=compound(
                **{
                    "create:click_to_link_data": compound(
                        selected_pos=int_array(-218, 65, -99),
                        selected_dim=nbt.TAG_String("minecraft:overworld"),
                    )
                }
            ),
            Inventory=tag_list(nbt.TAG_Compound, computer, simple_filter),
        )
        before = converter.comparable_tag(block)

        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), before)
        self.assertEqual(self.audit["unsupported_block_entity_items"], [])
        self.assertEqual(self.audit["unsupported_block_entity_components"], [])

    def test_malformed_cc_reference_rolls_back_other_component_changes(self):
        computer = item("computercraft:pocket_computer_advanced")
        computer["components"] = compound(
            **{
                "computercraft:computer": compound(
                    session=nbt.TAG_Int(123),
                    instance=int_array(1, 2, 3),
                ),
                "minecraft:item_name": compound(
                    translate=nbt.TAG_String("item.computercraft.pocket_computer_advanced")
                ),
            }
        )
        block = compound(
            id=nbt.TAG_String("minecraft:barrel"),
            Items=tag_list(nbt.TAG_Compound, computer),
        )
        before = converter.comparable_tag(block)

        self.assertFalse(converter.convert_block_entity(block, self.audit))
        self.assertEqual(converter.comparable_tag(block), before)
        self.assertIn(
            "ServerComputerReference.CODEC",
            self.audit["unsupported_block_entity_items"][0]["reason"],
        )


class PlayerConversionTests(unittest.TestCase):
    def setUp(self):
        self.audit = converter.new_audit(Path("fixture"), 100)
        self.path = Path("00000000-0000-0000-0000-000000000001.dat")

    def test_equipment_maps_to_inventory_slots(self):
        player = compound(
            SelectedItemSlot=nbt.TAG_Int(2),
            Inventory=tag_list(nbt.TAG_Compound),
            equipment=compound(
                mainhand=item("minecraft:diamond_sword"),
                offhand=item("minecraft:shield"),
                head=item("minecraft:netherite_helmet"),
            ),
        )
        self.assertTrue(converter.convert_player_equipment(player, self.path, self.audit))
        self.assertNotIn("equipment", player)
        by_slot = {converter.inventory_slot(value): value for value in player["Inventory"]}
        self.assertEqual(str(by_slot[2]["id"]), "minecraft:diamond_sword")
        self.assertEqual(str(by_slot[103]["id"]), "minecraft:netherite_helmet")
        self.assertEqual(str(by_slot[150]["id"]), "minecraft:shield")
        self.assertEqual(int(by_slot[150]["Slot"].value), -106)

    def test_item_text_components_use_flat_codec_without_losing_spaces(self):
        literal = item("minecraft:diamond_spear")
        literal["components"] = compound()
        literal["components"]["minecraft:custom_name"] = nbt.TAG_String("冈格尼尔  ")
        structured = item("minecraft:filled_map")
        structured["components"] = compound()
        structured["components"]["minecraft:item_name"] = compound(
            translate=nbt.TAG_String("filled_map.buried_treasure"),
        )
        structured["components"]["minecraft:custom_name"] = compound(
            italic=nbt.TAG_Byte(0),
            translate=nbt.TAG_String("create.materialChecklist"),
        )
        existing = item("minecraft:name_tag")
        existing["components"] = compound()
        existing["components"]["minecraft:custom_name"] = nbt.TAG_String('{"text":"Home"}')
        player = compound(Inventory=tag_list(nbt.TAG_Compound, literal, structured, existing))

        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertTrue(changed)
        self.assertTrue(safe)
        self.assertEqual(str(player["Inventory"][0]["components"]["minecraft:custom_name"]), '"冈格尼尔  "')
        self.assertEqual(
            str(player["Inventory"][1]["components"]["minecraft:item_name"]),
            '{"translate":"filled_map.buried_treasure"}',
        )
        self.assertEqual(
            str(player["Inventory"][1]["components"]["minecraft:custom_name"]),
            '{"italic":false,"translate":"create.materialChecklist"}',
        )
        self.assertEqual(str(player["Inventory"][2]["components"]["minecraft:custom_name"]), '{"text":"Home"}')
        self.assertEqual(len(self.audit["item_text_components"]), 3)

    def test_nested_container_bundle_and_projectile_items_are_converted(self):
        bucket = item("minecraft:axolotl_bucket")
        bucket["components"] = compound()
        bucket["components"]["minecraft:axolotl/variant"] = nbt.TAG_String("lucy")
        bucket["components"]["minecraft:bucket_entity_data"] = compound(
            Age=nbt.TAG_Int(0),
            Health=nbt.TAG_Float(13.0),
        )
        shulker = item("minecraft:shulker_box")
        shulker["components"] = compound()
        shulker["components"]["minecraft:container"] = tag_list(
            nbt.TAG_Compound,
            compound(slot=nbt.TAG_Int(13), item=bucket),
        )

        bundled = item("minecraft:paper")
        bundled["components"] = compound()
        bundled["components"]["minecraft:custom_name"] = nbt.TAG_String("bundle child")
        bundle = item("minecraft:bundle")
        bundle["components"] = compound()
        bundle["components"]["minecraft:bundle_contents"] = tag_list(nbt.TAG_Compound, bundled)

        projectile = item("minecraft:arrow")
        projectile["components"] = compound()
        projectile["components"]["minecraft:custom_name"] = nbt.TAG_String("projectile child")
        crossbow = item("minecraft:crossbow")
        crossbow["components"] = compound()
        crossbow["components"]["minecraft:charged_projectiles"] = tag_list(nbt.TAG_Compound, projectile)
        player = compound(EnderItems=tag_list(nbt.TAG_Compound, shulker, bundle, crossbow))

        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertTrue(changed)
        self.assertTrue(safe)
        nested_components = player["EnderItems"][0]["components"]["minecraft:container"][0]["item"]["components"]
        self.assertNotIn("minecraft:axolotl/variant", nested_components)
        self.assertEqual(int(nested_components["minecraft:bucket_entity_data"]["Variant"].value), 0)
        self.assertEqual(float(nested_components["minecraft:bucket_entity_data"]["Health"].value), 13.0)
        self.assertEqual(
            str(player["EnderItems"][1]["components"]["minecraft:bundle_contents"][0]["components"]["minecraft:custom_name"]),
            '"bundle child"',
        )
        self.assertEqual(
            str(player["EnderItems"][2]["components"]["minecraft:charged_projectiles"][0]["components"]["minecraft:custom_name"]),
            '"projectile child"',
        )
        self.assertEqual(len(self.audit["axolotl_variants"]), 1)

    def test_clipboard_hover_event_is_rewritten_and_icon_is_traversed(self):
        hover = compound(
            action=nbt.TAG_String("show_item"),
            id=nbt.TAG_String("minecraft:activator_rail"),
            count=nbt.TAG_Int(1),
        )
        translated = compound(
            translate=nbt.TAG_String("block.minecraft.activator_rail"),
            hover_event=hover,
        )
        text = compound(text=nbt.TAG_String(""), extra=tag_list(nbt.TAG_Compound, translated))
        icon = item("minecraft:activator_rail")
        entry = compound(
            checked=nbt.TAG_Byte(0),
            icon=icon,
            item_amount=nbt.TAG_Int(1),
            text=text,
        )
        page = tag_list(nbt.TAG_Compound, entry)
        pages = tag_list(nbt.TAG_List, page)
        clipboard = item("create:clipboard")
        clipboard["components"] = compound()
        clipboard["components"]["create:clipboard_content"] = compound(
            type=nbt.TAG_String("written"),
            pages=pages,
            read_only=nbt.TAG_Byte(1),
            previously_opened_page=nbt.TAG_Int(0),
        )
        player = compound(Inventory=tag_list(nbt.TAG_Compound, clipboard))

        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertTrue(changed)
        self.assertTrue(safe)
        style = player["Inventory"][0]["components"]["create:clipboard_content"]["pages"][0][0]["text"]["extra"][0]
        self.assertNotIn("hover_event", style)
        self.assertEqual(str(style["hoverEvent"]["action"]), "show_item")
        self.assertEqual(str(style["hoverEvent"]["contents"]["id"]), "minecraft:activator_rail")
        self.assertEqual(int(style["hoverEvent"]["contents"]["count"].value), 1)
        self.assertEqual(self.audit["clipboard_hovers"][0]["converted"], 1)

    def test_unknown_component_blocks_without_partial_item_mutation(self):
        first = item("minecraft:diamond_sword")
        first["components"] = compound()
        first["components"]["minecraft:custom_name"] = nbt.TAG_String("would convert")
        second = item("minecraft:stone")
        second["components"] = compound()
        second["components"]["future:unknown"] = nbt.TAG_Int(1)
        player = compound(Inventory=tag_list(nbt.TAG_Compound, first, second))
        before = converter.comparable_tag(player)

        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertFalse(changed)
        self.assertFalse(safe)
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertEqual(self.audit["unsupported_player_items"][0]["component"], "future:unknown")

    def test_malformed_container_and_unknown_axolotl_variant_block(self):
        bucket = item("minecraft:axolotl_bucket")
        bucket["components"] = compound()
        bucket["components"]["minecraft:axolotl/variant"] = nbt.TAG_String("future_variant")
        box = item("minecraft:shulker_box")
        box["components"] = compound()
        box["components"]["minecraft:container"] = tag_list(
            nbt.TAG_Compound,
            compound(slot=nbt.TAG_String("bad"), item=bucket),
        )
        player = compound(Inventory=tag_list(nbt.TAG_Compound, box))
        before = converter.comparable_tag(player)

        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertFalse(changed)
        self.assertFalse(safe)
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertIn("container slot", self.audit["unsupported_player_items"][0]["reason"])

    def test_unknown_axolotl_variant_blocks_without_guessing(self):
        bucket = item("minecraft:axolotl_bucket")
        bucket["components"] = compound()
        bucket["components"]["minecraft:axolotl/variant"] = nbt.TAG_String("future_variant")
        player = compound(EnderItems=tag_list(nbt.TAG_Compound, bucket))
        before = converter.comparable_tag(player)

        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertFalse(changed)
        self.assertFalse(safe)
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertIn("unknown or malformed axolotl variant", self.audit["unsupported_player_items"][0]["reason"])

    def test_whole_player_conversion_is_transactional_but_reports_all_blockers(self):
        named = item("minecraft:diamond_sword")
        named["components"] = compound()
        named["components"]["minecraft:custom_name"] = nbt.TAG_String("would convert")
        player = compound(
            Inventory=tag_list(nbt.TAG_Compound, named),
            respawn=compound(
                pos=int_array(1, 70, 2),
                yaw=nbt.TAG_Float(0.0),
                pitch=nbt.TAG_Float(12.0),
                dimension=nbt.TAG_String("minecraft:overworld"),
                forced=nbt.TAG_Byte(0),
                future_field=nbt.TAG_Int(1),
            ),
        )
        before = converter.comparable_tag(player)

        self.assertFalse(converter.convert_player(player, self.path, self.audit, Path("game")))
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertEqual(len(self.audit["item_text_components"]), 1)
        self.assertEqual(len(self.audit["unsupported_player_respawns"]), 1)

    def test_source_missing_schematic_is_preserved_as_inherited_warning(self):
        schematic = item("create:schematic")
        schematic["components"] = compound()
        schematic["components"]["create:schematic_owner"] = nbt.TAG_String("SyntheticOwner")
        schematic["components"]["create:schematic_file"] = nbt.TAG_String("niko.nbt")
        player = compound(Inventory=tag_list(nbt.TAG_Compound, schematic))
        before = converter.comparable_tag(player)
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            game_dir = Path(temp)
            changed, safe = converter.convert_player_items(player, self.path, self.audit, game_dir)
        self.assertFalse(changed)
        self.assertTrue(safe)
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertEqual(self.audit["unsupported_player_items"], [])
        self.assertEqual(len(self.audit["inherited_missing_schematic_files"]), 1)
        self.assertFalse(self.audit["inherited_missing_schematic_files"][0]["source_exists"])

    def test_existing_schematic_dependency_passes_and_is_audited(self):
        schematic = item("create:schematic")
        schematic["components"] = compound()
        schematic["components"]["create:schematic_owner"] = nbt.TAG_String("SyntheticOwner")
        schematic["components"]["create:schematic_file"] = nbt.TAG_String("niko.nbt")
        player = compound(Inventory=tag_list(nbt.TAG_Compound, schematic))
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            game_dir = Path(temp)
            target = game_dir / "schematics" / "uploaded" / "SyntheticOwner" / "niko.nbt"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"fixture")
            changed, safe = converter.convert_player_items(player, self.path, self.audit, game_dir)
        self.assertFalse(changed)
        self.assertTrue(safe)
        self.assertEqual(len(self.audit["schematic_files"]), 1)
        self.assertEqual(self.audit["schematic_files"][0]["source_size"], 7)
        self.assertEqual(
            self.audit["schematic_files"][0]["source_sha256"],
            hashlib.sha256(b"fixture").hexdigest(),
        )

    def test_source_missing_but_explicit_target_exists_is_blocked(self):
        schematic = item("create:schematic")
        schematic["components"] = compound()
        schematic["components"]["create:schematic_owner"] = nbt.TAG_String("SyntheticOwner")
        schematic["components"]["create:schematic_file"] = nbt.TAG_String("niko.nbt")
        player = compound(Inventory=tag_list(nbt.TAG_Compound, schematic))
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            source_dir = Path(temp) / "source"
            target_dir = Path(temp) / "target"
            target = target_dir / "schematics" / "uploaded" / "SyntheticOwner" / "niko.nbt"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"unexpected")
            self.audit["target_game_dir"] = str(target_dir)
            changed, safe = converter.convert_player_items(player, self.path, self.audit, source_dir)
        self.assertFalse(changed)
        self.assertFalse(safe)
        self.assertEqual(len(self.audit["inherited_missing_schematic_files"]), 1)
        self.assertTrue(self.audit["inherited_missing_schematic_files"][0]["target_exists"])
        self.assertIn("source schematic is missing but target dependency exists", self.audit["unsupported_player_items"][0]["reason"])

    def test_explicit_target_schematic_must_exist_and_match_source(self):
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        for target_payload, expected_safe in ((None, False), (b"different", False), (b"fixture", True)):
            with self.subTest(target_payload=target_payload):
                schematic = item("create:schematic")
                schematic["components"] = compound()
                schematic["components"]["create:schematic_owner"] = nbt.TAG_String("SyntheticOwner")
                schematic["components"]["create:schematic_file"] = nbt.TAG_String("niko.nbt")
                player = compound(Inventory=tag_list(nbt.TAG_Compound, schematic))
                with tempfile.TemporaryDirectory(dir=base) as temp:
                    source_dir = Path(temp) / "source"
                    target_dir = Path(temp) / "target"
                    source = source_dir / "schematics" / "uploaded" / "SyntheticOwner" / "niko.nbt"
                    target = target_dir / "schematics" / "uploaded" / "SyntheticOwner" / "niko.nbt"
                    source.parent.mkdir(parents=True)
                    source.write_bytes(b"fixture")
                    if target_payload is not None:
                        target.parent.mkdir(parents=True)
                        target.write_bytes(target_payload)
                    audit = converter.new_audit(Path("fixture"), 100, target_dir)
                    changed, safe = converter.convert_player_items(player, self.path, audit, source_dir)
                self.assertFalse(changed)
                self.assertEqual(safe, expected_safe)
                if expected_safe:
                    self.assertTrue(audit["schematic_files"][0]["target_matches_source"])
                    self.assertEqual(audit["unsupported_player_items"], [])
                else:
                    self.assertEqual(len(audit["unsupported_player_items"]), 1)

    def test_schematic_path_validation_remains_fail_closed(self):
        schematic = item("create:schematic")
        schematic["components"] = compound()
        schematic["components"]["create:schematic_owner"] = nbt.TAG_String("../SyntheticOwner")
        schematic["components"]["create:schematic_file"] = nbt.TAG_String("niko.nbt")
        player = compound(Inventory=tag_list(nbt.TAG_Compound, schematic))
        changed, safe = converter.convert_player_items(player, self.path, self.audit, Path("game"))
        self.assertFalse(changed)
        self.assertFalse(safe)
        self.assertIn("safe single path segment", self.audit["unsupported_player_items"][0]["reason"])

    def test_functional_schematic_gate_promotes_inherited_warning_only_when_requested(self):
        warning = {"reason": "source schematic missing"}
        self.audit["inherited_missing_schematic_files"].append(warning)
        self.assertNotIn(warning, converter.collect_preflight_blockers(self.audit, False))
        self.assertIn(warning, converter.collect_preflight_blockers(self.audit, True))

    def test_player_scan_uses_explicit_source_dir_when_world_is_in_target_dir(self):
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            source_dir = Path(temp) / "source"
            target_dir = Path(temp) / "target"
            world = target_dir / "world"
            player_dir = world / "playerdata"
            player_dir.mkdir(parents=True)
            relative = Path("schematics") / "uploaded" / "SyntheticOwner" / "niko.nbt"
            for game_dir in (source_dir, target_dir):
                dependency = game_dir / relative
                dependency.parent.mkdir(parents=True)
                dependency.write_bytes(b"same fixture")

            schematic = item("create:schematic")
            schematic["components"] = compound()
            schematic["components"]["create:schematic_owner"] = nbt.TAG_String("SyntheticOwner")
            schematic["components"]["create:schematic_file"] = nbt.TAG_String("niko.nbt")
            root = nbt.NBTFile()
            root["Inventory"] = tag_list(nbt.TAG_Compound, schematic)
            root.write_file(filename=str(player_dir / self.path.name))

            audit = converter.new_audit(
                world,
                100,
                target_game_dir=target_dir,
                source_game_dir=source_dir,
            )
            converter.process_players(world, True, audit)
        self.assertEqual(audit["unsupported_player_items"], [])
        self.assertEqual(audit["inherited_missing_schematic_files"], [])
        self.assertEqual(len(audit["schematic_files"]), 1)
        self.assertTrue(audit["schematic_files"][0]["target_matches_source"])
        self.assertEqual(audit["schematic_files"][0]["source_resolved"], str(source_dir / relative))

    def test_equipment_collision_is_fail_closed(self):
        existing = item("minecraft:elytra")
        existing["Slot"] = nbt.TAG_Byte(102)
        player = compound(
            Inventory=tag_list(nbt.TAG_Compound, existing),
            equipment=compound(chest=item("minecraft:netherite_chestplate")),
        )
        before = converter.comparable_tag(player)
        self.assertFalse(converter.convert_player_equipment(player, self.path, self.audit))
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertEqual(len(self.audit["unsupported_player_equipment"]), 1)

    def test_zero_pitch_respawn_maps_to_legacy_fields(self):
        player = compound(respawn=compound(
            pos=int_array(12, 70, -4),
            yaw=nbt.TAG_Float(45.0),
            pitch=nbt.TAG_Float(0.0),
            dimension=nbt.TAG_String("minecraft:overworld"),
            forced=nbt.TAG_Byte(1),
        ))
        self.assertTrue(converter.convert_player_respawn(player, self.path, self.audit))
        self.assertNotIn("respawn", player)
        self.assertEqual([int(player[key].value) for key in ("SpawnX", "SpawnY", "SpawnZ")], [12, 70, -4])
        self.assertEqual(float(player["SpawnAngle"].value), 45.0)
        self.assertEqual(str(player["SpawnDimension"]), "minecraft:overworld")
        self.assertEqual(int(player["SpawnForced"].value), 1)
        self.assertEqual(float(player[converter.PLAYER_RESPAWN_PITCH_KEY].value), 0.0)

    def test_nonzero_respawn_pitch_maps_to_compatibility_field(self):
        player = compound(respawn=compound(
            pos=int_array(12, 70, -4),
            yaw=nbt.TAG_Float(45.0),
            pitch=nbt.TAG_Float(17.5),
            dimension=nbt.TAG_String("minecraft:overworld"),
            forced=nbt.TAG_Byte(0),
        ))
        self.assertTrue(converter.convert_player_respawn(player, self.path, self.audit))
        self.assertNotIn("respawn", player)
        self.assertEqual(float(player[converter.PLAYER_RESPAWN_PITCH_KEY].value), 17.5)
        self.assertEqual(self.audit["unsupported_player_respawns"], [])

    def test_conflicting_existing_respawn_pitch_is_fail_closed(self):
        player = compound(respawn=compound(
            pos=int_array(12, 70, -4),
            yaw=nbt.TAG_Float(45.0),
            pitch=nbt.TAG_Float(17.5),
            dimension=nbt.TAG_String("minecraft:overworld"),
            forced=nbt.TAG_Byte(0),
        ))
        player[converter.PLAYER_RESPAWN_PITCH_KEY] = nbt.TAG_Float(-2.0)
        before = converter.comparable_tag(player)
        self.assertFalse(converter.convert_player_respawn(player, self.path, self.audit))
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertIn("conflicts", self.audit["unsupported_player_respawns"][0]["reason"])

    def test_legacy_player_without_modern_respawn_is_unchanged(self):
        player = compound(
            SpawnX=nbt.TAG_Int(4),
            SpawnY=nbt.TAG_Int(70),
            SpawnZ=nbt.TAG_Int(8),
            SpawnAngle=nbt.TAG_Float(20.0),
            SpawnDimension=nbt.TAG_String("minecraft:overworld"),
            SpawnForced=nbt.TAG_Byte(0),
        )
        before = converter.comparable_tag(player)
        self.assertFalse(converter.convert_player_respawn(player, self.path, self.audit))
        self.assertEqual(converter.comparable_tag(player), before)
        self.assertNotIn(converter.PLAYER_RESPAWN_PITCH_KEY, player)

    def test_player_file_conversion_is_atomic_and_idempotent(self):
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temp:
            world = Path(temp) / "world"
            player_dir = world / "playerdata"
            player_dir.mkdir(parents=True)
            path = player_dir / self.path.name
            root = nbt.NBTFile()
            root["SelectedItemSlot"] = nbt.TAG_Int(0)
            root["Inventory"] = tag_list(nbt.TAG_Compound)
            root["equipment"] = compound(head=item("minecraft:diamond_helmet"))
            root.write_file(filename=str(path))

            first = converter.new_audit(world, 100)
            converter.process_players(world, False, first)
            self.assertEqual(len(first["players"]), 1)
            converted = nbt.NBTFile(filename=str(path))
            self.assertNotIn("equipment", converted)
            self.assertEqual(converter.inventory_slot(converted["Inventory"][0]), 103)

            before = path.read_bytes()
            second = converter.new_audit(world, 100)
            converter.process_players(world, False, second)
            self.assertEqual(len(second["players"]), 0)
            self.assertEqual(path.read_bytes(), before)


class RuntimeCapabilityTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)

    def tearDown(self):
        self.temp.cleanup()

    def write_compat_jar(self, capabilities=None, include_marker=True):
        capabilities = capabilities or sorted(converter.WAYPOINT_FIRE_REQUIRED_CAPABILITIES)
        path = Path(self.temp.name) / "waypoint-fire-equivalence.jar"
        marker = {
            "schema": 1,
            "mod_id": converter.WAYPOINT_FIRE_MOD_ID,
            "minecraft_version": "1.21.1",
            "capabilities": capabilities,
        }
        metadata = (
            'modLoader="javafml"\n'
            'loaderVersion="[4,)"\n'
            'license="MIT"\n'
            '[[mods]]\n'
            f'modId="{converter.WAYPOINT_FIRE_MOD_ID}"\n'
            'version="test"\n'
            'displayName="test"\n'
            f'[[dependencies.{converter.WAYPOINT_FIRE_MOD_ID}]]\n'
            'modId="neoforge"\n'
            'type="required"\n'
            'versionRange="[21.1,)"\n'
            'ordering="NONE"\n'
            'side="BOTH"\n'
            f'[[dependencies.{converter.WAYPOINT_FIRE_MOD_ID}]]\n'
            'modId="minecraft"\n'
            'type="required"\n'
            'versionRange="[1.21.1,1.21.2)"\n'
            'ordering="NONE"\n'
            'side="BOTH"\n'
            '[[mixins]]\n'
            'config="waypoint_fire_equivalence.mixins.json"\n'
        )
        mixin_config = {
            "required": True,
            "package": "com.bmt.waypointfire.mixin",
            "mixins": sorted(converter.WAYPOINT_FIRE_REQUIRED_MIXINS),
        }
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("META-INF/neoforge.mods.toml", metadata)
            if include_marker:
                archive.writestr(converter.WAYPOINT_FIRE_MARKER, json.dumps(marker))
            archive.writestr("waypoint_fire_equivalence.mixins.json", json.dumps(mixin_config))
            for class_name in converter.WAYPOINT_FIRE_REQUIRED_CLASSES:
                archive.writestr(class_name, b"\xca\xfe\xba\xbe" + b"\x00" * 32)
        return path

    def test_explicit_marker_declares_runtime_capability(self):
        path = self.write_compat_jar()
        expected_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        record = converter.inspect_waypoint_fire_compat_jar(path, expected_sha256)
        self.assertEqual(record["capability"], converter.WAYPOINT_FIRE_CAPABILITY)
        self.assertEqual(record["mod_id"], converter.WAYPOINT_FIRE_MOD_ID)
        self.assertEqual(record["size"], path.stat().st_size)
        self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_missing_marker_capability_is_rejected(self):
        capabilities = sorted(
            converter.WAYPOINT_FIRE_REQUIRED_CAPABILITIES
            - {"canonical_fire_spread_radius_rule"}
        )
        path = self.write_compat_jar(capabilities)
        with self.assertRaisesRegex(ValueError, "canonical_fire_spread_radius_rule"):
            converter.inspect_waypoint_fire_compat_jar(
                path,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_mod_id_without_explicit_marker_is_rejected(self):
        path = self.write_compat_jar(include_marker=False)
        with self.assertRaisesRegex(ValueError, "capabilities.json"):
            converter.inspect_waypoint_fire_compat_jar(
                path,
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_hash_and_target_deployment_are_both_enforced(self):
        path = self.write_compat_jar()
        expected_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            converter.inspect_waypoint_fire_compat_jar(path, "0" * 64)

        target = Path(self.temp.name) / "target"
        (target / "mods").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "not deployed"):
            converter.inspect_waypoint_fire_compat_jar(path, expected_sha256, target)
        deployed = target / "mods" / path.name
        deployed.write_bytes(path.read_bytes())
        record = converter.inspect_waypoint_fire_compat_jar(path, expected_sha256, target)
        self.assertEqual(record["target_deployment"], str(deployed.resolve()))

        disabled = path.with_suffix(".jar.disabled")
        disabled.write_bytes(path.read_bytes())
        with self.assertRaisesRegex(ValueError, "enabled .jar suffix"):
            converter.inspect_waypoint_fire_compat_jar(disabled, expected_sha256)


class LevelConversionTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.world = Path(self.temp.name) / "world"
        self.world.mkdir()
        (self.world.parent / "server.properties").write_text(
            "difficulty=easy\n"
            "allow-nether=true\n"
            "enable-command-block=false\n"
            "pvp=true\n"
            "spawn-monsters=true\n",
            encoding="ascii",
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_level(
        self,
        dimension="minecraft:overworld",
        pitch=0.0,
        rules=None,
        difficulty=3,
        target_rules=None,
    ):
        root = nbt.NBTFile()
        data = compound(
            Time=nbt.TAG_Long(100),
            Difficulty=nbt.TAG_Byte(difficulty),
            spawn=compound(
                pos=int_array(16, 65, -2),
                yaw=nbt.TAG_Float(22.5),
                pitch=nbt.TAG_Float(pitch),
                dimension=nbt.TAG_String(dimension),
            ),
        )
        if rules is not None:
            data["game_rules"] = compound(**rules)
        if target_rules is not None:
            data["GameRules"] = compound(**target_rules)
        root["Data"] = data
        root.write_file(filename=str(self.world / "level.dat"))

    def load_data(self):
        root = nbt.NBTFile(filename=str(self.world / "level.dat"))
        return root["Data"]

    def test_spawn_rules_difficulty_and_server_properties_are_idempotent(self):
        self.write_level(rules={
            "minecraft:keep_inventory": nbt.TAG_Byte(1),
            "minecraft:respawn_radius": nbt.TAG_Int(0),
            "minecraft:players_nether_portal_creative_delay": nbt.TAG_Int(0),
            "minecraft:elytra_movement_check": nbt.TAG_Byte(1),
            "minecraft:raids": nbt.TAG_Byte(1),
            "minecraft:command_blocks_work": nbt.TAG_Byte(1),
            "minecraft:pvp": nbt.TAG_Byte(1),
            "minecraft:allow_entering_nether_using_portals": nbt.TAG_Byte(1),
            "minecraft:spawn_monsters": nbt.TAG_Byte(1),
            "mishanguc:force_placing_tool_access": nbt.TAG_String("CREATIVE_ONLY"),
        })
        audit = converter.new_audit(self.world, 100)
        self.assertTrue(converter.convert_level_dat(self.world, False, audit))
        self.assertEqual(audit["level_blockers"], [])
        data = self.load_data()
        self.assertNotIn("spawn", data)
        self.assertEqual([int(data[key].value) for key in ("SpawnX", "SpawnY", "SpawnZ")], [16, 65, -2])
        self.assertEqual(float(data["SpawnAngle"].value), 22.5)
        self.assertEqual(int(data["Difficulty"].value), 3)
        self.assertNotIn("game_rules", data)
        rules = data["GameRules"]
        self.assertEqual(str(rules["keepInventory"]), "true")
        self.assertEqual(str(rules["spawnRadius"]), "0")
        self.assertEqual(str(rules["playersNetherPortalCreativeDelay"]), "0")
        self.assertEqual(str(rules["disableElytraMovementCheck"]), "false")
        self.assertEqual(str(rules["disableRaids"]), "false")
        self.assertEqual(str(rules["mishanguc:force_placing_tool_access"]), "CREATIVE_ONLY")
        properties = (self.world.parent / "server.properties").read_text(encoding="ascii")
        self.assertIn("difficulty=hard\n", properties)
        self.assertIn("enable-command-block=true\n", properties)

        level_before = (self.world / "level.dat").read_bytes()
        properties_before = (self.world.parent / "server.properties").read_bytes()
        second = converter.new_audit(self.world, 100)
        self.assertFalse(converter.convert_level_dat(self.world, False, second))
        self.assertEqual((self.world / "level.dat").read_bytes(), level_before)
        self.assertEqual((self.world.parent / "server.properties").read_bytes(), properties_before)

    def test_properties_commit_first_keeps_level_source_recoverable(self):
        self.write_level(rules={
            "minecraft:command_blocks_work": nbt.TAG_Byte(1),
            "minecraft:keep_inventory": nbt.TAG_Byte(1),
        })
        real_replace = os.replace

        def fail_level_replace(source, target):
            if Path(target).name == "level.dat":
                raise OSError("fixture interruption before level.dat commit")
            return real_replace(source, target)

        audit = converter.new_audit(self.world, 100)
        with mock.patch.object(converter.os, "replace", side_effect=fail_level_replace):
            with self.assertRaisesRegex(OSError, "fixture interruption"):
                converter.convert_level_dat(self.world, False, audit)

        # The idempotent property side committed, while the authoritative
        # modern rule tree remains available for recovery.
        self.assertIn("enable-command-block=true\n", (self.world.parent / "server.properties").read_text(encoding="ascii"))
        self.assertIn("game_rules", self.load_data())

        recovery = converter.new_audit(self.world, 100)
        self.assertTrue(converter.convert_level_dat(self.world, False, recovery))
        self.assertNotIn("game_rules", self.load_data())
        self.assertEqual(recovery["unsupported_game_rules"], [])

    def test_non_overworld_spawn_is_fail_closed(self):
        self.write_level(dimension="minecraft:the_nether", rules={})
        before = (self.world / "level.dat").read_bytes()
        audit = converter.new_audit(self.world, 100)
        self.assertFalse(converter.convert_level_dat(self.world, False, audit))
        self.assertEqual((self.world / "level.dat").read_bytes(), before)
        self.assertIn("not overworld", audit["level_blockers"][0]["reason"])

    def test_nonzero_spawn_pitch_is_fail_closed(self):
        self.write_level(pitch=12.5, rules={})
        before = (self.world / "level.dat").read_bytes()
        audit = converter.new_audit(self.world, 100)
        self.assertFalse(converter.convert_level_dat(self.world, False, audit))
        self.assertEqual((self.world / "level.dat").read_bytes(), before)
        self.assertIn("pitch", audit["level_blockers"][0]["reason"])

    def test_unknown_minecraft_rule_is_fail_closed(self):
        self.write_level(rules={"minecraft:locator_bar": nbt.TAG_Byte(1)})
        before = (self.world / "level.dat").read_bytes()
        audit = converter.new_audit(self.world, 100)
        self.assertFalse(converter.convert_level_dat(self.world, False, audit))
        self.assertEqual((self.world / "level.dat").read_bytes(), before)
        self.assertEqual(audit["unsupported_game_rules"][0]["id"], "minecraft:locator_bar")

    def test_waypoint_fire_rules_use_exact_namespaced_string_keys(self):
        self.write_level(rules={
            "minecraft:locator_bar": nbt.TAG_Byte(1),
            "minecraft:fire_spread_radius_around_player": nbt.TAG_Int(128),
        })
        audit = converter.new_audit(
            self.world,
            100,
            runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
        )
        self.assertTrue(converter.convert_level_dat(self.world, False, audit))
        data = self.load_data()
        self.assertNotIn("game_rules", data)
        self.assertEqual(str(data["GameRules"]["minecraft:locator_bar"]), "true")
        self.assertEqual(
            str(data["GameRules"]["minecraft:fire_spread_radius_around_player"]),
            "128",
        )
        self.assertEqual(audit["unsupported_game_rules"], [])

        before = (self.world / "level.dat").read_bytes()
        second = converter.new_audit(
            self.world,
            100,
            runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
        )
        self.assertFalse(converter.convert_level_dat(self.world, False, second))
        self.assertEqual((self.world / "level.dat").read_bytes(), before)
        self.assertEqual(second["game_rules"], [])

    def test_existing_equal_rule_merges_but_conflict_blocks_transactionally(self):
        self.write_level(
            rules={"minecraft:keep_inventory": nbt.TAG_Byte(1)},
            target_rules={"keepInventory": nbt.TAG_String("TRUE")},
        )
        equal_audit = converter.new_audit(self.world, 100)
        self.assertTrue(converter.convert_level_dat(self.world, False, equal_audit))
        self.assertEqual(equal_audit["game_rule_collisions"][0]["resolution"], "merge_equal")
        self.assertNotIn("game_rules", self.load_data())
        self.assertEqual(str(self.load_data()["GameRules"]["keepInventory"]), "true")

        self.write_level(
            rules={"minecraft:keep_inventory": nbt.TAG_Byte(1)},
            target_rules={"keepInventory": nbt.TAG_String("false")},
        )
        before = (self.world / "level.dat").read_bytes()
        conflict_audit = converter.new_audit(self.world, 100)
        self.assertFalse(converter.convert_level_dat(self.world, False, conflict_audit))
        self.assertEqual((self.world / "level.dat").read_bytes(), before)
        self.assertEqual(conflict_audit["game_rule_collisions"][0]["resolution"], "blocked_conflict")
        self.assertEqual(conflict_audit["unsupported_game_rules"][0]["target_id"], "keepInventory")
        data = self.load_data()
        self.assertIn("game_rules", data)
        self.assertEqual(str(data["GameRules"]["keepInventory"]), "false")

    def test_collision_comparison_uses_java_parser_and_canonicalizes(self):
        unsafe = (
            ("minecraft:keep_inventory", nbt.TAG_Byte(1), "keepInventory", "1"),
            ("minecraft:keep_inventory", nbt.TAG_Byte(1), "keepInventory", " true "),
            ("minecraft:respawn_radius", nbt.TAG_Int(1000), "spawnRadius", "1_000"),
        )
        for source_id, source_value, target_id, target_value in unsafe:
            with self.subTest(target_value=target_value):
                data = compound(
                    game_rules=compound(**{source_id: source_value}),
                    GameRules=compound(**{target_id: nbt.TAG_String(target_value)}),
                )
                before = converter.comparable_tag(data)
                audit = converter.new_audit(self.world, 100)
                changed, _ = converter.convert_game_rules(data, audit)
                self.assertFalse(changed)
                self.assertEqual(converter.comparable_tag(data), before)
                self.assertEqual(audit["game_rule_collisions"][0]["resolution"], "blocked_conflict")

        data = compound(
            game_rules=compound(**{"minecraft:respawn_radius": nbt.TAG_Int(10)}),
            GameRules=compound(spawnRadius=nbt.TAG_String("+010")),
        )
        audit = converter.new_audit(self.world, 100)
        changed, _ = converter.convert_game_rules(data, audit)
        self.assertTrue(changed)
        self.assertNotIn("game_rules", data)
        self.assertEqual(str(data["GameRules"]["spawnRadius"]), "10")

    def test_waypoint_rule_conflict_is_not_resolved_by_target_or_source_wins(self):
        self.write_level(
            rules={"minecraft:locator_bar": nbt.TAG_Byte(1)},
            target_rules={"minecraft:locator_bar": nbt.TAG_String("false")},
        )
        before = (self.world / "level.dat").read_bytes()
        audit = converter.new_audit(
            self.world,
            100,
            runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
        )
        self.assertFalse(converter.convert_level_dat(self.world, False, audit))
        self.assertEqual((self.world / "level.dat").read_bytes(), before)
        self.assertEqual(audit["game_rule_collisions"][0]["resolution"], "blocked_conflict")

    def test_formal_1_21_1_rules_without_modern_source_tree_are_untouched(self):
        data = compound(GameRules=compound(
            doFireTick=nbt.TAG_String("false"),
            **{
                "minecraft:locator_bar": nbt.TAG_String("false"),
                "minecraft:fire_spread_radius_around_player": nbt.TAG_String("0"),
            },
        ))
        before = converter.comparable_tag(data)
        audit = converter.new_audit(
            self.world,
            100,
            runtime_capabilities=[converter.WAYPOINT_FIRE_CAPABILITY],
        )
        changed, properties = converter.convert_game_rules(data, audit)
        self.assertFalse(changed)
        self.assertEqual(properties, {})
        self.assertEqual(converter.comparable_tag(data), before)
        self.assertEqual(audit["game_rules"], [])


class RegionMultiprocessingTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("MIGRATION_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.world = Path(self.temp.name) / "world"
        for index in range(4):
            write_entity_region(
                self.world / "entities" / f"r.{index}.0.mca"
            )

    def tearDown(self):
        self.temp.cleanup()

    def run_regions(self, dry_run, workers):
        audit = converter.new_audit(self.world, 100)
        converter.process_regions(
            self.world,
            set(),
            100,
            dry_run,
            audit,
            include_blocks=False,
            workers=workers,
            phase="test",
        )
        return audit

    def test_four_workers_match_serial_audit(self):
        serial = self.run_regions(True, 1)
        parallel = self.run_regions(True, 4)
        self.assertEqual(parallel, serial)
        json.dumps(parallel)

    def test_multi_region_conversion_is_idempotent(self):
        first = self.run_regions(False, 4)
        self.assertEqual(len(first["regions"]), 4)
        self.assertTrue(all(record["writes"] == 1 for record in first["regions"]))
        for path in sorted((self.world / "entities").glob("*.mca")):
            converted = first_region_entity(path)
            self.assertEqual(str(converted["id"]), "minecraft:boat")
            self.assertEqual(str(converted["Type"]), "oak")

        before = {
            path.name: path.read_bytes()
            for path in sorted((self.world / "entities").glob("*.mca"))
        }
        second = self.run_regions(False, 4)
        self.assertEqual(second["regions"], [])
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in sorted((self.world / "entities").glob("*.mca"))
            },
            before,
        )

    def test_late_malformed_preflight_causes_zero_writes(self):
        malformed = self.world / "entities" / "r.9.0.mca"
        malformed.write_bytes(b"not-an-anvil-region")
        originals = {
            path.name: path.read_bytes()
            for path in sorted((self.world / "entities").glob("r.[0-3].0.mca"))
        }
        report = Path(self.temp.name) / "blocked.json"
        argv = [
            "convert_world_nbt.py",
            "convert",
            "--world",
            str(self.world),
            "--report",
            str(report),
            "--workers",
            "4",
            "--entities-only",
        ]
        with mock.patch.object(sys, "argv", argv):
            with self.assertRaisesRegex(SystemExit, "preflight blocked conversion"):
                converter.main()

        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in sorted((self.world / "entities").glob("r.[0-3].0.mca"))
            },
            originals,
        )
        blocked = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(blocked["malformed_regions"][0]["path"], "entities/r.9.0.mca")

    def test_worker_exception_fails_conversion_pass(self):
        (self.world / "entities" / "r.9.0.mca").write_bytes(b"malformed")
        with self.assertRaisesRegex(RuntimeError, "region worker failed.*r.9.0.mca"):
            self.run_regions(False, 4)


if __name__ == "__main__":
    unittest.main()
