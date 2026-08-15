#!/usr/bin/env python3
"""Produce a read-only schema/count audit for Create's create_tracks.dat."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import nbtlib


UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def tag_name(value) -> str:
    return type(value).__name__


def scalar(value):
    if hasattr(value, "unpack"):
        return scalar(value.unpack())
    if hasattr(value, "tolist"):
        return scalar(value.tolist())
    if isinstance(value, dict):
        return {str(k): scalar(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scalar(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = nbtlib.load(args.input)
    path_types: dict[str, Counter] = defaultdict(Counter)
    path_occurrences = Counter()
    uuid_strings: dict[str, Counter] = defaultdict(Counter)
    int4_arrays: dict[str, Counter] = defaultdict(Counter)
    compound_key_shapes: dict[str, Counter] = defaultdict(Counter)
    list_lengths: dict[str, Counter] = defaultdict(Counter)
    item_stack_candidates = Counter()

    def visit(value, path: str) -> None:
        path_types[path][tag_name(value)] += 1
        path_occurrences[path] += 1

        if isinstance(value, nbtlib.Compound):
            keys = tuple(sorted(str(k) for k in value.keys()))
            compound_key_shapes[path]["|".join(keys)] += 1
            lowered = {str(k).lower() for k in value.keys()}
            if "id" in lowered and ("count" in lowered or "Count" in value):
                item_stack_candidates[path] += 1
            for key, child in value.items():
                visit(child, f"{path}.{key}" if path else str(key))
            return

        if isinstance(value, nbtlib.List):
            list_lengths[path][str(len(value))] += 1
            for child in value:
                visit(child, f"{path}[]")
            return

        if isinstance(value, nbtlib.Array):
            unpacked = value.unpack()
            length = len(unpacked)
            list_lengths[path][str(length)] += 1
            if isinstance(value, nbtlib.IntArray) and length == 4:
                int4_arrays[path][json.dumps(scalar(unpacked))] += 1
            return

        unpacked = scalar(value)
        if isinstance(unpacked, str) and UUID_RE.fullmatch(unpacked):
            uuid_strings[path][unpacked.lower()] += 1

    visit(root, "")

    data = root.get("data", {})
    top_counts = {}
    if isinstance(data, nbtlib.Compound):
        for key, value in data.items():
            top_counts[str(key)] = len(value) if hasattr(value, "__len__") else None

    report = {
        "input": str(args.input.resolve()),
        "input_size": args.input.stat().st_size,
        "input_sha256": sha256(args.input),
        "data_version": scalar(root.get("DataVersion")),
        "root_keys": list(root.keys()),
        "data_keys": list(data.keys()) if isinstance(data, nbtlib.Compound) else None,
        "top_level_counts": top_counts,
        "path_types": {
            path or "<root>": dict(sorted(counter.items()))
            for path, counter in sorted(path_types.items())
        },
        "compound_key_shapes": {
            path or "<root>": dict(counter.most_common())
            for path, counter in sorted(compound_key_shapes.items())
        },
        "list_lengths": {
            path or "<root>": dict(sorted(counter.items(), key=lambda item: int(item[0])))
            for path, counter in sorted(list_lengths.items())
        },
        "uuid_strings": {
            path: {
                "count": sum(counter.values()),
                "unique": len(counter),
                "examples": list(counter.keys())[:5],
            }
            for path, counter in sorted(uuid_strings.items())
        },
        "int4_arrays": {
            path: {
                "count": sum(counter.values()),
                "unique": len(counter),
                "examples": list(counter.keys())[:5],
            }
            for path, counter in sorted(int4_arrays.items())
        },
        "item_stack_candidate_paths": dict(sorted(item_stack_candidates.items())),
    }

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
