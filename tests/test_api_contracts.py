from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from etf_theme_radar.api import _research_run_snapshot, app
from etf_theme_radar.store import EvidenceStore


def test_fastapi_research_and_capability_contract(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "api.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200 and health.json()["trading"] == "disabled"
        capability = client.get("/api/capabilities")
        assert capability.status_code == 200
        payload = capability.json()
        assert payload["output_types"] == {"theme_report": True}
        assert payload["core_capability"]["name"] == "分析 ETF 格局、跟踪产业动量"
        assert payload["service"]["id"] == "etf-theme-radar"
        assert payload["service"]["contract_version"] == "2026-08-05.v9"
        assert payload["worker"]["alive"] is True and payload["worker"]["heartbeat_at"]
        assert payload["sync_discovery_worker"]["alive"] is True
        assert payload["source_coverage"] == {"ready": 7, "total": 8, "label": "7/8", "excluded": ["patentsview"]}
        sources = {item["source_name"]: item for item in payload["sources"]}
        assert sources["google_patents"]["evidence_role"] == "discovery"
        assert sources["official_etf_holdings"]["authority"] == "official"
        assert sources["official_etf_holdings"]["logo_url"] is None
        assert sources["yahoo_etf_news"]["cache_ttl_seconds"] == 1800
        assert payload["runtime_profiles"]["theme_report"]["source_selection"] == "automatic"

        listed = client.get("/api/research-runs", params={"limit": 5, "offset": 0})
        assert listed.status_code == 200
        assert listed.json() == {
            "runs": [], "total": 0, "limit": 5, "offset": 0, "has_more": False,
        }

        legacy = client.post("/api/research-runs", json={"topic": "机器人", "output_type": "quick_scan"})
        assert legacy.status_code == 422
        created = client.post("/api/research-runs", json={"topic": "机器人", "output_type": "theme_report", "sources": []})
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            item = client.get(f"/api/research-runs/{run_id}")
            if item.json()["status"] == "awaiting_theme_review":
                break
            time.sleep(.02)
        assert item.status_code == 200
        assert item.json()["request"]["output_type"] == "theme_report"
        assert item.json()["request"]["source_selection"] == "automatic"
        assert item.json()["request"]["time_range"] == "multi_horizon"
        assert any(call["tool_name"] == "llm_theme_definition" for call in item.json()["tool_calls"])

        search = client.get("/api/search", params={"q": "机器人"})
        assert search.status_code == 200
        assert search.json()["count"] >= 0


def test_stream_snapshot_exposes_running_tool_and_incremental_progress(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "stream.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    store = EvidenceStore(db)
    store.create_research_run(
        "stream-run", "robotics", "2026-08-05T00:00:00+00:00",
        {"topic": "机器人", "sources": ["arxiv"], "output_type": "theme_report"},
        status="collecting", stage="collecting",
    )
    store.start_tool_call(
        run_id="stream-run", attempt=1, call_uid="stream-call", agent_run_id="agent",
        round_number=1, tool_name="collect_from_source",
        started_at="2026-08-05T00:00:01+00:00", arguments={"source": "arxiv"},
    )
    store.close()

    snapshot = _research_run_snapshot("stream-run")
    assert snapshot and snapshot["progress"] == 30
    assert snapshot["stream_events"] == [{
        "id": 1, "kind": "tool_call", "name": "collect_from_source", "status": "running",
        "started_at": "2026-08-05T00:00:01+00:00", "finished_at": "", "source": "arxiv",
        "evidence_delta": 0, "relevant_evidence_delta": 0, "latency_ms": 0,
    }]
