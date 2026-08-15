#!/usr/bin/env python3
"""Static audit for title-screen branding and hosting hooks in a modpack.

The audit is deliberately read-only. It scans JAR entry names, mixin JSON,
selected text assets, and class-file constant pools for narrowly scoped UI
signals. It does not load Java, NeoForge, Minecraft, or any mod classes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


TEXT_SUFFIXES = (
    ".json",
    ".toml",
    ".cfg",
    ".properties",
    ".txt",
    ".mcmeta",
    ".snbt",
    ".bak",
)
ENTRY_PATTERNS = (
    re.compile(r"title.?screen", re.I),
    re.compile(r"main.?menu", re.I),
    re.compile(r"branding", re.I),
    re.compile(r"logo.?renderer", re.I),
    re.compile(r"assets/minecraft/textures/gui/title/", re.I),
)
SIGNALS = {
    b"menu.online": "menu.online",
    b"Acquire a server": "Acquire a server",
    "\u5f00\u670d".encode("utf-8"): "Chinese hosting label",
    b"bisecthosting.com": "BisectHosting URL",
    b"xyebbs.com/resources/1116/prom": "XYEBBS hosting URL",
    b"net/minecraft/client/gui/screens/TitleScreen": "TitleScreen class reference",
    b"BrandingControl": "NeoForge branding control",
    b"LogoRenderer": "Minecraft logo renderer",
    b"mixin.feature.branding": "ModernFix branding toggle",
    b"window_title": "KubeJS window title setting",
    b"mainMenuConfigButtonRow": "Create main-menu button setting",
    b"config_button_main_menu_row": "Tweaked Controllers main-menu button setting",
    b"onLoadingComplete": "Iris loading-complete hook",
    b"This line is printed by an example mod mixin from NeoForge!": (
        "undeclared NeoForge example mixin log"
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def scan_jar(path: Path) -> dict | None:
    entry_hits: list[str] = []
    signal_hits: dict[str, list[str]] = {}
    mixin_configs: dict[str, dict] = {}
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            name = info.filename
            if any(pattern.search(name) for pattern in ENTRY_PATTERNS):
                entry_hits.append(name)
            if info.is_dir():
                continue
            should_read = (
                name.endswith(".class")
                or name.endswith(TEXT_SUFFIXES)
                or "mixin" in name.lower()
            )
            if not should_read:
                continue
            payload = archive.read(name)
            for needle, label in SIGNALS.items():
                if needle in payload:
                    signal_hits.setdefault(label, []).append(name)
            if name.lower().endswith(".json") and "mixin" in name.lower():
                try:
                    value = json.loads(payload.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                declared = []
                for section in ("mixins", "client", "server"):
                    rows = value.get(section, [])
                    if isinstance(rows, list):
                        declared.extend(
                            f"{section}:{row}"
                            for row in rows
                            if isinstance(row, str)
                            and re.search(
                                r"title.?screen|main.?menu|branding|logo.?renderer",
                                row,
                                re.I,
                            )
                        )
                if declared:
                    mixin_configs[name] = {"declared_ui_mixins": declared}
    if not entry_hits and not signal_hits and not mixin_configs:
        return None
    return {
        "name": path.name,
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "entry_hits": sorted(set(entry_hits)),
        "signal_hits": {
            key: sorted(set(value)) for key, value in sorted(signal_hits.items())
        },
        "mixin_configs": mixin_configs,
    }


def scan_overrides(path: Path) -> dict:
    rows: list[dict] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(path).as_posix()
        name_hit = any(pattern.search(relative) for pattern in ENTRY_PATTERNS)
        signal_labels: list[str] = []
        if item.suffix.lower() in TEXT_SUFFIXES:
            payload = item.read_bytes()
            for needle, label in SIGNALS.items():
                if needle in payload:
                    signal_labels.append(label)
        if name_hit or signal_labels or relative in {
            "icon.png",
            "kubejs/config/client.json",
            "config/create-client.toml",
            "config/createtweakedcontrollers-client.toml",
            "config/modernfix-mixins.properties",
        }:
            rows.append(
                {
                    "path": relative,
                    "bytes": item.stat().st_size,
                    "sha256": sha256_file(item),
                    "name_hit": name_hit,
                    "signals": sorted(set(signal_labels)),
                }
            )
    return {"root": str(path.resolve()), "files": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mods", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    jars = sorted(args.mods.resolve().glob("*.jar"))
    results: list[dict] = []
    errors: list[dict] = []
    for jar in jars:
        try:
            result = scan_jar(jar)
        except (OSError, zipfile.BadZipFile) as exc:
            errors.append({"path": str(jar), "error": repr(exc)})
            continue
        if result:
            results.append(result)
    report = {
        "schema": 1,
        "mods_root": str(args.mods.resolve()),
        "jar_count": len(jars),
        "jar_hit_count": len(results),
        "jar_hits": results,
        "overrides": scan_overrides(args.overrides.resolve()),
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "jar_count": len(jars),
        "jar_hit_count": len(results),
        "errors": len(errors),
        "output": str(args.output.resolve()),
    }, ensure_ascii=True, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
