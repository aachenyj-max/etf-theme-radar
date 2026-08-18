from __future__ import annotations

import json
from pathlib import Path

from etf_theme_radar.knowledge_base import KnowledgeBase
from etf_theme_radar.knowledge_permissions import KnowledgePermissions
from etf_theme_radar.knowledge_retrieval import KnowledgeRetrieval
from etf_theme_radar.context_builder import build_research_context
from etf_theme_radar.store import EvidenceStore


NOW = "2026-08-18T00:00:00+00:00"


def test_retrieval_filters_permissions_before_ranking_and_budgeting(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "retrieval.db")
    library = KnowledgeBase(store, files_root=tmp_path / "knowledge-files")
    permissions = KnowledgePermissions(store)
    try:
        for item_id, owner, title, content in (
            ("shared-item", "user-a", "公开给成员的机器人材料", b"robotics hardware supplier meeting"),
            ("secret-item", "user-c", "绝不可见的标题", b"SECRET hardware acquisition plan"),
        ):
            library.create_item(
                item_id=item_id, owner_user_id=owner, kind="meeting_material", title=title,
                content=content, filename=f"{item_id}.txt", mime_type="text/plain",
                theme_id="robotics", folder_id=f"folder-{owner}", created_at=NOW,
            )
            store.conn.execute(
                """INSERT INTO document_chunks
                (chunk_id,knowledge_item_id,version,chunk_index,text,page_number,char_start,char_end,source_type,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (f"chunk-{item_id}", item_id, 1, 0, content.decode(), 1, 0, len(content), "meeting_material", NOW),
            )
            store.conn.commit()
        permissions.preview_operation(
            operation_id="share-retrieval", owner_user_id="user-a", operation_type="share",
            item_id="shared-item", payload={"subject_type": "user", "subject_id": "user-b"},
            idempotency_key="share-retrieval-user-b", confirmation_token="confirm-retrieval",
            created_at=NOW, expires_at="2026-08-18T01:00:00+00:00",
        )
        permissions.confirm_operation("share-retrieval", "user-a", "confirm-retrieval", confirmed_at=NOW)

        result = KnowledgeRetrieval(store).search(
            user_id="user-b", query="hardware", theme_id="robotics", token_budget=30,
        )

        assert [item["knowledge_item_id"] for item in result["items"]] == ["shared-item"]
        assert result["items"][0]["page_number"] == 1
        assert result["items"][0]["char_start"] == 0
        assert result["items"][0]["source_type"] == "meeting_material"
        assert result["items"][0]["internal_material"] is True
        assert result["estimated_tokens"] <= 30
        assert "绝不可见的标题" not in json.dumps(result, ensure_ascii=False)
        assert "SECRET" not in json.dumps(result, ensure_ascii=False)
    finally:
        store.close()


def test_retrieval_orders_equally_relevant_authorized_chunks_by_newest_first(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "newest.db")
    library = KnowledgeBase(store, files_root=tmp_path / "knowledge-files")
    permissions = KnowledgePermissions(store)
    try:
        for index, (item_id, created_at) in enumerate((
            ("older-item", "2026-08-18T00:00:00+00:00"),
            ("newer-item", "2026-08-18T00:01:00+00:00"),
        )):
            content = f"robotics hardware item {index}".encode()
            library.create_item(
                item_id=item_id, owner_user_id="user-a", kind="note", title=item_id,
                content=content, filename=f"{item_id}.txt", mime_type="text/plain",
                theme_id="robotics", folder_id="folder-a", created_at=created_at,
            )
            store.conn.execute(
                """INSERT INTO document_chunks
                (chunk_id,knowledge_item_id,version,chunk_index,text,page_number,char_start,char_end,source_type,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (f"chunk-{item_id}", item_id, 1, 0, content.decode(), None, 0, len(content), "note", created_at),
            )
            store.conn.commit()
            permissions.preview_operation(
                operation_id=f"share-{item_id}", owner_user_id="user-a", operation_type="share",
                item_id=item_id, payload={"subject_type": "user", "subject_id": "user-b"},
                idempotency_key=f"share-{item_id}-user-b", confirmation_token=f"confirm-{item_id}",
                created_at=created_at, expires_at="2026-08-19T00:00:00+00:00",
            )
            permissions.confirm_operation(f"share-{item_id}", "user-a", f"confirm-{item_id}", confirmed_at=created_at)

        result = KnowledgeRetrieval(store).search(
            user_id="user-b", query="hardware", theme_id="robotics", token_budget=100,
        )

        assert [item["knowledge_item_id"] for item in result["items"]] == ["newer-item", "older-item"]
    finally:
        store.close()


def test_authorized_parsed_knowledge_enters_context_after_frozen_etf_data(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "context.db")
    library = KnowledgeBase(store, files_root=tmp_path / "knowledge-files")
    permissions = KnowledgePermissions(store)
    try:
        library.create_item(
            item_id="context-item", owner_user_id="user-a", kind="etf_material",
            title="内部 ETF 材料", content=b"robotics hardware coverage", filename="etf.txt",
            mime_type="text/plain", theme_id="robotics", folder_id="folder-a", created_at=NOW,
        )
        library.parse_current_version("context-item", "user-a", chunk_size=100, overlap=0)
        permissions.preview_operation(
            operation_id="share-context", owner_user_id="user-a", operation_type="share",
            item_id="context-item", payload={"subject_type": "user", "subject_id": "user-b"},
            idempotency_key="share-context-user-b", confirmation_token="confirm-context",
            created_at=NOW, expires_at="2026-08-19T00:00:00+00:00",
        )
        permissions.confirm_operation("share-context", "user-a", "confirm-context", confirmed_at=NOW)

        knowledge = KnowledgeRetrieval(store).for_research_context(
            user_id="user-b", theme_id="robotics", query="hardware", token_budget=20,
        )
        context = build_research_context(
            user_id="user-b", conversation_id="conversation-b", token_budget=100,
            theme_definition={"id": "theme", "token_count": 1},
            evidence=[{"id": "evidence", "token_count": 1}],
            etf_snapshots=[{"id": "etf", "token_count": 1}], knowledge=knowledge,
        )

        assert [layer["kind"] for layer in context["layers"]] == [
            "theme_definition", "evidence", "etf_snapshots", "knowledge",
        ]
        assert context["layers"][-1]["items"][0]["internal_material"] is True
        assert context["layers"][-1]["items"][0]["source_type"] == "etf_material"
    finally:
        store.close()
