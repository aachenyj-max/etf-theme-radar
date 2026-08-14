from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import threading
import time

import pytest

from etf_theme_radar.api import EventResearchRequest, ResearchRequest, create_event_research_run, create_research_run, get_event_research_run, get_research_run
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.worker import DurableWorker, stop_all_workers
import etf_theme_radar.worker as worker_module


def test_run_lease_is_atomic_and_expired_lease_can_be_reclaimed(tmp_path: Path) -> None:
    db = tmp_path / "lease.db"
    store = EvidenceStore(db)
    store.create_research_run("run-1", "pending", "2026-07-29T00:00:00+00:00", {"topic": "机器人"}, status="planning", stage="planning")
    store.close()

    def claim(owner: str):
        local = EvidenceStore(db)
        try: return local.claim_next_run(owner, "2026-07-29T00:00:01+00:00", "2026-07-29T00:01:01+00:00")
        finally: local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(claim, ["worker-a", "worker-b"]))
    assert sum(item is not None for item in claimed) == 1

    local = EvidenceStore(db)
    try:
        reclaimed = local.claim_next_run("worker-c", "2026-07-29T00:02:00+00:00", "2026-07-29T00:03:00+00:00")
    finally: local.close()
    assert reclaimed and reclaimed["lease_owner"] == "worker-c"


def test_market_refresh_is_claimed_before_older_research_phase(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "priority.db")
    store.create_research_run(
        "older-research", "robotics", "2026-07-29T00:00:00+00:00",
        {"topic": "机器人"}, status="governing", stage="governing",
    )
    store.create_research_run(
        "market-refresh", "report-refresh:report:one", "2026-07-29T00:01:00+00:00",
        {"report_id": "report:one"}, status="queued", stage="market_refresh",
    )

    claimed = store.claim_next_run(
        "worker", "2026-07-29T00:02:00+00:00", "2026-07-29T00:03:00+00:00",
    )

    assert claimed and claimed["run_id"] == "market-refresh"
    store.close()


def test_worker_resumes_one_persisted_phase_at_a_time(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "phases.db"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    store = EvidenceStore(db)
    store.create_research_run("run-phases", "robotics", "2026-07-29T00:00:00+00:00", {"topic": "机器人", "sources": [], "output_type": "theme_report"}, status="queued", stage="collecting")
    store.update_research_run("run-phases", status="queued", stage="collecting", updated_at="2026-07-29T00:00:01+00:00", result={"theme_definition": {"theme_id": "robotics", "name": "机器人", "aliases": ["robotics"], "include_terms": ["robotics"]}})
    store.close()
    worker = DurableWorker(db)
    assert worker.run_once() is True
    assert EvidenceStore(db).research_run("run-phases")["stage"] == "governing"
    assert worker.run_once() is True
    assert EvidenceStore(db).research_run("run-phases")["stage"] == "analyzing"
    assert worker.run_once() is True
    assert EvidenceStore(db).research_run("run-phases")["stage"] == "auditing"
    assert worker.run_once() is True
    final_store = EvidenceStore(db)
    try: final = final_store.research_run("run-phases")
    finally: final_store.close()
    assert final and final["status"] == "awaiting_report_review"
    assert final["result"]["output_type"] == "theme_report"


def test_worker_survives_a_transient_sqlite_lock(tmp_path: Path, monkeypatch) -> None:
    worker = DurableWorker(tmp_path / "transient-lock.db", poll_seconds=.01)
    recovered = threading.Event()
    calls = 0

    def flaky_run_once() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("database is locked")
        recovered.set()
        return False

    monkeypatch.setattr(worker, "run_once", flaky_run_once)
    worker.start()
    assert recovered.wait(2)
    worker.stop()
    assert calls >= 2


def test_heartbeat_retries_a_transient_sqlite_lock(tmp_path: Path, monkeypatch) -> None:
    attempts = 0
    renewed = threading.Event()

    class FlakyHeartbeatStore:
        def __init__(self, _path): pass
        def heartbeat_run(self, *_args) -> bool:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise sqlite3.OperationalError("database is locked")
            renewed.set()
            return False
        def close(self): pass

    monkeypatch.setattr(worker_module, "EvidenceStore", FlakyHeartbeatStore)
    worker = DurableWorker(tmp_path / "heartbeat-lock.db", poll_seconds=.01, lease_seconds=1)
    stopped = threading.Event()
    thread = threading.Thread(target=worker._heartbeat_loop, args=("run-1", stopped), daemon=True)
    thread.start()
    assert renewed.wait(3)
    stopped.set()
    thread.join(1)
    assert attempts >= 2


def test_stale_agent_audit_is_closed_before_recovery(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "agent-recovery.db")
    store.create_agent_run({
        "agent_run_id": "stale-agent", "run_id": "run-1", "attempt": 1,
        "provider": "test", "model": "test", "prompt_version": "v1",
        "prompt_hash": "hash", "status": "running", "started_at": "2026-08-05T00:00:00+00:00",
    })
    assert store.close_interrupted_agent_runs("run-1", "2026-08-05T00:01:00+00:00") == 1
    recovered = store.agent_runs("run-1")[0]
    assert recovered["status"] == "interrupted"
    assert recovered["stop_reason"] == "worker_recovered"
    assert recovered["finished_at"] == "2026-08-05T00:01:00+00:00"
    store.close()


def test_expired_agent_goal_is_recovered_after_worker_restart(tmp_path: Path) -> None:
    database = tmp_path / "goal-recovery.db"
    first = EvidenceStore(database)
    first.create_agent_goal(
        goal_id="goal-restart",
        idempotency_key="restart:goal",
        goal_type="information_collection",
        lane="background",
        payload={"theme_id": "robotics"},
        created_at="2026-08-14T00:00:00+00:00",
    )
    claimed = first.claim_next_agent_goal(
        "worker-before-restart", "background", "2026-08-14T00:00:01+00:00",
        "2026-08-14T00:00:10+00:00", 2,
    )
    assert claimed and claimed["attempt"] == 1
    first.close()

    restarted = EvidenceStore(database)
    recovered = restarted.claim_next_agent_goal(
        "worker-after-restart", "background", "2026-08-14T00:00:11+00:00",
        "2026-08-14T00:01:11+00:00", 2,
    )

    assert recovered and recovered["goal_id"] == "goal-restart"
    assert recovered["status"] == "planning"
    assert recovered["attempt"] == 2
    assert recovered["lease_owner"] == "worker-after-restart"
    assert [event["event_type"] for event in restarted.agent_goal_events("goal-restart")] == [
        "created", "claimed", "recovered"
    ]
    restarted.close()


def test_custom_database_path_is_resolved_from_registry(tmp_path: Path, monkeypatch) -> None:
    control = tmp_path / "control.db"
    custom = tmp_path / "custom.db"
    monkeypatch.setenv("DATABASE_PATH", str(control))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    created = create_research_run(ResearchRequest(topic="核能", database_path=str(custom)))
    run_id = created["run_id"]
    deadline=time.time()+5
    while True:
        item = get_research_run(run_id)
        if item["status"] == "awaiting_theme_review" or time.time()>=deadline: break
        time.sleep(.02)
    assert item["database_path"] == str(custom)
    assert item["status"] == "awaiting_theme_review"
    stop_all_workers()


def test_event_research_creation_is_retired_but_legacy_reads_remain(tmp_path: Path, monkeypatch) -> None:
    db=tmp_path/"events-worker.db"; monkeypatch.setenv("DATABASE_PATH",str(db)); monkeypatch.setenv("DEEPSEEK_API_KEY","")
    store=EvidenceStore(db)
    store.save_event(NormalizedEvent("event-1","fixture","https://example.com/event","social","Generic event","Unverified event lead",None,"2026-07-29T00:00:00+00:00",("robotics",),publisher="example.com",relevance_status="relevant",theme_assignment_status="assigned",primary_theme="robotics",classification_confidence=.8)); store.commit(); store.close()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        create_event_research_run(EventResearchRequest(evidence_id="event-1"))
    assert exc.value.status_code == 410
