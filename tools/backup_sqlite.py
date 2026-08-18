"""Create a consistent SQLite backup without stopping the API service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
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


def create_backup(source: Path, destination_dir: Path, *, knowledge_dir: Path | None = None) -> Path:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite source does not exist: {source}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = destination_dir / f"radar-{stamp}.db"
    temporary = destination_dir / f".{destination.name}.{uuid4().hex}.tmp"

    source_connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(temporary)
    try:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise RuntimeError(f"backup integrity check failed: {result}")
    finally:
        destination_connection.close()
        source_connection.close()

    os.replace(temporary, destination)
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_name": source.name,
        "database": destination.name,
        "sha256": _sha256(destination),
        "bytes": destination.stat().st_size,
    }
    if knowledge_dir is not None:
        knowledge_dir = knowledge_dir.resolve()
        if not knowledge_dir.is_dir():
            raise FileNotFoundError(f"knowledge directory does not exist: {knowledge_dir}")
        knowledge_destination = destination.with_suffix(".knowledge")
        temporary_knowledge = knowledge_destination.with_name(f".{knowledge_destination.name}.{uuid4().hex}.tmp")
        shutil.copytree(knowledge_dir, temporary_knowledge)
        if knowledge_destination.exists():
            shutil.rmtree(knowledge_destination)
        os.replace(temporary_knowledge, knowledge_destination)
        metadata["knowledge_snapshot"] = knowledge_destination.name
        metadata["knowledge_files"] = _directory_manifest(knowledge_destination)
    destination.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination-dir", required=True, type=Path)
    parser.add_argument("--knowledge-dir", type=Path)
    args = parser.parse_args()
    print(create_backup(args.source, args.destination_dir, knowledge_dir=args.knowledge_dir))


if __name__ == "__main__":
    main()
