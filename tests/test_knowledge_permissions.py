from __future__ import annotations

import json
from pathlib import Path

import pytest

from etf_theme_radar.knowledge_base import KnowledgeBase
from etf_theme_radar.knowledge_permissions import KnowledgePermissions
from etf_theme_radar.store import EvidenceStore


NOW = "2026-08-18T00:00:00+00:00"


def _services(tmp_path: Path) -> tuple[EvidenceStore, KnowledgeBase, KnowledgePermissions]:
    store = EvidenceStore(tmp_path / "permissions.db")
    library = KnowledgeBase(store, files_root=tmp_path / "knowledge-files")
    return store, library, KnowledgePermissions(store)


def _create_private_item(library: KnowledgeBase, item_id: str, owner: str) -> None:
    library.create_item(
        item_id=item_id,
        owner_user_id=owner,
        kind="note",
        title=f"{owner} private {item_id}",
        content=f"{owner} private content".encode(),
        filename=f"{item_id}.txt",
        mime_type="text/plain",
        theme_id="robotics",
        folder_id=f"folder-{owner}",
        created_at=NOW,
    )


def test_private_by_default_and_member_share_requires_single_confirmation(tmp_path: Path) -> None:
    store, library, permissions = _services(tmp_path)
    try:
        _create_private_item(library, "item-a", "user-a")
        assert [item["knowledge_item_id"] for item in permissions.visible_items("user-a")] == ["item-a"]
        assert permissions.visible_items("user-b") == []

        preview = permissions.preview_operation(
            operation_id="operation-share", owner_user_id="user-a", operation_type="share",
            item_id="item-a", payload={"subject_type": "user", "subject_id": "user-b"},
            idempotency_key="share-item-a-user-b", confirmation_token="confirm-share",
            created_at=NOW, expires_at="2026-08-18T01:00:00+00:00",
        )
        assert preview["status"] == "pending_confirmation"
        assert permissions.visible_items("user-b") == []

        confirmed = permissions.confirm_operation(
            "operation-share", "user-a", "confirm-share", confirmed_at="2026-08-18T00:01:00+00:00",
        )
        assert confirmed["status"] == "completed"
        assert [item["knowledge_item_id"] for item in permissions.visible_items("user-b")] == ["item-a"]
        with pytest.raises(ValueError, match="single-use"):
            permissions.confirm_operation(
                "operation-share", "user-a", "confirm-share", confirmed_at="2026-08-18T00:02:00+00:00",
            )
    finally:
        store.close()


def test_team_share_and_revocation_take_effect_before_any_projection(tmp_path: Path) -> None:
    store, library, permissions = _services(tmp_path)
    try:
        _create_private_item(library, "item-team", "user-a")
        permissions.set_team_membership("team-research", "user-b", enabled=True, updated_at=NOW)
        permissions.preview_operation(
            operation_id="operation-team", owner_user_id="user-a", operation_type="share",
            item_id="item-team", payload={"subject_type": "team", "subject_id": "team-research"},
            idempotency_key="share-team", confirmation_token="confirm-team", created_at=NOW,
            expires_at="2026-08-18T01:00:00+00:00",
        )
        permissions.confirm_operation("operation-team", "user-a", "confirm-team", confirmed_at=NOW)
        assert permissions.can_read("item-team", "user-b") is True

        permissions.preview_operation(
            operation_id="operation-revoke", owner_user_id="user-a", operation_type="revoke_share",
            item_id="item-team", payload={"subject_type": "team", "subject_id": "team-research"},
            idempotency_key="revoke-team", confirmation_token="confirm-revoke", created_at=NOW,
            expires_at="2026-08-18T01:00:00+00:00",
        )
        permissions.confirm_operation("operation-revoke", "user-a", "confirm-revoke", confirmed_at="2026-08-18T00:01:00+00:00")

        assert permissions.can_read("item-team", "user-b") is False
        assert permissions.item_for_user("item-team", "user-b") is None
        assert "item-team" not in json.dumps(permissions.visible_items("user-b"))
    finally:
        store.close()


def test_move_rejects_a_folder_owned_by_another_user(tmp_path: Path) -> None:
    store, library, permissions = _services(tmp_path)
    try:
        _create_private_item(library, "item-move", "user-a")
        _create_private_item(library, "other-item", "user-b")
        permissions.preview_operation(
            operation_id="operation-move", owner_user_id="user-a", operation_type="move",
            item_id="item-move", payload={"folder_id": "folder-user-b"},
            idempotency_key="move-item-to-foreign-folder", confirmation_token="confirm-move",
            created_at=NOW, expires_at="2026-08-18T01:00:00+00:00",
        )

        with pytest.raises(ValueError, match="owned active folder"):
            permissions.confirm_operation("operation-move", "user-a", "confirm-move", confirmed_at=NOW)
    finally:
        store.close()
