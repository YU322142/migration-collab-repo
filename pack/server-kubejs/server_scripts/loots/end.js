LootJS.lootTables((event) => {
  const pimaryLootChance = 0.67;
  const endCityLootChance = 2.5;
  // 一般末地宝箱
  let table = event.getLootTable("minecraft:chests/end_city_treasure");
  table.createPool((pool) => {
    pool.addEntry(
      LootEntry.of(
        'patchouli:guide_book[patchouli:book="umapyoi:trainers_manual"]'
      )
    );
    pool.addEntry(LootEntry.of("umapyoi:blank_ticket").withWeight(2));
  });

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.015);
    })
    .addEntry(LootEntry.of("irons_spellbooks:cinderous_soulcaller"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.002);
    })
    .addEntry(LootEntry.of("irons_spellbooks:timeless_slurry"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.01 * pimaryLootChance);
    })
    .addEntry(LootEntry.of("l2complements:eternium_nugget"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.001 * pimaryLootChance);
    })
    .addEntry(LootEntry.of("l2hostility:chaos_ingot"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.001 * pimaryLootChance);
    })
    .addEntry(LootEntry.of("create:creative_blaze_cake"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.0003 * pimaryLootChance);
    })
    .addEntry(LootEntry.of("create:creative_motor"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.01 * pimaryLootChance);
    })
    .addEntry(LootEntry.of("umapyoi:jewel").setCount([1, 4]));

  // Aviation branch: add Create Ages machines to vanilla End City loot.
  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.3);
    })
    .addEntry(LootEntry.of("createages:andesite_machine").setCount([1, 4]));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.3);
    })
    .addEntry(LootEntry.of("createages:brass_machine").setCount([1, 4]));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.3);
    })
    .addEntry(LootEntry.of("createages:copper_machine").setCount([1, 4]));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.3);
    })
    .addEntry(LootEntry.of("createages:redstone_machine").setCount([1, 4]));

  // 末地城宝箱
  table = event.getLootTable("c6c:chests/end_city_treasure");

  table.createPool((pool) => {
    pool.when((conditions) => {
      conditions.randomChance(0.09);
    });
    pool.addEntry(LootEntry.of("createages:andesite_machine").setCount([1, 6]));
    pool.addEntry(LootEntry.of("createages:copper_machine").setCount([1, 6]));
    pool.addEntry(LootEntry.of("createages:brass_machine").setCount([1, 6]));
    pool.addEntry(LootEntry.of("createages:redstone_machine").setCount([1, 6]));
  });

  table.createPool((pool) => {
    pool.when((conditions) => {
      conditions.randomChance(0.02);
    });
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2complements:hardened":1}}]'
      )
    );
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2complements:ender_mask":1}}]'
      )
    );
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2complements:safeguard":1}}]'
      )
    );
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2complements:shinny":1}}]'
      )
    );
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2complements:stable_body":1}}]'
      )
    );
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2complements:snow_walker":1}}]'
      )
    );
    pool.addEntry(
      LootEntry.of(
        'minecraft:enchanted_book[stored_enchantments={levels:{"l2hostility:insulator":1}}]'
      )
    );
  });

  table.createPool((pool) => {
    pool.when((conditions) => {
      conditions.randomChance(0.025);
    });
    pool.addEntry(LootEntry.of("l2complements:captured_wind"));
    pool.addEntry(LootEntry.of("l2complements:captured_shulker_bullet"));
    pool.addEntry(LootEntry.of("l2complements:sun_membrane"));
    pool.addEntry(LootEntry.of("l2complements:explosion_shard"));
    pool.addEntry(LootEntry.of("l2complements:hard_ice"));
    pool.addEntry(LootEntry.of("l2complements:soul_flame"));
    pool.addEntry(LootEntry.of("l2complements:storm_core"));
    pool.addEntry(LootEntry.of("l2complements:blackstone_core"));
    pool.addEntry(LootEntry.of("l2complements:resonant_feather"));
    pool.addEntry(LootEntry.of("l2complements:warden_bone_shard"));
    pool.addEntry(LootEntry.of("l2complements:guardian_eye"));
    pool.addEntry(LootEntry.of("l2complements:cursed_droplet"));
    pool.addEntry(LootEntry.of("l2complements:life_essence"));
    pool.addEntry(LootEntry.of("l2complements:force_field"));
    pool.addEntry(LootEntry.of("l2complements:fragile_warp_stone"));
  });

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.02);
    })
    .addEntry(LootEntry.of("irons_spellbooks:timeless_slurry"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.015);
    })
    .addEntry(LootEntry.of("irons_spellbooks:cinderous_soulcaller"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.001 * endCityLootChance);
    })
    .addEntry(LootEntry.of("create:creative_blaze_cake"));

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.005 * endCityLootChance);
    })
    .addEntry(LootEntry.of("bhc:red_heart"));

  event.create("touhou_little_maid:entities/fairy").createPool((pool) => {
    pool.addEntry(LootEntry.of("umapyoi:jewel").setCount([1, 2]).withWeight(9));
    pool.addEntry(
      LootEntry.of("umapyoi:blank_ticket").setCount([1, 6]).withWeight(1)
    );
  });

  // 潜影贝
  table = event.getLootTable("minecraft:entities/shulker");
  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.1);
    })
    .addEntry(LootEntry.of("umapyoi:hachimi_mid"))
    .addEntry(LootEntry.of("umapyoi:hachimi_big"))
    .addEntry(LootEntry.of("umapyoi:royal_bitter"))
    .addEntry(LootEntry.of("umapyoi:cupcake"))
    .addEntry(LootEntry.of("umapyoi:sweet_cupcake"))
    .addEntry(LootEntry.of("umapyoi:small_energy_drink"))
    .addEntry(LootEntry.of("umapyoi:medium_energy_drink"))
    .addEntry(LootEntry.of("umapyoi:large_energy_drink"));
  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.1);
    })
    .addEntry(LootEntry.of("umapyoi:jewel"));

  table = event.getLootTable("minecraft:entities/ender_dragon");
  table.createPool().addEntry(LootEntry.of("minecraft:dragon_head"));

  // 试炼大厅
  table = event.getLootTable(
    "minecraft:chests/trial_chambers/intersection_barrel"
  );

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.3);
    })
    .addEntry(LootEntry.of("umapyoi:blank_ticket"));

  table = event.getLootTable("minecraft:chests/trial_chambers/corridor");

  table
    .createPool()
    .when((conditions) => {
      conditions.randomChance(0.3);
    })
    .addEntry(LootEntry.of("umapyoi:blank_ticket"));
});
