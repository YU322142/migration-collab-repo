"""Convert MineAstr Fabric JSON configuration to NeoForge TOML.

The report intentionally contains no configuration values. The generated
TOML is written only to an explicit staging path and the source is never
modified in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Field:
    kind: str
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None


FIELDS: dict[str, Field] = {
    "enabled": Field("bool"),
    "websocketUrl": Field("string"),
    "token": Field("string"),
    "serverId": Field("string"),
    "serverName": Field("string"),
    "botDisplayName": Field("string"),
    "reconnectSeconds": Field("int", minimum=1, maximum=300),
    "maxMessageLength": Field("int", minimum=1, maximum=4096),
    "enablePlayerStateTool": Field("bool"),
    "enableInventoryTool": Field("bool"),
    "enableNearbyEntitiesTool": Field("bool"),
    "enableRegionTool": Field("bool"),
    "regionMaxBlocks": Field("int", minimum=4096, maximum=131072),
    "enableCommandTool": Field("bool"),
    "syncTrustedCommandUsers": Field("bool"),
    "trustedCommandUsers": Field("string_list"),
    "allowedCommandRules": Field("string_list"),
    "commandPermissionLevel": Field("int", minimum=0, maximum=4),
    "commandMaxLength": Field("int", minimum=1, maximum=1024),
    "commandApprovalTimeoutSeconds": Field("int", default=300, minimum=30, maximum=3600),
    "commandMaxPendingApprovals": Field("int", default=128, minimum=1, maximum=512),
    "enablePlayerNotifications": Field("bool"),
    "notifyActionBar": Field("bool"),
    "notifyTitle": Field("bool"),
    "notifySound": Field("bool"),
    "notificationMaxLength": Field("int", minimum=32, maximum=2000),
    "enableBindingSync": Field("bool"),
    "bindingSyncWhitelist": Field("bool"),
    "loginBindingCheckEnabled": Field("bool"),
    "loginCheckTimeoutSeconds": Field("int", minimum=1, maximum=30),
    "loginCheckFailOpen": Field("bool"),
    "generateBindingCodeOnReject": Field("bool"),
    "verifyCodeLength": Field("int", minimum=4, maximum=12),
    "loginCodeMessage": Field(
        "string",
        default="\n\u7ed1\u5b9a\u9a8c\u8bc1\u7801\uff1a{code}\n\u8bf7\u5728 QQ/Discord \u4f7f\u7528 /mc bind {code}",
    ),
}


def _validate_value(key: str, value: Any, field: Field) -> Any:
    if field.kind == "bool":
        if type(value) is not bool:
            raise ValueError(f"{key} must be a boolean")
        return value
    if field.kind == "int":
        if type(value) is not int:
            raise ValueError(f"{key} must be an integer")
        if field.minimum is not None and value < field.minimum:
            raise ValueError(f"{key} is below {field.minimum}")
        if field.maximum is not None and value > field.maximum:
            raise ValueError(f"{key} is above {field.maximum}")
        return value
    if field.kind == "string":
        if not isinstance(value, str) or len(value) > 16_384:
            raise ValueError(f"{key} must be a bounded string")
        return value
    if field.kind == "string_list":
        if not isinstance(value, list) or len(value) > 512:
            raise ValueError(f"{key} must be a bounded string list")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 256 for item in value):
            raise ValueError(f"{key} contains an invalid string")
        return list(value)
    raise AssertionError(f"unknown schema kind {field.kind}")


def validate(source: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    unknown = sorted(set(source) - set(FIELDS))
    if unknown:
        raise ValueError(f"unknown configuration keys: {', '.join(unknown)}")
    missing_required = [key for key, field in FIELDS.items() if key not in source and field.default is None]
    if missing_required:
        raise ValueError(f"missing required configuration keys: {', '.join(missing_required)}")
    result: dict[str, Any] = {}
    defaults: list[str] = []
    for key, field in FIELDS.items():
        if key in source:
            value = source[key]
        else:
            value = field.default
            defaults.append(key)
        result[key] = _validate_value(key, value, field)
    return result, defaults


def _toml_value(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value) + "]"
    raise TypeError(f"unsupported TOML value {type(value).__name__}")


def serialize(values: dict[str, Any]) -> str:
    result = "\n".join(f"{key} = {_toml_value(values[key])}" for key in FIELDS) + "\n"
    parsed = tomllib.loads(result)
    if parsed != values:
        raise ValueError("generated TOML failed semantic round-trip validation")
    return result


def migrate(source: Path, output: Path, report_path: Path | None) -> dict[str, Any]:
    if source.resolve() == output.resolve():
        raise ValueError("refusing in-place conversion; choose a separate staging output")
    raw = source.read_bytes()
    try:
        decoded = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid UTF-8 JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ValueError("configuration root must be an object")
    values, defaults = validate(decoded)
    target_text = serialize(values)

    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    os.close(fd)
    try:
        Path(temporary).write_text(target_text, encoding="utf-8", newline="\n")
        Path(temporary).replace(output)
    finally:
        Path(temporary).unlink(missing_ok=True)

    report = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "target_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "source_key_count": len(decoded),
        "target_key_count": len(values),
        "preserved_keys": sorted(decoded),
        "defaulted_keys": defaults,
        "sensitive_values_redacted": True,
        "status": "CHANGED",
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate MineAstr JSON config to NeoForge TOML")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = migrate(args.source, args.output, args.report)
    except Exception as exc:  # CLI must fail without printing source values.
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
