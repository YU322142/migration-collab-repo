"""Inspect migration candidate jars without modifying the audit workspace."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ is expected
    tomllib = None


KEYWORDS = (
    "barched",
    "chest",
    "dynamic",
    "froglight",
    "happyghast",
    "cookery",
    "kaleidoscope_end",
    "kaleidoscope-nether",
    "kaleidoscopetavern",
    "mineastr-0.6.25",
    "mishanguc-pale",
    "nautilus-equivalence",
    "nautilus-alias",
    "potted-farms-1.1.1-equivalence3",
    "toms_storage-neoforge-1.21.1-2.4.1-perf5.2",
    "waypoint-fire",
    "xiyuslogin",
)

EXTRA_NAMES = {
    "i_want_my_nautilus-0.1-neoforge-1.21.1.jar",
    "platform-neoforge-1.21.1-1.3.3.jar",
    "VanillaBackport-neoforge-1.21.1-1.1.7.10.jar",
}


def candidate_paths(root: pathlib.Path, explicit: list[pathlib.Path] | None = None) -> list[pathlib.Path]:
    paths: set[pathlib.Path] = set()
    for path in explicit or []:
        if path.is_file() and path.suffix.lower() == ".jar":
            paths.add(path.resolve())
    for path in root.rglob("*.jar"):
        text = str(path).lower()
        if "\\build\\libs\\" in text or path.parent.name == "Potted-Farms-1.21.1-equivalence":
            if "sources" not in path.name.lower() and any(k in path.name.lower() for k in KEYWORDS):
                paths.add(path.resolve())
    nautilus = root / "nautilus-backport-audit"
    for name in EXTRA_NAMES:
        path = nautilus / name
        if path.is_file():
            paths.add(path.resolve())
    return sorted(paths, key=lambda path: str(path).lower())


def inspect(path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    record: dict = {
        "path": str(path),
        "name": path.name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest().upper(),
    }
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            record["zip_valid"] = archive.testzip() is None
            manifests = {
                name for name in (
                    "META-INF/neoforge.mods.toml",
                    "META-INF/mods.toml",
                    "fabric.mod.json",
                    "quilt.mod.json",
                ) if name in names
            }
            record["manifest_files"] = sorted(manifests)
            if "META-INF/neoforge.mods.toml" in names and tomllib is not None:
                data = tomllib.loads(archive.read("META-INF/neoforge.mods.toml").decode("utf-8"))
                record["loader"] = "neoforge"
                record["mods"] = [
                    {
                        "id": item.get("modId"),
                        "version": item.get("version"),
                        "display": item.get("displayName"),
                        "display_test": item.get("displayTest"),
                    }
                    for item in data.get("mods", [])
                ]
                raw_dependencies = data.get("dependencies", {})
                dependency_items = []
                if isinstance(raw_dependencies, dict):
                    for value in raw_dependencies.values():
                        dependency_items.extend(value if isinstance(value, list) else [value])
                elif isinstance(raw_dependencies, list):
                    dependency_items = raw_dependencies
                record["mandatory_dependencies"] = [
                    {
                        "mod_id": item.get("modId"),
                        "version_range": item.get("versionRange"),
                        "side": item.get("side"),
                        "ordering": item.get("ordering"),
                    }
                    for item in dependency_items
                    if isinstance(item, dict)
                    if item.get("mandatory") is True or item.get("type") == "required"
                ]
            elif "fabric.mod.json" in names:
                data = json.loads(archive.read("fabric.mod.json").decode("utf-8"))
                record["loader"] = "fabric"
                record["mods"] = [{
                    "id": data.get("id"),
                    "version": data.get("version"),
                    "display": data.get("name"),
                }]
    except (OSError, zipfile.BadZipFile, UnicodeError, ValueError) as exc:
        record["zip_valid"] = False
        record["error"] = type(exc).__name__
    return record


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--only":
        explicit = [pathlib.Path(arg) for arg in sys.argv[2:]]
        print(json.dumps([inspect(path.resolve()) for path in explicit if path.is_file()], ensure_ascii=False, indent=2))
        return 0
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\Trans\migration-audit-work")
    explicit = [pathlib.Path(arg) for arg in sys.argv[2:]]
    print(json.dumps([inspect(path) for path in candidate_paths(root, explicit)], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
