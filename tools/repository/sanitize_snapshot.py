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

# Public snapshots must not expose workstation layout or live deployment
# locations. Keep the replacements stable so scripts remain understandable
# without retaining a usable production path.
AUDIT_ROOT_PATH = re.compile(r"D:(?:\\\\|\\|/)+Trans(?:\\\\|\\|/)+migration-audit-work", re.IGNORECASE)
HANDOFF_ROOT_PATH = re.compile(r"D:(?:\\\\|\\|/)+Trans(?:\\\\|\\|/)+migration-handoff-20260812", re.IGNORECASE)
PUBLICATION_ROOT_PATH = re.compile(r"D:(?:\\\\|\\|/)+Trans(?:\\\\|\\|/)+github-publication-20260819", re.IGNORECASE)
DOWNLOAD_ROOT_PATH = re.compile(r"D:(?:\\\\|\\|/)+Down", re.IGNORECASE)
INSTANCE_ROOT_PATH = re.compile(r"D:(?:\\\\|\\|/)+D(?:\\\\|\\|/)+Tools", re.IGNORECASE)
ASTRBOT_ROOT_PATH = re.compile(r"/(?:opt|srv)/(?:AstrBot|astrbot)(?:/|$)", re.IGNORECASE)
TRANS_ROOT_PATH = re.compile(r"D:(?:\\\\|\\|/)+Trans", re.IGNORECASE)


def scrub(text: str) -> str:
    text = WORKSPACE_PATH.sub("<WORKSPACE>", text)
    text = USER_HOME_PATH.sub("<USER_HOME>", text)
    text = PRIVATE_HOST.sub("play.example.invalid", text)
    text = PRIVATE_DOMAIN.sub("example.invalid", text)
    text = AUDIT_ROOT_PATH.sub("<AUDIT_ROOT>", text)
    text = HANDOFF_ROOT_PATH.sub("<HANDOFF_ROOT>", text)
    text = PUBLICATION_ROOT_PATH.sub("<PUBLICATION_ROOT>", text)
    text = DOWNLOAD_ROOT_PATH.sub("<DOWNLOAD_ROOT>", text)
    text = INSTANCE_ROOT_PATH.sub("<INSTANCE_ROOT>", text)
    text = ASTRBOT_ROOT_PATH.sub("<ASTRBOT_ROOT>/", text)
    text = TRANS_ROOT_PATH.sub("<TRANS_ROOT>", text)
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
