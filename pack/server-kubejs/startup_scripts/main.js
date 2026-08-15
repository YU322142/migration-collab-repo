StartupEvents.registry("item", (event) => {
  event.create("ticket").rarity("epic");

  event.create("createages:iron_mechanism");
  event.create("createages:copper_mechanism");
  event.create("createages:incomplete_brass_mechanism");
});

StartupEvents.registry('block', event => {
  event.create('createages:andesite_machine')
    .displayName('Andesite Machine')
    .soundType('stone')
    .notSolid()
    .hardness(0)
    .tagBlock('kubejs:create_machines')
    .tagBlock('create:wrench_pickup')
    .item(itm=>itm.maxStackSize(99))

  event.create('createages:copper_machine')
    .displayName('Copper Machine')
    .soundType('stone')
    .notSolid()
    .hardness(0)
    .tagBlock('kubejs:create_machines')
    .tagBlock('create:wrench_pickup')
    .item(itm=>itm.maxStackSize(99))

  event.create('createages:brass_machine')
    .displayName('Brass Machine')
    .soundType('stone')
    .notSolid()
    .hardness(0)
    .tagBlock('kubejs:create_machines')
    .tagBlock('create:wrench_pickup')
    .item(itm=>itm.maxStackSize(99))

  event.create('createages:redstone_machine')
    .displayName('Redstone Machine')
    .soundType('stone')
    .notSolid()
    .hardness(0)
    .tagBlock('kubejs:create_machines')
    .tagBlock('create:wrench_pickup')
    .item(itm=>itm.maxStackSize(99))

  event.create('warped_stem_chlorophyte')
    .displayName('Chlorophyted Warped Stem')
    .soundType('wood')
    .hardness(240)
    .defaultCutout()
    .tagBlock('minecraft:mineable/axe')
    .tagBlock('minecraft:needs_netherite_tool')

  event.create('compressed_tuff')
    .displayName('Compressed Tuff')
    .soundType('stone')
    .hardness(10)
    .tagBlock('minecraft:mineable/pickaxe')

  event.create('oiled_lapis')
    .displayName('Oiled Lapis')
    .soundType('stone')
    .hardness(20)
    .tagBlock('minecraft:mineable/pickaxe')
})