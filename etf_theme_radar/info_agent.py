"""Bounded, durable information planning for daily and event research goals."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .models import utcnow
from .store import EvidenceStore


INFO_AGENT_PROMPT_VERSION = "info-agent-v1"
INFO_AGENT_PROMPT_PATH = Path(__file__).with_name("prompts") / "info_agent.md"
DEFAULT_INFORMATION_SOURCES = ("sec", "company_careers", "etf_holdings", "etf_news")
DEFAULT_COUNTER_SOURCES = ("arxiv",)
InformationKind = Literal["daily", "event", "background_research"]
CollectionFn = Callable[[str, str, dict[str, Any]], dict[str, Any]]


def information_agent_prompt() -> str:
    return INFO_AGENT_PROMPT_PATH.read_text(encoding="utf-8")


def information_agent_prompt_hash() -> str:
    return hashlib.sha256(information_agent_prompt().encode("utf-8")).hexdigest()


def _runtime_limit() -> int:
    section = ""
    path = Path(__file__).parents[1] / "config" / "defaults.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section = raw.strip()[:-1]
            continue
        if section == "agent_runtime" and raw.strip().startswith("consecutive_no_evidence_limit:"):
            return max(1, int(raw.split(":", 1)[1].strip()))
    return 2


def create_information_goal(
    store: EvidenceStore, *, kind: InformationKind, goal_id: str, now: str,
    scheduled_for: str | None = None, evidence_id: str = "", sources: list[str] | None = None,
    counter_sources: list[str] | None = None,
    payload: dict[str, Any] | None = None, idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Create one replay-safe information Goal without changing public APIs."""
    if kind not in {"daily", "event", "background_research"}:
        raise ValueError(f"Unsupported information Goal kind: {kind}")
    if kind == "event" and not evidence_id:
        raise ValueError("event information Goal requires evidence_id")
    if not idempotency_key:
        if kind == "daily":
            day = scheduled_for or now[:10]
            idempotency_key = f"information:daily:{day}"
        elif kind == "event":
            idempotency_key = f"information:event:{evidence_id}"
        else:
            idempotency_key = f"information:background:{goal_id}"
    goal_payload = dict(payload or {})
    trigger = next((event for event in store.events() if str(event["event_id"]) == evidence_id), None)
    trigger_themes = [str(trigger.get("primary_theme") or "")] if trigger else []
    if trigger:
        trigger_themes.extend(str(item) for item in json.loads(str(trigger.get("themes") or "[]")))
    goal_payload.update({
        "information_kind": kind,
        "scheduled_for": scheduled_for or now[:10],
        "evidence_id": evidence_id,
        "sources": list(dict.fromkeys(sources if sources is not None else DEFAULT_INFORMATION_SOURCES)),
        "counter_sources": list(dict.fromkeys(counter_sources if counter_sources is not None else DEFAULT_COUNTER_SOURCES)),
        "target_theme_ids": list(dict.fromkeys(
            item for item in trigger_themes if item not in {"", "unknown"}
        )),
        "prompt_version": INFO_AGENT_PROMPT_VERSION,
        "prompt_hash": information_agent_prompt_hash(),
    })
    return store.create_agent_goal(
        goal_id=goal_id,
        idempotency_key=idempotency_key,
        goal_type="information_collection",
        lane="background",
        payload=goal_payload,
        created_at=now,
        priority=10 if kind in {"daily", "event"} else 0,
    )


def _event_matches_goal(event: dict[str, Any], payload: dict[str, Any]) -> bool:
    evidence_id = str(payload.get("evidence_id") or "")
    if evidence_id and str(event["event_id"]) == evidence_id:
        return True
    theme_ids = [str(item) for item in payload.get("target_theme_ids") or []]
    theme_id = str(payload.get("theme_id") or payload.get("selected_theme_id") or "")
    if theme_id:
        theme_ids.append(theme_id)
    if not theme_ids:
        return not evidence_id
    if str(event.get("primary_theme") or "") in theme_ids:
        return True
    try:
        return bool(set(theme_ids) & set(json.loads(str(event.get("themes") or "[]"))))
    except json.JSONDecodeError:
        return False


def governed_evidence_ids(store: EvidenceStore, payload: dict[str, Any]) -> set[str]:
    """Return only quality-gated evidence relevant to this information Goal."""
    return {
        str(event["event_id"])
        for event in store.publishable_events()
        if _event_matches_goal(event, payload)
    }


def _cancel_requested(store: EvidenceStore, goal_id: str) -> bool:
    current = store.agent_goal(goal_id)
    return bool(current and current["cancel_requested"])


def _transition(
    store: EvidenceStore, goal_id: str, owner: str, now: str, to_status: str, *,
    summary: str, progress: dict[str, Any], error: str = "",
) -> dict[str, Any]:
    return store.transition_agent_goal(
        goal_id, owner, to_status, now, safe_summary=summary, result=progress, error=error,
    )


def _collect_once(
    store: EvidenceStore, *, goal: dict[str, Any], source: str, purpose: str,
    collect: CollectionFn | None, before_ids: set[str], now: str,
) -> dict[str, Any]:
    call_uid = f"{goal['goal_id']}:{goal['attempt']}:{purpose}:{source}"
    existing = store.tool_call_by_uid(goal["goal_id"], call_uid)
    if existing and existing["status"] in {"succeeded", "failed", "unavailable", "disabled", "degraded"}:
        return dict(existing["result"])
    call_id = store.start_tool_call(
        run_id=goal["goal_id"], attempt=int(goal["attempt"]), call_uid=call_uid,
        agent_run_id=f"information:{goal['goal_id']}:{goal['attempt']}", round_number=len(store.tool_calls(goal["goal_id"])) + 1,
        tool_name="collect_information", started_at=now, arguments={"source": source, "purpose": purpose},
    )
    try:
        raw_result = collect(source, purpose, goal["payload"]) if collect else {
            "status": "unavailable", "reason": "no_information_collector",
        }
        result = dict(raw_result or {})
        result["status"] = str(result.get("status") or "succeeded")
    except Exception:  # Source failures are isolated to this one collection.
        result = {"status": "failed", "reason": "collection_exception"}
        error = "source_collection_failed"
    else:
        error = ""
    after_ids = governed_evidence_ids(store, goal["payload"])
    effective_delta = len(after_ids - before_ids)
    result.update({
        "source": source,
        "purpose": purpose,
        "governed_effective_delta": effective_delta,
        "governed_evidence_count": len(after_ids),
    })
    audit_status = result["status"] if result["status"] in {"failed", "unavailable", "disabled", "degraded"} else "succeeded"
    store.finish_tool_call(
        call_id, status=audit_status, finished_at=utcnow(), result=result, error=error,
        evidence_delta=max(0, int(result.get("events") or result.get("raw_added") or 0)), relevant_evidence_delta=effective_delta,
        coverage_before={"governed_evidence": len(before_ids)},
        coverage_after={"governed_evidence": len(after_ids)},
    )
    return result


def _remaining_gaps(*, baseline: int, current: int, counter: dict[str, Any]) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if current == baseline:
        gaps.append({
            "gap": "未获得治理后有效新增证据",
            "cause": "已批准来源未产生通过完整性门且与目标相关的新记录",
            "impact": "不能据此提升主题或产业动量判断",
            "next_path": "等待下一观察窗口，或由人工指定新的独立公开来源",
        })
    if str(counter.get("status")) != "succeeded":
        gaps.append({
            "gap": "反方检查未取得可用结果",
            "cause": str(counter.get("reason") or "反方来源不可用"),
            "impact": "支持性信息不能单独形成强结论",
            "next_path": "下一轮优先补充独立反方公开来源",
        })
    elif int(counter.get("governed_effective_delta") or 0) == 0:
        gaps.append({
            "gap": "反方检查未发现治理后有效反证",
            "cause": "独立反方来源已执行，但没有新增通过完整性门的相关记录",
            "impact": "支持性信息仍需保持证据边界，不能因缺少反证而提升结论强度",
            "next_path": "下一观察窗口优先补充不同发布方或来源类型的反方公开证据",
        })
    return gaps


def run_information_goal(
    store: EvidenceStore, goal: dict[str, Any], owner: str, *,
    collect: CollectionFn | None = None, now: str | None = None,
) -> dict[str, Any]:
    """Run one claimed Goal with durable, governed stopping and counter checks."""
    if goal["goal_type"] != "information_collection":
        raise ValueError("Goal is not an information_collection Goal")
    if goal["lease_owner"] != owner:
        raise ValueError("Information Goal lease is not owned by this worker")
    now = now or utcnow()
    progress = dict(goal.get("result") or {})
    progress.setdefault("prompt_version", INFO_AGENT_PROMPT_VERSION)
    progress.setdefault("prompt_hash", information_agent_prompt_hash())
    progress.setdefault("support_sources", [])
    progress.setdefault("consecutive_zero_effective_deltas", 0)
    baseline_ids = set(progress.get("baseline_evidence_ids") or governed_evidence_ids(store, goal["payload"]))
    progress["baseline_evidence_ids"] = sorted(baseline_ids)
    progress["baseline_governed_evidence"] = len(baseline_ids)

    if _cancel_requested(store, goal["goal_id"]):
        _transition(store, goal["goal_id"], owner, now, "cancelled", summary="信息 Goal 已在规划边界取消", progress=progress)
        return {"status": "cancelled", "reason": "user_requested"}
    current_status = str(store.agent_goal(goal["goal_id"])["status"])
    if current_status == "planning":
        _transition(store, goal["goal_id"], owner, now, "collecting", summary="开始受限信息采集", progress=progress)
    elif current_status == "validating":
        _transition(store, goal["goal_id"], owner, now, "replanning", summary="恢复后继续受限重规划", progress=progress)
        _transition(store, goal["goal_id"], owner, now, "collecting", summary="恢复后继续受限信息采集", progress=progress)
    elif current_status == "replanning":
        _transition(store, goal["goal_id"], owner, now, "collecting", summary="恢复后继续受限信息采集", progress=progress)

    sources = [str(source) for source in goal["payload"].get("sources") or []]
    limit = _runtime_limit()
    stop_reason = "sources_exhausted"
    for source in sources:
        if source in progress["support_sources"]:
            continue
        if _cancel_requested(store, goal["goal_id"]):
            _transition(store, goal["goal_id"], owner, now, "cancelled", summary="信息 Goal 已在采集边界取消", progress=progress)
            return {"status": "cancelled", "reason": "user_requested"}
        before_ids = governed_evidence_ids(store, goal["payload"])
        item = _collect_once(store, goal=goal, source=source, purpose="support", collect=collect, before_ids=before_ids, now=now)
        progress["support_sources"].append(source)
        progress["last_support_result"] = item
        progress["consecutive_zero_effective_deltas"] = (
            0 if int(item["governed_effective_delta"]) > 0 else int(progress["consecutive_zero_effective_deltas"]) + 1
        )
        _transition(store, goal["goal_id"], owner, now, "validating", summary="按治理后有效增量重规划", progress=progress)
        if _cancel_requested(store, goal["goal_id"]):
            _transition(store, goal["goal_id"], owner, now, "cancelled", summary="信息 Goal 已在验证边界取消", progress=progress)
            return {"status": "cancelled", "reason": "user_requested"}
        if int(progress["consecutive_zero_effective_deltas"]) >= limit:
            stop_reason = "governed_no_effective_increment"
            break
        if source != sources[-1]:
            _transition(store, goal["goal_id"], owner, now, "replanning", summary="继续受限重规划", progress=progress)
            _transition(store, goal["goal_id"], owner, now, "collecting", summary="执行下一支持性采集", progress=progress)

    current = store.agent_goal(goal["goal_id"])
    if current and current["status"] == "collecting":
        _transition(store, goal["goal_id"], owner, now, "validating", summary="支持性采集结束，准备反方检查", progress=progress)
    _transition(store, goal["goal_id"], owner, now, "replanning", summary="规划一次必经反方检查", progress=progress)
    _transition(store, goal["goal_id"], owner, now, "collecting", summary="执行反方检查", progress=progress)
    completed_support = set(progress["support_sources"])
    counter_source = next(
        (source for source in goal["payload"].get("counter_sources") or [] if source not in completed_support),
        "counter_source_unavailable",
    )
    counter = _collect_once(
        store, goal=goal, source=counter_source, purpose="counter", collect=collect,
        before_ids=governed_evidence_ids(store, goal["payload"]), now=now,
    )
    progress["counter_check"] = {"attempted": True, **counter}
    _transition(store, goal["goal_id"], owner, now, "validating", summary="已完成反方检查并汇总缺口", progress=progress)
    current_ids = governed_evidence_ids(store, goal["payload"])
    progress.update({
        "status": "completed",
        "stop_reason": stop_reason,
        "governed_effective_added": len(current_ids - baseline_ids),
        "current_governed_evidence": len(current_ids),
        "remaining_gaps": _remaining_gaps(baseline=len(baseline_ids), current=len(current_ids), counter=counter),
    })
    _transition(store, goal["goal_id"], owner, now, "completed", summary="信息 Goal 已完成反方检查和缺口汇总", progress=progress)
    return progress
