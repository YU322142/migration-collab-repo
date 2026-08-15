#!/usr/bin/env python3
"""Parallel, read-only scan of all region files for Cookery chopping boards."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import io
import json
import os
import zlib
from pathlib import Path

import nbtlib


TARGET_ID = "kaleidoscope_cookery:chopping_board"


def plain(value):
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def decompress(payload: bytes, kind: int) -> bytes:
    kind &= 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def scan_region(path_text: str) -> dict:
    path = Path(path_text)
    chunks = 0
    block_entities = 0
    matches: list[dict] = []
    errors: list[dict] = []
    if path.stat().st_size == 0:
        return {
            "region": str(path),
            "chunks": 0,
            "block_entities": 0,
            "matches": [],
            "errors": [],
            "empty_placeholder": True,
        }
    try:
        with path.open("rb") as handle:
            locations = handle.read(4096)
            if len(locations) != 4096:
                raise ValueError("truncated location table")
            for slot in range(1024):
                entry = locations[slot * 4 : (slot + 1) * 4]
                offset = int.from_bytes(entry[:3], "big")
                if not offset:
                    continue
                chunks += 1
                try:
                    handle.seek(offset * 4096)
                    length_bytes = handle.read(4)
                    if len(length_bytes) != 4:
                        raise ValueError("truncated chunk length")
                    length = int.from_bytes(length_bytes, "big")
                    kind_bytes = handle.read(1)
                    if not kind_bytes:
                        raise ValueError("missing compression byte")
                    kind = kind_bytes[0]
                    if kind & 0x80:
                        raise ValueError("external .mcc chunks are not supported by this audit")
                    raw = decompress(handle.read(length - 1), kind)
                    chunk = nbtlib.File.parse(io.BytesIO(raw), byteorder="big")
                    values = []
                    for key in ("block_entities", "BlockEntities", "blockEntities"):
                        if key in chunk:
                            values = chunk[key]
                            break
                        if "Level" in chunk and key in chunk["Level"]:
                            values = chunk["Level"][key]
                            break
                    block_entities += len(values)
                    for value in values:
                        if str(value.get("id", "")) == TARGET_ID:
                            matches.append({"region": str(path), "slot": slot, "value": plain(value)})
                except Exception as exc:  # fail closed and preserve exact location
                    errors.append({"region": str(path), "slot": slot, "error": repr(exc)})
    except Exception as exc:
        errors.append({"region": str(path), "slot": None, "error": repr(exc)})
    return {
        "region": str(path),
        "chunks": chunks,
        "block_entities": block_entities,
        "matches": matches,
        "errors": errors,
        "empty_placeholder": False,
    }


def stack_empty(value) -> bool:
    return value in (None, {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path)
    parser.add_argument("--workers", type=int, default=min(12, os.cpu_count() or 1))
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    regions = sorted(path for path in args.world.rglob("*.mca") if "region" in path.parts)
    if not regions:
        raise SystemExit("no terrain region files found")

    matches: list[dict] = []
    errors: list[dict] = []
    chunks = 0
    block_entities = 0
    empty_placeholders = 0
    completed = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(scan_region, str(path)) for path in regions]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            chunks += result["chunks"]
            block_entities += result["block_entities"]
            matches.extend(result["matches"])
            errors.extend(result["errors"])
            empty_placeholders += int(result["empty_placeholder"])
            completed += 1
            if completed % 100 == 0 or completed == len(regions):
                print(f"progress={completed}/{len(regions)} matches={len(matches)} errors={len(errors)}", flush=True)

    matches.sort(key=lambda row: (row["region"], row["slot"], row["value"].get("x", 0), row["value"].get("z", 0)))
    exact_empty_air = []
    air_nonempty_or_progress = []
    missing_model = []
    for row in matches:
        value = row["value"]
        model = value.get("ModelId")
        empty = (
            int(value.get("MaxCutCount", 0)) == 0
            and int(value.get("CurrentCutCount", 0)) == 0
            and stack_empty(value.get("CurrentCutStack"))
            and stack_empty(value.get("ResultItem"))
        )
        if model == "minecraft:air":
            (exact_empty_air if empty else air_nonempty_or_progress).append(row)
        if model in (None, ""):
            missing_model.append(row)

    failures = []
    if errors:
        failures.append("region_parse_errors")
    if air_nonempty_or_progress:
        failures.append("air_model_with_nonempty_or_progress_data")
    report = {
        "schema": 1,
        "status": "PASS" if not failures else "FAIL",
        "world": str(args.world.resolve()),
        "target_id": TARGET_ID,
        "workers": args.workers,
        "region_files": len(regions),
        "chunks": chunks,
        "block_entities": block_entities,
        "empty_region_placeholders": empty_placeholders,
        "match_count": len(matches),
        "exact_empty_air_count": len(exact_empty_air),
        "air_nonempty_or_progress_count": len(air_nonempty_or_progress),
        "missing_model_count": len(missing_model),
        "matches": matches,
        "exact_empty_air": exact_empty_air,
        "air_nonempty_or_progress": air_nonempty_or_progress,
        "missing_model": missing_model,
        "errors": errors,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.report.with_suffix(args.report.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(args.report)
    print(json.dumps({"status": report["status"], "report": str(args.report), "matches": len(matches), "errors": len(errors)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
