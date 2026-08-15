# Attempt10 loot follow-up static audit

Status: `PASS_STATIC_CANDIDATE`. Java/Minecraft was not started and no runtime, world, release, or Prism directory was modified.

## Diagnosis

- `irons_spellbooks:test/ring_gen_break_me` is an orphan test resource, not gameplay: it lives under `loot_table/test`, is named `break_me`, intentionally filters the invalid spell `none`, has no installed textual/code/data reference, and the official pack loose copy is byte-identical to the original Iron's Spells test entry. The previously patched Iron JAR already removed its own copy; the server KubeJS override was the surviving source.
- The DnT `library_chest` and `secret_room` files are production-shaped gameplay loot tables, not tests. Attempt6 removed the unavailable `nova_structures:illagers_bane` fields but left `{}` inside each `functions` array, which the 1.21.1 loot codec rejects.

## Static fix

- Delete exactly the 466-byte server loose test table after verifying SHA-256 `C836FCE6BE894AB5C5004692A4F2215B6FCCAF7EE88848E2F476CC3C0F189636`. Do not rebuild Iron's Spells again.
- Replace DnT on both server and client with the generated JAR. Each affected book entry keeps its item, weight, pool, table, and outer no-op Nova modifier; only the now-empty `functions` property is removed.
- Patched DnT SHA-256: `A7D3ABB6C39FB50C791D52E596C9D14C22D0287EAF6BA055A687C31C0A4C8A7E`; bytes: `945155`. Two independent builds were byte-identical.
- Exactly two JAR entries changed; the other `195` entries are byte-identical. All `19` DnT loot/item-modifier JSON files parsed, no empty function object remains, and ZIP CRC validation passed.

## Fresh Attempt11 integration

Apply only the three operations in `integration-plan-attempt11.json`: replace DnT on server, replace DnT on client, and delete the exact server loose Iron test table. Then run a fresh strict startup ERROR gate; this static package deliberately does not claim runtime PASS.
