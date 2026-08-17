from __future__ import annotations

from datetime import date
from pathlib import Path

from .models import utcnow
from .store import EvidenceStore


def _briefing_event(store: EvidenceStore, event: dict) -> dict:
    fact = store.extracted_fact(str(event["event_id"]))
    industry_chain = "unknown"
    if fact and fact.get("status") == "audited":
        industry_chain = str(fact.get("industry_chain_position") or "unknown")
    return {
        "evidence_id": str(event["event_id"]),
        "title": str(event.get("title") or ""),
        "summary": str(event.get("summary") or ""),
        "occurred_at": str(event.get("published_at") or event.get("observed_at") or "")[:10],
        "theme": str(event.get("primary_theme") or "unknown"),
        "source": str(event.get("source") or "unknown"),
        "industry_chain": industry_chain,
    }


def build_daily_briefing(
    store: EvidenceStore, *, as_of_date: str, generated_at: str,
) -> dict:
    """Freeze only publishable evidence into a deterministic daily briefing payload."""
    events = sorted(
        (_briefing_event(store, event) for event in store.publishable_events()),
        key=lambda item: (item["occurred_at"], item["evidence_id"]),
    )
    return {
        "briefing_id": f"daily-briefing:{as_of_date}",
        "as_of_date": as_of_date,
        "generated_at": generated_at,
        "evidence_ids": [item["evidence_id"] for item in events],
        "payload": {"events": events},
    }


def render_daily_briefing_markdown(asset: dict) -> str:
    """Render a persisted daily briefing without re-querying raw or rejected evidence."""
    events = list((asset.get("payload") or {}).get("events") or [])
    lines = [
        "# ETF 主题雷达：每日简报", "",
        f"- 截至日期：{asset.get('as_of_date', '')}",
        f"- 有效证据：{len(events)}",
        "- 本简报仅包含通过内容完整性门的公开信息；不构成投资、ETF 产品或组合建议。", "",
        "## 已治理信息", "",
    ]
    if not events:
        lines.append("- 暂无通过完整性门的证据。")
    for item in events:
        lines.extend([
            f"### {item['title']}",
            f"- 主题：{item['theme']}；产业链位置：{item['industry_chain']}；来源：{item['source']}；日期：{item['occurred_at']}",
            f"- 摘要：{item['summary']}",
            "",
        ])
    return "\n".join(lines)


def build_daily_brief(store: EvidenceStore, output: str | Path) -> Path:
    """Render the deterministic daily briefing model for the legacy CLI output."""
    as_of_date = date.today().isoformat()
    asset = build_daily_briefing(store, as_of_date=as_of_date, generated_at=utcnow())
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_daily_briefing_markdown(asset), encoding="utf-8")
    return target
