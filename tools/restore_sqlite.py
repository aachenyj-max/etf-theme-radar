"""Restore a verified SQLite backup. The target service must be stopped first."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_manifest(root: Path) -> list[dict[str, object]]:
    return [
        {"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": _sha256(path), "bytes": path.stat().st_size}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]


def restore_backup(
    backup: Path, target: Path, confirmation: str, *, knowledge_backup_dir: Path | None = None,
    knowledge_target_dir: Path | None = None,
) -> None:
    backup = backup.resolve()
    target = target.resolve()
    if confirmation != str(target):
        raise ValueError("--confirm-target must exactly match the resolved --target path")
    if not backup.is_file():
        raise FileNotFoundError(f"backup does not exist: {backup}")
    metadata_path = backup.with_suffix(".json")
    metadata: dict = {}
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_hash = metadata.get("sha256", "")
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
    if knowledge_backup_dir is not None or knowledge_target_dir is not None:
        if knowledge_backup_dir is None or knowledge_target_dir is None:
            raise ValueError("knowledge backup and target directories must be provided together")
        knowledge_backup_dir = knowledge_backup_dir.resolve()
        knowledge_target_dir = knowledge_target_dir.resolve()
        if not knowledge_backup_dir.is_dir():
            raise FileNotFoundError(f"knowledge backup directory does not exist: {knowledge_backup_dir}")
        expected = metadata.get("knowledge_files", [])
        actual = _directory_manifest(knowledge_backup_dir)
        if expected and actual != expected:
            raise RuntimeError("knowledge backup manifest does not match its metadata")
        if knowledge_target_dir.exists() and any(knowledge_target_dir.iterdir()):
            raise ValueError("knowledge restore target must be empty")
        temporary_knowledge = knowledge_target_dir.with_name(f".{knowledge_target_dir.name}.{uuid4().hex}.restore")
        shutil.copytree(knowledge_backup_dir, temporary_knowledge)
        if _directory_manifest(temporary_knowledge) != actual:
            shutil.rmtree(temporary_knowledge)
            raise RuntimeError("restored knowledge file hashes do not match backup")
        if knowledge_target_dir.exists():
            knowledge_target_dir.rmdir()
        os.replace(temporary_knowledge, knowledge_target_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--confirm-target", required=True)
    parser.add_argument("--knowledge-backup-dir", type=Path)
    parser.add_argument("--knowledge-target-dir", type=Path)
    args = parser.parse_args()
    restore_backup(
        args.backup, args.target, args.confirm_target,
        knowledge_backup_dir=args.knowledge_backup_dir, knowledge_target_dir=args.knowledge_target_dir,
    )


if __name__ == "__main__":
    main()
