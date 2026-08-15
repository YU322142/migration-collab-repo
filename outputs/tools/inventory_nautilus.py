from __future__ import annotations

import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import compare_world_entities as compare


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(f"usage: {sys.argv[0]} <server-root> [--summary]")
    server = pathlib.Path(sys.argv[1]).resolve()
    summary_only = len(sys.argv) == 3 and sys.argv[2] == "--summary"
    rows = []
    counts = collections.Counter()

    for root, dimension in compare.roots(server, "entities"):
        for region in sorted(root.glob("*.mca")):
            for slot, chunk in compare.read_region(region):
                for raw in compare.list_values(chunk, ("Entities", "entities")):
                    queue = [(raw, True)]
                    while queue:
                        entity, top_level = queue.pop(0)
                        plain = compare.plain(entity)
                        identifier = str(plain.get("id", ""))
                        counts[identifier] += 1
                        if identifier.endswith("nautilus") and top_level:
                            rows.append(
                                {
                                    "id": identifier,
                                    "uuid": plain.get("UUID"),
                                    "pos": plain.get("Pos"),
                                    "dimension": dimension,
                                    "region": region.name,
                                    "slot": slot,
                                    "keys": sorted(plain),
                                    "equipment": plain.get("equipment"),
                                    "drop_chances": plain.get("drop_chances"),
                                    "home_pos": plain.get("home_pos"),
                                    "home_radius": plain.get("home_radius"),
                                    "variant": plain.get("variant"),
                                    "owner": plain.get("Owner"),
                                    "leash": plain.get("leash"),
                                    "passengers": [
                                        str(compare.plain(passenger).get("id", ""))
                                        for passenger in plain.get("Passengers", [])
                                        if isinstance(passenger, dict)
                                    ],
                                }
                            )
                        for passenger in plain.get("Passengers", []):
                            queue.append((passenger, False))

    result = {
        "source": str(server),
        "counts": dict(counts),
        "nautilus_top_level": rows,
        "nautilus_top_level_count": len(rows),
        "nautilus_recursive_count": sum(
            count for identifier, count in counts.items() if identifier.endswith("nautilus")
        ),
    }
    if summary_only:
        print(json.dumps({
            "counts": {key: value for key, value in counts.items() if key.endswith("nautilus")},
            "nautilus_top_level_count": len(rows),
            "nautilus_recursive_count": result["nautilus_recursive_count"],
            "records": rows,
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
