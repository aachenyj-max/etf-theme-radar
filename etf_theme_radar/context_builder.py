"""Permission-first, budgeted assembly of frozen research context."""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


def _token_count(item: dict[str, Any]) -> int:
    declared = item.get("token_count")
    if isinstance(declared, int) and declared > 0:
        return declared
    serialized = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return max(1, (len(serialized) + 3) // 4)


def _owned_or_shared(item: dict[str, Any], user_id: str) -> bool:
    owner = str(item.get("owner_user_id") or "")
    allowed = {str(value) for value in item.get("allowed_user_ids") or []}
    return owner == user_id or user_id in allowed


def _filter_private(
    items: Iterable[dict[str, Any]], user_id: str,
) -> tuple[list[dict[str, Any]], int]:
    allowed: list[dict[str, Any]] = []
    excluded = 0
    for item in items:
        if _owned_or_shared(item, user_id):
            allowed.append(dict(item))
        else:
            excluded += 1
    return allowed, excluded


def build_research_context(
    *, user_id: str, conversation_id: str, token_budget: int,
    theme_definition: dict[str, Any],
    score_snapshots: list[dict[str, Any]] | None = None,
    checkpoint: dict[str, Any] | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    etf_snapshots: list[dict[str, Any]] | None = None,
    memories: list[dict[str, Any]] | None = None,
    linked_summaries: list[dict[str, Any]] | None = None,
    allowed_linked_conversation_ids: set[str] | None = None,
    knowledge: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if token_budget < 1:
        raise ValueError("token_budget must be positive")

    filtered_memories, excluded_memories = _filter_private(memories or [], user_id)
    private_summaries, excluded_summary_acl = _filter_private(linked_summaries or [], user_id)
    linked_ids = allowed_linked_conversation_ids or set()
    filtered_summaries = [
        item for item in private_summaries
        if str(item.get("conversation_id") or "") in linked_ids
    ]
    excluded_summaries = excluded_summary_acl + len(private_summaries) - len(filtered_summaries)
    filtered_knowledge, excluded_knowledge = _filter_private(knowledge or [], user_id)

    permission_counts = {
        key: count for key, count in (
            ("memories", excluded_memories),
            ("linked_summaries", excluded_summaries),
            ("knowledge", excluded_knowledge),
        ) if count
    }
    recent = sorted(
        (dict(item) for item in recent_messages or []),
        key=lambda item: int(item.get("message_seq") or 0),
        reverse=True,
    )
    ordered_layers: list[tuple[str, list[dict[str, Any]], bool]] = [
        ("theme_definition", [dict(theme_definition)], False),
        ("score_snapshots", [dict(item) for item in score_snapshots or []], False),
        ("checkpoint", [dict(checkpoint)] if checkpoint else [], False),
        ("recent_messages", recent, True),
        ("evidence", [dict(item) for item in evidence or []], False),
        ("etf_snapshots", [dict(item) for item in etf_snapshots or []], False),
        ("memories", filtered_memories, False),
        ("linked_summaries", filtered_summaries, False),
        ("knowledge", filtered_knowledge, False),
    ]

    layers: list[dict[str, Any]] = []
    truncated: list[str] = []
    used = 0
    budget_closed = False
    for kind, items, restore_sequence in ordered_layers:
        if not items:
            continue
        if budget_closed:
            truncated.append(kind)
            continue
        selected: list[dict[str, Any]] = []
        for item in items:
            cost = _token_count(item)
            if used + cost > token_budget:
                if kind not in truncated:
                    truncated.append(kind)
                budget_closed = True
                continue
            selected.append(item)
            used += cost
        if restore_sequence:
            selected.sort(key=lambda item: int(item.get("message_seq") or 0))
        if selected:
            layers.append({"kind": kind, "items": selected})

    return {
        "conversation_id": conversation_id,
        "layers": layers,
        "estimated_tokens": used,
        "token_budget": token_budget,
        "excluded_by_permission": permission_counts,
        "truncated_layers": truncated,
    }
