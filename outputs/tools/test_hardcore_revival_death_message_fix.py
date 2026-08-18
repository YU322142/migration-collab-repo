from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "projects" / "hardcore-revival-death-message-fix-neoforge"
JAR = ROOT / "build" / "libs" / "hardcore-revival-death-message-fix-1.0.0+neoforge.1.21.1.1.jar"


def main() -> None:
    assert JAR.is_file(), f"missing build output: {JAR}"
    with zipfile.ZipFile(JAR) as zf:
        names = set(zf.namelist())
        assert len(names) == len(zf.namelist()), "duplicate ZIP entries"
        mixin = zf.read("hardcore_revival_death_fix.mixins.json").decode("utf-8")
        assert "HardcoreRevivalManagerMixin" in mixin
        toml = zf.read("META-INF/neoforge.mods.toml").decode("utf-8")
        assert 'modId="hardcorerevival"' in toml
        cls = zf.read("dev/migration/hardcore_revival_death_fix/mixin/HardcoreRevivalManagerMixin.class")
        assert b"RULE_SHOWDEATHMESSAGES" in cls
        assert b"knockout" in cls
        assert b"notRescuedInTime" not in cls
    print(json.dumps({"status": "PASS", "jar": str(JAR), "entries": len(names)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
