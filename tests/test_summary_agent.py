from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
from etf_theme_radar.conversations import ConversationService
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.summary_agent import persist_summary_result, schedule_summary, summary_agent_prompt


NOW = "2026-08-14T00:00:00+00:00"


def test_summary_agent_prompt_is_versioned_and_forbids_external_tools() -> None:
    prompt = summary_agent_prompt()
    assert "不调用外部工具" in prompt
    assert "rebuild_required" in prompt
    assert "previous_version_id" in prompt


def _conversation(store: EvidenceStore) -> list[dict]:
    service = ConversationService(store)
    service.create_conversation(
        conversation_id="conversation-a", user_id="user-a",
        selected_theme_id="robotics", created_at=NOW,
    )
    for seq in range(1, 4):
        service.append_user_message(
            conversation_id="conversation-a", user_id="user-a",
            message_id=f"message-{seq}", goal_id=f"goal-{seq}",
            idempotency_key=f"turn-{seq}", content=f"消息 {seq}，引用 evidence-{seq}。",
            created_at=f"2026-08-14T00:0{seq}:00+00:00",
        )
    return service.messages("conversation-a", "user-a")


def _output(*, previous_version_id: str | None = None) -> dict:
    return {
        "status": "completed",
        "conversation_summary": "已核验 evidence-1，仍需核验 evidence-3。",
        "memory_changes": [],
        "keywords": ["机器人"],
        "related_theme_suggestions": [],
        "compression_checkpoint": {
            "goal": "研究机器人主题", "evidence_ids": ["evidence-1", "evidence-3"],
            "next_steps": ["补齐反方证据"],
        },
        "covered_from_seq": 1,
        "covered_to_seq": 3,
        "previous_version_id": previous_version_id,
        "source_message_ids": ["message-1", "message-2", "message-3"],
    }


def test_summary_persists_immutable_version_and_contiguous_checkpoint(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "summary.db")
    messages = _conversation(store)

    result = persist_summary_result(
        store, conversation_id="conversation-a", user_id="user-a",
        messages_snapshot=messages, output=_output(),
        valid_evidence_ids={"evidence-1", "evidence-3"}, created_at=NOW,
    )

    assert result["status"] == "completed"
    assert result["version"] == 1
    assert result["covered_to_seq"] == 3
    assert store.latest_conversation_checkpoint("conversation-a", "user-a")["covered_to_seq"] == 3
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.conn.execute(
            "UPDATE conversation_summary_versions SET status='changed' WHERE summary_version_id=?",
            (result["summary_version_id"],),
        )
    store.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.conn.execute(
            "DELETE FROM context_checkpoints WHERE summary_version_id=?",
            (result["summary_version_id"],),
        )
    store.rollback()
    store.close()


def test_summary_rebuilds_on_gap_missing_citation_or_previous_version_mismatch(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path / "summary-invalid.db")
    messages = _conversation(store)
    first = persist_summary_result(
        store, conversation_id="conversation-a", user_id="user-a",
        messages_snapshot=messages, output=_output(),
        valid_evidence_ids={"evidence-1", "evidence-3"}, created_at=NOW,
    )

    cases = [
        (messages[:1] + messages[2:], _output(previous_version_id=first["summary_version_id"]), {"evidence-1", "evidence-3"}, "message_sequence_gap"),
        (messages, _output(previous_version_id=first["summary_version_id"]), {"evidence-1"}, "unknown_evidence_id"),
        (messages, _output(previous_version_id="wrong-version"), {"evidence-1", "evidence-3"}, "previous_version_mismatch"),
    ]
    for snapshot, output, evidence_ids, reason in cases:
        result = persist_summary_result(
            store, conversation_id="conversation-a", user_id="user-a",
            messages_snapshot=snapshot, output=output,
            valid_evidence_ids=evidence_ids, created_at=NOW,
        )
        assert result == {"status": "rebuild_required", "reason": reason}

    assert len(store.conversation_summary_versions("conversation-a", "user-a")) == 1
    store.close()


def test_summary_scheduling_is_persistent_and_debounces_to_latest_answer(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "summary-queue.db")
    _conversation(store)

    first = schedule_summary(
        store, conversation_id="conversation-a", user_id="user-a", message_seq=2,
        goal_id="summary-goal-1", now=NOW, due_at="2026-08-14T00:00:05+00:00",
    )
    second = schedule_summary(
        store, conversation_id="conversation-a", user_id="user-a", message_seq=3,
        goal_id="summary-goal-2", now="2026-08-14T00:00:02+00:00",
        due_at="2026-08-14T00:00:07+00:00",
    )

    assert first["goal_id"] == second["goal_id"] == "summary-goal-1"
    assert second["debounced"] is True
    assert second["payload"]["target_message_seq"] == 3
    assert second["payload"]["not_before_at"] == "2026-08-14T00:00:07+00:00"
    assert store.claim_next_agent_goal(
        "summary-worker", "background", "2026-08-14T00:00:06+00:00",
        "2026-08-14T00:01:06+00:00", 1,
    ) is None
    claimed = store.claim_next_agent_goal(
        "summary-worker", "background", "2026-08-14T00:00:08+00:00",
        "2026-08-14T00:01:08+00:00", 1,
    )
    assert claimed is not None
    assert claimed["status"] == "summarizing"
    store.close()
