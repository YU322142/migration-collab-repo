from __future__ import annotations

import argparse
import json
import math
import re
import socket
import struct
import time
from collections import defaultdict
from pathlib import Path


RESULT_PATTERN = re.compile(
    r"VILLAGER_DUMP_RESULT uuid=(?P<uuid>[0-9a-f-]+) status=present "
    r"profession=(?P<profession>\S+) level=(?P<level>-?\d+) "
    r"xp=(?P<xp>-?\d+) offers=(?P<offers>-?\d+) "
    r"pos=(?P<x>-?[0-9.eE+]+),(?P<y>-?[0-9.eE+]+),(?P<z>-?[0-9.eE+]+)"
)
GAMERULE_PATTERN = re.compile(r"(?:currently set to:|is)\s*(?P<value>true|false)", re.I)


def receive_exact(connection: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    while length:
        chunk = connection.recv(length)
        if not chunk:
            raise ConnectionError("RCON connection closed")
        chunks.append(chunk)
        length -= len(chunk)
    return b"".join(chunks)


class Rcon:
    def __init__(self, host: str, port: int, password: str):
        self.connection = socket.create_connection((host, port), timeout=30)
        self.connection.settimeout(120)
        self.request_id = 0
        response_id, response = self._packet(3, password)
        if response_id == -1:
            self.close()
            raise PermissionError(f"RCON authentication failed: {response}")

    def _packet(self, packet_type: int, body: str) -> tuple[int, str]:
        self.request_id += 1
        payload = (
            struct.pack("<ii", self.request_id, packet_type)
            + body.encode("utf-8")
            + b"\0\0"
        )
        self.connection.sendall(struct.pack("<i", len(payload)) + payload)
        length = struct.unpack("<i", receive_exact(self.connection, 4))[0]
        value = receive_exact(self.connection, length)
        response_id, _ = struct.unpack("<ii", value[:8])
        return response_id, value[8:-2].decode("utf-8", errors="replace")

    def command(self, body: str) -> str:
        response_id, response = self._packet(2, body)
        if response_id != self.request_id:
            raise RuntimeError(
                f"unexpected RCON response id {response_id}; expected {self.request_id}"
            )
        return response

    def close(self) -> None:
        try:
            self.connection.close()
        except OSError:
            pass

    def __enter__(self) -> "Rcon":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def chunk_coordinate(value: float) -> int:
    return math.floor(value) // 16


def checkpoint(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def command_record(rcon: Rcon, command: str, records: list[dict]) -> str:
    started = time.monotonic()
    response = rcon.command(command)
    records.append(
        {
            "command": command,
            "response": response,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    )
    return response


def query_gamerule(rcon: Rcon, name: str, records: list[dict]) -> bool | None:
    response = command_record(rcon, f"gamerule {name}", records)
    match = GAMERULE_PATTERN.search(response)
    if match:
        return match.group("value").lower() == "true"
    # Vanilla's 1.21.1 response is stable, but retain the raw response in the
    # report if a compatible server localizes or reformats it.
    return None


def expected_fields(villager: dict) -> dict:
    data = villager.get("villager_data", {})
    return {
        "uuid": villager["uuid"],
        "profession": data.get("profession"),
        "level": int(data.get("level", 0)),
        "xp": int(villager.get("xp", 0)),
        "offers": len(villager.get("recipes", [])),
        "position": [float(value) for value in villager.get("position", [])],
    }


def compare_runtime(expected: dict, response: str, tolerance: float) -> dict:
    match = RESULT_PATTERN.search(response)
    if not match:
        return {
            "uuid": expected["uuid"],
            "status": "missing_or_unparseable",
            "response": response,
        }
    actual = {
        "uuid": match.group("uuid"),
        "profession": match.group("profession"),
        "level": int(match.group("level")),
        "xp": int(match.group("xp")),
        "offers": int(match.group("offers")),
        "position": [
            float(match.group("x")),
            float(match.group("y")),
            float(match.group("z")),
        ],
    }
    mismatches: dict[str, dict] = {}
    for key in ("uuid", "profession", "level", "xp", "offers"):
        if actual[key] != expected[key]:
            mismatches[key] = {"expected": expected[key], "actual": actual[key]}
    if len(expected["position"]) != 3 or any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)
        for left, right in zip(expected["position"], actual["position"])
    ):
        mismatches["position"] = {
            "expected": expected["position"],
            "actual": actual["position"],
        }
    return {
        "uuid": expected["uuid"],
        "status": "match" if not mismatches else "mismatch",
        "actual": actual,
        "mismatches": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--batch-chunks", type=int, default=200)
    parser.add_argument("--position-tolerance", type=float, default=1e-9)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument(
        "--stabilize-npcs",
        action="store_true",
        help="temporarily disable doMobSpawning while frozen; restore its prior value",
    )
    parser.add_argument(
        "--load-settle-seconds",
        type=float,
        default=0.15,
        help="allow asynchronous entity storage loads to settle after each chunk",
    )
    parser.add_argument("--missing-retries", type=int, default=3)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    villagers = baseline["villagers"]
    grouped: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    for villager in villagers:
        position = villager["position"]
        key = (
            villager["dimension"],
            chunk_coordinate(float(position[0])),
            chunk_coordinate(float(position[2])),
        )
        grouped[key].append(villager)

    unsupported_dimensions = sorted(
        dimension for dimension, _, _ in grouped if dimension != "minecraft:overworld"
    )
    if unsupported_dimensions:
        raise SystemExit(
            "the current diagnostic command is overworld-scoped; unsupported dimensions: "
            + ", ".join(unsupported_dimensions)
        )

    chunks = sorted(grouped)
    report = {
        "baseline": str(args.baseline.resolve()),
        "expected_villagers": len(villagers),
        "expected_chunks": len(chunks),
        "batch_chunks": args.batch_chunks,
        "position_tolerance": args.position_tolerance,
        "started_unix": time.time(),
        "freeze_response": None,
        "original_do_mob_spawning": None,
        "restored_do_mob_spawning": None,
        "batches_completed": 0,
        "villagers_checked": 0,
        "matches": 0,
        "mismatches": [],
        "command_failures": [],
        "commands": [],
        "stop_response": None,
        "complete": False,
    }
    checkpoint(args.report, report)

    rcon: Rcon | None = None
    try:
        rcon = Rcon(args.host, args.port, args.password)
        report["freeze_response"] = command_record(
            rcon, "tick freeze", report["commands"]
        )
        if args.stabilize_npcs:
            report["original_do_mob_spawning"] = query_gamerule(
                rcon, "doMobSpawning", report["commands"]
            )
            command_record(
                rcon, "gamerule doMobSpawning false", report["commands"]
            )
        checkpoint(args.report, report)

        for offset in range(0, len(chunks), args.batch_chunks):
            batch = chunks[offset : offset + args.batch_chunks]
            loaded: list[tuple[str, int, int]] = []
            try:
                for dimension, chunk_x, chunk_z in batch:
                    block_x = chunk_x * 16
                    block_z = chunk_z * 16
                    response = command_record(
                        rcon,
                        f"forceload add {block_x} {block_z}",
                        report["commands"],
                    )
                    loaded.append((dimension, chunk_x, chunk_z))
                    if "too many" in response.lower() or "failed" in response.lower():
                        report["command_failures"].append(
                            {
                                "command": f"forceload add {block_x} {block_z}",
                                "response": response,
                            }
                        )

                    # forceload queues entity storage work; the diagnostic
                    # command's synchronous getChunk call gives that work a
                    # server-thread synchronization point before UUID lookup.
                    command_record(
                        rcon,
                        f"poi_migration load {block_x} {block_z}",
                        report["commands"],
                    )
                    if args.load_settle_seconds > 0:
                        time.sleep(args.load_settle_seconds)

                for key in batch:
                    for villager in grouped[key]:
                        expected = expected_fields(villager)
                        response = ""
                        result = None
                        for attempt in range(args.missing_retries + 1):
                            response = command_record(
                                rcon,
                                f"poi_migration villager {expected['uuid']}",
                                report["commands"],
                            )
                            result = compare_runtime(
                                expected, response, args.position_tolerance
                            )
                            if result["status"] != "missing_or_unparseable":
                                break
                            if attempt < args.missing_retries:
                                chunk_x = chunk_coordinate(expected["position"][0])
                                chunk_z = chunk_coordinate(expected["position"][2])
                                command_record(
                                    rcon,
                                    f"poi_migration load {chunk_x * 16} {chunk_z * 16}",
                                    report["commands"],
                                )
                                if args.load_settle_seconds > 0:
                                    time.sleep(args.load_settle_seconds)
                        assert result is not None
                        report["villagers_checked"] += 1
                        if result["status"] == "match":
                            report["matches"] += 1
                        else:
                            report["mismatches"].append(result)

                command_record(rcon, "save-all flush", report["commands"])
            finally:
                for _dimension, chunk_x, chunk_z in loaded:
                    block_x = chunk_x * 16
                    block_z = chunk_z * 16
                    try:
                        command_record(
                            rcon,
                            f"forceload remove {block_x} {block_z}",
                            report["commands"],
                        )
                    except Exception as exception:
                        report["command_failures"].append(
                            {
                                "command": f"forceload remove {block_x} {block_z}",
                                "error": f"{type(exception).__name__}: {exception}",
                            }
                        )
            report["batches_completed"] += 1
            checkpoint(args.report, report)

        if args.stabilize_npcs and report["original_do_mob_spawning"] is not None:
            value = "true" if report["original_do_mob_spawning"] else "false"
            command_record(
                rcon,
                f"gamerule doMobSpawning {value}",
                report["commands"],
            )
            report["restored_do_mob_spawning"] = query_gamerule(
                rcon, "doMobSpawning", report["commands"]
            )
            command_record(rcon, "save-all flush", report["commands"])

        report["complete"] = (
            report["villagers_checked"] == len(villagers)
            and not report["mismatches"]
            and not report["command_failures"]
        )
    except Exception as exception:
        report["fatal_error"] = f"{type(exception).__name__}: {exception}"
        raise
    finally:
        if rcon is not None and args.stop:
            try:
                report["stop_response"] = command_record(
                    rcon, "stop", report["commands"]
                )
            except Exception as exception:
                report["stop_error"] = f"{type(exception).__name__}: {exception}"
        if rcon is not None:
            rcon.close()
        report["finished_unix"] = time.time()
        checkpoint(args.report, report)

    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "expected_villagers",
                    "expected_chunks",
                    "batches_completed",
                    "villagers_checked",
                    "matches",
                    "mismatches",
                    "command_failures",
                    "complete",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
