#!/usr/bin/env python3
"""Fail-closed contract validator for the CEI 2.5.1 legacy-Sable build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


OFFICIAL_242_SHA256 = "81F192BB53888E01F87A82EAAC2F261C93715F2221DBCF5D8A8D414F912F75EF"
OFFICIAL_251_SHA256 = "0D27024C0F8E94261689EB198D96003BA5A1697D4478B41E298BCA707CEAE988"
EXPECTED_VERSION = "2.5.1.1-legacy-sable"
EXPECTED_SABLE_RANGE = "[1.2.2,3.0.0)"

ALLOWED_CHANGED_CLASSES = {
    "plus/dragons/createenchantmentindustry/common/processing/forger/BlazeForgerBlockEntity.class",
    "plus/dragons/createenchantmentindustry/common/processing/forger/BlazeForgerInventory.class",
}

SABLE_CLASS_PREFIXES = (
    "plus/dragons/createenchantmentindustry/integration/sable/",
    "plus/dragons/createenchantmentindustry/integration/sable_apotheosis/",
)

REQUIRED_251_ENTRIES = {
    "assets/create_enchantment_industry/blockstates/blaze_composer.json",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/BlazeComposerBlockEntity.class",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/processing/affix/blazeComposer/BlazeComposerInventory.class",
    "plus/dragons/createenchantmentindustry/integration/apotheosis/common/registry/CEIAXDataComponents.class",
    "data/create_enchantment_industry/recipe/sequenced_assembly/brass_affix_template.json",
    "data/create_enchantment_industry/recipe/sequenced_assembly/crystal_affix_template.json",
    "data/create_enchantment_industry/recipe/sequenced_assembly/apotheotic_affix_template.json",
}


class ContractError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def normalized_equal(name: str, left: bytes, right: bytes) -> bool:
    if left == right:
        return True
    if name.endswith((".json", ".mcmeta")):
        try:
            return json.loads(left) == json.loads(right)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
    try:
        return left.decode("utf-8").replace("\r\n", "\n") == right.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        return False


def javap(javap_exe: Path, jar: Path, class_name: str) -> str:
    completed = subprocess.run(
        [str(javap_exe), "-classpath", str(jar), "-c", "-p", class_name],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ContractError(f"javap failed for {class_name}: {completed.stderr}")
    return completed.stdout


def validate(args: argparse.Namespace) -> dict:
    official_242 = args.official_242.resolve()
    official_251 = args.official_251.resolve()
    candidate = args.candidate.resolve()
    javap_exe = args.javap.resolve()

    for path in (official_242, official_251, candidate, javap_exe):
        if not path.is_file() or path.is_symlink():
            raise ContractError(f"missing or linked input: {path}")

    if sha256(official_242) != OFFICIAL_242_SHA256:
        raise ContractError("official CEI 2.4.2 hash mismatch")
    if sha256(official_251) != OFFICIAL_251_SHA256:
        raise ContractError("official CEI 2.5.1 hash mismatch")

    with zipfile.ZipFile(official_242) as z242, zipfile.ZipFile(official_251) as z251, zipfile.ZipFile(candidate) as zc:
        if zc.testzip() is not None:
            raise ContractError("candidate ZIP CRC failure")
        names_242 = set(z242.namelist())
        names_251 = set(z251.namelist())
        names_c = set(zc.namelist())
        if names_c != names_251:
            raise ContractError(
                f"candidate entry set differs from 2.5.1: added={sorted(names_c - names_251)}, missing={sorted(names_251 - names_c)}"
            )
        missing_required = sorted(REQUIRED_251_ENTRIES - names_c)
        if missing_required:
            raise ContractError(f"missing 2.5.1 gameplay entries: {missing_required}")

        changed_classes = {
            name for name in names_c if name.endswith(".class") and zc.read(name) != z251.read(name)
        }
        if changed_classes != ALLOWED_CHANGED_CLASSES:
            raise ContractError(f"unexpected changed class set: {sorted(changed_classes)}")

        substantive_nonclass_changes: list[str] = []
        for name in sorted(names_c):
            if name.endswith(".class") or name == "META-INF/neoforge.mods.toml":
                continue
            if not normalized_equal(name, zc.read(name), z251.read(name)):
                substantive_nonclass_changes.append(name)
        if substantive_nonclass_changes:
            raise ContractError(f"unexpected non-class content changes: {substantive_nonclass_changes}")

        sable_entries = sorted(
            name
            for name in names_c
            if (
                (name.endswith(".class") and name.startswith(SABLE_CLASS_PREFIXES))
                or name == "create_enchantment_industry.sable.mixins.json"
                or name.startswith("data/sable/")
            )
        )
        sable_mismatches: list[str] = []
        for name in sable_entries:
            if name not in names_242 or name not in names_251:
                sable_mismatches.append(name)
                continue
            if name.endswith(".class"):
                equal = zc.read(name) == z242.read(name) == z251.read(name)
            else:
                equal = normalized_equal(name, zc.read(name), z242.read(name)) and normalized_equal(
                    name, zc.read(name), z251.read(name)
                )
            if not equal:
                sable_mismatches.append(name)
        if sable_mismatches:
            raise ContractError(f"Sable compatibility content changed: {sable_mismatches}")

        mods_toml = zc.read("META-INF/neoforge.mods.toml").decode("utf-8")
        if f'version="{EXPECTED_VERSION}"' not in mods_toml:
            raise ContractError("compat version is not embedded in neoforge.mods.toml")
        sable_block = mods_toml.split('modId="sable"', 1)
        if len(sable_block) != 2 or f'versionRange="{EXPECTED_SABLE_RANGE}"' not in sable_block[1].split("[[dependencies", 1)[0]:
            raise ContractError("Sable compatibility range is missing or too broad")

    inventory_bytecode = javap(
        javap_exe,
        candidate,
        "plus.dragons.createenchantmentindustry.common.processing.forger.BlazeForgerInventory",
    )
    block_entity_bytecode = javap(
        javap_exe,
        candidate,
        "plus.dragons.createenchantmentindustry.common.processing.forger.BlazeForgerBlockEntity",
    )
    for required in (
        "Unsupported Blaze Forger inventory size",
        "String Size",
        "String Operation",
        "String Mode",
        "java/lang/IllegalArgumentException",
    ):
        if required not in inventory_bytecode:
            raise ContractError(f"legacy inventory bytecode contract missing: {required}")
    for required in ("String ForgingMode", "String Operation", "String Mode"):
        if required not in block_entity_bytecode:
            raise ContractError(f"legacy mode bytecode contract missing: {required}")

    return {
        "schema": 1,
        "status": "PASS",
        "candidate": {
            "path": str(candidate),
            "bytes": candidate.stat().st_size,
            "sha256": sha256(candidate),
            "version": EXPECTED_VERSION,
        },
        "official_242_sha256": OFFICIAL_242_SHA256,
        "official_251_sha256": OFFICIAL_251_SHA256,
        "entry_count": len(names_c),
        "entry_set_identical_to_251": True,
        "changed_classes": sorted(ALLOWED_CHANGED_CLASSES),
        "other_class_files_identical_to_251": True,
        "other_content_semantically_identical_to_251": True,
        "sable_classes_and_data_equivalent_to_242_and_251": True,
        "legacy_forger_size_4_to_internal_6_guard": True,
        "dual_mode_write_for_242_and_251": True,
        "new_251_gameplay_entries_present": sorted(REQUIRED_251_ENTRIES),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-242", type=Path, required=True)
    parser.add_argument("--official-251", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--javap", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args)
    except (ContractError, OSError, zipfile.BadZipFile) as exc:
        print(f"CEI compatibility contract: FAIL: {exc}")
        return 1
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print("CEI compatibility contract: PASS")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
