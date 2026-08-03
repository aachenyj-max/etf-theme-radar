"""On-demand company/event deep dives with a strict fact, inference, and verification boundary."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .theme_research import _llm_evidence_analysis


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _original_source(event: dict) -> dict:
    return {
        "source_id": "discovery-source",
        "tier": "secondary",
        "verification_status": "unverified",
        "publisher": event.get("publisher"),
        "url": event["source_url"],
        "title": event["title"],
        "note": "该来源用于发现事件；其叙述不自动升级为一级事实。",
    }


def _verified_fact_pack(events: list[dict], target: dict) -> tuple[list[dict], list[dict]]:
    authoritative = {"official", "sec_filing", "academic", "patent", "etf"}
    target_company = target.get("company_id") or target.get("publisher")
    candidates = []
    for event in events:
        source_type = event.get("origin_source_type") or event.get("source_type")
        same_subject = bool(target_company and (event.get("company_id") or event.get("publisher")) == target_company)
        if event["event_id"] != target["event_id"] and same_subject and event.get("source_url") and event.get("primary_or_secondary") == "primary" and source_type in authoritative:
            candidates.append(event)
    sources=[]; facts=[]
    for index,event in enumerate(candidates[:12],1):
        source_id=f"primary-{index}"
        sources.append({"source_id":source_id,"tier":"primary","verification_status":"verified","publisher":event.get("publisher") or event.get("source"),"url":event["source_url"],"title":event["title"],"note":"独立权威来源；事实仅限其标准化标题与摘要。"})
        facts.append({"fact_id":f"f{index}","statement":event.get("summary") or event["title"],"source_id":source_id,"url":event["source_url"],"status":"verified"})
    return sources,facts


def _fallback_analysis(facts: list[dict]) -> dict:
    coverage = f"当前有 {len(facts)} 条一级事实可用于交叉核验。" if facts else "当前没有一级事实可用于交叉核验。"
    return {
        "strategic_change": f"该事件可能反映公司或产业活动发生变化。{coverage} 在缺少独立一级来源时，不将发现页叙述升级为公司事实。",
        "economic_mechanism": "只有当公开材料明确披露合同主体、客户、交付、价格或收入机制时，才能建立经济机制；当前未披露部分保持 unknown。",
        "commercialization": "商业化应由订单、交付、验收、收入确认或客户侧独立材料支持，公告、招聘或讨论本身不足以证明规模化采用。",
        "risk": "来源集中、主体边界、履约条件、时间窗口和二级叙述偏差均可能改变事件含义。",
        "next_steps": ["查找公司或监管一级披露", "寻找交易对手或客户侧交叉确认", "核验订单、金额、交付、验收与收入", "映射冲突证据和否定条件", "记录无法确认的数据并保持 unknown"],
    }


def run_event_deep_dive(store, evidence_id: str, output: str | Path, run_id: str = "", llm_config: dict | None = None) -> dict:
    run_id = run_id or str(uuid4())
    event = next((item for item in store.events() if item["event_id"] == evidence_id), None)
    if not event:
        raise ValueError("证据不存在")
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    sources = [_original_source(event)]
    facts = [{"fact_id": "f0", "statement": f"二级报道披露：{event['title']}。其关于产品构成、市场机会和商业前景的描述尚需与一级文件或合作方资料交叉核验。", "source_id": "discovery-source", "url": event["source_url"], "status": "unverified"}]
    primary_sources, primary_facts = _verified_fact_pack(store.events(),event)
    sources.extend(primary_sources); facts.extend(primary_facts)
    verified = [fact for fact in facts if fact["status"] == "verified"]
    analysis = _fallback_analysis(verified)
    # The LLM is deliberately limited to the verified fact package; deterministic labels and URLs remain program-controlled.
    llm_items = [{"evidence_id": fact["fact_id"], "source_url": fact["url"], "publisher": "verified-source", "source_type": "primary", "event_kind": "filing", "excerpt": fact["statement"], "matched_terms": (), "limitation": "不得超出该事实。"} for fact in verified]
    llm_result, llm_note = _llm_evidence_analysis(llm_items, llm_config) if llm_items else ({}, "缺少一级事实，使用规则化分析")
    if llm_result:
        analysis["llm_fact_notes"] = llm_result
    confidence = "medium" if verified else "low"
    verification_gaps = ["客户订单、合同金额、收入、部署容量和盈利能力未由当前事实包证明时保持 unknown。", "价格、容量、交付与支持条件需要一级来源逐项确认。", "发现来源的产品性能与市场机会描述需与公司、监管或交易对手资料交叉核验。"]
    audit_errors = [fact["fact_id"] for fact in facts if not fact.get("url")]
    audit = {"run_id": run_id, "passed": not audit_errors, "errors": audit_errors, "verified_fact_count": len(verified), "unverified_fact_count": len(facts) - len(verified), "llm_used": bool(llm_result), "no_investment_recommendation": True}
    payload = {"run_id": run_id, "evidence_id": evidence_id, "company": event.get("company_id") or event.get("publisher") or "unknown", "event_title": event["title"], "data_confidence": confidence, "sources": sources, "facts": facts, "analysis": analysis, "verification_gaps": verification_gaps, "audit": audit}
    _write(out / "event-fact-pack.json", payload)
    lines = [
        f"# {payload['company']}｜公司/事件深度研究", "",
        f"**事件：{event['title']}**  ", f"**数据置信度：{confidence}**　**审计：{'通过' if audit['passed'] else '失败'}**", "",
        "## 1. 事件概览与来源强度", f"- 发现来源：[{event['publisher']}]({event['source_url']})（发现线索，待交叉核验）。", f"- 已核验一级来源：{len(verified)} 条事实。" if verified else "- 当前未找到一级核验来源。", "",
        "## 2. 已验证事实", *[f"- {fact['statement']}（[来源]({fact['url']})，{fact['status']}）" for fact in verified], "",
        "## 3. 未独立核验的事件描述", *[f"- {fact['statement']}（[发现来源]({fact['url']}））" for fact in facts if fact['status'] != 'verified'], "",
        "## 4. 战略变化与产业链含义", analysis["strategic_change"], "", analysis["economic_mechanism"], "",
        "## 5. 商业化路径与关键验证点", analysis["commercialization"], "", "## 6. 风险与不确定性", analysis["risk"], *[f"- {gap}" for gap in verification_gaps], "",
        "## 7. 后续观察指标", *[f"- {item}" for item in analysis["next_steps"]], "",
        "## 8. 研究结论", "当前事实包仅用于判断后续核验优先级；现有材料不足时不推断订单、收入或规模化部署。该报告不构成投资、产品或交易建议。", "",
        "## 完整引用", *[f"- [{source['title']}]({source['url']})：{source['tier']} / {source['verification_status']}" for source in sources], f"- LLM：{llm_note or '已使用受控一级事实归纳。'}",
    ]
    markdown = "\n".join(lines)
    (out / "event-deep-dive.md").write_text(markdown, encoding="utf-8")
    return {"run_id": run_id, "evidence_id": evidence_id, "status": "completed", "stage": "completed", "markdown": markdown, "fact_pack": payload, "audit": audit, "output_dir": str(out)}
