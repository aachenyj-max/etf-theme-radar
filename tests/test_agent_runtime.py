from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai import UsageLimits
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from etf_theme_radar.agent_runtime import (
    AgentBudget,
    ModelConfig,
    ResearchAgentDeps,
    _audited_tool,
    _build_research_agent,
    capability_status,
    prompt_hash,
    run_research_agent,
)
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.api import _research_run_snapshot
import etf_theme_radar.agent_runtime as runtime_module


def test_unconfigured_agent_is_audited_without_calling_a_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store = EvidenceStore(tmp_path / "agent.db")
    store.create_research_run("run-1", "pending", "2026-07-28T00:00:00Z", {"topic": "机器人", "sources": [], "time_range": "90d"})
    run = store.research_run("run-1")
    assert run is not None

    result = run_research_agent(store, run, {"theme_id": "robotics", "name": "机器人", "aliases": ["robotics"]})

    assert result["stop_reason"] == "model_not_configured"
    audits = store.agent_runs("run-1")
    assert audits[0]["status"] == "skipped"
    assert audits[0]["prompt_hash"] == prompt_hash("research_agent")
    store.close()


def test_function_model_chooses_tools_and_writes_audit(tmp_path: Path) -> None:
    calls = 0

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        returned = [part for message in messages for part in message.parts if isinstance(part, ToolReturnPart)]
        if not returned:
            return ModelResponse(parts=[ToolCallPart("query_existing_evidence", {"limit": 3}, "call-query")])
        if len(returned) == 1:
            return ModelResponse(parts=[ToolCallPart("finish_research", {"stop_reason": "tools_unavailable", "remaining_gaps": ["反方证据"]}, "call-finish")])
        output_tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(output_tool.name, {"summary": "已检查现有证据并记录缺口。", "stop_reason": "tools_unavailable", "counter_search_completed": False, "remaining_gaps": ["反方证据"]}, "call-output")])

    store = EvidenceStore(tmp_path / "tools.db")
    store.create_research_run("run-2", "pending", "2026-07-28T00:00:00Z", {"topic": "机器人", "sources": [], "time_range": "90d"})
    config = ModelConfig("deepseek", "https://api.deepseek.com", "deepseek-v4-flash", "deepseek-v4-pro", "test", 500)
    deps = ResearchAgentDeps(store, "run-2", 1, "agent-2", {"topic": "机器人", "sources": [], "time_range": "90d"}, {"theme_id": "robotics", "name": "机器人", "aliases": ["robotics"]}, AgentBudget())
    result = _build_research_agent(config, FunctionModel(model_function)).run_sync("研究机器人", deps=deps, usage_limits=UsageLimits(request_limit=6, tool_calls_limit=12))

    assert result.output.stop_reason == "tools_unavailable"
    assert calls == 3
    tool_calls = store.tool_calls("run-2")
    assert [item["tool_name"] for item in tool_calls] == ["query_existing_evidence", "finish_research"]
    assert all(item["status"] == "succeeded" for item in tool_calls)
    store.close()


def test_capability_status_never_exposes_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-for-output")
    status = capability_status()
    assert status["configured"] is True
    assert "api_key" not in status
    assert "not-for-output" not in str(status)


def test_capability_status_exposes_bounded_agent_concurrency_without_runtime_secrets(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-for-output")

    status = capability_status()

    assert status["concurrency"] == {
        "total_limit": 12,
        "lane_reservations": {"interactive": 10, "background": 2},
        "minimum_total": 2,
        "cooldown_seconds": 30,
        "pressure_status_codes": [429, 503],
    }
    assert "not-for-output" not in str(status["concurrency"])


def test_no_evidence_guard_is_audited_and_allows_counter_call(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "guard.db")
    store.create_research_run("guard-run", "collecting", "2026-07-29T00:00:00Z", {"topic": "AI", "sources": ["arxiv"]})
    deps = ResearchAgentDeps(
        store, "guard-run", 1, "guard-agent", {"topic": "AI", "sources": ["arxiv"]},
        {"theme_id": "ai-infrastructure", "name": "AI", "aliases": ["AI"]}, AgentBudget(),
        consecutive_no_evidence=2,
    )
    support_ctx = SimpleNamespace(deps=deps, tool_call_id="support-call", run_step=1)
    counter_ctx = SimpleNamespace(deps=deps, tool_call_id="counter-call", run_step=2)
    support = asyncio.run(_audited_tool(support_ctx, "collect_from_source", {"source": "arxiv", "purpose": "support"}, lambda: {"status": "unexpected"}))
    counter = asyncio.run(_audited_tool(counter_ctx, "collect_from_source", {"source": "arxiv", "purpose": "counter"}, lambda: {"status": "succeeded"}))
    calls = store.tool_calls("guard-run")
    assert support["status"] == "stopped_no_new_evidence"
    assert counter["status"] == "succeeded"
    assert [item["status"] for item in calls] == ["skipped", "succeeded"]
    store.close()


def test_unified_request_budget_records_finish_research_guardrail(tmp_path: Path, monkeypatch) -> None:
    class BudgetExhaustingAgent:
        def run_sync(self, *_args, **_kwargs):
            raise RuntimeError("The next request would exceed the request_limit of 6")

    config = ModelConfig("deepseek", "https://api.deepseek.com", "deepseek-v4-flash", "deepseek-v4-pro", "test", 500)
    monkeypatch.setattr(runtime_module, "model_config", lambda: config)
    monkeypatch.setattr(runtime_module, "_build_research_agent", lambda _config: BudgetExhaustingAgent())
    store = EvidenceStore(tmp_path / "budget.db")
    store.create_research_run(
        "budget-run", "robotics", "2026-07-31T00:00:00Z",
        {"topic": "robotics", "sources": [], "time_range": "multi_horizon", "output_type": "theme_report"},
        status="collecting", stage="collecting",
    )
    run = store.research_run("budget-run")
    assert run is not None

    result = run_research_agent(store, run, {"theme_id": "robotics", "name": "Robotics", "aliases": ["robotics"]})

    assert result["status"] == "succeeded"
    assert result["stop_reason"] == "budget_exhausted"
    assert result["usage"] == {"requests": 6, "tool_calls": 1}
    assert [item["tool_name"] for item in store.tool_calls("budget-run")] == ["finish_research"]
    audit = store.agent_runs("budget-run")[0]
    assert audit["status"] == "succeeded" and audit["model_requests"] == 6
    store.close()


def test_collection_audit_separates_raw_and_relevant_evidence(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "progress.db"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    store = EvidenceStore(database)
    store.create_research_run(
        "progress-run", "robotics", "2026-07-31T00:00:00Z",
        {"topic": "机器人", "sources": ["arxiv"]}, status="collecting", stage="collecting",
        database_path=str(database),
    )
    store.register_run("progress-run", str(database), "2026-07-31T00:00:00Z")
    deps = ResearchAgentDeps(
        store, "progress-run", 1, "progress-agent", {"topic": "机器人", "sources": ["arxiv"]},
        {"theme_id": "robotics", "name": "机器人", "aliases": ["robotics"]}, AgentBudget(),
    )
    context = SimpleNamespace(deps=deps, tool_call_id="progress-call", run_step=1)

    def action() -> dict:
        store.save_event(NormalizedEvent(
            "new-event", "fixture", "https://example.com/new", "academic", "Robotics evidence",
            "robotics deployment evidence", "2026-07-31", "2026-07-31T00:00:00Z", ("robotics",),
            origin_source_type="academic", publisher="example.com", publisher_domain="example.com",
            primary_or_secondary="primary", relevance_status="relevant", theme_assignment_status="assigned",
            primary_theme="robotics", classification_confidence=.9,
        ))
        store.commit()
        return {"status": "succeeded"}

    result = asyncio.run(_audited_tool(
        context, "collect_from_source", {"source": "arxiv", "purpose": "support"}, action
    ))
    assert result["evidence_delta"] == 1
    assert result["relevant_evidence_delta"] == 1
    store.close()
    snapshot = _research_run_snapshot("progress-run")
    assert snapshot["evidence_progress"] == {
        "baseline": 0, "current": 1, "raw_added": 1, "relevant_added": 1,
    }
