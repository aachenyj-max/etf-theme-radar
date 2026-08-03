from __future__ import annotations

import json, os, time
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

from .models import ConnectorHealth, NormalizedEvent, RawDocument, utcnow

class SourceConnector(ABC):
    source_name: str
    @abstractmethod
    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]: ...
    @abstractmethod
    def fetch(self, item_id: str) -> RawDocument: ...
    @abstractmethod
    def normalize(self, document: RawDocument) -> list[NormalizedEvent]: ...
    @abstractmethod
    def healthcheck(self) -> ConnectorHealth: ...

class FixtureConnector(SourceConnector):
    """Deterministic connector used for safe demos and contract tests."""
    source_name = "fixture"
    def __init__(self, fixture_file: Path): self.fixture_file = fixture_file
    def _items(self) -> list[dict]: return json.loads(self.fixture_file.read_text(encoding="utf-8"))
    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]:
        return [x["id"] for x in self._items()]
    def fetch(self, item_id: str) -> RawDocument:
        item = next(x for x in self._items() if x["id"] == item_id)
        return RawDocument(**item["document"])
    def normalize(self, document: RawDocument) -> list[NormalizedEvent]:
        return [NormalizedEvent(event_id=document.content_hash[:16], source=document.source,
            source_url=document.source_url, source_type=document.source_type, title=document.title,
            summary=document.text[:500], published_at=document.published_at, observed_at=utcnow(),
            themes=("edge-ai-infrastructure",), companies=("Example Semiconductor",), tickers=("EXSM",),
            source_quality=0.95 if document.source_type == "official" else 0.75,
            extraction_confidence=0.90, raw_content_hash=document.content_hash)]
    def healthcheck(self) -> ConnectorHealth:
        return ConnectorHealth(self.source_name, True, "healthy", "fixture coverage: deterministic")

class SecEdgarConnector(SourceConnector):
    """Public SEC submissions connector. Never bypasses access restrictions."""
    source_name = "sec_edgar"
    def __init__(self, cache_dir: Path, user_agent: str | None = None, enabled: bool = True):
        self.cache_dir, self.enabled = cache_dir, enabled
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT", "")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    def discover(self, since: date, until: date, cursor: str | None = None) -> list[str]: return []
    def _get(self, url: str) -> bytes:
        if not self.enabled: raise RuntimeError("SEC connector disabled")
        if not self.user_agent: raise RuntimeError("SEC_USER_AGENT is required by SEC access policy")
        key = __import__("hashlib").sha256(url.encode()).hexdigest(); cached = self.cache_dir / key
        if cached.exists(): return cached.read_bytes()
        last_error = None
        for attempt in range(3):
            try:
                time.sleep(0.12)  # <= 10 requests/sec
                with urlopen(Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}), timeout=20) as r:
                    data = r.read(); cached.write_bytes(data); return data
            except Exception as exc: last_error = exc; time.sleep(2 ** attempt)
        raise RuntimeError(f"SEC request failed after retries: {last_error}")
    def fetch(self, item_id: str) -> RawDocument:
        url = item_id; payload = self._get(url).decode("utf-8", "replace")
        return RawDocument(source=self.source_name, source_url=url, title="SEC EDGAR filing", text=payload, source_type="official", access_note="SEC public data")
    def normalize(self, document: RawDocument) -> list[NormalizedEvent]: return []
    def healthcheck(self) -> ConnectorHealth:
        status = "disabled" if not self.enabled else ("healthy" if self.user_agent else "degraded")
        note = "已通过配置关闭" if not self.enabled else "需要配置 SEC_USER_AGENT；尚未发起请求"
        return ConnectorHealth(self.source_name, self.enabled, status, note)
