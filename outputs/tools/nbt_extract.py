import argparse
import json
from pathlib import Path

import nbtlib


def plain(v):
    if hasattr(v, "unpack"):
        return plain(v.unpack())
    if hasattr(v, "tolist"):
        return plain(v.tolist())
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v


def get(root, path):
    cur = root
    for part in path.split(".") if path else []:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return plain(cur)


ap = argparse.ArgumentParser()
ap.add_argument("file", type=Path)
ap.add_argument("paths", nargs="*")
ap.add_argument("--output", type=Path)
a = ap.parse_args()
root = nbtlib.load(a.file)
out = {p: get(root, p) for p in a.paths} if a.paths else plain(root)
s = json.dumps(out, ensure_ascii=False, indent=2)
if a.output:
    a.output.write_text(s, encoding="utf-8")
else:
    print(s)
