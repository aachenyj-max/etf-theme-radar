from __future__ import annotations

from pathlib import Path

from .store import EvidenceStore
from .theme_research import run_theme_research
from .etf_market import collect_market_snapshot, match_competitors, minimum_verified_etfs
from .etf_discovery import discover_global_etfs


def run_research_output(
    store: EvidenceStore, theme_id: str, output: Path, run_id: str, llm_config: dict | None,
    *, output_type: str, theme_name: str, aliases: list[str], approved_sources: list[str] | None = None,
) -> dict:
    discovered = {"candidates": [], "remaining_gaps": [], "status": "not_needed"}
    configured = match_competitors(theme_id, theme_name, aliases)
    if len(configured) < minimum_verified_etfs() and "etf_news" in set(approved_sources or []):
        discovered = discover_global_etfs(
            {"theme_id": theme_id, "name": theme_name, "aliases": aliases},
            llm_config or {},
        )
    result = run_theme_research(
        store, theme_id, output, run_id, llm_config,
        theme_name=theme_name, aliases=aliases,
        discovered_etfs=discovered.get("candidates") or [],
    )
    result["etf_discovery"] = discovered
    result["output_type"] = output_type
    landscape = (result.get("detail") or {}).get("landscape") or {}
    competitors = landscape.get("similar_etfs") or []
    if competitors and "etf_news" in set(approved_sources or []):
        landscape["market_snapshot"] = collect_market_snapshot(
            competitors, Path("data/cache/yahoo-etf-market")
        )
    else:
        landscape["market_snapshot"] = {
            "market_as_of": "", "status": "unknown", "products": [],
            "limitations": ["未获准使用 ETF 行情来源，市场指标保持未核验。"],
        }
    if output_type == "quick_scan":
        brief = result.get("brief") or {}
        gaps = ((result.get("detail") or {}).get("counter") or {}).get("missing_evidence") or []
        lines = [
            f"# {theme_name}｜快速扫描", "",
            f"- 已治理证据：{result.get('selected', 0)} 条；来源类型：{brief.get('source_types', 0)}。",
            f"- 当前状态：{result.get('status', 'WATCH')}；本输出仅作线索初筛。", "",
            "## 重点证据",
        ]
        for item in (brief.get("key_evidence") or [])[:3]:
            lines.append(f"- [{item['claim']}]({item['source_url']})（证据 ID：`{item['evidence_id']}`）")
        lines += ["", "## 证据缺口", *[f"- {gap}" for gap in gaps[:6]], "", "不得将快速扫描视为投资或 ETF 产品建议。"]
        result["report_markdown"] = "\n".join(lines)
        (output / f"{theme_id}-quick-scan.md").write_text(result["report_markdown"], encoding="utf-8")
    elif output_type == "etf_opportunity_analysis":
        investability = (result.get("detail") or {}).get("investability") or {}
        result["etf_opportunity"] = {
            "status": "requires_human_review" if landscape.get("overlap_status") == "available" and investability.get("investability_status") != "insufficient_data" else "insufficient_data",
            "competitor_count": landscape.get("competitor_count", 0),
            "official_holdings_covered": landscape.get("official_holdings_covered", []),
            "holdings_overlap": landscape.get("holdings_overlap", []),
            "investability_status": investability.get("investability_status", "insufficient_data"),
            "index_rules": "not_assessed", "liquidity": "not_assessed",
            "limitations": ["指数规则与流动性尚未完成官方逐项核验；不得据此启动产品。"],
        }
        result["report_markdown"] += "\n\n## ETF 机会分析附录\n" + f"- 竞品配置：{landscape.get('competitor_count', 0)} 只。\n- 官方持仓覆盖：{len(landscape.get('official_holdings_covered', []))} 只。\n- 机会状态：{result['etf_opportunity']['status']}。"
        (output / f"{theme_id}-etf-opportunity.md").write_text(result["report_markdown"], encoding="utf-8")
    return result
