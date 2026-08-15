#!/usr/bin/env python3
"""Build object-level Create storage OTA draft ledgers from audited evidence.

The builder never mutates a world.  It binds every member to the stopped
world's block entity identity and block state, embeds only audited payloads,
and splits fluid fields into deterministic passes so one block entity appears
at most once in each package.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import nbtlib

import create_storage_object_ota as ota


DIMENSION_PREFIX = {
    "minecraft:overworld": PurePosixPath("region"),
    "minecraft:the_nether": PurePosixPath("DIM-1/region"),
    "minecraft:the_end": PurePosixPath("DIM1/region"),
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ota.OtaError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def region_path_for(dimension: str, chunk: Mapping[str, Any]) -> PurePosixPath:
    prefix = DIMENSION_PREFIX.get(dimension)
    if prefix is None:
        raise ota.OtaError(f"unsupported dimension: {dimension}")
    name = chunk.get("region_file")
    if not isinstance(name, str) or ota.REGION_NAME.fullmatch(name) is None:
        raise ota.OtaError(f"invalid region filename: {name!r}")
    return prefix / name


def load_live_member(
    world: Path,
    dimension: str,
    pos: list[int],
    region_path: PurePosixPath,
) -> tuple[Mapping[str, Any], Mapping[str, Any], list[int]]:
    if len(pos) != 3 or not all(isinstance(value, int) for value in pos):
        raise ota.OtaError(f"invalid position: {pos!r}")
    chunk = [math.floor(pos[0] / 16), math.floor(pos[2] / 16)]
    image = ota.read_chunk_image(ota.local_path(world, region_path), ota.slot_for_chunk(*chunk))
    if image is None:
        raise ota.OtaError(f"missing live chunk for {dimension}:{pos}")
    block_entity = ota.find_block_entity(image.chunk, tuple(pos))
    if block_entity is None:
        raise ota.OtaError(f"missing live block entity for {dimension}:{pos}")
    block_state = ota.block_state_at(image.chunk, tuple(pos))
    return block_entity, block_state, chunk


def stable_identity(block_entity: Mapping[str, Any], structural: str) -> tuple[dict[str, Any], list[str]]:
    stable: dict[str, Any] = {}
    for key in ("Controller", "LastKnownPos", "Size", "Length", "Height", "StorageType", "keepPacked"):
        if key in block_entity:
            stable[key] = ota.plain(block_entity[key])
    absent: list[str] = []
    structural_keys: tuple[str, ...]
    if structural == "vault":
        structural_keys = ("Controller", "Size", "Length")
    elif structural == "fluid_tank":
        structural_keys = ("Controller", "Size", "Height")
    else:
        structural_keys = ()
    for key in structural_keys:
        if key not in block_entity:
            absent.append(key)
    return stable, absent


def expected_state(block_state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "Name": str(block_state["Name"]),
        "Properties": {str(key): str(value) for key, value in block_state.get("Properties", {}).items()},
        "property_match": "exact",
    }


def base_draft(package_id: str, world: Path, server_root: Path, sources: Mapping[str, Path]) -> dict[str, Any]:
    return {
        "package_id": package_id,
        "created_utc": ota.utc_now(),
        "mode": "object_level_compare_and_set",
        "chunk_overwrite": False,
        "world_identity": ota.parse_level_dat(world / "level.dat"),
        "server_root": str(server_root.resolve()),
        "source_evidence": {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in sources.items()
        },
        "groups": [],
    }


def vault_draft(
    ledger_path: Path,
    ledger: Mapping[str, Any],
    world: Path,
    server_root: Path,
) -> dict[str, Any]:
    if ledger.get("schema") != 3 or ledger.get("chunk_overwrite") is not False:
        raise ota.OtaError("vault ledger must be signed schema 3 with chunk_overwrite=false")
    if ledger.get("blockers") or ledger.get("typed_payload_errors"):
        raise ota.OtaError("vault ledger contains blockers or typed payload errors")
    payloads: dict[str, str] = {}
    payload_rows = (
        list(ledger.get("safe_restore_ledger", []))
        + list(ledger.get("legacy_schema_pending", []))
        + list(ledger.get("live_nonempty_conflicts", []))
    )
    for row in payload_rows:
        key = row.get("key")
        payload = row.get("target_inventory_payload", {})
        encoded = payload.get("base64")
        declared = payload.get("sha256")
        if not isinstance(key, str) or not isinstance(encoded, str) or not isinstance(declared, str):
            raise ota.OtaError("vault source-nonempty entry has no typed payload")
        raw = base64.b64decode(encoded, validate=True)
        if hashlib.sha256(raw).hexdigest() != declared:
            raise ota.OtaError(f"vault payload hash mismatch: {key}")
        payloads[key] = encoded
    expected_payloads = int(ledger.get("summary", {}).get("source_nonempty_members", -1))
    if len(payloads) != expected_payloads:
        raise ota.OtaError(
            f"vault typed payload coverage mismatch: {len(payloads)} != {expected_payloads}"
        )

    draft = base_draft(
        "mechanomania-attempt13-vault-cas-20260815",
        world,
        server_root,
        {"vault_ledger": ledger_path},
    )
    draft["server_config_requirements"] = {"logistics.vaultCapacity": 20}
    for group in ledger.get("group_actions", []):
        members: list[dict[str, Any]] = []
        for row in group.get("members", []):
            dimension = group["dimension"]
            pos = list(row["pos"])
            region_path = PurePosixPath(row["region_path"])
            block_entity, block_state, chunk = load_live_member(world, dimension, pos, region_path)
            if ota.plain(block_entity.get("id")) != "create:item_vault":
                raise ota.OtaError(f"live vault identity mismatch: {dimension}:{pos}")
            stable, absent = stable_identity(block_entity, "vault")
            member: dict[str, Any] = {
                "dimension": dimension,
                "pos": pos,
                "block_entity_id": "create:item_vault",
                "region_path": region_path.as_posix(),
                "chunk": chunk,
                "stable_fields": stable,
                "stable_absent": absent,
                "expected_block_state": expected_state(block_state),
                "content_path": "Inventory",
                "content_schema": "neoforge_item_stack_handler",
                "legacy_schema": "create_fly_dense_item_list",
            }
            key = f"{dimension}|{pos[0]},{pos[1]},{pos[2]}"
            if key in payloads:
                member["payload_nbt_base64"] = payloads[key]
                current = ota.dotted_get(block_entity, "Inventory")
                legacy, error = ota.legacy_dense_item_handler(current)
                if error is not None:
                    raise ota.OtaError(f"invalid live legacy vault content at {key}: {error}")
                if legacy is not None:
                    state, _ = ota.content_state("neoforge_item_stack_handler", legacy)
                    if state == "nonempty":
                        member["expected_legacy_converted_sha256"] = ota.content_hash(legacy)
            members.append(member)
        if not any("payload_nbt_base64" in member for member in members):
            raise ota.OtaError(f"vault group has no source content: {group.get('group_key')}")
        draft["groups"].append({
            "group_id": "vault-" + str(group["group_key"]).replace(":", "_").replace("|", "_").replace(",", "_"),
            "storage_kind": "create:item_vault",
            "source_nonempty": True,
            "source_summary": {
                "member_count": group.get("member_count"),
                "safe_restore_coords": group.get("safe_restore_coords", []),
                "legacy_schema_coords": group.get("legacy_schema_coords", []),
                "conflict_coords": group.get("conflict_coords", []),
            },
            "members": members,
        })
    if not draft["groups"]:
        raise ota.OtaError("vault draft contains no groups")
    return draft


def fluid_payload(candidate: Mapping[str, Any]) -> bytes:
    source = candidate.get("source", {})
    identifier = source.get("target_id")
    amount = source.get("target_amount")
    if not isinstance(identifier, str) or ":" not in identifier:
        raise ota.OtaError(f"invalid fluid id at {candidate.get('pos')}: {identifier!r}")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        raise ota.OtaError(f"invalid fluid amount at {candidate.get('pos')}: {amount!r}")
    tank = nbtlib.Compound({
        "Fluid": nbtlib.Compound({"id": nbtlib.String(identifier), "amount": nbtlib.Int(amount)})
    })
    return ota.serialize_payload_tag(tank)


def fluid_content_path(candidate: Mapping[str, Any]) -> str:
    target = candidate.get("target_path")
    if not isinstance(target, str) or not target.endswith(".Fluid"):
        raise ota.OtaError(f"invalid fluid target path: {target!r}")
    return target[:-6]


def fluid_member(
    world: Path,
    candidate: Mapping[str, Any],
    *,
    include_payload: bool,
    structural: str = "singleton",
) -> dict[str, Any]:
    dimension = str(candidate["dimension"])
    pos = list(candidate["pos"])
    location = candidate.get("locations", {}).get("runtime", {})
    absolute_region = Path(str(location.get("region", "")))
    if not absolute_region.name:
        raise ota.OtaError(f"fluid candidate has no runtime region: {dimension}:{pos}")
    chunk_info = {
        "region_file": absolute_region.name,
    }
    region_path = region_path_for(dimension, chunk_info)
    block_entity, block_state, chunk = load_live_member(world, dimension, pos, region_path)
    owner = str(candidate["owner_id"])
    if ota.plain(block_entity.get("id")) != owner:
        raise ota.OtaError(f"live fluid owner mismatch at {dimension}:{pos}")
    stable, absent = stable_identity(block_entity, structural)
    content_path = fluid_content_path(candidate)
    legacy_schema = "create_fly_root_or_direct_fluid" if owner in {"create:fluid_tank", "create:hose_pulley"} else None
    member: dict[str, Any] = {
        "dimension": dimension,
        "pos": pos,
        "block_entity_id": owner,
        "region_path": region_path.as_posix(),
        "chunk": chunk,
        "stable_fields": stable,
        "stable_absent": absent,
        "expected_block_state": expected_state(block_state),
        "content_path": content_path,
        "content_schema": "neoforge_fluid_tank",
        "legacy_schema": legacy_schema,
        "target_max_capacity": int(candidate["source"]["target_max_capacity"]),
    }
    if include_payload:
        member["payload_nbt_base64"] = base64.b64encode(fluid_payload(candidate)).decode("ascii")
    if legacy_schema is not None:
        converted, _, error = ota.legacy_fluid_tank(block_entity, content_path)
        if error is not None:
            raise ota.OtaError(f"invalid live legacy fluid content at {dimension}:{pos}: {error}")
        if converted is not None:
            state, _ = ota.content_state("neoforge_fluid_tank", converted)
            if state == "nonempty":
                member["expected_legacy_converted_sha256"] = ota.content_hash(converted)
    return member


def noop_topology_member(
    world: Path,
    dimension: str,
    pos: list[int],
    region_path: PurePosixPath,
    owner: str,
    structural: str,
) -> dict[str, Any]:
    block_entity, block_state, chunk = load_live_member(world, dimension, pos, region_path)
    if ota.plain(block_entity.get("id")) != owner:
        raise ota.OtaError(f"topology member owner mismatch at {dimension}:{pos}")
    stable, absent = stable_identity(block_entity, structural)
    absent = sorted(set(absent + ["__ota_no_content__"]))
    return {
        "dimension": dimension,
        "pos": pos,
        "block_entity_id": owner,
        "region_path": region_path.as_posix(),
        "chunk": chunk,
        "stable_fields": stable,
        "stable_absent": absent,
        "expected_block_state": expected_state(block_state),
        "content_path": "__ota_no_content__",
        "content_schema": "empty_compound",
        "legacy_schema": None,
    }


def fluid_drafts(
    report_path: Path,
    report: Mapping[str, Any],
    world: Path,
    server_root: Path,
) -> list[dict[str, Any]]:
    if report.get("schema") != 1 or report.get("read_only") is not True:
        raise ota.OtaError("fluid forensic report must be read-only schema 1")
    if report.get("conflicts") or report.get("capacity_violations"):
        raise ota.OtaError("fluid forensic report contains conflicts or capacity violations")
    candidates = list(report.get("force_restore_candidates", []))
    by_key: dict[tuple[str, tuple[int, int, int]], list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        key = (str(candidate["dimension"]), tuple(candidate["pos"]))
        by_key[key].append(candidate)
    for rows in by_key.values():
        rows.sort(key=lambda row: str(row["target_path"]))
    max_passes = max(len(rows) for rows in by_key.values())
    if max_passes > 2:
        raise ota.OtaError(f"fluid evidence needs {max_passes} passes; expected at most 2")

    tank_groups = {
        (str(group["dimension"]), tuple(group["controller"])): group
        for group in report.get("multiblock_groups", [])
    }
    drafts: list[dict[str, Any]] = []
    for pass_index in range(max_passes):
        draft = base_draft(
            f"mechanomania-attempt13-fluid-cas-p{pass_index + 1}-20260815",
            world,
            server_root,
            {"fluid_forensic_report": report_path},
        )
        draft["server_config_requirements"] = {"fluids.fluidTankCapacity": 8}
        consumed: set[tuple[str, tuple[int, int, int]]] = set()

        if pass_index == 0:
            for group_key, group in sorted(tank_groups.items()):
                rows = by_key.get(group_key, [])
                if not rows:
                    raise ota.OtaError(f"fluid tank controller has no payload candidate: {group_key}")
                candidate = rows[0]
                controller = list(group["controller"])
                members: list[dict[str, Any]] = []
                for topology in group.get("members", []):
                    pos = list(topology["pos"])
                    chunk = topology["chunk"]
                    region_path = region_path_for(str(group["dimension"]), chunk)
                    if pos == controller:
                        members.append(fluid_member(world, candidate, include_payload=True, structural="fluid_tank"))
                    else:
                        members.append(noop_topology_member(
                            world,
                            str(group["dimension"]),
                            pos,
                            region_path,
                            "create:fluid_tank",
                            "fluid_tank",
                        ))
                draft["groups"].append({
                    "group_id": "fluid-tank-" + str(group_key[0]).replace(":", "_") + "-" + "_".join(map(str, controller)),
                    "storage_kind": "create:fluid_tank",
                    "source_nonempty": True,
                    "source_summary": {
                        "controller": controller,
                        "member_count": group.get("member_count"),
                        "source_size": group.get("source_size"),
                        "source_height": group.get("source_height"),
                    },
                    "members": members,
                })
                consumed.add(group_key)

        for key, rows in sorted(by_key.items()):
            if pass_index >= len(rows) or (pass_index == 0 and key in consumed):
                continue
            candidate = rows[pass_index]
            member = fluid_member(world, candidate, include_payload=True)
            draft["groups"].append({
                "group_id": "fluid-" + key[0].replace(":", "_") + "-" + "_".join(map(str, key[1])) + f"-p{pass_index + 1}",
                "storage_kind": str(candidate["owner_id"]),
                "source_nonempty": True,
                "source_summary": {
                    "source_path": candidate.get("source_path"),
                    "target_path": candidate.get("target_path"),
                    "runtime_was_nonempty": candidate.get("runtime_was_nonempty"),
                },
                "members": [member],
            })
        if draft["groups"]:
            drafts.append(draft)
    return drafts


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault-ledger", type=Path, required=True)
    parser.add_argument("--fluid-report", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--server-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    world = args.world.resolve()
    server_root = args.server_root.resolve()
    if world.parent != server_root:
        raise ota.OtaError(f"world must be directly inside server root: {world} vs {server_root}")
    vault = vault_draft(args.vault_ledger, load_json(args.vault_ledger), world, server_root)
    fluids = fluid_drafts(args.fluid_report, load_json(args.fluid_report), world, server_root)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / "vault-draft.json", vault)
    for index, draft in enumerate(fluids, 1):
        write_json(args.output_dir / f"fluid-pass{index}-draft.json", draft)
    summary = {
        "status": "DRAFTS_BUILT",
        "world": str(world),
        "vault_groups": len(vault["groups"]),
        "vault_members": sum(len(group["members"]) for group in vault["groups"]),
        "fluid_passes": [
            {
                "pass": index,
                "groups": len(draft["groups"]),
                "members": sum(len(group["members"]) for group in draft["groups"]),
            }
            for index, draft in enumerate(fluids, 1)
        ],
        "chunk_overwrite": False,
    }
    write_json(args.output_dir / "build-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ota.OtaError as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
