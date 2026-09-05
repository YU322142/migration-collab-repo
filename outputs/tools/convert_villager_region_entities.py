from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path


def load_converter(path: Path):
    spec = importlib.util.spec_from_file_location("convert_world_nbt", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load converter from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def region_names(baseline: dict) -> list[str]:
    names = set()
    dimensions = set()
    for villager in baseline["villagers"]:
        dimensions.add(villager["dimension"])
        names.add(Path(villager["source"]["region"]).name)
    if dimensions != {"minecraft:overworld"}:
        raise ValueError(
            "the selected-region converter currently supports only overworld villagers; "
            f"found {sorted(dimensions)}"
        )
    return sorted(names)


def digest_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_pass(converter, paths: list[Path], game_time: int, dry_run: bool, capability: bool):
    runtime_capabilities = (
        [converter.WAYPOINT_FIRE_CAPABILITY] if capability else []
    )
    audit = converter.new_audit(
        paths[0].parent.parent,
        game_time,
        runtime_capabilities=runtime_capabilities,
    )
    audit["attribute_aliases"] = []
    for path in paths:
        changed, writes = converter.apply_region(
            path, "entities", game_time, dry_run, audit
        )
        if changed:
            audit["regions"].append(
                {
                    "path": str(path),
                    "kind": "entities",
                    "chunks_changed": changed,
                    "writes": writes,
                }
            )
            audit["counts"]["entities"] += changed
    blockers = converter.collect_preflight_blockers(audit)
    audit["counts"] = dict(audit["counts"])
    return audit, blockers


def summarize(audit: dict, blockers: list) -> dict:
    aliases = Counter(
        (record["source"], record["target"])
        for record in audit.get("attribute_aliases", [])
    )
    return {
        "regions_changed": len(audit["regions"]),
        "chunks_changed": audit["counts"].get("entities", 0),
        "attribute_aliases": len(audit.get("attribute_aliases", [])),
        "item_component_schema_aliases": len(
            audit.get("item_component_schema_aliases", [])
        ),
        "item_component_schema_alias_counts": dict(
            Counter(
                record.get("component", "<missing>")
                for record in audit.get("item_component_schema_aliases", [])
            )
        ),
        "attribute_alias_counts": {
            f"{source} -> {target}": count
            for (source, target), count in sorted(aliases.items())
        },
        "unsupported_attributes": len(audit.get("unsupported_attributes", [])),
        "unsupported_entities": len(audit.get("unsupported_entities", [])),
        "unsupported_entity_items": len(audit.get("unsupported_entity_items", [])),
        "blockers": len(blockers),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dry-run", "convert"))
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--converter", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--waypoint-fire-runtime", action="store_true")
    args = parser.parse_args()

    world = args.world.resolve()
    read_only_source = Path(r"<TRANS_ROOT>\20260807\world").resolve()
    if args.mode == "convert" and world == read_only_source:
        raise SystemExit("refusing to write the read-only source world")

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    names = region_names(baseline)
    paths = [world / "entities" / name for name in names]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"missing {len(missing)} selected entity regions: {missing[:10]}")

    converter = load_converter(args.converter.resolve())
    game_time = converter.read_game_time(world)
    before_sha256 = digest_files(paths)
    preflight, blockers = run_pass(
        converter,
        paths,
        game_time,
        True,
        args.waypoint_fire_runtime,
    )
    output = {
        "mode": args.mode,
        "world": str(world),
        "baseline": str(args.baseline.resolve()),
        "selected_regions": len(paths),
        "villagers": len(baseline["villagers"]),
        "game_time": game_time,
        "waypoint_fire_runtime": args.waypoint_fire_runtime,
        "before_sha256": before_sha256,
        "preflight_summary": summarize(preflight, blockers),
        "preflight": preflight,
    }

    if args.mode == "convert" and blockers:
        output["status"] = "BLOCKED"
        output["blockers"] = blockers
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise SystemExit(
            f"preflight blocked conversion: {len(blockers)} records; see {args.report}"
        )

    if args.mode == "convert":
        converted, unexpected_blockers = run_pass(
            converter,
            paths,
            game_time,
            False,
            args.waypoint_fire_runtime,
        )
        if unexpected_blockers:
            raise RuntimeError(
                f"conversion pass unexpectedly produced {len(unexpected_blockers)} blockers"
            )
        verification, verification_blockers = run_pass(
            converter,
            paths,
            game_time,
            True,
            args.waypoint_fire_runtime,
        )
        output["converted_summary"] = summarize(converted, unexpected_blockers)
        output["verification_summary"] = summarize(
            verification, verification_blockers
        )
        output["converted"] = converted
        output["verification"] = verification
        output["after_sha256"] = digest_files(paths)
        output["status"] = (
            "CONVERTED"
            if not verification_blockers
            and not verification.get("attribute_aliases")
            else "VERIFY_FAILED"
        )
    else:
        output["status"] = "PASS" if not blockers else "BLOCKED"
        output["blockers"] = blockers

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": output["status"],
                "selected_regions": output["selected_regions"],
                "villagers": output["villagers"],
                "preflight": output["preflight_summary"],
                "converted": output.get("converted_summary"),
                "verification": output.get("verification_summary"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
