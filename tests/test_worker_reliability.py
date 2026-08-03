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


@pytest.mark.parametrize("output_type", ["quick_scan", "theme_report", "etf_opportunity_analysis"])
def test_worker_resumes_one_persisted_phase_at_a_time(tmp_path: Path, monkeypatch, output_type: str) -> None:
    db = tmp_path / "phases.db"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    store = EvidenceStore(db)
    store.create_research_run("run-phases", "robotics", "2026-07-29T00:00:00+00:00", {"topic": "机器人", "sources": [], "output_type": output_type}, status="queued", stage="collecting")
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
    if output_type == "etf_opportunity_analysis":
        assert "etf_opportunity" in final["result"]


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


def test_event_research_uses_the_same_durable_worker(tmp_path: Path, monkeypatch) -> None:
    db=tmp_path/"events-worker.db"; monkeypatch.setenv("DATABASE_PATH",str(db)); monkeypatch.setenv("DEEPSEEK_API_KEY","")
    store=EvidenceStore(db)
    store.save_event(NormalizedEvent("event-1","fixture","https://example.com/event","social","Generic event","Unverified event lead",None,"2026-07-29T00:00:00+00:00",("robotics",),publisher="example.com",relevance_status="relevant",theme_assignment_status="assigned",primary_theme="robotics",classification_confidence=.8)); store.commit(); store.close()
    created=create_event_research_run(EventResearchRequest(evidence_id="event-1")); deadline=time.time()+5
    while True:
        item=get_event_research_run(created["run_id"])
        if item["status"] in {"completed","failed"} or time.time()>=deadline: break
        time.sleep(.02)
    assert item["status"]=="completed"
    assert item["result"]["fact_pack"]["audit"]["passed"] is True
    stop_all_workers()
