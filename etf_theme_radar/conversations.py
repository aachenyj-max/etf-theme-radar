"""Immutable conversation messages and audited research-turn enqueueing."""
from __future__ import annotations

from .store import EvidenceStore


class ConversationService:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def create_conversation(
        self, *, conversation_id: str, user_id: str, selected_theme_id: str,
        created_at: str, title: str = "",
    ) -> dict:
        return self.store.create_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            selected_theme_id=selected_theme_id,
            title=title or selected_theme_id,
            created_at=created_at,
        )

    def append_user_message(
        self, *, conversation_id: str, user_id: str, message_id: str, goal_id: str,
        idempotency_key: str, content: str, created_at: str,
    ) -> dict:
        return self.store.append_user_conversation_message(
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=message_id,
            goal_id=goal_id,
            idempotency_key=idempotency_key,
            content=content,
            created_at=created_at,
        )

    def messages(self, conversation_id: str, user_id: str) -> list[dict]:
        return self.store.conversation_messages(conversation_id, user_id)
