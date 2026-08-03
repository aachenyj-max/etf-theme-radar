"""Conservative evidence provenance, relevance and job-signal classification."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from .models import NormalizedEvent

QUALITY = json.loads((Path(__file__).parents[1] / "config" / "source-quality.json").read_text(encoding="utf-8"))
MEDIA_DOMAINS = {"reuters.com", "ft.com", "bloomberg.com", "wsj.com", "seekingalpha.com"}
SOCIAL_DOMAINS = {"x.com", "twitter.com", "linkedin.com", "reddit.com"}
FORUM_DOMAINS = {"reddit.com", "seekingalpha.com"}
ACADEMIC_DOMAINS = {"openalex.org", "arxiv.org", "semanticscholar.org", "nature.com", "science.org"}
COMPANY_DOMAINS = {"openai.com", "anthropic.com", "google.com", "deepmind.google", "meta.com", "x.ai", "nvidia.com", "microsoft.com", "amazon.com", "databricks.com"}
MAINTENANCE_LOCK = threading.RLock()

THEMES = {
    "ai-infrastructure": ("ai infrastructure", "ml platform", "compute cluster", "data center", "distributed training", "gpu cluster", "ai accelerator"),
    "edge-ai-infrastructure": ("edge ai", "on-device ai", "ai inference", "inference engine", "inference accelerator"),
    "robotics": ("robotics", "robotic", "autonomous robot", "industrial robot", "humanoid", "vision-language-action"),
    "semiconductors": ("semiconductor", "chip design", "asic", "wafer", "foundry", "gpu architecture", "chiplet"),
}
IRRELEVANT_TERMS = ("shiller p/e", "valuation", "price target", "hedge fund party", "technical accounting", "benefits manager", "training & operations")


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def origin(url: str, connector: str, source_type: str) -> tuple[str, str, str, str, float]:
    domain = _domain(url)
    if domain.endswith("sec.gov"):
        kind, primary = "sec", "primary"
    elif domain in ACADEMIC_DOMAINS or source_type == "academic":
        kind, primary = "academic", "primary"
    elif "patents.google" in domain or "patentsview" in domain or source_type == "patent":
        kind, primary = "patent", "primary"
    elif domain in SOCIAL_DOMAINS:
        kind, primary = "social", "secondary"
    elif domain in FORUM_DOMAINS:
        kind, primary = "forum", "secondary"
    elif domain in MEDIA_DOMAINS:
        kind, primary = "media", "secondary"
    elif domain.endswith("greenhouse.io") or domain.endswith("lever.co") or domain.endswith("ashbyhq.com") or any(domain.endswith(item) for item in COMPANY_DOMAINS):
        kind, primary = "company_official", "primary"
    elif connector == "sp_global_dji" and domain.endswith("spglobal.com"):
        kind, primary = "index_provider", "primary"
    elif connector == "official_etf_holdings":
        kind, primary = "etf_sponsor", "primary"
    elif source_type == "official":
        kind, primary = "government", "primary"
    else:
        kind, primary = "unknown", "unknown"
    publisher = domain or connector
    return kind, publisher, domain, primary, float(QUALITY[kind])


def job_metadata(title: str, text: str, publisher: str, observed_at: str) -> dict[str, str | float]:
    combined = f"{title} {text}".lower()
    title_lower = title.lower()
    technical = "technical" if any(term in combined for term in ("engineer", "scientist", "research", "developer", "architect", "hardware")) else "nontechnical"
    family = "engineering" if any(term in title_lower for term in ("engineer", "developer", "architect")) else "research" if "research" in title_lower else "operations" if any(term in title_lower for term in ("operations", "accounting", "recruit", "sales", "manager")) else "other"
    department = "research" if "research" in combined else "engineering" if family == "engineering" else "operations" if family == "operations" else "unknown"
    seniority = "manager" if "manager" in title_lower else "director" if "director" in title_lower else "senior" if "senior" in title_lower else "individual_contributor"
    location_match = re.search(r'"location"\s*:\s*"([^"]+)"', text, re.I)
    location = location_match.group(1) if location_match else ""
    cluster = sha256(re.sub(r"\b(remote|hybrid|new york|san francisco|london)\b", "", title_lower).encode()).hexdigest()[:16]
    return {"company_id": publisher, "canonical_job_family": family, "department": department, "technical_or_nontechnical": technical, "seniority": seniority, "first_seen_at": observed_at, "last_seen_at": observed_at, "posting_status": "open", "duplicate_job_cluster": cluster, "location": location}


def classify(event: NormalizedEvent, raw_text: str = "") -> NormalizedEvent:
    kind, publisher, domain, primary, quality = origin(event.source_url, event.source, event.source_type)
    text = f"{event.title} {event.summary} {raw_text}".lower()
    job = event.source_type == "jobs"
    matches: dict[str, list[str]] = {theme: [term for term in terms if term in text] for theme, terms in THEMES.items()}
    matches = {theme: terms for theme, terms in matches.items() if terms}
    irrelevant = any(term in text for term in IRRELEVANT_TERMS)
    # A job needs title/description evidence; the employer's name never triggers a theme.
    if job:
        for theme, terms in list(matches.items()):
            title_hits = [term for term in terms if term in event.title.lower()]
            if not title_hits and len(terms) < 2:
                matches.pop(theme)
    if irrelevant:
        status, primary_theme, confidence, reasons = "irrelevant", "irrelevant", 0.95, ("命中无关内容规则",)
        themes = ("irrelevant",)
    elif not matches:
        status, primary_theme, confidence, reasons = ("irrelevant", "no_theme_match", 0.85, ("未命中投资主题词",)) if job else ("uncertain", "needs_review", 0.25, ("无明确主题证据",))
        themes = (primary_theme,)
    else:
        ranked = sorted(matches, key=lambda item: (len(matches[item]), item), reverse=True)
        primary_theme, secondary = ranked[0], tuple(ranked[1:])
        total_hits = len(matches[primary_theme])
        confidence = min(0.95, 0.55 + 0.15 * total_hits + (0.10 if primary == "primary" else 0))
        status = "relevant" if confidence >= 0.65 else "uncertain"
        reasons = tuple(f"命中 {primary_theme} 术语：{', '.join(matches[primary_theme])}",)
        themes = (primary_theme, *secondary) if status == "relevant" else ("needs_review",)
    metadata = job_metadata(event.title, raw_text or event.summary, publisher, event.observed_at) if job else {}
    assignment = "assigned" if status == "relevant" else "no_theme_match" if primary_theme in {"irrelevant", "no_theme_match"} else "needs_review"
    return replace(event, source_quality=quality, discovery_source=event.source, origin_source_type=kind, publisher=publisher, publisher_domain=domain, primary_or_secondary=primary, relevance_status=status, theme_assignment_status=assignment, primary_theme=primary_theme, secondary_themes=tuple(theme for theme in themes if theme != primary_theme and theme not in {"irrelevant", "needs_review", "no_theme_match"}), classification_confidence=confidence, classification_reasons=reasons, matched_terms=tuple(term for terms in matches.values() for term in terms), themes=themes, theme_relevance=confidence if status == "relevant" else 0.0, **metadata)


def event_from_row(row: dict) -> NormalizedEvent:
    def array(name: str) -> tuple[str, ...]:
        value = row.get(name) or "[]"
        return tuple(json.loads(value)) if isinstance(value, str) else tuple(value)
    return NormalizedEvent(
        event_id=row["event_id"], source=row["source"], source_url=row["source_url"], source_type=row["source_type"], title=row["title"], summary=row["summary"], published_at=row["published_at"], observed_at=row["observed_at"], themes=array("themes"), companies=array("companies"), tickers=array("tickers"), source_quality=row["source_quality"], extraction_confidence=row["extraction_confidence"], raw_content_hash=row["raw_content_hash"],
    )


def reclassify_store(store) -> dict[str, int]:
    with MAINTENANCE_LOCK:
        counts = {"processed": 0, "relevant": 0, "irrelevant": 0, "uncertain": 0}
        for row in store.events():
            event = classify(event_from_row(row), store.raw_text(row["raw_content_hash"]))
            store.replace_event(event)
            counts["processed"] += 1
            counts[event.relevance_status] += 1
            # Ten rows stays below the heartbeat interval even when raw
            # documents are large, while avoiding a commit per event.
            if counts["processed"] % 10 == 0:
                store.commit()
        store.commit()
        return counts
