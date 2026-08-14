from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from etf_theme_radar.api import app
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
