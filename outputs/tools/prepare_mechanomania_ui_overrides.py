#!/usr/bin/env python3
"""Create a minimal overlay that disables remaining pack branding/UI buttons.

Only files that are known to affect the window title, pack icon, or optional
main-menu config buttons are emitted. The source overrides tree is read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


RULES = {
    "config/create-client.toml": [
        (
            r"(?m)^([ \t]*)mainMenuConfigButtonRow[ \t]*=[ \t]*-?\d+[ \t]*(?=\r?$)",
            r"\g<1>mainMenuConfigButtonRow = 0",
        ),
    ],
    "config/createtweakedcontrollers-client.toml": [
        (
            r"(?m)^([ \t]*)config_button_main_menu_row[ \t]*=[ \t]*-?\d+[ \t]*(?=\r?$)",
            r"\g<1>config_button_main_menu_row = 0",
        ),
    ],
    "config/modernfix-mixins.properties": [],
    "kubejs/config/client.json": [],
}
EXCLUDED = (
    "icon.png",
    "config/create-client-1.toml.bak",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def transform_json(relative: str, payload: bytes) -> tuple[bytes, list[str]]:
    value = json.loads(payload.decode("utf-8"))
    if relative == "kubejs/config/client.json":
        old = value.get("window_title")
        if not isinstance(old, str) or not old:
            raise RuntimeError("expected a non-empty KubeJS window_title")
        value["window_title"] = ""
        return stable_json(value), ["window_title: non-empty -> empty"]
    raise RuntimeError(f"no JSON transformer for {relative}")


def transform_text(relative: str, payload: bytes) -> tuple[bytes, list[str]]:
    text = payload.decode("utf-8")
    changes: list[str] = []
    if relative == "config/modernfix-mixins.properties":
        active = re.findall(
            r"(?m)^[ \t]*mixin\.feature\.branding[ \t]*=[ \t]*(?:true|false)[ \t]*(?=\r?$)",
            text,
        )
        if active:
            if len(active) != 1:
                raise RuntimeError("multiple active ModernFix branding overrides")
            text = re.sub(
                r"(?m)^[ \t]*mixin\.feature\.branding[ \t]*=[ \t]*(?:true|false)[ \t]*(?=\r?$)",
                "mixin.feature.branding=false",
                text,
                count=1,
            )
        else:
            text = text.rstrip("\r\n") + "\nmixin.feature.branding=false\n"
        return text.encode("utf-8"), ["mixin.feature.branding -> false"]
    for pattern, replacement in RULES[relative]:
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise RuntimeError(
                f"expected exactly one match for {pattern!r} in {relative}; got {len(matches)}"
            )
        text = re.sub(pattern, replacement, text, count=1)
        changes.append(f"{pattern} -> {replacement.strip()}")
    return text.encode("utf-8"), changes


def build_overlay(source: Path, output: Path) -> dict:
    source = source.resolve()
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"refusing to merge into non-empty overlay: {output}")
    output.mkdir(parents=True, exist_ok=True)

    emitted: list[dict] = []
    for relative in RULES:
        source_file = source / relative
        if not source_file.is_file():
            raise RuntimeError(f"missing audited source file: {source_file}")
        before = source_file.read_bytes()
        if source_file.suffix.lower() == ".json":
            after, changes = transform_json(relative, before)
        else:
            after, changes = transform_text(relative, before)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(after)
        emitted.append(
            {
                "path": relative,
                "source_sha256": sha256_bytes(before),
                "output_sha256": sha256_bytes(after),
                "source_bytes": len(before),
                "output_bytes": len(after),
                "changes": changes,
            }
        )

    excluded: list[dict] = []
    for relative in EXCLUDED:
        path = source / relative
        if not path.is_file():
            raise RuntimeError(f"missing audited excluded file: {path}")
        payload = path.read_bytes()
        excluded.append(
            {"path": relative, "bytes": len(payload), "sha256": sha256_bytes(payload)}
        )

    return {
        "schema": 1,
        "source": str(source),
        "output": str(output),
        "emitted": emitted,
        "excluded_not_copied": excluded,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = build_overlay(args.source, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_bytes(stable_json(report))
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
