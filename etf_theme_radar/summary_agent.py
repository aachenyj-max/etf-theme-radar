"""Validated, versioned conversation summaries with persistent debouncing."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .store import EvidenceStore


SUMMARY_AGENT_PROMPT_PATH = Path(__file__).with_name("prompts") / "summary_agent.md"


def summary_agent_prompt() -> str:
    return SUMMARY_AGENT_PROMPT_PATH.read_text(encoding="utf-8")


def _referenced_evidence_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        found: set[str] = set()
        for key, child in value.items():
            if key == "evidence_ids" and isinstance(child, list):
                found.update(str(item) for item in child)
            else:
                found.update(_referenced_evidence_ids(child))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for child in value:
            found.update(_referenced_evidence_ids(child))
        return found
    return set()


def _validate_summary(
    *, messages_snapshot: list[dict], output: dict, latest: dict | None,
    valid_evidence_ids: Iterable[str],
) -> str | None:
    required = {
        "status", "conversation_summary", "memory_changes", "keywords",
        "related_theme_suggestions", "compression_checkpoint", "covered_from_seq",
        "covered_to_seq", "previous_version_id", "source_message_ids",
    }
    if set(output) != required or output.get("status") != "completed":
        return "invalid_output_schema"
    start = int(output["covered_from_seq"])
    end = int(output["covered_to_seq"])
    ordered = sorted(messages_snapshot, key=lambda item: int(item["message_seq"]))
    sequences = [int(item["message_seq"]) for item in ordered]
    if sequences != list(range(start, end + 1)):
        return "message_sequence_gap"
    source_ids = [str(item) for item in output["source_message_ids"]]
    expected_ids = [str(item["message_id"]) for item in ordered]
    if source_ids != expected_ids:
        return "source_message_mismatch"
    expected_previous = latest["summary_version_id"] if latest else None
    if output.get("previous_version_id") != expected_previous:
        return "previous_version_mismatch"
    referenced = _referenced_evidence_ids(output)
    if not referenced.issubset({str(item) for item in valid_evidence_ids}):
        return "unknown_evidence_id"
    return None


def persist_summary_result(
    store: EvidenceStore, *, conversation_id: str, user_id: str,
    messages_snapshot: list[dict], output: dict, valid_evidence_ids: Iterable[str],
    created_at: str,
) -> dict:
    """Validate a frozen input/output pair before appending immutable summary state."""
    current_messages = store.conversation_messages(conversation_id, user_id)
    current_by_id = {item["message_id"]: item for item in current_messages}
    if any(current_by_id.get(item.get("message_id")) != item for item in messages_snapshot):
        return {"status": "rebuild_required", "reason": "message_snapshot_mismatch"}
    latest = store.latest_conversation_summary(conversation_id, user_id)
    reason = _validate_summary(
        messages_snapshot=messages_snapshot, output=output, latest=latest,
        valid_evidence_ids=valid_evidence_ids,
    )
    if reason:
        return {"status": "rebuild_required", "reason": reason}
    return store.save_conversation_summary(
        conversation_id=conversation_id, user_id=user_id, output=output,
        created_at=created_at,
    )


def schedule_summary(
    store: EvidenceStore, *, conversation_id: str, user_id: str, message_seq: int,
    goal_id: str, now: str, due_at: str,
) -> dict:
    """Coalesce queued summary work; a persistent worker claims it after ``due_at``."""
    return store.schedule_conversation_summary(
        conversation_id=conversation_id, user_id=user_id, message_seq=message_seq,
        goal_id=goal_id, now=now, not_before_at=due_at,
    )

