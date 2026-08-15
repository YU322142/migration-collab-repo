#!/usr/bin/env python3
"""Find an ASCII/UTF-8 byte sequence inside entries of JAR files."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("needles", nargs="+")
    args = parser.parse_args()
    needles = [(item, item.encode("utf-8")) for item in args.needles]
    for jar in sorted(args.root.glob("*.jar"), key=lambda path: path.name.lower()):
        try:
            with zipfile.ZipFile(jar) as archive:
                for entry in archive.infolist():
                    if entry.is_dir() or entry.file_size > 32 * 1024 * 1024:
                        continue
                    payload = archive.read(entry)
                    for label, needle in needles:
                        if needle in payload:
                            print(f"{jar.name}\t{entry.filename}\t{label}")
        except zipfile.BadZipFile:
            print(f"BAD_JAR\t{jar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
