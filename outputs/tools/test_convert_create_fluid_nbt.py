import sys
import unittest
from pathlib import Path

from nbt import nbt


sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_create_fluid_nbt as converter


def fluid(identifier, amount, maximum, extra_components=None):
    value = nbt.TAG_Compound()
    value["id"] = nbt.TAG_String(identifier)
    value["amount"] = nbt.TAG_Int(amount)
    components = nbt.TAG_Compound()
    components[converter.SOURCE_MAX_CAPACITY_COMPONENT] = nbt.TAG_Int(maximum)
    for key, component in (extra_components or {}).items():
        components[key] = component
    value["components"] = components
    return value


class CreateFluidNbtTests(unittest.TestCase):
    def test_scales_stored_quantity_and_removes_source_component(self):
        source = fluid("minecraft:water", 81_000, 81_000)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertEqual([], blockers)
        self.assertEqual(1_000, target["amount"].value)
        self.assertNotIn("components", target)
        self.assertEqual(81_000, source["amount"].value)

    def test_pipe_flow_uses_variant_sentinel_without_scaling(self):
        source = fluid("minecraft:lava", 1, 121_500)
        blockers = []
        normalizations = []
        target = converter.convert_create_fluid_tree(
            source,
            "north.Flow.Fluid",
            blockers,
            True,
            normalizations,
        )
        self.assertEqual([], blockers)
        self.assertEqual([], normalizations)
        self.assertEqual(1, target["amount"].value)
        self.assertNotIn("components", target)

    def test_maps_fabric_create_milk_to_neoforge_milk(self):
        source = fluid("create:milk", 40_500, 121_500)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertEqual([], blockers)
        self.assertEqual("minecraft:milk", target["id"].value)
        self.assertEqual(500, target["amount"].value)

    def test_preserves_target_supported_potion_components(self):
        potion_contents = nbt.TAG_Compound()
        potion_contents["potion"] = nbt.TAG_String("minecraft:healing")
        source = fluid(
            "create:potion",
            54_000,
            108_000,
            {
                "create:potion_fluid_bottle_type": nbt.TAG_String("regular"),
                "minecraft:potion_contents": potion_contents,
            },
        )
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertEqual([], blockers)
        self.assertEqual(500, target["amount"].value)
        self.assertEqual(
            {"create:potion_fluid_bottle_type", "minecraft:potion_contents"},
            set(target["components"].keys()),
        )

    def test_potion_uses_exact_108_to_1_bottle_scale(self):
        potion_contents = nbt.TAG_Compound()
        potion_contents["potion"] = nbt.TAG_String("minecraft:harming")
        source = fluid(
            "create:potion",
            896_400,
            2_592_000,
            {
                "create:potion_fluid_bottle_type": nbt.TAG_String("regular"),
                "minecraft:potion_contents": potion_contents,
            },
        )
        blockers = []
        normalizations = []

        target = converter.convert_create_fluid_tree(
            source,
            "TankContent",
            blockers,
            True,
            normalizations,
        )

        self.assertEqual([], blockers)
        self.assertEqual(8_300, target["amount"].value)
        self.assertEqual(
            [{
                "normalization": "exact_potion_bottle_scale",
                "path": "TankContent",
                "fluid_id": "create:potion",
                "source_amount": 896_400,
                "target_amount": 8_300,
                "source_max_capacity": 2_592_000,
                "target_max_capacity": 24_000,
                "divisor": 108,
                "reason": (
                    "Create potion fluid is encoded by the exact bottle ratio "
                    "27000 source units to 250 target millibuckets"
                ),
            }],
            normalizations,
        )

    def test_potion_amount_not_divisible_by_108_uses_user_approved_nearest_integer(self):
        source = fluid("create:potion", 810, 81_000)
        blockers = []
        normalizations = []
        target = converter.convert_create_fluid_tree(
            source, "TankContent", blockers, True, normalizations
        )
        self.assertEqual([], blockers)
        self.assertEqual(8, target["amount"].value)
        self.assertEqual(750, normalizations[0]["target_max_capacity"])
        self.assertEqual("nearest_potion_bottle_scale", normalizations[0]["normalization"])
        self.assertEqual(54, normalizations[0]["source_remainder"])
        self.assertEqual(0.5, normalizations[0]["target_error_millibuckets"])

        record = converter.audit_source_fluid_tree(source, "TankContent")[0]
        self.assertFalse(record["exact"])
        self.assertTrue(record["nearest_potion_bottle_scale_allowed"])
        self.assertEqual(8, record["target_amount"])
        self.assertEqual(0.5, record["target_error_millibuckets"])

    def test_potion_maximum_not_divisible_by_108_fails_closed(self):
        source = fluid("create:potion", 27_000, 81_001)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertIsNone(target)
        self.assertEqual(108, blockers[0]["divisor"])

    def test_potion_flow_variant_sentinel_stays_one_but_maximum_uses_108(self):
        source = fluid("create:potion", 1, 2_592_000)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "east.Flow.Fluid", blockers, True)
        self.assertEqual([], blockers)
        self.assertEqual(1, target["amount"].value)
        record = converter.audit_source_fluid_tree(source, "east.Flow.Fluid")[0]
        self.assertTrue(record["exact"])
        self.assertEqual(108, record["unit_divisor"])
        self.assertEqual(24_000, record["target_max_capacity"])

    def test_non_potion_non_integral_quantity_remains_fail_closed(self):
        source = fluid("minecraft:water", 896_400, 2_592_000)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertIsNone(target)
        self.assertIn("cannot be represented exactly", blockers[0]["reason"])

    def test_scales_empty_mounted_tank_capacity(self):
        source = nbt.TAG_Compound()
        source["type"] = nbt.TAG_String("create:fluid_tank")
        source["capacity"] = nbt.TAG_Int(81_000)
        source["fluid"] = nbt.TAG_Compound()
        blockers = []
        target = converter.convert_create_fluid_tree(source, "fluids[0].storage", blockers, True)
        self.assertEqual([], blockers)
        self.assertEqual(1_000, target["capacity"].value)

    def test_non_integral_quantity_fails_closed(self):
        source = fluid("minecraft:water", 82, 81_000)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertIsNone(target)
        self.assertEqual(82, source["amount"].value)
        self.assertIn("cannot be represented exactly", blockers[0]["reason"])

    def test_cei_experience_residual_is_empty_by_source_integer_semantics(self):
        source = fluid("create_enchantment_industry:experience", 23, 81_000)
        blockers = []
        normalizations = []
        target = converter.convert_create_fluid_tree(
            source,
            "down.OpenEnd.Fluid",
            blockers,
            True,
            normalizations,
        )
        self.assertEqual([], blockers)
        self.assertEqual([], list(target.keys()))
        self.assertEqual(
            [{
                "normalization": "semantic_floor",
                "path": "down.OpenEnd.Fluid",
                "fluid_id": "create_enchantment_industry:experience",
                "source_amount": 23,
                "target_amount": 0,
                "reason": "CEI Fabric integer division yields zero XP",
            }],
            normalizations,
        )

    def test_cei_experience_non_integral_positive_amount_is_floored(self):
        source = fluid("create_enchantment_industry:experience", 81_001, 81_000)
        blockers = []
        normalizations = []
        target = converter.convert_create_fluid_tree(
            source,
            "TankContent",
            blockers,
            True,
            normalizations,
        )
        self.assertEqual([], blockers)
        self.assertEqual(1000, target["amount"].value)
        self.assertEqual(1, len(normalizations))

    def test_unexpected_source_component_fails_closed(self):
        source = fluid(
            "minecraft:water",
            81_000,
            81_000,
            {"example:unknown": nbt.TAG_String("value")},
        )
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertIsNone(target)
        self.assertIn("without an audited target schema", blockers[0]["reason"])

    def test_target_shape_is_idempotent(self):
        target = nbt.TAG_Compound()
        target["id"] = nbt.TAG_String("minecraft:milk")
        target["amount"] = nbt.TAG_Int(500)
        blockers = []
        second = converter.convert_create_fluid_tree(target, "TankContent", blockers, False)
        self.assertEqual([], blockers)
        self.assertEqual("minecraft:milk", second["id"].value)
        self.assertEqual(500, second["amount"].value)

    def test_target_rejects_source_only_component(self):
        source = fluid("minecraft:water", 81_000, 81_000)
        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, False)
        self.assertIsNone(target)
        self.assertIn("source-only", blockers[0]["reason"])

    def test_clone_handles_real_nbt_array_tags(self):
        source = fluid("minecraft:water", 81_000, 81_000)
        byte_array = nbt.TAG_Byte_Array()
        byte_array.value = bytearray((1, 2, 255))
        int_array = nbt.TAG_Int_Array()
        int_array.value = [3, -4]
        int_array.update_fmt(2)
        long_array = nbt.TAG_Long_Array()
        long_array.value = [5, -6]
        long_array.update_fmt(2)
        payload = nbt.TAG_Compound()
        payload["bytes"] = byte_array
        payload["ints"] = int_array
        payload["longs"] = long_array
        source["payload"] = payload

        blockers = []
        target = converter.convert_create_fluid_tree(source, "TankContent", blockers, True)
        self.assertEqual([], blockers)
        self.assertEqual(bytearray((1, 2, 255)), target["payload"]["bytes"].value)
        self.assertEqual([3, -4], list(target["payload"]["ints"].value))
        self.assertEqual([5, -6], list(target["payload"]["longs"].value))
        self.assertEqual(81_000, source["components"][converter.SOURCE_MAX_CAPACITY_COMPONENT].value)


if __name__ == "__main__":
    unittest.main()
