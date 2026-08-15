#!/usr/bin/env python3
"""Standalone integrity and policy validator for the UI-sanitized release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


EXPECTED_JAR = "mods/c6c-1.2.5.1-purified.jar"
EXPECTED_OVERLAY = {
    "overrides/config/create-client.toml",
    "overrides/config/createtweakedcontrollers-client.toml",
    "overrides/config/modernfix-mixins.properties",
    "overrides/kubejs/config/client.json",
}
FORBIDDEN_JAR_ENTRIES = {
    "org/huahua/pr/mixin/BrandingControlMixin.class",
    "org/huahua/pr/mixin/UI/LogoRendererMixin.class",
    "org/huahua/pr/mixin/UI/TitleScreenMixin.class",
    "assets/minecraft/lang/en_us.json",
    "assets/minecraft/lang/zh_cn.json",
}
FORBIDDEN_BYTES = {
    b"https://www.xyebbs.com/resources/1116/prom": "XYEBBS hosting URL",
    b"https://www.bisecthosting.com/curseforge?curseforge_project_id=1469136": (
        "BisectHosting URL"
    ),
    b"Acquire a server": "hosting label",
    b"org/huahua/pr/mixin/UI/TitleScreenMixin": "title-screen mixin reference",
    b"org/huahua/pr/mixin/UI/LogoRendererMixin": "logo mixin reference",
    b"org/huahua/pr/mixin/BrandingControlMixin": "branding mixin reference",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def validate(root: Path) -> dict:
    failures: list[str] = []
    release_manifest_path = root / "manifests/release.json"
    if not release_manifest_path.is_file():
        return {"status": "FAIL", "root": str(root), "failures": [
            "missing manifests/release.json"
        ]}
    manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    expected_hashes = manifest.get("files", {})
    if not isinstance(expected_hashes, dict):
        failures.append("release manifest has no file hash map")
        expected_hashes = {}
    actual_release_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix() != "manifests/release.json"
    }
    expected_release_files = set(expected_hashes)
    if actual_release_files != expected_release_files:
        missing = sorted(expected_release_files - actual_release_files)
        untracked = sorted(actual_release_files - expected_release_files)
        if missing:
            failures.append("manifest-listed files missing: " + ", ".join(missing))
        if untracked:
            failures.append("untracked release files present: " + ", ".join(untracked))
    for relative, expected in sorted(expected_hashes.items()):
        path = root / relative
        if not path.is_file():
            failures.append(f"missing release file: {relative}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(
                f"hash mismatch: {relative}: expected {expected}, got {actual}"
            )

    jar = root / EXPECTED_JAR
    if not jar.is_file():
        failures.append(f"missing {EXPECTED_JAR}")
    elif not zipfile.is_zipfile(jar):
        failures.append("purified C6C artifact is not a readable JAR")
    else:
        with zipfile.ZipFile(jar, "r") as archive:
            bad_crc = archive.testzip()
            if bad_crc:
                failures.append(f"JAR CRC failure: {bad_crc}")
            names = set(archive.namelist())
            remaining = sorted(FORBIDDEN_JAR_ENTRIES & names)
            if remaining:
                failures.append("forbidden JAR entries remain: " + ", ".join(remaining))
            title_assets = sorted(
                name
                for name in names
                if name.startswith("assets/minecraft/textures/gui/title/")
            )
            if title_assets:
                failures.append("pack title assets remain in purified JAR")
            try:
                mixins = json.loads(archive.read("c6c.mixins.json"))
            except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                failures.append(f"invalid c6c.mixins.json: {exc}")
            else:
                if "BrandingControlMixin" in mixins.get("mixins", []):
                    failures.append("C6C branding mixin is still declared")
                for value in ("UI.LogoRendererMixin", "UI.TitleScreenMixin"):
                    if value in mixins.get("client", []):
                        failures.append(f"C6C client UI mixin is still declared: {value}")
                if len(mixins.get("mixins", [])) != 119:
                    failures.append("unexpected retained C6C common mixin count")
                if len(mixins.get("client", [])) != 9:
                    failures.append("unexpected retained C6C client mixin count")
            data_files = [name for name in names if name.startswith("data/") and not name.endswith("/")]
            if len(data_files) != 79:
                failures.append(f"unexpected C6C data file count: {len(data_files)}")
            binary_hits: list[str] = []
            for name in sorted(names):
                if name.endswith("/"):
                    continue
                payload = archive.read(name)
                for needle, label in FORBIDDEN_BYTES.items():
                    if needle in payload:
                        binary_hits.append(f"{label}: {name}")
            if binary_hits:
                failures.append("forbidden hosting/UI payload remains: " + "; ".join(binary_hits))

    overlay_files = {
        path.relative_to(root).as_posix()
        for path in (root / "overrides").rglob("*")
        if path.is_file()
    } if (root / "overrides").is_dir() else set()
    if overlay_files != EXPECTED_OVERLAY:
        failures.append(f"unexpected overlay file set: {sorted(overlay_files)}")
    if (root / "overrides/icon.png").exists() or (root / "icon.png").exists():
        failures.append("Mechanomania pack icon is present")

    create = root / "overrides/config/create-client.toml"
    if create.is_file():
        text = create.read_text(encoding="utf-8")
        if not re.search(r"(?m)^\s*mainMenuConfigButtonRow\s*=\s*0\s*$", text):
            failures.append("Create main-menu config button is enabled")
        if not re.search(r"(?m)^\s*ingameMenuConfigButtonRow\s*=\s*3\s*$", text):
            failures.append("Create in-game config button was not preserved")
    controller = root / "overrides/config/createtweakedcontrollers-client.toml"
    if controller.is_file():
        text = controller.read_text(encoding="utf-8")
        if not re.search(r"(?m)^\s*config_button_main_menu_row\s*=\s*0\s*$", text):
            failures.append("Tweaked Controllers main-menu button is enabled")
        if not re.search(r"(?m)^\s*config_button_ingame_menu_row\s*=\s*3\s*$", text):
            failures.append("Tweaked Controllers in-game button was not preserved")
    modernfix = root / "overrides/config/modernfix-mixins.properties"
    if modernfix.is_file():
        values = re.findall(
            r"(?m)^\s*mixin\.feature\.branding\s*=\s*(true|false)\s*$",
            modernfix.read_text(encoding="utf-8"),
        )
        if values != ["false"]:
            failures.append(f"ModernFix branding override is not uniquely false: {values}")
    kubejs = root / "overrides/kubejs/config/client.json"
    if kubejs.is_file():
        try:
            value = json.loads(kubejs.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            failures.append(f"invalid KubeJS client config: {exc}")
        else:
            if value.get("window_title") != "":
                failures.append("KubeJS Mechanomania window title remains")

    extra_c6c = sorted(
        path.name
        for path in (root / "mods").glob("*.jar")
        if path.name != Path(EXPECTED_JAR).name
        and path.name.lower().startswith("c6c")
    ) if (root / "mods").is_dir() else []
    if extra_c6c:
        failures.append("duplicate/original C6C JARs present: " + ", ".join(extra_c6c))

    return {
        "status": "PASS" if not failures else "FAIL",
        "root": str(root.resolve()),
        "manifest_hash_count": len(expected_hashes),
        "overlay_files_verified": len(overlay_files),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release", type=Path)
    args = parser.parse_args()
    result = validate(args.release.resolve())
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
