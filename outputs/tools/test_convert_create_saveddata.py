from __future__ import annotations

import unittest
from pathlib import Path

from nbt import nbt

import convert_create_saveddata as converter


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


def double_list(*values):
    return tag_list(nbt.TAG_Double, *(nbt.TAG_Double(value) for value in values))


def source_fluid(identifier, amount, maximum):
    return compound(
        id=nbt.TAG_String(identifier),
        amount=nbt.TAG_Int(amount),
        components=compound(**{
            "create:fluid_max_capacity": nbt.TAG_Int(maximum),
        }),
    )


def source_root(custom_name=None):
    stack = compound(id=nbt.TAG_String("minecraft:diamond"), count=nbt.TAG_Int(1))
    if custom_name is not None:
        components = nbt.TAG_Compound()
        components["minecraft:custom_name"] = nbt.TAG_String(custom_name)
        stack["components"] = components
    promise = compound(
        ticks_existed=nbt.TAG_Int(25),
        promised_stack=compound(item_stack=stack, count=nbt.TAG_Int(64)),
    )
    network = compound(
        Id=int_array(1, 2, 3, 4),
        Owner=int_array(5, 6, 7, 8),
        Locked=nbt.TAG_Byte(1),
        Promises=compound(List=tag_list(nbt.TAG_Compound, promise)),
        Links=tag_list(
            nbt.TAG_Compound,
            compound(pos=int_array(10, 64, -3), dimension=nbt.TAG_String("minecraft:overworld")),
            compound(pos=int_array(4, 70, 9), dimension=nbt.TAG_String("minecraft:the_nether")),
        ),
    )
    root = nbt.NBTFile()
    root["DataVersion"] = nbt.TAG_Int(4671)
    root["data"] = tag_list(nbt.TAG_Compound, network)
    return root


def source_tracks_root():
    condition = compound(
        Id=nbt.TAG_String("create:delay"),
        Data=compound(Value=nbt.TAG_Int(20)),
    )
    schedule_entry = compound(
        Instruction=compound(
            Id=nbt.TAG_String("create:destination"),
            Data=compound(Text=nbt.TAG_String("Track Station")),
        ),
        Conditions=tag_list(
            nbt.TAG_List,
            tag_list(nbt.TAG_Compound, condition),
        ),
    )
    location_a = compound(Pos=int_array(10, 64, -3), D=nbt.TAG_Int(0))
    location_b = compound(Pos=int_array(11, 64, -3), D=nbt.TAG_Int(0))
    bezier = compound(
        Positions=tag_list(
            nbt.TAG_Int_Array,
            int_array(10, 64, -3),
            int_array(11, 64, -3),
        ),
        Starts=tag_list(
            nbt.TAG_List,
            double_list(10.0, 64.0, -2.5),
            double_list(11.0, 64.0, -2.5),
        ),
        Axes=tag_list(
            nbt.TAG_List,
            double_list(1.0, 0.0, 0.0),
            double_list(-1.0, 0.0, 0.0),
        ),
        Normals=tag_list(
            nbt.TAG_List,
            double_list(0.0, 1.0, 0.0),
            double_list(0.0, 1.0, 0.0),
        ),
        Primary=nbt.TAG_Byte(1),
        Girder=nbt.TAG_Byte(0),
        Material=nbt.TAG_String("create:andesite"),
        Smoothing=tag_list(nbt.TAG_Int, nbt.TAG_Int(2), nbt.TAG_Int(3)),
    )
    edge_data = compound(
        Material=nbt.TAG_String("create:andesite"),
        Signals=nbt.TAG_Compound(),
        BezierConnection=bezier,
    )
    node = compound(
        Location=location_a,
        Connections=tag_list(
            nbt.TAG_Compound,
            compound(To=nbt.TAG_Int(1), EdgeData=edge_data),
        ),
    )

    dense_stacks = tag_list(
        nbt.TAG_Compound,
        nbt.TAG_Compound(),
        compound(id=nbt.TAG_String("minecraft:diamond"), count=nbt.TAG_Int(3)),
    )
    source_port = compound(
        address=nbt.TAG_String("factory"),
        offlineBuffer=compound(Size=nbt.TAG_Int(2), Stacks=dense_stacks),
        primed=nbt.TAG_Byte(1),
        restoring=nbt.TAG_Byte(0),
    )
    station = compound(
        Id=int_array(1, 2, 3, 4),
        Name=nbt.TAG_String("Track Station"),
        Ports=compound(
            Keys=tag_list(nbt.TAG_Int_Array, int_array(12, 65, -4)),
            Values=tag_list(nbt.TAG_Compound, source_port),
        ),
    )
    graph = compound(
        Id=int_array(5, 6, 7, 8),
        Nodes=tag_list(nbt.TAG_Compound, node),
        Points=compound(**{
            "create:station": tag_list(nbt.TAG_Compound, station),
            "create:signal": nbt.TAG_List(),
            "create:observer": nbt.TAG_List(),
        }),
    )

    signal_id = "11111111-2222-3333-4444-555555555555"
    connected_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    signal = compound(
        Id=nbt.TAG_String(signal_id),
        Connected=compound(**{connected_id: nbt.TAG_String(signal_id)}),
        Color=nbt.TAG_String("green"),
        Fallback=nbt.TAG_Byte(0),
    )
    positioning = compound(
        RotationAnchors=tag_list(
            nbt.TAG_List,
            double_list(10.5, 64.0, -3.0),
            double_list(11.5, 64.0, -3.0),
        ),
        items=tag_list(
            nbt.TAG_Compound,
            compound(
                pos=int_array(0, 1, -1),
                storage=compound(
                    type=nbt.TAG_String("create:chest"),
                    value=compound(size=nbt.TAG_Int(27), items=compound()),
                ),
            ),
        ),
        fluids=tag_list(
            nbt.TAG_Compound,
            compound(
                pos=int_array(0, 1, 1),
                storage=compound(
                    type=nbt.TAG_String("create:fluid_tank"),
                    capacity=nbt.TAG_Int(1_296_000),
                    fluid=source_fluid("create:milk", 81_000, 81_000),
                ),
            ),
        ),
    )
    contraption = compound(
        DisabledActors=tag_list(nbt.TAG_Compound),
        SubContraptions=compound(),
        AssemblyDirection=nbt.TAG_String("east"),
        CapturedMultiblocks=tag_list(
            nbt.TAG_Compound,
            compound(
                Controller=int_array(7, 8, 9),
                Parts=tag_list(nbt.TAG_Int_Array, int_array(7, 8, 9), int_array(8, 8, 9)),
            ),
        ),
        Blocks=compound(Palette=compound(), BlockList=tag_list(nbt.TAG_Compound)),
        Stalled=nbt.TAG_Byte(0),
        BackControls=nbt.TAG_Byte(0),
        Superglue=tag_list(
            nbt.TAG_List,
            double_list(0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
        ),
        Actors=tag_list(nbt.TAG_Compound),
        BoundsFront=double_list(-1.0, 0.0, -1.0, 2.0, 3.0, 2.0),
        ConductorSeats=tag_list(nbt.TAG_Compound),
        BottomlessSupply=nbt.TAG_Byte(0),
        BackBlazeConductor=nbt.TAG_Byte(0),
        FrontBlazeConductor=nbt.TAG_Byte(0),
        Interactors=tag_list(nbt.TAG_Int_Array, int_array(1, 2, 3)),
        Type=nbt.TAG_String("create:carriage"),
        Anchor=int_array(0, 0, 0),
        FrontControls=nbt.TAG_Byte(0),
        Seats=tag_list(nbt.TAG_Int_Array, int_array(4, 5, 6)),
        SoundQueue=compound(Offset=nbt.TAG_Int(0), Sounds=tag_list(nbt.TAG_Compound)),
        items=tag_list(
            nbt.TAG_Compound,
            compound(
                pos=int_array(2, 0, 0),
                storage=compound(
                    type=nbt.TAG_String("create:simple"),
                    value=compound(size=nbt.TAG_Int(27), items=compound()),
                ),
            ),
        ),
        fluids=tag_list(nbt.TAG_Compound),
    )
    carriage_entity = compound(
        InitialOrientation=nbt.TAG_String("east"),
        Contraption=contraption,
    )
    carriage = compound(
        EntityPositioning=tag_list(nbt.TAG_Compound, positioning),
        Entity=carriage_entity,
    )
    train = compound(
        Name=nbt.TAG_String("没名字的列车"),
        ReservedSignalBlocks=tag_list(nbt.TAG_Int_Array, int_array(1, 2, 3, 4)),
        OccupiedObservers=tag_list(nbt.TAG_Int_Array, int_array(5, 6, 7, 8)),
        Navigation=compound(
            Destination=int_array(1, 2, 3, 4),
            Path=tag_list(
                nbt.TAG_Compound,
                compound(First=location_a, Second=location_b),
            ),
        ),
        Runtime=compound(
            State=nbt.TAG_String("post_transit"),
            Schedule=compound(
                Cyclic=nbt.TAG_Byte(1),
                Entries=tag_list(nbt.TAG_Compound, schedule_entry),
            ),
        ),
        Carriages=tag_list(nbt.TAG_Compound, carriage),
    )
    data = compound(
        RailGraphs=tag_list(nbt.TAG_Compound, graph),
        SignalBlocks=tag_list(nbt.TAG_Compound, signal),
        DimensionPalette=tag_list(
            nbt.TAG_String,
            nbt.TAG_String("minecraft:overworld"),
            nbt.TAG_String("minecraft:the_nether"),
        ),
        Trains=tag_list(nbt.TAG_Compound, train),
    )
    root = nbt.NBTFile()
    root["DataVersion"] = nbt.TAG_Int(4671)
    root["data"] = data
    return root


class LogisticsConversionTests(unittest.TestCase):
    def convert(self, root):
        return converter.convert_logistics_root(root, Path("D:/source"), Path("D:/target"))

    def test_source_format_converts_without_semantic_loss(self):
        source = source_root()
        converted, report = self.convert(source)

        self.assertIsNotNone(converted)
        self.assertEqual(report["status"], "CONVERTED")
        self.assertEqual(report["networks"], 1)
        self.assertEqual(report["links"], 2)
        self.assertEqual(report["promises"], 1)
        self.assertEqual(converter.as_int(converted["DataVersion"]), 3955)
        networks = converted["data"]["LogisticsNetworks"]
        self.assertEqual(len(networks), 1)
        links = networks[0]["Links"]
        self.assertEqual(set(links[0]["Pos"].keys()), {"X", "Y", "Z"})
        self.assertNotIn("Dim", links[0])
        self.assertEqual(str(links[1]["Dim"]), "minecraft:the_nether")
        self.assertIsInstance(source["data"], nbt.TAG_List)
        self.assertEqual(converter.as_int(source["DataVersion"]), 4671)

    def test_target_format_is_idempotent(self):
        first, first_report = self.convert(source_root())
        second, second_report = self.convert(first)

        self.assertIsNotNone(second)
        self.assertEqual(second_report["status"], "ALREADY_1_21_1")
        self.assertEqual(first_report["semantic_sha256"], second_report["semantic_sha256"])
        self.assertEqual(converter.comparable_tag(first), converter.comparable_tag(second))

    def test_item_components_use_shared_converter(self):
        converted, report = self.convert(source_root("named diamond"))

        self.assertIsNotNone(converted)
        self.assertEqual(report["item_stacks_scanned"], 1)
        self.assertEqual(report["item_stacks_changed"], 1)
        stack = converted["data"]["LogisticsNetworks"][0]["Promises"]["List"][0]["promised_stack"]["item_stack"]
        self.assertEqual(str(stack["components"]["minecraft:custom_name"]), '"named diamond"')

    def test_unknown_network_field_blocks_transaction(self):
        source = source_root()
        source["data"][0]["FutureField"] = nbt.TAG_Int(1)
        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertTrue(any(entry["reason"] == "network has unknown fields" for entry in report["blockers"]))
        self.assertIn("FutureField", source["data"][0])

    def test_duplicate_links_block(self):
        source = source_root()
        duplicate = converter.clone_tag(source["data"][0]["Links"][0])
        source["data"][0]["Links"].append(duplicate)
        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "network contains duplicate links" for entry in report["blockers"]))

    def test_target_overworld_dim_is_rejected_as_noncanonical(self):
        converted, _ = self.convert(source_root())
        converted["data"]["LogisticsNetworks"][0]["Links"][0]["Dim"] = nbt.TAG_String("minecraft:overworld")
        result, report = self.convert(converted)

        self.assertIsNone(result)
        self.assertTrue(any(entry["reason"] == "target overworld link must omit Dim" for entry in report["blockers"]))


class TracksConversionTests(unittest.TestCase):
    def convert(self, root):
        return converter.convert_tracks_root(root, Path("D:/source"), Path("D:/target"))

    def test_all_changed_track_schemas_convert(self):
        source = source_tracks_root()
        converted, report = self.convert(source)

        self.assertIsNotNone(converted, report)
        self.assertEqual(report["status"], "CONVERTED")
        self.assertEqual(converter.as_int(converted["DataVersion"]), 3955)
        data = converted["data"]
        self.assertEqual(str(data["DimensionPalette"][1]["Id"]), "minecraft:the_nether")

        signal = data["SignalBlocks"][0]
        self.assertIsInstance(signal["Id"], nbt.TAG_Int_Array)
        self.assertEqual(set(signal["Connected"][0].keys()), {"Key", "Value"})
        self.assertEqual(str(signal["Color"]), "GREEN")
        self.assertEqual(report["signal_color_conversions"], 1)

        edge = data["RailGraphs"][0]["Nodes"][0]["Connections"][0]["EdgeData"]
        self.assertNotIn("BezierConnection", edge)
        self.assertEqual(set(edge["Positions"][0].keys()), {"Pos"})
        self.assertIsInstance(edge["Positions"][0]["Pos"], nbt.TAG_Int_Array)
        for key in ("Starts", "Axes", "Normals"):
            self.assertEqual(set(edge[key][0].keys()), {"V"})
            self.assertEqual(len(edge[key][0]["V"]), 3)
        self.assertEqual(converter.as_int(edge["Smoothing"][1]["V"]), 3)

        train = data["Trains"][0]
        self.assertEqual(str(train["Name"]), '"没名字的列车"')
        self.assertEqual(set(train["ReservedSignalBlocks"][0].keys()), {"Id"})
        self.assertEqual(set(train["OccupiedObservers"][0].keys()), {"Id"})
        self.assertEqual(set(train["Navigation"]["Path"][0].keys()), {"Nodes"})
        self.assertEqual(len(train["Navigation"]["Path"][0]["Nodes"]), 2)
        conditions = train["Runtime"]["Schedule"]["Entries"][0]["Conditions"]
        self.assertIsInstance(conditions[0], nbt.TAG_List)
        self.assertIsInstance(conditions[0][0], nbt.TAG_Compound)
        self.assertEqual(str(train["Runtime"]["State"]), "POST_TRANSIT")
        self.assertEqual(report["schema_counts"]["runtime_state_conversions"], 1)
        anchors = train["Carriages"][0]["EntityPositioning"][0]["RotationAnchors"]
        self.assertEqual(set(anchors[0].keys()), {"V"})
        positioning = train["Carriages"][0]["EntityPositioning"][0]
        self.assertEqual(
            {axis: converter.as_int(positioning["items"][0]["pos"][axis]) for axis in ("X", "Y", "Z")},
            {"X": 0, "Y": 1, "Z": -1},
        )
        mounted_fluid = positioning["fluids"][0]
        self.assertEqual(
            {axis: converter.as_int(mounted_fluid["pos"][axis]) for axis in ("X", "Y", "Z")},
            {"X": 0, "Y": 1, "Z": 1},
        )
        self.assertEqual(converter.as_int(mounted_fluid["storage"]["capacity"]), 16_000)
        self.assertEqual(str(mounted_fluid["storage"]["fluid"]["id"]), "minecraft:milk")
        self.assertEqual(converter.as_int(mounted_fluid["storage"]["fluid"]["amount"]), 1_000)
        self.assertNotIn("components", mounted_fluid["storage"]["fluid"])

        contraption = train["Carriages"][0]["Entity"]["Contraption"]
        self.assertEqual(
            str(train["Carriages"][0]["Entity"]["InitialOrientation"]),
            "EAST",
        )
        self.assertEqual(str(contraption["AssemblyDirection"]), "EAST")
        self.assertTrue(all(isinstance(part, nbt.TAG_Float) for part in contraption["BoundsFront"]))
        self.assertEqual(set(contraption["Seats"][0].keys()), {"Pos"})
        self.assertEqual(set(contraption["Interactors"][0].keys()), {"Pos"})
        self.assertEqual(set(contraption["Superglue"][0].keys()), {"From", "To"})
        self.assertIsInstance(contraption["SubContraptions"], nbt.TAG_List)
        self.assertEqual(set(contraption["CapturedMultiblocks"][0]["Parts"][0].keys()), {"Pos"})
        self.assertEqual(
            {axis: converter.as_int(contraption["items"][0]["pos"][axis]) for axis in ("X", "Y", "Z")},
            {"X": 2, "Y": 0, "Z": 0},
        )
        self.assertEqual(report["schema_counts"]["contraption_bounds"], 1)
        self.assertEqual(report["schema_counts"]["contraption_seats"], 1)
        self.assertEqual(report["schema_counts"]["contraption_interactors"], 1)
        self.assertEqual(report["schema_counts"]["contraption_superglue"], 1)
        self.assertEqual(report["schema_counts"]["captured_multiblock_parts"], 2)
        self.assertEqual(report["schema_counts"]["mounted_item_storage_entries"], 2)
        self.assertEqual(report["schema_counts"]["mounted_fluid_storage_entries"], 1)
        self.assertEqual(report["schema_counts"]["mounted_nonempty_fluid_stacks"], 1)
        self.assertEqual(
            report["initial_orientation_normalizations"],
            [
                {
                    "path": "data.Trains[0].Carriages[0].Entity.InitialOrientation",
                    "source": "east",
                    "target": "EAST",
                }
            ],
        )

        port = data["RailGraphs"][0]["Points"]["create:station"][0]["Ports"][0]
        self.assertEqual(set(port.keys()), {"Address", "OfflineBuffer", "Primed", "Pos"})
        self.assertEqual(set(port["OfflineBuffer"].keys()), {"Items", "Size"})
        self.assertEqual(len(port["OfflineBuffer"]["Items"]), 1)
        self.assertEqual(converter.as_int(port["OfflineBuffer"]["Items"][0]["Slot"]), 1)
        self.assertEqual(str(port["OfflineBuffer"]["Items"][0]["id"]), "minecraft:diamond")

        self.assertEqual(converter.as_int(source["DataVersion"]), 4671)
        self.assertIn(
            "BezierConnection",
            source["data"]["RailGraphs"][0]["Nodes"][0]["Connections"][0]["EdgeData"],
        )

    def test_target_format_is_idempotent(self):
        first, first_report = self.convert(source_tracks_root())
        self.assertIsNotNone(first, first_report)
        second, second_report = self.convert(first)

        self.assertIsNotNone(second, second_report)
        self.assertEqual(second_report["status"], "ALREADY_1_21_1")
        self.assertEqual(first_report["semantic_sha256"], second_report["semantic_sha256"])
        self.assertEqual(converter.comparable_tag(first), converter.comparable_tag(second))

    def test_missing_initial_orientation_blocks_transaction(self):
        source = source_tracks_root()
        del source["data"]["Trains"][0]["Carriages"][0]["Entity"]["InitialOrientation"]

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(
            any(
                entry["reason"] == "contraption InitialOrientation is missing"
                for entry in report["blockers"]
            )
        )

    def test_vertical_initial_orientation_blocks_transaction(self):
        source = source_tracks_root()
        source["data"]["Trains"][0]["Carriages"][0]["Entity"]["InitialOrientation"] = nbt.TAG_String("down")

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(
            any(
                entry["reason"] == "contraption InitialOrientation is not horizontal"
                for entry in report["blockers"]
            )
        )

    def test_mounted_storage_unknown_shape_blocks_transaction(self):
        source = source_tracks_root()
        entry = source["data"]["Trains"][0]["Carriages"][0]["EntityPositioning"][0]["fluids"][0]
        entry["future"] = nbt.TAG_Int(1)
        before = converter.comparable_tag(source)

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertEqual(converter.comparable_tag(source), before)
        self.assertTrue(any("mounted storage entry" in blocker["reason"] for blocker in report["blockers"]))

    def test_mounted_cei_experience_residual_uses_source_floor_semantics(self):
        source = source_tracks_root()
        fluid = source["data"]["Trains"][0]["Carriages"][0]["EntityPositioning"][0]["fluids"][0]["storage"]["fluid"]
        fluid["id"] = nbt.TAG_String("create_enchantment_industry:experience")
        fluid["amount"] = nbt.TAG_Int(23)

        converted, report = self.convert(source)

        self.assertIsNotNone(converted, report)
        target = converted["data"]["Trains"][0]["Carriages"][0]["EntityPositioning"][0]["fluids"][0]["storage"]["fluid"]
        self.assertFalse(target)
        self.assertEqual(1, len(report["fluid_semantic_floor_normalizations"]))
        self.assertEqual(23, report["fluid_semantic_floor_normalizations"][0]["source_amount"])

    def test_malformed_rotation_anchor_blocks_transaction(self):
        source = source_tracks_root()
        anchors = source["data"]["Trains"][0]["Carriages"][0]["EntityPositioning"][0]["RotationAnchors"]
        anchors[0] = double_list(1.0, 2.0)

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "source vector is not a three-double list" for entry in report["blockers"]))

    def test_malformed_contraption_bounds_blocks_transaction(self):
        source = source_tracks_root()
        bounds = source["data"]["Trains"][0]["Carriages"][0]["Entity"]["Contraption"]["BoundsFront"]
        bounds[0] = nbt.TAG_String("bad")
        converted, report = self.convert(source)
        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "contraption BoundsFront has the wrong numeric element type" for entry in report["blockers"]))

    def test_malformed_contraption_position_duplicate_blocks_transaction(self):
        source = source_tracks_root()
        seats = source["data"]["Trains"][0]["Carriages"][0]["Entity"]["Contraption"]["Seats"]
        seats.append(int_array(4, 5, 6))
        converted, report = self.convert(source)
        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "contraption position collection contains duplicate positions" for entry in report["blockers"]))

    def test_malformed_contraption_superglue_blocks_transaction(self):
        source = source_tracks_root()
        source["data"]["Trains"][0]["Carriages"][0]["Entity"]["Contraption"]["Superglue"][0] = double_list(0.0, 1.0)
        converted, report = self.convert(source)
        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "source Superglue entry is not six doubles" for entry in report["blockers"]))

    def test_mid_restore_station_port_blocks_transaction(self):
        source = source_tracks_root()
        station = source["data"]["RailGraphs"][0]["Points"]["create:station"][0]
        station["Ports"]["Values"][0]["restoring"] = nbt.TAG_Byte(1)

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "source port is mid-restore and has no stable target representation" for entry in report["blockers"]))

    def test_unknown_signal_color_blocks_transaction(self):
        source = source_tracks_root()
        source["data"]["SignalBlocks"][0]["Color"] = nbt.TAG_String("chartreuse")

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "signal group Color is not a known EdgeGroupColor" for entry in report["blockers"]))

    def test_target_lowercase_signal_color_is_rejected(self):
        converted, report = self.convert(source_tracks_root())
        self.assertIsNotNone(converted, report)
        converted["data"]["SignalBlocks"][0]["Color"] = nbt.TAG_String("green")

        result, report = self.convert(converted)

        self.assertIsNone(result)
        self.assertTrue(any(entry["reason"] == "target signal group Color is not the canonical uppercase enum" for entry in report["blockers"]))

    def test_unknown_schedule_runtime_state_blocks_transaction(self):
        source = source_tracks_root()
        source["data"]["Trains"][0]["Runtime"]["State"] = nbt.TAG_String("teleporting")

        converted, report = self.convert(source)

        self.assertIsNone(converted)
        self.assertTrue(any(entry["reason"] == "schedule runtime State is not a known enum value" for entry in report["blockers"]))

    def test_target_lowercase_schedule_runtime_state_is_rejected(self):
        converted, report = self.convert(source_tracks_root())
        self.assertIsNotNone(converted, report)
        converted["data"]["Trains"][0]["Runtime"]["State"] = nbt.TAG_String("post_transit")

        result, report = self.convert(converted)

        self.assertIsNone(result)
        self.assertTrue(any(entry["reason"] == "target schedule runtime State is not the canonical uppercase enum" for entry in report["blockers"]))


if __name__ == "__main__":
    unittest.main()
