from __future__ import annotations

import asyncio
import json
import time
from datetime import date
from pathlib import Path

from etf_theme_radar.api import ResearchRequest, ReviewRequest, create_research_run, research_run_events, review_report, review_theme
from etf_theme_radar.connectors import FixtureConnector
from etf_theme_radar.pipeline import ingest
from etf_theme_radar.store import EvidenceStore


def _wait_for(db: Path, run_id: str, status: str) -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        store = EvidenceStore(db)
        try: run = store.research_run(run_id)
        finally: store.close()
        if run and run["status"] == status: return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not reach {status}: {run}")


def test_open_theme_review_and_report_review_flow(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "workflow.db"
    store = EvidenceStore(db)
    try:
        ingest(FixtureConnector(Path("tests/fixtures/events.json")), store, date(2025, 1, 1), date.today())
    finally: store.close()
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    created = create_research_run(ResearchRequest(topic="AI 基础设施", sources=["arxiv"], output_type="theme_report"))
    run_id = created["run_id"]
    planned = _wait_for(db, run_id, "awaiting_theme_review")
    assert planned["result"]["theme_definition"]["name"] == "AI 基础设施"

    review_theme(run_id, ReviewRequest(decision="approve"))
    generated = _wait_for(db, run_id, "awaiting_report_review")
    assert generated["result"]["audit"]["passed"] is True

    review_report(run_id, ReviewRequest(decision="approve"))
    completed = _wait_for(db, run_id, "completed")
    assert completed["progress"] == 100
    store = EvidenceStore(db)
    try:
        reports = store.report_assets()
        approvals = store.approvals(run_id)
    finally: store.close()
    assert len(reports) == 1
    assert [item["gate"] for item in approvals] == ["theme_definition", "final_report"]


def test_return_does_not_automatically_rerun(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "returned.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    created = create_research_run(ResearchRequest(topic="核能", output_type="theme_report"))
    run_id = created["run_id"]
    _wait_for(db, run_id, "awaiting_theme_review")
    review_theme(run_id, ReviewRequest(decision="return", note="缩小研究边界"))
    returned = _wait_for(db, run_id, "returned")
    assert returned["stage"] == "theme_review"
    assert returned["result"]["available_actions"] == ["rerun"]


def test_known_theme_unified_research_skips_theme_review(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "known-etf.db"
    store = EvidenceStore(db)
    try:
        store.save_theme_definition({"theme_id": "robotics", "name": "机器人", "description": "机器人主题", "aliases": ["智能机器人"]}, "2026-07-30T00:00:00Z", confirmed=True)
    finally:
        store.close()
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    created = create_research_run(ResearchRequest(topic="智能机器人", sources=[], output_type="theme_report"))
    generated = _wait_for(db, created["run_id"], "awaiting_report_review")
    store = EvidenceStore(db)
    try:
        planning = next(item for item in store.run_steps(created["run_id"]) if item["step_name"] == "planning")
        approvals = store.approvals(created["run_id"])
    finally:
        store.close()
    assert planning["details"]["known_theme"] is True
    assert planning["details"]["auto_continue"] is True
    assert generated["review_gate"] == "final_report"
    assert approvals == []


def test_research_run_stream_emits_snapshot_and_stops_at_review(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "stream.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    store = EvidenceStore(db)
    try:
        store.create_research_run("stream-run", "pending", "2026-07-29T00:00:00Z", {"topic": "机器人"}, status="awaiting_theme_review", stage="theme_review")
        store.update_research_run("stream-run", status="awaiting_theme_review", stage="theme_review", updated_at="2026-07-29T00:00:01Z", progress=12, review_gate="theme_definition")
    finally:
        store.close()

    async def consume() -> tuple[str, bool]:
        events = research_run_events("stream-run", poll_interval=.001, heartbeat_seconds=.01)
        first = await anext(events)
        try:
            await anext(events)
        except StopAsyncIteration:
            return first, True
        return first, False

    first, stopped = asyncio.run(consume())
    payload = json.loads(first.split("data: ", 1)[1])
    assert "event: run_snapshot" in first
    assert payload["run_id"] == "stream-run"
    assert payload["status"] == "awaiting_theme_review"
    assert stopped is True
