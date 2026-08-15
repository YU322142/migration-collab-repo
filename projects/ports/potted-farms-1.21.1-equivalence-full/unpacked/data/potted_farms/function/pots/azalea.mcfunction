execute at @s if block ~1 ~ ~ minecraft:potted_azalea_bush if block ~1 ~-1 ~ minecraft:hopper[facing=west] run function potted_farms:insert/azalea
execute at @s if block ~-1 ~ ~ minecraft:potted_azalea_bush if block ~-1 ~-1 ~ minecraft:hopper[facing=east] run function potted_farms:insert/azalea
execute at @s if block ~ ~ ~1 minecraft:potted_azalea_bush if block ~ ~-1 ~1 minecraft:hopper[facing=north] run function potted_farms:insert/azalea
execute at @s if block ~ ~ ~-1 minecraft:potted_azalea_bush if block ~ ~-1 ~-1 minecraft:hopper[facing=south] run function potted_farms:insert/azalea