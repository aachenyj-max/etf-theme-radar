from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from etf_theme_radar.api import app


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
        assert payload["output_types"] == {"theme_report": True, "quick_scan": True, "etf_opportunity_analysis": True}
        assert payload["service"]["id"] == "etf-theme-radar"
        assert payload["service"]["contract_version"] == "2026-07-31.v4"
        assert payload["worker"]["alive"] is True and payload["worker"]["heartbeat_at"]
        assert payload["source_coverage"] == {"ready": 7, "total": 8, "label": "7/8", "excluded": ["patentsview"]}
        sources = {item["source_name"]: item for item in payload["sources"]}
        assert sources["google_patents"]["evidence_role"] == "discovery"
        assert sources["official_etf_holdings"]["authority"] == "official"
        assert sources["official_etf_holdings"]["logo_url"] is None
        assert sources["yahoo_etf_news"]["cache_ttl_seconds"] == 1800
        assert payload["runtime_profiles"]["etf_opportunity_analysis"]["max_seconds"] == 240

        listed = client.get("/api/research-runs", params={"limit": 5, "offset": 0})
        assert listed.status_code == 200
        assert listed.json() == {
            "runs": [], "total": 0, "limit": 5, "offset": 0, "has_more": False,
        }

        created = client.post("/api/research-runs", json={"topic": "机器人", "output_type": "quick_scan", "sources": []})
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        deadline = time.time() + 5
        while time.time() < deadline:
            item = client.get(f"/api/research-runs/{run_id}")
            if item.json()["status"] == "awaiting_theme_review":
                break
            time.sleep(.02)
        assert item.status_code == 200
        assert item.json()["request"]["output_type"] == "quick_scan"
        assert any(call["tool_name"] == "llm_theme_definition" for call in item.json()["tool_calls"])

        search = client.get("/api/search", params={"q": "机器人"})
        assert search.status_code == 200
        assert search.json()["count"] >= 0
