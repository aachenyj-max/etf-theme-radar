"""Deterministic completeness checks for evidence entering publishable flows."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .models import utcnow


PARSER_VERSION = "content-quality-v1"
_BOILERPLATE_TAGS = {"nav", "footer", "header", "aside"}
_IGNORED_TAGS = {"script", "style", "noscript"}
_ACTION_PATTERN = re.compile(
    r"\b(?:announc(?:e|ed|es|ing)|publish(?:ed|es|ing)?|launch(?:ed|es|ing)?|"
    r"expand(?:ed|s|ing)?|deploy(?:ed|s|ing)?|disclos(?:e|ed|es|ing)|"
    r"report(?:ed|s|ing)?|describe(?:d|s|ing)?|file(?:d|s|ing)?|hire(?:d|s|ing)?|acquir(?:e|ed|es|ing))\b|"
    r"发布|宣布|披露|推出|扩建|部署|招聘|收购|提交|发表|新增|建设",
    re.IGNORECASE,
)


def _quality_defaults() -> dict[str, float]:
    values: dict[str, float] = {}
    section = ""
    path = Path(__file__).parents[1] / "config" / "defaults.yaml"
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" ") and raw.rstrip().endswith(":"):
            section = raw.strip()[:-1]
            continue
        if section == "content_quality" and ":" in raw:
            key, value = raw.strip().split(":", 1)
            values[key] = float(value.strip())
    return values


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.visible: list[str] = []
        self.boilerplate: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        self.stack.append(tag.casefold())

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self.stack:
            reverse_index = self.stack[::-1].index(normalized)
            del self.stack[len(self.stack) - reverse_index - 1:]

    def handle_data(self, data: str) -> None:
        if any(tag in _IGNORED_TAGS for tag in self.stack):
            return
        normalized = re.sub(r"\s+", " ", data).strip()
        if not normalized:
            return
        self.visible.append(normalized)
        if any(tag in _BOILERPLATE_TAGS for tag in self.stack):
            self.boilerplate.append(normalized)


def _visible_text(raw_text: str) -> tuple[str, int]:
    if not re.search(r"<\s*[a-zA-Z][^>]*>", raw_text):
        return re.sub(r"\s+", " ", raw_text).strip(), 0
    parser = _VisibleTextParser()
    parser.feed(raw_text)
    visible = " ".join(parser.visible)
    boilerplate = " ".join(parser.boilerplate)
    return visible, len(boilerplate)


def _items(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            return [value.strip()]
    return []


@dataclass(frozen=True)
class ContentQualityResult:
    event_id: str
    content_hash: str
    parser_version: str
    status: str
    missing_fields: tuple[str, ...]
    issues: tuple[str, ...]
    metrics: dict[str, int | float]
    evaluated_at: str

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "content_hash": self.content_hash,
            "parser_version": self.parser_version,
            "status": self.status,
            "missing_fields": list(self.missing_fields),
            "issues": list(self.issues),
            "metrics": self.metrics,
            "evaluated_at": self.evaluated_at,
        }


def evaluate_content_quality(
    event: dict, raw_text: str, *, evaluated_at: str | None = None,
) -> ContentQualityResult:
    defaults = _quality_defaults()
    title = re.sub(r"\s+", " ", str(event.get("title") or "")).strip()
    summary = re.sub(r"\s+", " ", str(event.get("summary") or "")).strip()
    raw = str(raw_text or "")
    visible, boilerplate_chars = _visible_text(raw)
    metrics: dict[str, int | float] = {
        "raw_text_chars": len(visible),
        "summary_chars": len(summary),
        "boilerplate_chars": boilerplate_chars,
        "boilerplate_ratio": round(boilerplate_chars / max(1, len(visible)), 4),
    }
    if not visible:
        return ContentQualityResult(
            event_id=str(event.get("event_id") or ""),
            content_hash=str(event.get("raw_content_hash") or ""),
            parser_version=PARSER_VERSION,
            status="rejected",
            missing_fields=("raw_text",),
            issues=("empty_body",),
            metrics=metrics,
            evaluated_at=evaluated_at or utcnow(),
        )

    missing: list[str] = []
    issues: list[str] = []
    if not title:
        missing.append("title")
        issues.append("missing_title")
    if not summary:
        missing.append("summary")
        issues.append("missing_summary")
    elif title and title.casefold() == summary.casefold():
        missing.append("distinct_summary")
        issues.append("title_equals_summary")
    subjects = [
        *_items(event.get("companies")),
        str(event.get("company_id") or "").strip(),
        str(event.get("publisher") or "").strip(),
    ]
    if not any(subjects):
        missing.append("event_subject")
        issues.append("missing_event_subject")
    if not _ACTION_PATTERN.search(f"{summary} {visible}"):
        missing.append("event_action")
        issues.append("missing_event_action")
    maximum_ratio = defaults.get("maximum_boilerplate_ratio", 0.25)
    if metrics["boilerplate_ratio"] > maximum_ratio:
        missing.append("clean_body")
        issues.append("boilerplate_ratio_exceeded")
    return ContentQualityResult(
        event_id=str(event.get("event_id") or ""),
        content_hash=str(event.get("raw_content_hash") or ""),
        parser_version=PARSER_VERSION,
        status="publishable" if not issues else "needs_enrichment",
        missing_fields=tuple(missing),
        issues=tuple(issues),
        metrics=metrics,
        evaluated_at=evaluated_at or utcnow(),
    )
