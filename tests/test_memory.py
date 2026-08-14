from __future__ import annotations

from pathlib import Path

from etf_theme_radar.conversations import ConversationService
from etf_theme_radar.memory import MemoryService
from etf_theme_radar.store import EvidenceStore


NOW = "2026-08-14T00:00:00+00:00"


def test_memory_lifecycle_preserves_sources_and_supersede_history(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "memory.db")
    conversations = ConversationService(store)
    conversations.create_conversation(
        conversation_id="conversation-a", user_id="user-a",
        selected_theme_id="robotics", created_at=NOW,
    )
    conversations.append_user_message(
        conversation_id="conversation-a", user_id="user-a", message_id="message-1",
        goal_id="goal-1", idempotency_key="turn-1", content="默认比较全球 ETF。",
        created_at=NOW,
    )
    memories = MemoryService(store)

    original = memories.create(
        memory_id="memory-1", user_id="user-a", conversation_id="conversation-a",
        category="preference", scope="personal", content="默认比较全球 ETF",
        confidence=0.9, source_message_ids=["message-1"], created_at=NOW,
    )
    pinned = memories.pin("memory-1", "user-a", pinned=True, updated_at=NOW)
    edited = memories.edit(
        "memory-1", "user-a", replacement_memory_id="memory-2",
        content="默认分别比较全球与国内 ETF", source_message_ids=["message-1"],
        created_at="2026-08-14T00:01:00+00:00",
    )
    corrected = memories.correct(
        "memory-2", "user-a", replacement_memory_id="memory-3",
        content="只在用户要求时比较全球 ETF", source_message_ids=["message-1"],
        created_at="2026-08-14T00:02:00+00:00",
    )
    disabled = memories.disable("memory-3", "user-a", updated_at=NOW)
    deleted = memories.delete("memory-3", "user-a", updated_at=NOW)

    assert original["source_message_ids"] == ["message-1"]
    assert pinned["pinned"] is True
    assert edited["version"] == 2
    assert corrected["version"] == 3
    assert disabled["status"] == "disabled"
    assert deleted["status"] == "deleted"
    assert store.memory_relations("user-a") == [
        {"from_memory_id": "memory-2", "to_memory_id": "memory-1", "relation_type": "supersedes", "created_at": "2026-08-14T00:01:00+00:00"},
        {"from_memory_id": "memory-3", "to_memory_id": "memory-2", "relation_type": "supersedes", "created_at": "2026-08-14T00:02:00+00:00"},
    ]
    assert store.conn.execute("SELECT COUNT(*) FROM report_versions").fetchone()[0] == 0
    store.close()


def test_memory_rejects_foreign_or_missing_source_messages(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "memory-acl.db")
    conversations = ConversationService(store)
    conversations.create_conversation(
        conversation_id="conversation-a", user_id="user-a",
        selected_theme_id="robotics", created_at=NOW,
    )
    memories = MemoryService(store)

    for source_ids in (["missing-message"], []):
        try:
            memories.create(
                memory_id="memory-x", user_id="user-a", conversation_id="conversation-a",
                category="preference", scope="personal", content="偏好",
                confidence=0.8, source_message_ids=source_ids, created_at=NOW,
            )
        except ValueError as exc:
            assert str(exc) == "source_message_ids must belong to the conversation"
        else:
            raise AssertionError("invalid source messages were accepted")
    store.close()
