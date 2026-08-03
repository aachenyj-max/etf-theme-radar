from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .store import EvidenceStore


def _ratio(part: int, total: int) -> str:
    return f"{(100 * part / total) if total else 0:.1f}%"


def build_daily_brief(store: EvidenceStore, output: str | Path) -> Path:
    """Build a data-quality brief only; it contains no investment recommendation."""
    events = store.events(); total = len(events)
    status = Counter(event.get("relevance_status", "uncertain") for event in events)
    sources = Counter(event["source"] for event in events)
    primary = sum(event.get("primary_or_secondary") == "primary" for event in events)
    low = sum(float(event.get("classification_confidence") or 0) < 0.65 for event in events)
    duplicate = sum(bool(event.get("duplicate_job_cluster")) for event in events)
    groups: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        if event.get("relevance_status") == "relevant": groups[event.get("primary_theme", "unknown")].append(event)
    lines = [
        "# ETF \u4e3b\u9898\u96f7\u8fbe\uff1a\u8bc1\u636e\u8d28\u91cf\u65e5\u62a5", "",
        f"- \u622a\u6b62\u65e5\u671f\uff1a{date.today().isoformat()}",
        "- \u672c\u62a5\u544a\u53ea\u7528\u4e8e\u8bc1\u636e\u6cbb\u7406\u4e0e\u6570\u636e\u8d28\u91cf\u5ba1\u6838\uff0c\u4e0d\u542b\u6295\u8d44\u3001ETF \u4ea7\u54c1\u6216\u7ec4\u5408\u5efa\u8bae\u3002", "", "## \u6570\u636e\u8d28\u91cf\u6458\u8981", "",
        f"- \u603b\u4e8b\u4ef6\u6570\uff1a{total}", f"- \u76f8\u5173\u4e8b\u4ef6\u6570\uff1a{status['relevant']}", f"- \u65e0\u5173\u4e8b\u4ef6\u6570\uff1a{status['irrelevant']}", f"- \u5f85\u5ba1\u6838\u4e8b\u4ef6\u6570\uff1a{status['uncertain']}",
        f"- \u4e3b\u9898\u5206\u7c7b\u8986\u76d6\u7387\uff1a{_ratio(status['relevant'], total)}", f"- \u4f4e\u7f6e\u4fe1\u5ea6\u5206\u7c7b\u6bd4\u4f8b\uff1a{_ratio(low, total)}", f"- \u62db\u8058\u91cd\u590d\u8054\u7c7b\u8986\u76d6\u7387\uff1a{_ratio(duplicate, total)}", f"- \u4e00\u7ea7\u6765\u6e90\u5360\u6bd4\uff1a{_ratio(primary, total)}", "", "## \u5404 Connector \u6570\u636e\u5360\u6bd4", "",
    ]
    lines += [f"- `{source}`\uff1a{count} \u6761\uff08{_ratio(count, total)}\uff09" for source, count in sources.most_common()] or ["- \u65e0\u4e8b\u4ef6\u3002"]
    lines += ["", "## Connector \u5065\u5eb7\u72b6\u6001", ""]
    latest_health = {}
    for health in store.health_records(): latest_health.setdefault(health["source_name"], health)
    lines += [f"- `{name}`\uff1a{health['status']}\uff1b{health['coverage_note']}" for name, health in latest_health.items()] or ["- \u6682\u65e0\u5065\u5eb7\u68c0\u67e5\u8bb0\u5f55\u3002"]
    lines += ["", "## \u4e3b\u9898\u5ba1\u6838\u4fe1\u53f7\uff08\u975e\u6392\u540d\u3001\u975e\u6295\u8d44\u5efa\u8bae\uff09", ""]
    for theme, items in sorted(groups.items()):
        origin_types = {item.get("origin_source_type") for item in items}; companies = {item.get("company_id") or item.get("publisher") for item in items if item.get("company_id") or item.get("publisher")}
        first_party = sum(item.get("primary_or_secondary") == "primary" for item in items)
        average = sum(float(item.get("classification_confidence") or 0) for item in items) / len(items)
        lines += [f"### {theme}", f"- \u76f8\u5173\u8bc1\u636e\uff1a{len(items)}\uff1b\u72ec\u7acb\u6765\u6e90\u7c7b\u578b\uff1a{len(origin_types)}\uff1b\u72ec\u7acb\u516c\u53f8/\u53d1\u5e03\u8005\uff1a{len(companies)}\uff1b\u4e00\u7ea7\u6765\u6e90\uff1a{first_party}\uff1b\u5e73\u5747\u7f6e\u4fe1\u5ea6\uff1a{average:.2f}", "- 7/30/90 \u65e5\u57fa\u7ebf\u4e0e z-score\uff1a\u5f53\u524d\u5e93\u53ea\u6709\u4e00\u4e2a\u91c7\u96c6\u65e5\uff0c\u4e0d\u8db3\u4ee5\u5224\u5b9a\u589e\u957f\u6216\u5f02\u5e38\uff1b\u5df2\u6807\u8bb0\u4e3a\u5f85\u79ef\u7d2f\u5386\u53f2\u57fa\u7ebf\u3002", "- \u8986\u76d6\u53d8\u5316\uff1a\u672c\u671f\u542b OpenAlex\u3001\u516c\u5f00\u62db\u8058\u677f\u548c AnySearch \u53d1\u73b0\uff1b\u4e3b\u9898\u4fe1\u53f7\u4e0d\u5c06\u5355\u4e00\u516c\u53f8\u6279\u91cf\u62db\u8058\u89c6\u4e3a\u589e\u957f\u3002", ""]
    lines += ["## \u975e\u4e3b\u9898\u7b7e\u540d", "", f"- irrelevant\uff1a{status['irrelevant']}", f"- needs_review\uff1a{status['uncertain']}", f"- no_theme_match\uff1a{sum(event.get('primary_theme') == 'no_theme_match' for event in events)}", f"- unknown\uff1a{sum(event.get('primary_theme') == 'unknown' for event in events)}"]
    target = Path(output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text("\n".join(lines), encoding="utf-8")
    return target
