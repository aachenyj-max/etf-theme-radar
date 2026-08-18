"""One permission boundary for knowledge-listing, reads and retrieval."""
from __future__ import annotations

import json

from .store import EvidenceStore


class KnowledgePermissions:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    @staticmethod
    def _visibility_sql(alias: str = "i") -> str:
        return f"""(
            {alias}.owner_user_id=?
            OR EXISTS (
                SELECT 1 FROM knowledge_shares direct_share
                WHERE direct_share.knowledge_item_id={alias}.knowledge_item_id
                  AND direct_share.status='active'
                  AND direct_share.subject_type='user' AND direct_share.subject_id=?
            )
            OR EXISTS (
                SELECT 1 FROM knowledge_shares team_share
                JOIN knowledge_team_memberships membership
                  ON membership.team_id=team_share.subject_id
                WHERE team_share.knowledge_item_id={alias}.knowledge_item_id
                  AND team_share.status='active' AND team_share.subject_type='team'
                  AND membership.user_id=? AND membership.enabled=1
            )
        )"""

    @staticmethod
    def _visibility_arguments(user_id: str) -> tuple[str, str, str]:
        return (user_id, user_id, user_id)

    @staticmethod
    def _operation_from_row(row: tuple) -> dict:
        keys = (
            "operation_id", "owner_user_id", "operation_type", "target_kind", "target_id",
            "target_version", "idempotency_key", "preview", "confirmation_token", "status",
            "created_at", "expires_at", "confirmed_at",
        )
        result = dict(zip(keys, row))
        result["preview"] = json.loads(result["preview"])
        return result

    def _owned_item(self, item_id: str, owner_user_id: str) -> tuple:
        row = self.store.conn.execute(
            """SELECT knowledge_item_id,current_version,status FROM knowledge_items
            WHERE knowledge_item_id=? AND owner_user_id=?""",
            (item_id, owner_user_id),
        ).fetchone()
        if row is None:
            raise KeyError(item_id)
        return row

    def can_read(self, item_id: str, user_id: str) -> bool:
        row = self.store.conn.execute(
            f"""SELECT 1 FROM knowledge_items i WHERE i.knowledge_item_id=? AND i.status='active'
            AND {self._visibility_sql()}""",
            (item_id, *self._visibility_arguments(user_id)),
        ).fetchone()
        return row is not None

    def item_for_user(self, item_id: str, user_id: str) -> dict | None:
        row = self.store.conn.execute(
            f"""SELECT i.knowledge_item_id,i.kind,i.title,i.theme_id,i.current_version,
            i.updated_at,v.mime_type,v.original_filename
            FROM knowledge_items i JOIN knowledge_item_versions v
              ON v.knowledge_item_id=i.knowledge_item_id AND v.version=i.current_version
            WHERE i.knowledge_item_id=? AND i.status='active' AND {self._visibility_sql()}""",
            (item_id, *self._visibility_arguments(user_id)),
        ).fetchone()
        if row is None:
            return None
        keys = (
            "knowledge_item_id", "kind", "title", "theme_id", "current_version",
            "updated_at", "mime_type", "original_filename",
        )
        return dict(zip(keys, row))

    def visible_items(self, user_id: str) -> list[dict]:
        rows = self.store.conn.execute(
            f"""SELECT i.knowledge_item_id,i.kind,i.title,i.theme_id,i.current_version,
            i.updated_at,v.mime_type,v.original_filename
            FROM knowledge_items i JOIN knowledge_item_versions v
              ON v.knowledge_item_id=i.knowledge_item_id AND v.version=i.current_version
            WHERE i.status='active' AND {self._visibility_sql()}
            ORDER BY i.updated_at DESC,i.knowledge_item_id""",
            self._visibility_arguments(user_id),
        ).fetchall()
        keys = (
            "knowledge_item_id", "kind", "title", "theme_id", "current_version",
            "updated_at", "mime_type", "original_filename",
        )
        return [dict(zip(keys, row)) for row in rows]

    def authorized_chunks(self, user_id: str) -> list[dict]:
        rows = self.store.conn.execute(
            f"""SELECT i.knowledge_item_id,i.title,i.theme_id,i.kind,i.updated_at,v.version,
            c.chunk_id,c.chunk_index,c.text,c.page_number,c.char_start,c.char_end,c.source_type
            FROM knowledge_items i
            JOIN knowledge_item_versions v
              ON v.knowledge_item_id=i.knowledge_item_id AND v.version=i.current_version
            JOIN document_chunks c ON c.knowledge_item_id=v.knowledge_item_id AND c.version=v.version
            WHERE i.status='active' AND {self._visibility_sql()}
            ORDER BY i.updated_at DESC,i.knowledge_item_id,c.chunk_index""",
            self._visibility_arguments(user_id),
        ).fetchall()
        keys = (
            "knowledge_item_id", "title", "theme_id", "kind", "updated_at", "version",
            "chunk_id", "chunk_index", "text", "page_number", "char_start", "char_end", "source_type",
        )
        return [dict(zip(keys, row)) for row in rows]

    def set_team_membership(self, team_id: str, user_id: str, *, enabled: bool, updated_at: str) -> None:
        self.store.conn.execute(
            """INSERT INTO knowledge_team_memberships (team_id,user_id,enabled,updated_at)
            VALUES (?,?,?,?) ON CONFLICT(team_id,user_id) DO UPDATE SET
            enabled=excluded.enabled,updated_at=excluded.updated_at""",
            (team_id, user_id, int(enabled), updated_at),
        )
        self.store.conn.commit()

    def preview_operation(
        self, *, operation_id: str, owner_user_id: str, operation_type: str, item_id: str,
        payload: dict, idempotency_key: str, confirmation_token: str, created_at: str,
        expires_at: str,
    ) -> dict:
        item_id, version, _status = self._owned_item(item_id, owner_user_id)
        existing = self.store.conn.execute(
            """SELECT operation_id,owner_user_id,operation_type,target_kind,target_id,target_version,
            idempotency_key,preview_json,confirmation_token,status,created_at,expires_at,confirmed_at
            FROM pending_operations WHERE idempotency_key=?""",
            (idempotency_key,),
        ).fetchone()
        if existing is not None:
            return self._operation_from_row(existing)
        if operation_type not in {"share", "revoke_share", "move", "delete", "restore"}:
            raise ValueError("unsupported knowledge operation")
        if operation_type in {"share", "revoke_share"}:
            if payload.get("subject_type") not in {"user", "team"} or not str(payload.get("subject_id") or ""):
                raise ValueError("share operation requires a user or team subject")
        preview = {"operation_type": operation_type, "item_id": item_id, "target_version": version, "changes": dict(payload)}
        self.store.conn.execute(
            """INSERT INTO pending_operations
            (operation_id,owner_user_id,operation_type,target_kind,target_id,target_version,
             idempotency_key,preview_json,confirmation_token,status,created_at,expires_at,confirmed_at)
            VALUES (?,?,?,?,?,?,?,?,?,'pending_confirmation',?,?, '')""",
            (operation_id, owner_user_id, operation_type, "knowledge_item", item_id, version,
             idempotency_key, json.dumps(preview, ensure_ascii=False), confirmation_token,
             created_at, expires_at),
        )
        self.store.conn.commit()
        return {
            "operation_id": operation_id, "owner_user_id": owner_user_id,
            "operation_type": operation_type, "target_kind": "knowledge_item", "target_id": item_id,
            "target_version": version, "idempotency_key": idempotency_key, "preview": preview,
            "confirmation_token": confirmation_token, "status": "pending_confirmation",
            "created_at": created_at, "expires_at": expires_at, "confirmed_at": "",
        }

    def confirm_operation(
        self, operation_id: str, owner_user_id: str, confirmation_token: str, *, confirmed_at: str,
    ) -> dict:
        row = self.store.conn.execute(
            """SELECT operation_id,owner_user_id,operation_type,target_kind,target_id,target_version,
            idempotency_key,preview_json,confirmation_token,status,created_at,expires_at,confirmed_at
            FROM pending_operations WHERE operation_id=? AND owner_user_id=?""",
            (operation_id, owner_user_id),
        ).fetchone()
        if row is None:
            raise KeyError(operation_id)
        operation = self._operation_from_row(row)
        if operation["status"] != "pending_confirmation":
            raise ValueError("confirmation token is single-use")
        if operation["confirmation_token"] != confirmation_token:
            raise ValueError("confirmation token does not match")
        if operation["expires_at"] <= confirmed_at:
            raise ValueError("confirmation token has expired")
        item_id, current_version, _status = self._owned_item(operation["target_id"], owner_user_id)
        if int(current_version) != int(operation["target_version"]):
            raise ValueError("knowledge item version changed; preview again")
        changes = operation["preview"]["changes"]
        try:
            self.store.conn.execute("BEGIN IMMEDIATE")
            if operation["operation_type"] == "share":
                self.store.conn.execute(
                    """INSERT INTO knowledge_shares
                    (share_id,knowledge_item_id,subject_type,subject_id,created_by_user_id,status,created_at,revoked_at)
                    VALUES (?,?,?,?,?,'active',?,'') ON CONFLICT(knowledge_item_id,subject_type,subject_id)
                    DO UPDATE SET status='active',created_by_user_id=excluded.created_by_user_id,
                    created_at=excluded.created_at,revoked_at=''""",
                    (f"share:{item_id}:{changes['subject_type']}:{changes['subject_id']}", item_id,
                     changes["subject_type"], changes["subject_id"], owner_user_id, confirmed_at),
                )
            elif operation["operation_type"] == "revoke_share":
                self.store.conn.execute(
                    """UPDATE knowledge_shares SET status='revoked',revoked_at=?
                    WHERE knowledge_item_id=? AND subject_type=? AND subject_id=?
                      AND created_by_user_id=?""",
                    (confirmed_at, item_id, changes["subject_type"], changes["subject_id"], owner_user_id),
                )
            elif operation["operation_type"] == "delete":
                self.store.conn.execute(
                    "UPDATE knowledge_items SET status='deleted',deleted_at=?,updated_at=? WHERE knowledge_item_id=?",
                    (confirmed_at, confirmed_at, item_id),
                )
            elif operation["operation_type"] == "restore":
                self.store.conn.execute(
                    "UPDATE knowledge_items SET status='active',deleted_at=NULL,updated_at=? WHERE knowledge_item_id=?",
                    (confirmed_at, item_id),
                )
            elif operation["operation_type"] == "move":
                folder_id = str(changes.get("folder_id") or "")
                if not folder_id:
                    raise ValueError("move operation requires folder_id")
                folder = self.store.conn.execute(
                    """SELECT 1 FROM knowledge_folders
                    WHERE folder_id=? AND owner_user_id=? AND status='active'""",
                    (folder_id, owner_user_id),
                ).fetchone()
                if folder is None:
                    raise ValueError("move operation requires an owned active folder")
                self.store.conn.execute(
                    "UPDATE knowledge_folder_entries SET folder_id=? WHERE knowledge_item_id=?",
                    (folder_id, item_id),
                )
            self.store.conn.execute(
                "UPDATE pending_operations SET status='completed',confirmed_at=? WHERE operation_id=?",
                (confirmed_at, operation_id),
            )
            self.store.conn.commit()
        except Exception:
            self.store.conn.rollback()
            raise
        operation["status"] = "completed"
        operation["confirmed_at"] = confirmed_at
        return operation
