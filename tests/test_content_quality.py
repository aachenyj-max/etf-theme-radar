from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from etf_theme_radar.content_quality import evaluate_content_quality
from etf_theme_radar.api import dashboard
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.connectors import FixtureConnector
from etf_theme_radar.ontology import refresh_theme_snapshots
from etf_theme_radar.pipeline import ingest
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.theme_research import run_theme_research


FIXTURES = Path(__file__).parent / "fixtures"


def _event(**overrides) -> dict:
    item = {
        "event_id": "event-1",
        "title": "Sample Semiconductor expands advanced packaging capacity",
        "summary": "Sample Semiconductor announced a new advanced packaging production line.",
        "source_type": "official",
        "publisher": "Sample Semiconductor",
        "companies": ["Sample Semiconductor"],
        "raw_content_hash": "hash-1",
    }
    item.update(overrides)
    return item


def test_title_equal_to_summary_requires_distinct_factual_summary() -> None:
    sample = json.loads((FIXTURES / "title_equals_summary.json").read_text(encoding="utf-8"))

    result = evaluate_content_quality(
        sample,
        "Sample Research Institute published an outlook describing new AI infrastructure deployments.",
    )

    assert result.status == "needs_enrichment"
    assert "distinct_summary" in result.missing_fields
    assert "title_equals_summary" in result.issues


def test_navigation_or_disclaimer_dominated_body_is_not_publishable() -> None:
    raw_html = (FIXTURES / "holdings_navigation_noise.html").read_text(encoding="utf-8")

    result = evaluate_content_quality(
        _event(
            title="SAMP Holdings",
            summary="SAMP disclosed Sample Semiconductor at a 10.50% portfolio weight.",
            source_type="etf",
        ),
        raw_html,
    )

    assert result.status == "needs_enrichment"
    assert "clean_body" in result.missing_fields
    assert "boilerplate_ratio_exceeded" in result.issues
    assert result.metrics["boilerplate_ratio"] > 0.25


def test_empty_body_is_rejected() -> None:
    result = evaluate_content_quality(_event(), "  ")

    assert result.status == "rejected"
    assert "raw_text" in result.missing_fields
    assert result.issues == ("empty_body",)


def test_missing_event_subject_and_action_are_reported_independently() -> None:
    result = evaluate_content_quality(
        _event(
            title="Advanced packaging update",
            summary="Advanced packaging update for the current quarter.",
            publisher="",
            companies=[],
        ),
        "Advanced packaging technology and market context for the current quarter.",
    )

    assert result.status == "needs_enrichment"
    assert {"event_subject", "event_action"}.issubset(result.missing_fields)


def test_complete_event_is_publishable_with_deterministic_metrics() -> None:
    result = evaluate_content_quality(
        _event(),
        "Sample Semiconductor announced a new advanced packaging production line in Singapore.",
        evaluated_at="2026-08-14T00:00:00+00:00",
    )

    assert result.status == "publishable"
    assert result.missing_fields == ()
    assert result.issues == ()
    assert result.metrics == {
        "raw_text_chars": 85,
        "summary_chars": 72,
        "boilerplate_chars": 0,
        "boilerplate_ratio": 0.0,
    }
    assert result.evaluated_at == "2026-08-14T00:00:00+00:00"


def test_only_publishable_evidence_enters_dashboard_and_theme_score_inputs(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "gate.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    store = EvidenceStore(database)
    for event_id, status in (("good", "publishable"), ("bad", "needs_enrichment")):
        store.save_event(NormalizedEvent(
            event_id, "fixture", f"https://example.com/{event_id}", "official",
            f"{event_id} evidence", "Sample Company announced a production expansion.",
            "2026-08-14", "2026-08-14T00:00:00+00:00", ("robotics",),
            companies=("Sample Company",), tickers=("SAMP",),
            origin_source_type="official", publisher="Sample Company",
            publisher_domain="example.com", primary_or_secondary="primary",
            relevance_status="relevant", theme_assignment_status="assigned",
            primary_theme="robotics", classification_confidence=.9,
        ))
        store.save_content_quality_result({
            "event_id": event_id,
            "content_hash": f"hash-{event_id}",
            "parser_version": "content-quality-v1",
            "status": status,
            "missing_fields": [] if status == "publishable" else ["distinct_summary"],
            "issues": [] if status == "publishable" else ["title_equals_summary"],
            "metrics": {},
            "evaluated_at": "2026-08-14T00:00:00+00:00",
        })
    store.commit()

    assert [item["event_id"] for item in store.publishable_events()] == ["good"]
    snapshot = refresh_theme_snapshots(store, "2026-08-14")[0]
    assert snapshot["evidence_count"] == 1
    assert snapshot["metrics"]["listed_companies"] == 1
    store.close()
    assert dashboard()["metrics"]["evidence"] == 1


def test_ingest_persists_one_quality_result_per_normalized_event(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "ingest.db")

    outcome = ingest(
        FixtureConnector(FIXTURES / "events.json"), store,
        date(2025, 1, 1), date(2025, 1, 31),
    )

    assert outcome["events"] == 3
    assert all(store.content_quality_result(item["event_id"]) for item in store.events())
    store.close()


def test_formal_research_excludes_evidence_that_did_not_pass_quality_gate(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "research-gate.db")
    for event_id, status in (("good", "publishable"), ("bad", "needs_enrichment")):
        store.save_event(NormalizedEvent(
            event_id, "fixture", f"https://example.com/{event_id}", "official",
            f"{event_id} evidence", "Sample Company announced a production expansion.",
            "2026-08-14", "2026-08-14T00:00:00+00:00", ("robotics",),
            companies=("Sample Company",), tickers=("SAMP",), source_quality=.9,
            origin_source_type="official", publisher="Sample Company",
            publisher_domain="example.com", primary_or_secondary="primary",
            relevance_status="relevant", theme_assignment_status="assigned",
            primary_theme="robotics", classification_confidence=.9,
        ))
        store.save_content_quality_result({
            "event_id": event_id, "content_hash": f"hash-{event_id}",
            "parser_version": "content-quality-v1", "status": status,
            "missing_fields": [] if status == "publishable" else ["distinct_summary"],
            "issues": [] if status == "publishable" else ["title_equals_summary"],
            "metrics": {}, "evaluated_at": "2026-08-14T00:00:00+00:00",
        })
    store.commit()

    run_theme_research(store, "robotics", tmp_path / "output", theme_name="Robotics")
    appendix = json.loads((tmp_path / "output" / "evidence-appendix.json").read_text(encoding="utf-8"))

    assert [item["evidence_id"] for item in appendix["selected"]] == ["good"]
    store.close()
