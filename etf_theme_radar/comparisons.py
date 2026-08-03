from __future__ import annotations

from pathlib import Path

from .store import EvidenceStore


def legacy_theme(text: str) -> str:
    lowered = text.lower()
    rules = (("robotics", ("robot", "training", "operations", "technical")), ("semiconductors", ("semiconductor", "chip", "gpu", "valuation")), ("ai-infrastructure", ("artificial intelligence", "generative ai", "accelerator")))
    for theme, words in rules:
        if any(word in lowered for word in words): return theme
    return "unclassified"


def build_comparisons(store: EvidenceStore, output: str | Path, limit: int = 20) -> Path:
    rows = []
    for event in store.events():
        old = legacy_theme(f"{event['title']} {event['summary']}")
        new = event.get("primary_theme", "unknown")
        if old != new:
            rows.append((event, old, new))
        if len(rows) >= limit: break
    lines = ["# \u5206\u7c7b\u4fee\u590d\u524d\u540e\u5bf9\u6bd4", "", "- \u65e7\u89c4\u5219\u4ec5\u7528\u5bbd\u6cdb\u5173\u952e\u8bcd\u6a21\u62df\uff1b\u65b0\u89c4\u5219\u7ed3\u5408\u539f\u59cb\u6765\u6e90\u3001\u804c\u4f4d\u5185\u5bb9\u4e0e\u591a\u4e2a\u660e\u786e\u4e3b\u9898\u8bcd\u3002", ""]
    for number, (event, old, new) in enumerate(rows, 1):
        lines += [f"## {number}. {event['title'][:160]}", f"- \u4fee\u590d\u524d\uff1a`{old}`", f"- \u4fee\u590d\u540e\uff1a`{new}`\uff1b\u72b6\u6001\uff1a`{event.get('relevance_status')}`\uff1b\u7f6e\u4fe1\u5ea6\uff1a{float(event.get('classification_confidence') or 0):.2f}", f"- \u7406\u7531\uff1a{event.get('classification_reasons', '[]')}", f"- \u6765\u6e90\u7c7b\u578b\uff1a`{event.get('origin_source_type')}`\uff1b\u4e00/\u4e8c\u7ea7\uff1a`{event.get('primary_or_secondary')}`", ""]
    target = Path(output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text("\n".join(lines), encoding="utf-8")
    return target
