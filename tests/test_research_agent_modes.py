from __future__ import annotations

from pathlib import Path

import pytest

from etf_theme_radar.agent_runtime import (
    prepare_research_turn,
    route_research_turn,
    validate_research_answer,
)
from etf_theme_radar.store import EvidenceStore


def test_answer_now_uses_frozen_context_without_retrieval() -> None:
    decision = route_research_turn(
        context_sufficient=True,
        requires_latest=False,
        missing_critical_facts=[],
        quick_retrieval_sources=["sec", "openalex"],
    )

    assert decision == {
        "mode": "answer_now",
        "retrieval_sources": [],
        "stop_conditions": ["frozen_context_sufficient"],
    }


def test_quick_retrieve_is_bounded_and_stops_when_evidence_is_sufficient() -> None:
    decision = route_research_turn(
        context_sufficient=False,
        requires_latest=True,
        missing_critical_facts=["最新官方进展"],
        quick_retrieval_sources=["sec", "openalex", "official_etf_holdings", "yahoo_etf_news"],
    )

    assert decision["mode"] == "quick_retrieve"
    assert decision["retrieval_sources"] == ["sec", "openalex", "official_etf_holdings"]
    assert decision["stop_conditions"] == [
        "evidence_sufficient", "all_selected_sources_checked", "quick_budget_exhausted",
    ]


def test_background_research_returns_phase_answer_and_idempotent_goal(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "background.db")
    first = prepare_research_turn(
        store,
        conversation_id="conversation-a",
        message_seq=3,
        phase_answer="现有证据只支持阶段性判断，尚缺最新官方数据。",
        selected_theme_id="robotics",
        missing_critical_facts=["最新官方数据", "反方证据"],
        created_at="2026-08-14T00:00:00+00:00",
        background_goal_id="background-1",
    )
    replay = prepare_research_turn(
        store,
        conversation_id="conversation-a",
        message_seq=3,
        phase_answer="重放不得覆盖原阶段性回答。",
        selected_theme_id="changed",
        missing_critical_facts=["changed"],
        created_at="2026-08-14T00:01:00+00:00",
        background_goal_id="background-2",
    )

    assert first["mode"] == "background_research"
    assert first["events"] == ["phase_answer_ready", "background_goal_created"]
    assert first["phase_answer"] == "现有证据只支持阶段性判断，尚缺最新官方数据。"
    assert first["background_goal"]["lane"] == "background"
    assert first["background_goal"]["payload"]["missing_critical_facts"] == [
        "最新官方数据", "反方证据",
    ]
    assert replay["idempotent_replay"] is True
    assert replay["phase_answer"] == first["phase_answer"]
    assert replay["background_goal"]["goal_id"] == "background-1"
    store.close()


def test_answer_rejects_citations_not_present_in_frozen_or_tool_inputs() -> None:
    answer = {
        "text": "阶段性结论。",
        "citations": ["evidence-1", "invented-id"],
    }

    with pytest.raises(ValueError, match="invented-id"):
        validate_research_answer(
            answer,
            frozen_evidence_ids={"evidence-1"},
            tool_result_ids={"tool-evidence-1"},
        )
