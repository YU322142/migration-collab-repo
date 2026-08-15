from __future__ import annotations

import argparse
import socket
import struct
import sys
from pathlib import Path


def receive_exact(connection: socket.socket, length: int) -> bytes:
    chunks = []
    while length:
        chunk = connection.recv(length)
        if not chunk:
            raise ConnectionError("RCON connection closed")
        chunks.append(chunk)
        length -= len(chunk)
    return b"".join(chunks)


def packet(connection: socket.socket, request_id: int, packet_type: int, body: str):
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\0\0"
    connection.sendall(struct.pack("<i", len(payload)) + payload)
    length = struct.unpack("<i", receive_exact(connection, 4))[0]
    value = receive_exact(connection, length)
    return struct.unpack("<ii", value[:8])[0], value[8:-2].decode("utf-8", errors="replace")


def select_entity(region: Path, slot: int, uuid: str | None):
    sys.path.insert(0, r"D:\Trans\migration-audit-work")
    from audit_villagers import read_region_chunks

    for current_slot, chunk in read_region_chunks(region):
        if current_slot != slot:
            continue
        candidates = [entity for entity in chunk.get("Entities", []) if str(entity.get("id")) == "minecraft:villager"]
        if uuid is None:
            if len(candidates) != 1:
                raise ValueError(f"expected one villager in slot {slot}, found {len(candidates)}")
            return candidates[0]
        for entity in candidates:
            raw = entity.get("UUID")
            if raw is not None and str(raw) == uuid:
                return entity
    raise ValueError(f"villager {uuid or '<first>'} not found in {region} slot {slot}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", type=Path, required=True)
    parser.add_argument("--slot", type=int, required=True)
    parser.add_argument("--uuid")
    parser.add_argument("--port", type=int, default=11522)
    parser.add_argument("--password", default="poi-migration-local-only")
    parser.add_argument("--selector", default="@e[type=minecraft:villager,name=chef_probe,limit=1]")
    parser.add_argument("--drop", action="append", default=[], help="source NBT root key to omit")
    parser.add_argument("--only", action="append", default=[], help="keep only these source NBT root keys")
    args = parser.parse_args()

    entity = select_entity(args.region, args.slot, args.uuid)
    if args.only:
        for key in list(entity.keys()):
            if key not in args.only:
                del entity[key]
    for key in args.drop:
        if key in entity:
            del entity[key]
    command = f"data merge entity {args.selector} {entity.snbt()}"
    with socket.create_connection(("127.0.0.1", args.port), timeout=20) as connection:
        connection.settimeout(20)
        auth_id, auth = packet(connection, 1, 3, args.password)
        if auth_id == -1:
            raise PermissionError(f"RCON authentication failed: {auth}")
        response_id, response = packet(connection, 2, 2, command)
        if response_id != 2:
            raise RuntimeError(f"unexpected response id {response_id}")
    print(f"command_bytes={len(command.encode('utf-8'))}")
    print(response)


if __name__ == "__main__":
    main()
