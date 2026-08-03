"""Bounded, model-assisted discovery of globally listed ETF competitors."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelSettings, UsageLimits

from .official_connectors import AnySearchDiscoveryConnector


BLOCKED_DISCOVERY_DOMAINS = {
    "finance.yahoo.com", "google.com", "bing.com", "x.com", "twitter.com",
    "reddit.com", "seekingalpha.com",
}


class EtfCandidate(BaseModel):
    ticker: str
    yahoo_symbol: str
    fund_name: str
    issuer: str
    category: str
    exchange: str
    listing_market: str
    currency: str
    official_url: str
    discovery_url: str = ""
    relevance_reason: str


class EtfDiscoveryOutput(BaseModel):
    candidates: list[EtfCandidate] = Field(default_factory=list, max_length=12)
    remaining_gaps: list[str] = Field(default_factory=list, max_length=6)


class EtfSearchPlan(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=3)


def verify_etf_candidate(value: dict[str, Any]) -> dict[str, Any] | None:
    """Apply deterministic admission rules before a model candidate reaches a report."""
    try:
        candidate = EtfCandidate.model_validate(value)
    except Exception:
        return None
    ticker = candidate.ticker.strip().upper()
    yahoo_symbol = candidate.yahoo_symbol.strip().upper()
    currency = candidate.currency.strip().upper()
    official_url = candidate.official_url.strip()
    parsed = urlparse(official_url)
    domain = parsed.netloc.casefold().removeprefix("www.")
    if (
        not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,14}", ticker)
        or not re.fullmatch(r"[A-Z0-9][A-Z0-9.^=-]{0,20}", yahoo_symbol)
        or not re.fullmatch(r"[A-Z]{3}", currency)
        or parsed.scheme != "https"
        or not domain
        or domain in BLOCKED_DISCOVERY_DOMAINS
        or any(domain.endswith(f".{blocked}") for blocked in BLOCKED_DISCOVERY_DOMAINS)
        or not candidate.exchange.strip()
        or not candidate.listing_market.strip()
    ):
        return None
    return {
        "ticker": ticker,
        "yahoo_symbol": yahoo_symbol,
        "fund_name": candidate.fund_name.strip(),
        "issuer": candidate.issuer.strip(),
        "category": candidate.category.strip(),
        "exchange": candidate.exchange.strip(),
        "listing_market": candidate.listing_market.strip(),
        "currency": currency,
        "official_url": official_url,
        "holdings_url": official_url,
        "holdings_status": "待采集官方持仓",
        "discovery_url": candidate.discovery_url.strip(),
        "relevance_reason": candidate.relevance_reason.strip(),
        "verification_status": "official_url_verified",
        "verification_sources": [official_url],
        "discovery_method": "deepseek_tool_research",
    }


def _search_public_etf_sources(queries: list[str]) -> list[dict[str, str]]:
    connector = AnySearchDiscoveryConnector(
        Path("data/cache/anysearch-etf"),
        queries=[query[:200] for query in queries[:3] if query.strip()],
        enabled=True,
    )
    ids = connector.discover(date.today(), date.today())
    return [
        {
            "title": connector.records[item_id]["title"],
            "url": connector.records[item_id]["url"],
            "snippet": connector.records[item_id]["snippet"][:240],
        }
        for item_id in ids[:8]
    ]


def discover_global_etfs(
    definition: dict[str, Any],
    config: Any,
    *,
    searcher: Any = _search_public_etf_sources,
    model_override: Any = None,
) -> dict[str, Any]:
    """Let DeepSeek research missing ETF peers, while keeping admission deterministic."""
    configured = bool(config.get("api_key")) if isinstance(config, dict) else bool(getattr(config, "configured", False))
    if not configured and model_override is None:
        return {"candidates": [], "remaining_gaps": ["模型未配置，未执行动态 ETF 发现"], "status": "skipped"}

    if model_override is None:
        if isinstance(config, dict):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.deepseek import DeepSeekProvider
            from pydantic_ai.providers.openai import OpenAIProvider
            provider_name = str(config.get("provider") or "deepseek").casefold()
            provider = (
                DeepSeekProvider(api_key=config["api_key"])
                if provider_name == "deepseek"
                else OpenAIProvider(api_key=config["api_key"], base_url=config.get("base_url"))
            )
            model = OpenAIChatModel(str(config.get("model") or "deepseek-v4-pro"), provider=provider)
        else:
            # Imported lazily to avoid a module cycle with the main research agent.
            from .agent_runtime import _model
            model = _model(config, config.analysis_model)
    else:
        model = model_override
    max_output = config.get("max_output_tokens", 1600) if isinstance(config, dict) else getattr(config, "max_output_tokens", 1600)
    settings = ModelSettings(max_tokens=min(int(max_output), 1800), timeout=60)
    query_agent = Agent(
        model,
        output_type=EtfSearchPlan,
        model_settings=settings,
        instructions=(
            "你是 ETF 竞品调研规划代理。根据主题生成 1–3 个简洁的全球 ETF 公开搜索词，"
            "优先包含 official、issuer、exchange、ETF 和关键子赛道；不要回答候选结果。"
        ),
        retries=1,
    )
    prompt = {
        "theme": {
            "name": definition.get("name"),
            "description": definition.get("description"),
            "aliases": definition.get("aliases", []),
            "include_terms": definition.get("include_terms", []),
            "exclude_terms": definition.get("exclude_terms", []),
        },
        "instruction": "寻找与主题及其可投资子赛道直接相关的全球上市 ETF；最多返回 8 只，宁缺毋滥。",
    }
    try:
        plan = query_agent.run_sync(
            json.dumps(prompt, ensure_ascii=False),
            usage_limits=UsageLimits(request_limit=1, total_tokens_limit=5000),
        )
        search_results = searcher(plan.output.queries)
    except Exception as exc:
        return {"candidates": [], "remaining_gaps": [f"动态 ETF 查询规划或搜索失败：{str(exc)[:160]}"], "status": "failed"}
    if not search_results:
        return {"candidates": [], "remaining_gaps": ["公开搜索未返回可核验 ETF 页面"], "status": "insufficient_data"}

    discovered_urls = {str(item.get("url") or "").rstrip("/") for item in search_results}
    synthesis_agent = Agent(
        model,
        output_type=EtfDiscoveryOutput,
        model_settings=settings,
        instructions=(
            "你是 ETF 竞品核验代理。仅依据输入的公开搜索结果识别全球上市 ETF。"
            "候选必须给出搜索结果中出现的发行人或交易所 HTTPS 官方页、真实交易所、上市市场、"
            "交易币种及 Yahoo Finance symbol。聚合页、Yahoo、社交媒体不能作为 official_url。"
            "不要输出股票、ETN、共同基金或未上市产品；最多 8 只，宁缺毋滥。"
        ),
        retries=1,
    )
    try:
        result = synthesis_agent.run_sync(
            json.dumps({"theme": prompt["theme"], "search_results": search_results}, ensure_ascii=False),
            usage_limits=UsageLimits(request_limit=3, total_tokens_limit=11000),
        )
    except Exception as exc:
        return {"candidates": [], "remaining_gaps": [f"动态 ETF 结果综合失败：{str(exc)[:160]}"], "status": "failed"}

    admitted: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in result.output.candidates:
        candidate = verify_etf_candidate(raw.model_dump())
        if not candidate:
            continue
        if discovered_urls and candidate["official_url"].rstrip("/") not in discovered_urls:
            continue
        identity = (candidate["listing_market"].casefold(), candidate["ticker"])
        if identity not in seen:
            seen.add(identity)
            admitted.append(candidate)
    return {
        "candidates": admitted,
        "remaining_gaps": result.output.remaining_gaps,
        "status": "succeeded" if admitted else "insufficient_data",
    }
