#!/usr/bin/env python3
"""Verify the generated Mechanomania UI override overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def verify_overlay(overlay: Path) -> dict:
    overlay = overlay.resolve()
    failures: list[str] = []

    expected = {
        "config/create-client.toml",
        "config/createtweakedcontrollers-client.toml",
        "config/modernfix-mixins.properties",
        "kubejs/config/client.json",
    }
    actual = {
        path.relative_to(overlay).as_posix()
        for path in overlay.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        failures.append(f"unexpected overlay file set: {sorted(actual)}")
    if (overlay / "icon.png").exists():
        failures.append("pack icon was copied")

    create = (overlay / "config/create-client.toml").read_text(encoding="utf-8")
    if not re.search(r"(?m)^\s*mainMenuConfigButtonRow\s*=\s*0\s*$", create):
        failures.append("Create main-menu button is not disabled")
    if not re.search(r"(?m)^\s*ingameMenuConfigButtonRow\s*=\s*3\s*$", create):
        failures.append("Create in-game config button changed unexpectedly")

    controller = (
        overlay / "config/createtweakedcontrollers-client.toml"
    ).read_text(encoding="utf-8")
    if not re.search(
        r"(?m)^\s*config_button_main_menu_row\s*=\s*0\s*$", controller
    ):
        failures.append("Tweaked Controllers main-menu button is not disabled")
    if not re.search(
        r"(?m)^\s*config_button_ingame_menu_row\s*=\s*3\s*$", controller
    ):
        failures.append("Tweaked Controllers in-game button changed unexpectedly")

    modernfix = (
        overlay / "config/modernfix-mixins.properties"
    ).read_text(encoding="utf-8")
    active_branding = re.findall(
        r"(?m)^\s*mixin\.feature\.branding\s*=\s*(true|false)\s*$", modernfix
    )
    if active_branding != ["false"]:
        failures.append(
            f"ModernFix title branding is not uniquely disabled: {active_branding}"
        )

    kubejs = json.loads(
        (overlay / "kubejs/config/client.json").read_text(encoding="utf-8")
    )
    if kubejs.get("window_title") != "":
        failures.append("KubeJS window title was not cleared")

    return {
        "status": "PASS" if not failures else "FAIL",
        "overlay": str(overlay),
        "files_verified": len(actual),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("overlay", type=Path)
    args = parser.parse_args()
    result = verify_overlay(args.overlay)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
