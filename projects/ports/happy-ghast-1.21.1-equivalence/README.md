# Happy Ghast Equivalence for NeoForge 1.21.1

This companion requires Content Backport 1.5 and is intentionally scoped to
Happy Ghast behavior that is present in the 1.21.11 source world but absent
from the 1.21.1 Backport implementation:

* `home_pos` / `home_radius` are bridged to Backport's restriction API.
* Happy Ghast temptation checks use a 16-block range; other mobs remain at 10.
* The mounted third-person camera distance is 8 blocks on the client.
* `minecraft:happy_ghast_one_cm` and `minecraft:nautilus_one_cm` are registered
  as distance-formatted custom statistics, preserving migrated player values.
* Riding a Happy Ghast, Nautilus, or Zombie Nautilus continues those counters
  with the exact 1.21.11 three-dimensional distance and rounding formula.

The dedicated NBT save/reload smoke passed on NeoForge 21.1.241. The exact
evidence and artifact hash are recorded in `SMOKE-20260808.md`. A real client
camera test remains a release gate before this is copied into the target stack.
See `STAT-COMPAT-20260811.md` for the strict statistic audit and integration gate.
