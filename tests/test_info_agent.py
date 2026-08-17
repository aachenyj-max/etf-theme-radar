from __future__ import annotations

from pathlib import Path

from etf_theme_radar.info_agent import (
    create_information_goal,
    governed_evidence_ids,
    information_agent_prompt,
    run_information_goal,
)
from etf_theme_radar.agent_runtime import prepare_research_turn
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.sync_worker import SyncDiscoveryWorker


NOW = "2026-08-17T00:00:00+00:00"


def _save_publishable_event(store: EvidenceStore, event_id: str) -> None:
    event = NormalizedEvent(
        event_id=event_id,
        source="fixture",
        source_url=f"https://example.com/{event_id}",
        source_type="academic",
        title="Governed evidence",
        summary="A complete governed event for the information agent.",
        published_at="2026-08-17",
        observed_at=NOW,
        themes=("robotics",),
        primary_theme="robotics",
        relevance_status="relevant",
        theme_assignment_status="assigned",
    )
    store.save_event(event)
    store.save_content_quality_result({
        "event_id": event_id,
        "parser_version": "content-quality-v1",
        "status": "publishable",
        "evaluated_at": NOW,
    })
    store.commit()


def test_information_agent_prompt_is_versioned_and_requires_counter_check() -> None:
    prompt = information_agent_prompt()

    assert "info-agent-v1" in prompt
    assert "反方" in prompt
    assert "有效增量" in prompt


def test_daily_and_event_information_goals_are_idempotent(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "idempotency.db")
    first = create_information_goal(
        store, kind="daily", goal_id="daily-1", now=NOW, scheduled_for="2026-08-17",
    )
    replay = create_information_goal(
        store, kind="daily", goal_id="daily-2", now="2026-08-17T01:00:00+00:00",
        scheduled_for="2026-08-17",
    )
    event = create_information_goal(
        store, kind="event", goal_id="event-1", now=NOW, evidence_id="evidence-1",
    )

    assert first["idempotency_key"] == "information:daily:2026-08-17"
    assert replay["goal_id"] == "daily-1"
    assert replay["idempotent_replay"] is True
    assert event["idempotency_key"] == "information:event:evidence-1"
    assert event["payload"]["information_kind"] == "event"
    store.close()


def test_event_goal_freezes_trigger_context_for_related_governed_evidence(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "event-context.db")
    _save_publishable_event(store, "trigger")
    goal = create_information_goal(store, kind="event", goal_id="event-1", now=NOW, evidence_id="trigger")
    _save_publishable_event(store, "related")

    assert goal["payload"]["target_theme_ids"] == ["robotics"]
    assert governed_evidence_ids(store, goal["payload"]) == {"trigger", "related"}
    store.close()


def test_background_research_uses_limited_system_selected_sources(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "background.db")
    queued = prepare_research_turn(store, conversation_id="conversation-a", message_seq=1, phase_answer="阶段性回答", selected_theme_id="robotics", missing_critical_facts=["反方证据"], created_at=NOW, background_goal_id="background-1")["background_goal"]
    claimed = store.claim_next_agent_goal("worker-a", "background", NOW, "2026-08-17T00:01:00+00:00", 2)
    calls: list[tuple[str, str]] = []
    result = run_information_goal(store, claimed, "worker-a", collect=lambda source, purpose, _payload: calls.append((source, purpose)) or {"status": "succeeded"}, now=NOW)

    assert queued["payload"]["sources"]
    assert result["counter_check"]["attempted"] is True
    assert any(purpose == "support" for _, purpose in calls)
    store.close()


def test_information_goal_stops_support_collection_after_governed_zero_deltas_and_records_counter(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "bounded.db")
    queued = create_information_goal(
        store,
        kind="daily",
        goal_id="bounded-goal",
        now=NOW,
        scheduled_for="2026-08-17",
        sources=["first", "second", "third", "fourth"],
        counter_sources=["counter"],
    )
    goal = store.claim_next_agent_goal("worker-a", "background", NOW, "2026-08-17T00:01:00+00:00", 2)
    assert goal and goal["goal_id"] == queued["goal_id"]
    calls: list[tuple[str, str]] = []

    def collect(source: str, purpose: str, _payload: dict) -> dict:
        calls.append((source, purpose))
        if source == "first" and purpose == "support":
            _save_publishable_event(store, "accepted-event")
        return {"status": "succeeded", "source": source}

    result = run_information_goal(store, goal, "worker-a", collect=collect, now=NOW)

    assert result["status"] == "completed"
    assert result["governed_effective_added"] == 1
    assert result["stop_reason"] == "governed_no_effective_increment"
    assert result["counter_check"]["attempted"] is True
    assert calls == [
        ("first", "support"),
        ("second", "support"),
        ("third", "support"),
        ("counter", "counter"),
    ]
    persisted = store.agent_goal("bounded-goal")
    assert persisted and persisted["status"] == "completed"
    assert persisted["result"]["remaining_gaps"]
    assert [call["tool_name"] for call in store.tool_calls("bounded-goal")] == [
        "collect_information", "collect_information", "collect_information", "collect_information",
    ]
    store.close()


def test_information_goal_honours_cooperative_cancellation_at_collection_boundary(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "cancel.db")
    create_information_goal(store, kind="daily", goal_id="cancel-goal", now=NOW, scheduled_for="2026-08-17", sources=["first"])
    goal = store.claim_next_agent_goal("worker-a", "background", NOW, "2026-08-17T00:01:00+00:00", 2)
    assert goal

    def collect(_source: str, _purpose: str, _payload: dict) -> dict:
        store.request_agent_goal_cancel("cancel-goal", "2026-08-17T00:00:10+00:00", reason="user_requested")
        return {"status": "succeeded"}

    result = run_information_goal(store, goal, "worker-a", collect=collect, now=NOW)

    assert result == {"status": "cancelled", "reason": "user_requested"}
    assert store.agent_goal("cancel-goal")["status"] == "cancelled"
    store.close()


def test_recovered_information_goal_resumes_from_validating_without_replaying_completed_source(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "recovered.db")
    create_information_goal(
        store, kind="daily", goal_id="recovered-goal", now=NOW,
        scheduled_for="2026-08-17", sources=["first", "second"], counter_sources=["counter"],
    )
    claimed = store.claim_next_agent_goal("worker-a", "background", NOW, "2026-08-17T00:01:00+00:00", 2)
    assert claimed
    progress = {
        "support_sources": ["first"],
        "consecutive_zero_effective_deltas": 0,
        "baseline_evidence_ids": [],
    }
    store.transition_agent_goal("recovered-goal", "worker-a", "collecting", NOW, safe_summary="resume fixture", result=progress)
    store.transition_agent_goal("recovered-goal", "worker-a", "validating", NOW, safe_summary="resume fixture", result=progress)
    calls: list[tuple[str, str]] = []

    def collect(source: str, purpose: str, _payload: dict) -> dict:
        calls.append((source, purpose))
        return {"status": "succeeded"}

    result = run_information_goal(store, store.agent_goal("recovered-goal"), "worker-a", collect=collect, now=NOW)

    assert result["status"] == "completed"
    assert calls == [("second", "support"), ("counter", "counter")]
    store.close()


def test_sync_worker_claims_only_information_collection_goals(tmp_path: Path) -> None:
    database = tmp_path / "worker.db"
    store = EvidenceStore(database)
    create_information_goal(store, kind="daily", goal_id="information-goal", now=NOW, scheduled_for="2026-08-17", sources=[])
    store.create_agent_goal(
        goal_id="summary-goal",
        idempotency_key="summary:one",
        goal_type="conversation_summary",
        lane="background",
        payload={"conversation_id": "conversation-a", "not_before_at": "2026-08-17T00:00:00+00:00"},
        created_at=NOW,
    )
    store.close()

    worker = SyncDiscoveryWorker(database)

    assert worker.run_once() is True
    check = EvidenceStore(database)
    assert check.agent_goal("information-goal")["status"] == "completed"
    assert check.agent_goal("summary-goal")["status"] == "queued"
    check.close()
