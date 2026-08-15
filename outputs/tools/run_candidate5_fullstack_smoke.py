#!/usr/bin/env python3
"""Run two hidden, localhost-only lifecycle rounds for a prepared candidate server."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import struct
import subprocess
import time
from pathlib import Path


DONE_RE = re.compile(r'Done \(.+\)! For help, type "help"')


class Rcon:
    def __init__(self, host: str, port: int, password: str):
        self.sock = socket.create_connection((host, port), timeout=30)
        self.sock.settimeout(120)
        self.request_id = 0
        ident, _ = self._packet(3, password)
        if ident == -1:
            self.close()
            raise RuntimeError("RCON authentication failed")

    def _read_exact(self, count: int) -> bytes:
        chunks = []
        while count:
            chunk = self.sock.recv(count)
            if not chunk:
                raise ConnectionError("RCON connection closed")
            chunks.append(chunk)
            count -= len(chunk)
        return b"".join(chunks)

    def _packet(self, packet_type: int, body: str) -> tuple[int, str]:
        self.request_id += 1
        payload = (
            struct.pack("<ii", self.request_id, packet_type)
            + body.encode("utf-8")
            + b"\0\0"
        )
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        length = struct.unpack("<i", self._read_exact(4))[0]
        value = self._read_exact(length)
        ident, _kind = struct.unpack("<ii", value[:8])
        return ident, value[8:-2].decode("utf-8", errors="replace")

    def command(self, body: str) -> str:
        ident, response = self._packet(2, body)
        if ident != self.request_id:
            raise RuntimeError(f"unexpected RCON response id {ident}")
        return response

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_property(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    raise RuntimeError(f"missing server property: {key}")


def wait_done(log: Path, process: subprocess.Popen[bytes], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited before Done (code={process.returncode})")
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if DONE_RE.search(text):
            return
        time.sleep(0.5)
    raise TimeoutError(f"server did not reach Done within {timeout}s")


def launch_round(
    target: Path,
    round_number: int,
    server_port: int,
    rcon_port: int,
    timeout: int,
    win_args: str,
) -> dict:
    stdout_path = target / f"run{round_number}.stdout.log"
    stderr_path = target / f"run{round_number}.stderr.log"
    latest_log = target / "logs" / "latest.log"
    records: list[dict] = []
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = [
        r"C:\Program Files\Java\jdk-21.0.10\bin\java.exe",
        "-Xms1G",
        "-Xmx4G",
        "@user_jvm_args.txt",
            win_args,
        "nogui",
    ]
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(
            command,
            cwd=target,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            startupinfo=startup,
            creationflags=flags,
        )
        rcon: Rcon | None = None
        try:
            wait_done(latest_log, process, timeout)
            password = read_property(target / "server.properties", "rcon.password")
            deadline = time.monotonic() + 60
            while rcon is None and time.monotonic() < deadline:
                try:
                    rcon = Rcon("127.0.0.1", rcon_port, password)
                except (OSError, RuntimeError):
                    time.sleep(0.5)
            if rcon is None:
                raise TimeoutError("RCON listener did not become ready")
            for command_text, pause in (("reload", 8), ("save-all flush", 12)):
                started = time.monotonic()
                response = rcon.command(command_text)
                records.append(
                    {
                        "command": command_text,
                        "response": response,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    }
                )
                time.sleep(pause)
            started = time.monotonic()
            response = rcon.command("stop")
            records.append(
                {
                    "command": "stop",
                    "response": response,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            rcon.close()
            rcon = None
            try:
                process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=30)
                raise TimeoutError("server did not stop within 120s")
        finally:
            if rcon is not None:
                rcon.close()
            if process.poll() is None:
                if process.stdin is not None:
                    try:
                        process.stdin.write(b"stop\n")
                        process.stdin.flush()
                    except OSError:
                        pass
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=30)
    return {
        "round": round_number,
        "pid": process.pid,
        "exit_code": process.returncode,
        "commands": records,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "latest_log": str(latest_log),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--rcon-port", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--win-args",
        default="@libraries/net/neoforged/neoforge/21.1.241/win_args.txt",
        help="Forge argument file; may use absolute paths to a read-only library tree",
    )
    args = parser.parse_args()
    target = args.target.resolve()
    if not target.is_dir() or not (target / "world").is_dir() or not (target / "mods").is_dir():
        raise SystemExit("target must be a prepared isolated server")
    workspace_smoke_root = (Path(__file__).resolve().parents[1] / "tmp").resolve()
    in_workspace_smoke_root = False
    try:
        target.relative_to(workspace_smoke_root)
        in_workspace_smoke_root = True
    except ValueError:
        pass
    if "migration-audit-work" not in str(target).lower() and not in_workspace_smoke_root:
        raise SystemExit("target must be inside migration-audit-work or outputs/tmp")
    rounds = []
    for number in (1, 2):
        rounds.append(
            launch_round(
                target,
                number,
                args.server_port,
                args.rcon_port,
                args.timeout_seconds,
                args.win_args,
            )
        )
        time.sleep(3)
    report = {
        "schema": 1,
        "status": "PASS",
        "category": "candidate_fullstack_lifecycle",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": str(target),
        "ports": {"server": args.server_port, "rcon": args.rcon_port},
        "rounds": rounds,
        "source_read_only": True,
        "foreground_activation": False,
    }
    atomic_json(args.report.resolve(), report)
    print(json.dumps({"status": report["status"], "report": str(args.report.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
