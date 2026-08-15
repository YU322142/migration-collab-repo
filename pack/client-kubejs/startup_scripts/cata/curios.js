let $Player = Java.loadClass("net.minecraft.world.entity.player.Player")
let $SlotAttribute = Java.loadClass('top.theillusivec4.curios.api.SlotAttribute')
StartupEvents.registry("item", item => {
  item.create('c6c:utility_belt')
    .attachCuriosCapability(
      CuriosJSCapabilityBuilder.create()
        .canEquip((slotContext, stack) => {
          if (slotContext.entity())
            return !slotContext.entity().isCuriosEquipped('c6c:utility_belt') && slotContext.entity() instanceof $Player
        })
        .modifyAttribute(context => {
          context.modify(
            $SlotAttribute.getOrCreate('ring'),
            'utility_belt_addon',
            1,
            'add_value'
          )
          context.modify(
            $SlotAttribute.getOrCreate('hands'),
            'utility_belt_addon',
            1,
            'add_value'
          )
        })
        .addAttribute('irons_spellbooks:max_mana', 'utility_belt_addon', 100, 'add_value')
    )
    .maxStackSize(1)
    .tag(['curios:belt', 'l2hostility:chaos_equipment'])

  item.create('c6c:reinforced_carapace')
    .attachCuriosCapability(
      CuriosJSCapabilityBuilder.create()
        .canEquip((slotContext, stack) => {
          if (slotContext.entity())
            return !slotContext.entity().isCuriosEquipped('c6c:reinforced_carapace')
        })
        .addAttribute('minecraft:generic.armor', 'reinforced_carapace_addon', 4, 'add_value')
        .addAttribute('minecraft:generic.armor_toughness', 'reinforced_carapace_addon', 1, 'add_value')
    )
    .maxStackSize(1)
    .tag('curios:back')
})


