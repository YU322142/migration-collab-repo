from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

import nbtlib


def plain(value):
    if hasattr(value, "unpack"):
        return plain(value.unpack())
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def load(path: Path):
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return plain(nbtlib.load(path))


def kind(value):
    if isinstance(value, dict):
        return "compound"
    if isinstance(value, list):
        return "list"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if value is None:
        return "null"
    return type(value).__name__


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def diff(a, b, path="", out=None, limit=10000):
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) - set(b)):
            out.append({"path": f"{path}.{key}" if path else key, "kind": "missing_in_target", "source_type": kind(a[key])})
        for key in sorted(set(b) - set(a)):
            out.append({"path": f"{path}.{key}" if path else key, "kind": "extra_in_target", "target_type": kind(b[key])})
        for key in sorted(set(a) & set(b)):
            diff(a[key], b[key], f"{path}.{key}" if path else key, out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append({"path": path, "kind": "list_length", "source": len(a), "target": len(b)})
        for idx, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{idx}]", out, limit)
    elif kind(a) != kind(b):
        out.append({"path": path, "kind": "type", "source_type": kind(a), "target_type": kind(b), "source": a, "target": b})
    elif a != b:
        # Do not emit enormous arrays; retain values for scalar/player-visible fields.
        sa = a if not isinstance(a, (dict, list)) else None
        sb = b if not isinstance(b, (dict, list)) else None
        out.append({"path": path, "kind": "value", "source": sa, "target": sb, "source_hash": digest(a), "target_hash": digest(b)})
    return out


def item_ids(value):
    found = collections.Counter()
    def visit(v):
        if isinstance(v, dict):
            if isinstance(v.get("id"), str) and ":" in v["id"]:
                found[v["id"]] += int(v.get("count", 1) or 1)
            for child in v.values():
                visit(child)
        elif isinstance(v, list):
            for child in v:
                visit(child)
    visit(value)
    return found


def component_ids(value):
    found = collections.Counter()
    def visit(v):
        if isinstance(v, dict):
            # Item components are usually nested under components; report their exact IDs.
            comp = v.get("components")
            if isinstance(comp, dict):
                for key in comp:
                    found[key] += 1
            for child in v.values():
                visit(child)
        elif isinstance(v, list):
            for child in v:
                visit(child)
    visit(value)
    return found


def compare_file(src: Path, dst: Path, max_diffs: int = 10000):
    a = load(src)
    b = load(dst)
    changes = diff(a, b, limit=max_diffs)
    return {
        "source": str(src),
        "target": str(dst),
        "source_hash": digest(a),
        "target_hash": digest(b),
        "source_top_keys": sorted(a),
        "target_top_keys": sorted(b),
        "diff_count_capped": len(changes),
        "diffs": changes,
        "source_item_ids": dict(item_ids(a)),
        "target_item_ids": dict(item_ids(b)),
        "source_component_ids": dict(component_ids(a)),
        "target_component_ids": dict(component_ids(b)),
    }


def compare_dir(src_dir: Path, dst_dir: Path, pattern: str):
    rows = []
    src = {p.name: p for p in src_dir.glob(pattern)} if src_dir.exists() else {}
    dst = {p.name: p for p in dst_dir.glob(pattern)} if dst_dir.exists() else {}
    for name in sorted(set(src) | set(dst)):
        if name not in src:
            rows.append({"file": name, "kind": "extra_in_target"})
        elif name not in dst:
            rows.append({"file": name, "kind": "missing_in_target"})
        else:
            rows.append(compare_file(src[name], dst[name]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("target", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    sw = args.source / "world"
    tw = args.target / "world"
    out = {
        "level": compare_file(sw / "level.dat", tw / "level.dat"),
        "playerdata": compare_dir(sw / "playerdata", tw / "playerdata", "*.dat"),
        "data": compare_dir(sw / "data", tw / "data", "*.dat"),
        "advancements": compare_dir(sw / "advancements", tw / "advancements", "*.json"),
        "stats": compare_dir(sw / "stats", tw / "stats", "*.json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"level_diffs": out["level"]["diff_count_capped"], "player_files": len(out["playerdata"]), "data_files": len(out["data"]), "advancement_files": len(out["advancements"]), "stats_files": len(out["stats"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
