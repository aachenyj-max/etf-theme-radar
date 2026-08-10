"""Deterministic, evidence-first discovery of candidate investment themes."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from .models import utcnow
from .store import EvidenceStore


DEFAULTS_PATH = Path(__file__).parents[1] / "config" / "defaults.yaml"
TERMINAL_STATUSES = {"confirmed", "merged", "rejected"}
STOPWORDS = {
    "about", "after", "announces", "company", "could", "from", "into", "latest",
    "market", "more", "new", "news", "official", "research", "report", "says",
    "technology", "that", "their", "this", "using", "with", "will", "推出", "发布",
    "公司", "研究", "技术", "市场", "最新", "关于", "相关", "应用", "产品",
}


def _discovery_config(path: Path = DEFAULTS_PATH) -> dict[str, int | float]:
    defaults: dict[str, int | float] = {
        "window_days": 30, "minimum_evidence": 4, "minimum_publishers": 3,
        "minimum_source_types": 2, "minimum_entities": 2,
        "confirmation_source_types": 3, "confirmation_official_sources": 1,
        "minimum_quality": 0.45, "minimum_confidence": 0.45,
    }
    if not path.exists():
        return defaults
    active = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line and not raw_line.startswith(" "):
            active = raw_line.strip() == "theme_discovery:"
            continue
        if not active or ":" not in raw_line:
            continue
        key, raw_value = (part.strip() for part in raw_line.split(":", 1))
        if key not in defaults:
            continue
        try:
            defaults[key] = float(raw_value) if "." in raw_value else int(raw_value)
        except ValueError:
            continue
    return defaults


def _array(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _moment(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except ValueError:
        return None


def _tokens(event: dict) -> set[str]:
    text = f"{event.get('title', '')} {event.get('summary', '')}".casefold()
    latin = re.findall(r"[a-z][a-z0-9+.-]{2,}", text)
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,12}", text)
    chinese = [chunk for value in chinese_chunks for chunk in ({value} | {value[i:i + 4] for i in range(max(0, len(value) - 3))})]
    return {token.strip(".-") for token in (*latin, *chinese) if token not in STOPWORDS and len(token.strip(".-")) >= 3}


def _entities(event: dict) -> set[str]:
    values = _array(event.get("companies")) + _array(event.get("tickers"))
    values += [str(event.get("company_id") or "")]
    return {value.strip() for value in values if value.strip()}


def _publisher(event: dict) -> str:
    return str(event.get("publisher_domain") or event.get("publisher") or event.get("source") or "unknown")


def _source_type(event: dict) -> str:
    return str(event.get("origin_source_type") or event.get("source_type") or "unknown")


def _cluster(events: list[dict]) -> list[list[dict]]:
    """Join records only when they share a specific term or entity."""
    parents = list(range(len(events)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parents[b] = a

    token_index: dict[str, list[int]] = defaultdict(list)
    entity_index: dict[str, list[int]] = defaultdict(list)
    for index, event in enumerate(events):
        for token in _tokens(event):
            token_index[token].append(index)
        for entity in _entities(event):
            entity_index[entity.casefold()].append(index)
    # Terms appearing in one record cannot corroborate; terms in over half of a
    # large corpus are too broad to define a theme.
    maximum = max(4, len(events) // 2)
    for indexes in (*token_index.values(), *entity_index.values()):
        if 2 <= len(indexes) <= maximum:
            for index in indexes[1:]:
                union(indexes[0], index)
    grouped: dict[int, list[dict]] = defaultdict(list)
    for index, event in enumerate(events):
        grouped[find(index)].append(event)
    return list(grouped.values())


def _candidate(cluster: list[dict], config: dict[str, int | float], window_start: date, window_end: date) -> dict:
    now = utcnow()
    token_counts = Counter(token for event in cluster for token in _tokens(event))
    entity_counts = Counter(entity for event in cluster for entity in _entities(event))
    common = [item for item, count in token_counts.most_common(8) if count >= 2]
    signature_terms = sorted(common[:4] or token_counts.keys())[:4]
    signature = "|".join(signature_terms)
    candidate_id = "candidate:" + sha256(signature.encode("utf-8")).hexdigest()[:16]
    latin = [item for item in common if item.isascii()]
    proposed_name = " ".join(latin[:3]).title() if latin else (common[0] if common else str(cluster[0].get("title") or "待命名主题")[:32])
    publishers = {_publisher(event) for event in cluster}
    source_types = {_source_type(event) for event in cluster}
    official = sum(
        event.get("primary_or_secondary") == "primary" or _source_type(event) in {"government", "sec", "company_official", "etf_sponsor", "index_provider"}
        for event in cluster
    )
    moments = [_moment(event.get("published_at") or event.get("observed_at")) for event in cluster]
    moments = [item for item in moments if item]
    cutoff = datetime.combine(window_end - timedelta(days=6), datetime.min.time(), tzinfo=timezone.utc)
    recent = sum(item >= cutoff for item in moments)
    prior = max(0, len(moments) - recent)
    acceleration = round(recent / 7 / max(prior / 23, 0.1), 2)
    gate = (
        len(cluster) >= int(config["minimum_evidence"])
        and len(publishers) >= int(config["minimum_publishers"])
        and len(source_types) >= int(config["minimum_source_types"])
        and len(entity_counts) >= int(config["minimum_entities"])
    )
    confirmation_gate = gate and len(source_types) >= int(config["confirmation_source_types"]) and official >= int(config["confirmation_official_sources"])
    status = "awaiting_confirmation" if confirmation_gate else "validating" if gate else "signal"
    days = Counter((item.date().isoformat() for item in moments))
    types = Counter(_source_type(event) for event in cluster)
    etf_events = [event for event in cluster if _source_type(event) in {"etf", "etf_sponsor"}]
    metrics = {
        "evidence_count": len(cluster), "publisher_count": len(publishers),
        "source_type_count": len(source_types), "entity_count": len(entity_counts),
        "official_count": official, "recent_7d_count": recent, "prior_23d_count": prior,
        "acceleration": acceleration, "source_diffusion": round(len(source_types) / max(len(cluster), 1), 3),
        "persistence_days": len(days), "gate_passed": gate,
        "confirmation_gate_passed": confirmation_gate,
        "visualization_blocks": {
            "evidence_timeline": [{"date": key, "count": days[key]} for key in sorted(days)],
            "source_diffusion": [{"source_type": key, "count": count} for key, count in types.most_common()],
            "entity_coverage": [{"label": key, "count": count} for key, count in entity_counts.most_common(12)],
            "etf_coverage": {"status": "observed" if etf_events else "not_assessed", "evidence_count": len(etf_events), "note": "ETF 仅用于主题形成后的可投资性验证。"},
        },
    }
    first = min(moments).isoformat() if moments else ""
    last = max(moments).isoformat() if moments else ""
    rationale = f"{len(cluster)} 条证据，覆盖 {len(publishers)} 个独立发布方、{len(source_types)} 类来源和 {len(entity_counts)} 个实体。"
    return {
        "candidate_id": candidate_id, "proposed_name": proposed_name,
        "description": "由尚未归入已确认主题的公开证据聚类形成，需人工复核。",
        "status": status, "signature": signature, "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(), "first_seen_at": first, "last_seen_at": last,
        "metrics": metrics, "rationale": rationale, "created_at": now, "updated_at": now,
        "aliases": common[:8],
        "evidence": [{"event_id": event["event_id"], "relevance": float(event.get("extraction_confidence") or 0)} for event in cluster],
        "entities": [{"entity_key": key.casefold(), "label": key, "entity_type": "ticker" if key.isupper() and len(key) <= 8 else "company", "mention_count": count} for key, count in entity_counts.items()],
    }


def discover_theme_candidates(store: EvidenceStore, *, as_of: date | None = None) -> dict:
    """Refresh candidate themes and return an auditable, deterministic summary."""
    config = _discovery_config()
    window_end = as_of or date.today()
    window_start = window_end - timedelta(days=int(config["window_days"]) - 1)
    eligible: list[dict] = []
    for event in store.events():
        moment = _moment(event.get("published_at") or event.get("observed_at"))
        if not moment or not (window_start <= moment.date() <= window_end):
            continue
        if event.get("theme_assignment_status") == "assigned" or event.get("relevance_status") == "irrelevant":
            continue
        if float(event.get("source_quality") or 0) < float(config["minimum_quality"]):
            continue
        if float(event.get("extraction_confidence") or 0) < float(config["minimum_confidence"]):
            continue
        eligible.append(event)
    candidates = []
    for cluster in _cluster(eligible):
        if len(cluster) < 2:
            continue
        item = _candidate(cluster, config, window_start, window_end)
        store.save_theme_candidate(item)
        candidates.append(item)
    candidates.sort(key=lambda item: (
        bool(item["metrics"]["gate_passed"]), item["metrics"]["acceleration"],
        item["metrics"]["source_type_count"], item["metrics"]["evidence_count"],
    ), reverse=True)
    return {
        "window_start": window_start.isoformat(), "window_end": window_end.isoformat(),
        "eligible_evidence": len(eligible), "candidate_count": len(candidates),
        "ranked_candidate_ids": [item["candidate_id"] for item in candidates],
        "counter_check": "候选未通过门槛时保持 signal/validating；ETF 缺失不否定主题，只标记 not_assessed。",
        "gaps": ["候选名称为确定性临时名称，确认前需人工校正。"] if candidates else ["当前窗口没有形成至少两条相互印证的未归类证据。"],
        "finish_research": True, "generated_at": utcnow(),
    }
