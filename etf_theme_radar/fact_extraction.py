"""Evidence-bound deterministic facts and validation for model enrichments."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .models import utcnow


PARSER_VERSION = "fact-extraction-v1"
_ACTION_PATTERN = re.compile(
    r"\b(?:announc(?:e|ed|es|ing)|publish(?:ed|es|ing)?|launch(?:ed|es|ing)?|"
    r"expand(?:ed|s|ing)?|deploy(?:ed|s|ing)?|disclos(?:e|ed|es|ing)|"
    r"report(?:ed|s|ing)?|describe(?:d|s|ing)?|file(?:d|s|ing)?|hire(?:d|s|ing)?|"
    r"acquir(?:e|ed|es|ing))\b|发布|宣布|披露|推出|扩建|部署|招聘|收购|提交|发表|新增|建设",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(
    r"(?:[$¥￥]\s*)?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:%|percent|billion|million|trillion|亿元|万元|亿|万))?",
    re.IGNORECASE,
)


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


def find_action(text: str) -> str:
    match = _ACTION_PATTERN.search(str(text or ""))
    if not match:
        return ""
    value = match.group(0)
    return value.casefold() if value.isascii() else value


def extract_numbers(text: str) -> tuple[str, ...]:
    without_dates = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", str(text or ""))
    values: list[str] = []
    for match in _NUMBER_PATTERN.finditer(without_dates):
        value = re.sub(r"\s+", " ", match.group(0)).strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def _industry_chain_position(text: str) -> str:
    normalized = text.casefold()
    if re.search(r"production line|manufactur|factory|fabrication|\bfab\b|产线|制造|工厂|量产", normalized):
        return "manufacturing"
    if re.search(r"research|patent|r&d|研发|专利|论文", normalized):
        return "research_and_development"
    if re.search(r"distribution|sales|retail|deployment|销售|渠道|部署", normalized):
        return "downstream"
    if re.search(r"raw material|mining|矿产|原材料", normalized):
        return "upstream"
    return "unknown"


@dataclass(frozen=True)
class ExtractedFact:
    event_id: str
    content_hash: str
    parser_version: str
    status: str
    subject: str
    occurred_at: str
    action: str
    numbers: tuple[str, ...]
    domain: str
    location: str
    industry_chain_position: str
    audit_errors: tuple[str, ...]
    extracted_at: str

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id, "content_hash": self.content_hash,
            "parser_version": self.parser_version, "status": self.status,
            "subject": self.subject, "occurred_at": self.occurred_at,
            "action": self.action, "numbers": list(self.numbers), "domain": self.domain,
            "location": self.location, "industry_chain_position": self.industry_chain_position,
            "audit_errors": list(self.audit_errors), "extracted_at": self.extracted_at,
        }


def extract_facts(event: dict, raw_text: str, *, extracted_at: str | None = None) -> ExtractedFact:
    companies = _items(event.get("companies"))
    subject = next((item for item in [*companies, str(event.get("company_id") or "").strip(), str(event.get("publisher") or "").strip()] if item), "")
    published = str(event.get("published_at") or "").strip()
    occurred_at = published[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", published) else ""
    combined = f"{event.get('summary') or ''} {raw_text or ''}"
    action = find_action(combined)
    primary_theme = str(event.get("primary_theme") or "").strip()
    themes = _items(event.get("themes"))
    domain = primary_theme if primary_theme not in {"", "unknown", "no_theme_match", "needs_review"} else (themes[0] if themes else "unknown")
    errors = tuple(
        error for missing, error in ((not subject, "missing_subject"), (not action, "missing_action"))
        if missing
    )
    return ExtractedFact(
        event_id=str(event.get("event_id") or ""),
        content_hash=str(event.get("raw_content_hash") or ""),
        parser_version=PARSER_VERSION,
        status="audited" if not errors else "incomplete",
        subject=subject,
        occurred_at=occurred_at,
        action=action,
        numbers=extract_numbers(raw_text),
        domain=domain,
        location=str(event.get("location") or "").strip(),
        industry_chain_position=_industry_chain_position(combined),
        audit_errors=errors,
        extracted_at=extracted_at or utcnow(),
    )


@dataclass(frozen=True)
class ModelFactAudit:
    accepted: dict[str, dict]
    item_audits: dict[str, dict]
    errors: tuple[str, ...]


def audit_model_fact_extractions(inputs: list[dict], outputs: list[dict]) -> ModelFactAudit:
    input_by_id = {str(item.get("evidence_id") or ""): item for item in inputs}
    output_ids = [str(item.get("evidence_id") or "") for item in outputs]
    identity_errors: list[str] = []
    for evidence_id in dict.fromkeys(output_ids):
        if evidence_id and output_ids.count(evidence_id) > 1:
            identity_errors.append(f"duplicate_output_id:{evidence_id}")
    for evidence_id in input_by_id:
        if output_ids.count(evidence_id) == 0:
            identity_errors.append(f"missing_output_id:{evidence_id}")
    for evidence_id in output_ids:
        if evidence_id not in input_by_id:
            identity_errors.append(f"unknown_output_id:{evidence_id}")
    if len(outputs) != len(inputs) and not identity_errors:
        identity_errors.append(f"item_count_mismatch:{len(inputs)}:{len(outputs)}")
    if identity_errors:
        return ModelFactAudit({}, {}, tuple(identity_errors))

    accepted: dict[str, dict] = {}
    item_audits: dict[str, dict] = {}
    errors: list[str] = []
    for output in outputs:
        evidence_id = str(output["evidence_id"])
        allowed_numbers = set(extract_numbers(str(input_by_id[evidence_id].get("raw_text") or "")))
        invalid = [
            f"number_not_in_input:{number}" for number in output.get("numbers", [])
            if str(number) not in allowed_numbers
        ]
        if invalid:
            item_audits[evidence_id] = {"status": "rejected", "errors": invalid}
            errors.extend(f"{evidence_id}:{error}" for error in invalid)
        else:
            accepted[evidence_id] = output
            item_audits[evidence_id] = {"status": "accepted", "errors": []}
    return ModelFactAudit(accepted, item_audits, tuple(errors))

