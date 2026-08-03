from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal

SourceType = Literal["official", "academic", "patent", "jobs", "etf", "social", "forum"]

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class RawDocument:
    source: str
    source_url: str
    title: str
    text: str
    source_type: SourceType
    published_at: str | None = None
    access_note: str = "public"
    retrieved_at: str = field(default_factory=utcnow)
    parser_version: str = "1.0"

    @property
    def content_hash(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    source: str
    source_url: str
    source_type: SourceType
    title: str
    summary: str
    published_at: str | None
    observed_at: str
    themes: tuple[str, ...]
    companies: tuple[str, ...] = ()
    tickers: tuple[str, ...] = ()
    source_quality: float = 0.5
    extraction_confidence: float = 0.5
    raw_content_hash: str = ""
    discovery_source: str = ""
    origin_source_type: str = "unknown"
    publisher: str = ""
    publisher_domain: str = ""
    primary_or_secondary: str = "unknown"
    relevance_status: str = "uncertain"
    theme_assignment_status: str = "needs_review"
    primary_theme: str = "unknown"
    secondary_themes: tuple[str, ...] = ()
    classification_confidence: float = 0.0
    classification_reasons: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()
    company_id: str = ""
    canonical_job_family: str = ""
    department: str = ""
    technical_or_nontechnical: str = "unknown"
    seniority: str = "unknown"
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    posting_status: str = "unknown"
    duplicate_job_cluster: str = ""
    location: str = ""
    theme_relevance: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)

@dataclass(frozen=True)
class ConnectorHealth:
    source_name: str
    enabled: bool
    status: Literal["healthy", "degraded", "disabled"]
    coverage_note: str
    checked_at: str = field(default_factory=utcnow)

@dataclass(frozen=True)
class ThemeMetrics:
    theme_id: str
    signals: dict[str, float]
    source_types: tuple[str, ...]
    official_evidence_count: int
    listed_company_count: int
    evidence_ids: tuple[str, ...]
    counter_evidence: tuple[str, ...] = ()
