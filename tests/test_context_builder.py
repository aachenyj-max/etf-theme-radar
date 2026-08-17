from __future__ import annotations

from etf_theme_radar.context_builder import build_research_context


def _item(item_id: str, tokens: int, **values: object) -> dict:
    return {"id": item_id, "token_count": tokens, **values}


def test_context_filters_permissions_before_selecting_budgeted_items() -> None:
    context = build_research_context(
        user_id="user-a",
        conversation_id="conversation-a",
        token_budget=30,
        theme_definition=_item("theme", 4),
        score_snapshots=[_item("score", 3)],
        memories=[
            _item("private-other", 1, owner_user_id="user-b"),
            _item("private-own", 2, owner_user_id="user-a"),
        ],
        linked_summaries=[
            _item(
                "linked-allowed", 3, conversation_id="conversation-b",
                allowed_user_ids=["user-a"],
            ),
            _item(
                "linked-not-selected", 1, conversation_id="conversation-c",
                allowed_user_ids=["user-a"],
            ),
        ],
        allowed_linked_conversation_ids={"conversation-b"},
        knowledge=[
            _item("knowledge-shared", 3, owner_user_id="user-b", allowed_user_ids=["user-a"]),
            _item("knowledge-private", 1, owner_user_id="user-b", allowed_user_ids=[]),
        ],
    )

    selected_ids = [
        item["id"]
        for layer in context["layers"]
        for item in layer["items"]
    ]
    assert selected_ids == [
        "theme", "score", "private-own", "linked-allowed", "knowledge-shared",
    ]
    assert context["excluded_by_permission"] == {
        "memories": 1,
        "linked_summaries": 1,
        "knowledge": 1,
    }
    assert "private-other" not in str(context)
    assert "knowledge-private" not in str(context)


def test_context_uses_fixed_trust_order_and_keeps_newest_messages_within_budget() -> None:
    context = build_research_context(
        user_id="user-a",
        conversation_id="conversation-a",
        token_budget=18,
        theme_definition=_item("theme", 4),
        score_snapshots=[_item("score", 3)],
        checkpoint=_item("checkpoint", 4),
        recent_messages=[
            _item("message-old", 4, message_seq=1),
            _item("message-new", 4, message_seq=2),
        ],
        evidence=[_item("evidence", 5)],
        etf_snapshots=[_item("etf", 4)],
    )

    assert [layer["kind"] for layer in context["layers"]] == [
        "theme_definition", "score_snapshots", "checkpoint", "recent_messages",
    ]
    assert context["layers"][-1]["items"] == [
        _item("message-new", 4, message_seq=2)
    ]
    assert context["estimated_tokens"] == 15
    assert context["token_budget"] == 18
    assert context["truncated_layers"] == ["recent_messages", "evidence", "etf_snapshots"]


def test_context_never_includes_unselected_cross_conversation_summary() -> None:
    linked = [
        _item(
            "summary-b", 2, conversation_id="conversation-b",
            owner_user_id="user-a", allowed_user_ids=["user-a"],
            conversation_summary="显式关联摘要",
        ),
        _item(
            "summary-c", 2, conversation_id="conversation-c",
            owner_user_id="user-a", allowed_user_ids=["user-a"],
            conversation_summary="未关联摘要",
        ),
    ]
    disabled = build_research_context(
        user_id="user-a", conversation_id="conversation-a", token_budget=20,
        theme_definition=_item("theme", 2), linked_summaries=linked,
    )
    enabled = build_research_context(
        user_id="user-a", conversation_id="conversation-a", token_budget=20,
        theme_definition=_item("theme", 2), linked_summaries=linked,
        allowed_linked_conversation_ids={"conversation-b"},
    )

    assert all(layer["kind"] != "linked_summaries" for layer in disabled["layers"])
    assert enabled["layers"][-1]["items"] == [linked[0]]
