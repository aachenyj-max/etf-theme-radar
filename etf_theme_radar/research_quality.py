from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse
from .etf_market import match_competitors


def _list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def counter_evidence_map(events: list[dict]) -> dict:
    negative = re.compile(r"\b(delay|delayed|cancel|cancelled|decline|downturn|layoff|risk|shortage|failure|failed|cuts?|slowdown|weak)\b|推迟|取消|下降|裁员|风险|失败|放缓", re.I)
    conflicting = []
    for event in events:
        text = f"{event.get('title','')} {event.get('summary','')}"
        if negative.search(text):
            conflicting.append({
                "evidence_id": event["event_id"], "claim": event.get("title", ""),
                "source_url": event.get("source_url", ""), "reason": "文本包含可证伪、延迟、下降或执行风险信号；需人工复核语境。",
                "publisher": event.get("publisher", ""), "publisher_domain": event.get("publisher_domain", ""),
                "source_type": event.get("origin_source_type") or event.get("source_type") or "unknown",
                "event_kind": event.get("source_type") or "unknown", "publication_date": event.get("published_at"),
                "excerpt": str(event.get("summary") or "")[:1200], "companies": _list(event.get("companies")),
                "location": event.get("location") or "", "source_quality": event.get("source_quality", 0),
                "extraction_confidence": event.get("extraction_confidence", 0),
                "classification_confidence": event.get("classification_confidence", 0),
            })
    return {
        "conflicting_evidence": conflicting,
        "counter_evidence_status": "available" if conflicting else "insufficient_search",
        "searched_negative_conditions": True,
    }


def assess_investability(events: list[dict]) -> dict:
    company_tickers: dict[str, set[str]] = defaultdict(set)
    roles: dict[str, set[str]] = {"pure_play": set(), "enabler": set(), "beneficiary": set()}
    for event in events:
        tickers = {ticker.upper() for ticker in _list(event.get("tickers")) if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,5}", ticker.upper())}
        if not tickers or (event.get("origin_source_type") or event.get("source_type")) == "etf":
            continue
        company = str(event.get("company_id") or event.get("publisher") or "unknown")
        company_tickers[company].update(tickers)
        source = event.get("origin_source_type") or event.get("source_type")
        # Theme relevance alone never proves pure-play revenue exposure.
        role = "enabler" if source in {"patent", "jobs", "academic"} else "beneficiary"
        roles[role].add(company)
    listed = sorted({ticker for tickers in company_tickers.values() for ticker in tickers})
    counts = Counter(ticker for tickers in company_tickers.values() for ticker in tickers)
    concentration = "unknown" if not counts else round(max(counts.values()) / sum(counts.values()), 4)
    status = "partial" if listed else "insufficient_data"
    return {
        "listed_company_count": len(listed), "identified_public_companies": listed,
        "pure_play_count": len(roles["pure_play"]), "enabler_count": len(roles["enabler"]),
        "beneficiary_count": len(roles["beneficiary"]), "company_roles": {key: sorted(value) for key, value in roles.items()},
        "company_concentration": concentration, "us_tradable_coverage": "unverified" if listed else "unknown",
        "investability_status": status,
        "limitations": ["ticker 来自公开证据，尚未用交易所主表逐项确认美国可交易状态。"] if listed else ["招聘与技术活动不等于可投资上市公司"],
    }


def _universe() -> list[dict]:
    path = Path(__file__).parents[1] / "config" / "etf-competitor-universe.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def assess_etf_landscape(
    all_events: list[dict], theme: str, theme_name: str, aliases: list[str],
    discovered_etfs: list[dict] | None = None,
) -> dict:
    terms = {theme.casefold(), theme_name.casefold(), *(alias.casefold() for alias in aliases if len(alias) >= 2)}
    broad = set(re.findall(r"[a-z]{2,}|[\u4e00-\u9fff]{2,}", " ".join(terms)))
    competitors = match_competitors(theme, theme_name, aliases)
    identities = {(str(item.get("listing_market", "United States")).casefold(), str(item.get("ticker", "")).upper()) for item in competitors}
    for candidate in discovered_etfs or []:
        identity = (str(candidate.get("listing_market", "")).casefold(), str(candidate.get("ticker", "")).upper())
        if candidate.get("verification_status") == "official_url_verified" and identity not in identities:
            competitors.append(candidate)
            identities.add(identity)
    holdings: dict[str, set[str]] = defaultdict(set)
    for event in all_events:
        if (event.get("origin_source_type") or event.get("source_type")) != "etf":
            continue
        event_url = str(event.get("source_url") or "")
        for item in competitors:
            configured_url = str(item.get("holdings_url") or "")
            if event_url == configured_url or (urlparse(event_url).netloc == urlparse(configured_url).netloc and item["ticker"].casefold() in f"{event.get('title','')} {event_url}".casefold()):
                holdings[item["ticker"]].update(_list(event.get("tickers")))
    overlaps = []
    tickers = sorted(holdings)
    for index, left in enumerate(tickers):
        for right in tickers[index + 1:]:
            union = holdings[left] | holdings[right]
            if union:
                overlaps.append({"left": left, "right": right, "jaccard": round(len(holdings[left] & holdings[right]) / len(union), 4)})
    data_status = "available" if len(holdings) >= 2 else "partial" if holdings else "insufficient_data"
    return {
        "similar_etfs": [{
            key: item.get(key) for key in (
                "ticker", "yahoo_symbol", "fund_name", "category", "issuer", "exchange",
                "listing_market", "currency", "official_url", "holdings_url", "holdings_status",
                "verification_status", "verification_sources", "relevance_reason", "discovery_method",
            )
        } for item in competitors],
        "similar_sec_filings": [], "competitor_count": len(competitors), "official_holdings_covered": sorted(holdings),
        "holdings_overlap": overlaps, "overlap_status": data_status,
        "product_white_space": "unknown" if data_status != "available" else "requires_human_review",
        "limitations": ["仅纳入配置或具有发行人/交易所官方页面的 ETF；持仓覆盖不足时不推断产品空白。"],
    }
