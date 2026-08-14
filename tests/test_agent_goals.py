from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from etf_theme_radar.agent_goals import AgentGoalRuntime, GoalConcurrencyPolicy
from etf_theme_radar.store import EvidenceStore


def _create_goal(store: EvidenceStore, goal_id: str, key: str, *, lane: str = "background") -> dict:
    return store.create_agent_goal(
        goal_id=goal_id,
        idempotency_key=key,
        goal_type="information_collection",
        lane=lane,
        payload={"theme_id": "robotics"},
        created_at="2026-08-14T00:00:00+00:00",
    )


def test_goal_creation_is_idempotent_and_preserves_original_payload(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "idempotent.db")
    first = _create_goal(store, "goal-1", "daily:robotics")
    replay = store.create_agent_goal(
        goal_id="goal-2",
        idempotency_key="daily:robotics",
        goal_type="information_collection",
        lane="background",
        payload={"theme_id": "changed"},
        created_at="2026-08-14T00:01:00+00:00",
    )

    assert first["goal_id"] == "goal-1"
    assert replay["goal_id"] == "goal-1"
    assert replay["payload"] == {"theme_id": "robotics"}
    assert replay["idempotent_replay"] is True
    assert [event["event_type"] for event in store.agent_goal_events("goal-1")] == ["created"]
    store.close()


def test_goal_claim_is_atomic_and_records_state_transition(tmp_path: Path) -> None:
    database = tmp_path / "atomic.db"
    store = EvidenceStore(database)
    _create_goal(store, "goal-1", "atomic:goal")
    store.close()

    def claim(owner: str) -> dict | None:
        local = EvidenceStore(database)
        try:
            return local.claim_next_agent_goal(
                owner=owner,
                lane="background",
                now="2026-08-14T00:00:01+00:00",
                lease_expires_at="2026-08-14T00:01:01+00:00",
                slot_limit=2,
            )
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ["worker-a", "worker-b"]))

    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0]["status"] == "planning"
    assert claimed[0]["lease_owner"] in {"worker-a", "worker-b"}

    local = EvidenceStore(database)
    events = local.agent_goal_events("goal-1")
    leases = local.active_concurrency_leases("2026-08-14T00:00:02+00:00")
    assert [(event["from_status"], event["to_status"]) for event in events] == [
        ("", "queued"),
        ("queued", "planning"),
    ]
    assert len(leases) == 1 and leases[0]["goal_id"] == "goal-1"
    local.close()


def test_goal_heartbeat_requires_owner_and_renews_both_leases(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "heartbeat.db")
    _create_goal(store, "goal-1", "heartbeat:goal")
    store.claim_next_agent_goal(
        "worker-a", "background", "2026-08-14T00:00:01+00:00",
        "2026-08-14T00:01:01+00:00", 2,
    )

    assert store.heartbeat_agent_goal(
        "goal-1", "worker-b", "2026-08-14T00:00:10+00:00", "2026-08-14T00:01:10+00:00"
    ) is False
    assert store.heartbeat_agent_goal(
        "goal-1", "worker-a", "2026-08-14T00:00:10+00:00", "2026-08-14T00:01:10+00:00"
    ) is True
    goal = store.agent_goal("goal-1")
    lease = store.active_concurrency_leases("2026-08-14T00:00:11+00:00")[0]
    assert goal and goal["heartbeat_at"] == "2026-08-14T00:00:10+00:00"
    assert lease["expires_at"] == "2026-08-14T00:01:10+00:00"
    store.close()


def test_goal_cancellation_is_immediate_when_queued_and_cooperative_when_running(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "cancel.db")
    _create_goal(store, "queued-goal", "cancel:queued")
    queued = store.request_agent_goal_cancel(
        "queued-goal", "2026-08-14T00:00:05+00:00", reason="user_requested"
    )
    assert queued and queued["status"] == "cancelled"

    _create_goal(store, "running-goal", "cancel:running")
    store.claim_next_agent_goal(
        "worker-a", "background", "2026-08-14T00:00:06+00:00",
        "2026-08-14T00:01:06+00:00", 2,
    )
    running = store.request_agent_goal_cancel(
        "running-goal", "2026-08-14T00:00:07+00:00", reason="user_requested"
    )
    assert running and running["status"] == "planning"
    assert running["cancel_requested"] is True
    assert store.transition_agent_goal(
        "running-goal", "worker-a", "cancelled", "2026-08-14T00:00:08+00:00",
        safe_summary="cancel acknowledged",
    )["status"] == "cancelled"
    assert store.active_concurrency_leases("2026-08-14T00:00:09+00:00") == []
    store.close()


def test_invalid_goal_transition_is_rejected_without_audit_event(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "transition.db")
    _create_goal(store, "goal-1", "transition:goal")
    store.claim_next_agent_goal(
        "worker-a", "background", "2026-08-14T00:00:01+00:00",
        "2026-08-14T00:01:01+00:00", 2,
    )

    with pytest.raises(ValueError, match="planning -> completed"):
        store.transition_agent_goal(
            "goal-1", "worker-a", "completed", "2026-08-14T00:00:02+00:00"
        )

    assert [event["event_type"] for event in store.agent_goal_events("goal-1")] == [
        "created", "claimed"
    ]
    store.close()


def test_concurrency_policy_reserves_lanes_and_recovers_slowly_after_pressure() -> None:
    policy = GoalConcurrencyPolicy(
        total_limit=12,
        interactive_reserved=10,
        background_reserved=2,
        minimum_total=2,
        cooldown_seconds=30,
    )

    assert policy.lane_limits == {"interactive": 10, "background": 2}
    assert policy.record_pressure(429, observed_at=100) is True
    assert policy.effective_total == 6
    assert policy.lane_limits == {"interactive": 5, "background": 1}
    assert policy.record_pressure(503, observed_at=101) is True
    assert policy.effective_total == 3
    assert policy.record_pressure(400, observed_at=102) is False
    assert policy.record_success(observed_at=130) is False
    assert policy.record_success(observed_at=131) is True
    assert policy.effective_total == 4
    assert policy.lane_limits == {"interactive": 3, "background": 1}


def test_runtime_enforces_reserved_background_slots_without_blocking_interactive(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "slots.db")
    policy = GoalConcurrencyPolicy(
        total_limit=12,
        interactive_reserved=10,
        background_reserved=2,
        minimum_total=2,
        cooldown_seconds=30,
    )
    runtime = AgentGoalRuntime(store, "worker-a", policy=policy)
    for number in range(3):
        _create_goal(store, f"background-{number}", f"background:{number}")
    _create_goal(store, "interactive-1", "interactive:1", lane="interactive")

    assert runtime.claim("background", "2026-08-14T00:00:01+00:00", "2026-08-14T00:01:01+00:00")
    assert runtime.claim("background", "2026-08-14T00:00:02+00:00", "2026-08-14T00:01:02+00:00")
    assert runtime.claim("background", "2026-08-14T00:00:03+00:00", "2026-08-14T00:01:03+00:00") is None
    interactive = runtime.claim("interactive", "2026-08-14T00:00:04+00:00", "2026-08-14T00:01:04+00:00")
    assert interactive and interactive["goal_id"] == "interactive-1"
    store.close()


def test_default_concurrency_policy_is_loaded_from_project_configuration() -> None:
    policy = GoalConcurrencyPolicy.from_defaults()

    assert policy.total_limit == 12
    assert policy.interactive_reserved == 10
    assert policy.background_reserved == 2
