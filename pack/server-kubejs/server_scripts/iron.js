ServerEvents.recipes((event) => {
  event.remove({
    mod: "irons_spellbooks"
  });

  event.shapeless("2x irons_spellbooks:mithril_scrap", 'irons_spellbooks:mithril_ingot')
  event.shapeless("irons_spellbooks:mithril_ingot", '2x irons_spellbooks:mithril_scrap')

  event.shaped('irons_spellbooks:hither_thither_wand', [
    "  H",
    " D ",
    "T  ",
  ], {
    H: 'minecraft:amethyst_cluster',
    D: 'minecraft:stick',
    T: 'irons_spellbooks:pyrium_ingot'
  });

  event.shaped('irons_spellbooks:hither_thither_wand[irons_spellbooks:spell_container={data:[{id:"irons_spellbooks:teleport",index:0,level:3,locked:1b}],maxSpells:1,mustEquip:0b,spellWheel:1b}]', [
    "  H",
    " D ",
    "T  ",
  ], {
    H: 'cataclysm:tidal_claws',
    D: 'minecraft:stick',
    T: 'irons_spellbooks:pyrium_ingot'
  });

  event.blasting('irons_spellbooks:pyrium_ingot', 'irons_spellbooks:hellrazor')

  event.shaped('irons_spellbooks:graybeard_staff[irons_spellbooks:spell_container={data:[{id:"irons_spellbooks:black_hole",index:0,level:2,locked:1b}],maxSpells:1,mustEquip:0b,spellWheel:1b}]', [
    "GSG",
    "EPE",
  ], {
    S: 'irons_spellbooks:arcane_rune',
    G: 'l2complements:void_eye',
    E: 'l2complements:sculkium_ingot',
    P: 'irons_spellbooks:hither_thither_wand'
  });

  event.shaped('irons_spellbooks:graybeard_staff[irons_spellbooks:spell_container={data:[{id:"irons_spellbooks:sculk_tentacles",index:0,level:2,locked:1b}],maxSpells:1,mustEquip:0b,spellWheel:1b}]', [
    "GSG",
    "EPE",
  ], {
    S: 'irons_spellbooks:arcane_rune',
    G: 'l2complements:blackstone_core',
    E: 'l2complements:poseidite_ingot',
    P: 'irons_spellbooks:hither_thither_wand'
  });
})