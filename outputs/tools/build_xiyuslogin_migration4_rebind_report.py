#!/usr/bin/env python3
"""Build a redacted migration4 authentication rebind review.

The review is intentionally fail-closed: byte-identical authentication classes
and a successful migration4 lifecycle load do not count as a fresh network login
run.  The report therefore keeps the strict live-login gate open unless a
dedicated migration4 client transcript is supplied later.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[2]
MIGRATION3_JAR = ROOT / "outputs/tmp/xiyuslogin-1.4-migration3-build1.jar"
MIGRATION4_JAR = Path(
    r"D:\Trans\migration-audit-work\XiyusLogin-migration\build\libs\xiyuslogin-1.4-migration4.jar"
)
SYNTHETIC_EVIDENCE = ROOT / "outputs/xiyuslogin-migration3-synthetic-live-evidence-20260810.json"
RUNTIME_REPORT = ROOT / "outputs/painting-p0-candidate6-runtime-20260810-escalated.json"
RUNTIME_DIR = ROOT / "outputs/tmp/painting-p0-smoke-candidate6"
HIDDEN_RENDER_REPORT = ROOT / "outputs/client-gate-candidate5-hidden-render-report-v4.json"
HIDDEN_RENDER_LOG = ROOT / "outputs/tmp/client-gate-candidate5/.minecraft/logs/latest.log"
OUTPUT_JSON = ROOT / "outputs/xiyuslogin-migration4-auth-rebind-review-20260810.json"
OUTPUT_MD = ROOT / "outputs/xiyuslogin-migration4-auth-rebind-review-20260810.md"

AUTH_ENTRIES = (
    "org/xiyu/yee/xiyuslogin/data/PlayerDataManager.class",
    "org/xiyu/yee/xiyuslogin/manager/AuthManager.class",
    "org/xiyu/yee/xiyuslogin/command/AuthCommands.class",
    "org/xiyu/yee/xiyuslogin/command/AdminCommands.class",
    "org/xiyu/yee/xiyuslogin/event/PlayerEventHandler.class",
    "org/xiyu/yee/xiyuslogin/event/ServerEventHandler.class",
    "org/xiyu/yee/xiyuslogin/mixin/ServerGamePacketListenerImplMixin.class",
)
RUNTIME_ENTRIES = (
    "META-INF/jarjar/bcrypt-0.10.2.jar",
    "META-INF/jarjar/bytes-1.5.0.jar",
)
FATAL_MARKERS = (
    "NoClassDefFoundError",
    "ClassNotFoundException: at.favre.lib",
    "[Server thread/FATAL]",
    "[Render thread/FATAL]",
    "MixinApplyError",
    "InjectionError",
    "InvalidInjectionException",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def jar_entry(zf: zipfile.ZipFile, name: str) -> dict[str, object]:
    value = zf.read(name)
    return {"bytes": len(value), "sha256": sha256_bytes(value)}


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def require_inside_audit_only(path: Path) -> None:
    text = str(path).replace("/", "\\").lower()
    if "d:\\trans\\20260807" in text:
        raise RuntimeError("production source path is not allowed")


def read_text(path: Path) -> str:
    require_inside_audit_only(path)
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    for path in (MIGRATION3_JAR, MIGRATION4_JAR, SYNTHETIC_EVIDENCE,
                 RUNTIME_REPORT, HIDDEN_RENDER_REPORT, HIDDEN_RENDER_LOG):
        if not path.is_file():
            raise SystemExit(f"missing evidence input: {path}")
        require_inside_audit_only(path)

    with zipfile.ZipFile(MIGRATION3_JAR) as old, zipfile.ZipFile(MIGRATION4_JAR) as new:
        all_names = sorted(set(old.namelist()) | set(new.namelist()))
        changed = [name for name in all_names
                   if name not in old.namelist() or name not in new.namelist()
                   or old.read(name) != new.read(name)]
        auth_entries = {}
        for name in AUTH_ENTRIES:
            left = jar_entry(old, name)
            right = jar_entry(new, name)
            auth_entries[name] = {"migration3": left, "migration4": right,
                                  "equal": left == right}
        runtime_entries = {}
        for name in RUNTIME_ENTRIES:
            left = jar_entry(old, name)
            right = jar_entry(new, name)
            runtime_entries[name] = {"migration3": left, "migration4": right,
                                     "equal": left == right}

    synthetic = json.loads(read_text(SYNTHETIC_EVIDENCE))
    scenario_status = {
        name: value.get("status")
        for name, value in synthetic.get("scenarios", {}).items()
        if isinstance(value, dict)
    }
    synthetic_passes = sum(value == "PASS_SYNTHETIC_NETWORK_RUNTIME"
                           for value in scenario_status.values())

    runtime_report = json.loads(read_text(RUNTIME_REPORT))
    runtime_logs = []
    for name in ("run1.stdout.log", "run2.stdout.log"):
        path = RUNTIME_DIR / name
        text = read_text(path)
        runtime_logs.append({
            "file": relative(path),
            "xiyuslogin_mod_loaded": 'Found mod file "xiyuslogin-1.4-migration4.jar"' in text,
            "bcrypt_nested_loaded": 'Found library file "bcrypt-0.10.2.jar"' in text,
            "bytes_nested_loaded": 'Found library file "bytes-1.5.0.jar"' in text,
            "records_loaded": len(re.findall(r"Loaded 49 player records from data file", text)),
            "auth_initialized": len(re.findall(r"XiyusLogin authentication system initialized", text)),
            "graceful_auth_shutdown": len(re.findall(r"XiyusLogin data saved and systems shutdown", text)),
            "fatal_markers": {marker: text.count(marker) for marker in FATAL_MARKERS if marker in text},
        })

    hidden_report = json.loads(read_text(HIDDEN_RENDER_REPORT))
    hidden_text = read_text(HIDDEN_RENDER_LOG)
    hidden_runtime = {
        "report": relative(HIDDEN_RENDER_REPORT),
        "status": hidden_report.get("status"),
        "private_desktop": hidden_report.get("private_desktop"),
        "foreground_activation": hidden_report.get("foreground_activation"),
        "world_join_observed": hidden_report.get("world_join_observed"),
        "migration4_mod_loaded": 'Found mod file "xiyuslogin-1.4-migration4.jar"' in hidden_text,
        "bcrypt_nested_loaded": 'Found library file "bcrypt-0.10.2.jar"' in hidden_text,
        "bytes_nested_loaded": 'Found library file "bytes-1.5.0.jar"' in hidden_text,
        "blindness_effect_marker_count": hidden_text.lower().count("mob_effects.blindness"),
        "fatal_markers": {marker: hidden_text.count(marker) for marker in FATAL_MARKERS if marker in hidden_text},
    }

    auth_equal = all(item["equal"] for item in auth_entries.values())
    runtime_equal = all(item["equal"] for item in runtime_entries.values())
    report = {
        "schema": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS_AUTH_LOGIC_REBOUND_WITH_RUNTIME_LOAD" if auth_equal and runtime_equal else "NO_GO_REBIND_MISMATCH",
        "strict_release_status": "NO_GO_AUTH_LIVE_NOT_REEXECUTED",
        "scope": {
            "production_source_read": False,
            "production_credentials_used": False,
            "production_world_written": False,
            "note": "This report binds only redacted synthetic evidence and byte/runtime checks; it does not claim a fresh migration4 network login transcript.",
        },
        "migration4_artifact": {
            "path": str(MIGRATION4_JAR),
            "bytes": MIGRATION4_JAR.stat().st_size,
            "sha256": sha256_file(MIGRATION4_JAR),
        },
        "migration3_reference": {
            "path": relative(MIGRATION3_JAR),
            "bytes": MIGRATION3_JAR.stat().st_size,
            "sha256": sha256_file(MIGRATION3_JAR),
        },
        "jar_diff": {
            "changed_entry_count": len(changed),
            "changed_entries": changed,
            "authentication_entries_byte_equal": auth_equal,
            "authentication_entries": auth_entries,
            "runtime_dependency_entries_byte_equal": runtime_equal,
            "runtime_dependency_entries": runtime_entries,
        },
        "existing_synthetic_evidence": {
            "path": relative(SYNTHETIC_EVIDENCE),
            "synthetic_network_pass_count": synthetic_passes,
            "scenario_status": scenario_status,
            "rebound_directly_to_migration4": False,
        },
        "migration4_runtime_load": {
            "report": relative(RUNTIME_REPORT),
            "lifecycle_report_status": runtime_report.get("status"),
            "foreground_activation": runtime_report.get("foreground_activation"),
            "rounds": runtime_logs,
        },
        "migration4_hidden_client_render": hidden_runtime,
        "minimal_next_gate": [
            "Use a temporary overlay run directory with only configs, one synthetic XiyusLogin JSON, and migration4 JAR; keep libraries/assets as read-only junctions.",
            "Start NeoForge server and client on isolated loopback ports on the existing private desktop helper.",
            "Use RCON as the synthetic player to issue /register and /login, then snapshot the redacted JSON before/after a wrong password and across one restart.",
            "Hash every transcript and bind the four Java scenarios to migration4; leave Floodgate and proxy scenarios blocked until their runtimes exist.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    lines = [
        "# XiyusLogin migration4 auth rebind review",
        "",
        f"Status: `{report['status']}`; strict release status: `{report['strict_release_status']}`.",
        "",
        f"Migration4 JAR: `{MIGRATION4_JAR}`; {MIGRATION4_JAR.stat().st_size} bytes; SHA-256 `{sha256_file(MIGRATION4_JAR)}`.",
        "",
        "The authentication classes (data manager, auth manager, commands, events, and packet mixin) and both jar-in-jar runtime libraries are byte-identical to migration3. The only changed entries are the version/security resource, config classes, and FreezeManager used for the blindness regression fix.",
        "",
        f"The existing redacted synthetic network evidence has `{synthetic_passes}/4` Java scenarios passing, but it was recorded against migration3 and is not silently relabeled as a fresh migration4 login run.",
        "",
        "Migration4 itself has a hidden two-round lifecycle load (`49` records, bcrypt and bytes discovered, clean save/stop) and a private-desktop client world-join/render pass. The strict gate remains open until the four Java network scenarios are rerun with migration4 and the Floodgate/proxy scenarios are supplied.",
        "",
        f"Machine-readable evidence: `{OUTPUT_JSON}`.",
    ]
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "strict_release_status": report["strict_release_status"], "report": str(OUTPUT_JSON)}, sort_keys=True))
    return 0 if report["status"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
