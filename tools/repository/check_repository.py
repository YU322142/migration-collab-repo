#!/usr/bin/env python3
"""Fail-closed safety check for the local collaboration repository.

This checker is intentionally stricter than the migration-time scanners.  It
checks the *source repository* only: no live world, runtime, credential, or
player identity may enter Git by accident.  Synthetic fixtures are allowed;
known production identities are detected by digest so they are not repeated
in this source file.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE = 25 * 1024 * 1024
FORBIDDEN_TOP = {
    "world", "saves", "server", "client", "runtime", "instances",
    "logs", "crash-reports", "playerdata", "region", "entities", "poi",
}
FORBIDDEN_COMPONENTS = {".archive-unpack"}
FORBIDDEN_NAMES = {
    "server.properties", "ops.json", "whitelist.json", "usercache.json",
    "session.lock", "modsync.properties", "xiyus_player_data.json",
    "trueuuid-registry.json", "easyauth.db",
}
FORBIDDEN_SUFFIX = {
    ".mca", ".nbt", ".dat", ".jar", ".zip", ".7z", ".rar", ".class", ".dll",
    ".exe", ".dmp", ".log", ".sqlite", ".db",
}
TEXT_SUFFIXES = {
    "", ".txt", ".md", ".json", ".json5", ".yml", ".yaml", ".toml",
    ".properties", ".py", ".ps1", ".java", ".gradle", ".kts", ".sh",
    ".js", ".mcfunction", ".mcmeta", ".cfg",
}
SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "openai_key": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}"),
    "aws_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "bcrypt_hash": re.compile(rb"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}"),
    "high_entropy_json_credential": re.compile(
        rb'"(?:auth|password|passwordHash|token|secret)"\s*:\s*'
        rb'"(?!CHANGE_ME_LOCAL_ONLY|<[^>]+>)[A-Za-z0-9_./+$=-]{20,}"'
    ),
}
UUID_RE = re.compile(rb"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
                     rb"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
WORD_RE = re.compile(rb"(?i)\b[A-Za-z][A-Za-z0-9_]{2,31}\b")
# SHA-256(lowercase token), not the production values themselves.
IDENTITY_DIGESTS = {
    "3827FB8E86E1A19310E1C716F928EEFDD36F41D337F3775603404A94032530D8",
    "0D468F0BFD00E1479E7B195F7A2ECF9D6C7AC40E7C6DC7FF6F1A06B6FA776D74",
    "FABD232886F73E44DACA35C0A7B77BD682AD827934619E901B3447DD3D5BB99D",
    "A2032E91F499FCA2E89CDB7F0ED3FCE93655C9A28DAC97750EBDA46B00960677",
}
SELF = Path(__file__).resolve()
SKIP_DIRS = {".git", "__pycache__", ".gradle", "build", "run", "logs", "tmp"}


def token_digest(token: bytes) -> str:
    return hashlib.sha256(token.lower()).hexdigest().upper()


def validate_patterns() -> None:
    samples = {
        "openai_key": b"sk-" + b"A" * 24,
        "aws_key": b"AKIA" + b"A" * 16,
        "bcrypt_hash": b"$2b$12$" + b"A" * 53,
        "high_entropy_json_credential": b'{"token":"' + b"A" * 24 + b'"}',
    }
    for label, sample in samples.items():
        pattern = SECRET_PATTERNS[label]
        if b"\x08" in pattern.pattern or not pattern.search(sample):
            raise SystemExit(f"repository checker regex self-test failed: {label}")
    uuid_sample = b"123e4567-e89b-42d3-a456-426614174000"
    if b"\x08" in UUID_RE.pattern or not UUID_RE.search(uuid_sample):
        raise SystemExit("repository checker regex self-test failed: UUID_RE")


def check_file(path: Path, errors: list[str]) -> None:
    rel = path.relative_to(ROOT)
    if any(part.lower() in SKIP_DIRS for part in rel.parts):
        return
    if any(part.lower() in FORBIDDEN_COMPONENTS for part in rel.parts):
        errors.append(f"forbidden generated cache directory: {rel}")
    size = path.stat().st_size
    if size > MAX_FILE:
        errors.append(f"oversize file ({size} bytes): {rel}")
    lower_name = path.name.lower()
    if lower_name in FORBIDDEN_NAMES:
        errors.append(f"forbidden live/identity file: {rel}")
    if lower_name.endswith("server.properties") and not lower_name.endswith(
        "server.properties.example"
    ):
        errors.append(f"forbidden live configuration: {rel}")
    if path.suffix.lower() in FORBIDDEN_SUFFIX:
        # Gradle's wrapper is the only binary deliberately permitted.
        if not rel.as_posix().lower().endswith("gradle/wrapper/gradle-wrapper.jar"):
            errors.append(f"forbidden generated/binary artifact: {rel}")
    if rel.parts and rel.parts[0].lower() in FORBIDDEN_TOP:
        errors.append(f"forbidden top-level runtime directory: {rel}")
    if path == SELF or size > 2 * 1024 * 1024:
        return
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return
    data = path.read_bytes()
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(data):
            errors.append(f"possible {label}: {rel}")
    for match in UUID_RE.findall(data):
        if token_digest(match) in IDENTITY_DIGESTS:
            errors.append(f"known production UUID/identity: {rel}")
    for match in WORD_RE.findall(data):
        if token_digest(match) in IDENTITY_DIGESTS:
            errors.append(f"known production name/identity: {rel}")


validate_patterns()
errors: list[str] = []
files = 0
total = 0
for candidate in ROOT.rglob("*"):
    if not candidate.is_file():
        continue
    relative = candidate.relative_to(ROOT)
    if any(part.lower() in SKIP_DIRS for part in relative.parts):
        continue
    files += 1
    total += candidate.stat().st_size
    check_file(candidate, errors)

if errors:
    print("REPOSITORY_CHECK_FAILED")
    for error in sorted(set(errors)):
        print(f"- {error}")
    raise SystemExit(1)

print(f"REPOSITORY_CHECK_PASS files={files} bytes={total}")
