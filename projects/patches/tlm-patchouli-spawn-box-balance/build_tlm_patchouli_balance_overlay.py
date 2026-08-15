#!/usr/bin/env python3
"""Build a client-only Patchouli overlay without changing TLM gameplay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import zipfile
from pathlib import Path


RECIPE_ID = "touhou_little_maid:altar_recipe/spawn_box"
JAR_NAME = "touhoulittlemaid-1.5.3-neoforge+mc1.21.1.jar"
EXPECTED_JAR_SHA256 = (
    "F6DB04195820C8508704277EA76D63723804FF236A7B780369BA59EBE5CD9C27"
)
ENTRY_SPECS = {
    "maid/spawn_maid.json": {
        "jar_entry": (
            "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
            "en_us/entries/maid/spawn_maid.json"
        ),
        "source_sha256": (
            "F536A1BB528B4F7A8458C88985601F06E5225D33B34ACDA6F7A061E6B47AF2B3"
        ),
        "removed_page_index": 2,
    },
    "overview/multiblocks_altar.json": {
        "jar_entry": (
            "assets/touhou_little_maid/patchouli_books/memorizable_gensokyo/"
            "en_us/entries/overview/multiblocks_altar.json"
        ),
        "source_sha256": (
            "6DB3EA530DC9B745D5A31CDBB4CE34C3711B105F48F449E18AC69D692AF4F98E"
        ),
        "removed_page_index": 4,
    },
}
OVERLAY_ASSET_ROOT = Path(
    "overlay/kubejs/assets/touhou_little_maid/patchouli_books/"
    "memorizable_gensokyo/en_us/entries"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def remove_stale_recipe_page(source: dict[str, object]) -> tuple[dict[str, object], int, dict[str, object]]:
    pages = source.get("pages")
    if not isinstance(pages, list):
        raise ValueError("Patchouli entry has no pages array")
    matches = [
        (index, page)
        for index, page in enumerate(pages)
        if isinstance(page, dict)
        and page.get("type") == "altar_recipe"
        and page.get("recipe_id") == RECIPE_ID
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one stale recipe page, found {len(matches)}")
    index, removed_page = matches[0]
    patched = copy.deepcopy(source)
    del patched["pages"][index]
    return patched, index, copy.deepcopy(removed_page)


def build(client_root: Path, output_root: Path) -> dict[str, object]:
    client_root = client_root.resolve()
    output_root = output_root.resolve()
    if output_root == client_root or client_root in output_root.parents:
        raise ValueError("output root must not be inside the immutable Attempt9 client")

    jar_path = client_root / "mods" / JAR_NAME
    if not jar_path.is_file():
        raise FileNotFoundError(jar_path)
    actual_jar_sha = sha256_file(jar_path)
    if actual_jar_sha != EXPECTED_JAR_SHA256:
        raise ValueError(
            f"TLM JAR provenance mismatch: expected={EXPECTED_JAR_SHA256} "
            f"actual={actual_jar_sha}"
        )

    results: list[dict[str, object]] = []
    with zipfile.ZipFile(jar_path) as archive:
        for relative, spec in ENTRY_SPECS.items():
            entry = str(spec["jar_entry"])
            source_bytes = archive.read(entry)
            source_sha = sha256_bytes(source_bytes)
            if source_sha != spec["source_sha256"]:
                raise ValueError(
                    f"entry provenance mismatch for {entry}: "
                    f"expected={spec['source_sha256']} actual={source_sha}"
                )
            source = json.loads(source_bytes.decode("utf-8"))
            patched, removed_index, removed_page = remove_stale_recipe_page(source)
            if removed_index != spec["removed_page_index"]:
                raise ValueError(
                    f"unexpected removed page index for {entry}: {removed_index}"
                )

            output_path = output_root / OVERLAY_ASSET_ROOT / relative
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_bytes = (
                json.dumps(patched, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            output_path.write_bytes(output_bytes)
            results.append(
                {
                    "source_entry": entry,
                    "source_sha256": source_sha,
                    "output_path": output_path.relative_to(output_root).as_posix(),
                    "output_bytes": len(output_bytes),
                    "output_sha256": sha256_bytes(output_bytes),
                    "pages_before": len(source["pages"]),
                    "pages_after": len(patched["pages"]),
                    "removed_page_index": removed_index,
                    "removed_page": removed_page,
                }
            )

    report = {
        "schema": 1,
        "policy": "preserve_mechanomania_balance_remove_only_stale_patchouli_pages",
        "side": "CLIENT",
        "server_changes": [],
        "client_root": str(client_root),
        "source_jar": str(jar_path),
        "source_jar_sha256": actual_jar_sha,
        "recipe_id_remains_removed_by_server": RECIPE_ID,
        "entries": results,
    }
    report_path = output_root / "reports" / "exact-entry-diff.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-root", required=True, type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    args = parser.parse_args()
    try:
        report = build(args.client_root, args.output_root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
