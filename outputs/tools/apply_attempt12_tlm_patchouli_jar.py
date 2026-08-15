#!/usr/bin/env python3
"""Install the audited TLM Patchouli JAR fix on fresh Attempt12 roots."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path


ROOT = Path(r"D:\Trans\migration-audit-work")
SERVER = ROOT / "mechanomania-matched-runtime-attempt12-20260814"
CLIENT = ROOT / "mechanomania-matched-client-attempt12-20260814"
ARTIFACT = ROOT / "tlm-patchouli-jar-balance-fix-attempt11-20260814" / "jars" / "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
BACKUP = ROOT / "attempt12-tlm-patchouli-backup-20260814"
REPORT = ROOT / "attempt12-tlm-patchouli-jar-apply-20260814.json"
JAR_NAME = ARTIFACT.name
ORIGINAL_SHA = "F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27"
PATCHED_SHA = "32BE64DD058B7A91F90107972D104BDC0946D858E690D4C72032F64873F9B15B"
MAID_REL = Path("kubejs/server_scripts/maid.js")
MAID_SHA = "FA458896BC728721995925563DD491F7ED54073FD1A94A5AE87004C66E4990F4"
OVERLAYS = {
    Path("kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/maid/spawn_maid.json"): (443, "2904581BFC4704CAF6829ADE482959E766B1A2EDA76C03FF3F23945E4625BD9C"),
    Path("kubejs/assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/en_us/entries/overview/multiblocks_altar.json"): (980, "39CBE907D067E08C6FAD58FBB9601339D8A6141B236BD1F62FFEFB1603F25D3A"),
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def atomic_copy(source: Path, target: Path) -> None:
    tmp = target.with_name(target.name + ".attempt12-tlm.tmp")
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(source, tmp)
    tmp.replace(target)


def main() -> int:
    if REPORT.exists() or BACKUP.exists():
        raise SystemExit("refusing to overwrite Attempt12 TLM report/backup")
    if not ARTIFACT.is_file() or digest(ARTIFACT) != PATCHED_SHA:
        raise SystemExit("patched TLM artifact hash drifted")
    rows = []
    BACKUP.mkdir(parents=True)
    try:
        for side, root in (("server", SERVER), ("client", CLIENT)):
            if not root.is_dir() or root.is_symlink():
                raise SystemExit(f"unsafe missing Attempt12 root: {root}")
            jar = root / "mods" / JAR_NAME
            if digest(jar) != ORIGINAL_SHA:
                raise SystemExit(f"{side} TLM source hash drifted: {digest(jar)}")
            backup_jar = BACKUP / side / "mods" / JAR_NAME
            backup_jar.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jar, backup_jar)
            atomic_copy(ARTIFACT, jar)
            rows.append({"side": side, "jar": str(jar), "before_sha256": ORIGINAL_SHA, "after_sha256": digest(jar), "backup": str(backup_jar)})
        overlay_rows = []
        for relative, (size, expected) in OVERLAYS.items():
            path = CLIENT / relative
            if not path.is_file() or path.stat().st_size != size or digest(path) != expected:
                raise SystemExit(f"expected redundant TLM overlay missing/drifted: {path}")
            backup = BACKUP / "client" / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            path.unlink()
            overlay_rows.append({"relative": relative.as_posix(), "before_sha256": expected, "backup": str(backup), "after": "ABSENT"})
        maid = SERVER / MAID_REL
        if digest(maid) != MAID_SHA:
            raise SystemExit("maid.js changed unexpectedly")
        report = {
            "schema": "attempt12-tlm-patchouli-jar-transaction/v1",
            "status": "PASS_APPLIED",
            "server": str(SERVER),
            "client": str(CLIENT),
            "patched_jar_sha256": PATCHED_SHA,
            "jar_rows": rows,
            "removed_redundant_client_overlays": overlay_rows,
            "maid_js_sha256": MAID_SHA,
            "recipe_balance": "server kubejs maid.js remains unchanged; spawn_box recipe remains intentionally removed",
            "world_changes": 0,
            "config_changes": 0,
            "mcmodsync_active": False,
            "rollback": str(BACKUP),
        }
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "patched_sha256": PATCHED_SHA, "removed_overlays": len(overlay_rows)}, ensure_ascii=False))
        return 0
    except Exception:
        # Keep the exact backup for manual rollback; do not silently restore a
        # partially changed runtime without a human-auditable record.
        raise


if __name__ == "__main__":
    raise SystemExit(main())
