#!/usr/bin/env python3
"""Scrub private host, identity, and local-user paths from the Git snapshot.

This tool operates only inside the collaboration repository. It never reads
or writes a live client, server, world, or external artifact root.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
TEXT_SUFFIXES = {
    "", ".txt", ".md", ".json", ".json5", ".yml", ".yaml", ".toml",
    ".properties", ".py", ".ps1", ".java", ".gradle", ".kts", ".sh",
    ".js", ".mcfunction", ".mcmeta", ".cfg", ".xml",
}
SKIP_DIRS = {".git", "__pycache__", ".gradle", "build", "run", "logs", "tmp"}

# The patterns deliberately use flexible slash matching so they also scrub
# JSON-escaped Windows paths containing doubled backslashes.
PRIVATE_USER_TEXT = "YU" + "322142"
PRIVATE_DOMAIN_TEXT = "322142" + ".xyz"
WORKSPACE_PATH = re.compile(
    r"C:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+"
    + re.escape(PRIVATE_USER_TEXT)
    + r"(?:\\\\|\\|/)+Documents(?:\\\\|\\|/)+Codex"
    + r"(?:\\\\|\\|/)+(?:2026-08-07(?:\\\\|\\|/)+d-trans-1-21-11-1"
    + r"|2026-08-08(?:\\\\|\\|/)+new-chat)",
    re.IGNORECASE,
)
USER_HOME_PATH = re.compile(
    r"C:(?:\\\\|\\|/)+Users(?:\\\\|\\|/)+" + re.escape(PRIVATE_USER_TEXT),
    re.IGNORECASE,
)
PRIVATE_HOST = re.compile(r"mc\." + re.escape(PRIVATE_DOMAIN_TEXT), re.IGNORECASE)
PRIVATE_DOMAIN = re.compile(
    r"(?<![A-Za-z0-9.-])" + re.escape(PRIVATE_DOMAIN_TEXT), re.IGNORECASE
)


def scrub(text: str) -> str:
    text = WORKSPACE_PATH.sub("<WORKSPACE>", text)
    text = USER_HOME_PATH.sub("<USER_HOME>", text)
    text = PRIVATE_HOST.sub("play.example.invalid", text)
    text = PRIVATE_DOMAIN.sub("example.invalid", text)
    return text


rewritten: list[str] = []
for path in sorted(ROOT.rglob("*"), key=lambda item: item.as_posix().lower()):
    if not path.is_file() or path == SELF:
        continue
    rel = path.relative_to(ROOT)
    if any(part.lower() in SKIP_DIRS for part in rel.parts):
        continue
    if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 8 * 1024 * 1024:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError:
        continue
    updated = scrub(text)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")
        rewritten.append(rel.as_posix())

print(f"SNAPSHOT_SANITIZED rewritten={len(rewritten)}")
for rel in rewritten:
    print(f"REWRITTEN {rel}")
