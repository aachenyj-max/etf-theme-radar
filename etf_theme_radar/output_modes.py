from __future__ import annotations

from pathlib import Path

from .store import EvidenceStore
from .theme_research import _publication_gate, run_theme_research
from .etf_market import collect_dual_source_market_snapshot, match_competitors, minimum_verified_etfs
from .etf_discovery import discover_global_etfs
from .etf_preview import match_theme_preview_products


def run_research_output(
    store: EvidenceStore, theme_id: str, output: Path, run_id: str, llm_config: dict | None,
    *, output_type: str, theme_name: str, aliases: list[str], approved_sources: list[str] | None = None,
) -> dict:
    if output_type != "theme_report":
        raise ValueError("当前仅支持统一主题研究输出")
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
    landscape["theme_etf_snapshot"] = match_theme_preview_products(
        store.latest_etf_preview_snapshot(), theme_id, theme_name, aliases,
    )
    competitors = landscape.get("similar_etfs") or []
    if competitors and "etf_news" in set(approved_sources or []):
        landscape["market_snapshot"] = collect_dual_source_market_snapshot(
            competitors, landscape["theme_etf_snapshot"], Path("data/cache/yahoo-etf-market"),
            fetcher=lambda _symbol: (_ for _ in ()).throw(
                RuntimeError("报告生成仅复用成功缓存；实时行情由独立手动刷新 Worker 获取")
            ),
        )
    else:
        landscape["market_snapshot"] = {
            "market_as_of": "", "status": "unknown", "products": [],
            "limitations": ["未获准使用 ETF 行情来源，市场指标保持未核验。"],
        }
    sections = result.get("report_sections") or {}
    etf_angle = sections.get("etf_investment_angle") or {}
    etf_angle["products"] = list((landscape.get("market_snapshot") or {}).get("products") or [])
    etf_angle["no_suitable_etf"] = not bool(etf_angle["products"])
    sections["etf_investment_angle"] = etf_angle
    result["report_sections"] = sections
    preview = landscape["theme_etf_snapshot"]
    preview_lines = [
        "", "## 主题相关 ETF 现状（冻结快照）",
        f"- 快照日期：{preview.get('market_as_of') or '未核验'}；匹配产品：{preview.get('matched_count', 0)} 只。",
    ]
    for product in (preview.get("products") or [])[:10]:
        preview_lines.append(
            f"- {product.get('code')} · {product.get('name')}；规模 {product.get('scale_billion') if product.get('scale_billion') is not None else '未核验'} 亿元；近一年 {product.get('rolling_1y') if product.get('rolling_1y') is not None else '未核验'}%。"
        )
    preview_lines.append("- 仅按主题名称、别名及跟踪指数做确定性关联；未核验持仓时不推断实际主题暴露，也不构成投资建议。")
    result["report_markdown"] = str(result.get("report_markdown") or "") + "\n".join(preview_lines)
    audit = result.get("audit") or {}
    previous_gate = audit.get("publication_gate") or {}
    base_errors = [
        item for item in audit.get("errors") or []
        if item not in set(previous_gate.get("failed_checks") or [])
    ]
    publication_gate = _publication_gate(result)
    audit["publication_gate"] = publication_gate
    audit["errors"] = [*base_errors, *publication_gate["failed_checks"]]
    audit["passed"] = not audit["errors"]
    result["audit"] = audit
    return result
