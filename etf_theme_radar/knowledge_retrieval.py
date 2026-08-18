"""Deterministic, permission-first retrieval of versioned knowledge chunks."""
from __future__ import annotations

from .knowledge_permissions import KnowledgePermissions
from .store import EvidenceStore


class KnowledgeRetrieval:
    def __init__(self, store: EvidenceStore) -> None:
        self.permissions = KnowledgePermissions(store)

    @staticmethod
    def _tokens(text: str) -> int:
        return max(1, (len(text) + 3) // 4)

    def search(self, *, user_id: str, query: str, theme_id: str, token_budget: int) -> dict:
        if token_budget < 1:
            raise ValueError("token_budget must be positive")
        needle = query.casefold().strip()
        authorized = self.permissions.authorized_chunks(user_id)
        ranked = []
        for item in authorized:
            text = str(item["text"])
            haystack = f"{item['title']} {text}".casefold()
            if needle and needle not in haystack:
                continue
            score = (2 if theme_id and item["theme_id"] == theme_id else 0) + (1 if needle else 0)
            ranked.append((score, str(item["updated_at"]), item))
        ranked.sort(key=lambda row: (row[2]["knowledge_item_id"], row[2]["chunk_index"]))
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        selected: list[dict] = []
        used = 0
        for _score, _updated_at, item in ranked:
            cost = self._tokens(str(item["text"]))
            if used + cost > token_budget:
                continue
            selected.append({
                "knowledge_item_id": item["knowledge_item_id"], "version": item["version"],
                "title": item["title"], "text": item["text"], "page_number": item["page_number"],
                "char_start": item["char_start"], "char_end": item["char_end"],
                "source_type": item["source_type"], "internal_material": True, "token_count": cost,
            })
            used += cost
        return {"items": selected, "estimated_tokens": used, "token_budget": token_budget}
