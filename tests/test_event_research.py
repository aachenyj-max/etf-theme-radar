import json
from pathlib import Path

from etf_theme_radar.event_research import run_event_deep_dive
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore


def test_generic_deep_dive_separates_verified_and_unverified_facts(tmp_path: Path):
    store = EvidenceStore(tmp_path / "events.db")
    event = NormalizedEvent(
        "discovery-event", "anysearch_discovery", "https://example.com/modular-data-center", "social",
        "Company Announces Modular Data Center Project", "A company describes an AI modular data center project.",
        None, "2026-07-22T00:00:00+00:00", ("ai-infrastructure",), source_quality=.3,
        extraction_confidence=.8, discovery_source="anysearch_discovery", origin_source_type="unknown",
        publisher="stocktitan.net", publisher_domain="stocktitan.net", primary_or_secondary="secondary",
        relevance_status="relevant", theme_assignment_status="assigned", primary_theme="ai-infrastructure",
        classification_confidence=.85,
    )
    primary = NormalizedEvent(
        "primary-event", "sec_edgar", "https://www.sec.gov/Archives/primary", "official",
        "Company filing", "The company disclosed a signed agreement with conditions.", None,
        "2026-07-21T00:00:00+00:00", ("ai-infrastructure",), source_quality=1,
        extraction_confidence=.95, origin_source_type="official", publisher="stocktitan.net",
        primary_or_secondary="primary", relevance_status="relevant", theme_assignment_status="assigned",
        primary_theme="ai-infrastructure", classification_confidence=.95,
    )
    store.save_event(event); store.save_event(primary); store.commit()
    result = run_event_deep_dive(store, "discovery-event", tmp_path / "report")
    facts = result["fact_pack"]["facts"]
    assert any(fact["status"] == "unverified" for fact in facts)
    assert any(fact["status"] == "verified" and fact["url"] == primary.source_url for fact in facts)
    assert result["fact_pack"]["audit"]["passed"] is True
    report = (tmp_path / "report/event-deep-dive.md").read_text(encoding="utf-8")
    assert primary.source_url in report and "不构成投资" in report
    store.close()


def test_deep_dive_never_treats_unverified_discovery_as_primary(tmp_path: Path):
    store = EvidenceStore(tmp_path / "events.db")
    event = NormalizedEvent("other", "fixture", "https://example.test/story", "social", "Other event", "Unverified claim", None, "2026-07-22T00:00:00+00:00", ("robotics",), publisher="example.test", relevance_status="relevant", theme_assignment_status="assigned", primary_theme="robotics", classification_confidence=.8)
    store.save_event(event); store.commit(); result = run_event_deep_dive(store, "other", tmp_path / "report")
    assert result["fact_pack"]["data_confidence"] == "low"
    assert not any(source["tier"] == "primary" for source in result["fact_pack"]["sources"])
    store.close()
