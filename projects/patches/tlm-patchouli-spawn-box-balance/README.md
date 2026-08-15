# TLM Patchouli balance-preserving fix

Status: current  
Date: 2026-08-14  
Side: client only

## Decision

Keep the official Mechanomania 1.1.11.2
“kubejs/server_scripts/maid.js” unchanged. It intentionally removes
“touhou_little_maid:altar_recipe/spawn_box” as part of the pack's maid
progression and balance.

The earlier proposal that neutralized this script is superseded and has no
executable overlay left.

## Actual fault

TLM 1.5.3 still contains two client-side Patchouli “altar_recipe” pages that
resolve the intentionally removed recipe:

- “maid/spawn_maid.json”, page index 2
- “overview/multiblocks_altar.json”, page index 4

The official pack already removes the second page semantically in a
“kubejs/data” override, but that does not replace the TLM book entry loaded from
the client's “assets” namespace. It also contains no override for
“spawn_maid.json”. Attempt9 therefore logs the same missing-recipe render error
twice.

## Patch

The client overlay supplies the same two entries under
“kubejs/assets/touhou_little_maid/patchouli_books/...”.

Each entry is generated directly from the locked TLM JAR and removes exactly
one page whose complete value is:

    {
      "type": "altar_recipe",
      "recipe_id": "touhou_little_maid:altar_recipe/spawn_box"
    }

No text, icon, category, multiblock page, image page, ordering, translation key,
recipe, advancement, quest, mod JAR, or server script is changed.
“touhou_little_maid:altar_recipe/reborn_maid” remains in the altar guide.

## Application

Copy the contents of “overlay” into a freshly prepared matched client after the
Mechanomania client tree has been assembled. Do not apply this overlay to the
dedicated server.

The server must retain the original maid.js SHA-256:

    FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4

The client TLM JAR remains unmodified with SHA-256:

    F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27

## Verification boundary

The dual-side static gate proves the server projection is unchanged, the
client projection contains exactly two asset files, and both files are exact
single-page structural diffs. A fresh server/client launch gate must still
confirm that the two render errors disappear while the spawn_box altar recipe
remains unavailable.
