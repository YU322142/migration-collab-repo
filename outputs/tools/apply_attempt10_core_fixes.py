#!/usr/bin/env python3
"""Transactionally install the frozen Attempt10 core startup fixes.

The script is intentionally bound to the fresh, never-started Attempt10 roots.
Without --apply it performs a read-only preflight.  With --verify-installed it
only verifies the completed state.  --apply stages every payload, moves the
old JARs into a D:-resident rollback directory, installs the new JARs, and
rolls the whole transaction back if any operation fails.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid


SERVER = Path(r"D:\Trans\migration-audit-work\mechanomania-matched-runtime-attempt10-20260814")
CLIENT = Path(r"D:\Trans\migration-audit-work\mechanomania-matched-client-attempt10-20260814")
BACKUP = Path(r"D:\Trans\migration-audit-work\attempt10-core-fixes-backup-20260814")
REPORT = Path(r"D:\Trans\migration-audit-work\attempt10-core-fixes-apply-20260814.json")
ATTEMPT_MARKER = ".mechanomania-startup-gate-attempt.json"
MCMODSYNC_RE = re.compile(r"mcmodsync", re.I)


ARTIFACTS = {
    "mineastr": {
        "source": Path(
            r"D:\Trans\migration-audit-work\mcmodsync-latest-audit-20260813\mineastr-0.6.26\mineastr-neoforge-1.21.1-0.6.26.jar"
        ),
        "name": "mineastr-neoforge-1.21.1-0.6.26.jar",
        "bytes": 257_982,
        "sha256": "0264D729A3343BE1645B5AFE16C15A7A57C7E89A9405FA67EC80EE06D4A148D8",
    },
    "yacl": {
        "source": Path(
            r"D:\Trans\migration-audit-work\mechanomania-matched-release-v2-20260813\client\mods\yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar"
        ),
        "name": "yet_another_config_lib_v3-3.7.1+1.21.1-neoforge.jar",
        "bytes": 1_111_051,
        "sha256": "673FECBFFAD26BB6D025FB5F60560CF6340E542BDF091D8D66074490515292F3",
    },
    "backport": {
        "source": Path(
            r"D:\Trans\migration-audit-work\content-backport-1.5-cat-serializer-fix-artifacts-20260814\backport-1.5-cat-serializer-fix.1.jar"
        ),
        "name": "backport-1.5-cat-serializer-fix.1.jar",
        "bytes": 15_336_561,
        "sha256": "34291AF9D81B6AEE0780F5F511B2A9594664F36906AED40687DF1C7009E68B1D",
    },
    "hotbath": {
        "source": Path(
            r"D:\Trans\migration-audit-work\hotbath-300-trigger-fix-artifacts-20260814\hotbath-1.21.1-3.0.0-registry-fix.1.jar"
        ),
        "name": "hotbath-1.21.1-3.0.0-registry-fix.1.jar",
        "bytes": 712_893,
        "sha256": "1B53A2B7B2C6476BBAD3ACE344316DA7ABE62854967DE322E9A25CA1D5C7681A",
    },
    "worldedit": {
        "source": Path(
            r"D:\Trans\migration-audit-work\worldedit-738-direction-property-fix-artifacts-20260814\worldedit-mod-7.3.8-direction-property-fix.1.jar"
        ),
        "name": "worldedit-mod-7.3.8-direction-property-fix.1.jar",
        "bytes": 6_264_309,
        "sha256": "8EB5E39AA914EB1B09307B6C004478BD1263655FCCA880580673481EBFEF9283",
    },
    "cei": {
        "source": Path(
            r"D:\Trans\migration-audit-work\cei-242-251-backport-artifacts-20260814\create-enchantment-industry-2.4.2-cei251-backport.1.jar"
        ),
        "name": "create-enchantment-industry-2.4.2-cei251-backport.1.jar",
        "bytes": 1_575_446,
        "sha256": "5B2C3BE95385DBF93000759DB604AB4C71224D7455C437C1B4650D91FAC669EB",
    },
}


OLD = {
    "mineastr": (
        "mineastr-0.6.25.jar",
        258_008,
        "0809500F1993861B1F217D6FED89B68E3094396E853B29E9CF9BDD0C9CE0B787",
    ),
    "backport": (
        "backport-1.5.jar",
        15_301_451,
        "167534C66D5E6C09DCB01152EBD37D18CED5CF6278A9228C094F937886133AF5",
    ),
    "hotbath": (
        "hotbath-1.21.1-3.0.0.jar",
        712_727,
        "93EE276A0BD10D23101AE2EA7982933347D99B4FA9CD8B7E015F813BA6CF11AA",
    ),
    "worldedit": (
        "worldedit-mod-7.3.8.jar",
        6_222_854,
        "5E7752C97876D87411E3760BCC573CC431F43C453722E6959FA7FE54DB1B01CA",
    ),
    "cei": (
        "create-enchantment-industry-2.5.1.jar",
        1_573_096,
        "0D27024C0F8E94261689EB198D96003BA5A1697D4478B41E298BCA707CEAE988",
    ),
}


PLAN = [
    ("server", "mineastr", "mineastr"),
    ("client", "mineastr", "mineastr"),
    ("server", None, "yacl"),
    ("server", "backport", "backport"),
    ("client", "backport", "backport"),
    ("server", "hotbath", "hotbath"),
    ("client", "hotbath", "hotbath"),
    ("server", "worldedit", "worldedit"),
    ("client", "worldedit", "worldedit"),
    ("server", "cei", "cei"),
    ("client", "cei", "cei"),
]


class CoreFixError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def artifact(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise CoreFixError(f"missing or linked file: {path}")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def assert_exact(path: Path, size: int, digest: str) -> dict[str, object]:
    value = artifact(path)
    if value["bytes"] != size or value["sha256"] != digest:
        raise CoreFixError(
            f"artifact mismatch: {path}: {value['bytes']}/{value['sha256']} != {size}/{digest}"
        )
    return value


def root(side: str) -> Path:
    return SERVER if side == "server" else CLIENT


def ensure_root_safety() -> None:
    expected_parent = Path(r"D:\Trans\migration-audit-work").resolve()
    forbidden = Path(r"D:\Trans\20260807").resolve()
    for value in (SERVER, CLIENT):
        resolved = value.resolve()
        if not value.is_dir() or value.is_symlink():
            raise CoreFixError(f"unsafe target root: {value}")
        try:
            resolved.relative_to(expected_parent)
        except ValueError as exc:
            raise CoreFixError(f"target outside D audit root: {value}") from exc
        try:
            resolved.relative_to(forbidden)
        except ValueError:
            pass
        else:
            raise CoreFixError(f"target overlaps authoritative source: {value}")
        if (value / ATTEMPT_MARKER).exists():
            raise CoreFixError(f"target already claimed by startup gate: {value}")
        for runtime_name in ("logs", "crash-reports"):
            if (value / runtime_name).exists():
                raise CoreFixError(f"target already has runtime state: {value / runtime_name}")


def mcmodsync_hits(value: Path) -> list[str]:
    return sorted(
        str(path.relative_to(value))
        for path in value.rglob("*")
        if MCMODSYNC_RE.search(path.name) and "modsync-candidate" not in str(path).lower()
    )


def validate_sources() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for key, spec in ARTIFACTS.items():
        result[key] = assert_exact(spec["source"], spec["bytes"], spec["sha256"])
    return result


def validate_before() -> list[dict[str, object]]:
    ensure_root_safety()
    validate_sources()
    if REPORT.exists() or BACKUP.exists():
        raise CoreFixError("report/backup path must be fresh before --apply")
    if mcmodsync_hits(SERVER) or mcmodsync_hits(CLIENT):
        raise CoreFixError("MCModSync is present in an active Attempt10 path")
    rows: list[dict[str, object]] = []
    for side, old_key, new_key in PLAN:
        mods = root(side) / "mods"
        spec = ARTIFACTS[new_key]
        new_path = mods / spec["name"]
        if new_path.exists():
            raise CoreFixError(f"new target unexpectedly exists: {new_path}")
        old_value = None
        if old_key is not None:
            old_name, old_bytes, old_sha = OLD[old_key]
            old_path = mods / old_name
            old_value = assert_exact(old_path, old_bytes, old_sha)
        rows.append(
            {
                "side": side,
                "old": old_value,
                "new": {
                    "path": str(new_path.resolve()),
                    "bytes": spec["bytes"],
                    "sha256": spec["sha256"],
                    "source": str(spec["source"].resolve()),
                },
            }
        )
    return rows


def validate_installed() -> dict[str, object]:
    ensure_root_safety()
    rows: list[dict[str, object]] = []
    for side, old_key, new_key in PLAN:
        mods = root(side) / "mods"
        spec = ARTIFACTS[new_key]
        new_path = mods / spec["name"]
        new_value = assert_exact(new_path, spec["bytes"], spec["sha256"])
        if old_key is not None:
            old_name = OLD[old_key][0]
            if (mods / old_name).exists():
                raise CoreFixError(f"old JAR remains installed: {mods / old_name}")
        rows.append({"side": side, "artifact": new_value})
    server_jars = list((SERVER / "mods").glob("*.jar"))
    client_jars = list((CLIENT / "mods").glob("*.jar"))
    if len(server_jars) != 236 or len(client_jars) != 247:
        raise CoreFixError(
            f"unexpected mod counts after integration: server={len(server_jars)} client={len(client_jars)}"
        )
    server_mc = mcmodsync_hits(SERVER)
    client_mc = mcmodsync_hits(CLIENT)
    if server_mc or client_mc:
        raise CoreFixError(f"MCModSync active-path match: server={server_mc} client={client_mc}")
    return {
        "status": "PASS_INSTALLED",
        "operations": rows,
        "counts": {"server_jars": 236, "client_jars": 247},
        "mcmodsync": {"server_hits": [], "client_hits": [], "globally_disabled": True},
    }


def apply_transaction(before: list[dict[str, object]]) -> dict[str, object]:
    token = uuid.uuid4().hex
    staged: list[tuple[Path, Path]] = []
    completed: list[tuple[Path | None, Path, Path | None]] = []
    BACKUP.mkdir(parents=True, exist_ok=False)
    try:
        for side, _old_key, new_key in PLAN:
            spec = ARTIFACTS[new_key]
            destination = root(side) / "mods" / spec["name"]
            stage = destination.with_name(f".{destination.name}.attempt10-core-stage-{token}")
            shutil.copy2(spec["source"], stage)
            assert_exact(stage, spec["bytes"], spec["sha256"])
            staged.append((stage, destination))

        for index, ((side, old_key, _new_key), (stage, destination)) in enumerate(zip(PLAN, staged)):
            backup_path: Path | None = None
            old_path: Path | None = None
            if old_key is not None:
                old_path = root(side) / "mods" / OLD[old_key][0]
                backup_path = BACKUP / side / old_path.name
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(old_path, backup_path)
            os.replace(stage, destination)
            completed.append((old_path, destination, backup_path))

        installed = validate_installed()
    except Exception:
        for old_path, destination, backup_path in reversed(completed):
            if destination.exists():
                destination.unlink()
            if old_path is not None and backup_path is not None and backup_path.exists():
                os.replace(backup_path, old_path)
        for stage, _destination in staged:
            if stage.exists():
                stage.unlink()
        if BACKUP.exists():
            shutil.rmtree(BACKUP)
        raise

    return {
        "schema": 1,
        "status": "PASS_APPLIED",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "targets": {"server": str(SERVER), "client": str(CLIENT)},
        "before": before,
        "installed": installed,
        "backup": str(BACKUP),
        "policy": {
            "mcmodsync_globally_disabled": True,
            "server_memory_mb": 4096,
            "client_memory_mb": 4096,
            "java_started": False,
            "minecraft_started": False,
            "world_modified": False,
        },
    }


def write_report(value: dict[str, object]) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_name(REPORT.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, REPORT)


def main() -> int:
    global SERVER, CLIENT, BACKUP, REPORT
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-root", type=Path, default=SERVER)
    parser.add_argument("--client-root", type=Path, default=CLIENT)
    parser.add_argument("--backup-root", type=Path, default=BACKUP)
    parser.add_argument("--report", type=Path, default=REPORT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify-installed", action="store_true")
    args = parser.parse_args()
    SERVER = args.server_root.resolve()
    CLIENT = args.client_root.resolve()
    BACKUP = args.backup_root.resolve()
    REPORT = args.report.resolve()
    try:
        if args.verify_installed:
            result = validate_installed()
        else:
            before = validate_before()
            result = {"status": "PREFLIGHT_PASS", "operations": before}
            if args.apply:
                result = apply_transaction(before)
                write_report(result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
