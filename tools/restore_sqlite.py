"""Restore a verified SQLite backup. The target service must be stopped first."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def restore_backup(backup: Path, target: Path, confirmation: str) -> None:
    backup = backup.resolve()
    target = target.resolve()
    if confirmation != str(target):
        raise ValueError("--confirm-target must exactly match the resolved --target path")
    if not backup.is_file():
        raise FileNotFoundError(f"backup does not exist: {backup}")
    metadata_path = backup.with_suffix(".json")
    if metadata_path.is_file():
        expected_hash = json.loads(metadata_path.read_text(encoding="utf-8")).get("sha256", "")
        if expected_hash and expected_hash != _sha256(backup):
            raise RuntimeError("backup checksum does not match its metadata")

    check = sqlite3.connect(f"{backup.as_uri()}?mode=ro", uri=True)
    try:
        if check.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("backup integrity check failed")
    finally:
        check.close()

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{uuid4().hex}.restore"
    source_connection = sqlite3.connect(f"{backup.as_uri()}?mode=ro", uri=True)
    target_connection = sqlite3.connect(temporary)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    os.replace(temporary, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--confirm-target", required=True)
    args = parser.parse_args()
    restore_backup(args.backup, args.target, args.confirm_target)


if __name__ == "__main__":
    main()
