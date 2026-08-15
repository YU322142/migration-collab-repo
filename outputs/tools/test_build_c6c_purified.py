#!/usr/bin/env python3
"""Structural and preservation checks for a purified C6C JAR."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from build_c6c_purified import (
    COMMON_UI_MIXINS,
    LANG_FILES,
    MIXIN_CONFIG,
    TITLE_PREFIX,
    UI_CLASSES,
    UI_MIXINS,
)


EXPECTED_CHANGED = {MIXIN_CONFIG} | UI_CLASSES | LANG_FILES


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def verify(source: Path, output: Path) -> dict:
    failures: list[str] = []
    with zipfile.ZipFile(source, "r") as before, zipfile.ZipFile(output, "r") as after:
        failed_crc = after.testzip()
        if failed_crc:
            failures.append(f"CRC failure: {failed_crc}")
        before_names = set(before.namelist())
        after_names = set(after.namelist())

        for name in UI_CLASSES:
            if name in after_names:
                failures.append(f"UI class remains: {name}")
        title_entries = sorted(
            name for name in after_names if name.startswith(TITLE_PREFIX)
        )
        if title_entries:
            failures.append("title assets remain: " + ", ".join(title_entries))

        mixins = json.loads(after.read(MIXIN_CONFIG).decode("utf-8"))
        for value in COMMON_UI_MIXINS:
            if value in mixins.get("mixins", []):
                failures.append(f"branding mixin remains declared: {value}")
        for value in UI_MIXINS:
            if value in mixins.get("client", []):
                failures.append(f"UI mixin remains declared: {value}")

        for name in LANG_FILES & after_names:
            language = json.loads(after.read(name).decode("utf-8"))
            if "menu.online" in language:
                failures.append(f"menu.online remains: {name}")

        preserved = sorted(
            name
            for name in before_names & after_names
            if name not in EXPECTED_CHANGED
            and not name.startswith(TITLE_PREFIX)
        )
        byte_changes = [
            name for name in preserved if before.read(name) != after.read(name)
        ]
        if byte_changes:
            failures.append(
                "non-UI entries changed: " + ", ".join(byte_changes[:20])
            )

        source_mixin = json.loads(before.read(MIXIN_CONFIG).decode("utf-8"))
        expected_common = [
            value
            for value in source_mixin.get("mixins", [])
            if value not in COMMON_UI_MIXINS
        ]
        if mixins.get("mixins") != expected_common:
            failures.append("non-branding common/gameplay mixin list changed")
        expected_client = [
            value
            for value in source_mixin.get("client", [])
            if value not in UI_MIXINS
        ]
        if mixins.get("client") != expected_client:
            failures.append("non-UI client mixin list changed")

        source_data = sorted(name for name in before_names if name.startswith("data/"))
        output_data = sorted(name for name in after_names if name.startswith("data/"))
        if source_data != output_data:
            failures.append("data entry set changed")
        elif any(before.read(name) != after.read(name) for name in source_data):
            failures.append("data entry bytes changed")

        forbidden_strings: list[str] = []
        for name in sorted(after_names):
            if not name.endswith((".json", ".toml", ".cfg", ".properties")):
                continue
            try:
                text = after.read(name).decode("utf-8")
            except UnicodeDecodeError:
                continue
            lowered = text.lower()
            if (
                "menu.online" in lowered
                or "acquire a server" in lowered
                or "\u5f00\u670d" in text
                or "titlescreenmixin" in lowered
                or "logorenderermixin" in lowered
                or "brandingcontrolmixin" in lowered
            ):
                forbidden_strings.append(name)
        if forbidden_strings:
            failures.append(
                "forbidden UI/hosting signals remain: "
                + ", ".join(forbidden_strings)
            )

        forbidden_binary_signals = {
            b"https://www.xyebbs.com/resources/1116/prom": "xyebbs hosting URL",
            b"https://www.bisecthosting.com/curseforge?curseforge_project_id=1469136": "BisectHosting URL",
            b"Acquire a server": "hosting button label",
            b"org/huahua/pr/mixin/UI/TitleScreenMixin": "title-screen mixin class reference",
            b"org/huahua/pr/mixin/UI/LogoRendererMixin": "logo mixin class reference",
            b"org/huahua/pr/mixin/BrandingControlMixin": "branding mixin class reference",
        }
        binary_hits: list[str] = []
        for name in sorted(after_names):
            payload = after.read(name)
            for needle, label in forbidden_binary_signals.items():
                if needle in payload:
                    binary_hits.append(f"{label}: {name}")
        if binary_hits:
            failures.append(
                "forbidden binary UI/hosting signals remain: "
                + "; ".join(binary_hits[:20])
            )

        retained_manifest = hashlib.sha256()
        for name in preserved:
            retained_manifest.update(name.encode("utf-8"))
            retained_manifest.update(b"\0")
            retained_manifest.update(digest(after.read(name)).encode("ascii"))
            retained_manifest.update(b"\n")

    return {
        "status": "PASS" if not failures else "FAIL",
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "source_entries": len(before_names),
        "output_entries": len(after_names),
        "preserved_entries_verified": len(preserved),
        "data_entries_verified": len(source_data),
        "preserved_manifest_sha256": retained_manifest.hexdigest().upper(),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.source.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
