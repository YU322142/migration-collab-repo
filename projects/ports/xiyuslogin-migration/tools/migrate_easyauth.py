#!/usr/bin/env python3
"""Convert EasyAuth SQLite records to XiyusLogin JSON without plaintext."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path


def normalize_time(value: str | None) -> str | None:
    if not value:
        return None
    base = value.split("[", 1)[0]
    try:
        parsed = datetime.fromisoformat(base.replace("Z", "+00:00"))
    except ValueError:
        return value
    result = parsed.replace(tzinfo=None).isoformat(timespec="microseconds")
    return None if result == "1970-01-01T00:00:00.000000" else result


def hash_scheme(password: str) -> str:
    if not password:
        return "empty"
    if password.startswith(("$2a$", "$2b$", "$2y$")) and len(password) == 60:
        return "bcrypt"
    raise ValueError("unsupported or malformed EasyAuth password hash")


def convert(db_path: Path) -> tuple[dict[str, dict], dict[str, object]]:
    uri = "file:" + str(db_path.resolve()).replace("\\", "/") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        columns = {row[1] for row in connection.execute("pragma table_info(easyauth)")}
        required = {"username", "username_lower", "uuid", "data"}
        if not required.issubset(columns):
            raise ValueError(f"easyauth table is missing {sorted(required - columns)}")

        records: dict[str, dict] = {}
        source_hashes = {"bcrypt": 0, "empty": 0}
        uuid_present = 0
        rows = connection.execute(
            "select username, username_lower, uuid, data from easyauth order by id"
        ).fetchall()
        for username, username_lower, db_uuid, raw_data in rows:
            key = str(username_lower).lower()
            if key in records:
                raise ValueError(f"duplicate case-insensitive username: {key}")
            data = json.loads(raw_data)
            password = str(data.get("password", ""))
            scheme = hash_scheme(password)
            source_hashes[scheme] += 1

            parsed_uuid = None
            if db_uuid:
                parsed_uuid = str(uuid.UUID(str(db_uuid)))
                uuid_present += 1
            last_auth = normalize_time(data.get("last_authenticated_date"))
            records[key] = {
                "username": username,
                "uuid": parsed_uuid,
                "passwordHash": password,
                "registrationTime": normalize_time(data.get("registration_date")),
                "lastLoginTime": last_auth,
                "loginCount": 0,
                "lastIp": data.get("last_ip", ""),
                "lastAuthenticatedTime": last_auth,
                "loginTries": int(data.get("login_tries", 0)),
                "lastKickedTime": normalize_time(data.get("last_kicked_date")),
                "onlineAccount": data.get("online_account", "UNKNOWN"),
                "sourceDataVersion": int(data.get("data_version", 1)),
                # AuthManager additionally requires an authenticated server
                # profile and exact UUID before honoring this flag.
                "legacyPremiumAutoLogin": not password and parsed_uuid is not None,
                "passwordScheme": scheme,
            }
    finally:
        connection.close()

    manifest = {
        "source": str(db_path),
        "sourceSha256": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "records": len(records),
        "hashes": source_hashes,
        "uuidPresent": uuid_present,
        "plaintextStored": False,
        "notes": [
            "BCrypt hashes remain usable for first-login verification.",
            "Empty-password records are never authenticated on offline-mode servers.",
            "The original EasyAuth SQLite database is read-only and unchanged.",
        ],
    }
    return records, manifest


def atomic_json(path: Path, value: object, force: bool) -> str:
    if path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {path}; pass --force")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("db", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--expected-records",
        type=int,
        required=True,
        help="exact record count established from the read-only SQLite snapshot",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"database does not exist: {args.db}")
    if args.expected_records < 0:
        parser.error("--expected-records must be non-negative")

    records, manifest = convert(args.db)
    if len(records) != args.expected_records:
        raise ValueError(
            f"expected {args.expected_records} EasyAuth records, found {len(records)}"
        )
    manifest["expectedRecords"] = args.expected_records
    output_hash = atomic_json(args.output, records, args.force)
    manifest["output"] = str(args.output)
    manifest["outputSha256"] = output_hash
    if args.manifest:
        atomic_json(args.manifest, manifest, args.force)
    print(json.dumps({"records": len(records), "hashes": manifest["hashes"], "outputSha256": output_hash}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
