"""Auditable theme research. It produces research briefs, never ETF/product advice."""
from __future__ import annotations
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from urllib.request import Request, urlopen
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelSettings, UsageLimits
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider
from .store import EvidenceStore
from .research_quality import assess_etf_landscape, assess_investability, counter_evidence_map

ALLOWED_THEMES = {"ai-infrastructure", "edge-ai-infrastructure", "robotics", "semiconductors"}
WEIGHTS = {"evidence_quality": .20, "evidence_diversity": .15, "company_breadth": .15, "research_activity": .10, "hiring_activity": .10, "commercial_adoption": .15, "persistence": .10, "counter_evidence": .05}
EVIDENCE_SUMMARY_SCHEMA_VERSION = 5
LEGACY_EVIDENCE_SUMMARY = "已按主题相关性和来源质量完成确定性筛选"


class ResearchConclusionOutput(BaseModel):
    verdict: str
    confidence: str
    statement: str
    key_evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    limitations: list[str] = Field(default_factory=list, max_length=4)

def _write(path: Path, value: dict) -> None: path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _evidence(event: dict) -> dict:
    return {
        "evidence_id": event["event_id"], "source_url": event["source_url"],
        "publisher": event["publisher"], "publisher_domain": event.get("publisher_domain") or "",
        "source_type": event["origin_source_type"], "event_kind": event["source_type"],
        "publication_date": event["published_at"], "claim": event["title"],
        "excerpt": event["summary"][:1200], "companies": _json_list(event.get("companies")),
        "location": str(event.get("location") or ""),
        "source_quality": event["source_quality"], "extraction_confidence": event["extraction_confidence"],
        "classification_confidence": event["classification_confidence"],
    }

def _key_evidence(events: list[dict], limit: int = 5) -> list[dict]:
    """Select independent, high-quality evidence; job postings are capped at one."""
    chosen, publishers, origin_types = [], set(), set()
    ranked = sorted(events, key=lambda item: (
        item.get("primary_or_secondary") == "primary",
        item.get("source_type") != "jobs",
        item.get("source_quality", 0),
        item.get("classification_confidence", 0),
        len(json.loads(item.get("matched_terms") or "[]")),
        item.get("published_at") or "",
    ), reverse=True)
    for event in ranked:
        publisher = event.get("publisher")
        if not publisher or publisher in publishers:
            continue
        if event.get("source_type") == "jobs" and any(item.get("source_type") == "jobs" for item in chosen):
            continue
        # First prioritize a new original-source category; relax only to fill five cards.
        if len(chosen) < 3 and event.get("origin_source_type") in origin_types:
            continue
        chosen.append(event); publishers.add(publisher); origin_types.add(event.get("origin_source_type"))
        if len(chosen) == limit:
            return chosen
    for event in ranked:
        if len(chosen) == limit:
            break
        if event not in chosen and event.get("publisher") not in publishers and not (event.get("source_type") == "jobs" and any(item.get("source_type") == "jobs" for item in chosen)):
            chosen.append(event); publishers.add(event.get("publisher"))
    return chosen


def _evidence_limit(source_type: str) -> str:
    limits = {
        "company_official": "公司页面可证明其公开动作，但单一公司动作不能证明行业需求或收入。",
        "academic": "研究活动可证明技术进展，不能单独证明商业采用。",
        "media": "媒体报道需要结合一级来源核验，不能单独作为核心结论。",
        "press_release": "新闻稿具有宣传属性，需要独立来源佐证。",
        "social": "社交媒体仅作线索，不作为核心结论依据。",
    }
    return limits.get(source_type, "该证据需与其他独立来源交叉验证。")


def _fallback_evidence_analysis(item: dict) -> str:
    terms = ", ".join(item.get("matched_terms", [])) or "已治理主题术语"
    return f"该证据直接涉及 {terms}。它支持继续核验相关技术或产业活动，但不足以单独证明行业规模、商业收入或可投资性。"


_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def _format_chinese_date(value: str) -> str:
    value = value.strip()
    for candidate, pattern in (
        (value[:10], "%Y-%m-%d"),
        (value, "%B %d, %Y"),
        (value, "%b %d %H:%M:%S %z %Y"),
        (value, "%B %d %H:%M:%S %z %Y"),
    ):
        try:
            parsed = datetime.strptime(candidate, pattern)
            return f"{parsed.year}年{parsed.month}月{parsed.day}日"
        except ValueError:
            continue
    return value


def _summary_metadata(item: dict) -> tuple[str, str]:
    excerpt = str(item.get("excerpt") or item.get("fact_summary") or "")
    published = str(item.get("publication_date") or "").strip()
    if not published:
        posted = re.search(r"Posted:\s*(?:\w{3}\s+)?([A-Za-z]+\s+\d{1,2}(?:\s+\d{2}:\d{2}:\d{2}\s+\+\d{4})?\s+\d{4})", excerpt, re.I)
        ordinary = re.search(rf"\b({_MONTHS})\s+\d{{1,2}},\s+\d{{4}}\b", excerpt, re.I)
        matched = ordinary.group(0) if ordinary else posted.group(1) if posted else ""
        if matched:
            simple = re.search(rf"({_MONTHS})\s+(\d{{1,2}})(?:,)?(?:\s+\d{{2}}:\d{{2}}:\d{{2}}\s+\+\d{{4}})?\s+(\d{{4}})", matched, re.I)
            published = f"{simple.group(1)} {simple.group(2)}, {simple.group(3)}" if simple else matched
    author = ""
    author_match = re.search(r"Author:\s*(.+?)(?:\s*\[|\s*\||\s+Posted:|$)", excerpt, re.I)
    if author_match:
        author = author_match.group(1).strip(" -")
    else:
        by_match = re.search(rf"\bBy:\s*(.+?)(?=\s+(?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}}|\s+-\s+\d+\s+minutes|$)", excerpt, re.I)
        if by_match:
            author = by_match.group(1).strip(" -")
    return _format_chinese_date(published) if published else "", author


def _fallback_chinese_evidence(item: dict) -> dict[str, str]:
    publisher = str(item.get("publisher") or "公开来源")
    source_type = str(item.get("source_type") or "公开资料")
    published, author = _summary_metadata(item)
    actor = author or publisher
    date_prefix = f"{published}，" if published else ""
    claim = re.sub(r"\s+", " ", str(item.get("claim") or "公开资料")).strip()[:100]
    location = str(item.get("location") or "").strip()
    location_text = f"在{location}" if location else ""
    kind = {"patent": "公开专利", "academic": "发表研究", "social": "发布观点", "jobs": "发布招聘信息"}.get(source_type, "发布资料")
    return {
        "zh_title": claim,
        "zh_fact_summary": f"{date_prefix}{actor}{location_text}{kind}《{claim}》，内容涉及该主题相关的技术、产业活动或主要观点。",
        "research_implication": _fallback_evidence_analysis(item),
        "summary_method": "deterministic",
        "summary_schema_version": EVIDENCE_SUMMARY_SCHEMA_VERSION,
    }


def _llm_evidence_analysis(items: list[dict], config: dict | None) -> tuple[dict[str, dict[str, str]], str | None]:
    """Return evidence-bound Chinese fields; IDs, URLs and all numbers are audited."""
    unique_items = list({str(item["evidence_id"]): item for item in items}.values())
    allowed_input_fields = {
        "evidence_id", "publisher", "publisher_domain", "source_type", "event_kind",
        "publication_date", "claim", "excerpt", "companies", "location", "matched_terms",
        "fact_summary", "source_quality", "extraction_confidence", "classification_confidence",
    }
    model_items = []
    for item in unique_items:
        model_item = {key: value for key, value in item.items() if key in allowed_input_fields}
        verified_date, verified_authors = _summary_metadata(item)
        if verified_date:
            model_item["verified_publication_date"] = verified_date
        if verified_authors:
            model_item["verified_authors"] = verified_authors
        model_items.append(model_item)
    if not config or not config.get("api_key"):
        return {}, "未配置 LLM，使用规则化重点证据分析"
    payload = {
        "model": config.get("model", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": "仅依据提供的证据返回 json 对象：{\"analyses\":[{\"evidence_id\":\"id\",\"zh_title\":\"中文标题\",\"zh_fact_summary\":\"中文事实摘要\",\"research_implication\":\"中文研究含义\"}]}。输入中的唯一条目与输出条目数必须一致，每条必须引用已有 evidence_id。zh_fact_summary 使用一至两句自然中文且不超过180个汉字，概括主体、领域以及发生的事情或主要观点；输入含 verified_publication_date 时必须原样写入摘要，含 verified_authors 时应说明作者或以明确的发布机构作为观点主体；地点缺失时直接省略。品牌、公司、作者和 ticker 保留官方写法；不得添加输入中不存在的事实、数字、实体、URL、投资或产品建议。"},
            {"role": "user", "content": json.dumps(model_items, ensure_ascii=False)},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    try:
        request = Request(config.get("base_url", "https://api.openai.com/v1").rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"})
        with urlopen(request, timeout=60) as response:
            content = json.loads(response.read())["choices"][0]["message"]["content"]
        analyses = json.loads(content).get("analyses", [])
        by_id = {str(item["evidence_id"]): item for item in model_items}
        if len(analyses) != len(unique_items):
            raise ValueError("重点证据分析数量不匹配")
        result: dict[str, dict[str, str]] = {}
        for item in analyses:
            evidence_id = str(item.get("evidence_id") or "")
            fields = {
                "zh_title": str(item.get("zh_title") or "").strip(),
                "zh_fact_summary": str(item.get("zh_fact_summary") or "").strip(),
                "research_implication": str(item.get("research_implication") or "").strip(),
            }
            if evidence_id not in by_id or not all(fields.values()) or evidence_id in result:
                continue
            output_text = json.dumps(fields, ensure_ascii=False)
            valid_numbers = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(by_id[evidence_id], ensure_ascii=False)))
            if not set(re.findall(r"\d+(?:\.\d+)?", output_text)).issubset(valid_numbers):
                continue
            if "http://" in output_text.casefold() or "https://" in output_text.casefold():
                continue
            fact = fields["zh_fact_summary"]
            required_date = str(by_id[evidence_id].get("verified_publication_date") or "")
            if required_date and required_date not in fact:
                continue
            if not re.search(r"[\u4e00-\u9fff]", fact) or len(fact) > 220 or len(re.findall(r"[。！？]", fact)) > 2:
                continue
            result[evidence_id] = {
                **fields, "summary_method": "llm",
                "summary_schema_version": EVIDENCE_SUMMARY_SCHEMA_VERSION,
            }
        invalid_count = len(unique_items) - len(result)
        note = f"{invalid_count} 条重点证据未通过逐条审计，已使用规则化分析" if invalid_count else None
        return result, note
    except Exception:
        return {}, "LLM 重点证据分析未通过审计，使用规则化分析"

def _llm_summary(context: dict, config: dict | None) -> tuple[str | None, str | None]:
    if not config or not config.get("api_key"): return None, "未配置 LLM，使用固定模板"
    payload = {"model": config.get("model", "gpt-4o-mini"), "messages": [{"role":"system","content":"仅依据提供的证据返回一个 json 对象：{\"bullets\":[{\"text\":\"中文摘要\",\"evidence_ids\":[\"id\"]}]}。最多3条；每条必须引用已有 evidence_id；不得编造数字、公司、结论或投资建议。"}, {"role":"user","content": json.dumps(context, ensure_ascii=False)}], "temperature": 0, "response_format":{"type":"json_object"}}
    try:
        req = Request(config.get("base_url", "https://api.openai.com/v1") .rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"})
        with urlopen(req, timeout=20) as response: content = json.loads(response.read())["choices"][0]["message"]["content"]
        result = json.loads(content); bullets = result.get("bullets", [])
        valid_ids = {item["evidence_id"] for item in context["evidence"]}; valid_numbers = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(context, ensure_ascii=False)))
        if not 1 <= len(bullets) <= 3: raise ValueError("LLM 摘要条数无效")
        for bullet in bullets:
            if not bullet.get("text") or not set(bullet.get("evidence_ids", [])).issubset(valid_ids) or not bullet.get("evidence_ids"): raise ValueError("LLM 引用了不存在的证据")
            if not set(re.findall(r"\d+(?:\.\d+)?", bullet["text"])).issubset(valid_numbers): raise ValueError("LLM 生成了不存在的数字")
        urls = {item["evidence_id"]: item["source_url"] for item in context["evidence"]}
        return "\n".join(
            f"- {item['text']}（证据：{', '.join(f'[{evidence_id}]({urls[evidence_id]})' for evidence_id in item['evidence_ids'])}）"
            for item in bullets
        ), None
    except Exception: return None, "LLM 调用失败，使用固定模板"


def _fallback_conclusion(context: dict) -> dict:
    support = context.get("support") or []
    counter = context.get("counter") or []
    minimum_met = bool(context.get("minimum_met"))
    verdict = "mixed" if minimum_met and counter else "supported" if minimum_met else "insufficient"
    statements = {
        "supported": "现有多来源证据支持该主题继续进入深度研究，但仍不能据此形成买卖或产品决策。",
        "mixed": "现有证据同时显示主题催化与可证伪风险，结论偏混合，需继续核验商业兑现和可投资性。",
        "insufficient": "当前证据尚不足以形成稳健主题结论，应优先关闭一级来源、反方证据和可投资标的缺口。",
    }
    return {
        "verdict": verdict,
        "confidence": "medium" if minimum_met else "low",
        "statement": statements[verdict],
        "key_evidence_ids": [item["evidence_id"] for item in support[:3]],
        "limitations": list(context.get("missing") or [])[:4],
        "model_used": False,
    }


def _llm_conclusion(context: dict, config: dict | None) -> tuple[dict, str | None]:
    fallback = _fallback_conclusion(context)
    if not config or not config.get("api_key"):
        return fallback, "未配置 LLM，使用证据门槛结论"
    try:
        provider_name = str(config.get("provider") or "deepseek").casefold()
        provider = (
            DeepSeekProvider(api_key=config["api_key"])
            if provider_name == "deepseek"
            else OpenAIProvider(api_key=config["api_key"], base_url=config.get("base_url"))
        )
        agent = Agent(
            OpenAIChatModel(str(config.get("model") or "deepseek-v4-pro"), provider=provider),
            output_type=ResearchConclusionOutput,
            instructions=(
                "仅依据输入证据形成中文研究结论。verdict 只能是 supported、mixed、insufficient；"
                "confidence 只能是 high、medium、low。必须引用至少一个输入中的 evidence_id，"
                "同时考虑支持证据、反方证据和缺口；不得新增事实、数字、URL、买卖建议或产品建议。"
            ),
            model_settings=ModelSettings(max_tokens=1000, timeout=60),
            retries=2,
        )
        result = agent.run_sync(
            json.dumps(context, ensure_ascii=False),
            usage_limits=UsageLimits(request_limit=3, total_tokens_limit=10000),
        ).output.model_dump()
        valid_ids = {item["evidence_id"] for item in [*(context.get("support") or []), *(context.get("counter") or [])]}
        ids = result.get("key_evidence_ids") or []
        if (
            result.get("verdict") not in {"supported", "mixed", "insufficient"}
            or result.get("confidence") not in {"high", "medium", "low"}
            or not str(result.get("statement") or "").strip()
            or not ids
            or not set(ids).issubset(valid_ids)
        ):
            raise ValueError("结论结构或证据引用无效")
        valid_numbers = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(context, ensure_ascii=False)))
        if not set(re.findall(r"\d+(?:\.\d+)?", result["statement"])).issubset(valid_numbers):
            raise ValueError("结论生成了不存在的数字")
        if result["verdict"] == "supported" and not context.get("minimum_met"):
            result["verdict"] = "insufficient"
            result["confidence"] = "low"
            result["statement"] = fallback["statement"]
        if result["verdict"] == "supported" and context.get("counter"):
            result["verdict"] = "mixed"
        result["limitations"] = [str(item) for item in result.get("limitations", [])][:4]
        result["model_used"] = True
        return result, None
    except Exception:
        return fallback, "DeepSeek 研究结论未通过证据审计，使用证据门槛结论"


def run_theme_research(
    store: EvidenceStore, theme: str, output: str | Path, run_id: str = "",
    llm_config: dict | None = None, *, theme_name: str | None = None,
    aliases: list[str] | None = None, discovered_etfs: list[dict] | None = None,
) -> dict:
    run_id = run_id or str(uuid4())
    out = Path(output); out.mkdir(parents=True, exist_ok=True); all_events = store.events()
    keys = {theme.casefold(), *((item or "").casefold() for item in (aliases or []))}
    def belongs(e: dict) -> bool:
        assigned = {str(e.get("primary_theme") or "").casefold(), *(str(item).casefold() for item in json.loads(e.get("secondary_themes") or "[]"))}
        searchable = f"{e.get('title','')} {e.get('summary','')} {' '.join(json.loads(e.get('matched_terms') or '[]'))}".casefold()
        return bool(keys & assigned) or any(len(key) >= 3 and key in searchable for key in keys)
    selected = [e for e in all_events if e.get("relevance_status")=="relevant" and e.get("theme_assignment_status")=="assigned" and belongs(e) and float(e.get("classification_confidence") or 0)>=.65 and e.get("source_url") and e.get("publisher")]
    # Deduplicate job mirrors and same publisher/title, retaining strongest source quality.
    unique = {}
    for e in selected:
        key = e.get("duplicate_job_cluster") or (e["publisher_domain"], e["title"].lower())
        if key not in unique or e["source_quality"] > unique[key]["source_quality"]: unique[key] = e
    selected = sorted(unique.values(), key=lambda e: (e["source_quality"], e["classification_confidence"]), reverse=True)
    excluded = [{"evidence_id": e["event_id"], "reason": "不满足相关性、主题分配、置信度或可审计来源条件"} for e in all_events if e not in selected]
    support = [_evidence(e) for e in selected]; types = {e["origin_source_type"] for e in selected}; companies = {e.get("company_id") or e["publisher"] for e in selected}; first = [e for e in selected if e["primary_or_secondary"]=="primary"]
    hypothesis = {"theme_id": theme, "theme_name": theme_name or theme, "hypothesis": "现有高置信度证据显示该主题存在值得持续核验的技术与产业活动。", "economic_mechanism": ["技术部署可能带动相关基础设施、软硬件与服务需求"], "potential_beneficiaries": [], "key_catalysts": ["独立一级来源的持续新增证据"], "disconfirming_conditions": ["证据仅来自单一公司、无法验证商业采用或缺少可投资公司池"], "current_stage": "uncertain", "evidence_ids": [e["evidence_id"] for e in support]}
    available = {"evidence_quality": sum(e["source_quality"] for e in selected)/len(selected) if selected else 0, "evidence_diversity": min(1, len(types)/3), "company_breadth": min(1, len(companies)/3), "research_activity": min(1, sum(e["origin_source_type"]=="academic" for e in selected)/3), "hiring_activity": min(1, sum(e["source_type"]=="jobs" and e.get("technical_or_nontechnical")=="technical" for e in selected)/10), "commercial_adoption": 0, "counter_evidence": 0}
    active = sum(WEIGHTS[k] for k in available); components = {k:{"raw":v,"weight":WEIGHTS[k],"normalized_weight":WEIGHTS[k]/active,"available":True} for k,v in available.items()}; components["persistence"]={"raw":None,"weight":WEIGHTS["persistence"],"normalized_weight":0,"available":False,"reason":"insufficient_history"}; score=round(sum(v["raw"]*v["normalized_weight"] for v in components.values() if v["available"])*100,2)
    counter_map = counter_evidence_map(selected)
    counter = {"supporting_evidence":support, "counter_evidence":counter_map["conflicting_evidence"], "missing_evidence":["独立反方来源交叉确认", "交易所级上市公司确认", "历史基线", "完整 ETF 持仓重叠"], **counter_map}
    investability=assess_investability(selected)
    landscape=assess_etf_landscape(all_events,theme,theme_name or theme,aliases or [],discovered_etfs)
    status = "DEEP_RESEARCH" if len(types)>=3 and len(first)>=2 and len(companies)>=3 and investability["investability_status"]=="pass" and counter["counter_evidence_status"]!="insufficient_search" else "WATCH" if selected else "REJECT"
    headline_events = _key_evidence(selected)
    headline = [_evidence(event) for event in headline_events]
    for card, event in zip(headline, headline_events):
        card["matched_terms"] = tuple(json.loads(event.get("matched_terms") or "[]"))
        card["fact_summary"] = card["excerpt"] or card["claim"]
        card["limitation"] = _evidence_limit(card["source_type"])
    translation_items = [*headline, *(counter.get("counter_evidence") or [])]
    llm_analysis, analysis_note = _llm_evidence_analysis(translation_items, llm_config)
    for card in headline:
        card.update(llm_analysis.get(card["evidence_id"], _fallback_chinese_evidence(card)))
    for card in counter.get("counter_evidence") or []:
        card.update(llm_analysis.get(card["evidence_id"], _fallback_chinese_evidence(card)))
    summary, llm_note = _llm_summary({"theme":theme,"status":status,"score":score,"evidence":headline,"missing":counter["missing_evidence"]}, llm_config)
    conclusion_context = {
        "theme": theme_name or theme,
        "support": headline,
        "counter": counter["counter_evidence"],
        "missing": counter["missing_evidence"],
        "minimum_met": len(types) >= 3 and len(first) >= 1,
        "etf_landscape": {
            "verified_count": landscape.get("competitor_count", 0),
            "overlap_status": landscape.get("overlap_status"),
        },
    }
    conclusion, conclusion_note = _llm_conclusion(conclusion_context, llm_config)
    valid_event_ids = {x["event_id"] for x in all_events}
    audit_errors = [f"无效引用 {e['evidence_id']}" for e in support if e["evidence_id"] not in valid_event_ids or not e["source_url"]]
    audit_errors += [f"重点证据缺少 URL 或无效引用：{e['evidence_id']}" for e in headline if e["evidence_id"] not in valid_event_ids or not e["source_url"]]
    audit={"run_id":run_id,"passed":not audit_errors,"errors":audit_errors,"llm_used":bool(summary),"no_trend_claim":True,"no_product_recommendation":True,"evidence_summary_schema_version":EVIDENCE_SUMMARY_SCHEMA_VERSION,"evidence_summary_note":analysis_note or "逐条证据摘要已通过审计"}
    score_data={"run_id":run_id,"theme_id":theme,"theme_strength_score":score,"components":components,"unavailable_dimensions":["persistence"],"calculation":"仅对可用维度重新归一化；不推断历史趋势"}
    for name,data in (("theme-hypothesis.json",hypothesis),("theme-score.json",score_data),("investability-assessment.json",investability),("etf-landscape.json",landscape),("report-audit.json",audit),("evidence-appendix.json",{"key_evidence":headline,"selected":support,"excluded":excluded,"counter":counter})): _write(out/name,data)
    hiring=sum(e["source_type"]=="jobs" for e in selected)
    verdict_labels = {"supported": "支持", "mixed": "混合", "insufficient": "证据不足"}
    lines=[f"# {theme_name or theme}｜主题研究简报", "", f"**状态：{status}**　主题强度：**{score:.1f}/100**　数据置信度：**{'中' if len(types)>=2 else '低'}**", "", "## 研究结论", f"**{verdict_labels[conclusion['verdict']]}｜置信度 {conclusion['confidence']}**", conclusion["statement"], "", "## 一页决策摘要", hypothesis["hypothesis"], summary or "- 当前证据显示值得持续跟踪，但尚不具备形成产品或投资结论的条件。", f"- 独立来源类型：{len(types)}；独立公司/机构：{len(companies)}；一级来源：{len(first)}。", f"- 最大数据缺口：{counter['missing_evidence'][0]}。", "- 下一步：补充反方检索、上市公司映射与连续历史基线。", "", "## 五条重点证据分析"]
    for number, item in enumerate(headline, 1):
        lines += [f"### {number}. {item['claim']}", f"- 来源：{item['publisher']}（{item['source_type']}）；证据 ID：`{item['evidence_id']}`", f"- 原文：[查看来源]({item['source_url']})", f"- 发生了什么：{item['zh_fact_summary']}", f"- 研究含义：{item['research_implication']}", f"- 限制：{item['limitation']}", ""]
    lines += ["## 第二页｜证据、风险与覆盖", f"- 支持证据：{len(support)} 条；候选冲突证据：{len(counter['counter_evidence'])} 条（均需人工复核语境）。", f"- 招聘信号：{hiring} 条去重后岗位，按独立公司/机构而非原始职位数解读。", f"- 初步可投资性：{investability['investability_status']}；ETF 持仓覆盖：{landscape['overlap_status']}。", "", "## 评分与限制", "- 质量、来源多样性和公司广度已计入；Persistence 不可用（仅一个采集日）。", "- 不得将本报告理解为投资建议、ETF 产品建议、组合建议或 SEC 文件。", "", "## 审计与引用", f"- 审计：{'通过' if audit['passed'] else '失败'}；完整证据、排除原因与计算过程见 evidence-appendix.json。", f"- LLM 结论：{conclusion_note or '已使用受控证据结论。'}", f"- LLM 摘要：{llm_note or '已使用受控证据摘要。'}", f"- LLM 重点证据分析：{analysis_note or '已使用受控证据分析。'}"]
    markdown="\n".join(lines); (out/f"{theme}-report.md").write_text(markdown,encoding="utf-8")
    claims = [{"text": hypothesis["hypothesis"], "type": "thesis", "evidence_ids": hypothesis["evidence_ids"]}]
    claims.extend({"text": item["claim"], "type": "support", "evidence_ids": [item["evidence_id"]]} for item in headline)
    claims.extend({"text": item["claim"], "type": "counter", "evidence_ids": [item["evidence_id"]]} for item in counter["counter_evidence"])
    return {
        "run_id": run_id,
        "theme": theme,
        "status": status,
        "stage": "completed",
        "selected": len(support),
        "report_markdown": markdown,
        "brief": {
            "score": score,
            "source_types": len(types),
            "companies": len(companies),
            "first_party": len(first),
            "key_evidence": headline,
        },
        "conclusion": conclusion,
        "detail": {
            "hypothesis": hypothesis,
            "counter": counter,
            "investability": investability,
            "landscape": landscape,
            "score": score_data,
        },
        "audit": audit,
        "claims": claims,
        "output_dir": str(out),
    }
