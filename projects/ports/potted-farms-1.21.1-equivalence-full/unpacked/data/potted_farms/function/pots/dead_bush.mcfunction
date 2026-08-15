execute at @s if block ~1 ~ ~ minecraft:potted_dead_bush if block ~1 ~-1 ~ minecraft:hopper[facing=west] run function potted_farms:insert/dead_bush
execute at @s if block ~-1 ~ ~ minecraft:potted_dead_bush if block ~-1 ~-1 ~ minecraft:hopper[facing=east] run function potted_farms:insert/dead_bush
execute at @s if block ~ ~ ~1 minecraft:potted_dead_bush if block ~ ~-1 ~1 minecraft:hopper[facing=north] run function potted_farms:insert/dead_bush
execute at @s if block ~ ~ ~-1 minecraft:potted_dead_bush if block ~ ~-1 ~-1 minecraft:hopper[facing=south] run function potted_farms:insert/dead_bush