from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path


KEYS = (
    "commands.spawnpoint.success.single.new",
    "commands.spawnpoint.success.multiple.new",
)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "mc-1.21.11-to-1.21.1-migration-audit/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def decode_json(payload: bytes, source: str):
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid UTF-8 JSON from {source}: {exc}") from exc


def selected_locale(payload: dict, source: str):
    missing = [key for key in KEYS if not isinstance(payload.get(key), str)]
    if missing:
        raise ValueError(f"{source} is missing string keys: {', '.join(missing)}")
    return {key: payload[key] for key in KEYS}


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".migration.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser(description="Extract official 1.21.11 spawnpoint translations for a 1.21.1 resource overlay.")
    parser.add_argument("--asset-index-url", required=True)
    parser.add_argument("--en-us-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    index_bytes = download(args.asset_index_url)
    index = decode_json(index_bytes, args.asset_index_url)
    objects = index.get("objects")
    if not isinstance(objects, dict):
        raise ValueError("asset index has no objects map")

    records = []
    for logical_name, descriptor in sorted(objects.items()):
        if not logical_name.startswith("minecraft/lang/") or not logical_name.endswith(".json"):
            continue
        if not isinstance(descriptor, dict) or not isinstance(descriptor.get("hash"), str):
            raise ValueError(f"invalid descriptor for {logical_name}")
        object_hash = descriptor["hash"]
        url = f"https://resources.download.minecraft.net/{object_hash[:2]}/{object_hash}"
        payload = download(url)
        actual_hash = hashlib.sha1(payload).hexdigest()
        if actual_hash != object_hash:
            raise ValueError(f"SHA-1 mismatch for {logical_name}: expected {object_hash}, got {actual_hash}")
        expected_size = descriptor.get("size")
        if isinstance(expected_size, int) and len(payload) != expected_size:
            raise ValueError(f"size mismatch for {logical_name}: expected {expected_size}, got {len(payload)}")
        locale = Path(logical_name).stem
        selected = selected_locale(decode_json(payload, url), logical_name)
        target = args.output / f"{locale}.json"
        atomic_json(target, selected)
        records.append({
            "locale": locale,
            "source": logical_name,
            "source_sha1": object_hash,
            "source_size": len(payload),
            "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        })

    en_payload = args.en_us_source.read_bytes()
    en_target = args.output / "en_us.json"
    atomic_json(en_target, selected_locale(decode_json(en_payload, str(args.en_us_source)), str(args.en_us_source)))
    records.append({
        "locale": "en_us",
        "source": str(args.en_us_source.resolve()),
        "source_sha256": hashlib.sha256(en_payload).hexdigest(),
        "source_size": len(en_payload),
        "output_sha256": hashlib.sha256(en_target.read_bytes()).hexdigest(),
    })

    records.sort(key=lambda record: record["locale"])
    manifest = {
        "asset_index_url": args.asset_index_url,
        "asset_index_sha1": hashlib.sha1(index_bytes).hexdigest(),
        "keys": list(KEYS),
        "locales": len(records),
        "records": records,
    }
    atomic_json(args.manifest, manifest)
    print(json.dumps({
        "locales": len(records),
        "asset_index_sha1": manifest["asset_index_sha1"],
        "manifest": str(args.manifest),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
