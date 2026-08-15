const the_end_material = ['l2complements:totemic_gold', 'l2complements:poseidite', 'l2complements:shulkerate', 'l2complements:sculkium', 'l2complements:eternium', 'cataclysm:ignitium', 'cataclysm:cursium']
const equipment = ['helmet', 'chestplate', 'leggings', 'boots']
const projectile_source = ['minecraft:trident', 'cataclysm:cursed_bow', 'minecraft:bow', 'minecraft:crossbow']
ServerEvents.recipes(event => {
	event.shaped('c6c:momentum_boots', [
		"A A",
		"CDC",
		"AEA",
	], {
		A: 'l2hostility:speedy',
		C: 'l2complements:captured_wind',
		D: 'minecraft:leather_boots',
		E: 'l2hostility:chaos_ingot'
	})

	event.shaped('c6c:curse_of_timid', [
		" A ",
		" A ",
		"ABA"
	], {
		A: 'cataclysm:witherite_ingot',
		B: 'minecraft:totem_of_undying'
	})

	event.shaped('c6c:utility_belt', [
		"ABA",
		"BCB",
		"DAD",
	], {
		A: 'irons_spellbooks:magic_cloth',
		B: 'minecraft:tripwire_hook',
		C: 'l2hostility:miracle_ingot',
		D: 'cataclysm:essence_of_the_storm',
	})

	event.shaped('c6c:ward_breaker', [
		"AAA",
		"AAA",
		" B ",
	], {
		A: 'irons_spellbooks:arcane_ingot',
		B: 'l2hostility:teleport',
	})

	//event.blasting('kubejs:cooked_andesite_alloy', 'create:andesite_alloy', 0.05, 100)
	// event.smelting('kubejs:cooked_mouse', 'kaleidoscope_doll:doll_94', 0.2, 200)

	equipment.forEach(location => {
		the_end_material.forEach(material => {
			event.smithing(material + '_' + location, 'create:sand_paper', '#kubejs:the_end_' + location, material + '_' + location)
		})
	})
})


ServerEvents.tags('item', event => {
	equipment.forEach(location => {
		the_end_material.forEach(material => {
			event.add('kubejs:the_end_' + location, material + '_' + location)
		})
		projectile_source.forEach(sorce => {
			event.add('kubejs:projectile_source', sorce)
		})
	})
})
