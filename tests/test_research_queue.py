from pathlib import Path

from etf_theme_radar.store import EvidenceStore


def _request(topic: str) -> dict:
    return {"topic": topic, "sources": ["arxiv"], "output_type": "theme_report"}


def test_queue_allows_one_active_and_one_waiting_then_rejects_third(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "queue.db")
    created = "2026-07-31T00:00:00+00:00"
    assert store.enqueue_theme_research_run("active", "pending", created, _request("机器人")) == "planning"
    assert store.enqueue_theme_research_run("waiting", "pending", created, _request("核能")) == "waiting"
    assert store.enqueue_theme_research_run("third", "pending", created, _request("半导体")) == "full"
    assert store.research_run("waiting")["queue_position"] == 1
    assert store.research_run("third") is None
    store.close()


def test_terminal_transition_promotes_waiter_but_returned_keeps_slot(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "promote.db")
    created = "2026-07-31T00:00:00+00:00"
    store.enqueue_theme_research_run("active", "pending", created, _request("机器人"))
    store.enqueue_theme_research_run("waiting", "pending", created, _request("核能"))
    store.transition_research_run(
        "active", {"planning"}, status="returned", stage="theme_review",
        updated_at=created, result={}, progress=12,
    )
    assert store.promote_waiting_run(created) is None
    changed, promoted = store.transition_and_promote(
        "active", {"returned"}, promote=True, status="cancelled", stage="closed",
        updated_at=created, result={}, progress=12,
    )
    assert changed is True and promoted == "waiting"
    assert store.research_run("waiting")["status"] == "planning"
    assert store.research_run("waiting")["queue_position"] is None
    store.close()
