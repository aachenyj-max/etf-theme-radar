"""Versioned files in a local, controlled personal knowledge directory."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .store import EvidenceStore


class KnowledgeBase:
    def __init__(self, store: EvidenceStore, *, files_root: str | Path) -> None:
        self.store = store
        self.files_root = Path(files_root).resolve()
        self.files_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_identifier(value: str, label: str) -> str:
        normalized = str(value).strip()
        if not normalized or normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
            raise ValueError(f"{label} is invalid")
        return normalized

    @staticmethod
    def _validate_filename(filename: str) -> str:
        normalized = str(filename).strip()
        if not normalized or normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
            raise ValueError("filename must be a basename")
        return normalized

    def _storage_path(self, item_id: str, version: int) -> str:
        return f"{item_id}/v{version:06d}.bin"

    def _absolute_storage_path(self, storage_path: str) -> Path:
        candidate = (self.files_root / storage_path).resolve()
        if candidate != self.files_root and self.files_root not in candidate.parents:
            raise ValueError("storage path escapes controlled directory")
        return candidate

    @staticmethod
    def _hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _write_version_file(self, storage_path: str, content: bytes) -> None:
        destination = self._absolute_storage_path(storage_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _row_to_item(self, row: tuple | None) -> dict | None:
        if row is None:
            return None
        keys = (
            "knowledge_item_id", "owner_user_id", "kind", "title", "theme_id", "status",
            "current_version", "created_at", "updated_at", "deleted_at", "content_hash",
            "original_filename", "mime_type", "storage_path", "content_size", "parse_status",
        )
        item = dict(zip(keys, row))
        storage_path = str(item["storage_path"])
        if item["status"] == "active" and not self._absolute_storage_path(storage_path).is_file():
            item["status"] = "missing_file"
        return item

    def item(self, item_id: str, owner_user_id: str) -> dict | None:
        row = self.store.conn.execute(
            """SELECT i.knowledge_item_id,i.owner_user_id,i.kind,i.title,i.theme_id,i.status,
            i.current_version,i.created_at,i.updated_at,COALESCE(i.deleted_at,''),v.content_hash,
            v.original_filename,v.mime_type,v.storage_path,v.content_size,v.parse_status
            FROM knowledge_items i JOIN knowledge_item_versions v
              ON v.knowledge_item_id=i.knowledge_item_id AND v.version=i.current_version
            WHERE i.knowledge_item_id=? AND i.owner_user_id=?""",
            (item_id, owner_user_id),
        ).fetchone()
        return self._row_to_item(row)

    def _require_item(self, item_id: str, owner_user_id: str) -> dict:
        item = self.item(item_id, owner_user_id)
        if item is None:
            raise KeyError(item_id)
        return item

    def _ensure_folder(self, folder_id: str, owner_user_id: str, created_at: str) -> None:
        folder_id = self._validate_identifier(folder_id, "folder_id")
        self.store.conn.execute(
            """INSERT INTO knowledge_folders
            (folder_id,owner_user_id,name,status,created_at,updated_at,deleted_at)
            VALUES (?,?,?,?,?,?,NULL) ON CONFLICT(folder_id) DO NOTHING""",
            (folder_id, owner_user_id, folder_id, "active", created_at, created_at),
        )

    def create_item(
        self, *, item_id: str, owner_user_id: str, kind: str, title: str, content: bytes,
        filename: str, mime_type: str, theme_id: str, folder_id: str, created_at: str,
    ) -> dict:
        item_id = self._validate_identifier(item_id, "item_id")
        filename = self._validate_filename(filename)
        if not isinstance(content, bytes):
            raise ValueError("content must be bytes")
        storage_path = self._storage_path(item_id, 1)
        self._write_version_file(storage_path, content)
        try:
            self.store.conn.execute("BEGIN IMMEDIATE")
            self._ensure_folder(folder_id, owner_user_id, created_at)
            self.store.conn.execute(
                """INSERT INTO knowledge_items
                (knowledge_item_id,owner_user_id,kind,title,theme_id,status,current_version,
                 created_at,updated_at,deleted_at) VALUES (?,?,?,?,?,'active',1,?,?,NULL)""",
                (item_id, owner_user_id, str(kind), str(title), str(theme_id), created_at, created_at),
            )
            self.store.conn.execute(
                """INSERT INTO knowledge_item_versions
                (knowledge_item_id,version,content_hash,original_filename,mime_type,storage_path,
                 content_size,parse_status,created_at) VALUES (?,?,?,?,?,?,?,? ,?)""",
                (item_id, 1, self._hash(content), filename, str(mime_type), storage_path,
                 len(content), "pending", created_at),
            )
            self.store.conn.execute(
                "INSERT INTO knowledge_folder_entries (folder_id,knowledge_item_id,added_at) VALUES (?,?,?)",
                (folder_id, item_id, created_at),
            )
            self.store.conn.commit()
        except Exception:
            self.store.conn.rollback()
            self._absolute_storage_path(storage_path).unlink(missing_ok=True)
            raise
        item = self.item(item_id, owner_user_id)
        assert item is not None
        return item

    def replace_content(
        self, *, item_id: str, owner_user_id: str, content: bytes, filename: str,
        mime_type: str, created_at: str,
    ) -> dict:
        current = self._require_item(item_id, owner_user_id)
        if current["status"] != "active":
            raise ValueError("only active items can receive a new version")
        filename = self._validate_filename(filename)
        if not isinstance(content, bytes):
            raise ValueError("content must be bytes")
        version = int(current["current_version"]) + 1
        storage_path = self._storage_path(item_id, version)
        self._write_version_file(storage_path, content)
        try:
            self.store.conn.execute("BEGIN IMMEDIATE")
            self.store.conn.execute(
                """INSERT INTO knowledge_item_versions
                (knowledge_item_id,version,content_hash,original_filename,mime_type,storage_path,
                 content_size,parse_status,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                (item_id, version, self._hash(content), filename, str(mime_type), storage_path,
                 len(content), "pending", created_at),
            )
            self.store.conn.execute(
                """UPDATE knowledge_items SET current_version=?,updated_at=?
                WHERE knowledge_item_id=? AND owner_user_id=?""",
                (version, created_at, item_id, owner_user_id),
            )
            self.store.conn.commit()
        except Exception:
            self.store.conn.rollback()
            self._absolute_storage_path(storage_path).unlink(missing_ok=True)
            raise
        item = self.item(item_id, owner_user_id)
        assert item is not None
        return item

    def versions(self, item_id: str, owner_user_id: str) -> list[dict]:
        self._require_item(item_id, owner_user_id)
        rows = self.store.conn.execute(
            """SELECT version,content_hash,original_filename,mime_type,storage_path,content_size,
            parse_status,created_at FROM knowledge_item_versions
            WHERE knowledge_item_id=? ORDER BY version""",
            (item_id,),
        ).fetchall()
        keys = ("version", "content_hash", "original_filename", "mime_type", "storage_path", "content_size", "parse_status", "created_at")
        return [dict(zip(keys, row)) for row in rows]

    def soft_delete(self, item_id: str, owner_user_id: str, *, deleted_at: str) -> dict:
        self._require_item(item_id, owner_user_id)
        self.store.conn.execute(
            """UPDATE knowledge_items SET status='deleted',deleted_at=?,updated_at=?
            WHERE knowledge_item_id=? AND owner_user_id=?""",
            (deleted_at, deleted_at, item_id, owner_user_id),
        )
        self.store.conn.commit()
        item = self.item(item_id, owner_user_id)
        assert item is not None
        return item

    def restore(self, item_id: str, owner_user_id: str, *, restored_at: str) -> dict:
        self._require_item(item_id, owner_user_id)
        self.store.conn.execute(
            """UPDATE knowledge_items SET status='active',deleted_at=NULL,updated_at=?
            WHERE knowledge_item_id=? AND owner_user_id=?""",
            (restored_at, item_id, owner_user_id),
        )
        self.store.conn.commit()
        item = self.item(item_id, owner_user_id)
        assert item is not None
        return item

    def read_content(self, item_id: str, owner_user_id: str) -> bytes | None:
        item = self._require_item(item_id, owner_user_id)
        if item["status"] != "active":
            return None
        path = self._absolute_storage_path(str(item["storage_path"]))
        if not path.is_file():
            return None
        content = path.read_bytes()
        return content if self._hash(content) == item["content_hash"] else None
