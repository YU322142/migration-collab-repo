#!/usr/bin/env python3
"""Run the four Java XiyusLogin scenarios on a private Windows desktop.

Only synthetic credentials and a fresh workspace world are used. The server is
bound to loopback, the client is launched on a private desktop, and every child
process is stopped before the report is finalized.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "outputs/tools"
sys.path.insert(0, str(TOOLS))

from run_villager_full_gate import Rcon  # noqa: E402


JAVA = Path(r"C:\Program Files\Java\jdk-21.0.10\bin\java.exe")
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
MIGRATION4_JAR = Path(
    r"<AUDIT_ROOT>\XiyusLogin-migration\build\libs\xiyuslogin-1.4-migration4.jar"
)
SERVER_LIBRARIES = Path(
    r"<AUDIT_ROOT>\final-fullstack-smoke-corrected-schematicannon-20260810\libraries"
)
CLIENT_BASE = Path(r"<AUDIT_ROOT>\client-gate-20260809\.minecraft")
PRIVATE_CLIENT_HELPER = TOOLS / "run_private_desktop_client_session.ps1"
EXPECTED_JAR_SHA256 = "703E01B84558EA9AFE28E82B0FB67C12DC09BA2936DE70939F52759C52D2E998"
EXPECTED_JAR_BYTES = 170065
SYNTHETIC_USERNAME = "AuthM4Gate"
CREATE_NO_WINDOW = 0x08000000
PASSWORD_RE = re.compile(r"^\$2[aby]\$12\$[./A-Za-z0-9]{53}$")
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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def wait_until(predicate, timeout: float, label: str, interval: float = 0.25):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
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


def pick_ports() -> tuple[int, int]:
    for server_port in range(12641, 12990, 2):
        rcon_port = server_port + 1
        sockets: list[socket.socket] = []
        try:
            for port in (server_port, rcon_port):
                probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                probe.bind(("127.0.0.1", port))
                sockets.append(probe)
            return server_port, rcon_port
        except OSError:
            pass
        finally:
            for probe in sockets:
                probe.close()
    raise RuntimeError("no isolated loopback port pair is available")


def port_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) != 0


def empty_record() -> dict[str, object]:
    return {
        "username": SYNTHETIC_USERNAME,
        "uuid": None,
        "passwordHash": "",
        "registrationTime": None,
        "lastLoginTime": None,
        "loginCount": 0,
        "lastIp": "",
        "lastAuthenticatedTime": None,
        "loginTries": 0,
        "lastKickedTime": None,
        "onlineAccount": "UNKNOWN",
        "sourceDataVersion": 1,
        "legacyPremiumAutoLogin": False,
        "passwordScheme": "empty",
    }


def snapshot_record(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or set(value) != {SYNTHETIC_USERNAME.lower()}:
        raise RuntimeError("synthetic auth output must contain exactly one expected record")
    record = value[SYNTHETIC_USERNAME.lower()]
    if not isinstance(record, dict):
        raise RuntimeError("synthetic auth record is invalid")
    password_hash = record.get("passwordHash")
    if not isinstance(password_hash, str):
        raise RuntimeError("synthetic auth record has no password hash")
    forbidden = {"password", "newPassword", "plaintextPassword"}
    if forbidden.intersection(record):
        raise RuntimeError("synthetic auth output contains a plaintext password field")
    return {
        "file_sha256": sha256_bytes(raw),
        "password_hash_sha256": sha256_bytes(password_hash.encode("utf-8")),
        "bcrypt_cost_12": bool(PASSWORD_RE.fullmatch(password_hash)),
        "password_scheme": record.get("passwordScheme"),
        "login_count": int(record.get("loginCount", -1)),
        "uuid_present": isinstance(record.get("uuid"), str) and bool(record.get("uuid")),
        "source_data_version": int(record.get("sourceDataVersion", -1)),
        "plaintext_fields_present": False,
    }


def create_junction(link: Path, target: Path) -> None:
    command = (
        "New-Item -ItemType Junction -Path '"
        + str(link).replace("'", "''")
        + "' -Target '"
        + str(target).replace("'", "''")
        + "' | Out-Null"
    )
    subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        creationflags=CREATE_NO_WINDOW,
    )


def prepare_fixture(run_root: Path, server_port: int, rcon_port: int, rcon_password: str) -> tuple[Path, Path]:
    server = run_root / "server"
    client = run_root / "client"
    for directory in (server / "mods", server / "world", server / "config", client / "mods"):
        directory.mkdir(parents=True, exist_ok=True)

    shutil.copy2(MIGRATION4_JAR, server / "mods/xiyuslogin-1.4-migration4.jar")
    shutil.copy2(MIGRATION4_JAR, client / "mods/xiyuslogin-1.4-migration4.jar")
    for name in ("assets", "libraries", "versions"):
        create_junction(client / name, CLIENT_BASE / name)
    source_options = ROOT / "outputs/tmp/auth-live-min-client/options.txt"
    if source_options.is_file():
        shutil.copy2(source_options, client / "options.txt")

    (server / "eula.txt").write_text("eula=true\n", encoding="ascii")
    properties = {
        "accepts-transfers": "false",
        "allow-flight": "true",
        "allow-nether": "true",
        "broadcast-console-to-ops": "false",
        "broadcast-rcon-to-ops": "false",
        "difficulty": "peaceful",
        "enable-command-block": "false",
        "enable-jmx-monitoring": "false",
        "enable-query": "false",
        "enable-rcon": "true",
        "enable-status": "true",
        "enforce-secure-profile": "false",
        "enforce-whitelist": "false",
        "force-gamemode": "false",
        "gamemode": "creative",
        "generate-structures": "false",
        "hardcore": "false",
        "level-name": "world",
        "level-seed": "1",
        "level-type": "minecraft:flat",
        "max-players": "4",
        "max-tick-time": "60000",
        "motd": "Synthetic migration4 auth gate",
        "network-compression-threshold": "256",
        "online-mode": "false",
        "player-idle-timeout": "0",
        "prevent-proxy-connections": "false",
        "pvp": "false",
        "rate-limit": "0",
        "rcon.password": rcon_password,
        "rcon.port": str(rcon_port),
        "server-ip": "127.0.0.1",
        "server-port": str(server_port),
        "simulation-distance": "2",
        "spawn-animals": "false",
        "spawn-monsters": "false",
        "spawn-npcs": "false",
        "spawn-protection": "0",
        "sync-chunk-writes": "true",
        "use-native-transport": "true",
        "view-distance": "2",
        "white-list": "false",
    }
    (server / "server.properties").write_text(
        "# Synthetic migration4 authentication gate\n"
        + "\n".join(f"{key}={value}" for key, value in sorted(properties.items()))
        + "\n",
        encoding="ascii",
    )
    write_json(server / "world/xiyus_player_data.json", {SYNTHETIC_USERNAME.lower(): empty_record()})
    write_json(server / "world/xiyus_password_reset_requests.json", {})

    source_args = SERVER_LIBRARIES / "net/neoforged/neoforge/21.1.241/win_args.txt"
    text = source_args.read_text(encoding="utf-8")
    libraries = SERVER_LIBRARIES.as_posix()
    text = text.replace("libraries/", libraries + "/")
    text = text.replace("-DlibraryDirectory=libraries", "-DlibraryDirectory=" + libraries)
    (server / "win_args_abs.txt").write_text(text, encoding="utf-8")
    return server, client


class ServerSession:
    def __init__(self, root: Path, artifact_dir: Path, round_number: int, rcon_port: int, rcon_password: str):
        self.root = root
        self.artifact_dir = artifact_dir
        self.round_number = round_number
        self.rcon_port = rcon_port
        self.rcon_password = rcon_password
        self.stdout_path = artifact_dir / f"server-round{round_number}.stdout.log"
        self.stderr_path = artifact_dir / f"server-round{round_number}.stderr.log"
        self.stdout_stream = self.stdout_path.open("wb")
        self.stderr_stream = self.stderr_path.open("wb")
        temp_dir = root / "java-tmp"
        temp_dir.mkdir(exist_ok=True)
        command = [
            str(JAVA), "-Xms512m", "-Xmx2048m", f"-Djava.io.tmpdir={temp_dir}",
            "@win_args_abs.txt", "nogui",
        ]
        self.process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=self.stdout_stream,
            stderr=self.stderr_stream,
            creationflags=CREATE_NO_WINDOW,
        )

    @property
    def latest_log(self) -> Path:
        return self.root / "logs/latest.log"

    def wait_ready(self) -> None:
        def ready() -> bool:
            if self.process.poll() is not None:
                raise RuntimeError(f"server exited {self.process.returncode}")
            return 'For help, type "help"' in read_text(self.latest_log)

        wait_until(
            ready,
            180,
            f"server round {self.round_number} ready",
        )
        wait_until(lambda: self._rcon_available(), 30, "RCON listener")

    def _rcon_available(self) -> bool:
        try:
            with Rcon("127.0.0.1", self.rcon_port, self.rcon_password) as rcon:
                rcon.command("list")
            return True
        except (OSError, RuntimeError, PermissionError):
            return False

    def command(self, command: str) -> str:
        with Rcon("127.0.0.1", self.rcon_port, self.rcon_password) as rcon:
            return rcon.command(command)

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                self.command("stop")
            except (OSError, RuntimeError, PermissionError):
                pass
            try:
                self.process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=20)
        self.stdout_stream.close()
        self.stderr_stream.close()
        if self.process.returncode != 0:
            raise RuntimeError(f"server round {self.round_number} exited {self.process.returncode}")

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pass
        self.stdout_stream.close()
        self.stderr_stream.close()


class PrivateClientSession:
    def __init__(self, client_root: Path, artifact_dir: Path, server_port: int, sequence: int):
        self.client_root = client_root
        self.artifact_dir = artifact_dir
        self.server_port = server_port
        self.sequence = sequence
        self.state = artifact_dir / f"client-{sequence}.state.json"
        self.stop_file = artifact_dir / f"client-{sequence}.stop"
        self.helper_stdout = (artifact_dir / f"client-{sequence}.helper.stdout.log").open("wb")
        self.helper_stderr = (artifact_dir / f"client-{sequence}.helper.stderr.log").open("wb")
        self.process = subprocess.Popen(
            [
                str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(PRIVATE_CLIENT_HELPER),
                "-MinecraftRoot", str(client_root),
                "-ServerAddress", f"127.0.0.1:{server_port}",
                "-Username", SYNTHETIC_USERNAME,
                "-Uuid", str(uuid.UUID(int=sequence)),
                "-StatePath", str(self.state),
                "-StopPath", str(self.stop_file),
                "-MaximumMemoryMb", "2048",
                "-SessionTimeoutSeconds", "240",
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=self.helper_stdout,
            stderr=self.helper_stderr,
            creationflags=CREATE_NO_WINDOW,
        )
        self.launch = wait_until(self._running_state, 170, f"private client {sequence} launch")

    def _running_state(self):
        if self.process.poll() is not None:
            raise RuntimeError(f"private client helper exited {self.process.returncode}")
        if not self.state.is_file():
            return False
        value = json.loads(self.state.read_text(encoding="utf-8"))
        if value.get("status") == "FAILED":
            raise RuntimeError(f"private client helper failed: {value.get('error')}")
        return value if value.get("status") == "RUNNING" else False

    @property
    def stdout_path(self) -> Path:
        return Path(self.launch["stdout"])

    @property
    def stderr_path(self) -> Path:
        return Path(self.launch["stderr"])

    def stop(self) -> None:
        self.stop_file.write_text("stop\n", encoding="ascii")
        try:
            self.process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=20)
        self.helper_stdout.close()
        self.helper_stderr.close()
        if self.process.returncode != 0:
            raise RuntimeError(f"private client helper exited {self.process.returncode}")
        final = json.loads(self.state.read_text(encoding="utf-8"))
        if final.get("status") != "STOPPED" or final.get("foreground_activation") is not False:
            raise RuntimeError("private client did not stop cleanly in background")

    def terminate(self) -> None:
        try:
            self.stop_file.write_text("stop\n", encoding="ascii")
        except OSError:
            pass
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        if self.state.is_file():
            try:
                java_pid = json.loads(self.state.read_text(encoding="utf-8")).get("java_pid")
                if java_pid:
                    os.kill(int(java_pid), signal.SIGTERM)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        self.helper_stdout.close()
        self.helper_stderr.close()


def wait_join(server: ServerSession, baseline: int) -> None:
    wait_until(
        lambda: read_text(server.latest_log).count(f"{SYNTHETIC_USERNAME} joined the game") > baseline,
        180,
        "synthetic client join",
    )


def redact_artifact(source: Path, destination: Path, secrets_to_remove: tuple[str, ...]) -> dict[str, object]:
    text = read_text(source)
    for value in secrets_to_remove:
        if value:
            text = text.replace(value, "[REDACTED_SYNTHETIC_VALUE]")
    for value in secrets_to_remove:
        if value and value in text:
            raise RuntimeError("redaction failed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return {
        "path": destination.resolve().relative_to(ROOT.resolve()).as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "contains_secrets": False,
    }


def run() -> dict[str, object]:
    if not JAVA.is_file() or not POWERSHELL.is_file() or not PRIVATE_CLIENT_HELPER.is_file():
        raise RuntimeError("runtime prerequisites are missing")
    if MIGRATION4_JAR.stat().st_size != EXPECTED_JAR_BYTES or sha256_file(MIGRATION4_JAR) != EXPECTED_JAR_SHA256:
        raise RuntimeError("migration4 artifact lock mismatch")
    if str(MIGRATION4_JAR).lower().startswith(r"<TRANS_ROOT>\20260807".lower()):
        raise RuntimeError("production source artifact is forbidden")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    run_root = ROOT / "outputs/tmp" / ("xiyuslogin-migration4-private-" + run_id)
    artifact_dir = ROOT / "outputs/xiyuslogin-migration4-live-artifacts-20260810" / run_id
    run_root.mkdir(parents=True)
    artifact_dir.mkdir(parents=True)
    server_port, rcon_port = pick_ports()
    password = "M4" + secrets.token_hex(10)
    wrong_password = "W4" + secrets.token_hex(10)
    rcon_password = "R4" + secrets.token_hex(12)
    server_root, client_root = prepare_fixture(run_root, server_port, rcon_port, rcon_password)
    auth_file = server_root / "world/xiyus_player_data.json"
    sessions: list[PrivateClientSession] = []
    servers: list[ServerSession] = []
    client_stdout_paths: list[Path] = []
    wrong_before: dict[str, object] | None = None
    wrong_after: dict[str, object] | None = None
    registered: dict[str, object] | None = None
    after_correct: dict[str, object] | None = None
    after_restart: dict[str, object] | None = None
    try:
        server1 = ServerSession(server_root, artifact_dir, 1, rcon_port, rcon_password)
        servers.append(server1)
        server1.wait_ready()
        if "Loaded 1 player records from data file" not in read_text(server1.latest_log):
            raise RuntimeError("synthetic empty record was not loaded")

        baseline = read_text(server1.latest_log).count(f"{SYNTHETIC_USERNAME} joined the game")
        client1 = PrivateClientSession(client_root, artifact_dir, server_port, 1)
        sessions.append(client1)
        wait_join(server1, baseline)
        register_count = read_text(server1.latest_log).count("registered successfully")
        server1.command(f"execute as {SYNTHETIC_USERNAME} run register {password} {password}")
        wait_until(
            lambda: read_text(server1.latest_log).count("registered successfully") > register_count,
            20,
            "synthetic registration",
        )
        wait_until(lambda: snapshot_record(auth_file)["bcrypt_cost_12"], 20, "bcrypt persistence")
        registered = snapshot_record(auth_file)
        if registered["password_scheme"] != "bcrypt" or registered["login_count"] != 0:
            raise RuntimeError("registration semantics mismatch")
        if not registered["uuid_present"] or registered["source_data_version"] != 1:
            raise RuntimeError("empty-record metadata was not preserved")
        client_stdout_paths.append(client1.stdout_path)
        client1.stop()
        sessions.remove(client1)

        baseline = read_text(server1.latest_log).count(f"{SYNTHETIC_USERNAME} joined the game")
        client2 = PrivateClientSession(client_root, artifact_dir, server_port, 2)
        sessions.append(client2)
        wait_join(server1, baseline)
        wrong_before = snapshot_record(auth_file)
        server1.command(f"execute as {SYNTHETIC_USERNAME} run login {wrong_password}")
        time.sleep(2)
        wrong_after = snapshot_record(auth_file)
        if wrong_before != wrong_after:
            raise RuntimeError("wrong password mutated the synthetic auth record")
        login_count = read_text(server1.latest_log).count("logged in successfully")
        server1.command(f"execute as {SYNTHETIC_USERNAME} run login {password}")
        wait_until(
            lambda: read_text(server1.latest_log).count("logged in successfully") > login_count,
            20,
            "correct synthetic login",
        )
        wait_until(lambda: snapshot_record(auth_file)["login_count"] == 1, 20, "first login persistence")
        after_correct = snapshot_record(auth_file)
        client_stdout_paths.append(client2.stdout_path)
        client2.stop()
        sessions.remove(client2)
        server1.stop()
        servers.remove(server1)

        server2 = ServerSession(server_root, artifact_dir, 2, rcon_port, rcon_password)
        servers.append(server2)
        server2.wait_ready()
        if "Loaded 1 player records from data file" not in read_text(server2.latest_log):
            raise RuntimeError("restart did not load the synthetic record")
        baseline = read_text(server2.latest_log).count(f"{SYNTHETIC_USERNAME} joined the game")
        client3 = PrivateClientSession(client_root, artifact_dir, server_port, 3)
        sessions.append(client3)
        wait_join(server2, baseline)
        login_count = read_text(server2.latest_log).count("logged in successfully")
        server2.command(f"execute as {SYNTHETIC_USERNAME} run login {password}")
        wait_until(
            lambda: read_text(server2.latest_log).count("logged in successfully") > login_count,
            20,
            "restart synthetic login",
        )
        wait_until(lambda: snapshot_record(auth_file)["login_count"] == 2, 20, "restart login persistence")
        after_restart = snapshot_record(auth_file)
        client_stdout_paths.append(client3.stdout_path)
        client3.stop()
        sessions.remove(client3)
        server2.stop()
        servers.remove(server2)
    finally:
        for client in list(sessions):
            client.terminate()
        for server in list(servers):
            server.terminate()

    time.sleep(1)
    if not port_closed(server_port) or not port_closed(rcon_port):
        raise RuntimeError("isolated auth ports remained open")
    if None in (registered, wrong_before, wrong_after, after_correct, after_restart):
        raise RuntimeError("auth scenario did not complete")

    redacted_dir = artifact_dir / "redacted"
    secrets_to_remove = (password, wrong_password, rcon_password)
    server_artifacts = [
        redact_artifact(artifact_dir / f"server-round{round_number}.stdout.log",
                        redacted_dir / f"server-round{round_number}.stdout.log", secrets_to_remove)
        for round_number in (1, 2)
    ]
    client_artifacts = [
        redact_artifact(path, redacted_dir / f"client-session{index}.stdout.log", secrets_to_remove)
        for index, path in enumerate(client_stdout_paths, 1)
    ]
    wrong_report_path = redacted_dir / "wrong-password-no-mutation.json"
    wrong_report = {
        "schema": 1,
        "status": "PASS_WRONG_PASSWORD_REJECTED_NO_MUTATION",
        "contains_secrets": False,
        "tested_with_secrets": False,
        "synthetic_player_online": True,
        "record_file_sha256_unchanged": wrong_before["file_sha256"] == wrong_after["file_sha256"],
        "password_hash_sha256_unchanged": wrong_before["password_hash_sha256"] == wrong_after["password_hash_sha256"],
        "login_count_unchanged": wrong_before["login_count"] == wrong_after["login_count"],
        "login_count_before": wrong_before["login_count"],
        "login_count_after": wrong_after["login_count"],
    }
    write_json(wrong_report_path, wrong_report)
    wrong_artifact = {
        "path": wrong_report_path.resolve().relative_to(ROOT.resolve()).as_posix(),
        "bytes": wrong_report_path.stat().st_size,
        "sha256": sha256_file(wrong_report_path),
        "contains_secrets": False,
    }
    final_output = redacted_dir / "xiyus_player_data.synthetic.json"
    shutil.copy2(auth_file, final_output)
    final_artifact = {
        "path": final_output.resolve().relative_to(ROOT.resolve()).as_posix(),
        "bytes": final_output.stat().st_size,
        "sha256": sha256_file(final_output),
        "contains_secrets": False,
    }

    runtime_text = "\n".join(read_text(artifact_dir / f"server-round{n}.stdout.log") for n in (1, 2))
    client_text = "\n".join(read_text(path) for path in client_stdout_paths)
    fatal_counts = {marker: (runtime_text + client_text).count(marker) for marker in FATAL_MARKERS}
    if any(fatal_counts.values()):
        raise RuntimeError(f"fatal runtime markers found: {fatal_counts}")
    config_text = read_text(server_root / "config/xiyuslogin-common.toml")
    if "blindUnauthenticatedPlayers = false" not in config_text or "enableIpSession = false" not in config_text:
        raise RuntimeError("migration4 security/render defaults mismatch")

    report = {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "BLOCKED_LIVE_LOGIN_INCOMPLETE",
        "java_synthetic_status": "PASS_4_OF_4",
        "strict_verifier_eligible": False,
        "contains_secrets": False,
        "tested_with_secrets": False,
        "candidate_jar_sha256": EXPECTED_JAR_SHA256,
        "candidate": {
            "file": MIGRATION4_JAR.name,
            "bytes": MIGRATION4_JAR.stat().st_size,
            "sha256": sha256_file(MIGRATION4_JAR),
            "version": "1.4-migration4",
        },
        "fixture_scope": {
            "synthetic_accounts_only": True,
            "production_accounts_loaded": False,
            "production_credentials_used": False,
            "production_source_read": False,
            "production_source_written": False,
            "fresh_workspace_world": True,
            "private_desktop": True,
            "foreground_activation": False,
            "loopback_only": True,
        },
        "ports": {
            str(server_port): {"closed": True},
            str(rcon_port): {"closed": True},
        },
        "runtime": {
            "server_rounds": 2,
            "client_sessions": 3,
            "bcrypt_nested_loaded": runtime_text.count('Found library file "bcrypt-0.10.2.jar"') >= 2,
            "bytes_nested_loaded": runtime_text.count('Found library file "bytes-1.5.0.jar"') >= 2,
            "fatal_markers": fatal_counts,
            "blind_unauthenticated_players": False,
            "ip_session_enabled": False,
        },
        "scenarios": {
            "java_empty_record_registration_policy": {
                "status": "PASS_SYNTHETIC_NETWORK_RUNTIME",
                "basis": "empty synthetic record registered over a private-desktop NeoForge client connection; BCrypt cost 12 persisted and sourceDataVersion remained 1",
                "artifacts": [client_artifacts[0], server_artifacts[0], final_artifact],
            },
            "java_existing_bcrypt_wrong_rejected": {
                "status": "PASS_SYNTHETIC_NETWORK_RUNTIME",
                "basis": "wrong synthetic password left the complete record, BCrypt hash, and loginCount unchanged",
                "artifacts": [client_artifacts[1], server_artifacts[0], wrong_artifact],
            },
            "java_existing_bcrypt_correct": {
                "status": "PASS_SYNTHETIC_NETWORK_RUNTIME",
                "basis": "correct synthetic password authenticated through the exact migration4 JAR and incremented loginCount to 1",
                "artifacts": [client_artifacts[1], server_artifacts[0], final_artifact],
            },
            "java_restart_reauthentication": {
                "status": "PASS_SYNTHETIC_NETWORK_RUNTIME",
                "basis": "server restart loaded one record; reconnect required login and incremented loginCount to 2",
                "artifacts": [client_artifacts[2], server_artifacts[1], final_artifact],
            },
            "bedrock_floodgate_uuid_mapping": {
                "status": "BLOCKED_FLOODGATE_RUNTIME_AND_BEDROCK_CLIENT_MISSING",
                "basis": "no Floodgate/Geyser runtime or controlled Bedrock client was used",
            },
            "proxy_ip_session_policy": {
                "status": "BLOCKED_PROXY_RUNTIME_MISSING_DIRECT_IP_SESSION_POLICY_PASS",
                "basis": "direct loopback reconnect required login with enableIpSession=false; no supported proxy path was available",
            },
        },
        "synthetic_output": {
            "records": 1,
            "bcrypt_cost_12": 1,
            "password_scheme": after_restart["password_scheme"],
            "login_count_after_two_successful_reauthentications": after_restart["login_count"],
            "plaintext_fields_present": after_restart["plaintext_fields_present"],
            "bytes": final_output.stat().st_size,
            "sha256": sha256_file(final_output),
        },
        "artifacts": {
            "server": server_artifacts,
            "clients": client_artifacts,
            "wrong_password_no_mutation": wrong_artifact,
            "synthetic_output": final_artifact,
        },
        "remaining_blockers": [
            "controlled Bedrock client plus supported Geyser/Floodgate runtime and UUID mapping evidence",
            "supported production proxy topology and forwarding/session-bypass evidence",
            "rerun against the final assembled target after the stopped-source refresh",
        ],
    }
    report_path = ROOT / "outputs/xiyuslogin-migration4-synthetic-live-evidence-20260810.json"
    markdown_path = ROOT / "outputs/xiyuslogin-migration4-synthetic-live-evidence-20260810.md"
    write_json(report_path, report)
    markdown = [
        "# XiyusLogin migration4 synthetic live evidence",
        "",
        "Status: `PASS_4_OF_4` for the Java synthetic matrix; aggregate release status remains `BLOCKED_LIVE_LOGIN_INCOMPLETE`.",
        "",
        f"Candidate: `{MIGRATION4_JAR.name}`, {MIGRATION4_JAR.stat().st_size} bytes, SHA-256 `{EXPECTED_JAR_SHA256}`.",
        "",
        "The run used one disposable synthetic account, a fresh workspace world, loopback-only ports, and three NeoForge client sessions on a private Windows desktop. No foreground activation or production account data was used.",
        "",
        "Passed Java scenarios: empty-record registration with BCrypt cost 12, wrong-password rejection without record mutation, correct BCrypt login, and restart reauthentication. Both isolated ports were closed after clean server shutdown.",
        "",
        "Floodgate/Bedrock UUID mapping and the production proxy policy remain blocked because those runtimes were not present; this evidence does not fabricate them.",
        "",
        f"Machine-readable report: `{report_path}`.",
    ]
    markdown_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "java_synthetic_status": report["java_synthetic_status"],
        "report": str(report_path),
        "artifact_dir": str(artifact_dir),
        "ports_closed": True,
        "foreground_activation": False,
    }, sort_keys=True))
    return report


def main() -> int:
    try:
        run()
        return 0
    except Exception as exc:  # fail-closed evidence runner
        print(json.dumps({"status": "NO_GO", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
