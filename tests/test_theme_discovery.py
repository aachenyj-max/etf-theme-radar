from __future__ import annotations

from datetime import date
from pathlib import Path

from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.theme_discovery import discover_theme_candidates


def _signal(index: int, source_type: str, publisher: str, *, primary: str = "secondary") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=f"quantum-{index}", source=f"fixture-{index}", source_url=f"https://{publisher}/quantum-{index}",
        source_type=source_type, title=f"Quantum networking interconnect milestone {index}",
        summary=f"{publisher} expands quantum networking systems with Photon Corp and Node Labs.",
        published_at=f"2026-08-0{index}", observed_at=f"2026-08-0{index}T00:00:00+00:00",
        themes=("needs_review",), companies=("Photon Corp", "Node Labs"), source_quality=.9,
        extraction_confidence=.9, origin_source_type=source_type, publisher=publisher,
        publisher_domain=publisher, primary_or_secondary=primary, relevance_status="uncertain",
        theme_assignment_status="needs_review", primary_theme="needs_review",
    )


def test_candidate_requires_diverse_evidence_and_has_four_visual_blocks(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "discovery.db")
    for event in (
        _signal(1, "academic", "one.org", primary="primary"),
        _signal(2, "company_official", "two.com", primary="primary"),
        _signal(3, "patent", "three.gov", primary="primary"),
        _signal(4, "media", "four.com"),
    ):
        store.save_event(event)
    store.commit()
    summary = discover_theme_candidates(store, as_of=date(2026, 8, 4))
    candidates = store.theme_candidates()
    assert summary["finish_research"] is True
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["status"] == "awaiting_confirmation"
    assert candidate["metrics"]["gate_passed"] is True
    assert set(candidate["metrics"]["visualization_blocks"]) == {"evidence_timeline", "source_diffusion", "entity_coverage", "etf_coverage"}
    assert candidate["metrics"]["visualization_blocks"]["etf_coverage"]["status"] == "not_assessed"
    store.close()


def test_candidate_review_is_atomic_and_promotes_evidence(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "review.db")
    for index, source_type in enumerate(("academic", "company_official", "patent", "media"), 1):
        store.save_event(_signal(index, source_type, f"source{index}.org", primary="primary" if index < 4 else "secondary"))
    store.commit(); discover_theme_candidates(store, as_of=date(2026, 8, 4))
    candidate = store.theme_candidates()[0]
    result = store.review_theme_candidate(candidate["candidate_id"], "confirm", "2026-08-04T00:00:00+00:00", target_theme_id="quantum-networking")
    assert result == {"candidate_id": candidate["candidate_id"], "status": "confirmed", "theme_id": "quantum-networking"}
    assert all(store.event(f"quantum-{index}")["primary_theme"] == "quantum-networking" for index in range(1, 5))
    assert store.review_theme_candidate(candidate["candidate_id"], "reject", "2026-08-04T00:01:00+00:00") is None
    store.close()
