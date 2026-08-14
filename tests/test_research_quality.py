from __future__ import annotations

from etf_theme_radar.agent_runtime import validate_research_answer


def test_research_answer_accepts_only_existing_references() -> None:
    answer = {
        "text": "截至冻结日期，证据支持有限。",
        "citations": ["evidence-1", "tool-evidence-1"],
    }

    assert validate_research_answer(
        answer,
        frozen_evidence_ids={"evidence-1"},
        tool_result_ids={"tool-evidence-1"},
    ) == answer
