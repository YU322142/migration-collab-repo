"""Fail-closed migration for MineAstr sign translation cache v1 -> v2.

The NeoForge port reads the v1 NBT shape, but automatic v1 entries carry
policy_version=1 and are intentionally hidden by the current policy. This
tool promotes only those legacy automatic entries after validating the full
identity and translation payload. It never edits the source in place.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path

from nbt.nbt import NBTFile, TAG_Byte, TAG_Compound, TAG_Int, TAG_List, TAG_String


FILE_NAME = "mineastr_sign_translations.dat"
SOURCE_VERSION = 1
TARGET_VERSION = 2
CURRENT_POLICY_VERSION = 2
MAX_ENTRIES = 100_000
MAX_TEXT_LENGTH = 16_384
ROOT_KEYS = {"version", "entries"}
V1_ENTRY_KEYS = {"id", "fingerprint", "source", "show_original", "translations"}
V2_ENTRY_KEYS = V1_ENTRY_KEYS | {"skip_translation", "policy_version", "manual_languages"}


def _text(value: object, path: str) -> str:
    if not isinstance(value, TAG_String):
        raise ValueError(f"{path} must be a string tag")
    result = str(value)
    if len(result) > MAX_TEXT_LENGTH:
        raise ValueError(f"{path} exceeds text limit")
    return result


def _bool(value: object, path: str, default: bool | None = None) -> bool:
    if value is None and default is not None:
        return default
    if not isinstance(value, TAG_Byte):
        raise ValueError(f"{path} must be a byte tag")
    return int(value.value) != 0


def _int(value: object, path: str, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if not isinstance(value, TAG_Int):
        raise ValueError(f"{path} must be an int tag")
    return int(value.value)


def _translations(value: object, path: str) -> TAG_Compound:
    if not isinstance(value, TAG_Compound):
        raise ValueError(f"{path} must be a compound tag")
    result = TAG_Compound()
    for language, text in value.items():
        language_text = str(language)
        if not language_text or len(language_text) > 64:
            raise ValueError(f"{path}.{language_text} has an invalid language key")
        result[language_text] = TAG_String(_text(text, f"{path}.{language_text}"))
    return result


def _manual_languages(value: object, path: str, default_empty: bool) -> TAG_Compound:
    if value is None and default_empty:
        return TAG_Compound()
    if not isinstance(value, TAG_Compound):
        raise ValueError(f"{path} must be a compound tag")
    result = TAG_Compound()
    for language, flag in value.items():
        language_text = str(language)
        if not language_text or len(language_text) > 64:
            raise ValueError(f"{path}.{language_text} has an invalid language key")
        if not isinstance(flag, TAG_Byte):
            raise ValueError(f"{path}.{language_text} must be a byte tag")
        if int(flag.value) != 0:
            result[language_text] = TAG_Byte(1)
    return result


def _semantic(root: NBTFile) -> dict:
    entries = []
    for entry in root.get("entries", []):
        translations = {str(k): str(v.value) for k, v in entry.get("translations", {}).items()}
        manual = {str(k): int(v.value) != 0 for k, v in entry.get("manual_languages", {}).items()}
        entries.append(
            {
                "id": str(entry.get("id", "")),
                "fingerprint": str(entry.get("fingerprint", "")),
                "source": str(entry.get("source", "")),
                "show_original": int(entry.get("show_original", TAG_Byte(0)).value) != 0,
                "skip_translation": int(entry.get("skip_translation", TAG_Byte(0)).value) != 0,
                "policy_version": int(entry.get("policy_version", TAG_Int(1)).value),
                "translations": dict(sorted(translations.items())),
                "manual_languages": dict(sorted(manual.items())),
            }
        )
    version_tag = root.get("version", TAG_Int(0))
    return {"version": int(version_tag.value), "entries": sorted(entries, key=lambda x: x["id"])}


def semantic_hash(root: NBTFile) -> str:
    payload = json.dumps(_semantic(root), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_deterministic_gzip(root: NBTFile, path: Path) -> None:
    # python-nbt otherwise embeds the temporary filename and current time in
    # the gzip header, which makes byte-identical migrations hash differently.
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            root.write_file(buffer=compressed)


def _validate_and_convert(root: NBTFile, promote_automatic: bool) -> tuple[NBTFile, dict]:
    unknown_root = sorted(set(root.keys()) - ROOT_KEYS)
    if unknown_root:
        raise ValueError(f"unknown root keys: {', '.join(unknown_root)}")
    version = _int(root.get("version"), "version")
    if version not in (SOURCE_VERSION, TARGET_VERSION):
        raise ValueError(f"unsupported cache version {version}; expected 1 or 2")
    entries = root.get("entries")
    if not isinstance(entries, TAG_List) or entries.tagID != TAG_Compound.id:
        raise ValueError("entries must be a compound list")
    if len(entries) > MAX_ENTRIES:
        raise ValueError("entries exceeds limit")

    output = NBTFile()
    output["version"] = TAG_Int(TARGET_VERSION)
    output_entries = TAG_List(type=TAG_Compound)
    seen_ids: set[str] = set()
    changed = 0
    promoted = 0
    automatic_entries = 0
    manual_entries = 0
    skipped_entries = 0
    translation_values = 0
    manual_language_markers = 0
    output_usable_entries = 0
    for index, entry in enumerate(entries):
        path = f"entries[{index}]"
        if not isinstance(entry, TAG_Compound):
            raise ValueError(f"{path} must be a compound tag")
        allowed_keys = V1_ENTRY_KEYS if version == SOURCE_VERSION else V2_ENTRY_KEYS
        unknown_entry = sorted(set(entry.keys()) - allowed_keys)
        if unknown_entry:
            raise ValueError(f"{path} has unknown keys: {', '.join(unknown_entry)}")
        identifier = _text(entry.get("id"), f"{path}.id")
        fingerprint = _text(entry.get("fingerprint"), f"{path}.fingerprint")
        source = _text(entry.get("source"), f"{path}.source")
        if not identifier or not fingerprint:
            raise ValueError(f"{path} has a blank identity")
        if identifier in seen_ids:
            raise ValueError(f"duplicate sign id {identifier!r}")
        seen_ids.add(identifier)

        translations = _translations(entry.get("translations"), f"{path}.translations")
        manual = _manual_languages(entry.get("manual_languages"), f"{path}.manual_languages", version == 1)
        show_original = _bool(entry.get("show_original"), f"{path}.show_original")
        skip_translation = _bool(entry.get("skip_translation"), f"{path}.skip_translation", False)
        policy = _int(entry.get("policy_version"), f"{path}.policy_version", 1)
        if policy < 1 or policy > CURRENT_POLICY_VERSION:
            raise ValueError(f"{path}.policy_version is unsupported: {policy}")
        if any(language not in translations for language in manual):
            raise ValueError(f"{path}.manual_languages references a missing translation")

        translation_values += len(translations)
        manual_language_markers += len(manual)
        if manual:
            manual_entries += 1
        elif skip_translation:
            skipped_entries += 1
        else:
            automatic_entries += 1

        if promote_automatic and not manual and not skip_translation and policy < CURRENT_POLICY_VERSION:
            policy = CURRENT_POLICY_VERSION
            promoted += 1
        if policy == CURRENT_POLICY_VERSION or manual:
            output_usable_entries += 1
        if policy != _int(entry.get("policy_version"), f"{path}.policy_version", 1) or version == SOURCE_VERSION:
            changed += 1

        converted = TAG_Compound()
        converted["id"] = TAG_String(identifier)
        converted["fingerprint"] = TAG_String(fingerprint)
        converted["source"] = TAG_String(source)
        converted["show_original"] = TAG_Byte(1 if show_original else 0)
        converted["skip_translation"] = TAG_Byte(1 if skip_translation else 0)
        converted["policy_version"] = TAG_Int(policy)
        converted["translations"] = translations
        converted["manual_languages"] = manual
        output_entries.append(converted)

    output["entries"] = output_entries
    report = {
        "source_version": version,
        "target_version": TARGET_VERSION,
        "entries": len(entries),
        "changed_entries": changed,
        "promoted_automatic_entries": promoted,
        "automatic_entries": automatic_entries,
        "manual_entries": manual_entries,
        "skipped_entries": skipped_entries,
        "translation_value_count": translation_values,
        "manual_language_marker_count": manual_language_markers,
        "output_usable_entries": output_usable_entries,
        "source_semantic_sha256": semantic_hash(root),
        "target_semantic_sha256": semantic_hash(output),
        "entry_identifiers_redacted": True,
        "content_values_redacted": True,
        "status": "CHANGED" if changed else "ALREADY_TARGET",
    }
    return output, report


def migrate(source: Path, output: Path | None, report_path: Path | None, promote_automatic: bool) -> dict:
    if output is not None and source.resolve() == output.resolve():
        raise ValueError("refusing in-place conversion; choose a separate staging output")
    root = NBTFile(filename=str(source))
    converted, report = _validate_and_convert(root, promote_automatic)
    report["source_file_sha256"] = file_hash(source)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
        os.close(fd)
        try:
            _write_deterministic_gzip(converted, Path(temporary))
            Path(temporary).replace(output)
        finally:
            Path(temporary).unlink(missing_ok=True)
        report["output_bytes"] = output.stat().st_size
        report["target_file_sha256"] = file_hash(output)
        report["deterministic_gzip"] = True
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate MineAstr sign cache v1 to v2")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--promote-automatic",
        action="store_true",
        help="make legacy automatic translations visible under policy version 2",
    )
    args = parser.parse_args()
    try:
        report = migrate(args.source, args.output, args.report, args.promote_automatic)
    except Exception as exc:  # CLI must fail closed without writing partial output.
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
