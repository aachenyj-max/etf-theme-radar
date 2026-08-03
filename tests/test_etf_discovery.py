from types import SimpleNamespace

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from etf_theme_radar.etf_discovery import discover_global_etfs


def test_deepseek_discovery_calls_search_tool_and_admits_official_result() -> None:
    calls = 0

    def model_function(messages, info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        output_tool = info.output_tools[0]
        if calls == 1:
            return ModelResponse(parts=[ToolCallPart(
                output_tool.name,
                {"queries": ["nuclear energy ETF official issuer"]},
                "plan-output",
            )])
        return ModelResponse(parts=[ToolCallPart(output_tool.name, {
            "candidates": [{
                "ticker": "URA",
                "yahoo_symbol": "URA",
                "fund_name": "Global X Uranium ETF",
                "issuer": "Global X",
                "category": "铀产业链",
                "exchange": "NYSE Arca",
                "listing_market": "United States",
                "currency": "USD",
                "official_url": "https://www.globalxetfs.com/funds/ura",
                "discovery_url": "https://www.globalxetfs.com/funds/ura",
                "relevance_reason": "覆盖核燃料供应链",
            }],
            "remaining_gaps": ["尚未核验完整持仓"],
        }, "output-call")])

    result = discover_global_etfs(
        {"name": "核能新兴主题", "aliases": ["SMR", "铀供应链"]},
        SimpleNamespace(configured=True, max_output_tokens=1000),
        searcher=lambda _queries: [{
            "title": "Global X Uranium ETF",
            "url": "https://www.globalxetfs.com/funds/ura",
            "snippet": "Official fund page",
        }],
        model_override=FunctionModel(model_function),
    )

    assert calls == 2
    assert result["status"] == "succeeded"
    assert result["candidates"][0]["ticker"] == "URA"
    assert result["candidates"][0]["discovery_method"] == "deepseek_tool_research"
