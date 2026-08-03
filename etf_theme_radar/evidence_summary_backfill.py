"""Idempotent upgrade of frozen report evidence summaries."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import utcnow
from .store import EvidenceStore
from .theme_research import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    LEGACY_EVIDENCE_SUMMARY,
    _fallback_chinese_evidence,
    _llm_evidence_analysis,
)


def _has_legacy_summary(items: list[dict]) -> bool:
    return any(
        LEGACY_EVIDENCE_SUMMARY in str(item.get("zh_fact_summary") or "")
        for item in items
    )


def _has_deterministic_summary(items: list[dict]) -> bool:
    return any(str(item.get("summary_method") or "") == "deterministic" for item in items)


def _canonical_items(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in items:
        evidence_id = str(item.get("evidence_id") or "")
        if not evidence_id:
            continue
        target = merged.setdefault(evidence_id, {})
        for key, value in item.items():
            if value not in (None, "", [], {}) and target.get(key) in (None, "", [], {}):
                target[key] = value
    return list(merged.values())


def _hydrate_historical_cards(items: list[dict], events: dict[str, dict], report_created_at: str) -> list[str]:
    """Restore fields that existed before the report but were truncated from its frozen card."""
    hydrated = []
    for item in items:
        evidence_id = str(item.get("evidence_id") or "")
        event = events.get(evidence_id)
        if not event or str(event.get("observed_at") or "") > report_created_at:
            continue
        changed = False
        replacements = {
            "excerpt": str(event.get("summary") or "")[:1200],
            "publication_date": event.get("published_at"),
            "publisher": event.get("publisher"), "publisher_domain": event.get("publisher_domain"),
            "source_type": event.get("origin_source_type") or event.get("source_type"),
            "event_kind": event.get("source_type"), "location": event.get("location"),
        }
        for key, value in replacements.items():
            if value not in (None, "") and (key == "excerpt" or item.get(key) in (None, "", "unknown", "公开来源")):
                if item.get(key) != value:
                    item[key] = value; changed = True
        if changed:
            hydrated.append(evidence_id)
    return hydrated


def _replace_markdown_summaries(markdown: str, cards: list[dict]) -> str:
    if not markdown or not cards:
        return markdown
    summaries = iter(str(item.get("zh_fact_summary") or "") for item in cards)
    lines = markdown.splitlines()
    output = []
    for line in lines:
        if line.startswith("- 发生了什么："):
            summary = next(summaries, "")
            output.append(f"- 发生了什么：{summary}" if summary else line)
        else:
            output.append(line)
    return "\n".join(output)


def _upgrade_result(
    result: dict, llm_config: dict | None, *, force: bool = False,
    events: dict[str, dict] | None = None, report_created_at: str = "",
) -> tuple[dict, str | None]:
    upgraded = deepcopy(result)
    brief = upgraded.get("brief") or {}
    counter = ((upgraded.get("detail") or {}).get("counter") or {})
    headline = brief.get("key_evidence") or []
    counter_cards = counter.get("counter_evidence") or []
    cards = [*headline, *counter_cards]
    hydrated_ids = _hydrate_historical_cards(cards, events or {}, report_created_at) if report_created_at else []
    had_legacy = _has_legacy_summary(cards)
    had_deterministic = _has_deterministic_summary(cards)
    if not had_legacy and not had_deterministic and not force:
        return upgraded, "no_legacy_summary"

    canonical = _canonical_items(cards)
    analyses, note = _llm_evidence_analysis(canonical, llm_config)
    improved = 0
    for item in cards:
        evidence_id = str(item.get("evidence_id") or "")
        base = next((value for value in canonical if str(value.get("evidence_id")) == evidence_id), item)
        if evidence_id in analyses:
            item.update(analyses[evidence_id]); improved += 1
        elif LEGACY_EVIDENCE_SUMMARY in str(item.get("zh_fact_summary") or ""):
            item.update(_fallback_chinese_evidence(base))
    if _has_legacy_summary(cards):
        return upgraded, "legacy_summary_remains"
    if (had_deterministic or force) and improved == 0 and not had_legacy:
        return upgraded, "no_quality_improvement"

    audit = upgraded.setdefault("audit", {})
    audit["evidence_summary_schema_version"] = EVIDENCE_SUMMARY_SCHEMA_VERSION
    audit["evidence_summary_note"] = note or "历史重点证据摘要已通过逐条审计"
    audit["evidence_summary_hydrated_ids"] = sorted(set(hydrated_ids))
    upgraded["report_markdown"] = _replace_markdown_summaries(str(upgraded.get("report_markdown") or ""), headline)
    return upgraded, None


def backfill_evidence_summaries(
    store: EvidenceStore, llm_config: dict | None = None, *, apply: bool = False,
    report_id: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "mode": "apply" if apply else "dry_run", "scanned": 0, "updated": 0,
        "would_update": 0, "skipped": [], "failed": [],
    }
    assets = [item for item in store.report_assets() if not report_id or item["report_id"] == report_id]
    events = {str(item.get("event_id") or ""): item for item in store.events()}
    for asset in assets:
        summary["scanned"] += 1
        versions = store.report_versions(asset["report_id"])
        if not versions:
            summary["failed"].append({"report_id": asset["report_id"], "reason": "missing_report_version"})
            continue
        latest = versions[0]
        payload = deepcopy(latest.get("payload") or {})
        result = payload.get("result") or {}
        all_cards = [
            *((result.get("brief") or {}).get("key_evidence") or []),
            *((((result.get("detail") or {}).get("counter") or {}).get("counter_evidence")) or []),
        ]
        current_schema = int((result.get("audit") or {}).get("evidence_summary_schema_version") or 0)
        if current_schema >= EVIDENCE_SUMMARY_SCHEMA_VERSION and not _has_deterministic_summary(all_cards):
            summary["skipped"].append({"report_id": asset["report_id"], "reason": "already_current"})
            continue
        upgraded, reason = _upgrade_result(
            result, llm_config if apply else None,
            force=current_schema < EVIDENCE_SUMMARY_SCHEMA_VERSION,
            events=events, report_created_at=str(latest.get("created_at") or ""),
        )
        if reason:
            summary["skipped"].append({"report_id": asset["report_id"], "reason": reason})
            continue
        summary["would_update"] += 1
        if not apply:
            continue
        next_version = int(latest["version"]) + 1
        now = utcnow()
        next_asset = {**(payload.get("asset") or asset), "version": next_version, "updated_at": now}
        next_payload = {**payload, "asset": next_asset, "result": upgraded}
        claims = store.report_claims(asset["report_id"], int(latest["version"]))
        try:
            created = store.save_and_promote_report_version(
                asset["report_id"], next_version, next_payload,
                str(upgraded.get("report_markdown") or latest.get("markdown") or ""), now, claims,
            )
        except Exception as exc:
            summary["failed"].append({"report_id": asset["report_id"], "reason": str(exc)})
            continue
        if created:
            summary["updated"] += 1
        else:
            summary["skipped"].append({"report_id": asset["report_id"], "reason": "version_exists"})
    return summary
