#!/usr/bin/env python3
"""Apply the audited TLM Patchouli JAR balance fix to Attempt13."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(r"<AUDIT_ROOT>")
ARTIFACT = ROOT / "tlm-patchouli-jar-balance-fix-attempt11-20260814" / "jars" / "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
JAR_NAME = ARTIFACT.name
ORIGINAL_SHA = "F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27"
PATCHED_SHA = "32BE64DD058B7A91F90107972D104BDC0946D858E690D4C72032F64873F9B15B"
MAID_REL = Path("kubejs/server_scripts/maid.js")
MAID_SHA = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
OVERLAYS = (
    (Path("kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/maid/spawn_maid.json"), 443, "2904581BFC4704CAF6829ADE482959E766B1A2EDA76C03FF3F23945E4625BD9C"),
    (Path("kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json"), 980, "39CBE907D067E08C6FAD58FBB9601339D8A6141B236BD1F62FFEFB1603F25D3A"),
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    server, client, backup, report = [p.resolve() for p in (args.server, args.client, args.backup, args.report)]
    if report.exists() or backup.exists():
        raise SystemExit("refusing to overwrite Attempt13 TLM report/backup")
    if digest(ARTIFACT) != PATCHED_SHA:
        raise SystemExit("patched TLM artifact hash drifted")
    backup.mkdir(parents=True)
    rows = []
    for side, root in (("server", server), ("client", client)):
        jar = root / "mods" / JAR_NAME
        if digest(jar) != ORIGINAL_SHA:
            raise SystemExit(f"{side} TLM source hash drifted")
        b = backup / side / "mods" / JAR_NAME
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(jar, b)
        tmp = jar.with_name(jar.name + ".attempt13.tmp")
        shutil.copy2(ARTIFACT, tmp)
        tmp.replace(jar)
        rows.append({"side": side, "jar": str(jar), "before_sha256": ORIGINAL_SHA, "after_sha256": digest(jar), "backup": str(b)})
    overlay_rows = []
    for relative, size, expected in OVERLAYS:
        path = client / relative
        if not path.is_file() or path.stat().st_size != size or digest(path) != expected:
            raise SystemExit(f"expected redundant TLM overlay missing/drifted: {path}")
        b = backup / "client" / relative
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, b)
        path.unlink()
        overlay_rows.append({"relative": relative.as_posix(), "before_sha256": expected, "backup": str(b), "after": "ABSENT"})
    maid = server / MAID_REL
    if digest(maid) != MAID_SHA:
        raise SystemExit("maid.js changed unexpectedly")
    payload = {"schema": "attempt13-tlm-patchouli-jar-transaction/v1", "status": "PASS_APPLIED", "server": str(server), "client": str(client), "patched_jar_sha256": PATCHED_SHA, "jar_rows": rows, "removed_redundant_client_overlays": overlay_rows, "maid_js_sha256": MAID_SHA, "recipe_balance": "server kubejs maid.js remains unchanged; spawn_box recipe remains intentionally removed", "world_changes": 0, "config_changes": 0, "mcmodsync_active": False, "rollback": str(backup)}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS_APPLIED", "patched_sha256": PATCHED_SHA, "removed_overlays": len(overlay_rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
