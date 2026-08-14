"""Bounded, auditable LLM agents used inside the deterministic research workflow."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, ModelSettings, RunContext, UsageLimits
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider

from .browser_mcp import fetch_public_page
from .agent_goals import GoalConcurrencyPolicy
from .connector_factory import configured_connectors, load_project_env
from .governance import classify
from .models import NormalizedEvent, RawDocument, utcnow
from .official_connectors import AnySearchDiscoveryConnector
from .pipeline import ingest
from .store import EvidenceStore

PROMPT_VERSION = "agent-v1"
SOURCE_ALIASES = {
    "sec": "sec_edgar_etf",
    "arxiv": "openalex",
    "patents": "google_patents",
    "etf_holdings": "official_etf_holdings",
    "etf_news": "yahoo_etf_news",
    "company_careers": "public_job_boards",
    "sp_global": "sp_global_dji",
    "x": "anysearch_discovery",
    "forums": "anysearch_discovery",
}


def _numeric_config(section_name: str) -> dict[str, float]:
    result: dict[str, float] = {}
    section = ""
    path = Path(__file__).parents[1] / "config" / "defaults.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section = raw.strip()[:-1]
            continue
        if section == section_name and ":" in raw:
            key, value = raw.strip().split(":", 1)
            try:
                result[key] = float(value.strip())
            except ValueError:
                pass
    return result


AGENT_DEFAULTS = _numeric_config("agent_runtime")
EVIDENCE_DEFAULTS = _numeric_config("minimum_evidence")


class ThemeDefinitionOutput(BaseModel):
    name: str
    description: str
    aliases: list[str] = Field(min_length=1, max_length=8)
    include_terms: list[str] = Field(min_length=1, max_length=8)
    exclude_terms: list[str] = Field(default_factory=list, max_length=8)
    research_questions: list[str] = Field(min_length=3, max_length=6)


class ResearchAgentOutput(BaseModel):
    summary: str
    stop_reason: Literal["evidence_sufficient", "insufficient_evidence", "budget_exhausted", "tools_unavailable"]
    counter_search_completed: bool
    remaining_gaps: list[str] = Field(default_factory=list, max_length=8)


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    base_url: str
    agent_model: str
    analysis_model: str
    api_key: str
    max_output_tokens: int

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class AgentBudget:
    max_tool_calls: int = 12
    max_model_requests: int = 6
    max_seconds: int = 480
    max_total_tokens: int = 24_000
    max_cost_usd: float = 0.50
    estimated_cost_per_million_tokens: float = 2.0
    tool_calls: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)

    def consume_tool(self) -> None:
        if self.tool_calls >= self.max_tool_calls or time.monotonic() - self.started_monotonic >= self.max_seconds:
            raise RuntimeError("Agent 工具预算已耗尽")
        self.tool_calls += 1

    @property
    def token_limit(self) -> int:
        cost_tokens = int(self.max_cost_usd * 1_000_000 / max(self.estimated_cost_per_million_tokens, .000001))
        return min(self.max_total_tokens, cost_tokens)


@dataclass
class ResearchAgentDeps:
    store: EvidenceStore
    run_id: str
    attempt: int
    agent_run_id: str
    request: dict[str, Any]
    definition: dict[str, Any]
    budget: AgentBudget
    failures: dict[str, int] = field(default_factory=dict)
    counter_search_completed: bool = False
    requested_stop_reason: str = ""
    consecutive_no_evidence: int = 0


def model_config() -> ModelConfig:
    load_project_env()
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().casefold()
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    default_base = "https://api.deepseek.com" if provider == "deepseek" else "https://api.openai.com/v1"
    return ModelConfig(
        provider=provider,
        base_url=os.getenv("LLM_BASE_URL", default_base),
        agent_model=os.getenv("LLM_AGENT_MODEL", os.getenv("LLM_MODEL", "deepseek-v4-flash")),
        analysis_model=os.getenv("LLM_ANALYSIS_MODEL", "deepseek-v4-pro"),
        api_key=key,
        max_output_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1600")),
    )


def prompt_text(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def prompt_hash(name: str) -> str:
    return hashlib.sha256(prompt_text(name).encode("utf-8")).hexdigest()


def _model(config: ModelConfig, model_name: str) -> OpenAIChatModel:
    if config.provider == "deepseek":
        provider = DeepSeekProvider(api_key=config.api_key)
    else:
        provider = OpenAIProvider(api_key=config.api_key, base_url=config.base_url)
    return OpenAIChatModel(model_name, provider=provider)


def _settings(config: ModelConfig, *, thinking: bool = True) -> ModelSettings:
    extra_body: dict[str, object] = {}
    if config.provider == "deepseek":
        extra_body["thinking"] = {"type": "enabled" if thinking else "disabled"}
    return ModelSettings(max_tokens=config.max_output_tokens, timeout=60, extra_body=extra_body)


def generate_theme_definition(topic: str, objective: str) -> dict[str, Any] | None:
    config = model_config()
    if not config.configured:
        return None
    agent = Agent(
        _model(config, config.analysis_model),
        output_type=ThemeDefinitionOutput,
        instructions=prompt_text("theme_definition"),
        model_settings=_settings(config),
        retries=1,
    )
    try:
        result = agent.run_sync(
            json.dumps({"topic": topic, "objective": objective}, ensure_ascii=False),
            usage_limits=UsageLimits(request_limit=3, output_tokens_limit=config.max_output_tokens * 2),
        )
        return result.output.model_dump()
    except Exception:
        return None


def _date_window(request: dict[str, Any]) -> tuple[date, date]:
    until = date.today()
    custom = request.get("custom_date_range") or {}
    if request.get("time_range") == "custom" and custom.get("from") and custom.get("to"):
        return date.fromisoformat(custom["from"]), date.fromisoformat(custom["to"])
    days = {"30d": 30, "90d": 90, "1y": 365}.get(request.get("time_range"), 90)
    return until - timedelta(days=days), until


def evidence_coverage(store: EvidenceStore, definition: dict[str, Any]) -> dict[str, Any]:
    keys = {str(definition.get("theme_id", "")).casefold(), str(definition.get("name", "")).casefold()}
    keys.update(str(item).casefold() for item in definition.get("aliases", []))
    matched = []
    for event in store.events():
        searchable = f"{event.get('primary_theme', '')} {event.get('title', '')} {event.get('summary', '')}".casefold()
        if any(key and key in searchable for key in keys):
            matched.append(event)
    source_types = {str(item.get("origin_source_type") or item.get("source_type")) for item in matched}
    publishers = {str(item.get("publisher")) for item in matched if item.get("publisher")}
    first_party = sum(item.get("primary_or_secondary") == "primary" for item in matched)
    return {
        "evidence": len(matched),
        "independent_source_types": len(source_types),
        "publishers": len(publishers),
        "first_party": first_party,
        "minimum_met": len(source_types) >= int(EVIDENCE_DEFAULTS.get("independent_source_types", 3)) and first_party >= int(EVIDENCE_DEFAULTS.get("official_sources", 1)),
    }


async def _audited_tool(ctx: RunContext[ResearchAgentDeps], name: str, arguments: dict[str, Any], action) -> dict[str, Any]:
    deps = ctx.deps
    deps.budget.consume_tool()
    collection_tools = {"collect_from_source", "search_public_web", "browse_public_page"}
    no_evidence_limit = int(AGENT_DEFAULTS.get("consecutive_no_evidence_limit", 2))
    stable_external = name in collection_tools
    call_uid = hashlib.sha256(f"{deps.run_id}:{deps.attempt}:{name}:{json.dumps(arguments, sort_keys=True)}".encode()).hexdigest()[:24] if stable_external else (ctx.tool_call_id or hashlib.sha256(f"{deps.agent_run_id}:{ctx.run_step}:{name}:{json.dumps(arguments, sort_keys=True)}".encode()).hexdigest()[:24])
    existing = deps.store.tool_call_by_uid(deps.run_id, call_uid)
    if existing and existing["status"] in {"succeeded", "denied", "unavailable", "disabled", "degraded"}:
        return {**existing["result"], "idempotent_replay": True}
    started_at = utcnow()
    started = time.monotonic()
    call_id = deps.store.start_tool_call(
        run_id=deps.run_id,
        attempt=deps.attempt,
        call_uid=call_uid,
        agent_run_id=deps.agent_run_id,
        round_number=ctx.run_step,
        tool_name=name,
        started_at=started_at,
        arguments=arguments,
    )
    counter_call = arguments.get("purpose") == "counter" or arguments.get("counter_evidence") is True
    if name in collection_tools and deps.consecutive_no_evidence >= no_evidence_limit and not counter_call:
        result = {
            "status": "stopped_no_new_evidence",
            "tool": name,
            "instruction": "尚未反方检查时先执行一次 counter 调用；随后调用 summarize_evidence_gap 和 finish_research",
            "counter_search_completed": deps.counter_search_completed,
        }
        deps.store.finish_tool_call(call_id, status="skipped", finished_at=utcnow(), result=result, latency_ms=int((time.monotonic() - started) * 1000))
        return result
    if deps.failures.get(name, 0) >= 2:
        result = {"status": "disabled_after_failures", "tool": name}
        deps.store.finish_tool_call(call_id, status="skipped", finished_at=utcnow(), result=result, latency_ms=int((time.monotonic() - started) * 1000))
        return result
    before = len(deps.store.events())
    coverage_before = evidence_coverage(deps.store, deps.definition) if name in collection_tools else {}
    last_error = ""
    retries = 0
    for retries in range(3):
        try:
            result = action()
            if inspect.isawaitable(result):
                result = await result
            delta = max(0, len(deps.store.events()) - before)
            coverage_after = evidence_coverage(deps.store, deps.definition) if name in collection_tools else {}
            relevant_delta = max(
                0, int(coverage_after.get("evidence", 0)) - int(coverage_before.get("evidence", 0))
            )
            if name in collection_tools:
                deps.consecutive_no_evidence = 0 if delta else deps.consecutive_no_evidence + 1
            result_status = str(result.get("status", "succeeded")) if isinstance(result, dict) else "succeeded"
            audit_status = result_status if result_status in {"denied", "unavailable", "disabled", "failed", "degraded"} else "succeeded"
            deps.store.finish_tool_call(
                call_id, status=audit_status, finished_at=utcnow(), result=result, retry_count=retries,
                latency_ms=int((time.monotonic() - started) * 1000), evidence_delta=delta,
                relevant_evidence_delta=relevant_delta, coverage_before=coverage_before,
                coverage_after=coverage_after,
            )
            return {
                **result, "evidence_delta": delta, "relevant_evidence_delta": relevant_delta,
                "coverage_before": coverage_before, "coverage_after": coverage_after,
            }
        except Exception as exc:
            last_error = str(exc)
            if retries < 2:
                await asyncio.sleep(2**retries)
    deps.failures[name] = deps.failures.get(name, 0) + 1
    lowered = last_error.casefold()
    category = (
        "rate_limited" if "429" in lowered or "rate limit" in lowered else
        "timeout" if "timeout" in lowered or "timed out" in lowered else
        "forbidden" if "403" in lowered or "forbidden" in lowered else
        "upstream_5xx" if any(code in lowered for code in ("500", "502", "503", "504")) else
        "parse_error" if any(token in lowered for token in ("parse", "json", "decode")) else
        "unexpected_error"
    )
    result = {"status": "failed", "tool": name, "error": last_error, "failure_category": category, "degraded": True}
    deps.store.finish_tool_call(call_id, status="failed", finished_at=utcnow(), error=last_error, result=result, retry_count=retries, latency_ms=int((time.monotonic() - started) * 1000))
    return result


def _build_research_agent(config: ModelConfig, model_override: Any = None) -> Agent[ResearchAgentDeps, ResearchAgentOutput]:
    agent: Agent[ResearchAgentDeps, ResearchAgentOutput] = Agent(
        model_override or _model(config, config.agent_model),
        deps_type=ResearchAgentDeps,
        output_type=ResearchAgentOutput,
        instructions=prompt_text("research_agent"),
        model_settings=_settings(config),
        retries=1,
        tool_timeout=90,
    )

    @agent.tool
    async def query_existing_evidence(ctx: RunContext[ResearchAgentDeps], limit: int = 12) -> dict[str, Any]:
        """Inspect existing evidence and deterministic coverage for the approved theme."""
        limit = max(1, min(limit, 20))
        return await _audited_tool(ctx, "query_existing_evidence", {"limit": limit}, lambda: {
            "status": "succeeded",
            "coverage": evidence_coverage(ctx.deps.store, ctx.deps.definition),
            "items": [{"evidence_id": item["event_id"], "title": item["title"], "source_type": item.get("origin_source_type"), "publisher": item.get("publisher"), "url": item.get("source_url")} for item in ctx.deps.store.events()[:limit]],
        })

    @agent.tool
    async def inspect_source_health(ctx: RunContext[ResearchAgentDeps]) -> dict[str, Any]:
        """Return availability of the configured public data connectors."""
        def action() -> dict[str, Any]:
            health = [connector.healthcheck().__dict__ for connector in configured_connectors(Path("data/cache"))]
            return {"status": "succeeded", "sources": health}
        return await _audited_tool(ctx, "inspect_source_health", {}, action)

    @agent.tool
    async def collect_from_source(ctx: RunContext[ResearchAgentDeps], source: Literal["sec", "arxiv", "patents", "etf_holdings", "etf_news", "company_careers", "sp_global"], purpose: Literal["support", "counter"] = "support") -> dict[str, Any]:
        """Collect from one user-approved authoritative connector for the requested date window."""
        def action() -> dict[str, Any]:
            if source not in ctx.deps.request.get("sources", []):
                return {"status": "denied", "reason": "source_not_approved"}
            target = SOURCE_ALIASES[source]
            connector = next((item for item in configured_connectors(Path("data/cache")) if item.source_name == target), None)
            if connector is None:
                return {"status": "unavailable", "source": source}
            if source == "patents":
                terms = [ctx.deps.definition.get("name", ""), *ctx.deps.definition.get("aliases", [])]
                connector.queries = [f"site:patents.google.com/patent {term}" for term in terms if str(term).strip()][:5]
            since, until = _date_window(ctx.deps.request)
            result = ingest(connector, ctx.deps.store, since, until)
            if purpose == "counter":
                ctx.deps.counter_search_completed = True
            return result
        return await _audited_tool(ctx, "collect_from_source", {"source": source, "purpose": purpose}, action)

    @agent.tool
    async def search_public_web(ctx: RunContext[ResearchAgentDeps], query: str, counter_evidence: bool = False) -> dict[str, Any]:
        """Search public web sources for discovery; results are leads requiring corroboration."""
        query = query.strip()[:240]
        def action() -> dict[str, Any]:
            if not ({"x", "forums"} & set(ctx.deps.request.get("sources", []))):
                return {"status": "denied", "reason": "public_search_not_approved"}
            connector = AnySearchDiscoveryConnector(Path("data/cache/anysearch"), queries=[query], enabled=True)
            since, until = _date_window(ctx.deps.request)
            result = ingest(connector, ctx.deps.store, since, until)
            if counter_evidence:
                ctx.deps.counter_search_completed = True
            return result
        return await _audited_tool(ctx, "search_public_web", {"query": query, "counter_evidence": counter_evidence}, action)

    @agent.tool
    async def browse_public_page(ctx: RunContext[ResearchAgentDeps], url: str) -> dict[str, Any]:
        """Read one explicit public HTTP(S) page through Playwright MCP and save it as a low-trust lead."""
        async def action() -> dict[str, Any]:
            if os.getenv("PLAYWRIGHT_MCP_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
                return {"status": "disabled", "reason": "playwright_mcp_disabled"}
            page = await fetch_public_page(url)
            final_url = page["url"]
            raw = RawDocument(source="playwright_mcp", source_url=final_url, title=f"Public browser evidence: {final_url}", text=page["text"], source_type="social", access_note="public-playwright-mcp-untrusted-sanitized")
            ctx.deps.store.save_raw(raw)
            event = NormalizedEvent(event_id=f"playwright:{raw.content_hash[:24]}", source="playwright_mcp", source_url=final_url, source_type="social", title=raw.title, summary=page["text"][:1000], observed_at=utcnow(), themes=(ctx.deps.definition["theme_id"],), raw_content_hash=raw.content_hash, extraction_confidence=.5)
            ctx.deps.store.save_event(classify(event, raw.text))
            ctx.deps.store.commit()
            return {"status": "succeeded", "url": final_url, "requested_url": url, "content_length": page["content_length"], "removed_instruction_lines": page.get("removed_instruction_lines", 0)}
        return await _audited_tool(ctx, "browse_public_page", {"url": url}, action)

    @agent.tool
    async def summarize_evidence_gap(ctx: RunContext[ResearchAgentDeps]) -> dict[str, Any]:
        """Get deterministic evidence coverage and minimum-threshold status."""
        return await _audited_tool(ctx, "summarize_evidence_gap", {}, lambda: {
            "status": "succeeded",
            "coverage": evidence_coverage(ctx.deps.store, ctx.deps.definition),
            "counter_search_completed": ctx.deps.counter_search_completed,
            "required_next_action": "finish_research" if ctx.deps.counter_search_completed else "先执行一次 purpose='counter' 或 counter_evidence=true 的反方检查，再调用 finish_research",
        })

    @agent.tool
    async def finish_research(ctx: RunContext[ResearchAgentDeps], stop_reason: Literal["evidence_sufficient", "insufficient_evidence", "budget_exhausted", "tools_unavailable"], remaining_gaps: list[str]) -> dict[str, Any]:
        """Declare why the bounded research loop should stop after checking the evidence gap."""
        def action() -> dict[str, Any]:
            if stop_reason in {"evidence_sufficient", "insufficient_evidence"} and not ctx.deps.counter_search_completed:
                return {"status": "denied", "reason": "counter_search_required", "instruction": "先用 collect_from_source(purpose='counter') 或 search_public_web(counter_evidence=true) 执行反方检查"}
            ctx.deps.requested_stop_reason = stop_reason
            return {"status": "accepted", "stop_reason": stop_reason, "remaining_gaps": remaining_gaps[:8], "coverage": evidence_coverage(ctx.deps.store, ctx.deps.definition)}
        return await _audited_tool(ctx, "finish_research", {"stop_reason": stop_reason, "remaining_gaps": remaining_gaps[:8]}, action)

    @agent.output_validator
    def require_counter_search(ctx: RunContext[ResearchAgentDeps], output: ResearchAgentOutput) -> ResearchAgentOutput:
        if output.stop_reason in {"evidence_sufficient", "insufficient_evidence"} and not ctx.deps.counter_search_completed:
            raise ModelRetry("结束前必须执行一次 purpose='counter' 的权威来源采集或 counter_evidence=true 的公开搜索；若工具均不可用，使用 tools_unavailable。")
        if not ctx.deps.requested_stop_reason:
            raise ModelRetry("最终结构化输出前必须先调用 finish_research。")
        return output

    return agent


def run_research_agent(store: EvidenceStore, run: dict[str, Any], definition: dict[str, Any]) -> dict[str, Any]:
    config = model_config()
    agent_run_id = str(uuid4())
    default_tools = int(AGENT_DEFAULTS.get("max_tool_calls", 12))
    default_requests = int(AGENT_DEFAULTS.get("max_model_requests", 6))
    default_seconds = int(AGENT_DEFAULTS.get("max_seconds", 480))
    budget = AgentBudget(
        max_tool_calls=min(default_tools, int(os.getenv("AGENT_MAX_TOOL_CALLS", str(default_tools)))),
        max_model_requests=min(default_requests, int(os.getenv("AGENT_MAX_MODEL_REQUESTS", str(default_requests)))),
        max_seconds=min(default_seconds, int(os.getenv("AGENT_MAX_SECONDS", str(default_seconds)))),
        max_total_tokens=int(os.getenv("AGENT_MAX_TOTAL_TOKENS", str(int(AGENT_DEFAULTS.get("max_total_tokens", 24000))))),
        max_cost_usd=float(os.getenv("AGENT_MAX_COST_USD", str(AGENT_DEFAULTS.get("max_cost_usd", .5)))),
        estimated_cost_per_million_tokens=float(os.getenv("LLM_ESTIMATED_COST_PER_MILLION_TOKENS", str(AGENT_DEFAULTS.get("estimated_cost_per_million_tokens", 2.0)))),
    )
    base = {
        "agent_run_id": agent_run_id,
        "run_id": run["run_id"],
        "attempt": run["attempt"],
        "stage": "collecting",
        "provider": config.provider,
        "model": config.agent_model,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash("research_agent"),
        "started_at": utcnow(),
    }
    planning = {
        "questions": definition.get("research_questions", []),
        "approved_sources": run["request"].get("sources", []),
        "profile": "unified_theme_research",
        "source_priority": ["existing_cache", "official_etf_holdings", "tiantian", "yfinance", "sec", "arxiv", "company_careers", "patents_if_needed", "counter_search"],
        "limits": {"seconds": budget.max_seconds, "tool_calls": budget.max_tool_calls, "model_requests": budget.max_model_requests},
    }
    store.save_step(run["run_id"], run["attempt"], "query_planning", "succeeded", started_at=utcnow(), finished_at=utcnow(), details=planning)
    initial_coverage = evidence_coverage(store, definition)
    store.save_step(run["run_id"], run["attempt"], "evidence_gap_analysis", "succeeded", started_at=utcnow(), finished_at=utcnow(), details=initial_coverage)
    if not config.configured:
        store.create_agent_run({**base, "status": "skipped", "stop_reason": "model_not_configured", "finished_at": utcnow()})
        store.save_step(run["run_id"], run["attempt"], "counter_search", "skipped", started_at=utcnow(), finished_at=utcnow(), details={"reason": "model_not_configured"})
        call_id = store.start_tool_call(run_id=run["run_id"], attempt=run["attempt"], call_uid=f"{run['run_id']}:{run['attempt']}:finish_research", agent_run_id=agent_run_id, round_number=0, tool_name="finish_research", started_at=utcnow(), arguments={"stop_reason": "tools_unavailable", "remaining_gaps": ["模型未配置，未执行反方检索"]})
        store.finish_tool_call(call_id, status="succeeded", finished_at=utcnow(), result={"status": "accepted", "stop_reason": "tools_unavailable"})
        store.save_step(run["run_id"], run["attempt"], "synthesis", "succeeded", started_at=utcnow(), finished_at=utcnow(), details={"fallback": "deterministic", "remaining_gaps": ["模型未配置"]})
        return {"enabled": False, "status": "skipped", "stop_reason": "model_not_configured", "counter_search_completed": False, "coverage": initial_coverage}
    store.close_interrupted_agent_runs(run["run_id"], utcnow())
    store.create_agent_run({**base, "status": "running"})
    deps = ResearchAgentDeps(store, run["run_id"], run["attempt"], agent_run_id, run["request"], definition, budget)
    prompt = json.dumps({
        "theme_definition": definition,
        "request": run["request"],
        "current_coverage": evidence_coverage(store, definition),
        "runtime_profile": planning,
        "execution_instruction": "先复用现有证据与 ETF 缓存，再按产业动量和 ETF 格局缺口采集；必须完成一次反方检查，并在统一预算内调用 finish_research。",
    }, ensure_ascii=False)
    try:
        result = _build_research_agent(config).run_sync(
            prompt,
            deps=deps,
            conversation_id=agent_run_id,
            # OpenAIChatModel-compatible providers (including DeepSeek) cannot
            # pre-count request tokens. PydanticAI still enforces request/tool
            # limits and records provider-reported usage after every response.
            usage_limits=UsageLimits(request_limit=budget.max_model_requests, tool_calls_limit=budget.max_tool_calls, total_tokens_limit=budget.token_limit),
        )
        usage = result.usage()
        stop_reason = deps.requested_stop_reason or result.output.stop_reason
        store.finish_agent_run(agent_run_id, status="succeeded", stop_reason=stop_reason, model_requests=usage.requests, tool_calls=budget.tool_calls, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, finished_at=utcnow())
        store.save_step(run["run_id"], run["attempt"], "counter_search", "succeeded" if deps.counter_search_completed else "skipped", started_at=base["started_at"], finished_at=utcnow(), details={"completed": deps.counter_search_completed})
        store.save_step(run["run_id"], run["attempt"], "synthesis", "succeeded", started_at=base["started_at"], finished_at=utcnow(), details={"stop_reason": stop_reason, "remaining_gaps": result.output.remaining_gaps})
        return {"enabled": True, "status": "succeeded", **result.output.model_dump(), "stop_reason": stop_reason, "counter_search_completed": deps.counter_search_completed, "coverage": evidence_coverage(store, definition), "usage": {"requests": usage.requests, "tool_calls": budget.tool_calls, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}}
    except Exception as exc:
        message = str(exc)
        budget_boundary = "exceed" in message.casefold() and any(
            token in message.casefold()
            for token in ("request_limit", "tool_calls_limit", "total_tokens_limit")
        )
        if budget_boundary:
            current_calls = [item for item in store.tool_calls(run["run_id"]) if int(item.get("attempt") or 0) == int(run["attempt"])]
            counter_attempted = deps.counter_search_completed or any(
                item.get("arguments", {}).get("purpose") == "counter" or item.get("arguments", {}).get("counter_evidence") is True
                for item in current_calls
            )
            remaining_gaps = [] if deps.counter_search_completed else ["反方检索未取得可用证据"]
            if not any(item["tool_name"] == "finish_research" for item in current_calls):
                call_id = store.start_tool_call(
                    run_id=run["run_id"], attempt=run["attempt"],
                    call_uid=f"{run['run_id']}:{run['attempt']}:finish_research:budget",
                    agent_run_id=agent_run_id, round_number=budget.max_model_requests,
                    tool_name="finish_research", started_at=utcnow(),
                    arguments={"stop_reason": "budget_exhausted", "remaining_gaps": remaining_gaps},
                )
                store.finish_tool_call(
                    call_id, status="succeeded", finished_at=utcnow(),
                    result={"status": "accepted", "stop_reason": "budget_exhausted", "remaining_gaps": remaining_gaps, "deterministic_guardrail": True},
                )
            audited_tool_count = min(budget.max_tool_calls, len(current_calls) + 1)
            store.finish_agent_run(
                agent_run_id, status="succeeded", stop_reason="budget_exhausted",
                model_requests=budget.max_model_requests, tool_calls=audited_tool_count,
                finished_at=utcnow(), error="",
            )
            store.save_step(
                run["run_id"], run["attempt"], "counter_search",
                "succeeded" if deps.counter_search_completed else "attempted" if counter_attempted else "skipped",
                started_at=base["started_at"], finished_at=utcnow(),
                details={"completed": deps.counter_search_completed, "attempted": counter_attempted, "budget_exhausted": True},
            )
            store.save_step(
                run["run_id"], run["attempt"], "synthesis", "succeeded",
                started_at=base["started_at"], finished_at=utcnow(),
                details={"stop_reason": "budget_exhausted", "remaining_gaps": remaining_gaps, "fallback": "deterministic_guardrail"},
            )
            return {
                "enabled": True, "status": "succeeded", "summary": "已在统一主题研究预算边界停止，并保留未满足的证据缺口。",
                "stop_reason": "budget_exhausted", "counter_search_completed": deps.counter_search_completed,
                "counter_search_attempted": counter_attempted, "remaining_gaps": remaining_gaps,
                "coverage": evidence_coverage(store, definition),
                "usage": {"requests": budget.max_model_requests, "tool_calls": audited_tool_count},
            }
        configuration_error = any(token in message.casefold() for token in ("401", "authentication", "api key", "model not found", "404"))
        status = "blocked_configuration" if configuration_error else "degraded"
        stop_reason = "configuration_error" if configuration_error else "agent_failed"
        store.finish_agent_run(agent_run_id, status=status, stop_reason=stop_reason, tool_calls=budget.tool_calls, finished_at=utcnow(), error=message)
        store.save_step(run["run_id"], run["attempt"], "counter_search", "succeeded" if deps.counter_search_completed else "failed", started_at=base["started_at"], finished_at=utcnow(), error=message, details={"completed": deps.counter_search_completed})
        store.save_step(run["run_id"], run["attempt"], "synthesis", "failed", started_at=base["started_at"], finished_at=utcnow(), error=message, details={"fallback": "deterministic"})
        return {"enabled": True, "status": status, "stop_reason": stop_reason, "error": message, "coverage": evidence_coverage(store, definition)}


def analysis_llm_config() -> dict[str, str] | None:
    config = model_config()
    if not config.configured:
        return None
    return {
        "api_key": config.api_key,
        "base_url": config.base_url,
        "model": config.analysis_model,
        "provider": config.provider,
        "max_output_tokens": str(config.max_output_tokens),
    }


def capability_status() -> dict[str, Any]:
    config = model_config()
    concurrency = GoalConcurrencyPolicy.from_defaults()
    return {
        "configured": config.configured,
        "provider": config.provider,
        "agent_model": config.agent_model,
        "analysis_model": config.analysis_model,
        "framework": "pydantic-ai",
        "autonomy": "stage_bounded",
        "concurrency": {
            "total_limit": concurrency.total_limit,
            "lane_reservations": {
                "interactive": concurrency.interactive_reserved,
                "background": concurrency.background_reserved,
            },
            "minimum_total": concurrency.minimum_total,
            "cooldown_seconds": concurrency.cooldown_seconds,
            "pressure_status_codes": [429, 503],
        },
        "tools": ["query_existing_evidence", "inspect_source_health", "collect_from_source", "search_public_web", "browse_public_page", "discover_global_etfs", "summarize_evidence_gap", "finish_research"],
    }
