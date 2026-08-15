
ItemEvents.modification(event => {
  //深渊祭品
  event.modify('cataclysm:abyssal_sacrifice', item => {
    item.attachCuriosCapability(
      CuriosJSCapabilityBuilder.create()
        .modifyAttribute(attributeModificationContext => {
          let { slotContext } = attributeModificationContext
          attributeModificationContext.modify('minecraft:generic.armor', 'abyssal_sacrifice_' + slotContext.identifier() + slotContext.index(), 0.05, 'add_multiplied_base')
          attributeModificationContext.modify('minecraft:generic.max_health', 'abyssal_sacrifice_' + slotContext.identifier() + slotContext.index(), 0.05, 'add_multiplied_base')
          attributeModificationContext.modify('minecraft:generic.attack_damage', 'abyssal_sacrifice_' + slotContext.identifier() + slotContext.index(), 0.05, 'add_multiplied_base')
        })
    )
  })
  //沙漠项链
  event.modify('cataclysm:necklace_of_the_desert', item => {
    item.attachCuriosCapability(
      CuriosJSCapabilityBuilder.create()
        .modifyAttribute(attributeModificationContext => {
          let { slotContext } = attributeModificationContext
          attributeModificationContext.modify('l2damagetracker:damage_reduction', 'necklace_of_the_desert_' + slotContext.identifier() + slotContext.index(), -0.05, 'add_value')
          attributeModificationContext.modify('minecraft:generic.attack_damage', 'necklace_of_the_desert_' + slotContext.identifier() + slotContext.index(), -0.05, 'add_multiplied_base')
        })
    )
  })
  //恶兽犄角
  event.modify('cataclysm:monstrous_horn', item => {
    item.maxStackSize = 1
    item.attachCuriosCapability(
      CuriosJSCapabilityBuilder.create()
        .canEquip((slotContext, stack) => {
          if (slotContext.entity())
            return !slotContext.entity().isCuriosEquipped('cataclysm:monstrous_horn')
        })
        .addAttribute('minecraft:generic.armor', 'monstrous_horn_armor', 0.3, 'add_multiplied_base')
        .addAttribute('minecraft:generic.armor_toughness', 'monstrous_horn_armor_toughness', 0.25, 'add_multiplied_base')
        .addAttribute('minecraft:generic.max_health', 'monstrous_horn_max_health', 0.15, 'add_multiplied_base')
        .addAttribute('minecraft:generic.movement_speed', 'monstrous_horn_movement_speed', -0.2, 'add_multiplied_base')
    )
  })
  
  // event.modify('minecraft:elytra', item => {
  //   item.attachCuriosCapability(
  //     CuriosJSCapabilityBuilder.create()
  //       .modifyAttribute(attributeModificationContext => {
  //         attributeModificationContext.modify('apothic_attributes:elytra_flight', 'elytra_curios_flight', 1, 'add_value')
  //       })
  //   )
  // })
})