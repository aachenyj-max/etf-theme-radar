from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from etf_theme_radar.api import app
from etf_theme_radar.models import ConnectorHealth, NormalizedEvent
from etf_theme_radar.reports import build_daily_briefing
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.sync_worker import SyncDiscoveryWorker


NOW = "2026-08-17T08:00:00+00:00"


def _save_event(
    store: EvidenceStore,
    *,
    event_id: str,
    theme: str,
    source: str,
    quality_status: str,
    industry_chain: str = "unknown",
) -> None:
    store.save_event(NormalizedEvent(
        event_id=event_id,
        source=source,
        source_url=f"https://example.com/{event_id}",
        source_type="official",
        title=f"{event_id} title",
        summary=f"{event_id} announces a specific industrial action.",
        published_at="2026-08-17",
        observed_at=NOW,
        themes=(theme,),
        origin_source_type="official",
        publisher="Example Publisher",
        publisher_domain="example.com",
        primary_or_secondary="primary",
        relevance_status="relevant",
        theme_assignment_status="assigned",
        primary_theme=theme,
        classification_confidence=0.9,
    ))
    store.save_content_quality_result({
        "event_id": event_id,
        "content_hash": f"hash-{event_id}",
        "parser_version": "content-quality-v1",
        "status": quality_status,
        "missing_fields": [] if quality_status == "publishable" else ["event_action"],
        "issues": [] if quality_status == "publishable" else ["missing_event_action"],
        "metrics": {},
        "evaluated_at": NOW,
    })
    store.save_extracted_fact({
        "event_id": event_id,
        "content_hash": f"hash-{event_id}",
        "parser_version": "fact-extraction-v1",
        "status": "audited",
        "subject": "Example Publisher",
        "occurred_at": "2026-08-17",
        "action": "announced",
        "numbers": [],
        "domain": "industrial technology",
        "location": "",
        "industry_chain_position": industry_chain,
        "audit_errors": [],
        "extracted_at": NOW,
    })


def test_daily_briefing_persists_only_publishable_audited_facts(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "briefing.db")
    _save_event(
        store,
        event_id="publishable-event",
        theme="robotics",
        source="sec",
        quality_status="publishable",
        industry_chain="upstream",
    )
    _save_event(
        store,
        event_id="rejected-event",
        theme="robotics",
        source="jobs",
        quality_status="rejected",
        industry_chain="downstream",
    )
    store.commit()

    asset = build_daily_briefing(store, as_of_date="2026-08-17", generated_at=NOW)
    saved = store.save_daily_briefing_asset(asset)
    store.close()

    assert saved["briefing_id"] == "daily-briefing:2026-08-17"
    assert saved["evidence_ids"] == ["publishable-event"]
    assert saved["payload"]["events"] == [{
        "evidence_id": "publishable-event",
        "title": "publishable-event title",
        "summary": "publishable-event announces a specific industrial action.",
        "occurred_at": "2026-08-17",
        "theme": "robotics",
        "source": "sec",
        "industry_chain": "upstream",
    }]


def test_dashboard_intersects_drilldowns_and_returns_aggregated_exceptions(
    tmp_path: Path, monkeypatch,
) -> None:
    database = tmp_path / "dashboard.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")
    store = EvidenceStore(database)
    _save_event(store, event_id="e-1", theme="robotics", source="sec", quality_status="publishable", industry_chain="upstream")
    _save_event(store, event_id="e-2", theme="robotics", source="sec", quality_status="publishable", industry_chain="downstream")
    _save_event(store, event_id="e-3", theme="ai", source="openalex", quality_status="publishable", industry_chain="upstream")
    _save_event(store, event_id="rejected", theme="robotics", source="jobs", quality_status="rejected", industry_chain="downstream")
    store.save_health(ConnectorHealth("sec", True, "degraded", "temporary outage", checked_at=NOW))
    store.save_daily_briefing_asset(build_daily_briefing(store, as_of_date="2026-08-17", generated_at=NOW))
    store.commit()
    store.close()

    with TestClient(app) as client:
        response = client.get(
            "/api/dashboard",
            params={"theme": "robotics", "industry_chain": "upstream", "source": "sec"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["briefing"] == {
        "briefing_id": "daily-briefing:2026-08-17",
        "as_of_date": "2026-08-17",
        "generated_at": NOW,
        "status": "available",
    }
    assert [item["evidence_id"] for item in payload["events"]] == ["e-1"]
    assert payload["facets"] == {
        "themes": [{"value": "ai", "count": 1}, {"value": "robotics", "count": 2}],
        "industry_chains": [{"value": "downstream", "count": 1}, {"value": "upstream", "count": 2}],
        "sources": [{"value": "openalex", "count": 1}, {"value": "sec", "count": 2}],
    }
    assert payload["exceptions"] == {
        "quality_statuses": {"rejected": 1},
        "source_health": [{"source": "sec", "status": "degraded", "coverage_note": "temporary outage"}],
    }


def test_dashboard_without_asset_returns_read_only_empty_brief(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "empty-dashboard.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.setenv("STARTUP_SYNC_ENABLED", "false")

    with TestClient(app) as client:
        response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["briefing"] == {
        "briefing_id": None,
        "as_of_date": None,
        "generated_at": None,
        "status": "not_available",
    }
    assert response.json()["events"] == []
    assert response.json()["facets"] == {"themes": [], "industry_chains": [], "sources": []}


def test_completed_daily_sync_creates_a_daily_briefing_asset(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "sync.db"
    store = EvidenceStore(database)
    _save_event(store, event_id="sync-event", theme="robotics", source="sec", quality_status="publishable", industry_chain="upstream")
    store.create_sync_run("daily-sync", NOW, days=1, idempotency_key="daily:2026-08-17")
    store.commit()
    store.close()

    monkeypatch.setattr("etf_theme_radar.sync_worker.configured_connectors", lambda _cache: [])
    monkeypatch.setattr("etf_theme_radar.sync_worker.reclassify_store", lambda _store: {})
    monkeypatch.setattr("etf_theme_radar.sync_worker.refresh_research_assets", lambda _store: {"theme_discovery": {}})

    worker = SyncDiscoveryWorker(database)
    assert worker.run_once() is True

    check = EvidenceStore(database)
    asset = check.latest_daily_briefing_asset()
    check.close()
    assert asset is not None
    assert asset["as_of_date"] == "2026-08-17"
    assert asset["evidence_ids"] == ["sync-event"]
