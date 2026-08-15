#!/usr/bin/env python3
"""Run one redacted wrong-password probe against an isolated live player."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

from run_villager_full_gate import Rcon


SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def snapshot(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or len(value) != 1:
        raise RuntimeError("expected exactly one synthetic record")
    record = next(iter(value.values()))
    if not isinstance(record, dict) or not isinstance(record.get("passwordHash"), str):
        raise RuntimeError("synthetic record is missing passwordHash")
    return {
        "file_sha256": sha256_bytes(raw),
        "password_hash_sha256": sha256_bytes(record["passwordHash"].encode("utf-8")),
        "login_count": int(record.get("loginCount", -1)),
    }


def run_probe(args: argparse.Namespace) -> dict[str, object]:
    for label, value in (("player", args.player), ("wrong password", args.wrong_password)):
        if not SAFE_TOKEN_RE.fullmatch(value):
            raise RuntimeError(f"unsafe synthetic {label}")
    before = snapshot(args.synthetic_output)
    with Rcon(args.host, args.port, args.rcon_password) as rcon:
        online = False
        for _ in range(args.wait_seconds):
            if args.player in rcon.command("list"):
                online = True
                break
            time.sleep(1)
        if not online:
            raise RuntimeError("synthetic player did not connect")
        rcon.command(
            f"execute as {args.player} run login {args.wrong_password}"
        )
    time.sleep(2)
    after = snapshot(args.synthetic_output)
    unchanged = before == after
    if not unchanged:
        raise RuntimeError("wrong-password attempt mutated the synthetic record")
    return {
        "schema": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS_WRONG_PASSWORD_REJECTED_NO_MUTATION",
        "contains_secrets": False,
        "tested_with_secrets": False,
        "synthetic_player_online": True,
        "record_file_sha256_unchanged": True,
        "password_hash_sha256_unchanged": True,
        "login_count_unchanged": True,
        "login_count_before": before["login_count"],
        "login_count_after": after["login_count"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--rcon-password", required=True)
    parser.add_argument("--player", required=True)
    parser.add_argument("--wrong-password", required=True)
    parser.add_argument("--synthetic-output", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=50)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_probe(args)
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError, ConnectionError) as exc:
        print(json.dumps({"status": "PROBE_FAILED", "error": str(exc)}, sort_keys=True))
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
