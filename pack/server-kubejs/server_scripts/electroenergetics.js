ServerEvents.recipes((event) => {
  event.remove({id: "electroenergetics:compacting/plant_oil"});
  event.remove({id: "electroenergetics:crafting/copper_wire"});
  event.remove({id: "electroenergetics:crafting/iron_wire"});
});
