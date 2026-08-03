from __future__ import annotations

import json
import re
from datetime import date
from hashlib import sha256

from .models import ThemeMetrics, utcnow
from .governance import MAINTENANCE_LOCK
from .scoring import opportunity_score
from .store import EvidenceStore


def _items(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return [value]


def _entity_id(name: str, ticker: str = "") -> str:
    stable = (ticker or name).strip().casefold()
    slug = "-".join(re.findall(r"[a-z0-9]+", stable))[:48]
    return slug or sha256(stable.encode("utf-8")).hexdigest()[:16]


def refresh_entities(store: EvidenceStore) -> dict[str, int]:
    created = 0
    linked = 0
    now = utcnow()
    for event in store.events():
        theme_id = str(event.get("primary_theme") or "unknown")
        pairs: list[tuple[str, str]] = [(name, "") for name in _items(event.get("companies"))]
        pairs.extend((ticker, ticker.upper()) for ticker in _items(event.get("tickers")))
        if event.get("company_id"):
            pairs.append((str(event["company_id"]), ""))
        for name, ticker in dict.fromkeys(pairs):
            entity_id = _entity_id(name, ticker)
            store.save_entity({
                "entity_id": entity_id, "entity_type": "listed_company" if ticker else "company",
                "canonical_name": name, "ticker": ticker, "exchange": "unknown",
                "review_status": "needs_review", "aliases": [name], "created_at": now, "updated_at": now,
            })
            created += 1
            store.save_entity_link({
                "link_id": sha256(f"{entity_id}:{event['event_id']}:{theme_id}".encode()).hexdigest(),
                "entity_id": entity_id, "event_id": event["event_id"], "theme_id": theme_id,
                "relation_type": "mentioned", "confidence": float(event.get("classification_confidence") or .5),
                "review_status": "needs_review", "created_at": now,
            })
            linked += 1
    return {"entities_processed": created, "links_processed": linked}


def _signal(count: int, scale: float) -> float:
    return min(100.0, round(count * scale, 2))


def refresh_theme_snapshots(store: EvidenceStore, as_of_date: str | None = None) -> list[dict]:
    snapshot_date = as_of_date or date.today().isoformat()
    now = utcnow()
    events = [
        item for item in store.events()
        if item.get("relevance_status") == "relevant" and item.get("theme_assignment_status") == "assigned"
    ]
    definitions = {item["theme_id"]: item for item in store.theme_definitions()}
    theme_ids = set(definitions) | {
        str(item.get("primary_theme")) for item in events
        if item.get("primary_theme") not in {None, "", "unknown", "no_theme_match", "needs_review", "irrelevant"}
    }
    snapshots: list[dict] = []
    for theme_id in sorted(theme_ids):
        matched = [item for item in events if item.get("primary_theme") == theme_id]
        source_types = {str(item.get("origin_source_type") or item.get("source_type") or "unknown") for item in matched}
        official = sum(item.get("primary_or_secondary") == "primary" or item.get("source_type") == "official" for item in matched)
        companies = {value for item in matched for value in [str(item.get("company_id") or item.get("publisher") or "")] if value}
        tickers = {ticker for item in matched for ticker in _items(item.get("tickers"))}
        academic = sum((item.get("origin_source_type") or item.get("source_type")) == "academic" for item in matched)
        patents = sum((item.get("origin_source_type") or item.get("source_type")) == "patent" for item in matched)
        jobs = sum((item.get("origin_source_type") or item.get("source_type")) == "jobs" for item in matched)
        etf = sum((item.get("origin_source_type") or item.get("source_type")) == "etf" for item in matched)
        signals = {
            "research_momentum": _signal(academic, 8), "patent_momentum": _signal(patents, 8),
            "hiring_momentum": _signal(jobs, 2), "corporate_adoption": _signal(len(companies), 5),
            "capital_market_momentum": _signal(etf, 10), "investable_universe_quality": _signal(len(tickers), 6),
            # No similarity input means unavailable, not 100% white space.
            "product_white_space": 0.0,
            "evidence_diversity": _signal(len(source_types), 14),
            "hype": _signal(sum(item.get("primary_or_secondary") == "secondary" for item in matched), 2),
            "crowding": _signal(etf, 5), "concentration": 100.0 if len(companies) == 1 else (50.0 if len(companies) == 2 else 0.0),
            "data_quality": max(0.0, 100.0 - _signal(len(source_types), 20)),
        }
        scored = opportunity_score(ThemeMetrics(theme_id, signals, tuple(source_types), official, len(tickers), tuple(item["event_id"] for item in matched)))
        previous = next((item for item in store.theme_snapshots(theme_id) if item["as_of_date"] < snapshot_date), None)
        if previous is None:
            trend, reason = "unknown", "仅有一个可比快照，不推断 emerging/stable/cooling。"
        else:
            delta = scored["opportunity_score"] - float(previous["score"])
            trend = "emerging" if delta >= 3 else "cooling" if delta <= -3 else "stable"
            reason = f"与 {previous['as_of_date']} 快照相比，机会分变化 {delta:+.2f}；当前覆盖 {len(source_types)} 类来源、{len(matched)} 条证据。"
        item = {
            "snapshot_id": f"{theme_id}:{snapshot_date}", "theme_id": theme_id, "as_of_date": snapshot_date,
            "metrics": {**signals, "components": scored["components"], "penalties": scored["penalties"], "evidence_gate_passed": scored["evidence_gate_passed"], "listed_companies": len(tickers)},
            "score": scored["opportunity_score"], "confidence": scored["confidence"],
            "evidence_count": len(matched), "source_type_count": len(source_types),
            "trend": trend, "trend_reason": reason, "created_at": now,
        }
        store.save_theme_snapshot(item)
        snapshots.append(item)
    return snapshots


def refresh_research_assets(store: EvidenceStore, as_of_date: str | None = None) -> dict:
    with MAINTENANCE_LOCK:
        return {"entity_resolution": refresh_entities(store), "theme_snapshots": refresh_theme_snapshots(store, as_of_date)}
