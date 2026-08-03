import json
from pathlib import Path

from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.theme_research import run_theme_research


def _event(event_id: str, *, status="relevant", assignment="assigned", publisher="example.com", source_type="official"):
    return NormalizedEvent(
        event_id, "fixture", f"https://{publisher}/{event_id}", source_type, "AI infrastructure evidence",
        "AI infrastructure compute cluster evidence", "2026-07-22", "2026-07-22T00:00:00+00:00",
        ("ai-infrastructure",), source_quality=.9, extraction_confidence=.9,
        discovery_source="fixture", origin_source_type="company_official", publisher=publisher,
        publisher_domain=publisher, primary_or_secondary="primary", relevance_status=status,
        theme_assignment_status=assignment, primary_theme="ai-infrastructure", classification_confidence=.9,
        classification_reasons=("命中两个明确主题术语",), company_id=publisher,
        technical_or_nontechnical="technical", duplicate_job_cluster=event_id,
    )


def test_classification_reasons_round_trip_as_array(tmp_path: Path):
    store = EvidenceStore(tmp_path / "events.db"); store.save_event(_event("one")); store.commit()
    reasons = json.loads(store.events()[0]["classification_reasons"])
    assert reasons == ["命中两个明确主题术语"]
    store.close()


def test_irrelevant_and_uncertain_are_excluded_and_no_history_claim(tmp_path: Path):
    store = EvidenceStore(tmp_path / "events.db")
    for item in (_event("good"), _event("bad", status="irrelevant", assignment="no_theme_match"), _event("review", status="uncertain", assignment="needs_review")): store.save_event(item)
    store.commit(); result = run_theme_research(store, "ai-infrastructure", tmp_path / "report")
    assert result["selected"] == 1 and result["status"] == "WATCH"
    assert result["audit"]["no_trend_claim"] is True
    assert "历史趋势" not in result["report_markdown"]
    assert json.loads((tmp_path / "report/etf-landscape.json").read_text(encoding="utf-8"))["product_white_space"] == "unknown"
    store.close()


def test_single_source_and_missing_counter_search_cannot_deep_research(tmp_path: Path):
    store = EvidenceStore(tmp_path / "events.db")
    for number in range(5): store.save_event(_event(str(number), publisher="same.example"))
    store.commit(); result = run_theme_research(store, "ai-infrastructure", tmp_path / "report")
    assert result["status"] != "DEEP_RESEARCH"
    appendix = json.loads((tmp_path / "report/evidence-appendix.json").read_text(encoding="utf-8"))
    assert appendix["counter"]["counter_evidence_status"] == "insufficient_search"
    store.close()


def test_key_evidence_cards_have_urls_and_do_not_repeat_publishers(tmp_path: Path):
    store = EvidenceStore(tmp_path / "events.db")
    for number, publisher in enumerate(("a.example", "b.example", "c.example", "d.example", "e.example", "f.example")):
        item = _event(str(number), publisher=publisher)
        if number == 0:
            item = item.__class__(**{**item.__dict__, "source_type": "jobs"})
        store.save_event(item)
    store.commit(); result = run_theme_research(store, "ai-infrastructure", tmp_path / "report")
    cards = result["brief"]["key_evidence"]
    assert len(cards) == 5
    assert all(card["source_url"] and card["research_implication"] and card["limitation"] for card in cards)
    assert len({card["publisher"] for card in cards}) == 5
    assert sum(card["event_kind"] == "jobs" for card in cards) <= 1
    store.close()
