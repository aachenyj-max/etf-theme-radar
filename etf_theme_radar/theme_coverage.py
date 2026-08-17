"""Evidence-derived theme coverage matrix and bounded gap goals."""
from __future__ import annotations

from typing import Any

from .info_agent import create_information_goal
from .store import EvidenceStore

COVERAGE_KINDS = ("source_diversity", "counter_evidence", "entity_coverage", "time_continuity", "industry_chain", "etf_coverage")


def refresh_theme_coverage(store: EvidenceStore, *, theme_id: str, now: str) -> list[dict[str, Any]]:
    events = [event for event in store.publishable_events() if event.get("primary_theme") == theme_id]
    source_types = {str(event.get("origin_source_type") or event.get("source_type")) for event in events}
    dates = {str(event.get("published_at") or event.get("observed_at") or "")[:10] for event in events}
    entities = {str(event.get("company_id") or "") for event in events if event.get("company_id")}
    chain = {str(store.extracted_fact(event["event_id"]).get("industry_chain_position") or "") for event in events if store.extracted_fact(event["event_id"])}
    values = {"source_diversity": len(source_types) >= 3, "counter_evidence": any(event.get("primary_or_secondary") == "secondary" for event in events), "entity_coverage": len(entities) >= 2, "time_continuity": len(dates) >= 2, "industry_chain": bool(chain - {"", "unknown"}), "etf_coverage": False}
    result=[]
    evidence_ids=[str(event["event_id"]) for event in events]
    for kind in COVERAGE_KINDS:
        status="covered" if values[kind] else "gap"
        cell={"theme_id":theme_id,"coverage_kind":kind,"status":status,"evidence_ids":evidence_ids if status=="covered" else [],"reason":"已由当前治理后证据覆盖" if status=="covered" else "当前治理后证据不足，不能以固定模板推断覆盖","next_path":"补充独立公开证据并重新治理","updated_at":now}
        store.save_theme_coverage_cell(cell); result.append(cell)
        if status == "gap":
            create_information_goal(store, kind="background_research", goal_id=f"coverage:{theme_id}:{kind}", now=now, idempotency_key=f"coverage:{theme_id}:{kind}", payload={"theme_id":theme_id,"coverage_kind":kind,"missing_critical_facts":[kind]})
    return result
