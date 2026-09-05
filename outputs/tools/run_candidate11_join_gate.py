#!/usr/bin/env python3
"""Run the Candidate11 client's two-round private-desktop join gate.

The runner is deliberately limited to a disposable fresh disposable Candidate11 server
and the isolated Candidate11 client rooted under this workspace. It never
accepts the historical source backup as a runtime target. Every process is
hidden, every network listener is loopback-only, and a failed run still emits a
NO_GO report after cleanup.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import time
from typing import Any, Callable
import zipfile
import zlib

import nbtlib


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "outputs" / "tools"
OUTPUTS = ROOT / "outputs"
WORKSPACE_CLIENT_ROOT = OUTPUTS / "tmp"
FORBIDDEN_SOURCE = Path(r"<TRANS_ROOT>\20260807")
DEFAULT_JAVA = Path(r"C:\Program Files\Java\jdk-21.0.10\bin\java.exe")
DEFAULT_POWERSHELL = Path(
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
DEFAULT_PRIVATE_HELPER = TOOLS / "run_private_desktop_client_session.ps1"
DEFAULT_CLIENT_LAUNCHER = TOOLS / "launch_neoforge_client_isolated.ps1"
SYNTHETIC_USERNAME = "Candidate11Gate"
SYNTHETIC_UUID = "00000000-0000-0000-0000-000000001101"
CANDIDATE11_RELEASE_ROOT = Path(
    r"<AUDIT_ROOT>\final-mod-bundles-candidate11-20260811"
)
CANDIDATE11_READY = CANDIDATE11_RELEASE_ROOT / "READY.json"
CANDIDATE11_RELEASE_LOCK = CANDIDATE11_RELEASE_ROOT / "release-lock.json"
CANDIDATE11_SERVER_MANIFEST = CANDIDATE11_RELEASE_ROOT / "manifests" / "server.json"
CANDIDATE11_CLIENT_MANIFEST = CANDIDATE11_RELEASE_ROOT / "manifests" / "client.json"
CANDIDATE11_FULL_AUDIT = OUTPUTS / "candidate11-bundle-full-audit-20260811.json"
CANDIDATE11_READY_SHA256 = (
    "613025D9852956113DD5DB7653C37BD0DF3C36F93818AB79B3681338B03BA05E"
)
CANDIDATE11_SERVER_MANIFEST_SHA256 = (
    "66BA1B734E9A8BE2728A2FC9FCF77A8E49AAAEEFBEC3D0069EA63D0D841DAD3C"
)
CANDIDATE11_CLIENT_MANIFEST_SHA256 = (
    "1CECCAE36F9DDB47DDC9D882603C1A0D0AB54E073FCF21D86C34270D61B1C30D"
)
CANDIDATE11_FULL_AUDIT_SHA256 = (
    "C3C96146A488DDBC5054F3A7B721AE9EA8031C83615B817D07FA453981D40A4F"
)
CANDIDATE11_PUBLISHED_SERVER_BUNDLE = {
    "files": 52,
    "bytes": 164653932,
    "bundle_sha256": "CCFDA18205DF3C6D012B2C61890309CDBC3DAC016E698BB23DAE6DEB8DC2271A",
}
CANDIDATE11_RUNTIME_SERVER_BUNDLE = {
    "files": 52,
    "bytes": 164649980,
    "bundle_sha256": "2A4714F177A8FE7CE199E5143AAF619050BF161A2C946053B6A39DA318FBB18C",
}
CANDIDATE11_CLIENT_BUNDLE = {
    "files": 52,
    "bytes": 145847838,
    "bundle_sha256": "CABFD4F8AAC31A2A6910E4963442E683690CC4D2F2F60E7B26984D63E6DAE95B",
}
CANDIDATE11_BUNDLE_PAIR_SHA256 = (
    "FC008BD9ED9ABF5FF23B61E40ADDCAC46986E22147EB2437324C48E2E9242E56"
)
CANDIDATE11_CLIENT_ROOT = OUTPUTS / "tmp" / "client-gate-candidate11" / ".minecraft"
# The detached e5 pipeline names its freshly assembled target by pipeline
# generation (candidate8n), not by the mod-bundle generation (candidate11).
# Bind this exact path so the gate can use the verified 9GB target without
# renaming or copying it merely to satisfy a substring check.
PIPELINE_PREPARED_TARGET = Path(
    r"<AUDIT_ROOT>\manual-test-candidate8n-20260811"
)
CANDIDATE11_CLIENT_PREPARE_REPORT = OUTPUTS / "candidate11-client-root-prepare-20260811.json"
CC_GUARD_FILE = "cctweaked-startup-shutdown-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar"
CC_GUARD_SHA256 = "6744626E2B43643E9F28C9159FABD7A6A53CDCDEB83AE8252C266F7E987F84F7"
CREATE_GUARD_FILE = "create-chute-unload-guard-1.0.0+neoforge.1.21.1-equivalence.1.jar"
CREATE_GUARD_SHA256 = "AC51AEFDDA8437D777B5C8B3E285E9036676D854F7958C6B882807C15BE0910A"
CC_COMPUTER_ID = 11
CC_COMPUTER_POSITION = (1403, 67, -5088)
CC_COMPUTER_BLOCK_ENTITY_ID = "computercraft:computer_normal"
ATTEMPT_MARKER_NAME = ".candidate11-join-gate-attempt.json"
REQUIRED_LOCAL_RESOURCE_PACK_SOURCE = Path(
    "<INSTANCE_ROOT>/\u52a8\u9759\u4ea4\u6620-1.4.2-PCL2/.minecraft/versions/"
    "\u52a8\u9759\u4ea4\u6620\u5ba2\u6237\u7aef/resourcepacks/"
    "\u4e16\u754c\u6307\u5b9a\u8d44\u6e90\u5305\u55b5.zip"
)
REQUIRED_LOCAL_RESOURCE_PACK_NAME = (
    "\u4e16\u754c\u6307\u5b9a\u8d44\u6e90\u5305\u55b5.zip"
)
REQUIRED_LOCAL_RESOURCE_PACK_SHA256 = (
    "BF88450FF0EED414657DC75CC1F0FD6689109A654DEEC8CF5306A13C3900CCCC"
)
REQUIRED_LOCAL_RESOURCE_PACK_BYTES = 110867309
REQUIRED_LOCAL_RESOURCE_PACK_ZIP_ENTRIES = 15986
MINECRAFT_1_21_1_RESOURCE_PACK_FORMAT = 34
DONE_RE = re.compile(r'Done \([^)]+\)! For help, type "help"')
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


RISK_SITES = (
    {"name": "elevator_last_exception", "x": -159, "y": 65, "z": -42},
    {"name": "millstone_primary", "x": -165, "y": 65, "z": -92},
    {"name": "millstone_secondary", "x": 1414, "y": 66, "z": -5102},
    {"name": "cei_fractional_experience", "x": 27319, "y": 70, "z": -12919},
)

CRITICAL_WORLD_FILES = (
    "level.dat",
    "region/r.-1.-1.mca",
    "region/r.2.-10.mca",
    "region/r.53.-26.mca",
)

# These are intentionally narrow enough to avoid turning known harmless mod
# warnings into blockers while covering every failure seen in candidate7.
STRICT_COMMON_PATTERNS = (
    ("WHITELIST_REJECTION", re.compile(r"not white[- ]listed|not whitelisted", re.I)),
    ("CRASH_REPORT", re.compile(r"crash report|reported exception", re.I)),
    ("THREAD_FATAL", re.compile(r"\[(?:server|render) thread/FATAL\]", re.I)),
    (
        "THREAD_ERROR_EXCEPTION",
        re.compile(r"\[(?:server|render) thread/ERROR\].*(?:exception|crash|codec)", re.I),
    ),
    ("MIXIN_FATAL", re.compile(r"MixinApplyError|InjectionError|InvalidInjectionException")),
    ("OUT_OF_MEMORY", re.compile(r"OutOfMemoryError", re.I)),
    (
        "FLUID_MAX_CAPACITY_COMPONENT",
        re.compile(r"No component with type:\s*['\"]?create:fluid_max_capacity", re.I),
    ),
    ("UNKNOWN_CREATE_MILK", re.compile(r"Unknown registry key[^\r\n]*create:milk", re.I)),
    (
        "CC_COMPUTER_STARTUP_TIMEOUT",
        re.compile(r"Terminating computer #11 due to timeout|ABORT_WITH_TIMEOUT", re.I),
    ),
    (
        "CC_COMPUTER_STOP_DEADLINE",
        re.compile(r"Failed to stop computers under deadline", re.I),
    ),
    ("INVALID_FLUID", re.compile(r"Tried to load invalid fluid", re.I)),
    ("INVALID_ITEM_LOAD", re.compile(r"Tried to load invalid item", re.I)),
    ("INVALID_STATISTIC", re.compile(r"Invalid statistic in .*Don't know what ", re.I)),
    (
        "BLOCK_ENTITY_DATA_LOAD_FAILURE",
        re.compile(r"Failed to load data for block entity", re.I),
    ),
    ("SKIPPED_BLOCK_ENTITY", re.compile(r"Skipping BlockEntity", re.I)),
    ("COMPONENT_LOAD_FAILURE", re.compile(r"Failed to load components", re.I)),
    ("FLUIDSTACK_FAILURE", re.compile(r"(?:error|exception|failed|invalid)[^\r\n]*FluidStack|FluidStack[^\r\n]*(?:error|exception|failed|invalid)", re.I)),
    ("CONTRAPTION_BOUNDS", re.compile(r"contraption\.bounds", re.I)),
    ("ASSEMBLY_EXCEPTION", re.compile(r"AssemblyException", re.I)),
    ("ENTITY_LOAD_EXCEPTION", re.compile(r"Exception loading entity", re.I)),
    (
        "SKIPPED_CREATE_ENTITY",
        re.compile(r"Skipping Entity with id create:(?:stationary_contraption|carriage_contraption)", re.I),
    ),
    (
        "MILLSTONE_CODEC_FAILURE",
        re.compile(
            r"(?:kaleidoscope_cookery:millstone[^\r\n]*(?:codec|uuid|exception|failed)|"
            r"(?:codec|uuid|exception|failed)[^\r\n]*kaleidoscope_cookery:millstone)",
            re.I,
        ),
    ),
    (
        "ELEVATOR_CODEC_FAILURE",
        re.compile(
            r"(?:create:elevator_pulley[^\r\n]*(?:codec|LastException|exception|failed)|"
            r"(?:codec|LastException|exception|failed)[^\r\n]*create:elevator_pulley)",
            re.I,
        ),
    ),
)

STRICT_CLIENT_PATTERNS = (
    ("CLIENT_RENDER_FATAL", re.compile(r"\[Render thread/FATAL\]", re.I)),
    ("CLIENT_RENDER_ERROR", re.compile(r"\[Render thread/ERROR\]", re.I)),
    ("CLIENT_RENDER_EXCEPTION", re.compile(r'Exception in thread "Render thread"', re.I)),
    ("CLIENT_GAME_CRASH", re.compile(r"Minecraft has crashed|Game crashed", re.I)),
    (
        "CLIENT_RESOURCE_PACK_REMOVED",
        re.compile(r"Removed resource pack .* from options because it doesn't seem to exist", re.I),
    ),
    (
        "CLIENT_RESOURCE_PACK_FAILURE",
        re.compile(
            r"(?:failed to (?:load|apply|download)|could(?: not|n't) load|invalid)"
            r"[^\r\n]*resource pack|resource pack[^\r\n]*(?:failed|error)",
            re.I,
        ),
    ),
    (
        "CLIENT_REMOTE_RESOURCE_PACK_ACTIVITY",
        re.compile(
            r"(?:download(?:ing|ed)|apply(?:ing|ied))[^\r\n]*server resource pack|"
            r"server resource pack[^\r\n]*(?:download(?:ing|ed)|apply(?:ing|ied))",
            re.I,
        ),
    ),
)

# No Server-thread ERROR is currently accepted. Future exceptions must name an
# exact, reviewed line pattern here instead of weakening the general gate.
SERVER_THREAD_ERROR_ALLOWLIST: tuple[re.Pattern[str], ...] = ()
SERVER_THREAD_ERROR_RE = re.compile(r"^.*\[Server thread/ERROR\].*$", re.I | re.M)

# Minecraft rewrites server.properties through java.util.Properties on the
# first target startup. That changes comments, ordering and escaped values,
# and may add explicit defaults. Bind the security- and pack-sensitive values
# semantically instead of treating that deterministic formatting rewrite as a
# mutation.
DISPOSABLE_SERVER_PROPERTY_KEYS = (
    "server-ip",
    "server-port",
    "online-mode",
    "white-list",
    "enforce-whitelist",
    "enable-rcon",
    "rcon.port",
    "rcon.password",
    "level-name",
    "resource-pack",
    "resource-pack-id",
    "resource-pack-prompt",
    "resource-pack-sha1",
    "require-resource-pack",
)

COMMAND_FAILURE_RE = re.compile(
    r"Unknown or incomplete command|Incorrect argument|No player was found|"
    r"An unexpected error occurred|Could not|Failed to execute",
    re.I,
)


class GateError(RuntimeError):
    """A fail-closed gate failure."""


def client_state_failure_message(value: dict[str, Any]) -> str:
    """Render the helper's durable JVM diagnostics without losing file paths."""
    error = str(value.get("error") or "private client failed")
    exit_code = value.get("exit_code")
    code_text = "unavailable" if exit_code is None else str(exit_code)
    stdout = str(value.get("stdout") or "unavailable")
    stderr = str(value.get("stderr") or "unavailable")
    return (
        f"{error} [exit_code={code_text}; stdout={stdout}; stderr={stderr}]"
    )


def valid_startup_evidence(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("kind") in {"stdout_marker", "latest_log_update"}
        and isinstance(value.get("marker"), str)
        and bool(value.get("marker"))
        and isinstance(value.get("path"), str)
        and bool(value.get("path"))
    )


def valid_clean_private_client_state(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("status") == "STOPPED"
        and value.get("private_desktop") is True
        and value.get("foreground_activation") is False
        and value.get("processes_closed") is True
        and valid_startup_evidence(value.get("startup_evidence"))
    )


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest().upper()


def atomic_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)
    digest = sha256_file(path)
    sidecar = path.with_name(path.name + ".sha256")
    sidecar_tmp = sidecar.with_name(sidecar.name + ".tmp")
    sidecar_tmp.write_text(f"{digest} *{path.name}\n", encoding="ascii")
    os.replace(sidecar_tmp, sidecar)
    return digest


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def forbidden_source_path(path: Path) -> bool:
    return is_within(path, FORBIDDEN_SOURCE)


def validate_paths(target: Path, client_root: Path, report: Path) -> None:
    target_resolved = target.resolve()
    world_resolved = (target / "world").resolve()
    if forbidden_source_path(target_resolved) or forbidden_source_path(world_resolved):
        raise GateError("historical source backup is forbidden as a runtime target")

    workspace_server = is_within(target_resolved, WORKSPACE_CLIENT_ROOT)
    external_candidate11 = (
        "migration-audit-work" in {part.lower() for part in target_resolved.parts}
        and "candidate11" in target_resolved.name.lower()
    )
    external_pipeline_target = target_resolved == PIPELINE_PREPARED_TARGET.resolve()
    if not workspace_server and not external_candidate11 and not external_pipeline_target:
        raise GateError(
            "target must be outputs/tmp, the locked pipeline target, or a disposable candidate11 under migration-audit-work"
        )
    if client_root.resolve() != CANDIDATE11_CLIENT_ROOT.resolve():
        raise GateError(
            f"client root must be the fresh locked Candidate11 root: {CANDIDATE11_CLIENT_ROOT}"
        )
    if not client_root.is_dir() or client_root.is_symlink():
        raise GateError("Candidate11 client root is missing, linked, or not a directory")
    if not is_within(report, OUTPUTS):
        raise GateError("report must be written under this workspace's outputs")


def read_properties(path: Path) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise GateError(f"properties file is missing or linked: {path}")
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in result:
            raise GateError(f"duplicate server property: {key}")
        result[key] = value.strip()
    return result


def java_property_unescape(value: str) -> str:
    """Decode the escapes emitted by java.util.Properties.store()."""
    output: list[str] = []
    index = 0
    escapes = {"t": "\t", "n": "\n", "r": "\r", "f": "\f"}
    while index < len(value):
        char = value[index]
        if char != "\\":
            output.append(char)
            index += 1
            continue
        index += 1
        if index >= len(value):
            output.append("\\")
            break
        escaped = value[index]
        if escaped == "u":
            digits = value[index + 1 : index + 5]
            if len(digits) != 4 or not re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                raise GateError("server.properties contains a malformed unicode escape")
            output.append(chr(int(digits, 16)))
            index += 5
            continue
        output.append(escapes.get(escaped, escaped))
        index += 1
    return "".join(output)


def disposable_server_properties_fingerprint(
    properties: dict[str, str],
) -> dict[str, str | None]:
    return {
        key: java_property_unescape(properties[key]) if key in properties else None
        for key in DISPOSABLE_SERVER_PROPERTY_KEYS
    }


def candidate11_servers_dat_payload(server_address: str) -> bytes:
    """Build the complete one-entry NBT server list for the disposable client."""

    def nbt_string(value: str) -> bytes:
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise GateError("NBT string exceeds the unsigned-short length limit")
        return struct.pack(">H", len(encoded)) + encoded

    def named_tag(tag_id: int, name: str, payload: bytes) -> bytes:
        return bytes((tag_id,)) + nbt_string(name) + payload

    server = b"".join(
        (
            named_tag(8, "name", nbt_string("Minecraft Server")),
            named_tag(8, "ip", nbt_string(server_address)),
            named_tag(1, "acceptTextures", b"\x00"),
            named_tag(1, "hidden", b"\x01"),
            b"\x00",  # End the server compound.
        )
    )
    servers = b"\x0a" + struct.pack(">i", 1) + server
    return b"\x0a\x00\x00" + named_tag(9, "servers", servers) + b"\x00"


def configure_disposable_resource_pack_rejection(
    client_root: Path,
    server_port: int,
    properties: dict[str, str],
    properties_path: Path,
) -> dict[str, Any]:
    """Preselect DECLINED for an optional pack on the hidden smoke client."""
    required_text = properties.get("require-resource-pack", "false").strip().lower()
    if required_text not in {"true", "false"}:
        raise GateError(f"invalid require-resource-pack value: {required_text!r}")
    if required_text == "true":
        raise GateError(
            "Candidate11 policy rejects resource packs, but the server pack is required"
        )
    if not client_root.is_dir() or client_root.is_symlink():
        raise GateError(f"client root is missing or linked: {client_root}")

    properties_before = sha256_file(properties_path)
    path = client_root / "servers.dat"
    before: dict[str, Any] | None = None
    if path.exists():
        before = file_artifact(path)

    server_address = f"127.0.0.1:{server_port}"
    expected = candidate11_servers_dat_payload(server_address)
    temporary = path.with_name(f"{path.name}.candidate11.{os.getpid()}.tmp")
    if temporary.exists():
        raise GateError(f"refusing to reuse temporary servers.dat: {temporary}")
    try:
        temporary.write_bytes(expected)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

    actual = path.read_bytes()
    if actual != expected:
        raise GateError("servers.dat resource-pack rejection failed byte validation")
    properties_after = sha256_file(properties_path)
    if properties_after != properties_before:
        raise GateError("server.properties changed while configuring client pack policy")
    after = file_artifact(path)
    return {
        "policy": "reject_optional",
        "client_response": "DECLINED",
        "server_address": server_address,
        "resource_pack_configured": bool(properties.get("resource-pack", "").strip()),
        "require_resource_pack": False,
        "accept_textures": False,
        "servers_dat": {
            "before": before,
            "after": after,
            "changed": before is None or before["sha256"] != after["sha256"],
            "exact_payload_validated": True,
        },
        "server_properties": {
            "path": str(properties_path.resolve()),
            "before_sha256": properties_before,
            "after_sha256": properties_after,
            "semantic_fingerprint": disposable_server_properties_fingerprint(
                properties
            ),
            "unchanged": True,
        },
    }


def validate_disposable_resource_pack_rejection(
    client_root: Path,
    server_port: int,
    properties_path: Path,
    *,
    expected_properties_sha256: str,
    expected_properties_fingerprint: dict[str, str | None],
) -> dict[str, Any]:
    """Prove the optional server pack remains declined after Java normalization."""
    if not client_root.is_dir() or client_root.is_symlink():
        raise GateError(f"client root is missing or linked: {client_root}")
    properties = read_properties(properties_path)
    required_text = properties.get("require-resource-pack", "false").strip().lower()
    if required_text != "false":
        raise GateError("server resource-pack policy is no longer optional")
    properties_sha256 = sha256_file(properties_path)
    semantic_fingerprint = disposable_server_properties_fingerprint(properties)
    if semantic_fingerprint != expected_properties_fingerprint:
        changed = {
            key: {
                "expected": expected_properties_fingerprint.get(key),
                "actual": semantic_fingerprint.get(key),
            }
            for key in DISPOSABLE_SERVER_PROPERTY_KEYS
            if semantic_fingerprint.get(key) != expected_properties_fingerprint.get(key)
        }
        raise GateError(
            f"server.properties protected values changed after resource-pack setup: {changed}"
        )

    path = client_root / "servers.dat"
    artifact = file_artifact(path)
    expected = candidate11_servers_dat_payload(f"127.0.0.1:{server_port}")
    if path.read_bytes() != expected:
        raise GateError("servers.dat no longer proves acceptTextures=false")
    return {
        "policy": "reject_optional",
        "client_response": "DECLINED",
        "accept_textures": False,
        "require_resource_pack": False,
        "servers_dat": artifact,
        "exact_payload_validated": True,
        "server_properties": {
            "path": str(properties_path.resolve()),
            "expected_raw_sha256": expected_properties_sha256,
            "raw_sha256": properties_sha256,
            "raw_normalized_by_server": properties_sha256
            != expected_properties_sha256,
            "semantic_fingerprint": semantic_fingerprint,
            "semantic_unchanged": True,
        },
    }


def resource_packs_option(path: Path) -> list[str]:
    if not path.is_file() or path.is_symlink():
        raise GateError(f"options file is missing or linked: {path}")
    prefix = "resourcePacks:"
    values = [
        raw[len(prefix) :]
        for raw in path.read_text(encoding="utf-8", errors="strict").splitlines()
        if raw.startswith(prefix)
    ]
    if len(values) != 1:
        raise GateError(f"options.txt must have exactly one {prefix} entry")
    try:
        parsed = json.loads(values[0])
    except json.JSONDecodeError as exc:
        raise GateError("options.txt resourcePacks is not valid JSON") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise GateError("options.txt resourcePacks is not a string list")
    return parsed


def decode_pack_mcmeta(raw: bytes) -> tuple[dict[str, Any], str]:
    failures: list[str] = []
    encodings = ("utf-8-sig", "gbk") if raw.startswith(b"\xef\xbb\xbf") else ("utf-8", "gbk")
    for encoding in encodings:
        try:
            value = json.loads(raw.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            failures.append(f"{encoding}: {exc}")
            continue
        if not isinstance(value, dict) or not isinstance(value.get("pack"), dict):
            raise GateError("pack.mcmeta has no object-valued pack section")
        return value, encoding
    raise GateError(f"pack.mcmeta is not valid JSON in a supported encoding: {failures}")


def root_pack_mcmeta(path: Path) -> tuple[bytes, dict[str, Any], str]:
    try:
        with zipfile.ZipFile(path) as archive:
            matches = [info for info in archive.infolist() if info.filename == "pack.mcmeta"]
            if len(matches) != 1:
                raise GateError("resource pack must contain exactly one root pack.mcmeta")
            raw = archive.read(matches[0])
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise GateError(f"resource pack is not a readable ZIP: {path}") from exc
    value, encoding = decode_pack_mcmeta(raw)
    return raw, value, encoding


def derived_pack_mcmeta(source_raw: bytes, pack_format: int) -> tuple[bytes, str]:
    source_value, encoding = decode_pack_mcmeta(source_raw)
    source_pack = source_value["pack"]
    existing = source_pack.get("pack_format")
    if existing is not None:
        if existing != pack_format:
            raise GateError(
                f"source pack.mcmeta has unexpected pack_format {existing!r}"
            )
        return source_raw, encoding

    text = source_raw.decode(encoding)
    match = re.search(r'("pack"\s*:\s*\{)(\r\n|\n)([ \t]+)', text)
    if match is None:
        raise GateError("pack.mcmeta layout cannot be minimally patched")
    newline = match.group(2)
    indent = match.group(3)
    insertion = f'{match.group(1)}{newline}{indent}"pack_format": {pack_format},{newline}{indent}'
    patched_text = text[: match.start()] + insertion + text[match.end() :]
    patched = patched_text.encode(encoding)
    derived_value, _ = decode_pack_mcmeta(patched)
    derived_pack = dict(derived_value["pack"])
    if derived_pack.pop("pack_format", None) != pack_format or derived_pack != source_pack:
        raise GateError("pack.mcmeta derivation changed fields beyond pack_format")
    return patched, encoding


def resource_pack_zip_evidence(path: Path, expected_zip_entries: int) -> dict[str, Any]:
    manifest = hashlib.sha256()
    non_metadata_entries = 0
    non_metadata_bytes = 0
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) != expected_zip_entries:
                raise GateError(
                    f"resource pack ZIP entry count mismatch: {len(infos)}"
                )
            metadata = [info for info in infos if info.filename == "pack.mcmeta"]
            if len(metadata) != 1:
                raise GateError("resource pack must contain exactly one root pack.mcmeta")
            for index, info in enumerate(infos):
                with archive.open(info) as stream:
                    entry_digest = hashlib.sha256()
                    size = 0
                    for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                        entry_digest.update(block)
                        size += len(block)
                if size != info.file_size:
                    raise GateError(f"resource pack entry size mismatch: {info.filename}")
                if info.filename == "pack.mcmeta":
                    continue
                name = info.filename.encode("utf-8")
                manifest.update(struct.pack(">I", index))
                manifest.update(struct.pack(">I", len(name)))
                manifest.update(name)
                manifest.update(struct.pack(">Q", size))
                manifest.update(entry_digest.digest())
                non_metadata_entries += 1
                non_metadata_bytes += size
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise GateError(f"resource pack ZIP content validation failed: {path}") from exc

    metadata_raw, metadata_value, metadata_encoding = root_pack_mcmeta(path)
    pack = metadata_value["pack"]
    return {
        "zip_entries": expected_zip_entries,
        "pack_mcmeta_entries": 1,
        "pack_mcmeta_sha256": hashlib.sha256(metadata_raw).hexdigest().upper(),
        "pack_mcmeta_bytes": len(metadata_raw),
        "pack_mcmeta_encoding": metadata_encoding,
        "pack_format": pack.get("pack_format"),
        "min_format": pack.get("min_format"),
        "max_format": pack.get("max_format"),
        "non_metadata_entries": non_metadata_entries,
        "non_metadata_uncompressed_bytes": non_metadata_bytes,
        "non_metadata_content_manifest_sha256": manifest.hexdigest().upper(),
    }


def validate_local_world_resource_pack(
    client_root: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    filename: str = REQUIRED_LOCAL_RESOURCE_PACK_NAME,
    pack_format: int = MINECRAFT_1_21_1_RESOURCE_PACK_FORMAT,
) -> dict[str, Any]:
    destination = client_root / "resourcepacks" / filename
    artifact = file_artifact(destination)
    if artifact["bytes"] != expected_bytes or artifact["sha256"] != expected_sha256:
        raise GateError("isolated derived world resource pack hash/size mismatch")
    _raw, metadata, encoding = root_pack_mcmeta(destination)
    actual_pack_format = metadata["pack"].get("pack_format")
    if actual_pack_format != pack_format:
        raise GateError(
            f"isolated world resource pack format mismatch: {actual_pack_format!r}"
        )
    pack_id = f"file/{filename}"
    selected = resource_packs_option(client_root / "options.txt")
    if selected.count(pack_id) != 1:
        raise GateError("local world resource pack is not selected exactly once")
    return {
        "pack_id": pack_id,
        "destination": artifact,
        "pack_format": actual_pack_format,
        "pack_mcmeta_encoding": encoding,
        "selected_resource_packs": selected,
        "enabled_exactly_once": True,
    }


def configure_local_world_resource_pack(
    client_root: Path,
    *,
    source: Path = REQUIRED_LOCAL_RESOURCE_PACK_SOURCE,
    filename: str = REQUIRED_LOCAL_RESOURCE_PACK_NAME,
    expected_sha256: str = REQUIRED_LOCAL_RESOURCE_PACK_SHA256,
    expected_bytes: int = REQUIRED_LOCAL_RESOURCE_PACK_BYTES,
    expected_zip_entries: int = REQUIRED_LOCAL_RESOURCE_PACK_ZIP_ENTRIES,
) -> dict[str, Any]:
    """Derive and enable a 1.21.1-compatible copy of the user's exact local pack."""
    if not client_root.is_dir() or client_root.is_symlink():
        raise GateError(f"client root is missing or linked: {client_root}")
    source_artifact = file_artifact(source)
    if (
        source_artifact["sha256"] != expected_sha256
        or source_artifact["bytes"] != expected_bytes
    ):
        raise GateError("required local world resource pack source hash/size mismatch")
    source_evidence = resource_pack_zip_evidence(source, expected_zip_entries)
    source_metadata_raw, source_metadata, source_metadata_encoding = root_pack_mcmeta(
        source
    )
    patched_metadata, patched_encoding = derived_pack_mcmeta(
        source_metadata_raw, MINECRAFT_1_21_1_RESOURCE_PACK_FORMAT
    )
    patched_metadata_sha = hashlib.sha256(patched_metadata).hexdigest().upper()

    resourcepacks = client_root / "resourcepacks"
    if resourcepacks.exists() and (
        not resourcepacks.is_dir() or resourcepacks.is_symlink()
    ):
        raise GateError(f"client resourcepacks directory is unsafe: {resourcepacks}")
    resourcepacks.mkdir(parents=True, exist_ok=True)
    destination = resourcepacks / filename
    destination_before = file_artifact(destination) if destination.exists() else None
    destination_evidence_before: dict[str, Any] | None = None
    destination_matches = False
    if destination_before is not None:
        try:
            destination_evidence_before = resource_pack_zip_evidence(
                destination, expected_zip_entries
            )
            destination_matches = (
                destination_evidence_before["pack_format"]
                == MINECRAFT_1_21_1_RESOURCE_PACK_FORMAT
                and destination_evidence_before["pack_mcmeta_sha256"]
                == patched_metadata_sha
                and destination_evidence_before[
                    "non_metadata_content_manifest_sha256"
                ]
                == source_evidence["non_metadata_content_manifest_sha256"]
            )
        except GateError:
            destination_evidence_before = None
    if not destination_matches:
        temporary = destination.with_name(
            f"{destination.name}.candidate11.{os.getpid()}.tmp"
        )
        if temporary.exists():
            raise GateError(f"refusing to reuse temporary resource pack: {temporary}")
        try:
            with (
                zipfile.ZipFile(source) as source_archive,
                zipfile.ZipFile(temporary, "w", allowZip64=True) as derived_archive,
            ):
                derived_archive.comment = source_archive.comment
                metadata_writes = 0
                for info in source_archive.infolist():
                    data = source_archive.read(info)
                    if info.filename == "pack.mcmeta":
                        data = patched_metadata
                        metadata_writes += 1
                    derived_archive.writestr(info, data)
                if metadata_writes != 1:
                    raise GateError("derived resource pack did not patch one pack.mcmeta")
            temporary_evidence = resource_pack_zip_evidence(
                temporary, expected_zip_entries
            )
            if (
                temporary_evidence["pack_format"]
                != MINECRAFT_1_21_1_RESOURCE_PACK_FORMAT
                or temporary_evidence["pack_mcmeta_sha256"]
                != patched_metadata_sha
                or temporary_evidence["non_metadata_content_manifest_sha256"]
                != source_evidence["non_metadata_content_manifest_sha256"]
            ):
                raise GateError("derived local world resource pack failed validation")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    options_path = client_root / "options.txt"
    options_before = file_artifact(options_path)
    selected_before = resource_packs_option(options_path)
    pack_id = f"file/{filename}"
    selected_after = [item for item in selected_before if item != pack_id] + [pack_id]
    lines = options_path.read_text(encoding="utf-8", errors="strict").splitlines()
    replacement = "resourcePacks:" + json.dumps(
        selected_after, ensure_ascii=True, separators=(",", ":")
    )
    updated_lines = [
        replacement if raw.startswith("resourcePacks:") else raw for raw in lines
    ]
    updated_text = "\n".join(updated_lines) + "\n"
    current_text = options_path.read_text(encoding="utf-8", errors="strict")
    if updated_text != current_text:
        temporary = options_path.with_name(
            f"{options_path.name}.candidate11.{os.getpid()}.tmp"
        )
        if temporary.exists():
            raise GateError(f"refusing to reuse temporary options file: {temporary}")
        try:
            temporary.write_text(updated_text, encoding="utf-8")
            os.replace(temporary, options_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    source_after = file_artifact(source)
    if source_after != source_artifact:
        raise GateError("source local world resource pack changed during derivation")
    destination_after = file_artifact(destination)
    destination_evidence = resource_pack_zip_evidence(
        destination, expected_zip_entries
    )
    if (
        destination_evidence["pack_mcmeta_sha256"] != patched_metadata_sha
        or destination_evidence["non_metadata_content_manifest_sha256"]
        != source_evidence["non_metadata_content_manifest_sha256"]
    ):
        raise GateError("derived local world resource pack content binding mismatch")
    validated = validate_local_world_resource_pack(
        client_root,
        filename=filename,
        expected_sha256=destination_after["sha256"],
        expected_bytes=destination_after["bytes"],
    )
    destination_after = validated["destination"]
    options_after = file_artifact(options_path)
    return {
        "policy": "derive_1_21_1_metadata_and_enable",
        "source": {
            "before": source_artifact,
            "after": source_after,
            "unchanged": True,
            "expected_sha256": expected_sha256,
            "expected_bytes": expected_bytes,
            "zip": source_evidence,
        },
        "derivation": {
            "only_changed_entry": "pack.mcmeta",
            "source_pack_mcmeta_sha256": source_evidence["pack_mcmeta_sha256"],
            "derived_pack_mcmeta_sha256": patched_metadata_sha,
            "source_pack_mcmeta_encoding": source_metadata_encoding,
            "derived_pack_mcmeta_encoding": patched_encoding,
            "added_field": {
                "name": "pack_format",
                "value": MINECRAFT_1_21_1_RESOURCE_PACK_FORMAT,
            },
            "pack_format_evidence": {
                "minecraft_version": "1.21.1",
                "class": "net.minecraft.DetectedVersion",
                "field": "resourcePackVersion",
                "bytecode": "bipush 34",
            },
            "non_metadata_entries": source_evidence["non_metadata_entries"],
            "non_metadata_content_manifest_sha256": source_evidence[
                "non_metadata_content_manifest_sha256"
            ],
            "non_metadata_content_unchanged": True,
        },
        "destination": {
            "before": destination_before,
            "before_zip": destination_evidence_before,
            "after": destination_after,
            "after_zip": destination_evidence,
            "changed": destination_before is None
            or destination_before["sha256"] != destination_after["sha256"],
        },
        "options": {
            "before": options_before,
            "after": options_after,
            "selected_before": selected_before,
            "selected_after": validated["selected_resource_packs"],
            "changed": options_before["sha256"] != options_after["sha256"],
        },
        "pack_id": pack_id,
        "enabled_exactly_once": True,
    }


def normalize_disposable_whitelist(path: Path) -> dict[str, Any]:
    """Disable only the disposable candidate's whitelist, removing duplicates."""
    before_sha = sha256_file(path)
    updates = {"white-list": "false", "enforce-whitelist": "false"}
    found: set[str] = set()
    output: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if "=" not in stripped or stripped.startswith("#"):
            output.append(raw)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key not in updates:
            output.append(raw)
            continue
        if key not in found:
            output.append(f"{key}={updates[key]}")
            found.add(key)
    for key, value in updates.items():
        if key not in found:
            output.append(f"{key}={value}")
    value = "\n".join(output) + "\n"
    if value != path.read_text(encoding="utf-8", errors="replace"):
        temporary = path.with_name(path.name + ".candidate11.tmp")
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    return {
        "keys": updates,
        "changed": sha256_file(path) != before_sha,
        "before_sha256": before_sha,
        "after_sha256": sha256_file(path),
    }


def validate_server_properties(
    properties: dict[str, str], server_port: int, rcon_port: int
) -> None:
    expected = {
        "server-ip": "127.0.0.1",
        "server-port": str(server_port),
        "enable-rcon": "true",
        "rcon.port": str(rcon_port),
        "online-mode": "false",
        "white-list": "false",
        "enforce-whitelist": "false",
        "level-name": "world",
    }
    mismatches = {
        key: {"expected": value, "actual": properties.get(key)}
        for key, value in expected.items()
        if properties.get(key, "").lower() != value.lower()
    }
    if mismatches:
        raise GateError(f"unsafe or mismatched server properties: {mismatches}")
    if not properties.get("rcon.password"):
        raise GateError("rcon.password is missing")


def validate_prepare_report(
    path: Path, target: Path, server_port: int, rcon_port: int, voice_port: int | None
) -> dict[str, Any]:
    if forbidden_source_path(path):
        raise GateError("prepare report may not come from the historical source")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"prepare report is not valid JSON: {path}") from exc
    if not isinstance(value, dict) or value.get("status") != "PREPARED":
        raise GateError("prepare report is not PREPARED")
    if Path(str(value.get("output", ""))).resolve() != target.resolve():
        raise GateError("prepare report is bound to a different target")
    ports = value.get("ports")
    expected_ports = {"server": server_port, "rcon": rcon_port}
    if voice_port is not None:
        expected_ports["voice"] = voice_port
    if not isinstance(ports, dict) or any(ports.get(k) != v for k, v in expected_ports.items()):
        raise GateError("prepare report port binding mismatch")
    safety = value.get("network_safety")
    if not isinstance(safety, dict) or safety.get("server_bind") != "127.0.0.1":
        raise GateError("prepare report has no loopback safety binding")
    if safety.get("online_mode") is not False or safety.get("mineastr_enabled") is not False:
        raise GateError("prepare report network safety is incomplete")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "status": value.get("status"),
    }


def validate_client_prepare_report(
    path: Path, client_root: Path, client_bundle: dict[str, Any]
) -> dict[str, Any]:
    if path.resolve() != CANDIDATE11_CLIENT_PREPARE_REPORT.resolve():
        raise GateError(
            "client prepare report must be the locked Candidate11 preparation report"
        )
    if forbidden_source_path(path):
        raise GateError("client prepare report may not come from the historical source")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"client prepare report is not valid JSON: {path}") from exc
    if not isinstance(value, dict) or value.get("status") != "PREPARED":
        raise GateError("client prepare report is not PREPARED")
    if Path(str(value.get("output_root", ""))).resolve() != client_root.resolve():
        raise GateError("client prepare report is bound to a different client root")
    if value.get("source_unchanged") is not True:
        raise GateError("client prepare report did not preserve its source root")
    if value.get("saves_logs_caches_absent") is not True:
        raise GateError("client prepare report did not exclude saves/logs/caches")
    if value.get("forbidden_runtime_state_found") != []:
        raise GateError("client prepare report contains forbidden runtime state")
    if value.get("candidate8_root_read_or_written") is not False:
        raise GateError("client preparation read or wrote a Candidate8 runtime root")
    if value.get("candidate10_root_read_or_written") is not False:
        raise GateError("client preparation read or wrote the used Candidate10 gate root")
    if value.get("prior_gate_root_read_or_written") is not False:
        raise GateError("client preparation reused a prior gate root")
    if value.get("java_started") is not False:
        raise GateError("client prepare report was generated after Java launch")
    if value.get("historical_backup_accessed") is not False:
        raise GateError("client prepare report accessed the historical backup")
    release = value.get("release")
    if (
        not isinstance(release, dict)
        or Path(str(release.get("root", ""))).resolve()
        != CANDIDATE11_RELEASE_ROOT.resolve()
        or release.get("ready_sha256") != CANDIDATE11_READY_SHA256
        or release.get("release_lock_sha256") != CANDIDATE11_READY_SHA256
        or release.get("ready_lock_byte_identical") is not True
    ):
        raise GateError("client prepare report Candidate11 release binding mismatch")
    allowed_top_level = {
        "assets",
        "config",
        "data",
        "defaultconfigs",
        "libraries",
        "mods",
        "natives",
        "options.txt",
        "resourcepacks",
        "versions",
    }
    actual_top_level = {item.name for item in client_root.iterdir()}
    if actual_top_level != allowed_top_level:
        raise GateError(
            "client root is not pristine: "
            f"missing={sorted(allowed_top_level - actual_top_level)}, "
            f"unexpected={sorted(actual_top_level - allowed_top_level)}"
        )
    for directory_name in ("natives", "resourcepacks"):
        directory = client_root / directory_name
        if not directory.is_dir() or directory.is_symlink() or any(directory.iterdir()):
            raise GateError(f"client root has reused {directory_name} state")
    copied_state = value.get("copied_non_world_client_state")
    options_binding = (
        copied_state.get("options.txt") if isinstance(copied_state, dict) else None
    )
    options_path = client_root / "options.txt"
    if (
        not isinstance(options_binding, dict)
        or not options_path.is_file()
        or options_path.is_symlink()
        or options_binding.get("files") != 1
        or options_binding.get("bytes") != options_path.stat().st_size
        or str(options_binding.get("sha256", "")).upper() != sha256_file(options_path)
    ):
        raise GateError("client options.txt no longer matches its preparation report")
    identity = value.get("offline_identity")
    if not isinstance(identity, dict):
        raise GateError("client prepare report has no offline identity")
    if identity.get("username") != SYNTHETIC_USERNAME or identity.get("uuid") != SYNTHETIC_UUID:
        raise GateError("client prepare report identity mismatch")
    if identity.get("inherited_account_cache") is not False:
        raise GateError("client prepare report inherited an account cache")
    bundle = value.get("client_bundle")
    if not isinstance(bundle, dict):
        raise GateError("client prepare report has no client bundle binding")
    if Path(str(bundle.get("destination", ""))).resolve() != (client_root / "mods").resolve():
        raise GateError("client prepare report mods destination mismatch")
    expected = {
        "file_count": client_bundle["files"],
        "bytes": client_bundle["bytes"],
        "bundle_sha256": client_bundle["bundle_sha256"],
    }
    actual = {key: bundle.get(key) for key in expected}
    if actual != expected or bundle.get("exact_manifest_match") is not True:
        raise GateError(
            f"client prepare report bundle mismatch: expected={expected}, actual={actual}"
        )
    if (
        Path(str(bundle.get("source", ""))).resolve()
        != (CANDIDATE11_RELEASE_ROOT / "client-mods").resolve()
        or Path(str(bundle.get("manifest", ""))).resolve()
        != CANDIDATE11_CLIENT_MANIFEST.resolve()
        or bundle.get("manifest_sha256") != CANDIDATE11_CLIENT_MANIFEST_SHA256
        or bundle.get("cc_guard_file") != CC_GUARD_FILE
        or bundle.get("cc_guard_sha256") != CC_GUARD_SHA256
        or bundle.get("create_guard_file") != CREATE_GUARD_FILE
        or bundle.get("create_guard_sha256") != CREATE_GUARD_SHA256
    ):
        raise GateError("client prepare report compatibility-guard binding mismatch")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "status": value.get("status"),
        "identity": {"username": SYNTHETIC_USERNAME, "uuid": SYNTHETIC_UUID},
        "bundle_sha256": client_bundle["bundle_sha256"],
        "saves_logs_caches_absent": True,
    }


def validate_port_number(port: int) -> None:
    if port < 1024 or port > 65535:
        raise GateError(f"unsafe port: {port}")


def tcp_closed(port: int, timeout: float = 0.25) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def udp_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def wait_until(
    predicate: Callable[[], Any],
    timeout: float,
    label: str,
    *,
    health: Callable[[], None] | None = None,
    interval: float = 0.25,
) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if health is not None:
            health()
        try:
            value = predicate()
            if value:
                return value
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(interval)
    suffix = f": {last_error}" if last_error else ""
    raise TimeoutError(f"timeout waiting for {label}{suffix}")


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def process_exists(pid: Any) -> bool:
    try:
        value = int(pid)
        if value <= 0:
            return False
        if os.name == "nt":
            # os.kill(pid, 0) is not a reliable existence probe for a GUI
            # process created on another Windows desktop. Query the process
            # handle without requesting terminate or VM access instead.
            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
            kernel32.GetExitCodeProcess.restype = ctypes.c_bool
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_bool
            handle = kernel32.OpenProcess(
                process_query_limited_information, False, value
            )
            if not handle:
                # Access denied means the process exists but cannot be queried;
                # invalid or missing PIDs use other Win32 errors.
                return ctypes.get_last_error() == 5
            try:
                exit_code = ctypes.c_uint32()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return True
                return exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        os.kill(value, 0)
        return True
    except PermissionError:
        return True
    except (OSError, TypeError, ValueError):
        return False


def strict_marker_hits(text: str, *, client: bool = False) -> list[dict[str, Any]]:
    patterns = STRICT_COMMON_PATTERNS + (STRICT_CLIENT_PATTERNS if client else ())
    hits: list[dict[str, Any]] = []
    for name, pattern in patterns:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        samples = []
        for match in matches[:3]:
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            if end < 0:
                end = len(text)
            samples.append(text[start:end][:500])
        hits.append({"marker": name, "count": len(matches), "samples": samples})
    if not client:
        unallowed_server_errors = [
            match.group(0)[:500]
            for match in SERVER_THREAD_ERROR_RE.finditer(text)
            if not any(
                allow.search(match.group(0))
                for allow in SERVER_THREAD_ERROR_ALLOWLIST
            )
        ]
        if unallowed_server_errors:
            hits.append(
                {
                    "marker": "UNALLOWLISTED_SERVER_THREAD_ERROR",
                    "count": len(unallowed_server_errors),
                    "samples": unallowed_server_errors[:3],
                }
            )
    return hits


def assert_no_strict_markers(text: str, scope: str, *, client: bool = False) -> None:
    hits = strict_marker_hits(text, client=client)
    if hits:
        raise GateError(f"strict {scope} marker(s): {hits}")


def joined_count(text: str, username: str = SYNTHETIC_USERNAME) -> int:
    return len(re.findall(rf"\b{re.escape(username)} joined the game\b", text))


def lost_count(text: str, username: str = SYNTHETIC_USERNAME) -> int:
    return len(re.findall(rf"\b{re.escape(username)} lost connection\b", text))


def command_plan(username: str = SYNTHETIC_USERNAME) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for site in RISK_SITES:
        commands.append(
            {
                "kind": "forceload",
                "site": site["name"],
                "command": f"forceload add {site['x']} {site['z']}",
            }
        )
    for site in RISK_SITES:
        commands.append(
            {
                "kind": "teleport",
                "site": site["name"],
                "command": f"tp {username} {site['x']} {site['y']} {site['z']}",
            }
        )
    commands.append({"kind": "save", "site": None, "command": "save-all flush"})
    return commands


def validate_command_response(command: str, response: str) -> None:
    if COMMAND_FAILURE_RE.search(response):
        raise GateError(f"RCON command failed: {command}: {response}")
    if command == "save-all flush" and "Saved the game" not in response:
        raise GateError(f"save-all flush did not confirm persistence: {response}")


class Rcon:
    def __init__(self, host: str, port: int, password: str):
        self.socket = socket.create_connection((host, port), timeout=10)
        self.socket.settimeout(30)
        self.request_id = 1000
        ident, _ = self._packet(3, password)
        if ident == -1:
            self.close()
            raise GateError("RCON authentication failed")

    def __enter__(self) -> "Rcon":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _read_exact(self, count: int) -> bytes:
        chunks: list[bytes] = []
        while count:
            block = self.socket.recv(count)
            if not block:
                raise ConnectionError("RCON connection closed")
            chunks.append(block)
            count -= len(block)
        return b"".join(chunks)

    def _packet(self, packet_type: int, body: str) -> tuple[int, str]:
        self.request_id += 1
        request_id = self.request_id
        payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\0\0"
        self.socket.sendall(struct.pack("<i", len(payload)) + payload)
        length = struct.unpack("<i", self._read_exact(4))[0]
        if length < 10 or length > 1024 * 1024:
            raise GateError(f"invalid RCON response length: {length}")
        response = self._read_exact(length)
        ident, _kind = struct.unpack("<ii", response[:8])
        return ident, response[8:-2].decode("utf-8", errors="replace")

    def command(self, body: str) -> str:
        ident, response = self._packet(2, body)
        if ident != self.request_id:
            raise GateError(f"unexpected RCON response id: {ident}")
        return response

    def close(self) -> None:
        try:
            self.socket.close()
        except OSError:
            pass


def hidden_startup_kwargs() -> dict[str, Any]:
    result: dict[str, Any] = {"creationflags": CREATE_NO_WINDOW}
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        result["startupinfo"] = startup
    return result


class ServerSession:
    def __init__(
        self,
        target: Path,
        artifact_dir: Path,
        round_number: int,
        java: Path,
        win_args: str,
        rcon_port: int,
        rcon_password: str,
        memory_mb: int,
    ):
        self.target = target
        self.round_number = round_number
        self.rcon_port = rcon_port
        self.rcon_password = rcon_password
        self.latest_log = target / "logs" / "latest.log"
        self.previous_log = read_text(self.latest_log)
        self.stdout_path = artifact_dir / f"server-round{round_number}.stdout.log"
        self.stderr_path = artifact_dir / f"server-round{round_number}.stderr.log"
        self.stdout_stream = self.stdout_path.open("wb")
        self.stderr_stream = self.stderr_path.open("wb")
        command = [
            str(java),
            "-Xms1G",
            f"-Xmx{memory_mb}M",
            "@user_jvm_args.txt",
            win_args,
            "nogui",
        ]
        try:
            self.process = subprocess.Popen(
                command,
                cwd=target,
                stdin=subprocess.DEVNULL,
                stdout=self.stdout_stream,
                stderr=self.stderr_stream,
                **hidden_startup_kwargs(),
            )
        except Exception:
            self.stdout_stream.close()
            self.stderr_stream.close()
            raise
        self.stopped_cleanly = False

    def current_log(self) -> str:
        return read_text(self.latest_log)

    def assert_alive(self) -> None:
        if self.process.poll() is not None:
            raise GateError(
                f"server round {self.round_number} exited early with {self.process.returncode}"
            )
        text = self.current_log()
        if text != self.previous_log:
            assert_no_strict_markers(text, f"server round {self.round_number}")

    def wait_ready(self, timeout: float) -> None:
        wait_until(
            lambda: (
                self.current_log() != self.previous_log
                and bool(DONE_RE.search(self.current_log()))
            ),
            timeout,
            f"server round {self.round_number} Done",
            health=self.assert_alive,
        )

        def rcon_ready() -> bool:
            try:
                with Rcon("127.0.0.1", self.rcon_port, self.rcon_password) as rcon:
                    rcon.command("list")
                return True
            except (OSError, ConnectionError, TimeoutError, GateError):
                return False

        wait_until(
            rcon_ready,
            60,
            f"server round {self.round_number} RCON",
            health=self.assert_alive,
        )

    def command(self, command: str) -> str:
        self.assert_alive()
        with Rcon("127.0.0.1", self.rcon_port, self.rcon_password) as rcon:
            response = rcon.command(command)
        if command != "stop":
            validate_command_response(command, response)
            self.assert_alive()
        return response

    def stop(self) -> str:
        response = ""
        if self.process.poll() is None:
            try:
                response = self.command("stop")
            except (OSError, ConnectionError, TimeoutError):
                # The listener can close before returning its short stop response.
                response = "RCON listener closed during controlled stop"
            try:
                self.process.wait(timeout=120)
            except subprocess.TimeoutExpired as exc:
                self.process.kill()
                self.process.wait(timeout=30)
                raise GateError("server did not stop within 120 seconds") from exc
        self._close_streams()
        if self.process.returncode != 0:
            raise GateError(
                f"server round {self.round_number} exited with {self.process.returncode}"
            )
        self.stopped_cleanly = True
        return response

    def abort(self) -> None:
        if self.process.poll() is None:
            try:
                with Rcon("127.0.0.1", self.rcon_port, self.rcon_password) as rcon:
                    rcon.command("stop")
                self.process.wait(timeout=45)
            except (OSError, ConnectionError, TimeoutError, GateError, subprocess.TimeoutExpired):
                if self.process.poll() is None:
                    self.process.kill()
                    try:
                        self.process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        pass
        self._close_streams()

    def _close_streams(self) -> None:
        if not self.stdout_stream.closed:
            self.stdout_stream.close()
        if not self.stderr_stream.closed:
            self.stderr_stream.close()


class PrivateClientSession:
    def __init__(
        self,
        client_root: Path,
        artifact_dir: Path,
        round_number: int,
        server_port: int,
        powershell: Path,
        helper: Path,
        launcher: Path,
        java: Path,
        memory_mb: int,
        launch_timeout: int,
        session_timeout: int,
    ):
        self.round_number = round_number
        self.state_path = artifact_dir / f"client-round{round_number}.state.json"
        self.stop_path = artifact_dir / f"client-round{round_number}.stop"
        self.helper_stdout_path = artifact_dir / f"client-round{round_number}.helper.stdout.log"
        self.helper_stderr_path = artifact_dir / f"client-round{round_number}.helper.stderr.log"
        self.helper_stdout = self.helper_stdout_path.open("wb")
        self.helper_stderr = self.helper_stderr_path.open("wb")
        command = [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "-MinecraftRoot",
            str(client_root),
            "-ServerAddress",
            f"127.0.0.1:{server_port}",
            "-Username",
            SYNTHETIC_USERNAME,
            "-Uuid",
            SYNTHETIC_UUID,
            "-StatePath",
            str(self.state_path),
            "-StopPath",
            str(self.stop_path),
            "-Launcher",
            str(launcher),
            "-Java",
            str(java),
            "-MaximumMemoryMb",
            str(memory_mb),
            "-LaunchTimeoutSeconds",
            str(launch_timeout),
            "-SessionTimeoutSeconds",
            str(session_timeout),
        ]
        self.process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=self.helper_stdout,
            stderr=self.helper_stderr,
            **hidden_startup_kwargs(),
        )
        try:
            self.running_state = wait_until(
                self._running_state,
                launch_timeout + 20,
                f"private client round {round_number} launch",
                health=self._helper_alive,
            )
        except Exception:
            self.abort()
            raise
        self.stdout_path = Path(str(self.running_state["stdout"]))
        self.stderr_path = Path(str(self.running_state["stderr"]))
        self.controlled_stop_started = False

    def _read_state(self) -> dict[str, Any] | None:
        if not self.state_path.is_file():
            return None
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise GateError("private client state root is not an object")
        return value

    def _helper_alive(self) -> None:
        if self.process.poll() is not None:
            value = self._read_state()
            if value is not None and value.get("status") == "FAILED":
                raise GateError(client_state_failure_message(value))
            raise GateError(
                f"private client helper round {self.round_number} exited early with "
                f"{self.process.returncode}"
            )

    def _running_state(self) -> dict[str, Any] | bool:
        value = self._read_state()
        if value is None:
            return False
        if value.get("status") == "FAILED":
            raise GateError(client_state_failure_message(value))
        if value.get("status") != "RUNNING":
            return False
        if value.get("private_desktop") is not True or value.get("foreground_activation") is not False:
            raise GateError("client did not launch on a non-activating private desktop")
        if not valid_startup_evidence(value.get("startup_evidence")):
            raise GateError("client helper reported RUNNING without explicit JVM startup evidence")
        return value

    def combined_text(self) -> str:
        return "\n".join(
            read_text(path)
            for path in (
                getattr(self, "stdout_path", Path("__missing__")),
                getattr(self, "stderr_path", Path("__missing__")),
                self.helper_stdout_path,
                self.helper_stderr_path,
            )
        )

    def assert_running(self) -> None:
        self._helper_alive()
        value = self._read_state()
        if value is not None and value.get("status") == "FAILED":
            raise GateError(client_state_failure_message(value))
        if value is None or value.get("status") != "RUNNING":
            raise GateError("client exited before the controlled stop")
        if not valid_startup_evidence(value.get("startup_evidence")):
            raise GateError("client RUNNING state lost its JVM startup evidence")
        if not process_exists(value.get("java_pid")):
            # The helper owns the Java handle and may still be publishing its
            # exit record. Give that atomic FAILED update a short head start so
            # the gate reports the real exit code and log paths.
            deadline = time.monotonic() + 7
            while time.monotonic() < deadline:
                time.sleep(0.1)
                refreshed = self._read_state()
                if refreshed is not None and refreshed.get("status") == "FAILED":
                    raise GateError(client_state_failure_message(refreshed))
                if self.process.poll() is not None:
                    self._helper_alive()
            raise GateError(
                client_state_failure_message(
                    {
                        **value,
                        "error": "client Java process exited before the controlled stop",
                    }
                )
            )
        assert_no_strict_markers(
            self.combined_text(), f"client round {self.round_number}", client=True
        )

    def stop(self) -> dict[str, Any]:
        self.assert_running()
        self.controlled_stop_started = True
        self.stop_path.write_text("controlled candidate11 stop\n", encoding="ascii")
        try:
            self.process.wait(timeout=60)
        except subprocess.TimeoutExpired as exc:
            self.process.kill()
            self.process.wait(timeout=20)
            raise GateError("private client helper did not stop in 60 seconds") from exc
        self._close_streams()
        if self.process.returncode != 0:
            raise GateError(
                f"private client helper round {self.round_number} exited with "
                f"{self.process.returncode}"
            )
        value = self._read_state()
        if (
            value is None
            or value.get("status") != "STOPPED"
            or value.get("private_desktop") is not True
            or value.get("foreground_activation") is not False
            or not valid_startup_evidence(value.get("startup_evidence"))
        ):
            raise GateError("private client final state is not a clean private-desktop stop")
        if read_text(self.stderr_path).strip():
            raise GateError("client stderr is not empty")
        if read_text(self.helper_stderr_path).strip():
            raise GateError("private client helper stderr is not empty")
        for pid_name in ("java_pid", "launcher_pid"):
            pid_value = value.get(pid_name)
            if not isinstance(pid_value, int) or pid_value <= 0:
                raise GateError(f"private client final state has no valid {pid_name}")
        process_status = {
            "java": not process_exists(value.get("java_pid")),
            "launcher": not process_exists(value.get("launcher_pid")),
            "helper": self.process.poll() is not None,
        }
        if not all(process_status.values()):
            raise GateError(f"private client process cleanup is incomplete: {process_status}")
        value["process_status"] = process_status
        value["processes_closed"] = True
        assert_no_strict_markers(
            self.combined_text(), f"client round {self.round_number}", client=True
        )
        return value

    def abort(self) -> None:
        try:
            self.stop_path.write_text("abort candidate11 client\n", encoding="ascii")
        except OSError:
            pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
        self._close_streams()

    def _close_streams(self) -> None:
        if not self.helper_stdout.closed:
            self.helper_stdout.close()
        if not self.helper_stderr.closed:
            self.helper_stderr.close()


def file_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise GateError(f"artifact is missing, linked, or not a regular file: {path}")
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise GateError(f"{label} must be a JSON object: {path}")
    return value


def require_exact_bundle(
    actual: dict[str, Any], expected: dict[str, Any], label: str
) -> None:
    observed = {key: actual.get(key) for key in expected}
    if observed != expected:
        raise GateError(
            f"{label} bundle mismatch: expected={expected}, actual={observed}"
        )


def validate_candidate11_release() -> dict[str, Any]:
    paths = {
        "ready": (CANDIDATE11_READY, CANDIDATE11_READY_SHA256),
        "release_lock": (CANDIDATE11_RELEASE_LOCK, CANDIDATE11_READY_SHA256),
        "server_manifest": (
            CANDIDATE11_SERVER_MANIFEST,
            CANDIDATE11_SERVER_MANIFEST_SHA256,
        ),
        "client_manifest": (
            CANDIDATE11_CLIENT_MANIFEST,
            CANDIDATE11_CLIENT_MANIFEST_SHA256,
        ),
        "full_audit": (CANDIDATE11_FULL_AUDIT, CANDIDATE11_FULL_AUDIT_SHA256),
    }
    artifacts: dict[str, Any] = {}
    for name, (path, expected_hash) in paths.items():
        artifact = file_artifact(path)
        if artifact["sha256"] != expected_hash:
            raise GateError(f"Candidate11 {name} hash mismatch")
        artifacts[name] = artifact
    if CANDIDATE11_READY.read_bytes() != CANDIDATE11_RELEASE_LOCK.read_bytes():
        raise GateError("Candidate11 READY and release-lock are not byte-identical")

    ready = read_json_object(CANDIDATE11_READY, "Candidate11 READY")
    server_manifest = read_json_object(
        CANDIDATE11_SERVER_MANIFEST, "Candidate11 server manifest"
    )
    client_manifest = read_json_object(
        CANDIDATE11_CLIENT_MANIFEST, "Candidate11 client manifest"
    )
    audit = read_json_object(CANDIDATE11_FULL_AUDIT, "Candidate11 full audit")
    if (
        ready.get("schema") != 1
        or ready.get("candidate") != 11
        or ready.get("status") != "PASS"
        or ready.get("source_unchanged") is not True
        or Path(str(ready.get("output_root", ""))).resolve()
        != CANDIDATE11_RELEASE_ROOT.resolve()
        or ready.get("bundle_pair_sha256") != CANDIDATE11_BUNDLE_PAIR_SHA256
    ):
        raise GateError("Candidate11 READY identity mismatch")
    for side, manifest, expected_hash, expected_bundle in (
        (
            "server",
            server_manifest,
            CANDIDATE11_SERVER_MANIFEST_SHA256,
            CANDIDATE11_PUBLISHED_SERVER_BUNDLE,
        ),
        (
            "client",
            client_manifest,
            CANDIDATE11_CLIENT_MANIFEST_SHA256,
            CANDIDATE11_CLIENT_BUNDLE,
        ),
    ):
        release_side = ready.get(side)
        if not isinstance(release_side, dict):
            raise GateError(f"Candidate11 READY has no {side} binding")
        release_observed = {
            "files": release_side.get("file_count"),
            "bytes": release_side.get("bytes"),
            "bundle_sha256": release_side.get("bundle_sha256"),
        }
        if (
            release_observed != expected_bundle
            or release_side.get("manifest_sha256") != expected_hash
            or manifest.get("schema") != 1
            or manifest.get("candidate") != 11
            or manifest.get("status") != "PASS"
            or manifest.get("side") != side
            or manifest.get("file_count") != expected_bundle["files"]
            or len(manifest.get("files", [])) != expected_bundle["files"]
            or manifest.get("bytes") != expected_bundle["bytes"]
            or manifest.get("bundle_sha256") != expected_bundle["bundle_sha256"]
        ):
            raise GateError(f"Candidate11 {side} release/manifest mismatch")

    patches = ready.get("patches")
    if not isinstance(patches, dict):
        raise GateError("Candidate11 READY has no patch binding")
    patch_rows = {
        "cc_stop_worker_compat": (CC_GUARD_FILE, CC_GUARD_SHA256),
        "create_chute_guard": (CREATE_GUARD_FILE, CREATE_GUARD_SHA256),
    }
    for name, (filename, digest) in patch_rows.items():
        row = patches.get(name)
        if (
            not isinstance(row, dict)
            or row.get("file") != filename
            or row.get("sha256") != digest
            or row.get("operation") != "add_both_sides"
        ):
            raise GateError(f"Candidate11 {name} patch binding mismatch")

    runtime = audit.get("expected_disposable_server_runtime")
    audit_release = audit.get("release")
    if (
        audit.get("schema") != 1
        or audit.get("status") != "PASS"
        or not isinstance(audit_release, dict)
        or audit_release.get("ready_sha256") != CANDIDATE11_READY_SHA256
        or audit_release.get("bundle_pair_sha256")
        != CANDIDATE11_BUNDLE_PAIR_SHA256
        or not isinstance(runtime, dict)
        or {
            "files": runtime.get("file_count"),
            "bytes": runtime.get("bytes"),
            "bundle_sha256": runtime.get("bundle_sha256"),
        }
        != CANDIDATE11_RUNTIME_SERVER_BUNDLE
        or runtime.get("approved_jar_transform_count") != 2
        or audit.get("runtime_boundary", {}).get(
            "new_guard_jars_must_remain_byte_identical"
        )
        is not True
    ):
        raise GateError("Candidate11 runtime audit binding mismatch")
    return {
        **artifacts,
        "bundle_pair_sha256": CANDIDATE11_BUNDLE_PAIR_SHA256,
        "published_server_bundle": CANDIDATE11_PUBLISHED_SERVER_BUNDLE,
        "expected_runtime_server_bundle": CANDIDATE11_RUNTIME_SERVER_BUNDLE,
        "client_bundle": CANDIDATE11_CLIENT_BUNDLE,
    }


def validate_candidate11_runtime_bundles(
    target: Path,
    client_root: Path,
    server_bundle: dict[str, Any],
    client_bundle: dict[str, Any],
) -> dict[str, Any]:
    require_exact_bundle(
        server_bundle, CANDIDATE11_RUNTIME_SERVER_BUNDLE, "Candidate11 server runtime"
    )
    require_exact_bundle(client_bundle, CANDIDATE11_CLIENT_BUNDLE, "Candidate11 client")
    guards: dict[str, Any] = {}
    for filename, digest in (
        (CC_GUARD_FILE, CC_GUARD_SHA256),
        (CREATE_GUARD_FILE, CREATE_GUARD_SHA256),
    ):
        server = file_artifact(target / "mods" / filename)
        client = file_artifact(client_root / "mods" / filename)
        if server["sha256"] != digest or client["sha256"] != digest:
            raise GateError(f"Candidate11 guard changed at runtime: {filename}")
        guards[filename] = {
            "expected_sha256": digest,
            "server": server,
            "client": client,
            "both_sides_byte_identical": True,
        }
    return {
        "server": server_bundle,
        "client": client_bundle,
        "guards": guards,
        "exact_52_jar_bundles": True,
    }


def validate_computer_11_records(
    entities: list[Any], phase: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = []
    for record in entities:
        if not isinstance(record, dict):
            continue
        record_position = tuple(record.get(axis) for axis in ("x", "y", "z"))
        if record_position == CC_COMPUTER_POSITION or record.get("ComputerId") == CC_COMPUTER_ID:
            candidates.append(record)
    if len(candidates) != 1:
        raise GateError(
            f"ComputerId 11 must have exactly one bound record, found {len(candidates)}"
        )
    computer = candidates[0]
    observed = {
        "id": computer.get("id"),
        "ComputerId": computer.get("ComputerId"),
        "On": computer.get("On"),
        "position": [computer.get(axis) for axis in ("x", "y", "z")],
    }
    expected = {
        "id": CC_COMPUTER_BLOCK_ENTITY_ID,
        "ComputerId": CC_COMPUTER_ID,
        "On": 1,
        "position": list(CC_COMPUTER_POSITION),
    }
    if observed != expected:
        raise GateError(
            f"ComputerId 11 offline NBT mismatch at {phase}: "
            f"expected={expected}, actual={observed}"
        )
    return observed, expected


def computer_11_on_evidence(world: Path, phase: str) -> dict[str, Any]:
    x, y, z = CC_COMPUTER_POSITION
    chunk_x, chunk_z = x // 16, z // 16
    region_x, region_z = chunk_x // 32, chunk_z // 32
    local_x, local_z = chunk_x % 32, chunk_z % 32
    slot = local_z * 32 + local_x
    region = world / "region" / f"r.{region_x}.{region_z}.mca"
    artifact = file_artifact(region)
    data = region.read_bytes()
    if len(data) < 8192:
        raise GateError("ComputerId 11 region has a short Anvil header")
    entry = data[slot * 4 : slot * 4 + 4]
    offset, sectors = int.from_bytes(entry[:3], "big"), entry[3]
    if offset < 2 or sectors < 1:
        raise GateError("ComputerId 11 chunk is absent from its Anvil region")
    position = offset * 4096
    if position + 5 > len(data):
        raise GateError("ComputerId 11 chunk header is out of bounds")
    length = int.from_bytes(data[position : position + 4], "big")
    compression = data[position + 4]
    if length <= 1 or length > sectors * 4096 - 4:
        raise GateError("ComputerId 11 chunk has an invalid Anvil length")
    if compression & 0x80:
        raise GateError("ComputerId 11 chunk unexpectedly uses external storage")
    payload = data[position + 5 : position + 4 + length]
    try:
        if compression == 1:
            decoded = gzip.decompress(payload)
        elif compression == 2:
            decoded = zlib.decompress(payload)
        elif compression == 3:
            decoded = payload
        else:
            raise GateError(
                f"ComputerId 11 chunk has unsupported compression {compression}"
            )
        root = nbtlib.File.parse(io.BytesIO(decoded), byteorder="big").unpack()
    except GateError:
        raise
    except Exception as exc:
        raise GateError("ComputerId 11 chunk NBT could not be decoded") from exc
    if not isinstance(root, dict):
        raise GateError("ComputerId 11 chunk NBT root is not a compound")
    level = root.get("Level") if isinstance(root.get("Level"), dict) else root
    entities = None
    for key in ("block_entities", "BlockEntities", "blockEntities"):
        if key in level:
            entities = level[key]
            break
    if not isinstance(entities, list):
        raise GateError("ComputerId 11 chunk has no block-entity list")
    observed, expected = validate_computer_11_records(entities, phase)
    return {
        "phase": phase,
        "world": str(world.resolve()),
        "region": artifact,
        "chunk": [chunk_x, chunk_z],
        "slot": slot,
        "compression": compression,
        "observed": observed,
        "expected": expected,
        "on_preserved": True,
    }


def claim_fresh_gate_attempt(target: Path) -> dict[str, Any]:
    marker = target / ATTEMPT_MARKER_NAME
    value = {
        "schema": 1,
        "candidate": 11,
        "status": "RUNTIME_ATTEMPT_CLAIMED",
        "generated_at_utc": utc_now(),
        "target": str(target.resolve()),
        "reuse_allowed": False,
    }
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise GateError(
            "Candidate11 target already has a gate-attempt marker; failed or used worlds "
            "must never be reused"
        ) from exc
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return file_artifact(marker)


def bundle_binding(path: Path) -> dict[str, Any]:
    if not path.is_dir() or path.is_symlink():
        raise GateError(f"bundle directory is missing or linked: {path}")
    rows: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix().lower()):
        if item.is_dir():
            continue
        if not item.is_file() or item.is_symlink():
            raise GateError(f"bundle has a linked or non-file entry: {item}")
        rows.append(
            {
                "path": item.relative_to(path).as_posix(),
                "bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            }
        )
    if not rows:
        raise GateError(f"bundle is empty: {path}")
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda value: str(value["path"]).lower()):
        digest.update(str(row["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(row["sha256"]).upper().encode("ascii"))
        digest.update(b"\n")
    return {
        "root": str(path.resolve()),
        "files": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "bundle_sha256": digest.hexdigest().upper(),
    }


def critical_world_binding(world: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for relative in CRITICAL_WORLD_FILES:
        values[relative] = file_artifact(world / relative)
    tracks = world / "data" / "create_tracks.dat"
    values["data/create_tracks.dat"] = file_artifact(tracks) if tracks.is_file() else None
    return values


def copy_artifact(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file() or source.is_symlink():
        raise GateError(f"runtime artifact is missing or linked: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return file_artifact(destination)


def artifact_directory_binding(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix().lower()):
        if item.is_dir():
            continue
        if not item.is_file() or item.is_symlink():
            raise GateError(f"runtime artifact directory contains a linked entry: {item}")
        rows.append(
            {
                "path": item.relative_to(path).as_posix(),
                "bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            }
        )
    return {
        "root": str(path.resolve()),
        "files": len(rows),
        "bytes": sum(int(row["bytes"]) for row in rows),
        "manifest_sha256": stable_hash(rows),
        "artifacts": rows,
    }


def collect_failure_artifacts(target: Path, artifact_dir: Path) -> None:
    latest = target / "logs" / "latest.log"
    if latest.is_file() and not latest.is_symlink():
        shutil.copy2(latest, artifact_dir / "failure-final-server.latest.log")
    for state_path in sorted(artifact_dir.glob("client-round*.state.json")):
        try:
            value = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        for kind in ("stdout", "stderr"):
            source_value = value.get(kind)
            if not isinstance(source_value, str) or not source_value:
                continue
            source = Path(source_value)
            if source.is_file() and not source.is_symlink():
                destination = artifact_dir / f"failure-{state_path.stem}.{kind}.log"
                shutil.copy2(source, destination)


def wait_settle(seconds: float, health: Callable[[], None]) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        health()
        time.sleep(min(0.25, max(0.01, deadline - time.monotonic())))


def capture_round_artifacts(
    artifact_dir: Path,
    round_number: int,
    server: ServerSession,
    client: PrivateClientSession,
) -> dict[str, Any]:
    latest_copy = artifact_dir / f"server-round{round_number}.latest.log"
    return {
        "server_latest": copy_artifact(server.latest_log, latest_copy),
        "server_stdout": file_artifact(server.stdout_path),
        "server_stderr": file_artifact(server.stderr_path),
        "client_stdout": copy_artifact(
            client.stdout_path, artifact_dir / f"client-round{round_number}.stdout.log"
        ),
        "client_stderr": copy_artifact(
            client.stderr_path, artifact_dir / f"client-round{round_number}.stderr.log"
        ),
        "client_helper_stdout": file_artifact(client.helper_stdout_path),
        "client_helper_stderr": file_artifact(client.helper_stderr_path),
        "client_state": file_artifact(client.state_path),
    }


def run_round(
    *,
    target: Path,
    artifact_dir: Path,
    round_number: int,
    java: Path,
    powershell: Path,
    helper: Path,
    launcher: Path,
    client_root: Path,
    win_args: str,
    server_port: int,
    rcon_port: int,
    rcon_password: str,
    server_memory_mb: int,
    client_memory_mb: int,
    startup_timeout: int,
    join_timeout: int,
    client_launch_timeout: int,
    client_session_timeout: int,
    teleport_pause: float,
    settle_seconds: float,
) -> dict[str, Any]:
    server: ServerSession | None = None
    client: PrivateClientSession | None = None
    commands: list[dict[str, Any]] = []
    client_state: dict[str, Any] | None = None
    controlled_disconnect_baseline = 0
    try:
        server = ServerSession(
            target,
            artifact_dir,
            round_number,
            java,
            win_args,
            rcon_port,
            rcon_password,
            server_memory_mb,
        )
        server.wait_ready(startup_timeout)
        before_join_text = server.current_log()
        join_baseline = joined_count(before_join_text)
        loss_baseline = lost_count(before_join_text)
        client = PrivateClientSession(
            client_root,
            artifact_dir,
            round_number,
            server_port,
            powershell,
            helper,
            launcher,
            java,
            client_memory_mb,
            client_launch_timeout,
            client_session_timeout,
        )

        def runtime_health() -> None:
            server.assert_alive()
            client.assert_running()

        wait_until(
            lambda: joined_count(server.current_log()) == join_baseline + 1,
            join_timeout,
            f"Candidate11 client round {round_number} join",
            health=runtime_health,
        )
        if joined_count(server.current_log()) != join_baseline + 1:
            raise GateError("synthetic player joined more than once")
        if lost_count(server.current_log()) != loss_baseline:
            raise GateError("synthetic player disconnected before high-risk loading")

        final_teleport_at: float | None = None
        for planned in command_plan():
            if planned["kind"] == "save":
                if final_teleport_at is None:
                    raise GateError("RCON plan did not execute a teleport")
                remaining = settle_seconds - (time.monotonic() - final_teleport_at)
                if remaining > 0:
                    wait_settle(remaining, runtime_health)
            started = time.monotonic()
            response = server.command(str(planned["command"]))
            commands.append(
                {
                    **planned,
                    "response": response,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            if planned["kind"] == "teleport":
                final_teleport_at = time.monotonic()
                wait_settle(teleport_pause, runtime_health)

        client.assert_running()
        pre_client_stop_text = server.current_log()
        if joined_count(pre_client_stop_text) != join_baseline + 1:
            raise GateError("synthetic player join count changed during the round")
        if lost_count(pre_client_stop_text) != loss_baseline:
            raise GateError("synthetic player lost connection before controlled client stop")
        assert_no_strict_markers(pre_client_stop_text, f"server round {round_number}")
        controlled_disconnect_baseline = lost_count(pre_client_stop_text)
        client_state = client.stop()
        server.assert_alive()
        stop_response = server.stop()
        assert_no_strict_markers(
            "\n".join(
                (read_text(server.latest_log), read_text(server.stdout_path), read_text(server.stderr_path))
            ),
            f"server round {round_number}",
        )
        artifacts = capture_round_artifacts(
            artifact_dir, round_number, server, client
        )
        return {
            "round": round_number,
            "status": "PASS",
            "server_exit_code": server.process.returncode,
            "server_stop_response": stop_response,
            "join": {
                "username": SYNTHETIC_USERNAME,
                "baseline": join_baseline,
                "after": joined_count(read_text(server.latest_log)),
                "new_join_lines": joined_count(read_text(server.latest_log)) - join_baseline,
                "lost_before_controlled_client_stop": 0,
                "lost_after_controlled_client_stop": max(
                    0, lost_count(read_text(server.latest_log)) - controlled_disconnect_baseline
                ),
            },
            "commands": commands,
            "client_state": {
                "status": client_state.get("status"),
                "private_desktop": client_state.get("private_desktop"),
                "foreground_activation": client_state.get("foreground_activation"),
                "exit_code": client_state.get("exit_code"),
                "startup_evidence": client_state.get("startup_evidence"),
                "process_status": client_state.get("process_status"),
                "processes_closed": client_state.get("processes_closed"),
            },
            "strict_marker_hits": [],
            "artifacts": artifacts,
        }
    finally:
        if client is not None:
            client.abort()
        if server is not None:
            server.abort()


def check_ports_closed(server_port: int, rcon_port: int, voice_port: int | None) -> dict[str, Any]:
    tcp = {
        str(server_port): tcp_closed(server_port),
        str(rcon_port): tcp_closed(rcon_port),
    }
    udp = {str(voice_port): udp_free(voice_port)} if voice_port is not None else {}
    return {"tcp": tcp, "udp": udp, "all_closed": all(tcp.values()) and all(udp.values())}


def wait_ports_closed(
    server_port: int, rcon_port: int, voice_port: int | None, timeout: float = 30
) -> dict[str, Any]:
    return wait_until(
        lambda: (
            value
            if (value := check_ports_closed(server_port, rcon_port, voice_port))["all_closed"]
            else False
        ),
        timeout,
        "isolated ports to close",
        interval=0.25,
    )


def validate_prerequisites(
    target: Path,
    client_root: Path,
    java: Path,
    powershell: Path,
    helper: Path,
    launcher: Path,
    win_args: str,
) -> Path:
    for path in (java, powershell, helper, launcher, target / "user_jvm_args.txt"):
        if not path.is_file():
            raise GateError(f"required runtime file is missing: {path}")
    for path in (target / "world", target / "mods", client_root / "mods"):
        if not path.is_dir():
            raise GateError(f"required runtime directory is missing: {path}")
    relative = win_args[1:] if win_args.startswith("@") else win_args
    win_args_path = Path(relative)
    if not win_args_path.is_absolute():
        win_args_path = target / win_args_path
    if not win_args_path.is_file():
        raise GateError(f"NeoForge win_args is missing: {win_args_path}")
    for path in (
        target / "server.properties",
        target / "world",
        target / "mods",
        win_args_path,
        client_root,
        client_root / "mods",
    ):
        if forbidden_source_path(path.resolve()):
            raise GateError(f"runtime prerequisite resolves into the historical source: {path}")
    return win_args_path


def execute(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    target = args.target.resolve()
    client_root = args.client_root.resolve()
    report_path = args.report.resolve()
    prepare_report = args.prepare_report.resolve()
    client_prepare_report = args.client_prepare_report.resolve()
    if not is_within(report_path, OUTPUTS):
        raise GateError("report must be written under this workspace's outputs")
    artifact_dir = report_path.parent / (
        report_path.stem
        + "-artifacts-"
        + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    if artifact_dir.exists():
        raise GateError(f"refusing to reuse artifact directory: {artifact_dir}")
    artifact_dir.mkdir(parents=True)
    report: dict[str, Any] = {
        "schema": 1,
        "status": "NO_GO",
        "category": "candidate11_private_desktop_join_smoke",
        "generated_at_utc": utc_now(),
        "target": str(target),
        "client_root": str(client_root),
        "prepare_report": str(prepare_report),
        "client_prepare_report": str(client_prepare_report),
        "ports": {
            "server": args.server_port,
            "rcon": args.rcon_port,
            "voice": args.voice_port,
        },
        "identity": {"username": SYNTHETIC_USERNAME, "uuid": SYNTHETIC_UUID},
        "rounds": [],
        "cc_computer_on_checks": [],
        "local_resource_pack_checks": [],
        "server_resource_pack_checks": [],
        "blockers": [],
        "cleanup": {"attempted": False, "ports_closed": False},
        "safety": {
            "loopback_only": True,
            "private_desktop": True,
            "foreground_activation": False,
            "historical_source_forbidden": str(FORBIDDEN_SOURCE),
            "historical_source_read": False,
            "historical_source_written": False,
        },
    }
    runtime_attempted = False
    try:
        validate_paths(target, client_root, report_path)
        ports = [args.server_port, args.rcon_port]
        if args.voice_port is not None:
            ports.append(args.voice_port)
        for port in ports:
            validate_port_number(port)
        if len(set(ports)) != len(ports):
            raise GateError("server, RCON, and voice ports must be distinct")
        initial_ports = check_ports_closed(args.server_port, args.rcon_port, args.voice_port)
        if not initial_ports["all_closed"]:
            raise GateError(f"isolated port is already occupied: {initial_ports}")
        win_args_path = validate_prerequisites(
            target,
            client_root,
            args.java.resolve(),
            args.powershell.resolve(),
            args.private_helper.resolve(),
            args.client_launcher.resolve(),
            args.win_args,
        )
        prepare_binding = validate_prepare_report(
            prepare_report, target, args.server_port, args.rcon_port, args.voice_port
        )
        release_binding = validate_candidate11_release()
        server_bundle = bundle_binding(target / "mods")
        client_bundle = bundle_binding(client_root / "mods")
        runtime_bundle_binding = validate_candidate11_runtime_bundles(
            target, client_root, server_bundle, client_bundle
        )
        client_prepare_binding = validate_client_prepare_report(
            client_prepare_report, client_root, client_bundle
        )
        properties_path = target / "server.properties"
        whitelist_setup = normalize_disposable_whitelist(properties_path)
        properties = read_properties(properties_path)
        validate_server_properties(properties, args.server_port, args.rcon_port)
        local_resource_pack_setup = configure_local_world_resource_pack(client_root)
        resource_pack_setup = configure_disposable_resource_pack_rejection(
            client_root, args.server_port, properties, properties_path
        )
        initial_binding = critical_world_binding(target / "world")
        initial_computer = computer_11_on_evidence(target / "world", "before_round_1")
        report["cc_computer_on_checks"].append(initial_computer)
        report["bindings"] = {
            "candidate11_release": release_binding,
            "prepare_report": prepare_binding,
            "client_prepare_report": client_prepare_binding,
            "tools": {
                "orchestrator": file_artifact(Path(__file__)),
                "private_client_helper": file_artifact(args.private_helper.resolve()),
                "client_launcher": file_artifact(args.client_launcher.resolve()),
            },
            "runtime": {
                "java": file_artifact(args.java.resolve()),
                "powershell": file_artifact(args.powershell.resolve()),
                "user_jvm_args": file_artifact(target / "user_jvm_args.txt"),
                "win_args": file_artifact(win_args_path),
                "server_properties": file_artifact(properties_path),
                "server_mods": server_bundle,
                "client_mods": client_bundle,
                "candidate11_bundles": runtime_bundle_binding,
            },
            "world_before": initial_binding,
        }
        report["disposable_setup"] = {
            "whitelist": whitelist_setup,
            "server_resource_pack": resource_pack_setup,
            "local_world_resource_pack": local_resource_pack_setup,
        }
        local_pack_expectation = {
            "expected_sha256": local_resource_pack_setup["destination"]["after"][
                "sha256"
            ],
            "expected_bytes": local_resource_pack_setup["destination"]["after"][
                "bytes"
            ],
        }
        server_pack_expectation = {
            "expected_properties_sha256": resource_pack_setup["server_properties"][
                "after_sha256"
            ],
            "expected_properties_fingerprint": resource_pack_setup[
                "server_properties"
            ]["semantic_fingerprint"],
        }
        rcon_password = properties["rcon.password"]
        report["attempt_marker"] = claim_fresh_gate_attempt(target)
        for round_number in (1, 2):
            pack_check = validate_local_world_resource_pack(
                client_root, **local_pack_expectation
            )
            report["local_resource_pack_checks"].append(
                {"phase": f"before_round_{round_number}", **pack_check}
            )
            server_pack_check = validate_disposable_resource_pack_rejection(
                client_root,
                args.server_port,
                properties_path,
                **server_pack_expectation,
            )
            report["server_resource_pack_checks"].append(
                {"phase": f"before_round_{round_number}", **server_pack_check}
            )
            runtime_attempted = True
            round_report = run_round(
                target=target,
                artifact_dir=artifact_dir,
                round_number=round_number,
                java=args.java.resolve(),
                powershell=args.powershell.resolve(),
                helper=args.private_helper.resolve(),
                launcher=args.client_launcher.resolve(),
                client_root=client_root,
                win_args=args.win_args,
                server_port=args.server_port,
                rcon_port=args.rcon_port,
                rcon_password=rcon_password,
                server_memory_mb=args.server_memory_mb,
                client_memory_mb=args.client_memory_mb,
                startup_timeout=args.startup_timeout_seconds,
                join_timeout=args.join_timeout_seconds,
                client_launch_timeout=args.client_launch_timeout_seconds,
                client_session_timeout=args.client_session_timeout_seconds,
                teleport_pause=args.teleport_pause_seconds,
                settle_seconds=args.settle_seconds,
            )
            report["rounds"].append(round_report)
            wait_ports_closed(args.server_port, args.rcon_port, args.voice_port)
            computer_check = computer_11_on_evidence(
                target / "world", f"after_round_{round_number}"
            )
            report["cc_computer_on_checks"].append(computer_check)
            if round_number == 1:
                time.sleep(2)
        final_pack_check = validate_local_world_resource_pack(
            client_root, **local_pack_expectation
        )
        report["local_resource_pack_checks"].append(
            {"phase": "after_round_2", **final_pack_check}
        )
        final_server_pack_check = validate_disposable_resource_pack_rejection(
            client_root,
            args.server_port,
            properties_path,
            **server_pack_expectation,
        )
        report["server_resource_pack_checks"].append(
            {"phase": "after_round_2", **final_server_pack_check}
        )
        report["bindings"]["world_after"] = critical_world_binding(target / "world")
        report["strict_assertions"] = {
            "round_count": len(report["rounds"]),
            "round_sequence": [value["round"] for value in report["rounds"]],
            "each_round_one_join": all(
                value["join"]["new_join_lines"] == 1 for value in report["rounds"]
            ),
            "each_round_clean_server_exit": all(
                value["server_exit_code"] == 0 for value in report["rounds"]
            ),
            "each_round_private_client": all(
                valid_clean_private_client_state(value["client_state"])
                for value in report["rounds"]
            ),
            "each_round_high_risk_commands": all(
                [item["command"] for item in value["commands"]]
                == [item["command"] for item in command_plan()]
                for value in report["rounds"]
            ),
            "strict_marker_hits": 0,
            "computer_11_on_preserved": (
                [value["phase"] for value in report["cc_computer_on_checks"]]
                == ["before_round_1", "after_round_1", "after_round_2"]
                and all(
                    value["on_preserved"] is True
                    and value["observed"]["ComputerId"] == CC_COMPUTER_ID
                    and value["observed"]["On"] == 1
                    for value in report["cc_computer_on_checks"]
                )
            ),
            "candidate11_exact_bundles": runtime_bundle_binding[
                "exact_52_jar_bundles"
            ],
            "fresh_world_single_attempt": report["attempt_marker"]["sha256"]
            == sha256_file(target / ATTEMPT_MARKER_NAME),
            "local_resource_pack_enabled": (
                len(report["local_resource_pack_checks"]) == 3
                and all(
                    value["enabled_exactly_once"]
                    for value in report["local_resource_pack_checks"]
                )
            ),
            "remote_resource_pack_declined": (
                len(report["server_resource_pack_checks"]) == 3
                and all(
                    value["client_response"] == "DECLINED"
                    and value["accept_textures"] is False
                    and value["exact_payload_validated"] is True
                    and value["server_properties"]["semantic_unchanged"] is True
                    for value in report["server_resource_pack_checks"]
                )
            ),
        }
        assertions = report["strict_assertions"]
        if (
            assertions["round_count"] != 2
            or assertions["round_sequence"] != [1, 2]
            or assertions["strict_marker_hits"] != 0
            or not all(
                assertions[key]
                for key in (
                    "each_round_one_join",
                    "each_round_clean_server_exit",
                    "each_round_private_client",
                    "each_round_high_risk_commands",
                    "computer_11_on_preserved",
                    "candidate11_exact_bundles",
                    "fresh_world_single_attempt",
                    "local_resource_pack_enabled",
                    "remote_resource_pack_declined",
                )
            )
        ):
            raise GateError(f"final strict assertion failed: {report['strict_assertions']}")
        report["status"] = "PASS"
    except Exception as exc:  # The evidence report must fail closed.
        report["blockers"].append(
            {"type": type(exc).__name__, "message": str(exc)}
        )
    finally:
        report["cleanup"]["attempted"] = True
        try:
            cleanup = (
                wait_ports_closed(
                    args.server_port, args.rcon_port, args.voice_port, timeout=45
                )
                if runtime_attempted
                else check_ports_closed(args.server_port, args.rcon_port, args.voice_port)
            )
        except Exception as exc:
            cleanup = check_ports_closed(args.server_port, args.rcon_port, args.voice_port)
            report["blockers"].append(
                {"type": "PORT_CLEANUP_FAILURE", "message": str(exc)}
            )
            report["status"] = "NO_GO"
        report["cleanup"]["port_state"] = cleanup
        report["cleanup"]["ports_closed"] = cleanup["all_closed"]
        if runtime_attempted and report["status"] != "PASS":
            try:
                collect_failure_artifacts(target, artifact_dir)
            except Exception as exc:
                report["blockers"].append(
                    {"type": "ARTIFACT_COLLECTION_FAILURE", "message": str(exc)}
                )
        try:
            report["runtime_artifacts"] = artifact_directory_binding(artifact_dir)
        except Exception as exc:
            report["blockers"].append(
                {"type": "ARTIFACT_BINDING_FAILURE", "message": str(exc)}
            )
        report["artifact_directory"] = str(artifact_dir.resolve())
        report["generated_at_utc_completed"] = utc_now()
        if report["blockers"] or not cleanup["all_closed"]:
            report["status"] = "NO_GO"
    digest = atomic_json(report_path, report)
    return report, digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Candidate11 client's two-round hidden join gate"
    )
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--prepare-report", type=Path, required=True)
    parser.add_argument("--client-prepare-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--rcon-port", type=int, required=True)
    parser.add_argument("--voice-port", type=int)
    parser.add_argument("--java", type=Path, default=DEFAULT_JAVA)
    parser.add_argument("--powershell", type=Path, default=DEFAULT_POWERSHELL)
    parser.add_argument("--private-helper", type=Path, default=DEFAULT_PRIVATE_HELPER)
    parser.add_argument("--client-launcher", type=Path, default=DEFAULT_CLIENT_LAUNCHER)
    parser.add_argument(
        "--win-args",
        default="@libraries/net/neoforged/neoforge/21.1.241/win_args.txt",
    )
    parser.add_argument("--server-memory-mb", type=int, default=4096)
    parser.add_argument("--client-memory-mb", type=int, default=2048)
    parser.add_argument("--startup-timeout-seconds", type=int, default=300)
    parser.add_argument("--join-timeout-seconds", type=int, default=180)
    parser.add_argument("--client-launch-timeout-seconds", type=int, default=150)
    parser.add_argument("--client-session-timeout-seconds", type=int, default=300)
    parser.add_argument("--teleport-pause-seconds", type=float, default=0.25)
    parser.add_argument("--settle-seconds", type=float, default=15.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report, digest = execute(args)
    except Exception as exc:
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "report": str(args.report.resolve()),
                "report_sha256": digest,
                "ports_closed": report["cleanup"]["ports_closed"],
                "foreground_activation": False,
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
