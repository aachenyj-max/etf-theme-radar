"""User-controlled long-term memory revisions isolated from formal assets."""
from __future__ import annotations

from .store import EvidenceStore


class MemoryService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def _validate_sources(
        self, conversation_id: str, user_id: str, source_message_ids: list[str],
    ) -> None:
        valid = {
            item["message_id"]
            for item in self.store.conversation_messages(conversation_id, user_id)
        }
        if not source_message_ids or not set(source_message_ids).issubset(valid):
            raise ValueError("source_message_ids must belong to the conversation")

    def create(
        self, *, memory_id: str, user_id: str, conversation_id: str, category: str,
        scope: str, content: str, confidence: float, source_message_ids: list[str],
        created_at: str,
    ) -> dict:
        if scope not in {"personal", "theme"}:
            raise ValueError("unsupported memory scope")
        if not 0 <= float(confidence) <= 1:
            raise ValueError("memory confidence must be between 0 and 1")
        self._validate_sources(conversation_id, user_id, source_message_ids)
        return self.store.save_memory(
            memory_id=memory_id, user_id=user_id, conversation_id=conversation_id,
            category=category, scope=scope, content=content, confidence=confidence,
            source_message_ids=source_message_ids, created_at=created_at,
        )

    def pin(self, memory_id: str, user_id: str, *, pinned: bool, updated_at: str) -> dict:
        return self.store.update_memory_state(
            memory_id, user_id, pinned=pinned, updated_at=updated_at,
        )

    def _supersede(
        self, memory_id: str, user_id: str, *, replacement_memory_id: str,
        content: str, source_message_ids: list[str], created_at: str,
    ) -> dict:
        old = self.store.memory(memory_id, user_id)
        if old is None:
            raise KeyError(memory_id)
        self._validate_sources(old["conversation_id"], user_id, source_message_ids)
        return self.store.supersede_memory(
            old_memory_id=memory_id, user_id=user_id,
            replacement_memory_id=replacement_memory_id, content=content,
            source_message_ids=source_message_ids, created_at=created_at,
        )

    def edit(self, memory_id: str, user_id: str, **changes: object) -> dict:
        return self._supersede(memory_id, user_id, **changes)

    def correct(self, memory_id: str, user_id: str, **changes: object) -> dict:
        return self._supersede(memory_id, user_id, **changes)

    def disable(self, memory_id: str, user_id: str, *, updated_at: str) -> dict:
        return self.store.update_memory_state(
            memory_id, user_id, status="disabled", updated_at=updated_at,
        )

    def delete(self, memory_id: str, user_id: str, *, updated_at: str) -> dict:
        return self.store.update_memory_state(
            memory_id, user_id, status="deleted", pinned=False, updated_at=updated_at,
        )

