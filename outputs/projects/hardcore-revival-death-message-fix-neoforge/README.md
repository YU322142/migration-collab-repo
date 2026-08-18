# Hardcore Revival death-message compatibility fix

This small BOTH-side NeoForge compatibility module addresses one narrow interaction in Hardcore Revival 21.1.14.

Hardcore Revival announces the original damage's death message as soon as a player is knocked out, even though the player is still alive and can be rescued. If the rescue timer expires, it then applies the `hardcorerevival:not_rescued_in_time` damage source and vanilla correctly broadcasts the actual death. The mixin suppresses only the premature knockout announcement. The later `未及时获救` timeout message, ordinary deaths, and all revival mechanics remain visible and unchanged.

MineAstr is intentionally not patched. Its `forwardPlayerDeath` path only sends a `player_death` event to the configured bridge; it does not broadcast a chat/system message. This was verified against the deployed 0.6.27 server artifact and the 0.6.28 client artifact. Keeping those JARs unchanged avoids coupling the fix to MineAstr's chat and translation protocol.

Install the single built JAR on both sides, replacing no existing mod and leaving the original Hardcore Revival JAR untouched. Do not place two copies of this module in a `mods` directory. The module requires Hardcore Revival 21.1.14 and NeoForge 21.1.241 for Minecraft 1.21.1.

The fix is deliberately limited to the knockout path. `/kill`, lava, ordinary combat, and other causes still produce a death message if the player actually dies; they no longer claim the player died merely because the player entered the rescuable state.
