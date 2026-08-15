from __future__ import annotations

import re

from nbt import nbt


FABRIC_BUCKET = 81_000
NEOFORGE_BUCKET = 1_000
FLUID_UNIT_DIVISOR = FABRIC_BUCKET // NEOFORGE_BUCKET
SOURCE_POTION_BOTTLE = 27_000
TARGET_POTION_BOTTLE = 250
POTION_UNIT_DIVISOR = SOURCE_POTION_BOTTLE // TARGET_POTION_BOTTLE
POTION_FLUID_ID = "create:potion"
SOURCE_MAX_CAPACITY_COMPONENT = "create:fluid_max_capacity"

FLUID_ID_ALIASES = {
    # The Fabric fork registered its own milk.  Create 6.0.10 enables
    # NeoForge's canonical milk fluid, whose registry key is minecraft:milk.
    "create:milk": "minecraft:milk",
}

# Create Enchantment Industry's Fabric implementation stores experience in
# Create's 81-units-per-millibucket scale, then intentionally floors it when
# converting back to millibuckets.  NeoForge stores the already-floored value
# directly.  This is the only audited fluid allowed to have a non-integral
# downgrade; rounding it upward would create XP that did not exist in the
# source gameplay semantics.
FLOOR_TO_MILLIBUCKET_FLUIDS = {
    "create_enchantment_industry:experience",
}

KNOWN_SOURCE_COMPONENTS = {
    SOURCE_MAX_CAPACITY_COMPONENT,
    "create:potion_fluid_bottle_type",
    "minecraft:potion_contents",
}

FLOW_VARIANT_PATH = re.compile(r"(?:^|\.)Flow\.Fluid$")


def _string(value):
    return value.value if isinstance(value, nbt.TAG_String) else None


def _clone_tag(value):
    """Clone parser tags without copying anvil-parser's internal Struct objects."""
    if not isinstance(value, nbt.TAG):
        return value
    if isinstance(value, nbt.TAG_Compound):
        result = nbt.TAG_Compound(name=getattr(value, "name", ""))
        for key, child in value.items():
            result[key] = _clone_tag(child)
        return result
    if isinstance(value, nbt.TAG_List):
        result = nbt.TAG_List(name=getattr(value, "name", ""))
        result.tagID = value.tagID
        result.tags = [_clone_tag(child) for child in value]
        return result
    if isinstance(value, nbt.TAG_Byte_Array):
        result = nbt.TAG_Byte_Array(name=getattr(value, "name", ""))
        result.value = bytearray(value.value)
        return result
    if isinstance(value, nbt.TAG_Int_Array):
        result = nbt.TAG_Int_Array(name=getattr(value, "name", ""))
        result.value = list(value.value)
        result.update_fmt(len(result.value))
        return result
    if isinstance(value, nbt.TAG_Long_Array):
        result = nbt.TAG_Long_Array(name=getattr(value, "name", ""))
        result.value = list(value.value)
        result.update_fmt(len(result.value))
        return result
    try:
        return type(value)(value=value.value, name=getattr(value, "name", ""))
    except TypeError:
        return type(value)(value.value)


def _integer(value):
    return isinstance(value, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long))


def _int_value(value):
    return int(value.value)


def _fail(blockers, path, reason, **details):
    blockers.append({"path": path, "reason": reason, **details})


def _scale_source_units(
    value,
    path,
    blockers,
    *,
    allow_variant_sentinel=False,
    floor_remainder=False,
    round_to_nearest=False,
    divisor=FLUID_UNIT_DIVISOR,
):
    if not isinstance(value, nbt.TAG_Int):
        _fail(blockers, path, "source fluid quantity is not a TAG_Int")
        return None
    amount = _int_value(value)
    if allow_variant_sentinel:
        if amount != 1:
            _fail(
                blockers,
                path,
                "source pipe Flow fluid does not use the required variant sentinel",
                value=amount,
                expected=1,
            )
            return None
        return nbt.TAG_Int(1)
    if amount <= 0:
        _fail(blockers, path, "source fluid quantity is not positive", value=amount)
        return None
    quotient, remainder = divmod(amount, divisor)
    if remainder and floor_remainder:
        # The audited CEI experience helper uses integer division.  A zero
        # quotient is represented by an empty FluidStack by the target codec.
        return nbt.TAG_Int(quotient)
    if remainder and round_to_nearest:
        # Explicit user-approved lossy policy for persisted Create potion
        # amounts only. Use integer half-up rounding so the result is stable
        # across Python versions and never depends on bankers' rounding.
        rounded = (amount + divisor // 2) // divisor
        if rounded <= 0:
            _fail(blockers, path, "rounded fluid quantity is not positive", value=amount)
            return None
        return nbt.TAG_Int(rounded)
    if remainder:
        _fail(
            blockers,
            path,
            "source fluid quantity cannot be represented exactly in NeoForge millibuckets",
            value=amount,
            divisor=divisor,
            remainder=remainder,
        )
        return None
    if quotient <= 0:
        _fail(blockers, path, "scaled fluid quantity is not positive", value=amount)
        return None
    return nbt.TAG_Int(quotient)


def _validate_target_quantity(value, path, blockers):
    if not isinstance(value, nbt.TAG_Int) or _int_value(value) <= 0:
        _fail(blockers, path, "target fluid quantity is not a positive TAG_Int")
        return None
    return _clone_tag(value)


def _is_source_fluid_stack(value):
    if not isinstance(value, nbt.TAG_Compound):
        return False
    components = value.get("components")
    return isinstance(components, nbt.TAG_Compound) and SOURCE_MAX_CAPACITY_COMPONENT in components


def _is_target_fluid_stack(value):
    if not isinstance(value, nbt.TAG_Compound):
        return False
    return isinstance(value.get("id"), nbt.TAG_String) and isinstance(value.get("amount"), nbt.TAG_Int)


def _convert_fluid_stack(value, path, blockers, source_format, normalizations=None):
    if not isinstance(value, nbt.TAG_Compound):
        _fail(blockers, path, "fluid stack is not a compound")
        return
    identifier = _string(value.get("id"))
    amount = value.get("amount")
    components = value.get("components")
    if identifier is None:
        _fail(blockers, f"{path}.id", "fluid id is not a string")
    if source_format:
        if not isinstance(components, nbt.TAG_Compound):
            _fail(blockers, f"{path}.components", "source fluid components are not a compound")
            return
        unknown = sorted(set(components.keys()) - KNOWN_SOURCE_COMPONENTS)
        if unknown:
            _fail(
                blockers,
                f"{path}.components",
                "source fluid contains components without an audited target schema",
                components=unknown,
            )
        maximum = components.get(SOURCE_MAX_CAPACITY_COMPONENT)
        unit_divisor = POTION_UNIT_DIVISOR if identifier == POTION_FLUID_ID else FLUID_UNIT_DIVISOR
        scaled_maximum = _scale_source_units(
            maximum,
            f"{path}.components.{SOURCE_MAX_CAPACITY_COMPONENT}",
            blockers,
            divisor=unit_divisor,
        )
        scaled_amount = _scale_source_units(
            amount,
            f"{path}.amount",
            blockers,
            allow_variant_sentinel=bool(FLOW_VARIANT_PATH.search(path)),
            floor_remainder=identifier in FLOOR_TO_MILLIBUCKET_FLUIDS,
            round_to_nearest=identifier == POTION_FLUID_ID,
            divisor=unit_divisor,
        )
        if identifier is not None:
            value["id"] = nbt.TAG_String(FLUID_ID_ALIASES.get(identifier, identifier))
        if scaled_amount is not None:
            if (
                identifier in FLOOR_TO_MILLIBUCKET_FLUIDS
                and isinstance(amount, nbt.TAG_Int)
                and int(amount.value) % FLUID_UNIT_DIVISOR
                and not FLOW_VARIANT_PATH.search(path)
                and int(scaled_amount.value) == 0
            ):
                if normalizations is not None:
                    normalizations.append(
                        {
                            "normalization": "semantic_floor",
                            "path": path,
                            "fluid_id": identifier,
                            "source_amount": int(amount.value),
                            "target_amount": 0,
                            "reason": "CEI Fabric integer division yields zero XP",
                        }
                    )
                for key in list(value.keys()):
                    del value[key]
                return
            if (
                identifier in FLOOR_TO_MILLIBUCKET_FLUIDS
                and isinstance(amount, nbt.TAG_Int)
                and int(amount.value) % FLUID_UNIT_DIVISOR
                and not FLOW_VARIANT_PATH.search(path)
                and normalizations is not None
            ):
                normalizations.append(
                    {
                        "normalization": "semantic_floor",
                        "path": path,
                        "fluid_id": identifier,
                        "source_amount": int(amount.value),
                        "target_amount": int(scaled_amount.value),
                        "reason": "CEI Fabric integer division floors to millibuckets",
                    }
                )
            if identifier == POTION_FLUID_ID and not FLOW_VARIANT_PATH.search(path) and normalizations is not None:
                source_amount = int(amount.value)
                remainder = source_amount % POTION_UNIT_DIVISOR
                rounded = bool(remainder)
                normalization = {
                    "normalization": (
                        "nearest_potion_bottle_scale"
                        if rounded
                        else "exact_potion_bottle_scale"
                    ),
                    "path": path,
                    "fluid_id": identifier,
                    "source_amount": source_amount,
                    "target_amount": int(scaled_amount.value),
                    "source_max_capacity": int(maximum.value),
                    "target_max_capacity": int(scaled_maximum.value) if scaled_maximum is not None else None,
                    "divisor": POTION_UNIT_DIVISOR,
                    "reason": (
                        "User-approved nearest-integer conversion using Create's potion bottle ratio "
                        "27000 source units to 250 target millibuckets"
                        if rounded
                        else "Create potion fluid is encoded by the exact bottle ratio "
                        "27000 source units to 250 target millibuckets"
                    ),
                }
                if rounded:
                    normalization.update(
                        {
                            "source_remainder": remainder,
                            "target_error_millibuckets": (
                                int(scaled_amount.value) - source_amount / POTION_UNIT_DIVISOR
                            ),
                        }
                    )
                normalizations.append(normalization)
            value["amount"] = scaled_amount
        if scaled_maximum is not None:
            del components[SOURCE_MAX_CAPACITY_COMPONENT]
            if not components:
                del value["components"]
    else:
        if identifier in FLUID_ID_ALIASES:
            _fail(blockers, f"{path}.id", "target fluid still uses a source-only id", value=identifier)
        if isinstance(components, nbt.TAG_Compound) and SOURCE_MAX_CAPACITY_COMPONENT in components:
            _fail(
                blockers,
                f"{path}.components.{SOURCE_MAX_CAPACITY_COMPONENT}",
                "target fluid still contains the source-only maximum-capacity component",
            )
        _validate_target_quantity(amount, f"{path}.amount", blockers)


def _convert_mounted_storage(value, path, blockers, source_format, normalizations=None):
    if not isinstance(value, nbt.TAG_Compound):
        return False
    if set(value.keys()) != {"type", "capacity", "fluid"}:
        return False
    storage_type = _string(value.get("type"))
    if storage_type != "create:fluid_tank":
        _fail(
            blockers,
            f"{path}.type",
            "mounted fluid storage with capacity/fluid has an unaudited type",
            value=storage_type,
        )
        return True
    capacity = value.get("capacity")
    if source_format:
        scaled = _scale_source_units(capacity, f"{path}.capacity", blockers)
        if scaled is not None:
            value["capacity"] = scaled
    else:
        _validate_target_quantity(capacity, f"{path}.capacity", blockers)
    fluid = value.get("fluid")
    if not isinstance(fluid, nbt.TAG_Compound):
        _fail(blockers, f"{path}.fluid", "mounted fluid value is not a compound")
    elif fluid:
        if source_format and not _is_source_fluid_stack(fluid):
            _fail(blockers, f"{path}.fluid", "non-empty source mounted fluid lacks its source schema marker")
        else:
            _convert_fluid_stack(
                fluid,
                f"{path}.fluid",
                blockers,
                source_format,
                normalizations,
            )
    return True


def _walk(value, path, blockers, source_format, normalizations=None):
    if isinstance(value, nbt.TAG_Compound):
        if _convert_mounted_storage(value, path, blockers, source_format, normalizations):
            return
        if source_format and _is_source_fluid_stack(value):
            _convert_fluid_stack(value, path, blockers, True, normalizations)
            return
        if not source_format and _is_target_fluid_stack(value):
            components = value.get("components")
            if isinstance(components, nbt.TAG_Compound) and SOURCE_MAX_CAPACITY_COMPONENT in components:
                _convert_fluid_stack(value, path, blockers, False, normalizations)
                return
            if _string(value.get("id")) in FLUID_ID_ALIASES:
                _convert_fluid_stack(value, path, blockers, False, normalizations)
                return
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            _walk(child, child_path, blockers, source_format, normalizations)
    elif isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            _walk(child, f"{path}[{index}]", blockers, source_format, normalizations)


def convert_create_fluid_tree(value, path, blockers, source_format, normalizations=None):
    """Return a converted clone, or None while leaving *value* untouched.

    The source marker makes ordinary FluidStacks unambiguous.  Mounted fluid
    storage is handled separately because an empty tank has no FluidStack and
    still carries a Fabric-unit capacity that must be scaled.
    """
    local = []
    converted = _clone_tag(value)
    _walk(converted, path, local, source_format, normalizations)
    if local:
        blockers.extend(local)
        return None
    return converted


def audit_source_fluid_tree(value, path=""):
    records = []

    def visit(node, node_path):
        if isinstance(node, nbt.TAG_Compound):
            if _is_source_fluid_stack(node):
                components = node["components"]
                amount = node.get("amount")
                maximum = components.get(SOURCE_MAX_CAPACITY_COMPONENT)
                amount_value = _int_value(amount) if _integer(amount) else None
                maximum_value = _int_value(maximum) if _integer(maximum) else None
                variant = bool(FLOW_VARIANT_PATH.search(node_path))
                identifier = _string(node.get("id"))
                unit_divisor = POTION_UNIT_DIVISOR if identifier == POTION_FLUID_ID else FLUID_UNIT_DIVISOR
                exact_amount = amount_value == 1 if variant else (
                    amount_value is not None
                    and amount_value > 0
                    and amount_value % unit_divisor == 0
                )
                nearest_potion_amount = (
                    identifier == POTION_FLUID_ID
                    and not variant
                    and amount_value is not None
                    and amount_value > 0
                    and not exact_amount
                )
                exact_maximum = (
                    maximum_value is not None
                    and maximum_value > 0
                    and maximum_value % unit_divisor == 0
                )
                records.append(
                    {
                        "path": node_path,
                        "id": identifier,
                        "target_id": FLUID_ID_ALIASES.get(identifier, identifier),
                        "amount": amount_value,
                        "target_amount": (
                            amount_value
                            if variant and amount_value == 1
                            else amount_value // unit_divisor
                            if exact_amount
                            else (amount_value + unit_divisor // 2) // unit_divisor
                            if nearest_potion_amount
                            else amount_value // FLUID_UNIT_DIVISOR
                            if identifier in FLOOR_TO_MILLIBUCKET_FLUIDS
                            and amount_value is not None
                            and amount_value > 0
                            else None
                        ),
                        "max_capacity": maximum_value,
                        "target_max_capacity": maximum_value // unit_divisor if exact_maximum else None,
                        "unit_divisor": unit_divisor,
                        "flow_variant": variant,
                        "components": sorted(components.keys()),
                        "exact": exact_amount and exact_maximum,
                        "semantic_floor_allowed": identifier in FLOOR_TO_MILLIBUCKET_FLUIDS,
                        "exact_potion_bottle_scale": identifier == POTION_FLUID_ID,
                        "nearest_potion_bottle_scale_allowed": nearest_potion_amount and exact_maximum,
                        "source_remainder": amount_value % unit_divisor if nearest_potion_amount else 0,
                        "target_error_millibuckets": (
                            ((amount_value + unit_divisor // 2) // unit_divisor)
                            - amount_value / unit_divisor
                            if nearest_potion_amount
                            else 0
                        ),
                    }
                )
                return
            for key, child in node.items():
                visit(child, f"{node_path}.{key}" if node_path else key)
        elif isinstance(node, nbt.TAG_List):
            for index, child in enumerate(node):
                visit(child, f"{node_path}[{index}]")

    visit(value, path)
    return records


def audit_source_mounted_storages(value, path=""):
    records = []

    def visit(node, node_path):
        if isinstance(node, nbt.TAG_Compound):
            if set(node.keys()) == {"type", "capacity", "fluid"}:
                capacity = node.get("capacity")
                raw_capacity = _int_value(capacity) if _integer(capacity) else None
                exact = (
                    isinstance(capacity, nbt.TAG_Int)
                    and raw_capacity > 0
                    and raw_capacity % FLUID_UNIT_DIVISOR == 0
                )
                records.append(
                    {
                        "path": node_path,
                        "type": _string(node.get("type")),
                        "capacity": raw_capacity,
                        "target_capacity": raw_capacity // FLUID_UNIT_DIVISOR if exact else None,
                        "fluid_empty": isinstance(node.get("fluid"), nbt.TAG_Compound) and not node["fluid"],
                        "exact": exact,
                    }
                )
                return
            for key, child in node.items():
                visit(child, f"{node_path}.{key}" if node_path else key)
        elif isinstance(node, nbt.TAG_List):
            for index, child in enumerate(node):
                visit(child, f"{node_path}[{index}]")

    visit(value, path)
    return records
