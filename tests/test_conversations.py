from __future__ import annotations

import sqlite3
import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from etf_theme_radar.api import app, conversation_event_stream
from etf_theme_radar.conversations import ConversationService
from etf_theme_radar.store import EvidenceStore


CREATED_AT = "2026-08-14T00:00:00+00:00"


def test_message_write_is_idempotent_sequenced_and_immutable(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "messages.db")
    service = ConversationService(store)
    service.create_conversation(
        conversation_id="conversation-a",
        user_id="user-a",
        selected_theme_id="robotics",
        created_at=CREATED_AT,
    )

    first = service.append_user_message(
        conversation_id="conversation-a",
        user_id="user-a",
        message_id="message-1",
        goal_id="goal-1",
        idempotency_key="turn:conversation-a:1",
        content="机器人产业链的最新证据是什么？",
        created_at=CREATED_AT,
    )
    replay = service.append_user_message(
        conversation_id="conversation-a",
        user_id="user-a",
        message_id="message-2",
        goal_id="goal-2",
        idempotency_key="turn:conversation-a:1",
        content="这段重放内容不得覆盖原消息",
        created_at="2026-08-14T00:01:00+00:00",
    )
    second = service.append_user_message(
        conversation_id="conversation-a",
        user_id="user-a",
        message_id="message-3",
        goal_id="goal-3",
        idempotency_key="turn:conversation-a:2",
        content="补充 ETF 格局。",
        created_at="2026-08-14T00:02:00+00:00",
    )

    assert first["message"]["message_seq"] == 1
    assert replay["idempotent_replay"] is True
    assert replay["message"] == first["message"]
    assert replay["goal"]["goal_id"] == "goal-1"
    assert second["message"]["message_seq"] == 2
    assert [item["content"] for item in service.messages("conversation-a", "user-a")] == [
        "机器人产业链的最新证据是什么？",
        "补充 ETF 格局。",
    ]

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.conn.execute(
            "UPDATE conversation_messages SET content='changed' WHERE message_id='message-1'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.conn.execute("DELETE FROM conversation_messages WHERE message_id='message-1'")
    store.close()


def test_conversation_api_replays_idempotency_key_without_duplicate_goal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "conversation-api.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")

    with TestClient(app) as client:
        created = client.post(
            "/api/conversations",
            json={"selected_theme_id": "robotics", "title": "机器人研究"},
        )
        assert created.status_code == 201
        conversation_id = created.json()["conversation_id"]

        first = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "机器人产业链的最新证据是什么？", "idempotency_key": "client-turn-1"},
        )
        replay = client.post(
            f"/api/conversations/{conversation_id}/messages",
            json={"content": "重放不得覆盖", "idempotency_key": "client-turn-1"},
        )
        listed = client.get(f"/api/conversations/{conversation_id}/messages")

    assert first.status_code == 202
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["message"] == first.json()["message"]
    assert listed.status_code == 200
    assert listed.json()["messages"] == [first.json()["message"]]

    store = EvidenceStore(database)
    assert store.conn.execute("SELECT COUNT(*) FROM agent_goals").fetchone()[0] == 1
    store.close()


def test_conversation_audit_events_are_persistent_safe_and_cursor_resumable(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "audit.db")
    service = ConversationService(store)
    service.create_conversation(
        conversation_id="conversation-a", user_id="user-a",
        selected_theme_id="robotics", created_at=CREATED_AT,
    )
    turn = service.append_user_message(
        conversation_id="conversation-a", user_id="user-a",
        message_id="message-1", goal_id="goal-1", idempotency_key="turn-1",
        content="分析机器人主题。", created_at=CREATED_AT,
    )
    created_event_id = store.agent_goal_events("goal-1")[-1]["event_id"]
    action_id = store.append_conversation_audit_event(
        "goal-1", "action_status", "2026-08-14T00:00:01+00:00",
        action="正在检索公开来源", status="running", elapsed_ms=50, source_count=2,
    )
    store.append_conversation_audit_event(
        "goal-1", "tool_summary", "2026-08-14T00:00:02+00:00",
        tool_name="collect_from_source", tool_status="succeeded",
        safe_summary="SEC 返回 1 条已治理证据", raw_added=2, relevant_added=1,
    )
    store.append_conversation_audit_event(
        "goal-1", "answer_chunk", "2026-08-14T00:00:03+00:00",
        answer_chunk="阶段性结论。",
    )

    first_page = store.conversation_audit_events(
        "conversation-a", "user-a", after_event_id=created_event_id,
    )
    resumed = store.conversation_audit_events(
        "conversation-a", "user-a", after_event_id=action_id,
    )

    assert turn["goal"]["goal_id"] == "goal-1"
    assert [item["kind"] for item in first_page] == [
        "action_status", "tool_summary", "answer_chunk",
    ]
    assert resumed[0] == {
        "event_id": resumed[0]["event_id"],
        "goal_id": "goal-1",
        "kind": "tool_summary",
        "created_at": "2026-08-14T00:00:02+00:00",
        "action": "",
        "status": "",
        "elapsed_ms": 0,
        "source_count": 0,
        "tool_name": "collect_from_source",
        "tool_status": "succeeded",
        "safe_summary": "SEC 返回 1 条已治理证据",
        "raw_added": 2,
        "relevant_added": 1,
        "answer_chunk": "",
    }
    assert "url" not in json.dumps(first_page).casefold()
    store.close()


def test_conversation_sse_resumes_after_persisted_event_id(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "stream.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    store = EvidenceStore(database)
    service = ConversationService(store)
    service.create_conversation(
        conversation_id="conversation-a", user_id="local",
        selected_theme_id="robotics", created_at=CREATED_AT,
    )
    service.append_user_message(
        conversation_id="conversation-a", user_id="local",
        message_id="message-1", goal_id="goal-1", idempotency_key="turn-1",
        content="分析机器人主题。", created_at=CREATED_AT,
    )
    first_id = store.append_conversation_audit_event(
        "goal-1", "action_status", "2026-08-14T00:00:01+00:00",
        action="正在组装上下文", status="completed",
    )
    second_id = store.append_conversation_audit_event(
        "goal-1", "answer_chunk", "2026-08-14T00:00:02+00:00",
        answer_chunk="第一段回答。",
    )
    store.close()

    async def consume() -> str:
        stream = conversation_event_stream(
            "conversation-a", "local", after_event_id=first_id,
            poll_interval=.001, heartbeat_seconds=.01,
        )
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    event = asyncio.run(consume())
    assert f"id: {second_id}" in event
    assert "event: answer_chunk" in event
    assert "第一段回答。" in event
    assert f"id: {first_id}" not in event
