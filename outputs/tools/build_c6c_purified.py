#!/usr/bin/env python3
"""Deterministically remove C6C main-menu branding/hosting hooks from a JAR.

This is intentionally a ZIP-level transformation.  It never starts Java or
Minecraft, never modifies the source archive, and fails closed unless the three
known UI/branding mixins and the menu.online translations are present as expected.
All non-UI classes, mixin declarations, assets, and data files are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


UI_MIXINS = ("UI.LogoRendererMixin", "UI.TitleScreenMixin")
COMMON_UI_MIXINS = ("BrandingControlMixin",)
UI_CLASSES = {
    "org/huahua/pr/mixin/BrandingControlMixin.class",
    "org/huahua/pr/mixin/UI/LogoRendererMixin.class",
    "org/huahua/pr/mixin/UI/TitleScreenMixin.class",
}
TITLE_PREFIX = "assets/minecraft/textures/gui/title/"
LANG_FILES = {
    "assets/minecraft/lang/en_us.json",
    "assets/minecraft/lang/zh_cn.json",
}
MIXIN_CONFIG = "c6c.mixins.json"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class PurificationError(RuntimeError):
    """Raised when the input does not match the audited C6C layout."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def is_signature(name: str) -> bool:
    upper = name.upper()
    return upper.startswith("META-INF/") and upper.endswith(
        (".SF", ".RSA", ".DSA", ".EC")
    )


def canonical_manifest(rows: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, payload in rows:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_bytes(payload).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest().upper()


def safe_label(value: object) -> dict[str, str]:
    text = str(value)
    return {
        "escaped": json.dumps(text, ensure_ascii=True)[1:-1],
        "utf8_sha256": sha256_bytes(text.encode("utf-8")),
    }


def clone_info(source: zipfile.ZipInfo) -> zipfile.ZipInfo:
    target = zipfile.ZipInfo(source.filename, FIXED_TIMESTAMP)
    target.compress_type = source.compress_type
    target.comment = source.comment
    target.internal_attr = source.internal_attr
    target.external_attr = source.external_attr
    target.create_system = source.create_system
    target.extract_version = source.extract_version
    return target


def transform(source: Path, output: Path) -> dict:
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise PurificationError(f"input is not a readable JAR: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)

    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise PurificationError("duplicate ZIP entry names are not supported")
        signatures = sorted(name for name in names if is_signature(name))
        if signatures:
            raise PurificationError(
                "signed JAR cannot be safely rewritten: " + ", ".join(signatures)
            )
        required = UI_CLASSES | LANG_FILES | {MIXIN_CONFIG}
        missing = sorted(required - set(names))
        if missing:
            raise PurificationError(
                "audited UI entries are missing: " + ", ".join(missing)
            )

        original_mixin = json.loads(archive.read(MIXIN_CONFIG).decode("utf-8"))
        client_mixins = original_mixin.get("client")
        if not isinstance(client_mixins, list):
            raise PurificationError("c6c.mixins.json has no client list")
        for mixin in UI_MIXINS:
            if client_mixins.count(mixin) != 1:
                raise PurificationError(
                    f"expected exactly one {mixin} declaration"
                )
        common_mixins = original_mixin.get("mixins")
        if not isinstance(common_mixins, list):
            raise PurificationError("c6c.mixins.json has no common mixin list")
        for mixin in COMMON_UI_MIXINS:
            if common_mixins.count(mixin) != 1:
                raise PurificationError(
                    f"expected exactly one {mixin} declaration"
                )
        purified_mixin = dict(original_mixin)
        purified_mixin["mixins"] = [
            value for value in common_mixins if value not in COMMON_UI_MIXINS
        ]
        purified_mixin["client"] = [
            value for value in client_mixins if value not in UI_MIXINS
        ]

        replacements: dict[str, bytes | None] = {
            MIXIN_CONFIG: stable_json(purified_mixin),
            **{name: None for name in UI_CLASSES},
        }
        menu_values: dict[str, dict[str, str]] = {}
        for name in sorted(LANG_FILES):
            language = json.loads(archive.read(name).decode("utf-8"))
            if not isinstance(language, dict) or "menu.online" not in language:
                raise PurificationError(f"{name} has no menu.online key")
            menu_values[name] = safe_label(language["menu.online"])
            purified_language = dict(language)
            del purified_language["menu.online"]
            replacements[name] = (
                stable_json(purified_language) if purified_language else None
            )

        removed = sorted(
            UI_CLASSES
            | {
                name
                for name in names
                if name.startswith(TITLE_PREFIX)
            }
            | {
                name for name, payload in replacements.items() if payload is None
            }
        )
        modified = sorted(
            name for name, payload in replacements.items() if payload is not None
        )
        rows: list[tuple[zipfile.ZipInfo, bytes]] = []
        preserved_rows: list[tuple[str, bytes]] = []
        data_rows: list[tuple[str, bytes]] = []
        for info in infos:
            name = info.filename
            original = archive.read(name)
            if name in removed or name.startswith(TITLE_PREFIX):
                continue
            payload = replacements.get(name, original)
            if payload is None:
                continue
            rows.append((clone_info(info), payload))
            if name not in modified:
                preserved_rows.append((name, original))
            if name.startswith("data/"):
                data_rows.append((name, original))

    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as target:
            for info, payload in rows:
                target.writestr(info, payload)
        with zipfile.ZipFile(temporary, "r") as check:
            failed = check.testzip()
            if failed is not None:
                raise PurificationError(f"output CRC failure: {failed}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "source": str(source.resolve()),
        "source_bytes": source.stat().st_size,
        "source_sha256": sha256_file(source),
        "output": str(output.resolve()),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "removed_entries": removed,
        "modified_entries": modified,
        "removed_menu_values": menu_values,
        "retained_entry_count": len(rows),
        "preserved_entry_manifest_sha256": canonical_manifest(preserved_rows),
        "preserved_data_entry_count": len(data_rows),
        "preserved_data_manifest_sha256": canonical_manifest(data_rows),
        "retained_common_mixin_count": len(purified_mixin.get("mixins", [])),
        "retained_client_mixin_count": len(purified_mixin.get("client", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = transform(args.source.resolve(), args.output.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_bytes(stable_json(result))
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
