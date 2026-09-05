from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import tempfile
import time
import tomllib
import uuid
import zipfile
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

try:
    from nbt import nbt
except ImportError as exc:  # pragma: no cover - command reports a useful error
    raise SystemExit("install anvil-parser into the D: work area first") from exc


REGION_ROOTS = (Path("."), Path("DIM-1"), Path("DIM1"))
ENTITY_RELATIVE = tuple(root / "entities" for root in REGION_ROOTS)
BLOCK_RELATIVE = tuple(root / "region" for root in REGION_ROOTS)

ATTRIBUTE_ALIASES = {
    "minecraft:armor": "minecraft:generic.armor",
    "minecraft:armor_toughness": "minecraft:generic.armor_toughness",
    "minecraft:attack_damage": "minecraft:generic.attack_damage",
    "minecraft:attack_knockback": "minecraft:generic.attack_knockback",
    "minecraft:attack_speed": "minecraft:generic.attack_speed",
    # NeoForge/Minecraft 1.21.1 registers the player-only attributes under
    # the ``minecraft:player`` namespace.  The 1.21.11 codec (and the first
    # version of this converter) used the unscoped ids, so these aliases must
    # land on the player registry entries rather than ``generic.*``.  A
    # previous converter build emitted the wrong generic ids; keep those as
    # repair aliases so a failed/partial conversion can be safely re-run.
    "minecraft:block_break_speed": "minecraft:player.block_break_speed",
    "minecraft:block_interaction_range": "minecraft:player.block_interaction_range",
    "minecraft:burning_time": "minecraft:generic.burning_time",
    "minecraft:explosion_knockback_resistance": "minecraft:generic.explosion_knockback_resistance",
    "minecraft:entity_interaction_range": "minecraft:player.entity_interaction_range",
    "minecraft:fall_damage_multiplier": "minecraft:generic.fall_damage_multiplier",
    "minecraft:flying_speed": "minecraft:generic.flying_speed",
    "minecraft:follow_range": "minecraft:generic.follow_range",
    "minecraft:gravity": "minecraft:generic.gravity",
    "minecraft:jump_strength": "minecraft:generic.jump_strength",
    "minecraft:knockback_resistance": "minecraft:generic.knockback_resistance",
    "minecraft:luck": "minecraft:generic.luck",
    "minecraft:max_absorption": "minecraft:generic.max_absorption",
    "minecraft:max_health": "minecraft:generic.max_health",
    "minecraft:mining_efficiency": "minecraft:player.mining_efficiency",
    "minecraft:movement_efficiency": "minecraft:generic.movement_efficiency",
    "minecraft:movement_speed": "minecraft:generic.movement_speed",
    "minecraft:oxygen_bonus": "minecraft:generic.oxygen_bonus",
    "minecraft:safe_fall_distance": "minecraft:generic.safe_fall_distance",
    "minecraft:scale": "minecraft:generic.scale",
    "minecraft:sneaking_speed": "minecraft:player.sneaking_speed",
    "minecraft:step_height": "minecraft:generic.step_height",
    "minecraft:submerged_mining_speed": "minecraft:player.submerged_mining_speed",
    "minecraft:sweeping_damage_ratio": "minecraft:player.sweeping_damage_ratio",
    "minecraft:water_movement_efficiency": "minecraft:generic.water_movement_efficiency",
    "minecraft:spawn_reinforcements": "minecraft:zombie.spawn_reinforcements",
    # Already-canonical 1.21.1 ids are idempotent.  These seven generic ids
    # were emitted by the pre-fix converter and are accepted as repair input.
    "minecraft:generic.block_break_speed": "minecraft:player.block_break_speed",
    "minecraft:generic.block_interaction_range": "minecraft:player.block_interaction_range",
    "minecraft:generic.entity_interaction_range": "minecraft:player.entity_interaction_range",
    "minecraft:generic.mining_efficiency": "minecraft:player.mining_efficiency",
    "minecraft:generic.sneaking_speed": "minecraft:player.sneaking_speed",
    "minecraft:generic.submerged_mining_speed": "minecraft:player.submerged_mining_speed",
    "minecraft:generic.sweeping_damage_ratio": "minecraft:player.sweeping_damage_ratio",
    "minecraft:player.block_break_speed": "minecraft:player.block_break_speed",
    "minecraft:player.block_interaction_range": "minecraft:player.block_interaction_range",
    "minecraft:player.entity_interaction_range": "minecraft:player.entity_interaction_range",
    "minecraft:player.mining_efficiency": "minecraft:player.mining_efficiency",
    "minecraft:player.sneaking_speed": "minecraft:player.sneaking_speed",
    "minecraft:player.submerged_mining_speed": "minecraft:player.submerged_mining_speed",
    "minecraft:player.sweeping_damage_ratio": "minecraft:player.sweeping_damage_ratio",
}

SUPPORTED_ATTRIBUTES = set(ATTRIBUTE_ALIASES.values()) | {
    "minecraft:generic.attack_speed",
    "minecraft:generic.luck",
}

WAYPOINT_FIRE_CAPABILITY = "waypoint_fire_equivalence"
WAYPOINT_FIRE_MOD_ID = "waypoint_fire_equivalence"
WAYPOINT_FIRE_MARKER = "META-INF/waypoint-fire-equivalence-capabilities.json"
WAYPOINT_FIRE_REQUIRED_CAPABILITIES = {
    "canonical_waypoint_attributes",
    "canonical_locator_bar_rule",
    "canonical_fire_spread_radius_rule",
    "legacy_1_21_1_rule_migration",
}
WAYPOINT_FIRE_REQUIRED_CLASSES = {
    "com/bmt/waypointfire/WaypointFireEquivalence.class",
    "com/bmt/waypointfire/CompatGameRules.class",
    "com/bmt/waypointfire/ParitySemantics.class",
    "com/bmt/waypointfire/WaypointIcon.class",
    "com/bmt/waypointfire/WaypointIconCarrier.class",
    "com/bmt/waypointfire/client/ClientWaypointState.class",
    "com/bmt/waypointfire/client/WaypointClientEvents.class",
    "com/bmt/waypointfire/client/WaypointClientRuntimeEvents.class",
    "com/bmt/waypointfire/command/WaypointCommand.class",
    "com/bmt/waypointfire/mixin/FireBlockMixin.class",
    "com/bmt/waypointfire/mixin/GameRulesIntegerValueAccessor.class",
    "com/bmt/waypointfire/mixin/GameRulesLoadProbeMixin.class",
    "com/bmt/waypointfire/mixin/LivingEntityWaypointDataMixin.class",
    "com/bmt/waypointfire/network/WaypointDeltaPayload.class",
    "com/bmt/waypointfire/network/WaypointNetworking.class",
    "com/bmt/waypointfire/server/WaypointManager.class",
    "com/bmt/waypointfire/client/WaypointHud.class",
}
WAYPOINT_FIRE_REQUIRED_ENTRIES = WAYPOINT_FIRE_REQUIRED_CLASSES | {
    WAYPOINT_FIRE_MARKER,
    "META-INF/neoforge.mods.toml",
    "waypoint_fire_equivalence.mixins.json",
}
WAYPOINT_FIRE_REQUIRED_MIXINS = {
    "FireBlockMixin",
    "GameRulesIntegerValueAccessor",
    "GameRulesLoadProbeMixin",
    "LivingEntityWaypointDataMixin",
}
WAYPOINT_ATTRIBUTES = {
    "minecraft:waypoint_transmit_range",
    "minecraft:waypoint_receive_range",
}
ATTRIBUTE_MODIFIER_OPERATIONS = {
    "add_value",
    "add_multiplied_base",
    "add_multiplied_total",
}
LEGACY_ATTRIBUTE_MODIFIER_OPERATIONS = {
    0: "add_value",
    1: "add_multiplied_base",
    2: "add_multiplied_total",
}
LEGACY_ATTRIBUTE_MODIFIER_NAMES = {
    "Random spawn bonus": "minecraft:random_spawn_bonus",
    "Covered armor bonus": "minecraft:covered_armor_bonus",
}
RESOURCE_LOCATION_PATTERN = re.compile(r"^[a-z0-9_.-]+:[a-z0-9/._-]+$")
INTEGER_TEXT_PATTERN = re.compile(r"^[+-]?[0-9]+$")
UUID_TEXT_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

REMOVABLE_DEFAULT_ATTRIBUTES = {
    "minecraft:waypoint_transmit_range": 0.0,
    "minecraft:camera_distance": 4.0,
    "minecraft:tempt_range": 10.0,
}

HAPPY_GHAST_COMPAT_ATTRIBUTES = {
    # Implemented by happyghast-equivalence on both logical sides.
    "minecraft:camera_distance": 8.0,
    "minecraft:tempt_range": 16.0,
}

NEUTRAL_WAYPOINT_HIDE_MODIFIER = {
    "id": "minecraft:effect.waypoint_transmit_range_hide",
    "amount": -1.0,
    "operation": "add_multiplied_total",
}

BOAT_TYPES = {
    "oak": "oak",
    "spruce": "spruce",
    "birch": "birch",
    "jungle": "jungle",
    "acacia": "acacia",
    "cherry": "cherry",
    "dark_oak": "dark_oak",
    "mangrove": "mangrove",
    "bamboo": "bamboo",
    "pale_oak": "backport:pale_oak",
}

HAND_SLOTS = ("mainhand", "offhand")
ARMOR_SLOTS = ("feet", "legs", "chest", "head")
KNOWN_EQUIPMENT_SLOTS = set(HAND_SLOTS + ARMOR_SLOTS + ("body", "saddle"))

# Inventory slot IDs used by 1.21.1 Player/Inventory NBT. Slot 150 is encoded
# as signed byte -106 on disk, but comparisons use its unsigned value.
PLAYER_EQUIPMENT_SLOTS = {
    "feet": 100,
    "legs": 101,
    "chest": 102,
    "head": 103,
    "offhand": 150,
}
PLAYER_EQUIPMENT_NAMES = set(PLAYER_EQUIPMENT_SLOTS) | {"mainhand"}
PLAYER_RESPAWN_PITCH_KEY = "respawn_pitch_compat:respawn_pitch"

AXOLOTL_VARIANTS = {
    "lucy": 0,
    "wild": 1,
    "gold": 2,
    "cyan": 3,
    "blue": 4,
}

# Audited component set observed across the source ItemStack carriers. Unknown
# component types are a migration blocker: 1.21.1 rejects an unregistered
# component type while decoding the containing ItemStack.
KNOWN_PLAYER_ITEM_COMPONENTS = {
    "!minecraft:attribute_modifiers",
    "!minecraft:enchantments",
    "computercraft:back_pocket_upgrade",
    "computercraft:bottom_pocket_upgrade",
    "computercraft:computer",
    "computercraft:computer_id",
    "computercraft:on",
    "computercraft:pocket_upgrade",
    "create:banktank_air",
    "create:click_to_link_data",
    "create:clipboard_content",
    "create:filter_items",
    "create:filter_items_blacklist",
    "create:filter_items_respect_nbt",
    "create:linked_controller_items",
    "create:schematic_anchor",
    "create:schematic_bounds",
    "create:schematic_deployed",
    "create:schematic_file",
    "create:schematic_mirror",
    "create:schematic_owner",
    "create:schematic_rotation",
    "create:schematicannon_options",
    "create:sequenced_assembly",
    "create:sequenced_assembly_progress",
    "create:train_schedule",
    "kaleidoscope_cookery:recipe_record",
    "kaleidoscope_cookery:kitchen_shovel_has_oil",
    "kaleidoscope_tavern:brew_level",
    "minecraft:axolotl/variant",
    "minecraft:banner_patterns",
    "minecraft:block_entity_data",
    "minecraft:bucket_entity_data",
    "minecraft:bundle_contents",
    "minecraft:charged_projectiles",
    "minecraft:container",
    "minecraft:custom_name",
    "minecraft:damage",
    "minecraft:dyed_color",
    "minecraft:enchantments",
    "minecraft:fireworks",
    "minecraft:item_name",
    "minecraft:lore",
    "minecraft:map_color",
    "minecraft:map_decorations",
    "minecraft:map_id",
    "minecraft:max_stack_size",
    "minecraft:ominous_bottle_amplifier",
    "minecraft:potion_contents",
    "minecraft:pot_decorations",
    "minecraft:repair_cost",
    "minecraft:rarity",
    "minecraft:stored_enchantments",
    "minecraft:suspicious_stew_effects",
    "minecraft:trim",
    "minecraft:tooltip_display",
    "minecraft:unbreakable",
    "minecraft:hide_additional_tooltip",
    "minecraft:hide_tooltip",
    "minecraft:instrument",
    "minecraft:intangible_projectile",
    "minecraft:writable_book_content",
    "minecraft:written_book_content",
    "create:minecart_contraption_data",
    "create:package_address",
    "create:package_contents",
    "toms_storage:bound_pos",
    "toms_storage:configurator",
    "toms_storage:simple_item_filter",
    "toms_storage:tag_filter",
}

COMPUTERCRAFT_POCKET_COMPUTERS = {
    "computercraft:pocket_computer_normal",
    "computercraft:pocket_computer_advanced",
}
COMPUTERCRAFT_BACK_POCKET_UPGRADE = "computercraft:back_pocket_upgrade"
COMPUTERCRAFT_BOTTOM_POCKET_UPGRADE = "computercraft:bottom_pocket_upgrade"
COMPUTERCRAFT_TARGET_POCKET_UPGRADE = "computercraft:pocket_upgrade"
COMPUTERCRAFT_AUDITED_POCKET_UPGRADES = {"computercraft:speaker"}

# Modern ItemStack.CODEC owns only these root fields. Slot is an inventory
# carrier annotation used by several persisted handlers, not part of the stack
# itself. The block-entity tree walker only considers compounds which also have
# a components field, avoiding false positives for arbitrary mod id/count data.
ITEM_STACK_CARRIER_KEYS = {"id", "count", "Count", "components", "Slot"}

TEXT_BOOLEAN_FIELDS = {
    "bold", "italic", "underlined", "strikethrough", "obfuscated", "interpret",
}

SADDLE_ITEM_ENTITY_IDS = {
    "minecraft:horse", "minecraft:donkey", "minecraft:mule",
    "minecraft:zombie_horse", "minecraft:skeleton_horse", "minecraft:camel",
    "minecraft:nautilus", "minecraft:zombie_nautilus",
}
SADDLE_BOOLEAN_ENTITY_IDS = {
    "minecraft:pig", "minecraft:strider",
}
UNSUPPORTED_ENTITY_IDS = set()

# Modern 1.21.11 decoration entities persist their anchor as block_pos; the
# 1.21.1 BlockAttachedEntity serializer still reads the legacy Tile* fields.
BLOCK_ATTACHED_ENTITY_IDS = {
    "minecraft:item_frame",
    "minecraft:glow_item_frame",
    "minecraft:painting",
    "minecraft:leash_knot",
    # Immersive Paintings uses the same modern block_pos anchor while its
    # 1.21.1 entity class inherits the legacy BlockAttachedEntity serializer.
    "immersive_paintings:painting",
    "immersive_paintings:glow_painting",
    "immersive_paintings:graffiti",
    "immersive_paintings:glow_graffiti",
    # Create's hand-held blueprint entity is also attached to its block
    # anchor in the 1.21.1 target serializer.
    "create:crafting_blueprint",
}
BLOCK_ENTITY_ID_ALIASES = {
    # Create renamed this registered BlockEntityType between the two versions.
    "create:bracketed_kinetic": "create:simple_kinetic",
}
SCHEMATICANNON_STATES = {"stopped": "STOPPED", "paused": "PAUSED", "running": "RUNNING"}
SCHEMATICANNON_PRINT_STAGES = {
    "blocks": "BLOCKS",
    "deferred_blocks": "DEFERRED_BLOCKS",
    "entities": "ENTITIES",
}
SCHEMATICANNON_INVENTORY_SIZE = 5
CREATE_ITEM_VAULT_INVENTORY_SIZE = 20
SCHEMATICANNON_ITEM_KEYS = {"id", "count", "components"}

# Create Fly 6.0.9-15 writes Direction's serialized lower-case name while
# Create 6.0.10 for 1.21.1 reads these two Basin fields with Enum.valueOf.
CREATE_DIRECTION_NAMES = {"DOWN", "UP", "NORTH", "SOUTH", "WEST", "EAST"}

# The three transitional items shipped by the source and target Create JARs
# map one-to-one to these recipe ids.  The total is sequence length * loops and
# is also persisted in Create Fly's generated lore, giving us an independent
# check before replacing its float-only progress component.
CREATE_SEQUENCED_ASSEMBLY_RECIPES = {
    "create:incomplete_precision_mechanism": {
        "id": "create:sequenced_assembly/precision_mechanism",
        "total": 15,
        "descriptions": (
            {
                "translate": "create.recipe.assembly.deploying_item",
                "with": [{"ingredient": "create:cogwheel"}],
            },
            {
                "translate": "create.recipe.assembly.deploying_item",
                "with": [{"ingredient": "create:large_cogwheel"}],
            },
            {
                "translate": "create.recipe.assembly.deploying_item",
                "with": [{"ingredient": "#c:nuggets/iron"}],
            },
        ),
    },
    "create:incomplete_track": {
        "id": "create:sequenced_assembly/track",
        "total": 3,
        "descriptions": (
            {
                "translate": "create.recipe.assembly.deploying_item",
                "with": [{"ingredient": "#create:track_nuggets"}],
            },
            {
                "translate": "create.recipe.assembly.deploying_item",
                "with": [{"ingredient": "#create:track_nuggets"}],
            },
            {"translate": "create.recipe.assembly.pressing"},
        ),
    },
    "create:unprocessed_obsidian_sheet": {
        "id": "create:sequenced_assembly/sturdy_sheet",
        "total": 3,
        # The first filling operation creates the transitional item, so every
        # persisted step for this one-loop recipe points at a pressing step.
        "descriptions": (
            {
                "translate": "create.recipe.assembly.spout_filling_fluid",
                "with": ["Lava"],
            },
            {"translate": "create.recipe.assembly.pressing"},
            {"translate": "create.recipe.assembly.pressing"},
        ),
    },
}

CEI_BLAZE_FORGER_SOURCE_INVENTORY_KEYS = {
    "Size", "Items", "Cost", "Mode", "Conflicting", "OverCap",
}
CEI_BLAZE_FORGER_TARGET_INVENTORY_KEYS = {
    "Size", "Items", "Cost", "Operation", "Conflicting", "OverCap",
}

# 1.21.11 persists TrialSpawnerConfig holders as registry ids. 1.21.1 has no
# trial-spawner-config registry and its TrialSpawnerConfig.CODEC expects inline
# maps. These specs reproduce the 14 vanilla 1.21.1 trial-chamber structure
# templates, including their deliberately differential ominous_config maps.
TRIAL_SPAWNER_VARIANTS = {
    "minecraft:trial_chamber/breeze": {
        "target_template": "trial_chambers/spawner/breeze/breeze.nbt",
        "spawns": (({"id": "minecraft:breeze"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 1.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "total_mobs": 2.0,
        "total_mobs_added_per_player": 1.0,
        "ominous_kind": "breeze",
    },
    "minecraft:trial_chamber/melee/husk": {
        "target_template": "trial_chambers/spawner/melee/husk.nbt",
        "spawns": (({"id": "minecraft:husk"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_equipment": "minecraft:equipment/trial_chamber_melee",
    },
    "minecraft:trial_chamber/melee/spider": {
        "target_template": "trial_chambers/spawner/melee/spider.nbt",
        "spawns": (({"id": "minecraft:spider"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_kind": "swarm",
    },
    "minecraft:trial_chamber/melee/zombie": {
        "target_template": "trial_chambers/spawner/melee/zombie.nbt",
        "spawns": (({"id": "minecraft:zombie"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_equipment": "minecraft:equipment/trial_chamber_melee",
    },
    "minecraft:trial_chamber/ranged/poison_skeleton": {
        "target_template": "trial_chambers/spawner/ranged/poison_skeleton.nbt",
        "spawns": (({"id": "minecraft:bogged"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_equipment": "minecraft:equipment/trial_chamber_ranged",
    },
    "minecraft:trial_chamber/ranged/skeleton": {
        "target_template": "trial_chambers/spawner/ranged/skeleton.nbt",
        "spawns": (({"id": "minecraft:skeleton"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_equipment": "minecraft:equipment/trial_chamber_ranged",
    },
    "minecraft:trial_chamber/ranged/stray": {
        "target_template": "trial_chambers/spawner/ranged/stray.nbt",
        "spawns": (({"id": "minecraft:stray"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_equipment": "minecraft:equipment/trial_chamber_ranged",
    },
    "minecraft:trial_chamber/slow_ranged/poison_skeleton": {
        "target_template": "trial_chambers/spawner/slow_ranged/poison_skeleton.nbt",
        "spawns": (({"id": "minecraft:bogged"}, 1),),
        "ticks_between_spawn": 160,
        "simultaneous_mobs": 4.0,
        "simultaneous_mobs_added_per_player": 2.0,
        "ominous_equipment": "minecraft:equipment/trial_chamber_ranged",
    },
    "minecraft:trial_chamber/slow_ranged/skeleton": {
        "target_template": "trial_chambers/spawner/slow_ranged/skeleton.nbt",
        "spawns": (({"id": "minecraft:skeleton"}, 1),),
        "ticks_between_spawn": 160,
        "simultaneous_mobs": 4.0,
        "simultaneous_mobs_added_per_player": 2.0,
        "ominous_equipment": "minecraft:equipment/trial_chamber_ranged",
    },
    "minecraft:trial_chamber/slow_ranged/stray": {
        "target_template": "trial_chambers/spawner/slow_ranged/stray.nbt",
        "spawns": (({"id": "minecraft:stray"}, 1),),
        "ticks_between_spawn": 160,
        "simultaneous_mobs": 4.0,
        "simultaneous_mobs_added_per_player": 2.0,
        "ominous_equipment": "minecraft:equipment/trial_chamber_ranged",
    },
    "minecraft:trial_chamber/small_melee/baby_zombie": {
        "target_template": "trial_chambers/spawner/small_melee/baby_zombie.nbt",
        "spawns": (({"IsBaby": True, "id": "minecraft:zombie"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 2.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_equipment": "minecraft:equipment/trial_chamber_melee",
    },
    "minecraft:trial_chamber/small_melee/cave_spider": {
        "target_template": "trial_chambers/spawner/small_melee/cave_spider.nbt",
        "spawns": (({"id": "minecraft:cave_spider"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_kind": "swarm",
    },
    "minecraft:trial_chamber/small_melee/silverfish": {
        "target_template": "trial_chambers/spawner/small_melee/silverfish.nbt",
        "spawns": (({"id": "minecraft:silverfish"}, 1),),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_kind": "swarm",
    },
    "minecraft:trial_chamber/small_melee/slime": {
        "target_template": "trial_chambers/spawner/small_melee/slime.nbt",
        "spawns": (
            ({"Size": 1, "id": "minecraft:slime"}, 3),
            ({"Size": 2, "id": "minecraft:slime"}, 1),
        ),
        "ticks_between_spawn": 20,
        "simultaneous_mobs": 3.0,
        "simultaneous_mobs_added_per_player": 0.5,
        "ominous_kind": "swarm",
    },
}

# 1.21.11 stores vanilla game rules under namespaced snake_case IDs. 1.21.1
# stores the registered rule names as strings in Data.GameRules.
# Values are (1.21.1 key, value kind, invert boolean).
GAME_RULE_ALIASES = {
    "minecraft:advance_weather": ("doWeatherCycle", "boolean", False),
    "minecraft:max_entity_cramming": ("maxEntityCramming", "integer", False),
    "minecraft:command_block_output": ("commandBlockOutput", "boolean", False),
    "minecraft:fall_damage": ("fallDamage", "boolean", False),
    "minecraft:spawn_wardens": ("doWardenSpawning", "boolean", False),
    "minecraft:respawn_radius": ("spawnRadius", "integer", False),
    "minecraft:max_command_sequence_length": ("maxCommandChainLength", "integer", False),
    "minecraft:immediate_respawn": ("doImmediateRespawn", "boolean", False),
    "minecraft:drowning_damage": ("drowningDamage", "boolean", False),
    "minecraft:natural_health_regeneration": ("naturalRegeneration", "boolean", False),
    "minecraft:tnt_explosion_drop_decay": ("tntExplosionDropDecay", "boolean", False),
    "minecraft:players_nether_portal_creative_delay": ("playersNetherPortalCreativeDelay", "integer", False),
    "minecraft:fire_damage": ("fireDamage", "boolean", False),
    "minecraft:advance_time": ("doDaylightCycle", "boolean", False),
    "minecraft:spectators_generate_chunks": ("spectatorsGenerateChunks", "boolean", False),
    "minecraft:keep_inventory": ("keepInventory", "boolean", False),
    "minecraft:log_admin_commands": ("logAdminCommands", "boolean", False),
    "minecraft:block_drops": ("doTileDrops", "boolean", False),
    "minecraft:limited_crafting": ("doLimitedCrafting", "boolean", False),
    "minecraft:elytra_movement_check": ("disableElytraMovementCheck", "boolean", True),
    "minecraft:global_sound_events": ("globalSoundEvents", "boolean", False),
    "minecraft:spread_vines": ("doVinesSpread", "boolean", False),
    "minecraft:lava_source_conversion": ("lavaSourceConversion", "boolean", False),
    "minecraft:players_nether_portal_default_delay": ("playersNetherPortalDefaultDelay", "integer", False),
    "minecraft:players_sleeping_percentage": ("playersSleepingPercentage", "integer", False),
    "minecraft:entity_drops": ("doEntityDrops", "boolean", False),
    "minecraft:spawn_phantoms": ("doInsomnia", "boolean", False),
    "minecraft:spawn_mobs": ("doMobSpawning", "boolean", False),
    "minecraft:freeze_damage": ("freezeDamage", "boolean", False),
    "minecraft:forgive_dead_players": ("forgiveDeadPlayers", "boolean", False),
    "minecraft:mob_drops": ("doMobLoot", "boolean", False),
    "minecraft:show_advancement_messages": ("announceAdvancements", "boolean", False),
    "minecraft:max_command_forks": ("maxCommandForkCount", "integer", False),
    "minecraft:water_source_conversion": ("waterSourceConversion", "boolean", False),
    "minecraft:show_death_messages": ("showDeathMessages", "boolean", False),
    "minecraft:spawn_patrols": ("doPatrolSpawning", "boolean", False),
    "minecraft:block_explosion_drop_decay": ("blockExplosionDropDecay", "boolean", False),
    "minecraft:max_block_modifications": ("commandModificationBlockLimit", "integer", False),
    "minecraft:mob_griefing": ("mobGriefing", "boolean", False),
    "minecraft:send_command_feedback": ("sendCommandFeedback", "boolean", False),
    "minecraft:random_tick_speed": ("randomTickSpeed", "integer", False),
    "minecraft:ender_pearls_vanish_on_death": ("enderPearlsVanishOnDeath", "boolean", False),
    "minecraft:spawn_wandering_traders": ("doTraderSpawning", "boolean", False),
    "minecraft:mob_explosion_drop_decay": ("mobExplosionDropDecay", "boolean", False),
    "minecraft:max_snow_accumulation_height": ("snowAccumulationHeight", "integer", False),
    "minecraft:projectiles_can_break_blocks": ("projectilesCanBreakBlocks", "boolean", False),
    "minecraft:reduced_debug_info": ("reducedDebugInfo", "boolean", False),
    "minecraft:universal_anger": ("universalAnger", "boolean", False),
    "minecraft:raids": ("disableRaids", "boolean", True),
    # These exact namespaced target keys are registered by the declared
    # waypoint-fire-equivalence runtime, not by vanilla 1.21.1.
    "minecraft:locator_bar": ("minecraft:locator_bar", "boolean", False),
    "minecraft:fire_spread_radius_around_player": (
        "minecraft:fire_spread_radius_around_player", "integer", False,
    ),
}

WAYPOINT_FIRE_GAME_RULES = {
    "minecraft:locator_bar",
    "minecraft:fire_spread_radius_around_player",
}

# These moved from 1.21.11 game rules back to dedicated.properties switches in
# 1.21.1. They must be updated together with level.dat or behavior diverges.
GAME_RULE_SERVER_PROPERTIES = {
    "minecraft:allow_entering_nether_using_portals": "allow-nether",
    "minecraft:command_blocks_work": "enable-command-block",
    "minecraft:pvp": "pvp",
    "minecraft:spawn_monsters": "spawn-monsters",
}

# 1.21.1 has these behaviors permanently enabled rather than configurable.
# Only the equivalent value can be consumed; any other value is a blocker.
FIXED_GAME_RULE_DEFAULTS = {
    "minecraft:player_movement_check": (True, "1.21.1 always performs the player movement check"),
    "minecraft:spawner_blocks_work": (True, "1.21.1 spawner blocks always work"),
    "minecraft:tnt_explodes": (True, "1.21.1 TNT always activates and explodes"),
}

DIFFICULTY_NAMES = {0: "peaceful", 1: "easy", 2: "normal", 3: "hard"}


def tag_value(tag):
    return tag.value if isinstance(tag, nbt.TAG) else tag


def clone_tag(value):
    """Clone an NBT tree without deepcopying the parser's Struct objects."""
    if not isinstance(value, nbt.TAG):
        return value
    if isinstance(value, nbt.TAG_Compound):
        result = nbt.TAG_Compound(name=getattr(value, "name", ""))
        for key, child in value.items():
            result[key] = clone_tag(child)
        return result
    if isinstance(value, nbt.TAG_List):
        result = nbt.TAG_List(name=getattr(value, "name", ""))
        result.tagID = value.tagID
        result.tags = [clone_tag(child) for child in value]
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
        return type(value)(value=tag_value(value), name=getattr(value, "name", ""))
    except TypeError:
        return type(value)(tag_value(value))


def comparable_tag(value):
    """Canonical, type-sensitive value used only for collision checks."""
    if isinstance(value, nbt.TAG_Compound):
        return ("compound", tuple(sorted((key, comparable_tag(child)) for key, child in value.items())))
    if isinstance(value, nbt.TAG_List):
        return ("list", tuple(comparable_tag(child) for child in value))
    if isinstance(value, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)):
        return (value.__class__.__name__, tuple(int(child) for child in value.value))
    if isinstance(value, nbt.TAG):
        return (value.__class__.__name__, tag_value(value))
    return (type(value).__name__, value)


def comparable_item(item):
    return (
        "compound",
        tuple(sorted((key, comparable_tag(child)) for key, child in item.items() if key != "Slot")),
    )


def as_float(tag):
    return float(tag_value(tag))


def as_int(tag):
    return int(tag_value(tag))


def list_tag(values, tag_type):
    result = nbt.TAG_List(type=tag_type)
    for value in values:
        result.append(value)
    return result


def empty_item():
    return nbt.TAG_Compound()


def item_is_empty(item):
    if not isinstance(item, nbt.TAG_Compound):
        return True
    return not item.get("id") or as_int(item.get("count", nbt.TAG_Int(0))) <= 0


def compound_value(value):
    return value if isinstance(value, nbt.TAG_Compound) else nbt.TAG_Compound()


def string_value(tag):
    value = tag_value(tag)
    return value if isinstance(value, str) else str(value)


def boolean_value(tag):
    value = tag_value(tag)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1"}:
            return True
        if lowered in {"false", "0"}:
            return False
        raise ValueError(f"not a boolean: {value!r}")
    if isinstance(value, (bool, int, float)):
        return bool(value)
    raise ValueError(f"not a boolean: {value!r}")


def game_rule_text(tag, kind, invert=False):
    if kind == "boolean":
        value = boolean_value(tag)
        if invert:
            value = not value
        return "true" if value else "false"
    if kind == "integer":
        return str(as_int(tag))
    if kind == "string":
        return string_value(tag)
    raise ValueError(f"unknown game-rule kind {kind!r}")


def java_target_game_rule_text(tag, kind):
    """Normalize an existing 1.21.1 StringTag using its Java decoder semantics."""
    if not isinstance(tag, nbt.TAG_String):
        raise ValueError("target game rule is not a StringTag")
    raw = string_value(tag)
    if kind == "boolean":
        # java.lang.Boolean.parseBoolean performs only an ASCII
        # case-insensitive comparison with "true"; it does not trim.
        return "true" if raw.lower() == "true" else "false"
    if kind == "integer":
        if not INTEGER_TEXT_PATTERN.fullmatch(raw):
            raise ValueError("target integer is not accepted by Integer.parseInt")
        value = int(raw, 10)
        if not -2_147_483_648 <= value <= 2_147_483_647:
            raise ValueError("target integer is outside the Java int range")
        return str(value)
    if kind == "string":
        return raw
    raise ValueError(f"unknown target game-rule kind {kind!r}")


def convert_game_rules(data, audit):
    source = data.get("game_rules")
    if not isinstance(source, nbt.TAG_Compound):
        return False, {}
    existing = data.get("GameRules")
    if existing is not None and not isinstance(existing, nbt.TAG_Compound):
        audit.setdefault("level_blockers", []).append({"reason": "Data.GameRules is not a compound"})
        return False, {}
    target = clone_tag(existing) if isinstance(existing, nbt.TAG_Compound) else nbt.TAG_Compound()
    converted = []
    consumed = []
    unsupported = []
    server_properties = {}

    def merge_rule(source_id, target_id, after, invert, kind):
        if target_id in target:
            target_tag = target[target_id]
            before = string_value(target_tag)
            try:
                normalized_target = java_target_game_rule_text(target_tag, kind)
            except (TypeError, ValueError):
                normalized_target = None
            equal = (
                isinstance(target_tag, nbt.TAG_String)
                and normalized_target is not None
                and normalized_target == after
            )
            collision = {
                "source_id": source_id,
                "target_id": target_id,
                "source_value": after,
                "target_value": before,
                "target_normalized": normalized_target,
                "target_tag": type(target_tag).__name__,
                "resolution": "merge_equal" if equal else "blocked_conflict",
            }
            audit.setdefault("game_rule_collisions", []).append(collision)
            if not equal:
                unsupported.append({
                    "id": source_id,
                    "target_id": target_id,
                    "value": tag_value(data["game_rules"][source_id]),
                    "target_value": tag_value(target_tag),
                    "reason": (
                        "source game_rules value conflicts with existing Data.GameRules; "
                        "neither side was overwritten"
                    ),
                })
                return False
            # Never retain a broad Python-only spelling after declaring a
            # collision equal. Persist the canonical string Java will read.
            target[target_id] = nbt.TAG_String(after)
        else:
            before = None
            target[target_id] = nbt.TAG_String(after)
        converted.append({
            "source_id": source_id,
            "target_id": target_id,
            "before": before,
            "after": after,
            "inverted": invert,
        })
        return True

    for source_id, value in source.items():
        if source_id in GAME_RULE_ALIASES:
            target_id, kind, invert = GAME_RULE_ALIASES[source_id]
            if (
                source_id in WAYPOINT_FIRE_GAME_RULES
                and WAYPOINT_FIRE_CAPABILITY not in audit.get("runtime_capabilities", ())
            ):
                unsupported.append({
                    "id": source_id,
                    "value": tag_value(value),
                    "reason": (
                        "requires a validated waypoint-fire-equivalence JAR; "
                        "declare it with --waypoint-fire-compat-jar"
                    ),
                })
                continue
            try:
                after = game_rule_text(value, kind, invert)
            except (TypeError, ValueError) as exc:
                unsupported.append({"id": source_id, "value": tag_value(value), "reason": str(exc)})
                continue
            if kind == "integer" and not -2_147_483_648 <= int(after) <= 2_147_483_647:
                unsupported.append({
                    "id": source_id,
                    "value": tag_value(value),
                    "reason": "integer game rule is outside the Java int range",
                })
                continue
            if source_id == "minecraft:fire_spread_radius_around_player" and int(after) < -1:
                unsupported.append({
                    "id": source_id,
                    "value": tag_value(value),
                    "reason": "waypoint-fire-equivalence accepts a minimum fire radius of -1",
                })
                continue
            merge_rule(source_id, target_id, after, invert, kind)
            continue
        if source_id in GAME_RULE_SERVER_PROPERTIES:
            try:
                after = game_rule_text(value, "boolean")
            except (TypeError, ValueError) as exc:
                unsupported.append({"id": source_id, "value": tag_value(value), "reason": str(exc)})
                continue
            server_properties[GAME_RULE_SERVER_PROPERTIES[source_id]] = {"value": after, "source": source_id}
            continue
        if source_id in FIXED_GAME_RULE_DEFAULTS:
            expected, reason = FIXED_GAME_RULE_DEFAULTS[source_id]
            try:
                actual = boolean_value(value)
            except (TypeError, ValueError) as exc:
                unsupported.append({"id": source_id, "value": tag_value(value), "reason": str(exc)})
                continue
            if actual != expected:
                unsupported.append({"id": source_id, "value": actual, "reason": f"no 1.21.1 equivalent; {reason}"})
            else:
                consumed.append({"id": source_id, "value": actual, "implementation": reason})
            continue
        if not source_id.startswith("minecraft:"):
            after = string_value(value)
            merge_rule(source_id, source_id, after, False, "string")
            continue
        unsupported.append({"id": source_id, "value": tag_value(value), "reason": "no proven 1.21.1 game-rule or fixed-behavior equivalent"})
    audit.setdefault("game_rules", []).extend(converted)
    audit.setdefault("consumed_default_game_rules", []).extend(consumed)
    audit.setdefault("unsupported_game_rules", []).extend(unsupported)
    if unsupported:
        return False, server_properties
    data["GameRules"] = target
    del data["game_rules"]
    return True, server_properties


def plan_server_properties(world, desired, audit):
    if not desired:
        return None, None, False
    path = world.parent / "server.properties"
    if not path.exists():
        audit.setdefault("level_blockers", []).append({"reason": "server.properties is missing", "properties": sorted(desired)})
        return None, None, False
    raw = path.read_bytes()
    text = raw.decode("latin-1")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    seen = set()
    output = []
    changed = False
    for line in lines:
        stripped = line.rstrip("\r\n")
        ending = line[len(stripped):]
        if stripped and not stripped.lstrip().startswith(("#", "!")) and "=" in stripped:
            key, before = stripped.split("=", 1)
            if key in desired:
                after = desired[key]["value"]
                source = desired[key]["source"]
                seen.add(key)
                audit.setdefault("server_properties", []).append({"key": key, "before": before, "after": after, "source": source})
                if before != after:
                    stripped = f"{key}={after}"
                    changed = True
        output.append(stripped + ending)
    for key in sorted(set(desired) - seen):
        after = desired[key]["value"]
        source = desired[key]["source"]
        if output and not output[-1].endswith(("\n", "\r")):
            output[-1] += newline
        output.append(f"{key}={after}{newline}")
        audit.setdefault("server_properties", []).append({"key": key, "before": None, "after": after, "source": source})
        changed = True
    return path, "".join(output).encode("latin-1"), changed


def canonical_component_text(value):
    """Return the JSON string format expected by 1.21.1 text components."""
    text = string_value(value)
    if text == "":
        return '""'
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return json.dumps(text, ensure_ascii=False, separators=(",", ":"))
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    if isinstance(parsed, str):
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(text, ensure_ascii=False, separators=(",", ":"))


def entity_ref(entity):
    return {
        "uuid": str(entity.get("UUID")),
        "id": string_value(entity.get("id", nbt.TAG_String(""))),
        "pos": [as_float(value) for value in entity.get("Pos", [])],
    }


def convert_custom_name(entity, audit):
    value = entity.get("CustomName")
    if not isinstance(value, nbt.TAG_String):
        return False
    before = string_value(value)
    after = canonical_component_text(value)
    if before == after:
        return False
    entity["CustomName"] = nbt.TAG_String(after)
    audit.setdefault("custom_names", []).append({**entity_ref(entity), "before": before, "after": after})
    return True


def split_boat_type(identifier):
    if not identifier.startswith("minecraft:"):
        return None
    path = identifier.removeprefix("minecraft:")
    chest = False
    if path.endswith("_chest_boat"):
        wood = path.removesuffix("_chest_boat")
        chest = True
    elif path.endswith("_boat"):
        wood = path.removesuffix("_boat")
    elif path.endswith("_chest_raft"):
        wood = path.removesuffix("_chest_raft")
        chest = True
    elif path.endswith("_raft"):
        wood = path.removesuffix("_raft")
    else:
        return None
    boat_type = BOAT_TYPES.get(wood)
    if boat_type is None:
        return None
    return ("minecraft:chest_boat" if chest else "minecraft:boat", boat_type)


def convert_sign_text(block, audit):
    changed = False
    for side in ("front_text", "back_text"):
        text = block.get(side)
        if not isinstance(text, nbt.TAG_Compound) or "messages" not in text:
            continue
        messages = text["messages"]
        before = [string_value(item) for item in messages]
        after = [canonical_component_text(item) for item in messages]
        if before != after:
            audit.setdefault("signs", []).append({"pos": [as_int(block.get("x", nbt.TAG_Int(0))), as_int(block.get("y", nbt.TAG_Int(0))), as_int(block.get("z", nbt.TAG_Int(0)))], "side": side, "before": before, "after": after})
            for index, value in enumerate(after):
                messages[index] = nbt.TAG_String(value)
            changed = True
    return changed


def _schematicannon_inventory_blocker(block, audit, reason):
    audit.setdefault("unsupported_block_entities", []).append(
        {
            "id": "create:schematicannon",
            "reason": reason,
            **block_position_ref(block),
        }
    )


def _validate_schematicannon_item(item, *, allow_slot):
    if not isinstance(item, nbt.TAG_Compound):
        return None, "inventory entry is not a compound"
    allowed = SCHEMATICANNON_ITEM_KEYS | ({"Slot"} if allow_slot else set())
    unknown = sorted(set(item.keys()) - allowed)
    if unknown:
        return None, f"inventory item has unknown fields: {', '.join(unknown)}"
    if allow_slot:
        slot_tag = item.get("Slot")
        if not isinstance(slot_tag, nbt.TAG_Int):
            return None, "target inventory item Slot is not an IntTag"
        slot = as_int(slot_tag)
        if not 0 <= slot < SCHEMATICANNON_INVENTORY_SIZE:
            return None, f"target inventory item Slot {slot} is outside 0..4"
    elif "Slot" in item:
        return None, "source positional inventory item unexpectedly contains Slot"
    identifier = item.get("id")
    if not isinstance(identifier, nbt.TAG_String) or ":" not in string_value(identifier):
        return None, "inventory item id is missing or malformed"
    count = item.get("count")
    integer_tags = (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)
    if not isinstance(count, integer_tags) or not 1 <= as_int(count) <= 99:
        return None, "inventory item count is missing or outside 1..99"
    components = item.get("components")
    if components is not None and not isinstance(components, nbt.TAG_Compound):
        return None, "inventory item components is not a compound"
    return {
        "slot": as_int(item["Slot"]) if allow_slot else None,
        "id": string_value(identifier),
        "count": as_int(count),
    }, None


def convert_schematicannon_inventory(block, audit):
    """Convert Create Fly's positional list to NeoForge ItemStackHandler NBT."""
    inventory = block.get("Inventory")
    if not isinstance(inventory, (nbt.TAG_List, nbt.TAG_Compound)):
        _schematicannon_inventory_blocker(
            block,
            audit,
            "schematicannon Inventory is neither a source list nor a target compound",
        )
        return False, False

    if isinstance(inventory, nbt.TAG_Compound):
        if set(inventory.keys()) != {"Size", "Items"}:
            _schematicannon_inventory_blocker(
                block,
                audit,
                "target schematicannon Inventory must contain exactly Size and Items",
            )
            return False, False
        size = inventory.get("Size")
        if not isinstance(size, nbt.TAG_Int) or as_int(size) != SCHEMATICANNON_INVENTORY_SIZE:
            _schematicannon_inventory_blocker(
                block,
                audit,
                "target schematicannon Inventory Size is not IntTag 5",
            )
            return False, False
        items = inventory.get("Items")
        if not isinstance(items, nbt.TAG_List):
            _schematicannon_inventory_blocker(
                block,
                audit,
                "target schematicannon Inventory Items is not a list",
            )
            return False, False
        occupied = set()
        for item in items:
            summary, reason = _validate_schematicannon_item(item, allow_slot=True)
            if reason is not None:
                _schematicannon_inventory_blocker(block, audit, reason)
                return False, False
            slot = summary["slot"]
            if slot in occupied:
                _schematicannon_inventory_blocker(
                    block,
                    audit,
                    f"target schematicannon Inventory duplicates Slot {slot}",
                )
                return False, False
            occupied.add(slot)
        return False, True

    if len(inventory) != SCHEMATICANNON_INVENTORY_SIZE:
        _schematicannon_inventory_blocker(
            block,
            audit,
            f"source schematicannon Inventory has {len(inventory)} entries, expected 5",
        )
        return False, False

    converted_items = []
    summaries = []
    for slot, item in enumerate(inventory):
        if not isinstance(item, nbt.TAG_Compound):
            _schematicannon_inventory_blocker(
                block,
                audit,
                f"source schematicannon Inventory slot {slot} is not a compound",
            )
            return False, False
        if not item:
            continue
        summary, reason = _validate_schematicannon_item(item, allow_slot=False)
        if reason is not None:
            _schematicannon_inventory_blocker(
                block,
                audit,
                f"source schematicannon Inventory slot {slot}: {reason}",
            )
            return False, False
        target_item = clone_tag(item)
        target_item["Slot"] = nbt.TAG_Int(slot)
        converted_items.append(target_item)
        summaries.append({**summary, "slot": slot})

    target = nbt.TAG_Compound()
    target["Size"] = nbt.TAG_Int(SCHEMATICANNON_INVENTORY_SIZE)
    target["Items"] = list_tag(converted_items, nbt.TAG_Compound)
    block["Inventory"] = target
    audit.setdefault("schematicannon_inventory_conversions", []).append(
        {
            "id": "create:schematicannon",
            "source_format": "positional_list",
            "target_format": "neoforge_item_stack_handler",
            "size": SCHEMATICANNON_INVENTORY_SIZE,
            "items": summaries,
            **block_position_ref(block),
        }
    )
    return True, True


def _block_entity_blocker(block, audit, reason):
    audit.setdefault("unsupported_block_entities", []).append(
        {
            "id": string_value(block.get("id", nbt.TAG_String(""))),
            "reason": reason,
            **block_position_ref(block),
        }
    )


def _trial_spawner_entity_tag(fields):
    entity = nbt.TAG_Compound()
    for key, value in fields.items():
        if key == "id":
            entity[key] = nbt.TAG_String(value)
        elif key == "IsBaby":
            entity[key] = nbt.TAG_Byte(1 if value else 0)
        elif key == "Size":
            entity[key] = nbt.TAG_Int(value)
        else:  # Internal specs are fixed; a new field must select its NBT type.
            raise ValueError(f"unsupported TrialSpawner entity field {key!r}")
    return entity


def _trial_spawner_spawn_potentials(spec, equipment=None):
    potentials = []
    for entity_fields, weight in spec["spawns"]:
        data = nbt.TAG_Compound()
        if equipment is not None:
            data["equipment"] = nbt.TAG_Compound()
            data["equipment"]["slot_drop_chances"] = nbt.TAG_Float(0.0)
            data["equipment"]["loot_table"] = nbt.TAG_String(equipment)
        data["entity"] = _trial_spawner_entity_tag(entity_fields)
        entry = nbt.TAG_Compound()
        entry["data"] = data
        entry["weight"] = nbt.TAG_Int(weight)
        potentials.append(entry)
    return list_tag(potentials, nbt.TAG_Compound)


def _trial_spawner_ominous_loot():
    entries = []
    for identifier, weight in (
        ("minecraft:spawners/ominous/trial_chamber/key", 3),
        ("minecraft:spawners/ominous/trial_chamber/consumables", 7),
    ):
        entry = nbt.TAG_Compound()
        entry["data"] = nbt.TAG_String(identifier)
        entry["weight"] = nbt.TAG_Int(weight)
        entries.append(entry)
    return list_tag(entries, nbt.TAG_Compound)


def build_trial_spawner_target_configs(base_identifier):
    """Build the exact inline maps shipped in the 1.21.1 structure template."""
    spec = TRIAL_SPAWNER_VARIANTS[base_identifier]
    normal = nbt.TAG_Compound()
    normal["ticks_between_spawn"] = nbt.TAG_Int(spec["ticks_between_spawn"])
    normal["spawn_potentials"] = _trial_spawner_spawn_potentials(spec)
    normal["simultaneous_mobs"] = nbt.TAG_Float(spec["simultaneous_mobs"])
    normal["simultaneous_mobs_added_per_player"] = nbt.TAG_Float(
        spec["simultaneous_mobs_added_per_player"]
    )
    if "total_mobs_added_per_player" in spec:
        normal["total_mobs_added_per_player"] = nbt.TAG_Float(
            spec["total_mobs_added_per_player"]
        )
    if "total_mobs" in spec:
        normal["total_mobs"] = nbt.TAG_Float(spec["total_mobs"])

    ominous = nbt.TAG_Compound()
    equipment = spec.get("ominous_equipment")
    if equipment is not None:
        ominous["spawn_potentials"] = _trial_spawner_spawn_potentials(
            spec, equipment
        )
    ominous["loot_tables_to_eject"] = _trial_spawner_ominous_loot()
    ominous_kind = spec.get("ominous_kind")
    if ominous_kind == "breeze":
        ominous["simultaneous_mobs"] = nbt.TAG_Float(2.0)
        ominous["total_mobs"] = nbt.TAG_Float(4.0)
    elif ominous_kind == "swarm":
        ominous["simultaneous_mobs"] = nbt.TAG_Float(4.0)
        ominous["total_mobs"] = nbt.TAG_Float(12.0)
    elif equipment is None:
        raise ValueError(
            f"TrialSpawner spec {base_identifier!r} has no ominous mapping"
        )
    return normal, ominous


def _trial_spawner_config_shape(value):
    if value is None:
        return "missing"
    if isinstance(value, nbt.TAG_String):
        return f"StringTag({string_value(value)!r})"
    return type(value).__name__


def _matching_trial_spawner_target_variant(normal, ominous):
    for base_identifier in TRIAL_SPAWNER_VARIANTS:
        expected_normal, expected_ominous = build_trial_spawner_target_configs(
            base_identifier
        )
        if (
            comparable_tag(normal) == comparable_tag(expected_normal)
            and comparable_tag(ominous) == comparable_tag(expected_ominous)
        ):
            return base_identifier
    return None


def convert_trial_spawner_configs(block, audit):
    """Replace 1.21.11 config-holder ids with 1.21.1 inline codec maps."""
    normal = block.get("normal_config")
    ominous = block.get("ominous_config")
    if normal is None and ominous is None:
        return False, True

    if isinstance(normal, nbt.TAG_Compound) and isinstance(
        ominous, nbt.TAG_Compound
    ):
        if _matching_trial_spawner_target_variant(normal, ominous) is not None:
            return False, True
        _block_entity_blocker(
            block,
            audit,
            "trial_spawner inline normal_config/ominous_config do not exactly "
            "match any of the 14 audited vanilla 1.21.1 template pairs",
        )
        return False, False

    if not isinstance(normal, nbt.TAG_String) or not isinstance(
        ominous, nbt.TAG_String
    ):
        _block_entity_blocker(
            block,
            audit,
            "trial_spawner config pair is neither two 1.21.11 registry-id "
            "StringTags nor two audited 1.21.1 compounds "
            f"(normal={_trial_spawner_config_shape(normal)}, "
            f"ominous={_trial_spawner_config_shape(ominous)})",
        )
        return False, False

    normal_identifier = string_value(normal)
    ominous_identifier = string_value(ominous)
    suffix = "/normal"
    base_identifier = (
        normal_identifier[: -len(suffix)]
        if normal_identifier.endswith(suffix)
        else None
    )
    if base_identifier not in TRIAL_SPAWNER_VARIANTS:
        _block_entity_blocker(
            block,
            audit,
            f"trial_spawner normal_config has unaudited registry id {normal_identifier!r}",
        )
        return False, False
    expected_ominous = f"{base_identifier}/ominous"
    if ominous_identifier != expected_ominous:
        _block_entity_blocker(
            block,
            audit,
            "trial_spawner normal_config/ominous_config registry ids are not "
            f"the same vanilla variant ({normal_identifier!r}, {ominous_identifier!r})",
        )
        return False, False

    target_normal, target_ominous = build_trial_spawner_target_configs(
        base_identifier
    )
    block["normal_config"] = target_normal
    block["ominous_config"] = target_ominous
    audit.setdefault("trial_spawner_config_conversions", []).append(
        {
            **block_position_ref(block),
            "id": "minecraft:trial_spawner",
            "source_normal_config": normal_identifier,
            "source_ominous_config": ominous_identifier,
            "target_template": TRIAL_SPAWNER_VARIANTS[base_identifier][
                "target_template"
            ],
            "source_format": "registry_holder_ids",
            "target_format": "inline_config_maps",
        }
    )
    return True, True


def _canonical_create_direction(value, field):
    if not isinstance(value, nbt.TAG_String):
        raise ValueError(f"basin {field} is not a StringTag")
    raw = string_value(value)
    canonical = raw.upper()
    if canonical not in CREATE_DIRECTION_NAMES:
        raise ValueError(f"basin {field} has unknown direction {raw!r}")
    if raw not in {raw.lower(), canonical}:
        raise ValueError(f"basin {field} has mixed-case direction {raw!r}")
    return canonical


def convert_create_basin_directions(block, audit):
    """Normalize Create Fly's serialized directions for 1.21.1 enum readers."""
    preferred = block.get("PreferredSpoutput")
    disabled = block.get("DisabledSpoutput")
    if preferred is None and disabled is None:
        return False, True

    try:
        preferred_target = (
            _canonical_create_direction(preferred, "PreferredSpoutput")
            if preferred is not None
            else None
        )
        if disabled is None:
            disabled_target = None
        else:
            if not isinstance(disabled, nbt.TAG_List) or any(
                not isinstance(entry, nbt.TAG_String) for entry in disabled
            ):
                raise ValueError("basin DisabledSpoutput is not a StringTag list")
            disabled_target = [
                _canonical_create_direction(entry, f"DisabledSpoutput[{index}]")
                for index, entry in enumerate(disabled)
            ]
    except ValueError as exc:
        _block_entity_blocker(block, audit, str(exc))
        return False, False

    preferred_before = string_value(preferred) if preferred is not None else None
    disabled_before = (
        [string_value(entry) for entry in disabled]
        if disabled is not None
        else None
    )
    changed = (
        (preferred is not None and preferred_before != preferred_target)
        or (disabled is not None and disabled_before != disabled_target)
    )
    if not changed:
        return False, True
    if preferred is not None:
        block["PreferredSpoutput"] = nbt.TAG_String(preferred_target)
    if disabled is not None:
        block["DisabledSpoutput"] = list_tag(
            [nbt.TAG_String(value) for value in disabled_target], nbt.TAG_String
        )
    audit.setdefault("basin_direction_conversions", []).append(
        {
            **block_position_ref(block),
            "id": "create:basin",
            "preferred_before": preferred_before,
            "preferred_after": preferred_target,
            "disabled_before": disabled_before,
            "disabled_after": disabled_target,
        }
    )
    return True, True


def _validate_cei_blaze_forger_inventory(block, inventory):
    if not isinstance(inventory, nbt.TAG_Compound):
        raise ValueError("blaze_forger Inventory is not a compound")
    size = inventory.get("Size")
    if not isinstance(size, nbt.TAG_Int):
        raise ValueError("blaze_forger Inventory.Size is not an IntTag")
    size_value = as_int(size)
    if size_value not in (4, 6):
        raise ValueError(
            f"blaze_forger Inventory.Size is {size_value}, expected source 4 or target 6"
        )
    keys = set(inventory.keys())
    if size_value == 4:
        if keys != CEI_BLAZE_FORGER_SOURCE_INVENTORY_KEYS:
            unknown = sorted(keys - CEI_BLAZE_FORGER_SOURCE_INVENTORY_KEYS)
            missing = sorted(CEI_BLAZE_FORGER_SOURCE_INVENTORY_KEYS - keys)
            raise ValueError(
                "blaze_forger source Inventory fields differ from the proven schema"
                f" (unknown={unknown}, missing={missing})"
            )
    elif frozenset(keys) not in {
        frozenset(CEI_BLAZE_FORGER_SOURCE_INVENTORY_KEYS),
        frozenset(CEI_BLAZE_FORGER_TARGET_INVENTORY_KEYS),
    }:
        raise ValueError("blaze_forger target Inventory fields differ from the proven schema")

    items = inventory.get("Items")
    if not isinstance(items, nbt.TAG_List) or any(
        not isinstance(entry, nbt.TAG_Compound) for entry in items
    ):
        raise ValueError("blaze_forger Inventory.Items is not a compound list")
    occupied = set()
    max_slot = size_value - 1
    for index, entry in enumerate(items):
        slot_tag = entry.get("Slot")
        if not isinstance(slot_tag, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
            raise ValueError(f"blaze_forger Inventory.Items[{index}].Slot is not an integer")
        slot = as_int(slot_tag)
        if not 0 <= slot <= max_slot:
            raise ValueError(
                f"blaze_forger Inventory.Items[{index}].Slot {slot} is outside 0..{max_slot}"
            )
        if slot in occupied:
            raise ValueError(f"blaze_forger Inventory.Items duplicates Slot {slot}")
        occupied.add(slot)
        identifier = entry.get("id")
        count = entry.get("count")
        allowed = {"Slot", "id", "count", "components"}
        unknown = sorted(set(entry.keys()) - allowed)
        if unknown:
            raise ValueError(
                f"blaze_forger Inventory.Items[{index}] has unknown fields: {', '.join(unknown)}"
            )
        if not isinstance(identifier, nbt.TAG_String) or not RESOURCE_LOCATION_PATTERN.fullmatch(
            string_value(identifier)
        ):
            raise ValueError(f"blaze_forger Inventory.Items[{index}].id is malformed")
        if not isinstance(count, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)) or not 1 <= as_int(count) <= 99:
            raise ValueError(f"blaze_forger Inventory.Items[{index}].count is outside 1..99")
        components = entry.get("components")
        if components is not None and not isinstance(components, nbt.TAG_Compound):
            raise ValueError(f"blaze_forger Inventory.Items[{index}].components is not a compound")

    cost = inventory.get("Cost")
    operation = inventory.get("Mode", inventory.get("Operation"))
    if not isinstance(cost, nbt.TAG_Int) or as_int(cost) < 0:
        raise ValueError("blaze_forger Inventory.Cost is not a non-negative IntTag")
    if not isinstance(operation, nbt.TAG_Int) or as_int(operation) not in (0, 1, 2):
        raise ValueError("blaze_forger Inventory mode is not an IntTag in 0..2")
    for key in ("Conflicting", "OverCap"):
        value = inventory.get(key)
        if not isinstance(value, nbt.TAG_Byte) or as_int(value) not in (0, 1):
            raise ValueError(f"blaze_forger Inventory.{key} is not a byte boolean")
    return size_value, sorted(occupied)


def convert_cei_blaze_forger_inventory(block, audit):
    """Expand the persisted four active slots to the target's six internal slots."""
    inventory = block.get("Inventory")
    try:
        size, occupied = _validate_cei_blaze_forger_inventory(block, inventory)
    except ValueError as exc:
        _block_entity_blocker(block, audit, str(exc))
        return False, False
    legacy_layout = "Mode" in inventory
    operation = as_int(inventory["Mode"] if legacy_layout else inventory["Operation"])
    existing_mode = block.get("ForgingMode")
    if existing_mode is not None and (
        not isinstance(existing_mode, nbt.TAG_Int)
        or as_int(existing_mode) != operation
    ):
        _block_entity_blocker(
            block,
            audit,
            "blaze_forger ForgingMode conflicts with its inventory operation",
        )
        return False, False
    changed = size == 4 or legacy_layout or existing_mode is None
    if not changed:
        return False, True
    if size == 4:
        inventory["Size"] = nbt.TAG_Int(6)
    if legacy_layout:
        inventory["Operation"] = nbt.TAG_Int(operation)
        del inventory["Mode"]
    if existing_mode is None:
        block["ForgingMode"] = nbt.TAG_Int(operation)
    audit.setdefault("blaze_forger_inventory_conversions", []).append(
        {
            **block_position_ref(block),
            "id": "create_enchantment_industry:blaze_forger",
            "source_size": size,
            "target_size": 6,
            "preserved_slots": occupied,
            "derived_result_slots": [4, 5],
            "legacy_mode": operation if legacy_layout else None,
            "target_operation": operation,
            "target_forging_mode": operation,
        }
    )
    return True, True


def _component_json_value(value, path="Component"):
    """Map ComponentSerialization.CODEC's NbtOps tree to JSON-compatible data."""
    if isinstance(value, nbt.TAG_Compound):
        if not value:
            raise ValueError(f"{path} is an empty compound")
        return {
            key: _component_json_value(child, f"{path}.{key}")
            for key, child in value.items()
        }
    if isinstance(value, nbt.TAG_List):
        if not value:
            raise ValueError(f"{path} is an empty list")
        return [
            _component_json_value(child, f"{path}[{index}]")
            for index, child in enumerate(value)
        ]
    if isinstance(value, nbt.TAG_String):
        return string_value(value)
    if isinstance(value, nbt.TAG_Byte):
        number = as_int(value)
        if number in (0, 1):
            return bool(number)
        return number
    if isinstance(value, (nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
        return as_int(value)
    if isinstance(value, (nbt.TAG_Float, nbt.TAG_Double)):
        number = as_float(value)
        if not math.isfinite(number):
            raise ValueError(f"{path} is not finite")
        return number
    raise ValueError(f"{path} has unsupported {type(value).__name__}")


def _valid_component_json_tree(value, *, root=True):
    if value is None:
        return False
    if root and not isinstance(value, (str, dict, list)):
        return False
    if isinstance(value, dict):
        return bool(value) and all(
            isinstance(key, str) and _valid_component_json_tree(child, root=False)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return bool(value) and all(
            _valid_component_json_tree(child, root=False) for child in value
        )
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, (str, bool, int))


def _assembly_component_json(component):
    if component is None:
        raise ValueError("LastException.Component is missing")
    if isinstance(component, nbt.TAG_String):
        raw = string_value(component)
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if _valid_component_json_tree(parsed):
            return raw, "target_json"
        return json.dumps(raw, ensure_ascii=False, separators=(",", ":")), "source_string"
    if not isinstance(component, (nbt.TAG_Compound, nbt.TAG_List)):
        raise ValueError(
            f"LastException.Component is unsupported {type(component).__name__}"
        )
    tree = _component_json_value(component, "LastException.Component")
    if not _valid_component_json_tree(tree):
        raise ValueError("LastException.Component is not a valid component tree")
    return json.dumps(tree, ensure_ascii=False, separators=(",", ":")), "source_nbt"


def _pack_block_pos(values):
    x, y, z = values
    if not -33_554_432 <= x <= 33_554_431:
        raise ValueError("LastException.Position x is outside packed BlockPos range")
    if not -2_048 <= y <= 2_047:
        raise ValueError("LastException.Position y is outside packed BlockPos range")
    if not -33_554_432 <= z <= 33_554_431:
        raise ValueError("LastException.Position z is outside packed BlockPos range")
    packed = ((x & 0x3FFFFFF) << 38) | ((z & 0x3FFFFFF) << 12) | (y & 0xFFF)
    return packed - (1 << 64) if packed >= (1 << 63) else packed


def convert_elevator_assembly_exception(block, audit):
    """Convert Create 6.0.9's codec NBT to 6.0.10's JSON/packed form."""
    last_exception = block.get("LastException")
    if last_exception is None:
        return False, True
    if not isinstance(last_exception, nbt.TAG_Compound):
        _block_entity_blocker(
            block, audit, "elevator pulley LastException is not a compound"
        )
        return False, False
    unknown = sorted(set(last_exception.keys()) - {"Component", "Position"})
    if unknown:
        _block_entity_blocker(
            block,
            audit,
            "elevator pulley LastException has unknown fields: " + ", ".join(unknown),
        )
        return False, False

    try:
        component_json, component_format = _assembly_component_json(
            last_exception.get("Component")
        )
    except (TypeError, ValueError, OverflowError) as exc:
        _block_entity_blocker(block, audit, f"elevator pulley {exc}")
        return False, False

    position = last_exception.get("Position")
    position_before = None
    position_after = None
    position_changed = False
    if position is not None:
        if isinstance(position, nbt.TAG_Long):
            position_after = as_int(position)
        elif isinstance(position, nbt.TAG_Int_Array) and len(position.value) == 3:
            try:
                position_before = [int(value) for value in position.value]
                position_after = _pack_block_pos(position_before)
            except (TypeError, ValueError, OverflowError) as exc:
                _block_entity_blocker(block, audit, f"elevator pulley {exc}")
                return False, False
            position_changed = True
        else:
            _block_entity_blocker(
                block,
                audit,
                "elevator pulley LastException.Position is neither source IntArray[3] nor target LongTag",
            )
            return False, False

    component = last_exception.get("Component")
    component_changed = not (
        isinstance(component, nbt.TAG_String)
        and string_value(component) == component_json
        and component_format == "target_json"
    )
    if not component_changed and not position_changed:
        return False, True

    target = clone_tag(last_exception)
    target["Component"] = nbt.TAG_String(component_json)
    if position_changed:
        target["Position"] = nbt.TAG_Long(position_after)
    block["LastException"] = target
    audit.setdefault("assembly_exception_conversions", []).append(
        {
            "id": "create:elevator_pulley",
            "component_source_format": component_format,
            "component_json": component_json,
            "position_source": position_before,
            "position_packed": position_after,
            **block_position_ref(block),
        }
    )
    return True, True


def _uuid_int_array(values):
    result = nbt.TAG_Int_Array()
    result.value = list(values)
    result.update_fmt(len(result.value))
    return result


def _signed_int32(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= (1 << 31) else value


def _uuid_words(value):
    number = value.int
    return [
        _signed_int32(number >> 96),
        _signed_int32(number >> 64),
        _signed_int32(number >> 32),
        _signed_int32(number),
    ]


def convert_cookery_millstone_uuid(block, audit):
    """Convert Cookery's UUID string/default into the target UUID IntArray."""
    entity_id = block.get("EntityId")
    source_uuid = None
    if entity_id is None:
        parsed = uuid.UUID(int=0)
        source_format = "missing_default_nil"
    elif isinstance(entity_id, nbt.TAG_String):
        source_uuid = string_value(entity_id)
        if not UUID_TEXT_PATTERN.fullmatch(source_uuid):
            _block_entity_blocker(
                block, audit, "millstone EntityId is not a canonical UUID string"
            )
            return False, False
        try:
            parsed = uuid.UUID(source_uuid)
        except (AttributeError, TypeError, ValueError):
            _block_entity_blocker(
                block, audit, "millstone EntityId is not a valid UUID string"
            )
            return False, False
        source_format = "uuid_string"
    elif isinstance(entity_id, nbt.TAG_Int_Array):
        words = [int(value) for value in entity_id.value]
        if len(words) != 4 or any(
            value < -2_147_483_648 or value > 2_147_483_647 for value in words
        ):
            _block_entity_blocker(
                block, audit, "millstone target EntityId is not a signed IntArray[4]"
            )
            return False, False
        return False, True
    else:
        _block_entity_blocker(
            block,
            audit,
            f"millstone EntityId has unsupported {type(entity_id).__name__}",
        )
        return False, False

    words = _uuid_words(parsed)
    block["EntityId"] = _uuid_int_array(words)
    audit.setdefault("millstone_uuid_conversions", []).append(
        {
            "id": "kaleidoscope_cookery:millstone",
            "source_format": source_format,
            "source_uuid": source_uuid,
            "target_uuid": str(parsed),
            "target_int_array": words,
            **block_position_ref(block),
        }
    )
    return True, True


def convert_create_fluid_payload(block, audit):
    """Transactionally normalize Create Fabric fluid stacks and capacities."""
    from convert_create_fluid_nbt import (
        audit_source_fluid_tree,
        audit_source_mounted_storages,
        convert_create_fluid_tree,
    )

    stack_records = audit_source_fluid_tree(block, "BlockEntity")
    mounted_records = audit_source_mounted_storages(block, "BlockEntity")
    source_format = (
        bool(stack_records)
        or audit.get("source_data_version") is not None
        and int(audit["source_data_version"]) >= 4671
        and bool(mounted_records)
    )
    if not stack_records and not mounted_records:
        return False, True
    blockers = []
    normalizations = []
    converted = convert_create_fluid_tree(
        block,
        "BlockEntity",
        blockers,
        source_format,
        normalizations,
    )
    if blockers or converted is None:
        audit.setdefault("unsupported_create_fluids", []).append(
            {
                **block_position_ref(block),
                "id": string_value(block.get("id", nbt.TAG_String(""))),
                "reason": "Create fluid schema conversion blocked",
                "blockers": blockers,
            }
        )
        return False, False
    floor_normalizations = [
        value for value in normalizations
        if value.get("normalization") == "semantic_floor"
    ]
    potion_scale_conversions = [
        value for value in normalizations
        if value.get("normalization") in {
            "exact_potion_bottle_scale",
            "nearest_potion_bottle_scale",
        }
    ]
    audit.setdefault("create_fluid_semantic_floor_normalizations", []).extend(
        floor_normalizations
    )
    audit.setdefault("create_fluid_exact_potion_scale_conversions", []).extend(
        potion_scale_conversions
    )
    audit.setdefault("create_fluid_nearest_potion_scale_conversions", []).extend(
        value for value in potion_scale_conversions
        if value.get("normalization") == "nearest_potion_bottle_scale"
    )
    changed = comparable_tag(block) != comparable_tag(converted)
    if not changed:
        return False, True
    for key in list(block.keys()):
        del block[key]
    for key, child in converted.items():
        block[key] = child
    audit.setdefault("create_fluid_conversions", []).append(
        {
            **block_position_ref(block),
            "id": string_value(block.get("id", nbt.TAG_String(""))),
            "fluid_stacks": len(stack_records),
            "mounted_storages": len(mounted_records),
            "source_ids": sorted({record.get("id") for record in stack_records}),
            "semantic_floor_normalizations": normalizations,
            "exact_potion_scale_conversions": potion_scale_conversions,
        }
    )
    return True, True


def _item_vault_blocker(block, audit, reason):
    audit.setdefault("unsupported_block_entities", []).append(
        {
            "id": "create:item_vault",
            "reason": reason,
            **block_position_ref(block),
        }
    )


def _validate_target_item_vault_inventory(block, inventory, audit):
    if set(inventory.keys()) != {"Size", "Items"}:
        _item_vault_blocker(
            block,
            audit,
            "target item_vault Inventory must contain exactly Size and Items",
        )
        return False
    size = inventory.get("Size")
    if not isinstance(size, nbt.TAG_Int) or as_int(size) != CREATE_ITEM_VAULT_INVENTORY_SIZE:
        _item_vault_blocker(
            block,
            audit,
            f"target item_vault Inventory Size is not IntTag {CREATE_ITEM_VAULT_INVENTORY_SIZE}",
        )
        return False
    items = inventory.get("Items")
    if not isinstance(items, nbt.TAG_List):
        _item_vault_blocker(block, audit, "target item_vault Inventory.Items is not a list")
        return False
    slots = set()
    for index, item in enumerate(items):
        if not isinstance(item, nbt.TAG_Compound):
            _item_vault_blocker(
                block,
                audit,
                f"target item_vault Inventory.Items[{index}] is not a compound",
            )
            return False
        slot = item.get("Slot")
        if not isinstance(slot, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
            _item_vault_blocker(
                block,
                audit,
                f"target item_vault Inventory.Items[{index}].Slot is not an integer",
            )
            return False
        slot_value = as_int(slot)
        if not 0 <= slot_value < CREATE_ITEM_VAULT_INVENTORY_SIZE:
            _item_vault_blocker(
                block,
                audit,
                f"target item_vault slot {slot_value} is outside 0..{CREATE_ITEM_VAULT_INVENTORY_SIZE - 1}",
            )
            return False
        if slot_value in slots:
            _item_vault_blocker(block, audit, f"target item_vault duplicates Slot {slot_value}")
            return False
        slots.add(slot_value)
    return True


def convert_create_item_vault_inventory(block, audit):
    """Convert the 1.21.11 positional vault list to NeoForge ItemStackHandler NBT.

    Create 1.21.11 writes only non-empty stacks to a positional ``Inventory``
    list and reads them back from slot zero upward.  Create 6.0.10 on NeoForge
    instead delegates to ``ItemStackHandler``, whose persistent shape is the
    compound ``{Size, Items:[... Slot ...]}``.  Feeding the old list to
    ``CompoundTag#getCompound`` silently produces an empty compound, so the
    first target save permanently replaces every vault inventory with empty
    data.  Preserve the source list order by assigning consecutive slots.
    """
    inventory = block.get("Inventory")
    if isinstance(inventory, nbt.TAG_Compound):
        return False, _validate_target_item_vault_inventory(block, inventory, audit)
    if not isinstance(inventory, nbt.TAG_List):
        _item_vault_blocker(
            block,
            audit,
            "item_vault Inventory is neither the source list nor target compound",
        )
        return False, False
    if len(inventory) > CREATE_ITEM_VAULT_INVENTORY_SIZE:
        _item_vault_blocker(
            block,
            audit,
            f"source item_vault has {len(inventory)} stacks, exceeding target capacity {CREATE_ITEM_VAULT_INVENTORY_SIZE}",
        )
        return False, False

    items = nbt.TAG_List(type=nbt.TAG_Compound)
    for slot, source_item in enumerate(inventory):
        if not isinstance(source_item, nbt.TAG_Compound):
            _item_vault_blocker(
                block,
                audit,
                f"source item_vault Inventory[{slot}] is not a compound",
            )
            return False, False
        if "Slot" in source_item:
            _item_vault_blocker(
                block,
                audit,
                f"source positional item_vault Inventory[{slot}] unexpectedly contains Slot",
            )
            return False, False
        target_item = clone_tag(source_item)
        target_item["Slot"] = nbt.TAG_Int(slot)
        items.append(target_item)

    target = nbt.TAG_Compound()
    target["Size"] = nbt.TAG_Int(CREATE_ITEM_VAULT_INVENTORY_SIZE)
    target["Items"] = items
    block["Inventory"] = target
    audit.setdefault("item_vault_inventory_conversions", []).append(
        {
            "id": "create:item_vault",
            "source_encoding": "positional_list",
            "target_encoding": "neoforge_item_stack_handler",
            "occupied_slots": len(items),
            "capacity": CREATE_ITEM_VAULT_INVENTORY_SIZE,
            **block_position_ref(block),
        }
    )
    return True, True


def convert_create_fluid_tank_storage(block, audit):
    """Wrap the 1.21.11 root Fluid stack in NeoForge's TankContent compound."""
    root_fluid = block.get("Fluid")
    tank_content = block.get("TankContent")

    if root_fluid is not None:
        if tank_content is not None:
            _block_entity_blocker(
                block,
                audit,
                "create:fluid_tank contains both legacy Fluid and target TankContent",
            )
            return False, False
        if not isinstance(root_fluid, nbt.TAG_Compound):
            _block_entity_blocker(block, audit, "create:fluid_tank root Fluid is not a compound")
            return False, False
        target = nbt.TAG_Compound()
        target["Fluid"] = clone_tag(root_fluid)
        block["TankContent"] = target
        del block["Fluid"]
        audit.setdefault("fluid_tank_storage_conversions", []).append(
            {
                "id": "create:fluid_tank",
                "source_encoding": "root_fluid",
                "target_encoding": "tank_content_fluid",
                **block_position_ref(block),
            }
        )
        return True, True

    if tank_content is None:
        # Empty source tanks omit Fluid entirely; the target reader treats an
        # absent TankContent as an empty compound, so no synthetic tag is needed.
        return False, True
    if not isinstance(tank_content, nbt.TAG_Compound):
        _block_entity_blocker(block, audit, "create:fluid_tank TankContent is not a compound")
        return False, False

    # Repair the earlier converter fixture/candidate shape where the FluidStack
    # itself was placed directly at TankContent instead of below TankContent.Fluid.
    if isinstance(tank_content.get("id"), nbt.TAG_String) and isinstance(
        tank_content.get("amount"), nbt.TAG_Int
    ):
        target = nbt.TAG_Compound()
        target["Fluid"] = clone_tag(tank_content)
        block["TankContent"] = target
        audit.setdefault("fluid_tank_storage_conversions", []).append(
            {
                "id": "create:fluid_tank",
                "source_encoding": "direct_tank_content_fluid_stack",
                "target_encoding": "tank_content_fluid",
                **block_position_ref(block),
            }
        )
        return True, True

    fluid = tank_content.get("Fluid")
    if fluid is not None and not isinstance(fluid, nbt.TAG_Compound):
        _block_entity_blocker(block, audit, "create:fluid_tank TankContent.Fluid is not a compound")
        return False, False
    unknown = sorted(set(tank_content.keys()) - {"Fluid"})
    if unknown:
        _block_entity_blocker(
            block,
            audit,
            "create:fluid_tank TankContent contains unaudited fields: " + ", ".join(unknown),
        )
        return False, False
    return False, True


CREATE_SMART_TANK_LIST_FIELDS = {
    "create:basin": ("InputTanks", "OutputTanks"),
    "create:item_drain": ("Tanks",),
    "create:spout": ("Tanks",),
    "create_enchantment_industry:blaze_enchanter": ("Tanks",),
    "create_enchantment_industry:blaze_forger": ("Tanks",),
    "create_enchantment_industry:experience_lantern": ("Tanks",),
}


def _wrap_smart_tank_segment(block, segment, audit, path):
    if not isinstance(segment, nbt.TAG_Compound):
        _block_entity_blocker(block, audit, f"{path} is not a compound")
        return False, False
    tank_content = segment.get("TankContent")
    if tank_content is None:
        return False, True
    if not isinstance(tank_content, nbt.TAG_Compound):
        _block_entity_blocker(block, audit, f"{path}.TankContent is not a compound")
        return False, False
    if isinstance(tank_content.get("id"), nbt.TAG_String) and isinstance(
        tank_content.get("amount"), nbt.TAG_Int
    ):
        wrapped = nbt.TAG_Compound()
        wrapped["Fluid"] = clone_tag(tank_content)
        segment["TankContent"] = wrapped
        audit.setdefault("internal_fluid_storage_conversions", []).append(
            {
                "id": string_value(block.get("id", nbt.TAG_String(""))),
                "path": path + ".TankContent",
                "source_encoding": "direct_fluid_stack",
                "target_encoding": "fluid_tank_compound",
                **block_position_ref(block),
            }
        )
        return True, True
    fluid = tank_content.get("Fluid")
    if fluid is not None and not isinstance(fluid, nbt.TAG_Compound):
        _block_entity_blocker(block, audit, f"{path}.TankContent.Fluid is not a compound")
        return False, False
    unknown = sorted(set(tank_content.keys()) - {"Fluid"})
    if unknown:
        _block_entity_blocker(
            block,
            audit,
            f"{path}.TankContent contains unaudited fields: " + ", ".join(unknown),
        )
        return False, False
    return False, True


def convert_create_internal_fluid_storage(block, audit):
    """Convert Create's 1.21.11 fluid-storage envelopes to NeoForge shapes."""
    identifier = string_value(block.get("id", nbt.TAG_String("")))
    if identifier == "create:hose_pulley":
        root_fluid = block.get("Fluid")
        tank = block.get("Tank")
        if root_fluid is not None:
            if not isinstance(root_fluid, nbt.TAG_Compound):
                _block_entity_blocker(block, audit, "create:hose_pulley Fluid is not a compound")
                return False, False
            if tank is not None and (
                not isinstance(tank, nbt.TAG_Compound) or "Fluid" in tank
            ):
                _block_entity_blocker(
                    block,
                    audit,
                    "create:hose_pulley contains both legacy Fluid and populated target Tank",
                )
                return False, False
            if tank is None:
                tank = nbt.TAG_Compound()
            tank["Fluid"] = clone_tag(root_fluid)
            block["Tank"] = tank
            del block["Fluid"]
            audit.setdefault("internal_fluid_storage_conversions", []).append(
                {
                    "id": identifier,
                    "path": "Fluid",
                    "source_encoding": "root_fluid",
                    "target_encoding": "Tank.Fluid",
                    **block_position_ref(block),
                }
            )
            return True, True
        if tank is None:
            return False, True
        if not isinstance(tank, nbt.TAG_Compound):
            _block_entity_blocker(block, audit, "create:hose_pulley Tank is not a compound")
            return False, False
        fluid = tank.get("Fluid")
        if fluid is not None and not isinstance(fluid, nbt.TAG_Compound):
            _block_entity_blocker(block, audit, "create:hose_pulley Tank.Fluid is not a compound")
            return False, False
        unknown = sorted(set(tank.keys()) - {"Fluid"})
        if unknown:
            _block_entity_blocker(
                block,
                audit,
                "create:hose_pulley Tank contains unaudited fields: " + ", ".join(unknown),
            )
            return False, False
        return False, True

    fields = CREATE_SMART_TANK_LIST_FIELDS.get(identifier)
    if fields is None:
        return False, True
    changed = False
    for field in fields:
        values = block.get(field)
        if values is None:
            continue
        if not isinstance(values, nbt.TAG_List):
            _block_entity_blocker(block, audit, f"{identifier} {field} is not a list")
            return changed, False
        for index, segment in enumerate(values):
            segment_changed, safe = _wrap_smart_tank_segment(
                block,
                segment,
                audit,
                f"{field}[{index}]",
            )
            changed = segment_changed or changed
            if not safe:
                return changed, False
    return changed, True


def _convert_block_entity_in_place(block, audit):
    """Map known block-entity schemas on an isolated working copy."""
    item_changed, item_safe = convert_block_entity_components_and_items(
        block, audit
    )
    if not item_safe:
        return False, False
    identifier = string_value(block.get("id", nbt.TAG_String("")))
    fluid_changed, fluid_safe = convert_create_fluid_payload(block, audit)
    changed = item_changed or fluid_changed
    if not fluid_safe:
        return changed, False
    if identifier == "create:item_vault":
        schema_changed, schema_safe = convert_create_item_vault_inventory(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    elif identifier == "create:fluid_tank":
        schema_changed, schema_safe = convert_create_fluid_tank_storage(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    if identifier == "create:hose_pulley" or identifier in CREATE_SMART_TANK_LIST_FIELDS:
        schema_changed, schema_safe = convert_create_internal_fluid_storage(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    if identifier == "minecraft:trial_spawner":
        schema_changed, schema_safe = convert_trial_spawner_configs(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    elif identifier == "create:basin":
        schema_changed, schema_safe = convert_create_basin_directions(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    elif identifier == "create_enchantment_industry:blaze_forger":
        schema_changed, schema_safe = convert_cei_blaze_forger_inventory(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    elif identifier == "create:elevator_pulley":
        schema_changed, schema_safe = convert_elevator_assembly_exception(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    elif identifier == "kaleidoscope_cookery:millstone":
        schema_changed, schema_safe = convert_cookery_millstone_uuid(block, audit)
        changed = schema_changed or changed
        if not schema_safe:
            return changed, False
    target_identifier = BLOCK_ENTITY_ID_ALIASES.get(identifier)
    if target_identifier is not None:
        block["id"] = nbt.TAG_String(target_identifier)
        audit.setdefault("block_entity_id_aliases", []).append(
            {"source_id": identifier, "target_id": target_identifier, **block_position_ref(block)}
        )
        changed = True

    if identifier == "create:schematicannon":
        inventory_changed, inventory_safe = convert_schematicannon_inventory(block, audit)
        changed = inventory_changed or changed
        if not inventory_safe:
            return changed, False

        state = block.get("State")
        if state is not None:
            if not isinstance(state, nbt.TAG_String):
                audit.setdefault("unsupported_block_entities", []).append(
                    {"id": identifier, "reason": "schematicannon State is not a string", **block_position_ref(block)}
                )
                return changed, False
            state_value = string_value(state)
            mapped = SCHEMATICANNON_STATES.get(state_value.lower())
            if mapped is None:
                audit.setdefault("unsupported_block_entities", []).append(
                    {"id": identifier, "state": state_value, "reason": "unknown schematicannon state", **block_position_ref(block)}
                )
                return changed, False
            if state_value != mapped:
                block["State"] = nbt.TAG_String(mapped)
                audit.setdefault("block_entity_state_aliases", []).append(
                    {"id": identifier, "source_state": state_value, "target_state": mapped, **block_position_ref(block)}
                )
                changed = True

        # Create stores the printer's nested enum separately from the
        # block-entity State.  The 1.21.1 reader calls Enum.valueOf directly,
        # so lowercase 1.21.11 values must be normalized before the first
        # target load; unknown schemas remain fail-closed.
        printer = block.get("Printer")
        if printer is not None:
            if not isinstance(printer, nbt.TAG_Compound):
                audit.setdefault("unsupported_block_entities", []).append(
                    {"id": identifier, "reason": "schematicannon Printer is not a compound", **block_position_ref(block)}
                )
                return changed, False
            print_stage = printer.get("PrintStage")
            if print_stage is not None:
                if not isinstance(print_stage, nbt.TAG_String):
                    audit.setdefault("unsupported_block_entities", []).append(
                        {"id": identifier, "reason": "schematicannon PrintStage is not a string", **block_position_ref(block)}
                    )
                    return changed, False
                stage_value = string_value(print_stage)
                mapped_stage = SCHEMATICANNON_PRINT_STAGES.get(stage_value.lower())
                if mapped_stage is None:
                    audit.setdefault("unsupported_block_entities", []).append(
                        {
                            "id": identifier,
                            "print_stage": stage_value,
                            "reason": "unknown schematicannon print stage",
                            **block_position_ref(block),
                        }
                    )
                    return changed, False
                if stage_value != mapped_stage:
                    printer["PrintStage"] = nbt.TAG_String(mapped_stage)
                    audit.setdefault("block_entity_print_stage_aliases", []).append(
                        {
                            "id": identifier,
                            "source_print_stage": stage_value,
                            "target_print_stage": mapped_stage,
                            **block_position_ref(block),
                        }
                    )
                    changed = True

    return changed, True


BLOCK_ENTITY_TRANSACTION_BLOCKER_KEYS = (
    "unsupported_block_entity_items",
    "unsupported_block_entity_components",
    "unsupported_create_fluids",
    "unsupported_block_entities",
)


def _snapshot_block_entity_audit(audit):
    """Capture cheap append/replace boundaries for one BE transaction.

    Audits can contain millions of records in a full-world run, so copying the
    entire audit for every block entity would be both quadratic and memory
    hostile. Conversion code appends to record lists and increments ``counts``;
    retain only their boundaries, plus a small snapshot of scalar metadata.
    """
    list_lengths = {
        key: len(value)
        for key, value in audit.items()
        if isinstance(value, list)
    }
    counts = audit.get("counts")
    counts_snapshot = Counter(counts) if isinstance(counts, Counter) else None
    scalar_snapshot = {
        key: copy.deepcopy(value)
        for key, value in audit.items()
        if key not in list_lengths and key != "counts"
    }
    return set(audit), list_lengths, counts_snapshot, scalar_snapshot


def _rollback_block_entity_audit(audit, snapshot):
    keys_before, list_lengths, counts_snapshot, scalar_snapshot = snapshot
    for key in list(audit):
        if key not in keys_before:
            del audit[key]
            continue
        if key in list_lengths and isinstance(audit.get(key), list):
            del audit[key][list_lengths[key]:]
    if counts_snapshot is not None:
        counts = audit.setdefault("counts", Counter())
        counts.clear()
        counts.update(counts_snapshot)
    for key, value in scalar_snapshot.items():
        audit[key] = copy.deepcopy(value)


def convert_block_entity(block, audit):
    """Transactionally map the observed block-entity schema changes.

    Several block entities contain multiple independently encoded fields. A
    late malformed field must not allow an earlier valid field (or its audit
    conversion records) to leak into the chunk. Run the complete conversion
    against an NBT clone, commit only after every path validates, and retain
    only the newly discovered blocker records when validation fails.
    """
    working = clone_tag(block)
    audit_snapshot = _snapshot_block_entity_audit(audit)
    _, list_lengths, _, _ = audit_snapshot
    try:
        changed, safe = _convert_block_entity_in_place(working, audit)
    except Exception:
        _rollback_block_entity_audit(audit, audit_snapshot)
        raise
    if not safe:
        blocker_deltas = {
            key: copy.deepcopy(audit.get(key, [])[list_lengths.get(key, 0):])
            for key in BLOCK_ENTITY_TRANSACTION_BLOCKER_KEYS
        }
        _rollback_block_entity_audit(audit, audit_snapshot)
        for key, records in blocker_deltas.items():
            audit.setdefault(key, []).extend(records)
        return False
    if changed:
        for key in list(block.keys()):
            del block[key]
        for key, child in working.items():
            block[key] = child
    return changed


def block_position_ref(block):
    result = {}
    for key in ("x", "y", "z"):
        if key not in block:
            result[key] = None
            continue
        try:
            result[key] = as_int(block[key])
        except (TypeError, ValueError, OverflowError):
            result[key] = None
    return result


def convert_block_attachment(entity, audit):
    """Convert modern block_pos to the legacy TileX/TileY/TileZ anchor."""
    source = entity.get("block_pos")
    if source is None:
        return False
    identifier = string_value(entity.get("id", nbt.TAG_String("")))
    if identifier not in BLOCK_ATTACHED_ENTITY_IDS:
        # Do not guess for a mod entity whose block_pos contract we have not
        # audited.  Leaving it in place would make the target silently load at
        # (0,0,0), so this is deliberately a preflight blocker.
        audit.setdefault("unsupported_entities", []).append(
            {**entity_ref(entity), "reason": "unknown block_pos entity schema"}
        )
        return False
    try:
        vector = read_int_vector(source)
    except (TypeError, ValueError, OverflowError):
        vector = None
    if vector is None or len(vector) != 3:
        audit.setdefault("unsupported_entities", []).append(
            {**entity_ref(entity), "reason": "block_pos is not a 3-element integer vector"}
        )
        return False
    target = {"TileX": int(vector[0]), "TileY": int(vector[1]), "TileZ": int(vector[2])}
    for key, expected in target.items():
        try:
            existing = as_int(entity[key]) if key in entity else expected
        except (TypeError, ValueError, OverflowError):
            audit.setdefault("unsupported_entities", []).append(
                {**entity_ref(entity), "reason": f"malformed {key} and block_pos", "key": key}
            )
            return False
        if key in entity and existing != expected:
            audit.setdefault("unsupported_entities", []).append(
                {**entity_ref(entity), "reason": f"conflicting {key} and block_pos", "key": key}
            )
            return False
    changed = False
    for key, expected in target.items():
        if key not in entity:
            entity[key] = nbt.TAG_Int(expected)
            changed = True
    if "block_pos" in entity:
        del entity["block_pos"]
        changed = True
    if changed:
        audit.setdefault("block_positions", []).append({**entity_ref(entity), "target": target})
    return changed


def convert_item_map(entity, audit):
    equipment = entity.get("equipment")
    if not isinstance(equipment, nbt.TAG_Compound):
        return False
    slots = set(equipment.keys())
    unknown_slots = sorted(slots - KNOWN_EQUIPMENT_SLOTS)
    if unknown_slots:
        audit.setdefault("unsupported_equipment", []).append({**entity_ref(entity), "slots": unknown_slots})
        return False
    drops = entity.get("drop_chances")
    # 1.21.1 stores saddles in entity-specific fields; never delete the source
    # map until the target entity's exact schema is known.
    if "saddle" in equipment:
        identifier = string_value(entity.get("id", nbt.TAG_String("")))
        saddle = clone_tag(equipment["saddle"])
        if identifier in SADDLE_ITEM_ENTITY_IDS:
            entity["SaddleItem"] = saddle
        elif identifier in SADDLE_BOOLEAN_ENTITY_IDS:
            entity["Saddle"] = nbt.TAG_Byte(0 if item_is_empty(saddle) else 1)
        else:
            audit.setdefault("unsupported_equipment", []).append({**entity_ref(entity), "slots": ["saddle"], "reason": "no target saddle schema"})
            return False
        if not isinstance(drops, nbt.TAG_Compound) or "saddle" not in drops or not math.isclose(
            as_float(drops["saddle"]), 2.0, rel_tol=0.0, abs_tol=1e-7
        ):
            audit.setdefault("unsupported_equipment", []).append({
                **entity_ref(entity),
                "slots": ["saddle"],
                "reason": "target saddle storage always drops its item; source drop chance must be exactly 2.0",
            })
            return False
        audit.setdefault("saddle_equipment", []).append({**entity_ref(entity), "item": string_value(saddle.get("id", nbt.TAG_String(""))), "target_key": "SaddleItem" if identifier in SADDLE_ITEM_ENTITY_IDS else "Saddle"})
    hands = [clone_tag(equipment.get(name, empty_item())) for name in HAND_SLOTS]
    armor = [clone_tag(equipment.get(name, empty_item())) for name in ARMOR_SLOTS]
    entity["HandItems"] = list_tag(hands, nbt.TAG_Compound)
    entity["ArmorItems"] = list_tag(armor, nbt.TAG_Compound)
    default = 0.085
    hand_drops = [default, default]
    armor_drops = [default, default, default, default]
    if isinstance(drops, nbt.TAG_Compound):
        for index, name in enumerate(HAND_SLOTS):
            if name in drops:
                hand_drops[index] = as_float(drops[name])
        for index, name in enumerate(ARMOR_SLOTS):
            if name in drops:
                armor_drops[index] = as_float(drops[name])
    entity["HandDropChances"] = list_tag([nbt.TAG_Float(v) for v in hand_drops], nbt.TAG_Float)
    entity["ArmorDropChances"] = list_tag([nbt.TAG_Float(v) for v in armor_drops], nbt.TAG_Float)
    if "body" in equipment:
        entity["body_armor_item"] = clone_tag(equipment["body"])
        body_drop = as_float(drops["body"]) if isinstance(drops, nbt.TAG_Compound) and "body" in drops else default
        entity["body_armor_drop_chance"] = nbt.TAG_Float(body_drop)
    audit.setdefault("equipment", []).append({**entity_ref(entity), "slots": sorted(slots)})
    del entity["equipment"]
    if "drop_chances" in entity:
        del entity["drop_chances"]
    return True


def convert_leash(entity, audit):
    source = entity.get("leash")
    if source is None:
        return False
    target = None
    if isinstance(source, nbt.TAG_Int_Array) and len(source.value) == 3:
        target = nbt.TAG_Compound()
        target["X"] = nbt.TAG_Int(int(source.value[0]))
        target["Y"] = nbt.TAG_Int(int(source.value[1]))
        target["Z"] = nbt.TAG_Int(int(source.value[2]))
    elif isinstance(source, nbt.TAG_Compound) and set(source.keys()) == {"UUID"}:
        uuid = source.get("UUID")
        if isinstance(uuid, nbt.TAG_Int_Array) and len(uuid.value) == 4:
            target = clone_tag(source)
    if target is None:
        audit.setdefault("unsupported_leashes", []).append({
            **entity_ref(entity),
            "reason": "modern leash is neither a 3-int fence position nor a compound containing one UUID int array",
            "source": comparable_tag(source),
        })
        return False
    existing = entity.get("Leash")
    if existing is not None and comparable_tag(existing) != comparable_tag(target):
        audit.setdefault("unsupported_leashes", []).append({
            **entity_ref(entity),
            "reason": "modern leash conflicts with an existing legacy Leash value",
            "source": comparable_tag(source),
            "target": comparable_tag(existing),
        })
        return False
    entity["Leash"] = target
    del entity["leash"]
    audit.setdefault("leashes", []).append(entity_ref(entity))
    return True


def validate_waypoint_attribute(attribute):
    numeric_tags = (
        nbt.TAG_Byte,
        nbt.TAG_Short,
        nbt.TAG_Int,
        nbt.TAG_Long,
        nbt.TAG_Float,
        nbt.TAG_Double,
    )
    base_tag = attribute.get("base")
    if not isinstance(base_tag, numeric_tags):
        return None, [], "base is not a numeric NBT tag"
    base = as_float(base_tag)
    if not math.isfinite(base) or not 0.0 <= base <= 60_000_000.0:
        return base, [], "base is not finite or is outside the registered 0..60000000 range"
    raw_modifiers = attribute.get("modifiers")
    if raw_modifiers is None:
        return base, [], None
    if not isinstance(raw_modifiers, nbt.TAG_List):
        return base, [], "modifiers is not a list"
    modifiers = []
    identifiers = set()
    for index, modifier in enumerate(raw_modifiers):
        if not isinstance(modifier, nbt.TAG_Compound):
            return base, modifiers, f"modifier {index} is not a compound"
        modifier_id = modifier.get("id")
        amount_tag = modifier.get("amount")
        operation_tag = modifier.get("operation")
        if not isinstance(modifier_id, nbt.TAG_String):
            return base, modifiers, f"modifier {index} id is not a StringTag"
        identifier = string_value(modifier_id)
        if not RESOURCE_LOCATION_PATTERN.fullmatch(identifier):
            return base, modifiers, f"modifier {index} id is not a canonical resource location"
        if identifier in identifiers:
            return base, modifiers, f"modifier {index} duplicates id {identifier}"
        identifiers.add(identifier)
        if not isinstance(amount_tag, numeric_tags):
            return base, modifiers, f"modifier {index} amount is not numeric"
        amount = as_float(amount_tag)
        if not math.isfinite(amount):
            return base, modifiers, f"modifier {index} amount is not finite"
        if not isinstance(operation_tag, nbt.TAG_String):
            return base, modifiers, f"modifier {index} operation is not a StringTag"
        operation = string_value(operation_tag)
        if operation not in ATTRIBUTE_MODIFIER_OPERATIONS:
            return base, modifiers, f"modifier {index} operation is unsupported: {operation}"
        modifiers.append({"id": identifier, "amount": amount, "operation": operation})
    return base, modifiers, None


def validate_legacy_attribute(attribute):
    """Validate the common 1.21.11 attribute codec before changing its id."""
    numeric_tags = (
        nbt.TAG_Byte,
        nbt.TAG_Short,
        nbt.TAG_Int,
        nbt.TAG_Long,
        nbt.TAG_Float,
        nbt.TAG_Double,
    )
    base_tag = attribute.get("base")
    if not isinstance(base_tag, numeric_tags):
        return None, [], "base is not a numeric NBT tag"
    base = as_float(base_tag)
    if not math.isfinite(base):
        return base, [], "base is not finite"
    raw_modifiers = attribute.get("modifiers")
    if raw_modifiers is None:
        return base, [], None
    if not isinstance(raw_modifiers, nbt.TAG_List):
        return base, [], "modifiers is not a list"
    modifiers = []
    identifiers = set()
    for index, modifier in enumerate(raw_modifiers):
        if not isinstance(modifier, nbt.TAG_Compound):
            return base, modifiers, f"modifier {index} is not a compound"
        modifier_id = modifier.get("id")
        amount_tag = modifier.get("amount")
        operation_tag = modifier.get("operation")
        if not isinstance(modifier_id, nbt.TAG_String):
            return base, modifiers, f"modifier {index} id is not a StringTag"
        identifier = string_value(modifier_id)
        if not RESOURCE_LOCATION_PATTERN.fullmatch(identifier):
            return base, modifiers, f"modifier {index} id is not a canonical resource location"
        if identifier in identifiers:
            return base, modifiers, f"modifier {index} duplicates id {identifier}"
        identifiers.add(identifier)
        if not isinstance(amount_tag, numeric_tags):
            return base, modifiers, f"modifier {index} amount is not numeric"
        amount = as_float(amount_tag)
        if not math.isfinite(amount):
            return base, modifiers, f"modifier {index} amount is not finite"
        if not isinstance(operation_tag, nbt.TAG_String):
            return base, modifiers, f"modifier {index} operation is not a StringTag"
        operation = string_value(operation_tag)
        if operation not in ATTRIBUTE_MODIFIER_OPERATIONS:
            return base, modifiers, f"modifier {index} operation is unsupported: {operation}"
        modifiers.append({"id": identifier, "amount": amount, "operation": operation})
    return base, modifiers, None


def convert_legacy_attribute_container(entity, audit, reference=None):
    """Convert the pre-1.21 Attributes/Name/Base codec transactionally.

    A small number of old villagers in the source still use this schema.  The
    target DFU accepts it, but converting it explicitly keeps the offline
    result deterministic and lets malformed legacy data fail closed.
    """
    legacy = entity.get("Attributes")
    if legacy is None:
        return False
    reference = reference or entity_ref(entity)
    if "attributes" in entity:
        audit.setdefault("unsupported_attributes", []).append({
            **reference,
            "reason": "both legacy Attributes and canonical attributes are present",
        })
        return False
    if not isinstance(legacy, nbt.TAG_List):
        audit.setdefault("unsupported_attributes", []).append({
            **reference,
            "reason": "legacy Attributes is not a list",
        })
        return False

    numeric_tags = (
        nbt.TAG_Byte,
        nbt.TAG_Short,
        nbt.TAG_Int,
        nbt.TAG_Long,
        nbt.TAG_Float,
        nbt.TAG_Double,
    )
    converted = []
    errors = []
    for index, attribute in enumerate(legacy):
        if not isinstance(attribute, nbt.TAG_Compound):
            errors.append({"index": index, "reason": "legacy attribute is not a compound"})
            continue
        unknown = sorted(set(attribute.keys()) - {"Name", "Base", "Modifiers"})
        if unknown:
            errors.append({"index": index, "reason": "unknown legacy attribute fields", "fields": unknown})
            continue
        name_tag = attribute.get("Name")
        base_tag = attribute.get("Base")
        if not isinstance(name_tag, nbt.TAG_String):
            errors.append({"index": index, "reason": "legacy attribute Name is not a StringTag"})
            continue
        if not isinstance(base_tag, numeric_tags) or not math.isfinite(as_float(base_tag)):
            errors.append({"index": index, "reason": "legacy attribute Base is not finite numeric"})
            continue
        source_name = string_value(name_tag)
        target_name = ATTRIBUTE_ALIASES.get(source_name, source_name)
        if target_name not in SUPPORTED_ATTRIBUTES and target_name not in WAYPOINT_ATTRIBUTES:
            errors.append({"index": index, "id": source_name, "reason": "legacy attribute id is unsupported"})
            continue
        modifiers = []
        raw_modifiers = attribute.get("Modifiers")
        if raw_modifiers is not None:
            if not isinstance(raw_modifiers, nbt.TAG_List):
                errors.append({"index": index, "id": source_name, "reason": "legacy Modifiers is not a list"})
                continue
            seen = set()
            modifier_error = None
            for modifier_index, modifier in enumerate(raw_modifiers):
                if not isinstance(modifier, nbt.TAG_Compound):
                    modifier_error = f"legacy modifier {modifier_index} is not a compound"
                    break
                unknown_modifier = sorted(
                    set(modifier.keys()) - {"Name", "Amount", "Operation", "UUID", "UUIDMost", "UUIDLeast"}
                )
                if unknown_modifier:
                    modifier_error = f"legacy modifier has unknown fields: {', '.join(unknown_modifier)}"
                    break
                modifier_name = modifier.get("Name")
                amount_tag = modifier.get("Amount")
                operation_tag = modifier.get("Operation")
                if not isinstance(modifier_name, nbt.TAG_String):
                    modifier_error = f"legacy modifier {modifier_index} Name is not a StringTag"
                    break
                modifier_id = LEGACY_ATTRIBUTE_MODIFIER_NAMES.get(
                    string_value(modifier_name), string_value(modifier_name)
                )
                if not RESOURCE_LOCATION_PATTERN.fullmatch(modifier_id):
                    modifier_error = f"legacy modifier {modifier_index} name is not a canonical resource location"
                    break
                if not isinstance(amount_tag, numeric_tags) or not math.isfinite(as_float(amount_tag)):
                    modifier_error = f"legacy modifier {modifier_index} Amount is not finite numeric"
                    break
                if isinstance(operation_tag, numeric_tags):
                    operation_number = as_int(operation_tag)
                    operation = LEGACY_ATTRIBUTE_MODIFIER_OPERATIONS.get(operation_number)
                elif isinstance(operation_tag, nbt.TAG_String):
                    operation = string_value(operation_tag)
                else:
                    operation = None
                if operation not in ATTRIBUTE_MODIFIER_OPERATIONS:
                    modifier_error = f"legacy modifier {modifier_index} Operation is unsupported"
                    break
                amount = as_float(amount_tag)
                existing = next(
                    (entry for entry in modifiers if entry["id"] == modifier_id),
                    None,
                )
                if existing is not None:
                    # The 1.21.1 DFU folds duplicate legacy random-spawn
                    # modifiers into one canonical modifier by summing their
                    # amounts. Different operations cannot be combined safely.
                    if existing["operation"] != operation:
                        modifier_error = (
                            f"legacy modifier {modifier_index} duplicates id "
                            f"{modifier_id} with a different operation"
                        )
                        break
                    existing["amount"] += amount
                    audit.setdefault("legacy_attribute_modifier_merges", []).append({
                        **reference,
                        "attribute": source_name,
                        "id": modifier_id,
                        "amount_added": amount,
                    })
                    continue
                seen.add(modifier_id)
                modifiers.append({
                    "id": modifier_id,
                    "amount": amount,
                    "operation": operation,
                })
            if modifier_error is not None:
                errors.append({"index": index, "id": source_name, "reason": modifier_error})
                continue
        target_attribute = nbt.TAG_Compound()
        target_attribute["id"] = nbt.TAG_String(target_name)
        target_attribute["base"] = nbt.TAG_Double(as_float(base_tag))
        if modifiers:
            modifier_tags = []
            for modifier in modifiers:
                modifier_tag = nbt.TAG_Compound()
                modifier_tag["id"] = nbt.TAG_String(modifier["id"])
                modifier_tag["amount"] = nbt.TAG_Double(modifier["amount"])
                modifier_tag["operation"] = nbt.TAG_String(modifier["operation"])
                modifier_tags.append(modifier_tag)
            target_attribute["modifiers"] = list_tag(
                modifier_tags,
                nbt.TAG_Compound,
            )
        converted.append(target_attribute)

    if errors:
        audit.setdefault("unsupported_attributes", []).append({
            **reference,
            "reason": "legacy Attributes conversion blocked",
            "attributes": errors,
        })
        return False
    entity["attributes"] = list_tag(converted, nbt.TAG_Compound)
    del entity["Attributes"]
    audit.setdefault("legacy_attribute_containers", []).append({
        **reference,
        "count": len(converted),
    })
    return True


def convert_attributes(entity, audit, reference=None, identifier_override=None):
    attributes = entity.get("attributes")
    legacy_changed = False
    if attributes is None and "Attributes" in entity:
        legacy_changed = convert_legacy_attribute_container(entity, audit, reference)
        if "attributes" not in entity:
            return legacy_changed
        attributes = entity.get("attributes")
    elif attributes is not None and "Attributes" in entity:
        reference = reference or entity_ref(entity)
        audit.setdefault("unsupported_attributes", []).append({
            **reference,
            "reason": "both legacy Attributes and canonical attributes are present",
        })
        return False
    if attributes is None:
        return False
    reference = reference or entity_ref(entity)
    if not isinstance(attributes, nbt.TAG_List):
        audit.setdefault("unsupported_attributes", []).append({
            **reference,
            "attributes": [{"reason": "attributes is not a list", "value": comparable_tag(attributes)}],
        })
        return False
    changed = legacy_changed
    unknown = []
    kept = []
    identifier = identifier_override or string_value(entity.get("id", nbt.TAG_String("")))
    for index, attribute in enumerate(attributes):
        if not isinstance(attribute, nbt.TAG_Compound):
            unknown.append({"index": index, "reason": "attribute is not a compound", "value": comparable_tag(attribute)})
            kept.append(attribute)
            continue
        if not isinstance(attribute.get("id"), nbt.TAG_String):
            unknown.append({"index": index, "reason": "attribute id is not a StringTag", "value": comparable_tag(attribute)})
            kept.append(attribute)
            continue
        old = string_value(attribute["id"])
        new = ATTRIBUTE_ALIASES.get(old, old)
        if new in SUPPORTED_ATTRIBUTES:
            base, modifiers, reason = validate_legacy_attribute(attribute)
            if reason is not None:
                unknown.append({
                    "index": index,
                    "id": old,
                    "base": base,
                    "modifiers": comparable_tag(attribute.get("modifiers")),
                    "reason": reason,
                })
                kept.append(attribute)
                continue
        if new != old:
            attribute["id"] = nbt.TAG_String(new)
            audit.setdefault("attribute_aliases", []).append({
                **reference,
                "source": old,
                "target": new,
                "base": base,
                "modifiers": modifiers,
            })
            changed = True
        compatibility_declared = (
            new in WAYPOINT_ATTRIBUTES
            and WAYPOINT_FIRE_CAPABILITY in audit.get("runtime_capabilities", ())
        )
        if compatibility_declared:
            base, modifiers, reason = validate_waypoint_attribute(attribute)
            if reason is not None:
                unknown.append({
                    "id": old,
                    "base": base,
                    "modifiers": comparable_tag(attribute.get("modifiers")),
                    "reason": reason,
                })
                kept.append(attribute)
                continue
            audit.setdefault("retained_compatibility_attributes", []).append({
                **reference,
                "attribute": new,
                "base": base,
                "modifiers": modifiers,
                "implementation": WAYPOINT_FIRE_MOD_ID,
            })
        else:
            modifiers = []
            for modifier in attribute.get("modifiers", []):
                if not isinstance(modifier, nbt.TAG_Compound):
                    continue
                modifiers.append({
                    "id": string_value(modifier.get("id", nbt.TAG_String(""))),
                    "amount": as_float(modifier.get("amount", nbt.TAG_Double(0.0))),
                    "operation": string_value(modifier.get("operation", nbt.TAG_String(""))),
                })
        if new not in SUPPORTED_ATTRIBUTES and not compatibility_declared:
            base = as_float(attribute.get("base", nbt.TAG_Double(0.0)))
            expected = REMOVABLE_DEFAULT_ATTRIBUTES.get(old)
            if identifier == "minecraft:happy_ghast" and old in HAPPY_GHAST_COMPAT_ATTRIBUTES:
                expected = HAPPY_GHAST_COMPAT_ATTRIBUTES[old]
            neutral_waypoint_modifier = (
                old == "minecraft:waypoint_transmit_range"
                and math.isclose(base, 0.0, rel_tol=0.0, abs_tol=1e-9)
                and modifiers == [NEUTRAL_WAYPOINT_HIDE_MODIFIER]
            )
            if expected is not None and math.isclose(base, expected, rel_tol=0.0, abs_tol=1e-9) and (not modifiers or neutral_waypoint_modifier):
                if identifier == "minecraft:happy_ghast" and old in HAPPY_GHAST_COMPAT_ATTRIBUTES:
                    implementation = "happyghast-equivalence"
                elif old == "minecraft:waypoint_transmit_range":
                    implementation = "source range is zero; known hide modifier is mathematically neutral"
                else:
                    implementation = "1.21.1 built-in default"
                audit.setdefault("consumed_default_attributes", []).append({
                    **reference,
                    "attribute": old,
                    "base": base,
                    "modifiers": modifiers,
                    "implementation": implementation,
                })
                changed = True
                continue
            unknown.append({"id": old, "base": base, "modifiers": modifiers})
        kept.append(attribute)
    if len(kept) != len(attributes):
        attributes.tags = kept
    if unknown:
        audit.setdefault("unsupported_attributes", []).append({**reference, "attributes": unknown})
    return changed


def player_ref(path):
    return {"file": path.name, "uuid": path.stem, "id": "minecraft:player"}


def inventory_slot(item):
    if not isinstance(item, nbt.TAG_Compound) or "Slot" not in item:
        return None
    return as_int(item["Slot"]) & 0xFF


def encoded_slot(slot):
    return slot if slot < 128 else slot - 256


def item_component_json_value(value, field=None):
    """Convert a structured 1.21.11 text component to JSON-compatible data."""
    if isinstance(value, (nbt.TAG_Byte_Array, nbt.TAG_Int_Array, nbt.TAG_Long_Array)):
        raise ValueError(f"text component field {field!r} uses an unsupported NBT array")
    if isinstance(value, nbt.TAG_Compound):
        return {key: item_component_json_value(child, key) for key, child in value.items()}
    if isinstance(value, nbt.TAG_List):
        return [item_component_json_value(child, field) for child in value]
    if isinstance(value, nbt.TAG_String):
        return string_value(value)
    if isinstance(value, nbt.TAG_Byte):
        number = as_int(value)
        if field in TEXT_BOOLEAN_FIELDS:
            if number not in (0, 1):
                raise ValueError(f"text component boolean field {field!r} is {number}, expected 0 or 1")
            return bool(number)
        return number
    if isinstance(value, (nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
        return as_int(value)
    if isinstance(value, (nbt.TAG_Float, nbt.TAG_Double)):
        number = as_float(value)
        if not math.isfinite(number):
            raise ValueError(f"text component field {field!r} is not finite")
        return number
    raise ValueError(f"unsupported text component tag {type(value).__name__} at field {field!r}")


def canonical_item_component_text(value):
    """Encode an ItemStack text component for 1.21.1 FLAT_CODEC."""
    if isinstance(value, nbt.TAG_String):
        return canonical_component_text(value)
    if not isinstance(value, (nbt.TAG_Compound, nbt.TAG_List)):
        raise ValueError(f"text component is {type(value).__name__}, expected String, Compound, or List")
    parsed = item_component_json_value(value)
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def item_blocker(context, item_path, item_id, reason, component=None):
    record = {
        **context["reference"],
        "path": item_path,
        "item": item_id,
        "reason": reason,
    }
    if component is not None:
        record["component"] = component
    context["blockers"].append(record)


def _validate_computercraft_pocket_upgrade(value):
    """Validate the exact UpgradeData codec subset proven equal on both jars."""
    if not isinstance(value, nbt.TAG_Compound):
        return None, "ComputerCraft pocket upgrade payload is not a compound"
    unknown = sorted(set(value.keys()) - {"id", "components"})
    if unknown:
        return None, (
            "ComputerCraft pocket upgrade payload has unknown fields: "
            + ", ".join(unknown)
        )
    upgrade_id = value.get("id")
    if not isinstance(upgrade_id, nbt.TAG_String):
        return None, "ComputerCraft pocket upgrade id is not a string"
    upgrade_id = string_value(upgrade_id)
    if upgrade_id not in COMPUTERCRAFT_AUDITED_POCKET_UPGRADES:
        return None, (
            "ComputerCraft pocket upgrade has no audited 1.21.1 codec/registry "
            f"equivalent: {upgrade_id}"
        )
    patch = value.get("components")
    if patch is not None and (
        not isinstance(patch, nbt.TAG_Compound) or bool(patch)
    ):
        return None, (
            "ComputerCraft pocket upgrade components are non-empty or malformed; "
            "their cross-version DataComponentPatch semantics were not proven"
        )
    return upgrade_id, None


def convert_computercraft_pocket_upgrade(
    components, item_path, item_id, context
):
    """Reverse CC:Tweaked's official 4314 pocket-upgrade field rename.

    The 1.21.11 jar's RenamePocketComputerUpgradeFix renames
    ``computercraft:pocket_upgrade`` to ``back_pocket_upgrade``. The locked
    1.21.1 target registers only the former single-slot component, so a back
    upgrade can be renamed back exactly. The newer bottom slot has no target
    representation and therefore remains a hard blocker.
    """
    back = components.get(COMPUTERCRAFT_BACK_POCKET_UPGRADE)
    bottom = components.get(COMPUTERCRAFT_BOTTOM_POCKET_UPGRADE)
    target = components.get(COMPUTERCRAFT_TARGET_POCKET_UPGRADE)
    if back is None and bottom is None and target is None:
        return False
    if item_id not in COMPUTERCRAFT_POCKET_COMPUTERS:
        item_blocker(
            context,
            item_path,
            item_id,
            "ComputerCraft pocket upgrade component appears on a non-pocket-computer item",
            next(
                component
                for component, value in (
                    (COMPUTERCRAFT_BACK_POCKET_UPGRADE, back),
                    (COMPUTERCRAFT_BOTTOM_POCKET_UPGRADE, bottom),
                    (COMPUTERCRAFT_TARGET_POCKET_UPGRADE, target),
                )
                if value is not None
            ),
        )
        return False
    if bottom is not None:
        item_blocker(
            context,
            item_path,
            item_id,
            "ComputerCraft bottom pocket upgrade has no 1.21.1 single-slot equivalent",
            COMPUTERCRAFT_BOTTOM_POCKET_UPGRADE,
        )
        return False
    if target is not None:
        _, reason = _validate_computercraft_pocket_upgrade(target)
        if reason is not None:
            item_blocker(
                context,
                item_path,
                item_id,
                reason,
                COMPUTERCRAFT_TARGET_POCKET_UPGRADE,
            )
            return False
        if back is not None:
            item_blocker(
                context,
                item_path,
                item_id,
                "both source back_pocket_upgrade and target pocket_upgrade are present",
                COMPUTERCRAFT_BACK_POCKET_UPGRADE,
            )
        return False
    if back is None:
        return False
    upgrade_id, reason = _validate_computercraft_pocket_upgrade(back)
    if reason is not None:
        item_blocker(
            context,
            item_path,
            item_id,
            reason,
            COMPUTERCRAFT_BACK_POCKET_UPGRADE,
        )
        return False
    components[COMPUTERCRAFT_TARGET_POCKET_UPGRADE] = clone_tag(back)
    del components[COMPUTERCRAFT_BACK_POCKET_UPGRADE]
    context.setdefault("computercraft_pocket_upgrades", []).append({
        **context["reference"],
        "path": item_path,
        "item": item_id,
        "upgrade": upgrade_id,
        "source_component": COMPUTERCRAFT_BACK_POCKET_UPGRADE,
        "target_component": COMPUTERCRAFT_TARGET_POCKET_UPGRADE,
    })
    return True


def normalize_vanilla_item_component_schema(components, item_path, item_id, context):
    """Normalize the three vanilla component shapes observed between 1.21.11 and 1.21.1.

    The 1.21.11 codec stores enchantment levels directly and dyed colors as an
    integer.  The 1.21.1 codec wraps those values in ``levels`` and ``rgb``
    compounds respectively.  Unknown or malformed shapes remain fail-closed.
    """
    changed = False
    for component_id in ("minecraft:stored_enchantments", "minecraft:enchantments"):
        value = components.get(component_id)
        if value is None:
            continue
        if not isinstance(value, nbt.TAG_Compound):
            item_blocker(
                context,
                item_path,
                item_id,
                f"{component_id} is not a compound",
                component_id,
            )
            continue
        if "levels" in value:
            if set(value.keys()) != {"levels"} or not isinstance(value["levels"], nbt.TAG_Compound):
                item_blocker(
                    context,
                    item_path,
                    item_id,
                    f"{component_id}.levels has an unsupported shape",
                    component_id,
                )
            continue
        if any(
            not isinstance(level, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long))
            or as_int(level) < 0
            for level in value.values()
        ):
            item_blocker(
                context,
                item_path,
                item_id,
                f"{component_id} contains a non-integer or negative level",
                component_id,
            )
            continue
        wrapper = nbt.TAG_Compound()
        # TAG_Compound.__setitem__ assigns the child name in place. Clone the
        # direct map so wrapping it cannot rename the original component key.
        wrapper["levels"] = clone_tag(value)
        components[component_id] = wrapper
        context.setdefault("component_schema_aliases", []).append({
            **context["reference"],
            "path": item_path,
            "item": item_id,
            "component": component_id,
            "source_shape": "direct_levels",
            "target_shape": "levels_compound",
        })
        changed = True

    value = components.get("minecraft:dyed_color")
    if value is not None:
        numeric = (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)
        if isinstance(value, numeric):
            wrapper = nbt.TAG_Compound()
            wrapper["rgb"] = nbt.TAG_Int(as_int(value))
            components["minecraft:dyed_color"] = wrapper
            context.setdefault("component_schema_aliases", []).append({
                **context["reference"],
                "path": item_path,
                "item": item_id,
                "component": "minecraft:dyed_color",
                "source_shape": "rgb_int",
                "target_shape": "rgb_compound",
            })
            changed = True
        elif isinstance(value, nbt.TAG_Compound):
            if set(value.keys()) != {"rgb"} or not isinstance(value["rgb"], numeric):
                item_blocker(
                    context,
                    item_path,
                    item_id,
                    "dyed_color.rgb has an unsupported shape",
                    "minecraft:dyed_color",
                )
        else:
            item_blocker(
                context,
                item_path,
                item_id,
                "dyed_color is neither an integer nor an rgb compound",
                "minecraft:dyed_color",
            )
    return changed


def convert_tooltip_display(value, components, item_path, item_id, context):
    """Map the observed 1.21.11 selective banner tooltip hide to 1.21.1.

    NeoForge 1.21.1 has only hide_tooltip and hide_additional_tooltip; it has
    no selective tooltip-display component.  The source world only uses the
    exact banner-pattern case, so all other shapes stay fail-closed.
    """
    if not isinstance(value, nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "tooltip_display is not a compound", "minecraft:tooltip_display")
        return False
    unknown = set(value.keys()) - {"hidden_components", "hide_tooltip"}
    if unknown:
        item_blocker(
            context,
            item_path,
            item_id,
            f"tooltip_display has unknown fields: {', '.join(sorted(unknown))}",
            "minecraft:tooltip_display",
        )
        return False
    hide_tooltip = value.get("hide_tooltip")
    if hide_tooltip is not None:
        if not isinstance(hide_tooltip, nbt.TAG_Byte) or as_int(hide_tooltip) not in (0, 1):
            item_blocker(context, item_path, item_id, "tooltip_display.hide_tooltip is not a byte boolean", "minecraft:tooltip_display")
            return False
        hide_tooltip = bool(as_int(hide_tooltip))
    else:
        hide_tooltip = False
    hidden = value.get("hidden_components", nbt.TAG_List(type=nbt.TAG_String))
    if not isinstance(hidden, nbt.TAG_List) or any(not isinstance(entry, nbt.TAG_String) for entry in hidden):
        item_blocker(context, item_path, item_id, "tooltip_display.hidden_components is not a string list", "minecraft:tooltip_display")
        return False
    hidden_ids = [string_value(entry) for entry in hidden]
    if hide_tooltip:
        target_id = "minecraft:hide_tooltip"
    elif hidden_ids == ["minecraft:banner_patterns"]:
        target_id = "minecraft:hide_additional_tooltip"
    elif not hidden_ids:
        target_id = None
    else:
        item_blocker(
            context,
            item_path,
            item_id,
            f"tooltip_display selectively hides unsupported components: {', '.join(hidden_ids)}",
            "minecraft:tooltip_display",
        )
        return False
    changed = False
    if target_id is not None:
        existing = components.get(target_id)
        if existing is not None and not isinstance(existing, nbt.TAG_Compound):
            item_blocker(context, item_path, item_id, f"existing {target_id} is not a Unit compound", target_id)
            return False
        if existing is None:
            components[target_id] = nbt.TAG_Compound()
            changed = True
    del components["minecraft:tooltip_display"]
    context.setdefault("tooltip_displays", []).append({
        **context["reference"],
        "path": item_path,
        "item": item_id,
        "hidden_components": hidden_ids,
        "hide_tooltip": hide_tooltip,
        "target": target_id,
    })
    return True


def rewrite_legacy_hover_events(value, item_path, item_id, context):
    """Rewrite 1.21.11 structured Component hover_event nodes in place."""
    changed = 0
    if isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            changed += rewrite_legacy_hover_events(child, f"{item_path}[{index}]", item_id, context)
        return changed
    if not isinstance(value, nbt.TAG_Compound):
        return changed
    if "hover_event" in value:
        if "hoverEvent" in value:
            item_blocker(context, item_path, item_id, "both hover_event and hoverEvent are present")
        else:
            source = value["hover_event"]
            allowed = {"action", "id", "count"}
            if not isinstance(source, nbt.TAG_Compound):
                item_blocker(context, item_path, item_id, "hover_event is not a compound")
            elif set(source.keys()) - allowed:
                item_blocker(
                    context,
                    item_path,
                    item_id,
                    f"hover_event has unknown fields: {', '.join(sorted(set(source.keys()) - allowed))}",
                )
            elif not isinstance(source.get("action"), nbt.TAG_String) or string_value(source["action"]) != "show_item":
                item_blocker(context, item_path, item_id, "hover_event action is not the supported show_item form")
            elif not isinstance(source.get("id"), nbt.TAG_String) or ":" not in string_value(source["id"]):
                item_blocker(context, item_path, item_id, "hover_event show_item id is malformed")
            elif "count" in source and not isinstance(source["count"], (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
                item_blocker(context, item_path, item_id, "hover_event show_item count is not an integer")
            elif "count" in source and as_int(source["count"]) <= 0:
                item_blocker(context, item_path, item_id, "hover_event show_item count is not positive")
            else:
                target = nbt.TAG_Compound()
                target["action"] = nbt.TAG_String("show_item")
                contents = nbt.TAG_Compound()
                contents["id"] = clone_tag(source["id"])
                if "count" in source:
                    contents["count"] = clone_tag(source["count"])
                target["contents"] = contents
                value["hoverEvent"] = target
                del value["hover_event"]
                changed += 1
    for key in list(value.keys()):
        changed += rewrite_legacy_hover_events(value[key], f"{item_path}.{key}", item_id, context)
    return changed


def valid_path_segment(value):
    return bool(value) and value not in {".", ".."} and not any(char in value for char in ("/", "\\", ":"))


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_waypoint_fire_compat_jar(path, expected_sha256, target_game_dir=None):
    """Validate the runtime contract before accepting compatibility-only NBT."""
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"waypoint/fire compatibility JAR is missing: {path}")
    if path.suffix.lower() != ".jar":
        raise ValueError("waypoint/fire compatibility artifact must have an enabled .jar suffix")
    expected_sha256 = str(expected_sha256).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("waypoint/fire compatibility SHA-256 must be exactly 64 hexadecimal characters")
    actual_sha256 = file_sha256(path)
    if actual_sha256.lower() != expected_sha256:
        raise ValueError(
            "waypoint/fire compatibility JAR SHA-256 mismatch: "
            f"expected {expected_sha256}, found {actual_sha256}"
        )
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing_entries = sorted(WAYPOINT_FIRE_REQUIRED_ENTRIES - names)
            if missing_entries:
                raise ValueError(
                    "waypoint/fire compatibility JAR lacks required entries: "
                    + ", ".join(missing_entries)
                )
            for class_name in sorted(WAYPOINT_FIRE_REQUIRED_CLASSES):
                payload = archive.read(class_name)
                if len(payload) < 16 or payload[:4] != b"\xca\xfe\xba\xbe":
                    raise ValueError(
                        f"waypoint/fire compatibility class is empty or invalid: {class_name}"
                    )
            metadata = tomllib.loads(
                archive.read("META-INF/neoforge.mods.toml").decode("utf-8")
            )
            marker = json.loads(archive.read(WAYPOINT_FIRE_MARKER).decode("utf-8"))
            mixin_config = json.loads(
                archive.read("waypoint_fire_equivalence.mixins.json").decode("utf-8")
            )
    except (OSError, UnicodeError, zipfile.BadZipFile, KeyError, tomllib.TOMLDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid waypoint/fire compatibility JAR {path}: {exc}") from exc

    mods = metadata.get("mods")
    if not isinstance(mods, list):
        raise ValueError("waypoint/fire compatibility JAR has no [[mods]] metadata")
    mod = next(
        (entry for entry in mods if isinstance(entry, dict) and entry.get("modId") == WAYPOINT_FIRE_MOD_ID),
        None,
    )
    if mod is None:
        raise ValueError(
            f"waypoint/fire compatibility JAR does not declare modId={WAYPOINT_FIRE_MOD_ID}"
        )
    dependency_root = metadata.get("dependencies")
    dependencies = (
        dependency_root.get(WAYPOINT_FIRE_MOD_ID, [])
        if isinstance(dependency_root, dict)
        else []
    )
    dependency_by_id = {
        entry.get("modId"): entry
        for entry in dependencies
        if isinstance(entry, dict) and isinstance(entry.get("modId"), str)
    }
    minecraft_dependency = dependency_by_id.get("minecraft")
    neoforge_dependency = dependency_by_id.get("neoforge")
    if not isinstance(minecraft_dependency, dict) or any((
        minecraft_dependency.get("type") != "required",
        minecraft_dependency.get("side") != "BOTH",
        minecraft_dependency.get("versionRange") != "[1.21.1,1.21.2)",
    )):
        raise ValueError("waypoint/fire compatibility JAR lacks the exact required Minecraft 1.21.1 BOTH dependency")
    if not isinstance(neoforge_dependency, dict) or any((
        neoforge_dependency.get("type") != "required",
        neoforge_dependency.get("side") != "BOTH",
        neoforge_dependency.get("versionRange") != "[21.1,)",
    )):
        raise ValueError("waypoint/fire compatibility JAR lacks the required NeoForge 21.1 BOTH dependency")
    declared_mixins = metadata.get("mixins")
    if not isinstance(declared_mixins, list) or not any(
        isinstance(entry, dict)
        and entry.get("config") == "waypoint_fire_equivalence.mixins.json"
        for entry in declared_mixins
    ):
        raise ValueError("waypoint/fire compatibility JAR does not declare its required mixin config")
    if not isinstance(mixin_config, dict):
        raise ValueError("waypoint/fire compatibility mixin config must be a JSON object")
    if mixin_config.get("required") is not True or mixin_config.get("package") != "com.bmt.waypointfire.mixin":
        raise ValueError("waypoint/fire compatibility mixin config is not required or has the wrong package")
    mixins = mixin_config.get("mixins")
    if (
        not isinstance(mixins, list)
        or not all(isinstance(value, str) for value in mixins)
        or not WAYPOINT_FIRE_REQUIRED_MIXINS.issubset(set(mixins))
    ):
        raise ValueError("waypoint/fire compatibility mixin config lacks required runtime mixins")
    if not isinstance(marker, dict):
        raise ValueError("waypoint/fire compatibility marker must be a JSON object")
    if type(marker.get("schema")) is not int or marker.get("schema") != 1:
        raise ValueError("waypoint/fire compatibility marker schema must be 1")
    if marker.get("mod_id") != WAYPOINT_FIRE_MOD_ID:
        raise ValueError("waypoint/fire compatibility marker has the wrong mod_id")
    if marker.get("minecraft_version") != "1.21.1":
        raise ValueError("waypoint/fire compatibility marker is not for Minecraft 1.21.1")
    capabilities = marker.get("capabilities")
    if not isinstance(capabilities, list) or not all(isinstance(value, str) for value in capabilities):
        raise ValueError("waypoint/fire compatibility marker capabilities must be a string list")
    missing_capabilities = sorted(WAYPOINT_FIRE_REQUIRED_CAPABILITIES - set(capabilities))
    if missing_capabilities:
        raise ValueError(
            "waypoint/fire compatibility marker lacks capabilities: "
            + ", ".join(missing_capabilities)
        )
    deployed_path = None
    if target_game_dir is not None:
        deployed_path = Path(target_game_dir).resolve() / "mods" / path.name
        if not deployed_path.is_file():
            raise ValueError(
                "validated waypoint/fire compatibility JAR is not deployed in target mods: "
                f"{deployed_path}"
            )
        deployed_sha256 = file_sha256(deployed_path)
        if deployed_sha256.lower() != actual_sha256.lower():
            raise ValueError(
                "target mods waypoint/fire JAR does not match the validated artifact: "
                f"{deployed_path}"
            )
    return {
        "capability": WAYPOINT_FIRE_CAPABILITY,
        "path": str(path),
        "sha256": actual_sha256,
        "size": path.stat().st_size,
        "mod_id": WAYPOINT_FIRE_MOD_ID,
        "version": str(mod.get("version", "")),
        "target_deployment": str(deployed_path) if deployed_path is not None else None,
        "marker": marker,
    }


def verify_schematic_dependency(components, item_path, item_id, game_dir, context):
    if "create:schematic_file" not in components and "create:schematic_owner" not in components:
        return
    owner = components.get("create:schematic_owner")
    filename = components.get("create:schematic_file")
    if not isinstance(owner, nbt.TAG_String) or not isinstance(filename, nbt.TAG_String):
        item_blocker(
            context,
            item_path,
            item_id,
            "schematic owner/file pair is missing or not StringTag",
            "create:schematic_file",
        )
        return
    owner_text = string_value(owner)
    file_text = string_value(filename)
    if not valid_path_segment(owner_text) or not valid_path_segment(file_text):
        item_blocker(
            context,
            item_path,
            item_id,
            "schematic owner/file is not a safe single path segment",
            "create:schematic_file",
        )
        return
    source_candidate = game_dir / "schematics" / "uploaded" / owner_text / file_text
    target_game_dir = context.get("target_game_dir")
    target_candidate = None
    if target_game_dir is not None:
        target_candidate = target_game_dir / "schematics" / "uploaded" / owner_text / file_text

    base_record = {
        **context["reference"],
        "path": item_path,
        "item": item_id,
        "owner": owner_text,
        "file": file_text,
        "resolved": str(source_candidate),
        "source_resolved": str(source_candidate),
    }
    if not source_candidate.is_file():
        record = {
            **base_record,
            "source_exists": False,
            "reason": "external schematic file is already missing from the source game directory",
        }
        if target_candidate is not None:
            record["target_resolved"] = str(target_candidate)
            record["target_exists"] = target_candidate.is_file()
        context["inherited_missing_schematic_files"].append(record)
        if target_candidate is not None and target_candidate.is_file():
            item_blocker(
                context,
                item_path,
                item_id,
                f"source schematic is missing but target dependency exists: {target_candidate}",
                "create:schematic_file",
            )
        return

    source_size = source_candidate.stat().st_size
    source_hash = file_sha256(source_candidate)
    record = {
        **base_record,
        "source_exists": True,
        "source_size": source_size,
        "source_sha256": source_hash,
    }
    if target_candidate is not None:
        record["target_resolved"] = str(target_candidate)
        record["target_exists"] = target_candidate.is_file()
        if not target_candidate.is_file():
            item_blocker(
                context,
                item_path,
                item_id,
                f"source schematic exists but target dependency is missing: {target_candidate}",
                "create:schematic_file",
            )
        else:
            target_size = target_candidate.stat().st_size
            target_hash = file_sha256(target_candidate)
            record["target_size"] = target_size
            record["target_sha256"] = target_hash
            record["target_matches_source"] = target_size == source_size and target_hash == source_hash
            if not record["target_matches_source"]:
                item_blocker(
                    context,
                    item_path,
                    item_id,
                    f"target schematic does not match source dependency: {target_candidate}",
                    "create:schematic_file",
                )
    context["schematic_files"].append(record)


def recurse_item_list(value, item_path, item_id, context, wrapped):
    if not isinstance(value, nbt.TAG_List):
        item_blocker(context, item_path, item_id, "ItemStack carrier is not a list")
        return False
    changed = False
    occupied = set()
    for index, child in enumerate(value):
        child_path = f"{item_path}[{index}]"
        stack = child
        if wrapped:
            if not isinstance(child, nbt.TAG_Compound):
                item_blocker(context, child_path, item_id, "container entry is not a compound")
                continue
            unknown = set(child.keys()) - {"slot", "item"}
            if unknown:
                item_blocker(context, child_path, item_id, f"container entry has unknown fields: {', '.join(sorted(unknown))}")
                continue
            if not isinstance(child.get("slot"), (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
                item_blocker(context, child_path, item_id, "container slot is not an integer")
                continue
            slot = as_int(child["slot"])
            if not 0 <= slot <= 255:
                item_blocker(context, child_path, item_id, f"container slot {slot} is outside 0..255")
                continue
            if slot in occupied:
                item_blocker(context, child_path, item_id, f"container slot {slot} is duplicated")
                continue
            occupied.add(slot)
            stack = child.get("item")
            child_path += ".item"
        changed = convert_item_stack(stack, child_path, context) or changed
    return changed


def convert_clipboard_content(value, item_path, item_id, context):
    if not isinstance(value, nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "clipboard_content is not a compound", "create:clipboard_content")
        return False
    unknown = set(value.keys()) - {"type", "pages", "read_only", "previously_opened_page"}
    pages = value.get("pages")
    if unknown:
        item_blocker(context, item_path, item_id, f"clipboard_content has unknown fields: {', '.join(sorted(unknown))}", "create:clipboard_content")
    if not isinstance(value.get("type"), nbt.TAG_String):
        item_blocker(context, item_path, item_id, "clipboard_content.type is not a StringTag", "create:clipboard_content")
    if not isinstance(value.get("read_only"), nbt.TAG_Byte) or as_int(value["read_only"]) not in (0, 1):
        item_blocker(context, item_path, item_id, "clipboard_content.read_only is not a byte boolean", "create:clipboard_content")
    if not isinstance(value.get("previously_opened_page"), (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)):
        item_blocker(context, item_path, item_id, "clipboard_content.previously_opened_page is not an integer", "create:clipboard_content")
    if not isinstance(pages, nbt.TAG_List):
        item_blocker(context, item_path, item_id, "clipboard_content.pages is not a list", "create:clipboard_content")
        return False
    hover_count = 0
    changed = False
    for page_index, page in enumerate(pages):
        if not isinstance(page, nbt.TAG_List):
            item_blocker(context, f"{item_path}.pages[{page_index}]", item_id, "clipboard page is not a list", "create:clipboard_content")
            continue
        for entry_index, entry in enumerate(page):
            entry_path = f"{item_path}.pages[{page_index}][{entry_index}]"
            if not isinstance(entry, nbt.TAG_Compound):
                item_blocker(context, entry_path, item_id, "clipboard entry is not a compound", "create:clipboard_content")
                continue
            entry_unknown = set(entry.keys()) - {"checked", "icon", "item_amount", "text"}
            if entry_unknown:
                item_blocker(context, entry_path, item_id, f"clipboard entry has unknown fields: {', '.join(sorted(entry_unknown))}", "create:clipboard_content")
                continue
            if not isinstance(entry.get("checked"), nbt.TAG_Byte) or as_int(entry["checked"]) not in (0, 1):
                item_blocker(context, entry_path, item_id, "clipboard entry checked is not a byte boolean", "create:clipboard_content")
            if not isinstance(entry.get("item_amount"), (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)) or as_int(entry["item_amount"]) < 0:
                item_blocker(context, entry_path, item_id, "clipboard entry item_amount is not a non-negative integer", "create:clipboard_content")
            text = entry.get("text")
            if not isinstance(text, (nbt.TAG_String, nbt.TAG_Compound, nbt.TAG_List)):
                item_blocker(context, entry_path, item_id, "clipboard entry text has an unsupported structure", "create:clipboard_content")
            else:
                converted = rewrite_legacy_hover_events(text, f"{entry_path}.text", item_id, context)
                hover_count += converted
                changed = bool(converted) or changed
            if "icon" in entry:
                changed = convert_item_stack(entry["icon"], f"{entry_path}.icon", context, allow_empty=True) or changed
    if hover_count:
        context["clipboard_hovers"].append({
            **context["reference"],
            "path": item_path,
            "item": item_id,
            "converted": hover_count,
        })
    return changed


def _expected_float32(numerator, denominator):
    return struct.unpack(">f", struct.pack(">f", numerator / denominator))[0]


def _read_generated_assembly_lore(lore, recipe):
    """Return (step, total) only for Create Fly's exact generated lore shell."""
    if not isinstance(lore, nbt.TAG_List):
        raise ValueError("sequenced assembly minecraft:lore is not a list")
    try:
        values = [item_component_json_value(entry) for entry in lore]
    except ValueError as exc:
        raise ValueError(f"sequenced assembly lore is malformed: {exc}") from exc
    if len(values) < 4:
        raise ValueError("sequenced assembly lore has fewer than four generated lines")
    if values[0] != {"": ""}:
        raise ValueError("sequenced assembly lore does not start with Create's empty line")
    if values[1] != {
        "italic": False,
        "translate": "create.recipe.sequenced_assembly",
        "color": "gray",
    }:
        raise ValueError("sequenced assembly lore title differs from Create's generated title")
    progress = values[2]
    if not isinstance(progress, dict) or set(progress) != {
        "italic", "translate", "with", "color",
    }:
        raise ValueError("sequenced assembly lore progress line has an unknown shape")
    if (
        progress.get("italic") is not False
        or progress.get("translate") != "create.recipe.assembly.progress"
        or progress.get("color") != "dark_gray"
        or not isinstance(progress.get("with"), list)
        or len(progress["with"]) != 2
        or any(type(value) is not int for value in progress["with"])
    ):
        raise ValueError("sequenced assembly lore progress line is malformed")
    step, total = progress["with"]
    preview_count = min(3, total - step)
    if not 1 <= step < total or len(values) != 3 + preview_count:
        raise ValueError("sequenced assembly lore step/total or preview count is invalid")

    descriptions = recipe["descriptions"]
    expected = [
        descriptions[(step + offset) % len(descriptions)]
        for offset in range(preview_count)
    ]

    first = values[3]
    if (
        not isinstance(first, dict)
        or set(first) != {"italic", "translate", "with", "color"}
        or first.get("italic") is not False
        or first.get("translate") != "create.recipe.assembly.next"
        or first.get("color") != "aqua"
        or not isinstance(first.get("with"), list)
        or len(first["with"]) != 1
        or first["with"][0] != expected[0]
    ):
        raise ValueError("sequenced assembly lore next-step line is malformed")
    for index, line in enumerate(values[4:], 4):
        if (
            not isinstance(line, dict)
            or set(line) != {"italic", "extra", "text", "color"}
            or line.get("italic") is not False
            or line.get("text") != "-> "
            or line.get("color") != "dark_aqua"
            or not isinstance(line.get("extra"), list)
            or len(line["extra"]) != 1
            or line["extra"][0] != expected[index - 3]
        ):
            raise ValueError(
                f"sequenced assembly lore preview line {index} is malformed"
            )
    return step, total


def _validate_target_sequenced_assembly(value, item_id, recipe):
    if not isinstance(value, nbt.TAG_Compound) or set(value.keys()) != {
        "id", "step", "progress",
    }:
        raise ValueError("create:sequenced_assembly is not the target three-field compound")
    recipe_id = value.get("id")
    step_tag = value.get("step")
    progress_tag = value.get("progress")
    if not isinstance(recipe_id, nbt.TAG_String) or string_value(recipe_id) != recipe["id"]:
        raise ValueError(
            f"create:sequenced_assembly recipe id does not match {item_id}"
        )
    if not isinstance(step_tag, nbt.TAG_Int):
        raise ValueError("create:sequenced_assembly.step is not an IntTag")
    step = as_int(step_tag)
    if not 1 <= step < recipe["total"]:
        raise ValueError("create:sequenced_assembly.step is outside the recipe")
    if not isinstance(progress_tag, nbt.TAG_Float):
        raise ValueError("create:sequenced_assembly.progress is not a FloatTag")
    progress = as_float(progress_tag)
    expected = _expected_float32(step, recipe["total"])
    if not math.isfinite(progress) or progress != expected:
        raise ValueError("create:sequenced_assembly.progress conflicts with step/recipe")
    return step, progress


def convert_create_sequenced_assembly(
    components, item_path, item_id, context
):
    """Replace Create Fly's float/lore state with Create 1.21.1's recipe state."""
    legacy = components.get("create:sequenced_assembly_progress")
    target = components.get("create:sequenced_assembly")
    if legacy is None and target is None:
        return False
    recipe = CREATE_SEQUENCED_ASSEMBLY_RECIPES.get(item_id)
    if recipe is None:
        item_blocker(
            context,
            item_path,
            item_id,
            "sequenced assembly component appears on an unaudited transitional item",
            "create:sequenced_assembly_progress" if legacy is not None else "create:sequenced_assembly",
        )
        return False
    if target is not None:
        try:
            target_step, target_progress = _validate_target_sequenced_assembly(
                target, item_id, recipe
            )
        except ValueError as exc:
            item_blocker(context, item_path, item_id, str(exc), "create:sequenced_assembly")
            return False
        if legacy is None:
            return False
    else:
        target_step = target_progress = None

    if not isinstance(legacy, nbt.TAG_Float):
        item_blocker(
            context,
            item_path,
            item_id,
            "create:sequenced_assembly_progress is not a FloatTag",
            "create:sequenced_assembly_progress",
        )
        return False
    progress = as_float(legacy)
    lore = components.get("minecraft:lore")
    try:
        step, total = _read_generated_assembly_lore(lore, recipe)
    except ValueError as exc:
        item_blocker(context, item_path, item_id, str(exc), "minecraft:lore")
        return False
    expected = _expected_float32(step, total)
    if total != recipe["total"] or not math.isfinite(progress) or progress != expected:
        item_blocker(
            context,
            item_path,
            item_id,
            "sequenced assembly item, lore step/total, and float progress disagree",
            "create:sequenced_assembly_progress",
        )
        return False
    if target is not None and (target_step != step or target_progress != progress):
        item_blocker(
            context,
            item_path,
            item_id,
            "legacy and target sequenced assembly components conflict",
            "create:sequenced_assembly",
        )
        return False
    if target is None:
        converted = nbt.TAG_Compound()
        converted["id"] = nbt.TAG_String(recipe["id"])
        converted["step"] = nbt.TAG_Int(step)
        converted["progress"] = clone_tag(legacy)
        components["create:sequenced_assembly"] = converted
    del components["create:sequenced_assembly_progress"]
    del components["minecraft:lore"]
    context.setdefault("sequenced_assemblies", []).append(
        {
            **context["reference"],
            "path": item_path,
            "item": item_id,
            "recipe": recipe["id"],
            "step": step,
            "total": total,
            "progress": progress,
            "removed_generated_lore_lines": len(lore),
        }
    )
    return True


def convert_item_lore(components, item_path, item_id, context):
    lore = components.get("minecraft:lore")
    if lore is None:
        return False
    if not isinstance(lore, nbt.TAG_List):
        item_blocker(context, item_path, item_id, "minecraft:lore is not a list", "minecraft:lore")
        return False
    converted = []
    changed = False
    for index, value in enumerate(lore):
        try:
            text = canonical_item_component_text(value)
        except (TypeError, ValueError) as exc:
            item_blocker(
                context,
                item_path,
                item_id,
                f"minecraft:lore[{index}]: {exc}",
                "minecraft:lore",
            )
            return False
        converted.append(nbt.TAG_String(text))
        if not isinstance(value, nbt.TAG_String) or string_value(value) != text:
            changed = True
            context["text_components"].append(
                {
                    **context["reference"],
                    "path": item_path,
                    "item": item_id,
                    "component": f"minecraft:lore[{index}]",
                    "before": comparable_tag(value),
                    "after": text,
                }
            )
    if changed:
        components["minecraft:lore"] = list_tag(converted, nbt.TAG_String)
    return changed


def validate_create_filter_components(components, item_path, item_id, context):
    for component_id in (
        "create:filter_items_respect_nbt",
        "create:filter_items_blacklist",
    ):
        value = components.get(component_id)
        if value is not None and (
            not isinstance(value, nbt.TAG_Byte) or as_int(value) not in (0, 1)
        ):
            item_blocker(
                context,
                item_path,
                item_id,
                f"{component_id} is not a byte boolean",
                component_id,
            )
    for component_id in (
        "!minecraft:attribute_modifiers",
        "!minecraft:enchantments",
    ):
        value = components.get(component_id)
        if value is not None and (
            not isinstance(value, nbt.TAG_Compound) or len(value) != 0
        ):
            item_blocker(
                context,
                item_path,
                item_id,
                f"{component_id} is not an empty removal marker",
                component_id,
            )


TARGET_1211_POT_DECORATIONS = {
    "minecraft:brick",
    "minecraft:angler_pottery_sherd",
    "minecraft:archer_pottery_sherd",
    "minecraft:arms_up_pottery_sherd",
    "minecraft:blade_pottery_sherd",
    "minecraft:brewer_pottery_sherd",
    "minecraft:burn_pottery_sherd",
    "minecraft:danger_pottery_sherd",
    "minecraft:explorer_pottery_sherd",
    "minecraft:flow_pottery_sherd",
    "minecraft:friend_pottery_sherd",
    "minecraft:guster_pottery_sherd",
    "minecraft:heart_pottery_sherd",
    "minecraft:heartbreak_pottery_sherd",
    "minecraft:howl_pottery_sherd",
    "minecraft:miner_pottery_sherd",
    "minecraft:mourner_pottery_sherd",
    "minecraft:plenty_pottery_sherd",
    "minecraft:prize_pottery_sherd",
    "minecraft:scrape_pottery_sherd",
    "minecraft:sheaf_pottery_sherd",
    "minecraft:shelter_pottery_sherd",
    "minecraft:skull_pottery_sherd",
    "minecraft:snort_pottery_sherd",
}


def _byte_boolean(value):
    return isinstance(value, nbt.TAG_Byte) and as_int(value) in (0, 1)


def _block_pos(value):
    return isinstance(value, nbt.TAG_Int_Array) and len(value.value) == 3


def _rewrite_empty_literal_keys(value, item_path, item_id, context):
    """Map 1.21.11's empty literal-content key to 1.21.1's ``text`` key."""
    changed = 0
    if isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            changed += _rewrite_empty_literal_keys(
                child, f"{item_path}[{index}]", item_id, context
            )
        return changed
    if not isinstance(value, nbt.TAG_Compound):
        return changed
    if "" in value:
        if "text" in value:
            item_blocker(
                context,
                item_path,
                item_id,
                "text component contains both the source empty literal key and target text",
                "minecraft:written_book_content",
            )
        elif not isinstance(value[""], nbt.TAG_String):
            item_blocker(
                context,
                item_path,
                item_id,
                "text component empty literal key is not a string",
                "minecraft:written_book_content",
            )
        else:
            value["text"] = clone_tag(value[""])
            del value[""]
            changed += 1
    for key in list(value.keys()):
        changed += _rewrite_empty_literal_keys(
            value[key], f"{item_path}.{key}", item_id, context
        )
    return changed


def _convert_written_book_page_text(value, path, item_id, context):
    before = comparable_tag(value)
    _rewrite_empty_literal_keys(value, path, item_id, context)
    rewrite_legacy_hover_events(value, path, item_id, context)
    try:
        encoded = canonical_item_component_text(value)
    except (TypeError, ValueError) as exc:
        item_blocker(
            context,
            path,
            item_id,
            f"written book page text: {exc}",
            "minecraft:written_book_content",
        )
        return None, False
    changed = not isinstance(value, nbt.TAG_String) or string_value(value) != encoded
    if changed:
        context["text_components"].append(
            {
                **context["reference"],
                "path": path,
                "item": item_id,
                "component": "minecraft:written_book_content",
                "before": before,
                "after": encoded,
            }
        )
    return nbt.TAG_String(encoded), changed


def convert_written_book_content(components, item_path, item_id, context):
    value = components.get("minecraft:written_book_content")
    if value is None:
        return False
    component_id = "minecraft:written_book_content"
    if item_id != "minecraft:written_book":
        item_blocker(
            context,
            item_path,
            item_id,
            "written_book_content appears on a non-written-book item",
            component_id,
        )
        return False
    if not isinstance(value, nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "written_book_content is not a compound", component_id)
        return False
    unknown = sorted(set(value.keys()) - {"title", "author", "generation", "pages", "resolved"})
    if unknown:
        item_blocker(
            context,
            item_path,
            item_id,
            "written_book_content has unknown fields: " + ", ".join(unknown),
            component_id,
        )
    title = value.get("title")
    if isinstance(title, nbt.TAG_String):
        titles = [title]
    elif isinstance(title, nbt.TAG_Compound) and set(title.keys()) <= {"raw", "filtered"} and "raw" in title:
        titles = [title[key] for key in ("raw", "filtered") if key in title]
    else:
        titles = []
        item_blocker(context, item_path, item_id, "written_book_content.title is not Filterable<String>", component_id)
    if any(not isinstance(part, nbt.TAG_String) or len(string_value(part)) > 32 for part in titles):
        item_blocker(context, item_path, item_id, "written_book_content.title exceeds the target string codec", component_id)
    if not isinstance(value.get("author"), nbt.TAG_String):
        item_blocker(context, item_path, item_id, "written_book_content.author is not a string", component_id)
    generation = value.get("generation")
    if generation is not None and (
        not isinstance(generation, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long))
        or not 0 <= as_int(generation) <= 3
    ):
        item_blocker(context, item_path, item_id, "written_book_content.generation is outside 0..3", component_id)
    resolved = value.get("resolved")
    if resolved is not None and not _byte_boolean(resolved):
        item_blocker(context, item_path, item_id, "written_book_content.resolved is not a byte boolean", component_id)
    pages = value.get("pages")
    if pages is None:
        return False
    if not isinstance(pages, nbt.TAG_List) or len(pages) > 100:
        item_blocker(context, item_path, item_id, "written_book_content.pages is not a list of at most 100 pages", component_id)
        return False
    changed = False
    for index, page in enumerate(pages):
        page_path = f"{item_path}.components.{component_id}.pages[{index}]"
        if not isinstance(page, nbt.TAG_Compound) or set(page.keys()) - {"raw", "filtered"} or "raw" not in page:
            item_blocker(context, page_path, item_id, "written book page is not Filterable<Component>", component_id)
            continue
        for key in ("raw", "filtered"):
            if key not in page:
                continue
            converted, text_changed = _convert_written_book_page_text(
                page[key], f"{page_path}.{key}", item_id, context
            )
            if converted is not None:
                page[key] = converted
                changed = text_changed or changed
    return changed


def validate_audited_passthrough_components(components, item_path, item_id, context):
    """Validate component codecs proven present in the locked 1.21.1 runtime."""
    component_id = "minecraft:max_stack_size"
    value = components.get(component_id)
    if value is not None and (not isinstance(value, nbt.TAG_Int) or not 1 <= as_int(value) <= 99):
        item_blocker(context, item_path, item_id, "max_stack_size is not an IntTag in 1..99", component_id)

    component_id = "minecraft:map_color"
    value = components.get(component_id)
    if value is not None and not isinstance(value, nbt.TAG_Int):
        item_blocker(context, item_path, item_id, "map_color is not an IntTag", component_id)

    component_id = "minecraft:pot_decorations"
    value = components.get(component_id)
    if value is not None:
        if not isinstance(value, nbt.TAG_List) or len(value) > 4:
            item_blocker(context, item_path, item_id, "pot_decorations is not a list of at most four items", component_id)
        elif any(
            not isinstance(decoration, nbt.TAG_String)
            or string_value(decoration) not in TARGET_1211_POT_DECORATIONS
            for decoration in value
        ):
            item_blocker(context, item_path, item_id, "pot_decorations contains an item absent from the audited 1.21.1 registry", component_id)

    component_id = "create:banktank_air"
    value = components.get(component_id)
    if value is not None and not isinstance(value, nbt.TAG_Int):
        item_blocker(context, item_path, item_id, "create:banktank_air is not an IntTag", component_id)

    component_id = "create:train_schedule"
    value = components.get(component_id)
    if value is not None and not isinstance(value, nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "create:train_schedule is not a CompoundTag", component_id)

    component_id = "create:click_to_link_data"
    value = components.get(component_id)
    if value is not None and (
        not isinstance(value, nbt.TAG_Compound)
        or set(value.keys()) != {"selected_pos", "selected_dim"}
        or not _block_pos(value.get("selected_pos"))
        or not isinstance(value.get("selected_dim"), nbt.TAG_String)
        or not RESOURCE_LOCATION_PATTERN.fullmatch(string_value(value["selected_dim"]))
    ):
        item_blocker(context, item_path, item_id, "create:click_to_link_data does not match its target record codec", component_id)

    component_id = "computercraft:computer_id"
    value = components.get(component_id)
    if value is not None and (not isinstance(value, nbt.TAG_Int) or as_int(value) < 0):
        item_blocker(context, item_path, item_id, "computercraft:computer_id is not a non-negative IntTag", component_id)

    component_id = "computercraft:on"
    value = components.get(component_id)
    if value is not None and not _byte_boolean(value):
        item_blocker(context, item_path, item_id, "computercraft:on is not a byte boolean", component_id)

    component_id = "computercraft:computer"
    value = components.get(component_id)
    if value is not None and (
        not isinstance(value, nbt.TAG_Compound)
        or set(value.keys()) != {"session", "instance"}
        or not isinstance(value.get("session"), nbt.TAG_Int)
        or not isinstance(value.get("instance"), nbt.TAG_Int_Array)
        or len(value["instance"].value) != 4
    ):
        item_blocker(context, item_path, item_id, "computercraft:computer does not match ServerComputerReference.CODEC", component_id)


def convert_toms_storage_components(components, item_path, item_id, context):
    changed = False
    component_id = "toms_storage:configurator"
    value = components.get(component_id)
    if value is not None:
        fields = {"bound", "is_bound", "selecting", "show_inv_box", "mass_select", "box_start", "selection", "last_action"}
        valid = isinstance(value, nbt.TAG_Compound) and set(value.keys()) == fields
        if valid:
            valid = _block_pos(value["bound"]) and _block_pos(value["box_start"])
            valid = valid and all(_byte_boolean(value[key]) for key in ("is_bound", "selecting", "show_inv_box", "mass_select"))
            valid = valid and isinstance(value["last_action"], nbt.TAG_Long)
            valid = valid and isinstance(value["selection"], nbt.TAG_List) and all(_block_pos(pos) for pos in value["selection"])
        if not valid:
            item_blocker(context, item_path, item_id, "toms_storage:configurator does not match the target eight-field record codec", component_id)

    component_id = "toms_storage:tag_filter"
    value = components.get(component_id)
    if value is not None:
        valid = (
            isinstance(value, nbt.TAG_Compound)
            and set(value.keys()) == {"tags", "allow_list"}
            and _byte_boolean(value.get("allow_list"))
            and isinstance(value.get("tags"), nbt.TAG_List)
            and all(
                isinstance(tag, nbt.TAG_String)
                and RESOURCE_LOCATION_PATTERN.fullmatch(string_value(tag))
                for tag in value["tags"]
            )
        )
        if not valid:
            item_blocker(context, item_path, item_id, "toms_storage:tag_filter does not match the target record codec", component_id)

    component_id = "toms_storage:simple_item_filter"
    value = components.get(component_id)
    if value is not None:
        valid = (
            isinstance(value, nbt.TAG_Compound)
            and set(value.keys()) == {"stacks", "match_component", "allow_list"}
            and _byte_boolean(value.get("match_component"))
            and _byte_boolean(value.get("allow_list"))
            and isinstance(value.get("stacks"), nbt.TAG_List)
        )
        if not valid:
            item_blocker(context, item_path, item_id, "toms_storage:simple_item_filter does not match the target record codec", component_id)
        else:
            for index, stack in enumerate(value["stacks"]):
                changed = convert_item_stack(
                    stack,
                    f"{item_path}.components.{component_id}.stacks[{index}]",
                    context,
                    allow_empty=True,
                ) or changed
    return changed


def convert_cookery_recipe_record(components, item_path, item_id, context):
    component_id = "kaleidoscope_cookery:recipe_record"
    value = components.get(component_id)
    if value is None:
        return False
    if item_id != "kaleidoscope_cookery:recipe_item" or not isinstance(value, nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "Cookery recipe_record has an invalid carrier or payload", component_id)
        return False
    unknown = set(value.keys()) - {"input", "output", "type", "flex_recipe"}
    if unknown or not {"input", "output", "type"} <= set(value.keys()):
        item_blocker(context, item_path, item_id, "Cookery recipe_record fields do not match the target codec", component_id)
        return False
    if not isinstance(value["input"], nbt.TAG_List):
        item_blocker(context, item_path, item_id, "Cookery recipe_record.input is not a list", component_id)
        return False
    if not isinstance(value["output"], nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "Cookery recipe_record.output is not an ItemStack", component_id)
        return False
    if not isinstance(value["type"], nbt.TAG_String) or not RESOURCE_LOCATION_PATTERN.fullmatch(string_value(value["type"])):
        item_blocker(context, item_path, item_id, "Cookery recipe_record.type is not a resource location", component_id)
        return False
    changed = False
    flex = value.get("flex_recipe")
    if flex is None:
        value["flex_recipe"] = nbt.TAG_Byte(0)
        context["component_schema_aliases"].append(
            {
                **context["reference"],
                "path": item_path,
                "item": item_id,
                "component": component_id,
                "source_shape": "three_field_record",
                "target_shape": "four_field_record_flex_recipe_false",
            }
        )
        changed = True
    elif not _byte_boolean(flex):
        item_blocker(context, item_path, item_id, "Cookery recipe_record.flex_recipe is not a byte boolean", component_id)
        return False
    for index, stack in enumerate(value["input"]):
        changed = convert_item_stack(
            stack,
            f"{item_path}.components.{component_id}.input[{index}]",
            context,
            allow_empty=True,
        ) or changed
    changed = convert_item_stack(
        value["output"],
        f"{item_path}.components.{component_id}.output",
        context,
    ) or changed
    return changed


def convert_component_map(
    components,
    item_path,
    item_id,
    context,
    *,
    recurse_items=True,
    verify_dependencies=True,
):
    """Convert one data-component map after its carrier has been identified."""
    unknown = sorted(set(components.keys()) - KNOWN_PLAYER_ITEM_COMPONENTS)
    for component_id in unknown:
        item_blocker(context, item_path, item_id, "component type was not covered by the source/target codec audit", component_id)

    changed = normalize_vanilla_item_component_schema(
        components, item_path, item_id, context
    )
    tooltip_display = components.get("minecraft:tooltip_display")
    if tooltip_display is not None:
        changed = convert_tooltip_display(tooltip_display, components, item_path, item_id, context) or changed
    changed = convert_computercraft_pocket_upgrade(
        components, item_path, item_id, context
    ) or changed
    validate_create_filter_components(components, item_path, item_id, context)
    validate_audited_passthrough_components(
        components, item_path, item_id, context
    )

    # Per-mod component conversions are applied here before text canonicalizing
    # and recursive ItemStack traversal.
    changed = convert_written_book_content(
        components, item_path, item_id, context
    ) or changed
    changed = convert_toms_storage_components(
        components, item_path, item_id, context
    ) or changed
    changed = convert_cookery_recipe_record(
        components, item_path, item_id, context
    ) or changed
    changed = convert_create_sequenced_assembly(
        components, item_path, item_id, context
    ) or changed
    changed = convert_item_lore(
        components, item_path, item_id, context
    ) or changed
    for component_id in ("minecraft:custom_name", "minecraft:item_name"):
        if component_id not in components:
            continue
        before = comparable_tag(components[component_id])
        try:
            after = canonical_item_component_text(components[component_id])
        except (TypeError, ValueError) as exc:
            item_blocker(context, item_path, item_id, str(exc), component_id)
            continue
        if not isinstance(components[component_id], nbt.TAG_String) or string_value(components[component_id]) != after:
            components[component_id] = nbt.TAG_String(after)
            context["text_components"].append({
                **context["reference"],
                "path": item_path,
                "item": item_id,
                "component": component_id,
                "before": before,
                "after": after,
            })
            changed = True

    variant_tag = components.get("minecraft:axolotl/variant")
    if variant_tag is not None:
        if item_id != "minecraft:axolotl_bucket":
            item_blocker(context, item_path, item_id, "axolotl variant appears on a non-axolotl bucket", "minecraft:axolotl/variant")
        elif not isinstance(variant_tag, nbt.TAG_String) or string_value(variant_tag) not in AXOLOTL_VARIANTS:
            item_blocker(context, item_path, item_id, "unknown or malformed axolotl variant", "minecraft:axolotl/variant")
        else:
            target_variant = AXOLOTL_VARIANTS[string_value(variant_tag)]
            bucket_data = components.get("minecraft:bucket_entity_data")
            if bucket_data is None:
                bucket_data = nbt.TAG_Compound()
                components["minecraft:bucket_entity_data"] = bucket_data
            if not isinstance(bucket_data, nbt.TAG_Compound):
                item_blocker(context, item_path, item_id, "bucket_entity_data is not a compound", "minecraft:bucket_entity_data")
            elif "Variant" in bucket_data and (
                not isinstance(bucket_data["Variant"], (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long))
                or as_int(bucket_data["Variant"]) != target_variant
            ):
                item_blocker(context, item_path, item_id, "bucket_entity_data.Variant conflicts with axolotl/variant", "minecraft:axolotl/variant")
            else:
                bucket_data["Variant"] = nbt.TAG_Int(target_variant)
                del components["minecraft:axolotl/variant"]
                context["axolotl_variants"].append({
                    **context["reference"],
                    "path": item_path,
                    "item": item_id,
                    "source": string_value(variant_tag),
                    "target": target_variant,
                })
                changed = True

    potion = components.get("minecraft:potion_contents")
    if potion is not None:
        if not isinstance(potion, nbt.TAG_Compound):
            item_blocker(context, item_path, item_id, "potion_contents is not a compound", "minecraft:potion_contents")
        elif "custom_name" in potion:
            item_blocker(context, item_path, item_id, "potion_contents.custom_name has no proven 1.21.1 equivalent", "minecraft:potion_contents")

    if verify_dependencies:
        verify_schematic_dependency(
            components, item_path, item_id, context["game_dir"], context
        )

    if recurse_items:
        if "minecraft:container" in components:
            changed = recurse_item_list(components["minecraft:container"], f"{item_path}.components.minecraft:container", item_id, context, True) or changed
        for component_id in ("minecraft:bundle_contents", "minecraft:charged_projectiles"):
            if component_id in components:
                changed = recurse_item_list(components[component_id], f"{item_path}.components.{component_id}", item_id, context, False) or changed
        if "create:linked_controller_items" in components:
            changed = recurse_item_list(components["create:linked_controller_items"], f"{item_path}.components.create:linked_controller_items", item_id, context, True) or changed
        if "create:filter_items" in components:
            changed = recurse_item_list(
                components["create:filter_items"],
                f"{item_path}.components.create:filter_items",
                item_id,
                context,
                True,
            ) or changed
        if "create:clipboard_content" in components:
            changed = convert_clipboard_content(
                components["create:clipboard_content"],
                f"{item_path}.components.create:clipboard_content",
                item_id,
                context,
            ) or changed
    return changed


def convert_item_stack(stack, item_path, context, allow_empty=False):
    if not isinstance(stack, nbt.TAG_Compound):
        item_blocker(context, item_path, "", "ItemStack is not a compound")
        return False
    identity = id(stack)
    if identity in context["visited"]:
        return False
    context["visited"].add(identity)
    if not stack:
        if allow_empty:
            return False
        item_blocker(context, item_path, "", "ItemStack is an empty compound")
        return False
    identifier = stack.get("id")
    item_id = string_value(identifier) if isinstance(identifier, nbt.TAG_String) else ""
    if not item_id or ":" not in item_id:
        item_blocker(context, item_path, item_id, "ItemStack id is missing or malformed")
        return False
    if "count" in stack and "Count" in stack:
        item_blocker(context, item_path, item_id, "ItemStack has both count and Count")
        return False
    count = stack.get("count", stack.get("Count"))
    if not isinstance(count, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)) or as_int(count) <= 0:
        item_blocker(context, item_path, item_id, "ItemStack count is missing, non-integer, or non-positive")
        return False
    slot = stack.get("Slot")
    if slot is not None and not isinstance(
        slot, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)
    ):
        item_blocker(context, item_path, item_id, "ItemStack carrier Slot is not an integer")
        return False
    context["scanned"] += 1
    components = stack.get("components")
    if components is None:
        return False
    if not isinstance(components, nbt.TAG_Compound):
        item_blocker(context, item_path, item_id, "ItemStack components is not a compound")
        return False
    changed = convert_component_map(
        components, item_path, item_id, context
    )
    if changed:
        context["changed_stacks"].add(item_path)
    return changed


def convert_player_items(player, path, audit, game_dir):
    """Validate and transactionally convert all player-owned ItemStacks."""
    context = {
        "reference": player_ref(path),
        "game_dir": Path(game_dir),
        "target_game_dir": Path(audit["target_game_dir"]) if audit.get("target_game_dir") else None,
        "blockers": [],
        "text_components": [],
        "clipboard_hovers": [],
        "axolotl_variants": [],
        "schematic_files": [],
        "inherited_missing_schematic_files": [],
        "tooltip_displays": [],
        "component_schema_aliases": [],
        "computercraft_pocket_upgrades": [],
        "sequenced_assemblies": [],
        "changed_stacks": set(),
        "visited": set(),
        "scanned": 0,
    }
    planned = {}
    changed = False
    for root_name in ("Inventory", "EnderItems"):
        source = player.get(root_name)
        if source is None:
            continue
        if not isinstance(source, nbt.TAG_List):
            item_blocker(context, root_name, "", f"player {root_name} is not a list")
            continue
        target = clone_tag(source)
        for index, stack in enumerate(target):
            changed = convert_item_stack(stack, f"{root_name}[{index}]", context) or changed
        planned[root_name] = target
    if "equipment" in player:
        source = player["equipment"]
        if not isinstance(source, nbt.TAG_Compound):
            item_blocker(context, "equipment", "", "player equipment is not a compound")
        else:
            target = clone_tag(source)
            for slot, stack in target.items():
                changed = convert_item_stack(stack, f"equipment.{slot}", context, allow_empty=True) or changed
            planned["equipment"] = target

    audit.setdefault("counts", Counter())["player_item_stacks_scanned"] += context["scanned"]
    audit.setdefault("item_text_components", []).extend(context["text_components"])
    audit.setdefault("clipboard_hovers", []).extend(context["clipboard_hovers"])
    audit.setdefault("axolotl_variants", []).extend(context["axolotl_variants"])
    audit.setdefault("schematic_files", []).extend(context["schematic_files"])
    audit.setdefault("inherited_missing_schematic_files", []).extend(context["inherited_missing_schematic_files"])
    audit.setdefault("item_tooltip_displays", []).extend(context["tooltip_displays"])
    audit.setdefault("item_component_schema_aliases", []).extend(context["component_schema_aliases"])
    audit.setdefault("computercraft_pocket_upgrade_conversions", []).extend(
        context["computercraft_pocket_upgrades"]
    )
    audit.setdefault("sequenced_assembly_conversions", []).extend(
        context["sequenced_assemblies"]
    )
    if context["blockers"]:
        audit.setdefault("unsupported_player_items", []).extend(context["blockers"])
        return False, False
    for root_name, target in planned.items():
        player[root_name] = target
    if changed:
        records = [
            {**context["reference"], "path": item_path}
            for item_path in sorted(context["changed_stacks"])
        ]
        audit.setdefault("player_item_stacks", []).extend(records)
        audit.setdefault("counts", Counter())["player_item_stacks"] += len(records)
        audit["counts"]["item_text_components"] += len(context["text_components"])
        audit["counts"]["clipboard_hovers"] += sum(record["converted"] for record in context["clipboard_hovers"])
        audit["counts"]["axolotl_variants"] += len(context["axolotl_variants"])
        audit["counts"]["item_tooltip_displays"] += len(context["tooltip_displays"])
        audit["counts"]["computercraft_pocket_upgrade_conversions"] += len(
            context["computercraft_pocket_upgrades"]
        )
        audit["counts"]["sequenced_assembly_conversions"] += len(
            context["sequenced_assemblies"]
        )
    return changed, True


def walk_entity_item_stacks(value, item_path, context):
    """Find ItemStacks in arbitrary entity data without mistaking block data for items."""
    changed = False
    if isinstance(value, nbt.TAG_Compound):
        identifier = value.get("id")
        count = value.get("count", value.get("Count"))
        if isinstance(identifier, nbt.TAG_String) and isinstance(
            count, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)
        ):
            changed = convert_item_stack(value, item_path, context) or changed
        for key in list(value.keys()):
            changed = walk_entity_item_stacks(value[key], f"{item_path}.{key}", context) or changed
    elif isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            changed = walk_entity_item_stacks(child, f"{item_path}[{index}]", context) or changed
    return changed


def convert_entity_items(entity, audit):
    """Validate and transactionally convert every ItemStack owned by one entity."""
    working = clone_tag(entity)
    source_game_dir = (
        Path(audit["source_game_dir"])
        if audit.get("source_game_dir")
        else Path(audit.get("world", ".")).resolve().parent
    )
    context = {
        "reference": entity_ref(entity),
        "game_dir": source_game_dir,
        "target_game_dir": Path(audit["target_game_dir"]) if audit.get("target_game_dir") else None,
        "blockers": [],
        "text_components": [],
        "clipboard_hovers": [],
        "axolotl_variants": [],
        "schematic_files": [],
        "inherited_missing_schematic_files": [],
        "tooltip_displays": [],
        "component_schema_aliases": [],
        "computercraft_pocket_upgrades": [],
        "sequenced_assemblies": [],
        "changed_stacks": set(),
        "visited": set(),
        "scanned": 0,
    }
    changed = False
    for key in list(working.keys()):
        if key == "Passengers":
            continue
        changed = walk_entity_item_stacks(working[key], key, context) or changed

    audit.setdefault("counts", Counter())["entity_item_stacks_scanned"] += context["scanned"]
    audit.setdefault("item_text_components", []).extend(context["text_components"])
    audit.setdefault("clipboard_hovers", []).extend(context["clipboard_hovers"])
    audit.setdefault("axolotl_variants", []).extend(context["axolotl_variants"])
    audit.setdefault("schematic_files", []).extend(context["schematic_files"])
    audit.setdefault("inherited_missing_schematic_files", []).extend(context["inherited_missing_schematic_files"])
    audit.setdefault("item_tooltip_displays", []).extend(context["tooltip_displays"])
    audit.setdefault("item_component_schema_aliases", []).extend(context["component_schema_aliases"])
    audit.setdefault("computercraft_pocket_upgrade_conversions", []).extend(
        context["computercraft_pocket_upgrades"]
    )
    audit.setdefault("sequenced_assembly_conversions", []).extend(
        context["sequenced_assemblies"]
    )
    if context["blockers"]:
        audit.setdefault("unsupported_entity_items", []).extend(context["blockers"])
        return False, False
    if changed:
        for key in list(entity.keys()):
            del entity[key]
        for key, child in working.items():
            entity[key] = child
        records = [
            {**context["reference"], "path": item_path}
            for item_path in sorted(context["changed_stacks"])
        ]
        audit.setdefault("entity_item_stacks", []).extend(records)
        audit["counts"]["entity_item_stacks"] += len(records)
        audit["counts"]["item_text_components"] += len(context["text_components"])
        audit["counts"]["clipboard_hovers"] += sum(record["converted"] for record in context["clipboard_hovers"])
        audit["counts"]["axolotl_variants"] += len(context["axolotl_variants"])
        audit["counts"]["item_tooltip_displays"] += len(context["tooltip_displays"])
        audit["counts"]["computercraft_pocket_upgrade_conversions"] += len(
            context["computercraft_pocket_upgrades"]
        )
        audit["counts"]["sequenced_assembly_conversions"] += len(
            context["sequenced_assemblies"]
        )
    return changed, True


def _block_entity_item_reference(block):
    return {
        "block_entity": string_value(block.get("id", nbt.TAG_String(""))),
        **block_position_ref(block),
    }


def _new_block_item_context(block, audit):
    source_game_dir = (
        Path(audit["source_game_dir"])
        if audit.get("source_game_dir")
        else Path(audit.get("world", ".")).resolve().parent
    )
    return {
        "reference": _block_entity_item_reference(block),
        "game_dir": source_game_dir,
        "target_game_dir": Path(audit["target_game_dir"])
        if audit.get("target_game_dir")
        else None,
        "blockers": [],
        "text_components": [],
        "clipboard_hovers": [],
        "axolotl_variants": [],
        "schematic_files": [],
        "inherited_missing_schematic_files": [],
        "tooltip_displays": [],
        "component_schema_aliases": [],
        "computercraft_pocket_upgrades": [],
        "sequenced_assemblies": [],
        "changed_stacks": set(),
        "visited": set(),
        "scanned": 0,
    }


def _strict_component_item_stack(value):
    """Return true only for the persisted ItemStack root shape we can prove.

    Requiring ``components`` is deliberate: compounds with arbitrary ``id``
    and ``count`` fields are common in mod state, while every stack relevant to
    component migration necessarily has this field. Unknown root fields are
    not mutated as ItemStacks by this generic block-entity walker.
    """
    if not isinstance(value, nbt.TAG_Compound) or "components" not in value:
        return False
    if set(value.keys()) - ITEM_STACK_CARRIER_KEYS:
        return False
    if not isinstance(value.get("id"), nbt.TAG_String):
        return False
    count = value.get("count", value.get("Count"))
    return isinstance(
        count, (nbt.TAG_Byte, nbt.TAG_Short, nbt.TAG_Int, nbt.TAG_Long)
    )


def walk_block_entity_item_stacks(value, item_path, context):
    """Convert component-bearing ItemStacks in an arbitrary block-entity tree."""
    changed = False
    if isinstance(value, nbt.TAG_Compound):
        if _strict_component_item_stack(value):
            changed = convert_item_stack(value, item_path, context) or changed
        for key in list(value.keys()):
            changed = walk_block_entity_item_stacks(
                value[key], f"{item_path}.{key}", context
            ) or changed
    elif isinstance(value, nbt.TAG_List):
        for index, child in enumerate(value):
            changed = walk_block_entity_item_stacks(
                child, f"{item_path}[{index}]", context
            ) or changed
    return changed


def convert_block_entity_components_and_items(block, audit):
    """Transactionally convert direct BE components and nested ItemStacks.

    A block entity's own ``components`` map is decoded by BlockEntity rather
    than ItemStack and is therefore audited separately. Both carrier classes
    are planned against one clone and committed together only when neither has
    a blocker.
    """
    working = clone_tag(block)
    identifier = string_value(working.get("id", nbt.TAG_String("")))
    component_context = _new_block_item_context(block, audit)
    item_context = _new_block_item_context(block, audit)

    component_changed = False
    direct_components = working.get("components")
    if direct_components is not None:
        if not isinstance(direct_components, nbt.TAG_Compound):
            item_blocker(
                component_context,
                "components",
                identifier,
                "block-entity components is not a compound",
            )
        else:
            component_changed = convert_component_map(
                direct_components,
                "components",
                identifier,
                component_context,
                recurse_items=False,
                verify_dependencies=False,
            )

    item_changed = False
    for key in list(working.keys()):
        item_changed = walk_block_entity_item_stacks(
            working[key], key, item_context
        ) or item_changed

    audit.setdefault("counts", Counter())["block_entity_item_stacks_scanned"] += (
        item_context["scanned"]
    )
    audit.setdefault("item_text_components", []).extend(
        item_context["text_components"]
    )
    audit.setdefault("clipboard_hovers", []).extend(
        item_context["clipboard_hovers"]
    )
    audit.setdefault("axolotl_variants", []).extend(
        item_context["axolotl_variants"]
    )
    audit.setdefault("schematic_files", []).extend(
        item_context["schematic_files"]
    )
    audit.setdefault("inherited_missing_schematic_files", []).extend(
        item_context["inherited_missing_schematic_files"]
    )
    audit.setdefault("item_tooltip_displays", []).extend(
        item_context["tooltip_displays"]
    )
    audit.setdefault("item_component_schema_aliases", []).extend(
        item_context["component_schema_aliases"]
    )
    audit.setdefault("computercraft_pocket_upgrade_conversions", []).extend(
        item_context["computercraft_pocket_upgrades"]
    )
    audit.setdefault("sequenced_assembly_conversions", []).extend(
        item_context["sequenced_assemblies"]
    )

    audit.setdefault("block_entity_text_components", []).extend(
        component_context["text_components"]
    )
    audit.setdefault("block_entity_tooltip_displays", []).extend(
        component_context["tooltip_displays"]
    )
    audit.setdefault("block_entity_component_schema_aliases", []).extend(
        component_context["component_schema_aliases"]
    )
    audit.setdefault("block_entity_computercraft_pocket_upgrades", []).extend(
        component_context["computercraft_pocket_upgrades"]
    )
    audit.setdefault("sequenced_assembly_conversions", []).extend(
        component_context["sequenced_assemblies"]
    )

    if component_context["blockers"]:
        audit.setdefault("unsupported_block_entity_components", []).extend(
            component_context["blockers"]
        )
    if item_context["blockers"]:
        audit.setdefault("unsupported_block_entity_items", []).extend(
            item_context["blockers"]
        )
    if component_context["blockers"] or item_context["blockers"]:
        return False, False

    changed = component_changed or item_changed
    if not changed:
        return False, True
    for key in list(block.keys()):
        del block[key]
    for key, child in working.items():
        block[key] = child

    if component_changed:
        audit.setdefault("block_entity_component_maps", []).append(
            _block_entity_item_reference(block)
        )
        audit["counts"]["block_entity_component_maps"] += 1
        audit["counts"]["block_entity_text_components"] += len(
            component_context["text_components"]
        )
        audit["counts"]["block_entity_tooltip_displays"] += len(
            component_context["tooltip_displays"]
        )
        audit["counts"]["block_entity_computercraft_pocket_upgrades"] += len(
            component_context["computercraft_pocket_upgrades"]
        )
        audit["counts"]["sequenced_assembly_conversions"] += len(
            component_context["sequenced_assemblies"]
        )
    if item_changed:
        records = [
            {**item_context["reference"], "path": item_path}
            for item_path in sorted(item_context["changed_stacks"])
        ]
        audit.setdefault("block_entity_item_stacks", []).extend(records)
        audit["counts"]["block_entity_item_stacks"] += len(records)
        audit["counts"]["item_text_components"] += len(
            item_context["text_components"]
        )
        audit["counts"]["clipboard_hovers"] += sum(
            record["converted"] for record in item_context["clipboard_hovers"]
        )
        audit["counts"]["axolotl_variants"] += len(
            item_context["axolotl_variants"]
        )
        audit["counts"]["item_tooltip_displays"] += len(
            item_context["tooltip_displays"]
        )
        audit["counts"]["computercraft_pocket_upgrade_conversions"] += len(
            item_context["computercraft_pocket_upgrades"]
        )
        audit["counts"]["sequenced_assembly_conversions"] += len(
            item_context["sequenced_assemblies"]
        )
    return True, True


def convert_create_contraption(entity, audit):
    """Transactionally normalize nested Create contraptions in entity MCA data."""
    if "Contraption" not in entity:
        return False, True
    working = clone_tag(entity)
    blockers = []
    # Loaded lazily because the SavedData converter reuses this module's NBT
    # helpers. At entity-conversion time this module is already initialized.
    from convert_create_saveddata import convert_contraption_entity

    convert_contraption_entity(working, "Entity", blockers, None)
    if blockers:
        audit.setdefault("unsupported_contraptions", []).append(
            {
                **entity_ref(entity),
                "reason": "nested Create Contraption schema is unsupported",
                "blockers": blockers,
            }
        )
        return False, False
    changed = comparable_tag(entity) != comparable_tag(working)
    if not changed:
        return False, True
    for key in list(entity.keys()):
        del entity[key]
    for key, child in working.items():
        entity[key] = child
    contraption = entity["Contraption"]
    audit.setdefault("contraption_entities", []).append(
        {
            **entity_ref(entity),
            "type": string_value(contraption.get("Type", nbt.TAG_String(""))),
            "interactors": len(contraption.get("Interactors", ())),
            "seats": len(contraption.get("Seats", ())),
            "superglue": len(contraption.get("Superglue", ())),
        }
    )
    return True, True


def convert_player_equipment(player, path, audit):
    equipment = player.get("equipment")
    if not isinstance(equipment, nbt.TAG_Compound):
        return False
    reference = player_ref(path)
    unknown = sorted(set(equipment.keys()) - PLAYER_EQUIPMENT_NAMES)
    inventory = player.get("Inventory")
    blockers = []
    if unknown:
        blockers.append({**reference, "slots": unknown, "reason": "unknown player equipment slot"})
    if inventory is None:
        inventory = nbt.TAG_List(type=nbt.TAG_Compound)
    elif not isinstance(inventory, nbt.TAG_List):
        blockers.append({**reference, "reason": "Inventory is not a list"})
    if blockers:
        audit.setdefault("unsupported_player_equipment", []).extend(blockers)
        return False

    selected = as_int(player.get("SelectedItemSlot", nbt.TAG_Int(0)))
    if "mainhand" in equipment and not 0 <= selected <= 8:
        audit.setdefault("unsupported_player_equipment", []).append({
            **reference,
            "slot": "mainhand",
            "selected_item_slot": selected,
            "reason": "SelectedItemSlot is outside the 0..8 hotbar range",
        })
        return False

    existing_by_slot = {}
    duplicate_slots = set()
    for existing in inventory:
        slot = inventory_slot(existing)
        if slot is None:
            continue
        if slot in existing_by_slot:
            duplicate_slots.add(slot)
        else:
            existing_by_slot[slot] = existing

    planned = []
    for source_slot, source_item in equipment.items():
        if not isinstance(source_item, nbt.TAG_Compound):
            blockers.append({**reference, "slot": source_slot, "reason": "equipment item is not a compound"})
            continue
        if item_is_empty(source_item):
            if len(source_item):
                blockers.append({**reference, "slot": source_slot, "reason": "non-empty item compound has no valid id/count"})
            continue
        target_slot = selected if source_slot == "mainhand" else PLAYER_EQUIPMENT_SLOTS[source_slot]
        if target_slot in duplicate_slots:
            blockers.append({
                **reference,
                "slot": source_slot,
                "target_slot": target_slot,
                "reason": "Inventory already contains duplicate target slots",
            })
            continue
        existing = existing_by_slot.get(target_slot)
        already_present = existing is not None and comparable_item(existing) == comparable_item(source_item)
        if existing is not None and not already_present:
            blockers.append({
                **reference,
                "slot": source_slot,
                "target_slot": target_slot,
                "source_item": string_value(source_item.get("id", nbt.TAG_String(""))),
                "existing_item": string_value(existing.get("id", nbt.TAG_String(""))),
                "reason": "target Inventory slot contains a different item",
            })
            continue
        planned.append((source_slot, target_slot, source_item, already_present))
    if blockers:
        audit.setdefault("unsupported_player_equipment", []).extend(blockers)
        return False

    converted_inventory = clone_tag(inventory)
    for source_slot, target_slot, source_item, already_present in planned:
        if not already_present:
            converted = clone_tag(source_item)
            converted["Slot"] = nbt.TAG_Byte(encoded_slot(target_slot))
            converted_inventory.append(converted)
        audit.setdefault("player_equipment", []).append({
            **reference,
            "source_slot": source_slot,
            "target_slot": target_slot,
            "item": string_value(source_item.get("id", nbt.TAG_String(""))),
            "already_present": already_present,
        })
    player["Inventory"] = converted_inventory
    del player["equipment"]
    return True


def convert_player_respawn(player, path, audit):
    respawn = player.get("respawn")
    if not isinstance(respawn, nbt.TAG_Compound):
        return False
    reference = player_ref(path)
    allowed = {"pos", "yaw", "pitch", "dimension", "forced"}
    unknown = sorted(set(respawn.keys()) - allowed)
    pos = read_int_vector(respawn.get("pos"))
    dimension = string_value(respawn.get("dimension", nbt.TAG_String("")))
    yaw = as_float(respawn.get("yaw", nbt.TAG_Float(0.0)))
    pitch = as_float(respawn.get("pitch", nbt.TAG_Float(0.0)))
    forced = boolean_value(respawn.get("forced", nbt.TAG_Byte(0)))
    reason = None
    if unknown:
        reason = f"unknown respawn fields: {', '.join(unknown)}"
    elif pos is None or len(pos) != 3:
        reason = "respawn.pos is not a 3-element integer vector"
    elif not dimension:
        reason = "respawn.dimension is empty"
    elif not math.isfinite(yaw) or not math.isfinite(pitch):
        reason = "respawn rotation is not finite"
    elif PLAYER_RESPAWN_PITCH_KEY in player:
        existing_pitch = player[PLAYER_RESPAWN_PITCH_KEY]
        if not isinstance(existing_pitch, nbt.TAG_Float):
            reason = f"existing {PLAYER_RESPAWN_PITCH_KEY} is not a float"
        elif not math.isclose(as_float(existing_pitch), pitch, rel_tol=0.0, abs_tol=1e-7):
            reason = f"existing {PLAYER_RESPAWN_PITCH_KEY} conflicts with respawn.pitch"
    if reason:
        audit.setdefault("unsupported_player_respawns", []).append({
            **reference,
            "pos": pos,
            "dimension": dimension,
            "yaw": yaw,
            "pitch": pitch,
            "forced": forced,
            "reason": reason,
        })
        return False

    before = {
        key: tag_value(player[key])
        for key in (
            "SpawnX", "SpawnY", "SpawnZ", "SpawnAngle", "SpawnDimension", "SpawnForced",
            PLAYER_RESPAWN_PITCH_KEY,
        )
        if key in player
    }
    player["SpawnX"] = nbt.TAG_Int(pos[0])
    player["SpawnY"] = nbt.TAG_Int(pos[1])
    player["SpawnZ"] = nbt.TAG_Int(pos[2])
    player["SpawnAngle"] = nbt.TAG_Float(yaw)
    player["SpawnDimension"] = nbt.TAG_String(dimension)
    player["SpawnForced"] = nbt.TAG_Byte(1 if forced else 0)
    player[PLAYER_RESPAWN_PITCH_KEY] = nbt.TAG_Float(pitch)
    del player["respawn"]
    audit.setdefault("player_respawns", []).append({
        **reference,
        "before": before,
        "source": {"pos": pos, "dimension": dimension, "yaw": yaw, "pitch": pitch, "forced": forced},
    })
    return True


def convert_player(player, path, audit, game_dir=None):
    game_dir = Path(game_dir) if game_dir is not None else Path(audit.get("world", ".")).resolve().parent
    working = clone_tag(player)
    blocker_keys = (
        "unsupported_player_items",
        "unsupported_player_equipment",
        "unsupported_player_respawns",
        "unsupported_attributes",
    )
    blockers_before = {key: len(audit.get(key, ())) for key in blocker_keys}
    changed, items_safe = convert_player_items(working, path, audit, game_dir)
    if "fall_distance" in working and "FallDistance" not in working:
        working["FallDistance"] = clone_tag(working["fall_distance"])
        del working["fall_distance"]
        changed = True
    changed = convert_player_equipment(working, path, audit) or changed
    changed = convert_player_respawn(working, path, audit) or changed
    changed = convert_attributes(
        working,
        audit,
        reference=player_ref(path),
        identifier_override="minecraft:player",
    ) or changed
    blocked = not items_safe or any(len(audit.get(key, ())) != blockers_before[key] for key in blocker_keys)
    if blocked:
        return False
    if changed:
        for key in list(player.keys()):
            del player[key]
        for key, value in working.items():
            player[key] = value
    return changed


def process_players(world: Path, dry_run: bool, audit: dict):
    root = world / "playerdata"
    if not root.exists():
        return
    for path in sorted(root.glob("*.dat")):
        relative = str(path.relative_to(world)).replace("\\", "/")
        try:
            player = nbt.NBTFile(filename=str(path))
            source_game_dir = (
                Path(audit["source_game_dir"])
                if audit.get("source_game_dir")
                else world.parent
            )
            changed = convert_player(player, path, audit, source_game_dir)
        except Exception as exc:
            if not dry_run:
                raise
            audit.setdefault("malformed_players", []).append({
                "path": relative,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        if not changed:
            continue
        record = {"path": relative, "writes": 0 if dry_run else 1}
        audit.setdefault("players", []).append(record)
        audit.setdefault("counts", Counter())["players"] += 1
        if dry_run:
            continue
        temp = path.with_suffix(path.suffix + ".migration.tmp")
        player.write_file(filename=str(temp))
        os.replace(temp, path)


def convert_entity(entity, game_time, audit):
    identifier = string_value(entity.get("id", nbt.TAG_String(""))) if "id" in entity else ""
    if identifier in UNSUPPORTED_ENTITY_IDS:
        audit.setdefault("unsupported_entities", []).append({**entity_ref(entity), "reason": "entity type is not registered by the 1.21.1 target stack"})
        return False
    contraption_changed, contraption_safe = convert_create_contraption(entity, audit)
    if not contraption_safe:
        return False
    items_changed, items_safe = convert_entity_items(entity, audit)
    changed = contraption_changed or items_changed
    boat = split_boat_type(identifier)
    if boat is not None:
        target_id, boat_type = boat
        entity["id"] = nbt.TAG_String(target_id)
        entity["Type"] = nbt.TAG_String(boat_type)
        audit.setdefault("boats", []).append({**entity_ref(entity), "source_id": identifier, "target_id": target_id, "type": boat_type})
        identifier = target_id
        changed = True
    if identifier == "create:super_glue" and "Box" in entity:
        box = entity["Box"]
        if isinstance(box, nbt.TAG_List) and len(box) == 6:
            entity["From"] = list_tag([clone_tag(value) for value in box[:3]], nbt.TAG_Double)
            entity["To"] = list_tag([clone_tag(value) for value in box[3:]], nbt.TAG_Double)
            del entity["Box"]
            audit.setdefault("super_glue", []).append(entity_ref(entity))
            changed = True
    if "fall_distance" in entity and "FallDistance" not in entity:
        entity["FallDistance"] = clone_tag(entity["fall_distance"])
        del entity["fall_distance"]
        changed = True
    changed = convert_custom_name(entity, audit) or changed
    changed = convert_block_attachment(entity, audit) or changed
    changed = convert_leash(entity, audit) or changed
    if "equipment" in entity and items_safe:
        changed = convert_item_map(entity, audit) or changed
    changed = convert_attributes(entity, audit) or changed
    if "anger_end_time" in entity and "AngerTime" not in entity:
        original_end = as_int(entity["anger_end_time"])
        unclamped = max(0, original_end - game_time)
        remaining = min(2_147_483_647, unclamped)
        entity["AngerTime"] = nbt.TAG_Int(remaining)
        del entity["anger_end_time"]
        audit.setdefault("anger", []).append({**entity_ref(entity), "end": original_end, "remaining": remaining})
        if remaining != unclamped:
            audit.setdefault("anger_clamped", []).append({**entity_ref(entity), "end": original_end, "unclamped": unclamped, "remaining": remaining})
        changed = True
    if "angry_at" in entity and "AngryAt" not in entity:
        entity["AngryAt"] = clone_tag(entity["angry_at"])
        del entity["angry_at"]
        audit.setdefault("angry_at", []).append(entity_ref(entity))
        changed = True
    passengers = entity.get("Passengers")
    if isinstance(passengers, nbt.TAG_List):
        for passenger in passengers:
            if isinstance(passenger, nbt.TAG_Compound):
                changed = convert_entity(passenger, game_time, audit) or changed
    return changed


def decode(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        import gzip
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def read_slots(path: Path):
    data = path.read_bytes()
    if not data:
        return
    if len(data) < 8192:
        raise ValueError(f"non-empty region is shorter than its 8192-byte header ({len(data)} bytes)")
    locations = data[:4096]
    for slot in range(1024):
        entry = locations[slot * 4:(slot + 1) * 4]
        offset = int.from_bytes(entry[:3], "big")
        sectors = entry[3]
        if not offset:
            continue
        if not sectors:
            raise ValueError(f"slot {slot} has an offset but zero allocated sectors")
        start = offset * 4096
        allocation_end = start + sectors * 4096
        if offset < 2 or start + 5 > len(data):
            raise ValueError(f"slot {slot} points outside the region file")
        length = int.from_bytes(data[start:start + 4], "big")
        if length < 1:
            raise ValueError(f"slot {slot} has an invalid payload length {length}")
        if start + 4 + length > len(data) or start + 4 + length > allocation_end:
            raise ValueError(f"slot {slot} payload exceeds its allocated sectors")
        kind = data[start + 4]
        yield slot, offset, sectors, kind, data[start + 5:start + 4 + length]


def serialize_chunk(chunk):
    out = io.BytesIO()
    chunk.write_file(buffer=out)
    return out.getvalue()


def apply_region(path: Path, kind: str, game_time: int, dry_run: bool, audit: dict):
    original = path.read_bytes()
    changes = {}
    for slot, offset, sectors, compression, payload in read_slots(path):
        raw = decode(payload, compression)
        chunk = nbt.NBTFile(buffer=io.BytesIO(raw))
        changed = False
        values = []
        if kind == "entities":
            values = chunk.get("Entities", [])
            for entity in values:
                if isinstance(entity, nbt.TAG_Compound):
                    changed = convert_entity(entity, game_time, audit) or changed
        else:
            for key in ("block_entities", "BlockEntities", "blockEntities", "TileEntities"):
                if key in chunk:
                    values = chunk[key]
                    break
            for block in values:
                if not isinstance(block, nbt.TAG_Compound):
                    continue
                changed = convert_block_entity(block, audit) or changed
                if string_value(block.get("id", nbt.TAG_String(""))) in {"minecraft:sign", "minecraft:hanging_sign"}:
                    changed = convert_sign_text(block, audit) or changed
        if changed:
            changes[slot] = serialize_chunk(chunk)
    if not changes or dry_run:
        return len(changes), 0
    data = bytearray(original)
    # Reuse the original slot when the converted chunk still fits.
    for slot, payload in changes.items():
        loc = slot * 4
        offset = int.from_bytes(data[loc:loc + 3], "big")
        old_sectors = data[loc + 3]
        compressed = zlib.compress(payload, 6)
        record = struct.pack(">I", len(compressed) + 1) + bytes([2]) + compressed
        needed = (len(record) + 4095) // 4096
        if needed <= old_sectors:
            start = offset * 4096
            data[start:start + len(record)] = record
            data[start + len(record):start + old_sectors * 4096] = b"\x00" * (old_sectors * 4096 - len(record))
        else:
            start = ((len(data) + 4095) // 4096) * 4096
            if start > len(data):
                data.extend(b"\x00" * (start - len(data)))
            data.extend(record)
            data.extend(b"\x00" * (needed * 4096 - len(record)))
            data[loc:loc + 3] = (start // 4096).to_bytes(3, "big")
            data[loc + 3] = needed
        timestamp = int(time.time())
        data[4096 + slot * 4:4096 + slot * 4 + 4] = timestamp.to_bytes(4, "big")
    temp = path.with_suffix(path.suffix + ".migration.tmp")
    temp.write_bytes(data)
    os.replace(temp, path)
    return len(changes), len(changes)


def read_game_time(world: Path) -> int:
    level = world / "level.dat"
    if not level.exists():
        return 0
    root = nbt.NBTFile(filename=str(level))
    data = root.get("Data", root)
    return as_int(data.get("Time", nbt.TAG_Long(0)))


def read_data_version(world: Path):
    """Read the world's root DataVersion for schema hints; return None if absent."""
    level = world / "level.dat"
    if not level.exists():
        return None
    try:
        root = nbt.NBTFile(filename=str(level))
        data = root.get("Data", root)
        value = data.get("DataVersion")
        return as_int(value) if isinstance(value, nbt.TAG) else None
    except (OSError, ValueError, TypeError, KeyError):
        return None


def read_int_vector(value):
    if isinstance(value, nbt.TAG_Int_Array):
        return [as_int(item) for item in value]
    if isinstance(value, nbt.TAG_List):
        return [as_int(item) for item in value]
    return None


def convert_level_dat(world: Path, dry_run: bool, audit: dict):
    path = world / "level.dat"
    if not path.exists():
        return False
    root = nbt.NBTFile(filename=str(path))
    data = root.get("Data", root)
    blockers_before = len(audit.setdefault("level_blockers", []))
    level_changed = False
    desired_properties = {}

    spawn = data.get("spawn")
    spawn_after = None
    if isinstance(spawn, nbt.TAG_Compound):
        pos = read_int_vector(spawn.get("pos"))
        dimension = string_value(spawn.get("dimension", nbt.TAG_String("minecraft:overworld")))
        yaw = as_float(spawn.get("yaw", nbt.TAG_Float(0.0)))
        pitch = as_float(spawn.get("pitch", nbt.TAG_Float(0.0)))
        if pos is None or len(pos) != 3:
            audit["level_blockers"].append({"reason": "spawn.pos is not a 3-element integer vector"})
        elif dimension != "minecraft:overworld":
            audit["level_blockers"].append({"reason": "global spawn is not overworld", "dimension": dimension, "pos": pos})
        elif not math.isclose(pitch, 0.0, rel_tol=0.0, abs_tol=1e-7):
            audit["level_blockers"].append({"reason": "global spawn pitch has no 1.21.1 persistence field", "pitch": pitch, "pos": pos})
        else:
            before = {key: data.get(key) for key in ("SpawnX", "SpawnY", "SpawnZ", "SpawnAngle") if key in data}
            spawn_after = {"SpawnX": pos[0], "SpawnY": pos[1], "SpawnZ": pos[2], "SpawnAngle": yaw}
            audit["level_spawn"] = {
                "before": {key: tag_value(value) for key, value in before.items()},
                "source": {"pos": pos, "yaw": yaw, "pitch": pitch, "dimension": dimension},
                "after": spawn_after,
            }
            level_changed = True

    rules_changed, rule_properties = convert_game_rules(data, audit)
    level_changed = rules_changed or level_changed
    desired_properties.update(rule_properties)

    difficulty_tag = data.get("Difficulty")
    if difficulty_tag is not None:
        difficulty = as_int(difficulty_tag)
        difficulty_name = DIFFICULTY_NAMES.get(difficulty)
        if difficulty_name is None:
            audit["level_blockers"].append({"reason": "unknown Data.Difficulty", "value": difficulty})
        else:
            audit["difficulty"] = {"source": difficulty, "target_name": difficulty_name}
            desired_properties["difficulty"] = {"value": difficulty_name, "source": "Data.Difficulty"}

    properties_path, properties_payload, properties_changed = plan_server_properties(world, desired_properties, audit)
    if len(audit["level_blockers"]) != blockers_before or audit.get("unsupported_game_rules"):
        return False

    if spawn_after is not None:
        data["SpawnX"] = nbt.TAG_Int(pos[0])
        data["SpawnY"] = nbt.TAG_Int(pos[1])
        data["SpawnZ"] = nbt.TAG_Int(pos[2])
        data["SpawnAngle"] = nbt.TAG_Float(spawn_after["SpawnAngle"])
        del data["spawn"]

    if not dry_run:
        level_temp = path.with_suffix(path.suffix + ".migration.tmp") if level_changed else None
        properties_temp = (
            properties_path.with_suffix(properties_path.suffix + ".migration.tmp")
            if properties_changed
            else None
        )
        try:
            # Stage every payload before the first commit so a full disk cannot
            # remove the modern source rules before properties are durable.
            if level_temp is not None:
                root.write_file(filename=str(level_temp))
            if properties_temp is not None:
                properties_temp.write_bytes(properties_payload)
        except Exception:
            for temp in (level_temp, properties_temp):
                if temp is not None:
                    temp.unlink(missing_ok=True)
            raise

        # Properties go first. If the following level.dat replace is
        # interrupted, game_rules remains available and a rerun is idempotent.
        if properties_temp is not None:
            os.replace(properties_temp, properties_path)
        if level_temp is not None:
            os.replace(level_temp, path)
    return level_changed or properties_changed


READ_SOURCE_DATA_VERSION = object()


def new_audit(
    world,
    game_time,
    target_game_dir=None,
    require_functional_schematics=False,
    source_game_dir=None,
    runtime_capabilities=(),
    compatibility_mods=(),
    source_data_version=READ_SOURCE_DATA_VERSION,
):
    return {
        "world": str(world),
        "game_time": game_time,
        "source_data_version": (
            read_data_version(world)
            if source_data_version is READ_SOURCE_DATA_VERSION
            else source_data_version
        ),
        "source_game_dir": str(source_game_dir) if source_game_dir is not None else None,
        "target_game_dir": str(target_game_dir) if target_game_dir is not None else None,
        "require_functional_schematics": bool(require_functional_schematics),
        "runtime_capabilities": sorted(set(runtime_capabilities)),
        "compatibility_mods": list(compatibility_mods),
        "regions": [],
        "counts": Counter(),
        "players": [],
        "player_item_stacks": [],
        "entity_item_stacks": [],
        "block_entity_item_stacks": [],
        "block_entity_component_maps": [],
        "item_text_components": [],
        "item_tooltip_displays": [],
        "item_component_schema_aliases": [],
        "computercraft_pocket_upgrade_conversions": [],
        "block_entity_text_components": [],
        "block_entity_tooltip_displays": [],
        "block_entity_component_schema_aliases": [],
        "block_entity_computercraft_pocket_upgrades": [],
        "clipboard_hovers": [],
        "axolotl_variants": [],
        "schematic_files": [],
        "inherited_missing_schematic_files": [],
        "unsupported_player_items": [],
        "unsupported_entity_items": [],
        "unsupported_block_entity_items": [],
        "unsupported_block_entity_components": [],
        "player_equipment": [],
        "unsupported_player_equipment": [],
        "player_respawns": [],
        "unsupported_player_respawns": [],
        "malformed_players": [],
        "signs": [],
        "block_positions": [],
        "block_entity_id_aliases": [],
        "block_entity_state_aliases": [],
        "block_entity_print_stage_aliases": [],
        "schematicannon_inventory_conversions": [],
        "item_vault_inventory_conversions": [],
        "fluid_tank_storage_conversions": [],
        "internal_fluid_storage_conversions": [],
        "basin_direction_conversions": [],
        "blaze_forger_inventory_conversions": [],
        "trial_spawner_config_conversions": [],
        "sequenced_assembly_conversions": [],
        "assembly_exception_conversions": [],
        "millstone_uuid_conversions": [],
        "create_fluid_conversions": [],
        "create_fluid_semantic_floor_normalizations": [],
        "create_fluid_exact_potion_scale_conversions": [],
        "create_fluid_nearest_potion_scale_conversions": [],
        "unsupported_create_fluids": [],
        "unsupported_block_entities": [],
        "custom_names": [],
        "equipment": [],
        "saddle_equipment": [],
        "unsupported_equipment": [],
        "leashes": [],
        "unsupported_leashes": [],
        "unsupported_entities": [],
        "contraption_entities": [],
        "unsupported_contraptions": [],
        "unsupported_attributes": [],
        "legacy_attribute_containers": [],
        "legacy_attribute_modifier_merges": [],
        "attribute_aliases": [],
        "consumed_default_attributes": [],
        "retained_compatibility_attributes": [],
        "anger": [],
        "anger_clamped": [],
        "angry_at": [],
        "super_glue": [],
        "boats": [],
        "level_spawn": None,
        "game_rules": [],
        "consumed_default_game_rules": [],
        "unsupported_game_rules": [],
        "game_rule_collisions": [],
        "server_properties": [],
        "difficulty": None,
        "level_blockers": [],
        "empty_regions": [],
        "malformed_regions": [],
    }


def collect_preflight_blockers(audit, require_functional_schematics=False):
    blockers = (
        audit["unsupported_equipment"]
        + audit["unsupported_leashes"]
        + audit["unsupported_player_items"]
        + audit["unsupported_entity_items"]
        + audit["unsupported_block_entity_items"]
        + audit["unsupported_block_entity_components"]
        + audit["unsupported_player_equipment"]
        + audit["unsupported_player_respawns"]
        + audit["unsupported_entities"]
        + audit["unsupported_contraptions"]
        + audit["unsupported_create_fluids"]
        + audit["unsupported_block_entities"]
        + audit["unsupported_attributes"]
        + audit["unsupported_game_rules"]
        + audit["level_blockers"]
        + audit["malformed_players"]
        + audit["malformed_regions"]
    )
    if require_functional_schematics:
        blockers = blockers + audit["inherited_missing_schematic_files"]
    return blockers


REGION_AUDIT_CONTEXT_KEYS = (
    "world",
    "game_time",
    "source_data_version",
    "source_game_dir",
    "target_game_dir",
    "require_functional_schematics",
    "runtime_capabilities",
    "compatibility_mods",
)


def _region_jobs(world, selected, include_entities, include_blocks):
    if include_entities:
        relative_roots = ENTITY_RELATIVE
    else:
        relative_roots = ()
    if include_blocks:
        relative_roots += BLOCK_RELATIVE
    jobs = []
    file_identities = {}
    for relative in relative_roots:
        root = world / relative
        if not root.exists():
            continue
        kind = "entities" if relative.name == "entities" else "region"
        for path in sorted(root.glob("*.mca")):
            rel = str(path.relative_to(world)).replace("\\", "/")
            if selected and rel not in selected and path.name not in selected:
                continue
            try:
                stat = path.stat()
                identity = (stat.st_dev, stat.st_ino)
            except OSError:
                # The worker records a stable malformed-region blocker if the
                # file vanished or became unreadable after enumeration.
                identity = None
            if identity is not None and identity in file_identities:
                raise RuntimeError(
                    "region file selected more than once: "
                    f"{file_identities[identity]} and {rel}"
                )
            if identity is not None:
                file_identities[identity] = rel
            jobs.append((str(path), rel, kind))
    return jobs


def _region_audit_context(audit):
    return {key: audit[key] for key in REGION_AUDIT_CONTEXT_KEYS}


def _process_region_job(job):
    path_text, rel, kind, dry_run, context = job
    path = Path(path_text)
    audit = new_audit(
        Path(context["world"]),
        context["game_time"],
        Path(context["target_game_dir"]) if context["target_game_dir"] else None,
        context["require_functional_schematics"],
        Path(context["source_game_dir"]) if context["source_game_dir"] else None,
        context["runtime_capabilities"],
        context["compatibility_mods"],
        context["source_data_version"],
    )
    try:
        if path.stat().st_size == 0:
            audit["empty_regions"].append(rel)
        else:
            before = len(audit["signs"])
            changed, writes = apply_region(
                path, kind, context["game_time"], dry_run, audit
            )
            if changed:
                audit["regions"].append(
                    {
                        "path": rel,
                        "kind": kind,
                        "chunks_changed": changed,
                        "writes": writes,
                        "signs": len(audit["signs"]) - before,
                    }
                )
                audit["counts"][kind] += changed
    except Exception as exc:
        if not dry_run:
            raise
        audit["malformed_regions"].append(
            {
                "path": rel,
                "kind": kind,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    # Keep the process boundary both pickle-safe and directly JSON-safe.
    audit["counts"] = dict(audit["counts"])
    return audit


def _merge_region_audit(audit, region_audit):
    for key, value in region_audit.items():
        if key == "counts":
            counts = audit.setdefault("counts", Counter())
            for count_key, count in value.items():
                counts[count_key] += count
        elif isinstance(value, list):
            audit.setdefault(key, []).extend(value)


def _print_region_progress(phase, completed, total, workers, started):
    print(
        "PROGRESS "
        + json.dumps(
            {
                "phase": phase,
                "completed": completed,
                "total": total,
                "workers": workers,
                "elapsed": round(time.monotonic() - started, 3),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def process_regions(
    world,
    selected,
    game_time,
    dry_run,
    audit,
    include_entities=True,
    include_blocks=True,
    workers=1,
    phase=None,
):
    if workers < 1:
        raise ValueError("workers must be at least 1")
    context = _region_audit_context(audit)
    jobs = [
        (path, rel, kind, dry_run, context)
        for path, rel, kind in _region_jobs(
            world, selected, include_entities, include_blocks
        )
    ]
    phase = phase or ("dry-run" if dry_run else "convert")
    started = time.monotonic()
    _print_region_progress(phase, 0, len(jobs), workers, started)
    if workers == 1 or len(jobs) < 2:
        for completed, job in enumerate(jobs, 1):
            _merge_region_audit(audit, _process_region_job(job))
            _print_region_progress(phase, completed, len(jobs), workers, started)
        return

    region_results = [None] * len(jobs)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_process_region_job, job): (index, job)
            for index, job in enumerate(jobs)
        }
        for completed, future in enumerate(as_completed(futures), 1):
            index, job = futures[future]
            try:
                region_audit = future.result()
            except Exception as exc:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(
                    f"region worker failed for {job[1]} ({job[2]})"
                ) from exc
            region_results[index] = region_audit
            _print_region_progress(phase, completed, len(jobs), workers, started)
    for region_audit in region_results:
        if region_audit is None:
            raise RuntimeError("region worker completed without an audit result")
        _merge_region_audit(audit, region_audit)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("convert", "dry-run"))
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--only-region", action="append", default=[])
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="region worker processes (default: 1)",
    )
    parser.add_argument("--entities-only", action="store_true", help="scan entity MCA files and level.dat, skipping block regions")
    parser.add_argument(
        "--source-game-dir",
        type=Path,
        help="read external dependencies from this source game directory (defaults to the world's parent)",
    )
    parser.add_argument(
        "--target-game-dir",
        type=Path,
        help="validate referenced external schematic files against this prepared target game directory",
    )
    parser.add_argument(
        "--require-functional-schematics",
        action="store_true",
        help="block conversion when a referenced schematic file was already missing from the source",
    )
    parser.add_argument(
        "--waypoint-fire-compat-jar",
        type=Path,
        help=(
            "validate and declare the waypoint-fire-equivalence 1.21.1 runtime; "
            "required before canonical waypoint attributes/rules are accepted"
        ),
    )
    parser.add_argument(
        "--waypoint-fire-compat-sha256",
        help="required audited SHA-256 for --waypoint-fire-compat-jar",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    world = args.world.resolve()
    source_game_dir = args.source_game_dir.resolve() if args.source_game_dir is not None else world.parent
    target_game_dir = args.target_game_dir.resolve() if args.target_game_dir is not None else None
    if args.mode == "convert" and world == Path(r"<TRANS_ROOT>\20260807\world").resolve():
        raise SystemExit("refusing to write the read-only source world; use a D: migration copy")
    compatibility_mods = []
    runtime_capabilities = []
    if args.waypoint_fire_compat_jar is not None:
        if args.waypoint_fire_compat_sha256 is None:
            raise SystemExit("--waypoint-fire-compat-sha256 is required with --waypoint-fire-compat-jar")
        if target_game_dir is None:
            raise SystemExit("--target-game-dir is required with --waypoint-fire-compat-jar")
        try:
            waypoint_fire_mod = inspect_waypoint_fire_compat_jar(
                args.waypoint_fire_compat_jar,
                args.waypoint_fire_compat_sha256,
                target_game_dir,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        compatibility_mods.append(waypoint_fire_mod)
        runtime_capabilities.append(waypoint_fire_mod["capability"])
    elif args.waypoint_fire_compat_sha256 is not None:
        raise SystemExit("--waypoint-fire-compat-sha256 requires --waypoint-fire-compat-jar")
    game_time = read_game_time(world)
    selected = set(args.only_region)
    # Preflight every region that will be touched so unsupported schemas or a
    # malformed late region cannot be discovered after earlier writes.
    if args.mode == "convert":
        preflight = new_audit(
            world,
            game_time,
            target_game_dir,
            args.require_functional_schematics,
            source_game_dir,
            runtime_capabilities,
            compatibility_mods,
        )
        convert_level_dat(world, True, preflight)
        process_players(world, True, preflight)
        process_regions(
            world,
            selected,
            game_time,
            True,
            preflight,
            include_entities=True,
            include_blocks=not args.entities_only,
            workers=args.workers,
            phase="preflight",
        )
        blockers = collect_preflight_blockers(preflight, args.require_functional_schematics)
        if blockers:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            preflight["counts"] = dict(preflight["counts"])
            preflight["preflight_blocked"] = blockers
            args.report.write_text(json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8")
            raise SystemExit(f"preflight blocked conversion: {len(blockers)} blocking migration records; see {args.report}")
    audit = new_audit(
        world,
        game_time,
        target_game_dir,
        args.require_functional_schematics,
        source_game_dir,
        runtime_capabilities,
        compatibility_mods,
    )
    convert_level_dat(world, args.mode == "dry-run", audit)
    process_players(world, args.mode == "dry-run", audit)
    process_regions(
        world,
        selected,
        game_time,
        args.mode == "dry-run",
        audit,
        include_blocks=not args.entities_only,
        workers=args.workers,
        phase="dry-run" if args.mode == "dry-run" else "convert",
    )
    audit["counts"] = dict(audit["counts"])
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "game_time": game_time,
        "regions": len(audit["regions"]),
        "counts": audit["counts"],
        "boats": len(audit["boats"]),
        "signs": len(audit["signs"]),
        "custom_names": len(audit["custom_names"]),
        "players": len(audit["players"]),
        "player_item_stacks": len(audit["player_item_stacks"]),
        "entity_item_stacks": len(audit["entity_item_stacks"]),
        "block_entity_item_stacks": len(audit["block_entity_item_stacks"]),
        "block_entity_component_maps": len(audit["block_entity_component_maps"]),
        "item_text_components": len(audit["item_text_components"]),
        "item_tooltip_displays": len(audit["item_tooltip_displays"]),
        "item_component_schema_aliases": len(audit["item_component_schema_aliases"]),
        "computercraft_pocket_upgrade_conversions": len(audit["computercraft_pocket_upgrade_conversions"]),
        "block_entity_text_components": len(audit["block_entity_text_components"]),
        "block_entity_tooltip_displays": len(audit["block_entity_tooltip_displays"]),
        "block_entity_component_schema_aliases": len(audit["block_entity_component_schema_aliases"]),
        "block_entity_computercraft_pocket_upgrades": len(audit["block_entity_computercraft_pocket_upgrades"]),
        "clipboard_hovers": sum(record["converted"] for record in audit["clipboard_hovers"]),
        "axolotl_variants": len(audit["axolotl_variants"]),
        "schematic_files": len(audit["schematic_files"]),
        "inherited_missing_schematic_files": len(audit["inherited_missing_schematic_files"]),
        "unsupported_player_items": len(audit["unsupported_player_items"]),
        "unsupported_entity_items": len(audit["unsupported_entity_items"]),
        "unsupported_block_entity_items": len(audit["unsupported_block_entity_items"]),
        "unsupported_block_entity_components": len(audit["unsupported_block_entity_components"]),
        "player_equipment": len(audit["player_equipment"]),
        "unsupported_player_equipment": len(audit["unsupported_player_equipment"]),
        "player_respawns": len(audit["player_respawns"]),
        "unsupported_player_respawns": len(audit["unsupported_player_respawns"]),
        "malformed_players": len(audit["malformed_players"]),
        "block_positions": len(audit["block_positions"]),
        "block_entity_id_aliases": len(audit["block_entity_id_aliases"]),
        "block_entity_state_aliases": len(audit["block_entity_state_aliases"]),
        "block_entity_print_stage_aliases": len(audit["block_entity_print_stage_aliases"]),
        "schematicannon_inventory_conversions": len(audit["schematicannon_inventory_conversions"]),
        "item_vault_inventory_conversions": len(audit["item_vault_inventory_conversions"]),
        "fluid_tank_storage_conversions": len(audit["fluid_tank_storage_conversions"]),
        "internal_fluid_storage_conversions": len(audit["internal_fluid_storage_conversions"]),
        "trial_spawner_config_conversions": len(audit["trial_spawner_config_conversions"]),
        "assembly_exception_conversions": len(audit["assembly_exception_conversions"]),
        "millstone_uuid_conversions": len(audit["millstone_uuid_conversions"]),
        "create_fluid_conversions": len(audit["create_fluid_conversions"]),
        "create_fluid_semantic_floor_normalizations": len(audit["create_fluid_semantic_floor_normalizations"]),
        "create_fluid_exact_potion_scale_conversions": len(audit["create_fluid_exact_potion_scale_conversions"]),
        "create_fluid_nearest_potion_scale_conversions": len(audit["create_fluid_nearest_potion_scale_conversions"]),
        "unsupported_create_fluids": len(audit["unsupported_create_fluids"]),
        "unsupported_block_entities": len(audit["unsupported_block_entities"]),
        "equipment": len(audit["equipment"]),
        "saddle_equipment": len(audit["saddle_equipment"]),
        "unsupported_equipment": len(audit["unsupported_equipment"]),
        "leashes": len(audit["leashes"]),
        "unsupported_leashes": len(audit["unsupported_leashes"]),
        "unsupported_entities": len(audit["unsupported_entities"]),
        "contraption_entities": len(audit["contraption_entities"]),
        "unsupported_contraptions": len(audit["unsupported_contraptions"]),
        "unsupported_attributes": len(audit["unsupported_attributes"]),
        "attribute_aliases": len(audit["attribute_aliases"]),
        "consumed_default_attributes": len(audit["consumed_default_attributes"]),
        "retained_compatibility_attributes": len(audit["retained_compatibility_attributes"]),
        "game_rules": len(audit["game_rules"]),
        "consumed_default_game_rules": len(audit["consumed_default_game_rules"]),
        "unsupported_game_rules": len(audit["unsupported_game_rules"]),
        "game_rule_collisions": len(audit["game_rule_collisions"]),
        "server_properties": len(audit["server_properties"]),
        "angry_at": len(audit["angry_at"]),
        "empty_regions": len(audit["empty_regions"]),
        "malformed_regions": len(audit["malformed_regions"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
