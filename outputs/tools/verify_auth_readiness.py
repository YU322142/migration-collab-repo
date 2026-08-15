#!/usr/bin/env python3
"""Fail-closed, offline verifier for the EasyAuth -> XiyusLogin handoff.

The verifier reads only a stopped/staged EasyAuth copy.  It never opens a
network connection and never writes to the source, staging world, or mod
directory.  It binds the source SQLite bytes, converted JSON semantics, the
candidate JAR digest, and two independent converter passes into one small
machine-readable report.

Exit codes:

* 0: data gates and the supplied live-login evidence are complete;
* 1: an integrity/schema/data gate failed;
* 2: data gates passed, but live-login evidence was not supplied or is
  incomplete.

The default expected counts are the current server's 49 records (29 BCrypt,
20 empty, 34 UUIDs).  A changed source therefore fails closed until the
operator explicitly updates the expected counts and reruns the gate.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_EXPECTED_RECORDS = 49
DEFAULT_EXPECTED_BCRYPT = 29
DEFAULT_EXPECTED_EMPTY = 20
DEFAULT_EXPECTED_UUIDS = 34
DEFAULT_EXPECTED_JAR_BYTES = 169896
DEFAULT_EXPECTED_JAR_SHA256 = (
    "D1A0FB4EE7E60C5893A7A2CBCAFA21434555AE5CC3F725AAEF59F8312169EE08"
)
EXPECTED_JAR_VERSION = "1.4-migration3"
EXPECTED_SECURITY_PROPERTIES = {
    "schema": "1",
    "enableIpSession.default": "false",
    "passwordReset.storage": "bcrypt",
    "passwordReset.bcryptCost": "12",
    "passwordReset.adminDisplay": "redacted",
    "password.storage": "bcrypt",
    "password.bcryptCost": "12",
    "password.legacySha256": "verify-and-upgrade",
    "passwordReset.clientTransport": "disabled-by-default",
}
VERSION_SECURITY_PROPERTIES = {
    "1.4-migration3": {},
    "1.4-migration4": {"unauthenticatedBlindness.default": "false"},
}
REQUIRED_LIVE_SCENARIOS = (
    "java_existing_bcrypt_correct",
    "java_existing_bcrypt_wrong_rejected",
    "java_empty_record_registration_policy",
    "java_restart_reauthentication",
    "bedrock_floodgate_uuid_mapping",
    "proxy_ip_session_policy",
)
EXPECTED_OUTPUT_RELATIVE = "world/xiyus_player_data.json"
EXPECTED_FIELDS = {
    "username",
    "uuid",
    "passwordHash",
    "registrationTime",
    "lastLoginTime",
    "loginCount",
    "lastIp",
    "lastAuthenticatedTime",
    "loginTries",
    "lastKickedTime",
    "onlineAccount",
    "sourceDataVersion",
    "legacyPremiumAutoLogin",
    "passwordScheme",
}
PASSWORD_KEYS = {"$2a$", "$2b$", "$2y$"}
MOD_ID_RE = re.compile(r"\bmodId\s*=\s*['\"]xiyuslogin['\"]")
MOD_VERSION_RE = re.compile(r"\bversion\s*=\s*['\"]([^'\"]+)['\"]")
NEOFORGE_RANGE_RE = re.compile(
    r"versionRange\s*=\s*['\"]\[21\.1\.215,21\.2\.0\)['\"]"
)
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
EXPECTED_RUNTIME_JARS = {
    "bcrypt": {
        "group": "at.favre.lib",
        "version": "0.10.2",
        "path": "META-INF/jarjar/bcrypt-0.10.2.jar",
        "required_class": "at/favre/lib/crypto/bcrypt/BCrypt.class",
    },
    "bytes": {
        "group": "at.favre.lib",
        "version": "1.5.0",
        "path": "META-INF/jarjar/bytes-1.5.0.jar",
        "required_class": "at/favre/lib/bytes/Bytes.class",
    },
}


class GateError(RuntimeError):
    """An expected, reportable gate failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def source_input_state(database: Path) -> dict[str, dict[str, Any]]:
    """Hash the SQLite main file and any sidecars as one immutable input set."""
    result: dict[str, dict[str, Any]] = {}
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(database) + suffix)
        if path.is_symlink():
            raise GateError("SOURCE_SQLITE_SIDECAR_INVALID")
        if not path.exists():
            continue
        if not path.is_file():
            raise GateError("SOURCE_SQLITE_SIDECAR_INVALID")
        before = path.stat()
        digest = sha256(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise GateError("SOURCE_SQLITE_INPUT_CHANGED_DURING_HASH")
        result[path.name] = {
            "bytes": after.st_size,
            "sha256": digest,
            "mtime_ns": after.st_mtime_ns,
        }
    if "easyauth.db" not in result:
        raise GateError("SOURCE_DB_MISSING_OR_SYMLINK")
    return result


def ensure_file(path: Path, code: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise GateError(code)
    return path.resolve()


def ensure_under(path: Path, root: Path, code: str) -> Path:
    path = path.resolve()
    root = root.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise GateError(code) from exc
    return path


def relative_or_name(path: Path, root: Path | None = None) -> str:
    if root is not None:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.name


def report_path_is_safe(report: Path, source_root: Path, staging_root: Path) -> bool:
    report = report.resolve()
    for root in (source_root.resolve(), staging_root.resolve()):
        try:
            report.relative_to(root)
        except ValueError:
            continue
        return False
    return True


def normalize_time(value: object) -> str | None:
    if not value:
        return None
    text = str(value)
    base = text.split("[", 1)[0]
    try:
        parsed = datetime.fromisoformat(base.replace("Z", "+00:00"))
    except ValueError:
        return text
    result = parsed.replace(tzinfo=None).isoformat(timespec="microseconds")
    return None if result == "1970-01-01T00:00:00.000000" else result


def classify_password(value: object) -> str:
    password = str(value or "")
    if not password:
        return "empty"
    if any(password.startswith(prefix) for prefix in PASSWORD_KEYS) and len(password) == 60:
        return "bcrypt"
    raise GateError("SOURCE_PASSWORD_HASH_UNSUPPORTED")


def source_records(database: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Read and normalize source records without retaining them in the report."""
    uri = "file:" + database.as_posix() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise GateError("SOURCE_SQLITE_OPEN_FAILED") from exc
    records: dict[str, dict[str, Any]] = {}
    bcrypt = empty = uuid_present = 0
    try:
        connection.execute("pragma query_only=on")
        integrity = [row[0] for row in connection.execute("pragma integrity_check")]
        if integrity != ["ok"]:
            raise GateError("SOURCE_SQLITE_INTEGRITY_FAILED")
        columns = {row[1] for row in connection.execute("pragma table_info(easyauth)")}
        required = {"username", "username_lower", "uuid", "data"}
        if not required.issubset(columns):
            raise GateError("SOURCE_SQLITE_SCHEMA_UNSUPPORTED")
        rows = connection.execute(
            "select username, username_lower, uuid, data from easyauth order by id"
        ).fetchall()
        for username, username_lower, db_uuid, raw_data in rows:
            key = str(username_lower).lower()
            if not key or key in records:
                raise GateError("SOURCE_USERNAME_KEY_INVALID")
            try:
                data = json.loads(raw_data)
            except (TypeError, json.JSONDecodeError) as exc:
                raise GateError("SOURCE_RECORD_JSON_INVALID") from exc
            if not isinstance(data, dict):
                raise GateError("SOURCE_RECORD_JSON_INVALID")
            if not isinstance(username, str) or not isinstance(username_lower, str):
                raise GateError("SOURCE_USERNAME_KEY_INVALID")
            scheme = classify_password(data.get("password", ""))
            if scheme == "bcrypt":
                bcrypt += 1
            else:
                empty += 1
            parsed_uuid: str | None = None
            if db_uuid:
                try:
                    parsed_uuid = str(uuid.UUID(str(db_uuid)))
                except (ValueError, AttributeError) as exc:
                    raise GateError("SOURCE_UUID_INVALID") from exc
                uuid_present += 1
            try:
                login_tries = int(data.get("login_tries", 0))
                source_data_version = int(data.get("data_version", 1))
            except (TypeError, ValueError) as exc:
                raise GateError("SOURCE_RECORD_NUMERIC_FIELD_INVALID") from exc
            records[key] = {
                "username": username,
                "uuid": parsed_uuid,
                "passwordHash": str(data.get("password", "")),
                "registrationTime": normalize_time(data.get("registration_date")),
                "lastLoginTime": normalize_time(data.get("last_authenticated_date")),
                "loginCount": 0,
                "lastIp": data.get("last_ip", ""),
                "lastAuthenticatedTime": normalize_time(data.get("last_authenticated_date")),
                "loginTries": login_tries,
                "lastKickedTime": normalize_time(data.get("last_kicked_date")),
                "onlineAccount": data.get("online_account", "UNKNOWN"),
                "sourceDataVersion": source_data_version,
                "legacyPremiumAutoLogin": scheme == "empty" and parsed_uuid is not None,
                "passwordScheme": scheme,
            }
    except sqlite3.Error as exc:
        raise GateError("SOURCE_SQLITE_QUERY_FAILED") from exc
    finally:
        connection.close()
    summary = {
        "records": len(records),
        "bcrypt": bcrypt,
        "empty": empty,
        "uuid_present": uuid_present,
        "legacy_premium_auto_login": sum(
            bool(value["legacyPremiumAutoLogin"]) for value in records.values()
        ),
        "plaintext_stored": False,
    }
    return records, summary


def validate_output(output: Path, expected: dict[str, dict[str, Any]]) -> dict[str, Any]:
    try:
        value = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("OUTPUT_JSON_INVALID") from exc
    if not isinstance(value, dict) or set(value) != set(expected):
        raise GateError("OUTPUT_RECORD_SET_MISMATCH")
    for key, expected_record in expected.items():
        actual = value.get(key)
        if not isinstance(actual, dict) or set(actual) != EXPECTED_FIELDS:
            raise GateError("OUTPUT_SCHEMA_MISMATCH")
        if actual != expected_record:
            raise GateError("OUTPUT_SEMANTICS_MISMATCH")
        # This is intentionally an in-memory check; no password material is
        # copied into the report.
        scheme = classify_password(actual.get("passwordHash", ""))
        if scheme != actual.get("passwordScheme"):
            raise GateError("OUTPUT_PASSWORD_SCHEME_MISMATCH")
        if "password" in actual:
            raise GateError("OUTPUT_PLAINTEXT_FIELD_PRESENT")
    return {
        "records": len(value),
        "bytes": output.stat().st_size,
        "sha256": sha256(output),
        "semantics_match_source": True,
    }


def validate_json_report(
    sqlite_report: Path,
    migration_report: Path,
    source: Path,
    output: Path,
    output_summary: dict[str, Any],
    source_summary: dict[str, Any],
) -> dict[str, Any]:
    try:
        sqlite_value = json.loads(sqlite_report.read_text(encoding="utf-8"))
        migration_value = json.loads(migration_report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("AUTH_REPORT_INVALID") from exc
    if not isinstance(sqlite_value, dict) or not isinstance(migration_value, dict):
        raise GateError("AUTH_REPORT_INVALID")
    source_files = sqlite_value.get("source_copy_files", {})
    if not isinstance(source_files, dict):
        raise GateError("SQLITE_REPORT_SOURCE_FILES_INVALID")
    source_file = source_files.get("easyauth.db", {})
    if not isinstance(source_file, dict):
        raise GateError("SQLITE_REPORT_SOURCE_FILE_INVALID")
    if source_file.get("sha256", "").upper() != sha256(source):
        raise GateError("SQLITE_REPORT_SOURCE_HASH_MISMATCH")
    if sqlite_value.get("source_integrity_check") != ["ok"]:
        raise GateError("SQLITE_REPORT_SOURCE_INTEGRITY_MISMATCH")
    if sqlite_value.get("snapshot_integrity_check") != ["ok"]:
        raise GateError("SQLITE_REPORT_SNAPSHOT_INTEGRITY_MISMATCH")
    if int(sqlite_value.get("records", -1)) != source_summary["records"]:
        raise GateError("SQLITE_REPORT_RECORD_COUNT_MISMATCH")
    if int(migration_value.get("records", -1)) != source_summary["records"]:
        raise GateError("AUTH_REPORT_RECORD_COUNT_MISMATCH")
    if migration_value.get("hashes") != {
        "bcrypt": source_summary["bcrypt"],
        "empty": source_summary["empty"],
    }:
        raise GateError("AUTH_REPORT_HASH_CLASSIFICATION_MISMATCH")
    if int(migration_value.get("uuidPresent", -1)) != source_summary["uuid_present"]:
        raise GateError("AUTH_REPORT_UUID_COUNT_MISMATCH")
    if migration_value.get("plaintextStored") is not False:
        raise GateError("AUTH_REPORT_PLAINTEXT_FLAG")
    if migration_value.get("outputSha256", "").upper() != output_summary["sha256"]:
        raise GateError("AUTH_REPORT_OUTPUT_HASH_MISMATCH")
    if Path(str(migration_value.get("output", ""))).name != output.name:
        raise GateError("AUTH_REPORT_OUTPUT_PATH_MISMATCH")
    return {
        "sqlite_report_sha256": sha256(sqlite_report),
        "migration_report_sha256": sha256(migration_report),
        "source_report_hash_matches": True,
        "output_report_hash_matches": True,
    }


def expected_security_properties(version: str) -> dict[str, str]:
    try:
        additions = VERSION_SECURITY_PROPERTIES[version]
    except KeyError as exc:
        raise GateError("CANDIDATE_JAR_VERSION_UNSUPPORTED") from exc
    return {**EXPECTED_SECURITY_PROPERTIES, **additions}


def validate_jar(
    jar: Path,
    expected_sha256: str,
    expected_bytes: int,
    expected_version: str = EXPECTED_JAR_VERSION,
) -> dict[str, Any]:
    if jar.stat().st_size != expected_bytes or sha256(jar) != expected_sha256.upper():
        raise GateError("CANDIDATE_JAR_DIGEST_MISMATCH")
    try:
        with zipfile.ZipFile(jar) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise GateError("CANDIDATE_JAR_DUPLICATE_ENTRIES")
            metadata = archive.read("META-INF/neoforge.mods.toml").decode("utf-8")
            security_text = archive.read(
                "META-INF/xiyuslogin-security.properties"
            ).decode("utf-8")
            jarjar_metadata = json.loads(
                archive.read("META-INF/jarjar/metadata.json").decode("utf-8")
            )
            runtime_dependencies: dict[str, dict[str, Any]] = {}
            raw_runtime_jars = jarjar_metadata.get("jars")
            if not isinstance(raw_runtime_jars, list) or len(raw_runtime_jars) != len(
                EXPECTED_RUNTIME_JARS
            ):
                raise GateError("CANDIDATE_JAR_RUNTIME_DEPENDENCIES_MISMATCH")
            by_artifact: dict[str, dict[str, Any]] = {}
            for item in raw_runtime_jars:
                if not isinstance(item, dict) or not isinstance(item.get("identifier"), dict):
                    raise GateError("CANDIDATE_JAR_RUNTIME_DEPENDENCIES_MISMATCH")
                artifact = item["identifier"].get("artifact")
                if not isinstance(artifact, str) or artifact in by_artifact:
                    raise GateError("CANDIDATE_JAR_RUNTIME_DEPENDENCIES_MISMATCH")
                by_artifact[artifact] = item
            if set(by_artifact) != set(EXPECTED_RUNTIME_JARS):
                raise GateError("CANDIDATE_JAR_RUNTIME_DEPENDENCIES_MISMATCH")
            for artifact, expected in EXPECTED_RUNTIME_JARS.items():
                item = by_artifact[artifact]
                version = item.get("version")
                if (
                    item.get("identifier")
                    != {"group": expected["group"], "artifact": artifact}
                    or not isinstance(version, dict)
                    or version.get("artifactVersion") != expected["version"]
                    or item.get("path") != expected["path"]
                    or item.get("isObfuscated") is not False
                ):
                    raise GateError("CANDIDATE_JAR_RUNTIME_DEPENDENCIES_MISMATCH")
                nested_bytes = archive.read(expected["path"])
                with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
                    if expected["required_class"] not in nested.namelist():
                        raise GateError("CANDIDATE_JAR_RUNTIME_CLASS_MISSING:" + artifact)
                runtime_dependencies[artifact] = {
                    "group": expected["group"],
                    "version": expected["version"],
                    "path": expected["path"],
                    "bytes": len(nested_bytes),
                    "sha256": hashlib.sha256(nested_bytes).hexdigest().upper(),
                    "required_class_present": True,
                }
    except (OSError, KeyError, UnicodeError, zipfile.BadZipFile) as exc:
        raise GateError("CANDIDATE_JAR_METADATA_INVALID") from exc
    except json.JSONDecodeError as exc:
        raise GateError("CANDIDATE_JAR_RUNTIME_DEPENDENCIES_MISMATCH") from exc
    if not MOD_ID_RE.search(metadata):
        raise GateError("CANDIDATE_JAR_MOD_ID_MISMATCH")
    version_match = MOD_VERSION_RE.search(metadata)
    if version_match is None or version_match.group(1) != expected_version:
        raise GateError("CANDIDATE_JAR_VERSION_MISMATCH")
    if not NEOFORGE_RANGE_RE.search(metadata):
        raise GateError("CANDIDATE_JAR_NEOFORGE_RANGE_MISMATCH")
    security: dict[str, str] = {}
    for raw_line in security_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise GateError("CANDIDATE_JAR_SECURITY_MANIFEST_INVALID")
        key, value = line.split("=", 1)
        security[key.strip()] = value.strip()
    if security != expected_security_properties(expected_version):
        raise GateError("CANDIDATE_JAR_SECURITY_MANIFEST_MISMATCH")
    return {
        "file": jar.name,
        "bytes": expected_bytes,
        "sha256": expected_sha256.upper(),
        "mod_id": "xiyuslogin",
        "version": version_match.group(1),
        "metadata": "META-INF/neoforge.mods.toml",
        "security_manifest": "META-INF/xiyuslogin-security.properties",
        "security_defaults": security,
        "runtime_dependencies": runtime_dependencies,
    }


def run_converter_twice(
    migration_tool: Path,
    source: Path,
    output: Path,
    work_parent: Path,
) -> dict[str, Any]:
    temp_root = Path(tempfile.mkdtemp(prefix=".auth-readiness-", dir=str(work_parent)))
    try:
        hashes: list[str] = []
        manifest_summaries: list[dict[str, Any]] = []
        for index in (1, 2):
            generated = temp_root / f"pass{index}" / "world" / output.name
            manifest = temp_root / f"pass{index}" / "manifest.json"
            env = os.environ.copy()
            env.update({"PYTHONDONTWRITEBYTECODE": "1", "TEMP": str(temp_root), "TMP": str(temp_root)})
            completed = subprocess.run(
                [
                    sys.executable,
                    str(migration_tool),
                    str(source),
                    str(generated),
                    "--manifest",
                    str(manifest),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=120,
            )
            if completed.returncode != 0:
                raise GateError("CONVERTER_PASS_FAILED")
            hashes.append(sha256(generated))
            manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_summaries.append(
                {
                    "records": manifest_value.get("records"),
                    "hashes": manifest_value.get("hashes"),
                    "uuidPresent": manifest_value.get("uuidPresent"),
                    "plaintextStored": manifest_value.get("plaintextStored"),
                    "outputSha256": manifest_value.get("outputSha256"),
                }
            )
        if hashes[0] != hashes[1] or manifest_summaries[0] != manifest_summaries[1]:
            raise GateError("CONVERTER_NOT_IDEMPOTENT")
        if hashes[0] != sha256(output):
            raise GateError("OUTPUT_DIFFERS_FROM_CONVERTER")
        return {
            "passes": 2,
            "output_sha256_pass1": hashes[0],
            "output_sha256_pass2": hashes[1],
            "hashes_equal": True,
            "manifest_summaries_equal": True,
            "output_matches_converter": True,
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def validate_live_report(
    path: Path | None,
    source_hash: str,
    output_hash: str,
    jar_hash: str,
) -> dict[str, Any]:
    base = {
        "required_scenarios": list(REQUIRED_LIVE_SCENARIOS),
        "status": "NOT_PROVIDED",
        "evidence_bound": False,
    }
    if path is None:
        return base
    if path.is_symlink() or not path.is_file():
        raise GateError("LIVE_REPORT_MISSING_OR_SYMLINK")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GateError("LIVE_REPORT_INVALID") from exc
    scenarios = value.get("scenarios")
    if (
        value.get("schema") != 1
        or value.get("contains_secrets") is not False
        or value.get("tested_with_secrets") is not False
        or not isinstance(scenarios, dict)
    ):
        raise GateError("LIVE_REPORT_INVALID")
    if set(scenarios) != set(REQUIRED_LIVE_SCENARIOS):
        raise GateError("LIVE_REPORT_SCENARIOS_INCOMPLETE")
    if str(value.get("source_sha256", "")).upper() != source_hash:
        raise GateError("LIVE_REPORT_SOURCE_BINDING_MISMATCH")
    if str(value.get("output_sha256", "")).upper() != output_hash:
        raise GateError("LIVE_REPORT_OUTPUT_BINDING_MISMATCH")
    if str(value.get("candidate_jar_sha256", "")).upper() != jar_hash:
        raise GateError("LIVE_REPORT_JAR_BINDING_MISMATCH")

    report_status = str(value.get("status", ""))
    if report_status != "PASS":
        if not report_status.startswith("BLOCKED_"):
            raise GateError("LIVE_REPORT_NOT_PASS")
        scenario_status: dict[str, str] = {}
        for name in REQUIRED_LIVE_SCENARIOS:
            scenario = scenarios[name]
            if not isinstance(scenario, dict):
                raise GateError("LIVE_REPORT_SCENARIO_INVALID:" + name)
            status = str(scenario.get("status", ""))
            if status != "PASS_SYNTHETIC_NETWORK_RUNTIME" and not status.startswith(
                "BLOCKED_"
            ):
                raise GateError("LIVE_REPORT_SCENARIO_STATUS_INVALID:" + name)
            scenario_status[name] = status
        if not any(status.startswith("BLOCKED_") for status in scenario_status.values()):
            raise GateError("LIVE_REPORT_BLOCKED_WITHOUT_BLOCKER")
        return {
            "required_scenarios": list(REQUIRED_LIVE_SCENARIOS),
            "status": report_status,
            "evidence_bound": False,
            "report": str(path.resolve()),
            "report_sha256": sha256(path),
            "scenario_status": scenario_status,
        }

    evidence_root = path.parent.resolve()
    scenario_evidence: dict[str, list[dict[str, Any]]] = {}
    for name in REQUIRED_LIVE_SCENARIOS:
        scenario = scenarios[name]
        if not isinstance(scenario, dict) or str(scenario.get("status", "")).upper() != "PASS":
            raise GateError("LIVE_REPORT_SCENARIO_NOT_PASS:" + name)
        artifacts = scenario.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise GateError("LIVE_REPORT_SCENARIO_ARTIFACTS_MISSING:" + name)
        normalized: list[dict[str, Any]] = []
        for item in artifacts:
            if not isinstance(item, dict):
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_INVALID:" + name)
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute():
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_PATH_INVALID:" + name)
            artifact_candidate = evidence_root / raw_path
            if artifact_candidate.is_symlink():
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_SYMLINK:" + name)
            artifact = artifact_candidate.resolve()
            try:
                relative = artifact.relative_to(evidence_root)
            except ValueError as exc:
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_OUTSIDE_ROOT:" + name) from exc
            if not artifact.is_file():
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_MISSING:" + name)
            if item.get("contains_secrets") is not False:
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_SECRET_FLAG:" + name)
            expected_hash = item.get("sha256")
            if not isinstance(expected_hash, str) or not HEX64_RE.fullmatch(expected_hash):
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_HASH_INVALID:" + name)
            actual_hash = sha256(artifact)
            if actual_hash != expected_hash.upper():
                raise GateError("LIVE_REPORT_SCENARIO_ARTIFACT_HASH_MISMATCH:" + name)
            normalized.append(
                {
                    "path": relative.as_posix(),
                    "bytes": artifact.stat().st_size,
                    "sha256": actual_hash,
                    "kind": str(item.get("kind", "unspecified")),
                }
            )
        scenario_evidence[name] = normalized
    return {
        "required_scenarios": list(REQUIRED_LIVE_SCENARIOS),
        "status": "PASS",
        "evidence_bound": True,
        "report": str(path.resolve()),
        "report_sha256": sha256(path),
        "scenario_evidence": scenario_evidence,
    }


def build_report(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source = ensure_file(args.source_db, "SOURCE_DB_MISSING_OR_SYMLINK")
    staging = args.staging_root.resolve()
    if not staging.is_dir():
        raise GateError("STAGING_ROOT_MISSING")
    ensure_under(source, args.allowed_source_root, "SOURCE_DB_OUTSIDE_ALLOWED_ROOT")
    output = ensure_file(args.output, "OUTPUT_MISSING_OR_SYMLINK")
    ensure_under(output, staging, "OUTPUT_OUTSIDE_STAGING_ROOT")
    if relative_or_name(output, staging) != EXPECTED_OUTPUT_RELATIVE:
        raise GateError("OUTPUT_PATH_UNEXPECTED")
    sqlite_report = ensure_file(args.sqlite_report, "SQLITE_REPORT_MISSING")
    migration_report = ensure_file(args.migration_report, "MIGRATION_REPORT_MISSING")
    jar = ensure_file(args.candidate_jar, "CANDIDATE_JAR_MISSING_OR_SYMLINK")
    migration_tool = ensure_file(args.migration_tool, "MIGRATION_TOOL_MISSING_OR_SYMLINK")
    report_path = args.report.resolve()
    if report_path == source or report_path == output:
        raise GateError("REPORT_OVERLAPS_INPUT")
    if not report_path_is_safe(
        report_path, args.allowed_source_root, args.staging_root
    ):
        raise GateError("REPORT_INSIDE_SOURCE_ROOT")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    source_files_before = source_input_state(source)
    source_before = source_files_before["easyauth.db"]["sha256"]
    if source_before != args.expected_source_sha256.upper():
        raise GateError("SOURCE_DIGEST_MISMATCH")
    expected, account_summary = source_records(source)
    output_summary = validate_output(output, expected)
    report_summary = validate_json_report(
        sqlite_report, migration_report, source, output, output_summary, account_summary
    )
    jar_summary = validate_jar(
        jar,
        args.expected_jar_sha256,
        args.expected_jar_bytes,
        args.expected_jar_version,
    )
    idempotence = run_converter_twice(
        migration_tool, source, output, report_path.parent
    )
    source_files_after = source_input_state(source)
    if source_files_after != source_files_before:
        raise GateError("SOURCE_CHANGED_DURING_GATE")
    live = validate_live_report(
        args.live_login_report, source_before, output_summary["sha256"], jar_summary["sha256"]
    )
    status = "READY_AUTH_CUTOVER" if live["status"] == "PASS" else "BLOCKED_LIVE_LOGIN_NOT_PROVEN"
    return {
        "schema": SCHEMA_VERSION,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "exit_code": 0 if status == "READY_AUTH_CUTOVER" else 2,
        "source": {
            "file": relative_or_name(source, args.allowed_source_root),
            "bytes": source.stat().st_size,
            "sha256": source_before,
            "files": source_files_before,
            "read_only": True,
            "unchanged_during_gate": True,
        },
        "accounts": account_summary,
        "output": {
            "file": relative_or_name(output, staging),
            **output_summary,
        },
        "reports": report_summary,
        "candidate_jar": jar_summary,
        "idempotence": idempotence,
        "live_login": live,
    }, 0 if status == "READY_AUTH_CUTOVER" else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--allowed-source-root", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sqlite-report", type=Path, required=True)
    parser.add_argument("--migration-report", type=Path, required=True)
    parser.add_argument("--candidate-jar", type=Path, required=True)
    parser.add_argument("--migration-tool", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--live-login-report", type=Path)
    parser.add_argument("--expected-source-sha256", default="", type=str)
    parser.add_argument("--expected-jar-sha256", default=DEFAULT_EXPECTED_JAR_SHA256, type=str)
    parser.add_argument("--expected-jar-bytes", default=DEFAULT_EXPECTED_JAR_BYTES, type=int)
    parser.add_argument("--expected-jar-version", default=EXPECTED_JAR_VERSION, type=str)
    parser.add_argument("--expected-records", default=DEFAULT_EXPECTED_RECORDS, type=int)
    parser.add_argument("--expected-bcrypt", default=DEFAULT_EXPECTED_BCRYPT, type=int)
    parser.add_argument("--expected-empty", default=DEFAULT_EXPECTED_EMPTY, type=int)
    parser.add_argument("--expected-uuids", default=DEFAULT_EXPECTED_UUIDS, type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not report_path_is_safe(
        args.report, args.allowed_source_root, args.staging_root
    ):
        print(
            json.dumps(
                {
                    "status": "BLOCKED_AUTH_DATA",
                    "error_code": "REPORT_INSIDE_SOURCE_OR_STAGING",
                }
            )
        )
        return 1
    if not HEX64_RE.fullmatch(args.expected_source_sha256 or ""):
        print(json.dumps({"status": "BLOCKED_AUTH_DATA", "error_code": "EXPECTED_SOURCE_DIGEST_REQUIRED"}))
        return 1
    try:
        report, code = build_report(args)
        expected_counts = {
            "records": args.expected_records,
            "bcrypt": args.expected_bcrypt,
            "empty": args.expected_empty,
            "uuid_present": args.expected_uuids,
        }
        actual_counts = {key: report["accounts"][key] for key in expected_counts}
        if actual_counts != expected_counts:
            raise GateError("EXPECTED_ACCOUNT_COUNTS_MISMATCH")
    except GateError as exc:
        report = {
            "schema": SCHEMA_VERSION,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "BLOCKED_AUTH_DATA",
            "exit_code": 1,
            "error_code": exc.code,
        }
        code = 1
    args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.report.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "report": str(args.report.resolve()), "exit_code": code}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
