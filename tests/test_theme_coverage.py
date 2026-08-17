from __future__ import annotations

from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.theme_coverage import refresh_theme_coverage


NOW = "2026-08-17T00:00:00+00:00"


def _event(event_id: str, *, source_type: str = "academic", theme: str = "robotics") -> NormalizedEvent:
    return NormalizedEvent(event_id, "fixture", f"https://example.com/{event_id}", source_type, "Evidence", "Evidence", "2026-08-17", NOW, (theme,), primary_theme=theme, relevance_status="relevant", theme_assignment_status="assigned", publisher="fixture")


def test_refresh_persists_six_evidence_derived_coverage_cells_and_gap_goal(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "coverage.db")
    store.save_event(_event("evidence-1")); store.save_content_quality_result({"event_id":"evidence-1","parser_version":"v1","status":"publishable","evaluated_at":NOW}); store.commit()

    cells = refresh_theme_coverage(store, theme_id="robotics", now=NOW)

    assert {cell["coverage_kind"] for cell in cells} == {"source_diversity", "counter_evidence", "entity_coverage", "time_continuity", "industry_chain", "etf_coverage"}
    industry = next(cell for cell in cells if cell["coverage_kind"] == "industry_chain")
    assert industry["status"] == "gap" and industry["evidence_ids"] == []
    goals = [goal for goal in (store.agent_goal(f"coverage:robotics:{cell['coverage_kind']}") for cell in cells) if goal]
    assert len(goals) == 6
    store.close()


def test_refresh_replays_gap_goals_without_overwriting_manual_terminal_goal(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "replay.db")
    first = refresh_theme_coverage(store, theme_id="robotics", now=NOW)
    goal_id = "coverage:robotics:source_diversity"
    store.request_agent_goal_cancel(goal_id, NOW, reason="manual_stop")
    refresh_theme_coverage(store, theme_id="robotics", now="2026-08-18T00:00:00+00:00")

    assert store.agent_goal(goal_id)["status"] == "cancelled"
    assert len(first) == 6
    store.close()
