from __future__ import annotations

import json
import base64
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from etf_theme_radar.api import _research_run_snapshot, _theme_payloads, app
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore


PROJECT_ROOT = Path(__file__).parents[1]


def test_knowledge_api_is_private_by_default_and_confirms_share_before_write(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "knowledge-api.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("KNOWLEDGE_FILES_DIR", str(tmp_path / "knowledge-files"))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")
    payload = {
        "kind": "note", "title": "内部机器人笔记", "content_base64": base64.b64encode(b"hardware notes").decode(),
        "filename": "notes.txt", "mime_type": "text/plain", "theme_id": "robotics",
        "folder_id": "private", "idempotency_key": "create-knowledge-1",
    }
    with TestClient(app) as client:
        assert client.get("/health").json()["contract_version"] == "2026-08-18.v18"
        created = client.post("/api/knowledge", json=payload)
        replay = client.post("/api/knowledge", json=payload)
        assert created.status_code == 201
        assert replay.status_code == 200
        item_id = created.json()["knowledge_item_id"]
        assert replay.json()["knowledge_item_id"] == item_id
        assert client.get("/api/knowledge").json()["items"][0]["visibility"] == "private"

        preview = client.post(f"/api/knowledge/{item_id}/operations/preview", json={
            "operation_type": "share", "payload": {"subject_type": "user", "subject_id": "user-b"},
            "idempotency_key": "share-knowledge-1",
        })
        assert preview.status_code == 201
        assert preview.json()["status"] == "pending_confirmation"
        confirmation = client.post(f"/api/knowledge/operations/{preview.json()['operation_id']}/confirm", json={
            "confirmation_token": preview.json()["confirmation_token"],
        })
        assert confirmation.status_code == 200
        assert confirmation.json()["status"] == "completed"
        assert client.post(f"/api/knowledge/operations/{preview.json()['operation_id']}/confirm", json={
            "confirmation_token": preview.json()["confirmation_token"],
        }).status_code == 409


def test_fastapi_research_and_capability_contract(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "api.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("SEC_USER_AGENT", "contract-test test@example.com")
    monkeypatch.setenv("ANYSEARCH_ENABLED", "true")
    monkeypatch.setenv("SP_GLOBAL_ENABLED", "false")
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200 and health.json()["trading"] == "disabled"
        capability = client.get("/api/capabilities")
        assert capability.status_code == 200
        payload = capability.json()
        assert payload["output_types"] == {"theme_report": True}
        assert payload["core_capability"]["name"] == "分析 ETF 格局、跟踪产业动量"
        assert payload["service"]["id"] == "etf-theme-radar"
        assert payload["service"]["contract_version"] == "2026-08-18.v18"
        assert payload["llm"]["concurrency"]["lane_reservations"] == {
            "interactive": 10, "background": 2,
        }
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


def test_theme_payload_exposes_governed_timeline_and_persisted_coverage_gaps(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "theme-detail.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    store = EvidenceStore(database)
    for event_id, status in (("publishable", "publishable"), ("blocked", "needs_enrichment")):
        store.save_event(NormalizedEvent(
            event_id, "fixture", f"https://example.com/{event_id}", "official",
            f"{event_id} event", "Robot manufacturer announced a production expansion.",
            "2026-08-17", "2026-08-17T00:00:00+00:00", ("robotics",),
            origin_source_type="official", publisher="Example Manufacturer",
            primary_or_secondary="primary", relevance_status="relevant",
            theme_assignment_status="assigned", primary_theme="robotics",
            classification_confidence=0.9,
        ))
        store.save_content_quality_result({
            "event_id": event_id, "content_hash": event_id, "parser_version": "content-quality-v1",
            "status": status, "missing_fields": [], "issues": [], "metrics": {},
            "evaluated_at": "2026-08-17T00:00:00+00:00",
        })
    store.save_theme_coverage_cell({
        "theme_id": "robotics", "coverage_kind": "source_diversity", "status": "covered",
        "evidence_ids": ["publishable"], "reason": "governed evidence", "next_path": "",
        "updated_at": "2026-08-17T00:00:00+00:00",
    })
    store.save_theme_coverage_cell({
        "theme_id": "robotics", "coverage_kind": "counter_evidence", "status": "missing",
        "evidence_ids": [], "reason": "no independent counter evidence", "next_path": "collect an independent source",
        "updated_at": "2026-08-17T00:00:00+00:00",
    })
    store.close()

    theme = _theme_payloads()[0]

    assert [item["evidence_id"] for item in theme["timeline"]] == ["publishable"]
    assert theme["coverageGaps"] == [{
        "kind": "counter_evidence", "reason": "no independent counter evidence",
        "next_path": "collect an independent source", "updated_at": "2026-08-17T00:00:00+00:00",
    }]


def test_legacy_report_id_resolves_registered_run_database(tmp_path: Path, monkeypatch) -> None:
    registry_db = tmp_path / "registry.db"
    run_db = tmp_path / "legacy-run.db"
    monkeypatch.setenv("DATABASE_PATH", str(registry_db))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")

    created_at = "2026-08-05T00:00:00+00:00"
    registry = EvidenceStore(registry_db)
    registry.register_run("legacy-run", str(run_db), created_at)
    registry.close()

    run_store = EvidenceStore(run_db)
    run_store.save_report_asset({
        "report_id": "report:legacy-run",
        "run_id": "legacy-run",
        "title": "旧版机器人主题报告",
        "kind": "theme_report",
        "theme_id": "robotics",
        "folder_id": "robotics",
        "status": "watch",
        "tags": ["机器人"],
        "summary": "旧版报告摘要。",
        "updated_at": created_at,
        "created_at": created_at,
        "version": 1,
        "source_count": 2,
        "evidence_count": 3,
        "audit_passed": True,
    })
    run_store.close()

    with TestClient(app) as client:
        response = client.get("/api/reports/report%3Alegacy-run/detail")

    assert response.status_code == 200
    assert response.json()["reportId"] == "report:legacy-run"
    assert response.json()["runId"] == "legacy-run"


def test_contract_snapshot_exports_runtime_and_frontend_dependencies() -> None:
    result = subprocess.run(
        [sys.executable, "tools/export_contract_snapshot.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
    )

    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0, stderr
    snapshot = json.loads(result.stdout.decode("utf-8"))
    assert snapshot["contract_version"] == "2026-08-18.v18"
    assert "research_runs" in snapshot["database_tables"]
    assert "report_versions" in snapshot["database_tables"]
    assert "content_quality_results" in snapshot["database_tables"]
    assert "extracted_facts" in snapshot["database_tables"]
    assert "extraction_exceptions" in snapshot["database_tables"]
    assert "independent_score_snapshots" in snapshot["database_tables"]
    assert "daily_briefing_assets" in snapshot["database_tables"]
    assert "conversations" in snapshot["database_tables"]
    assert "conversation_messages" in snapshot["database_tables"]
    assert "conversation_links" in snapshot["database_tables"]
    assert "knowledge_items" in snapshot["database_tables"]
    assert "knowledge_item_versions" in snapshot["database_tables"]
    assert "knowledge_shares" in snapshot["database_tables"]
    assert "document_chunks" in snapshot["database_tables"]
    assert snapshot["status_enums"]["content_quality"] == [
        "publishable", "needs_enrichment", "rejected",
    ]
    assert snapshot["status_enums"]["extracted_fact"] == ["audited", "incomplete"]
    assert snapshot["status_enums"]["extraction_exception"] == ["open", "resolved"]
    assert snapshot["status_enums"]["independent_score"] == ["assessed", "not_assessed"]
    assert snapshot["status_enums"]["agent_goal"] == {
        "active": [
            "planning", "collecting", "extracting", "validating", "replanning",
            "context_building", "answering", "quick_retrieval", "streaming",
            "summarizing", "validating_coverage",
        ],
        "terminal": [
            "completed", "partial", "needs_attention", "rebuild_required", "cancelled",
        ],
    }
    assert snapshot["status_enums"]["research_execution"] == [
        "planning", "queued", "collecting", "governing", "analyzing", "auditing",
    ]
    assert snapshot["status_enums"]["theme_candidate"] == [
        "signal", "validating", "awaiting_confirmation", "confirmed", "merged", "rejected",
    ]
    assert snapshot["status_enums"]["sync_run"] == [
        "queued", "running", "completed", "cancelled", "failed",
    ]
    assert snapshot["status_enums"]["discovery_run"] == [
        "queued", "running", "completed", "failed",
    ]
    assert snapshot["status_enums"]["report_asset"] == [
        "deep_research", "watch", "completed", "draft", "archived",
    ]
    assert snapshot["status_enums"]["connector_health"] == [
        "healthy", "degraded", "disabled",
    ]
    assert {"GET", "/api/capabilities"} in [set(item) for item in snapshot["api_routes"]]
    assert {"GET", "/api/dashboard"} in [set(item) for item in snapshot["api_routes"]]
    assert {"GET", "/api/reports/{report_id}/detail"} in [set(item) for item in snapshot["api_routes"]]
    assert {"POST", "/api/conversations"} in [set(item) for item in snapshot["api_routes"]]
    assert {"POST", "/api/conversations/{conversation_id}/messages"} in [
        set(item) for item in snapshot["api_routes"]
    ]
    assert {"GET", "/api/conversations/{conversation_id}/events"} in [
        set(item) for item in snapshot["api_routes"]
    ]
    assert {"GET", "/api/conversations/{conversation_id}/stream"} in [
        set(item) for item in snapshot["api_routes"]
    ]
    assert {"GET", "/api/conversations/{conversation_id}/links"} in [
        set(item) for item in snapshot["api_routes"]
    ]
    assert {"PUT", "/api/conversations/{conversation_id}/links"} in [
        set(item) for item in snapshot["api_routes"]
    ]
    assert {"GET", "/api/knowledge"} in [set(item) for item in snapshot["api_routes"]]
    assert {"POST", "/api/knowledge"} in [set(item) for item in snapshot["api_routes"]]
    assert {"POST", "/api/knowledge/{item_id}/operations/preview"} in [
        set(item) for item in snapshot["api_routes"]
    ]
    report_gateway = snapshot["frontend_gateway_dependencies"]["report-detail-gateway.ts"]
    assert "/api/reports/{report_id}/detail" in report_gateway
    research_gateway = snapshot["frontend_gateway_dependencies"]["research-workflow-gateway.ts"]
    assert research_gateway == [
        "/api/research-runs",
        "/api/research-runs/{run_id}",
        "/api/research-runs/{run_id}/cancel",
        "/api/research-runs/{run_id}/finish",
        "/api/research-runs/{run_id}/report-review",
        "/api/research-runs/{run_id}/rerun",
        "/api/research-runs/{run_id}/stream",
        "/api/research-runs/{run_id}/theme-review",
    ]
