#!/usr/bin/env python3
"""Build a fail-closed C6C overlay that applies maid model policy in singleplayer.

The audited C6C 1.2.5.1 class currently turns the Touhou Little Maid model-change
setting off on a dedicated server, but explicitly turns it back on on the client
distribution (which also hosts an integrated singleplayer server).  This overlay
keeps the existing config gate and makes its environment predicate constant true,
so the same configured gameplay policy applies to both server forms.

Only org/huahua/pr/C6C.class is changed.  Every other ZIP entry must remain byte
identical to the purified base JAR.  Login/authentication mods are not inspected or
modified by this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


LOCKED_BASE_SHA256 = "2666383E0E2C4C6F49494051FC2C3723D6B851DABD42D511F05712BAD2A529C4"
TARGET_CLASS = "org/huahua/pr/C6C.class"

# commonSetup bytecode from the locked C6C base:
#   invokestatic FMLLoader.getDist
#   invokevirtual Dist.isDedicatedServer
#   ifeq client_branch
# Replace only the invokevirtual with POP, ICONST_1, NOP.  Instruction sizes and
# branch/frame offsets remain unchanged, while the predicate becomes true.
OLD_SEQUENCE = bytes.fromhex("B8 00 A3 B6 00 A9 99 00 10")
NEW_SEQUENCE = bytes.fromhex("B8 00 A3 57 04 00 99 00 10")


class PatchError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def is_signature(name: str) -> bool:
    upper = name.upper()
    return upper.startswith("META-INF/") and upper.endswith(
        (".SF", ".RSA", ".DSA", ".EC")
    )


def clone_info(source: zipfile.ZipInfo) -> zipfile.ZipInfo:
    target = zipfile.ZipInfo(source.filename, source.date_time)
    target.compress_type = source.compress_type
    target.comment = source.comment
    target.internal_attr = source.internal_attr
    target.external_attr = source.external_attr
    target.create_system = source.create_system
    target.extract_version = source.extract_version
    target.flag_bits = source.flag_bits
    return target


def patch_class(payload: bytes) -> bytes:
    old_count = payload.count(OLD_SEQUENCE)
    new_count = payload.count(NEW_SEQUENCE)
    if old_count != 1 or new_count != 0:
        raise PatchError(
            f"unexpected C6C bytecode contract: old={old_count}, new={new_count}"
        )
    patched = payload.replace(OLD_SEQUENCE, NEW_SEQUENCE, 1)
    if len(patched) != len(payload):
        raise PatchError("class length changed")
    if patched.count(OLD_SEQUENCE) != 0 or patched.count(NEW_SEQUENCE) != 1:
        raise PatchError("post-patch bytecode contract failed")
    return patched


def transform(
    source: Path,
    output: Path,
    *,
    expected_sha256: str | None = LOCKED_BASE_SHA256,
) -> dict[str, object]:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise PatchError("source and output must be different files")
    if not source.is_file() or not zipfile.is_zipfile(source):
        raise PatchError(f"source is not a readable JAR: {source}")

    source_sha = sha256_file(source)
    if expected_sha256 and source_sha != expected_sha256.upper():
        raise PatchError(
            f"base SHA-256 mismatch: expected {expected_sha256}, got {source_sha}"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)

    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        names = [entry.filename for entry in infos]
        if len(names) != len(set(names)):
            raise PatchError("duplicate ZIP entries are not supported")
        signatures = [name for name in names if is_signature(name)]
        if signatures:
            raise PatchError("signed JAR cannot be overlaid")
        if names.count(TARGET_CLASS) != 1:
            raise PatchError(f"expected exactly one {TARGET_CLASS}")

        original_class = archive.read(TARGET_CLASS)
        patched_class = patch_class(original_class)
        rows: list[tuple[zipfile.ZipInfo, bytes]] = []
        preserved: list[tuple[str, str]] = []
        for info in infos:
            original = archive.read(info.filename)
            payload = patched_class if info.filename == TARGET_CLASS else original
            rows.append((clone_info(info), payload))
            if info.filename != TARGET_CLASS:
                preserved.append((info.filename, sha256_bytes(original)))

    try:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as target:
            for info, payload in rows:
                target.writestr(info, payload)
        with zipfile.ZipFile(temporary, "r") as check:
            failed = check.testzip()
            if failed:
                raise PatchError(f"output CRC failure: {failed}")
            if check.read(TARGET_CLASS) != patched_class:
                raise PatchError("written class does not match patched payload")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    with zipfile.ZipFile(output, "r") as result:
        non_target_mismatches = []
        with zipfile.ZipFile(source, "r") as base:
            for name, digest in preserved:
                if sha256_bytes(result.read(name)) != digest:
                    non_target_mismatches.append(name)
        if non_target_mismatches:
            raise PatchError(
                "non-target entries changed: " + ", ".join(non_target_mismatches)
            )

    return {
        "status": "PASS",
        "policy": "maid_model_change_policy_applies_to_dedicated_and_integrated_servers",
        "login_systems_modified": False,
        "source": str(source),
        "source_bytes": source.stat().st_size,
        "source_sha256": source_sha,
        "output": str(output),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "changed_entries": [TARGET_CLASS],
        "original_class_sha256": sha256_bytes(original_class),
        "patched_class_sha256": sha256_bytes(patched_class),
        "non_target_entry_count": len(preserved),
        "non_target_entries_byte_identical": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-sha256", default=LOCKED_BASE_SHA256)
    args = parser.parse_args()
    result = transform(
        args.source,
        args.output,
        expected_sha256=args.expected_sha256,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
