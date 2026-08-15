import argparse
import socket
import struct


def receive_exact(connection: socket.socket, length: int) -> bytes:
    chunks = []
    remaining = length
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise ConnectionError("RCON connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_packet(connection: socket.socket, request_id: int, packet_type: int, body: str) -> None:
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\0\0"
    connection.sendall(struct.pack("<i", len(payload)) + payload)


def receive_packet(connection: socket.socket) -> tuple[int, int, str]:
    length = struct.unpack("<i", receive_exact(connection, 4))[0]
    payload = receive_exact(connection, length)
    request_id, packet_type = struct.unpack("<ii", payload[:8])
    return request_id, packet_type, payload[8:-2].decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="+")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=10740, type=int)
    parser.add_argument("--password", default="mishang-equivalence-local-only")
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=10) as connection:
        connection.settimeout(10)
        send_packet(connection, 1, 3, args.password)
        auth_id, _, auth_body = receive_packet(connection)
        if auth_id == -1:
            raise PermissionError("RCON authentication failed")
        if auth_body:
            print(auth_body)
        for index, command in enumerate(args.command, start=2):
            send_packet(connection, index, 2, command)
            response_id, _, response = receive_packet(connection)
            if response_id != index:
                raise RuntimeError(f"Unexpected RCON response id {response_id}, expected {index}")
            print(f"> {command}\n{response}")


if __name__ == "__main__":
    main()
