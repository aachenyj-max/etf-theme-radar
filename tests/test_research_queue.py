from pathlib import Path

from etf_theme_radar.store import EvidenceStore


def _request(topic: str) -> dict:
    return {"topic": topic, "sources": ["arxiv"], "output_type": "theme_report"}


def test_queue_allows_one_execution_and_fifo_waiters(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "queue.db")
    created = "2026-07-31T00:00:00+00:00"
    assert store.enqueue_theme_research_run("active", "pending", created, _request("机器人")) == "planning"
    assert store.enqueue_theme_research_run("waiting-1", "pending", created, _request("核能")) == "waiting"
    assert store.enqueue_theme_research_run("waiting-2", "pending", created, _request("半导体")) == "waiting"
    assert store.research_run("waiting-1")["queue_position"] == 1
    assert store.research_run("waiting-2")["queue_position"] == 2
    store.close()


def test_attention_state_releases_execution_slot_and_promotes_fifo_head(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "promote.db")
    created = "2026-07-31T00:00:00+00:00"
    store.enqueue_theme_research_run("active", "pending", created, _request("机器人"))
    store.enqueue_theme_research_run("waiting-1", "pending", created, _request("核能"))
    store.enqueue_theme_research_run("waiting-2", "pending", created, _request("半导体"))

    changed, promoted = store.transition_and_promote(
        "active", {"planning"}, promote=True,
        status="awaiting_theme_review", stage="theme_review", updated_at=created,
        result={}, progress=12,
    )

    assert changed is True and promoted == "waiting-1"
    assert store.research_run("active")["status"] == "awaiting_theme_review"
    assert store.research_run("waiting-1")["status"] == "planning"
    assert store.research_run("waiting-2")["queue_position"] == 1
    store.close()


def test_reviewed_run_joins_fifo_and_resumes_only_when_it_reaches_head(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "review.db")
    created = "2026-07-31T00:00:00+00:00"
    store.create_research_run(
        "reviewed", "pending", created, _request("机器人"),
        status="awaiting_theme_review", stage="theme_review",
    )
    store.enqueue_theme_research_run("active", "pending", created, _request("核能"))
    store.enqueue_theme_research_run("waiting", "pending", created, _request("半导体"))

    changed, promoted = store.requeue_research_run(
        "reviewed", {"awaiting_theme_review"}, stage_after_promotion="queued",
        updated_at=created, result={}, progress=15,
    )
    assert changed is True and promoted is None
    assert store.research_run("waiting")["queue_position"] == 1
    assert store.research_run("reviewed")["status"] == "waiting"
    assert store.research_run("reviewed")["stage"] == "queued"
    assert store.research_run("reviewed")["queue_position"] == 2

    changed, promoted = store.transition_and_promote(
        "active", {"planning"}, promote=True,
        status="awaiting_report_review", stage="report_review", updated_at=created,
        result={}, progress=92,
    )
    assert changed is True and promoted == "waiting"
    store.transition_and_promote(
        "waiting", {"planning"}, promote=True,
        status="awaiting_theme_review", stage="theme_review", updated_at=created,
        result={}, progress=12,
    )
    assert store.research_run("reviewed")["status"] == "queued"
    assert store.research_run("reviewed")["stage"] == "queued"
    store.close()


def test_new_run_does_not_overtake_waiter_when_worker_was_restarted(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "restart.db")
    created = "2026-07-31T00:00:00+00:00"
    store.create_research_run(
        "waiting", "pending", created, _request("核能"),
        status="waiting", stage="planning",
    )
    store.conn.execute("UPDATE research_runs SET queue_position=1 WHERE run_id='waiting'")
    store.commit()

    assert store.enqueue_theme_research_run("new", "pending", created, _request("机器人")) == "waiting"
    assert store.research_run("waiting")["status"] == "planning"
    assert store.research_run("new")["queue_position"] == 1
    store.close()


def test_interactive_goals_are_serial_per_conversation_but_parallel_across_conversations(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path / "conversation-queue.db")
    created_at = "2026-08-14T00:00:00+00:00"
    for goal_id, conversation_id, number in (
        ("a-1", "conversation-a", 1),
        ("a-2", "conversation-a", 2),
        ("b-1", "conversation-b", 1),
    ):
        store.create_agent_goal(
            goal_id=goal_id,
            idempotency_key=f"{conversation_id}:{number}",
            goal_type="research_turn",
            lane="interactive",
            payload={"conversation_id": conversation_id, "message_seq": number},
            created_at=created_at,
        )

    first = store.claim_next_agent_goal(
        "worker-a", "interactive", "2026-08-14T00:00:01+00:00",
        "2026-08-14T00:01:01+00:00", 10,
    )
    parallel = store.claim_next_agent_goal(
        "worker-b", "interactive", "2026-08-14T00:00:02+00:00",
        "2026-08-14T00:01:02+00:00", 10,
    )

    assert first and first["goal_id"] == "a-1"
    assert first["status"] == "context_building"
    assert parallel and parallel["goal_id"] == "b-1"
    assert store.agent_goal("a-2")["status"] == "queued"

    store.transition_agent_goal(
        "a-1", "worker-a", "answering", "2026-08-14T00:00:03+00:00"
    )
    store.transition_agent_goal(
        "a-1", "worker-a", "completed", "2026-08-14T00:00:04+00:00"
    )
    resumed = store.claim_next_agent_goal(
        "worker-c", "interactive", "2026-08-14T00:00:05+00:00",
        "2026-08-14T00:01:05+00:00", 10,
    )

    assert resumed and resumed["goal_id"] == "a-2"
    store.close()
