from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import nbtlib


def read_responses(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    command: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("COMMAND: "):
            command = line.removeprefix("COMMAND: ")
        elif command is not None and line.startswith("RESPONSE: "):
            result[command] = line.removeprefix("RESPONSE: ")
            command = None
    return result


def plain(value):
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(child) for child in value]
    return value


def normalize(value, key: str | None = None):
    value = plain(value)
    if isinstance(value, dict):
        return {name: normalize(value[name], name) for name in sorted(value)}
    if isinstance(value, list):
        children = [normalize(child) for child in value]
        if key == "attributes" and all(isinstance(child, dict) and "id" in child for child in children):
            children.sort(key=lambda child: json.dumps(child, sort_keys=True, separators=(",", ":")))
        return children
    return value


def parse_response_nbt(response: str, kind: str):
    marker = f" has the following {kind} data: "
    if marker not in response:
        return response
    return normalize(nbtlib.parse_nbt(response.split(marker, 1)[1]))


def differences(before, after, path: str = "$") -> list[dict]:
    if type(before) is not type(after):
        return [{"path": path, "before": before, "after": after}]
    if isinstance(before, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            if key not in before:
                result.append({"path": f"{path}.{key}", "before": "<missing>", "after": after[key]})
            elif key not in after:
                result.append({"path": f"{path}.{key}", "before": before[key], "after": "<missing>"})
            else:
                result.extend(differences(before[key], after[key], f"{path}.{key}"))
        return result
    if isinstance(before, list):
        if len(before) != len(after):
            return [{"path": path, "before": before, "after": after}]
        result = []
        for index, (left, right) in enumerate(zip(before, after)):
            result.extend(differences(left, right, f"{path}[{index}]"))
        return result
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparable_villagers(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for row in data["villagers"]:
        row = dict(row)
        row.pop("source", None)
        result[row["uuid"]] = row
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-rcon", type=Path, required=True)
    parser.add_argument("--after-rcon", type=Path, required=True)
    parser.add_argument("--before-villagers", type=Path, required=True)
    parser.add_argument("--after-villagers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    before_responses = read_responses(args.before_rcon)
    after_responses = read_responses(args.after_rcon)
    block_commands = sorted(
        (command for command in before_responses if command.startswith("data get block ")),
        key=lambda command: int(re.match(r"data get block (\d+)", command).group(1)),
    )
    block_results = []
    for command in block_commands:
        before = parse_response_nbt(before_responses[command], "block")
        after = parse_response_nbt(after_responses.get(command, "<missing>"), "block")
        diff = differences(before, after)
        block_results.append({"command": command, "equal": not diff, "differences": diff})

    entity_commands = [command for command in before_responses if command.startswith("data get entity ")]
    entity_results = []
    for command in entity_commands:
        before = parse_response_nbt(before_responses[command], "entity")
        after = parse_response_nbt(after_responses.get(command, "<missing>"), "entity")
        diff = differences(before, after)
        entity_results.append({"command": command, "equal": not diff, "differences": diff})

    before_villagers = comparable_villagers(args.before_villagers)
    after_villagers = comparable_villagers(args.after_villagers)
    villager_results = []
    for identifier in sorted(set(before_villagers) | set(after_villagers)):
        diff = differences(before_villagers.get(identifier, "<missing>"), after_villagers.get(identifier, "<missing>"))
        villager_results.append({"uuid": identifier, "equal": not diff, "differences": diff})

    report = {
        "before_rcon_sha256": sha256(args.before_rcon),
        "after_rcon_sha256": sha256(args.after_rcon),
        "block_snapshot_count": len(block_results),
        "block_snapshots_equal": all(row["equal"] for row in block_results),
        "block_results": block_results,
        "entity_snapshot_count": len(entity_results),
        "entity_snapshots_semantically_equal": all(row["equal"] for row in entity_results),
        "entity_results": entity_results,
        "villager_count_before": len(before_villagers),
        "villager_count_after": len(after_villagers),
        "villager_audited_fields_equal": all(row["equal"] for row in villager_results),
        "villager_results": villager_results,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if not key.endswith("_results")}, indent=2))
    if not (
        report["block_snapshots_equal"]
        and report["entity_snapshots_semantically_equal"]
        and report["villager_audited_fields_equal"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
