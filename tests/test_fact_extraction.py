from __future__ import annotations

from datetime import date
from pathlib import Path

from etf_theme_radar.connectors import FixtureConnector
from etf_theme_radar.fact_extraction import audit_model_fact_extractions, extract_facts
from etf_theme_radar.pipeline import ingest
from etf_theme_radar.store import EvidenceStore


FIXTURES = Path(__file__).parent / "fixtures"


def _event(**overrides) -> dict:
    item = {
        "event_id": "e-1",
        "title": "Sample Semiconductor expands advanced packaging capacity",
        "summary": "Sample Semiconductor announced a new production line.",
        "published_at": "2026-07-31T08:00:00+00:00",
        "companies": ["Sample Semiconductor"],
        "publisher": "Sample Semiconductor",
        "primary_theme": "semiconductors",
        "themes": ["semiconductors"],
        "location": "Singapore",
        "raw_content_hash": "hash-1",
    }
    item.update(overrides)
    return item


def test_deterministic_extraction_uses_only_frozen_event_and_raw_text() -> None:
    fact = extract_facts(
        _event(),
        "On 2026-07-31, Sample Semiconductor announced a new production line in Singapore "
        "with 10.50% more capacity and a $2.4 billion budget.",
        extracted_at="2026-08-14T00:00:00+00:00",
    )

    assert fact.subject == "Sample Semiconductor"
    assert fact.occurred_at == "2026-07-31"
    assert fact.action == "announced"
    assert fact.numbers == ("10.50%", "$2.4 billion")
    assert fact.domain == "semiconductors"
    assert fact.location == "Singapore"
    assert fact.industry_chain_position == "manufacturing"
    assert fact.status == "audited"
    assert fact.audit_errors == ()
    assert fact.extracted_at == "2026-08-14T00:00:00+00:00"


def test_unknown_optional_fact_fields_remain_unknown_instead_of_being_invented() -> None:
    fact = extract_facts(
        _event(
            published_at=None, companies=[], publisher="", primary_theme="unknown",
            themes=[], location="", summary="Technology market context.",
        ),
        "Technology market context without an explicit actor or event.",
    )

    assert fact.subject == ""
    assert fact.occurred_at == ""
    assert fact.action == ""
    assert fact.numbers == ()
    assert fact.domain == "unknown"
    assert fact.location == ""
    assert fact.industry_chain_position == "unknown"
    assert fact.status == "incomplete"
    assert fact.audit_errors == ("missing_subject", "missing_action")


def test_model_fact_output_is_bound_to_input_ids_and_existing_numbers() -> None:
    inputs = [
        {"evidence_id": "e-1", "raw_text": "Sample announced capacity growth of 10.50%."},
        {"evidence_id": "e-2", "raw_text": "Issuer reported revenue of $2.4 billion."},
    ]
    outputs = [
        {"evidence_id": "e-1", "subject": "Sample", "action": "announced", "numbers": ["10.50%"]},
        {"evidence_id": "e-2", "subject": "Issuer", "action": "reported", "numbers": ["$2.4 billion"]},
    ]

    audit = audit_model_fact_extractions(inputs, outputs)

    assert audit.errors == ()
    assert list(audit.accepted) == ["e-1", "e-2"]
    assert all(item["status"] == "accepted" for item in audit.item_audits.values())


def test_model_fact_batch_rejects_duplicate_or_missing_evidence_ids() -> None:
    inputs = [
        {"evidence_id": "e-1", "raw_text": "One"},
        {"evidence_id": "e-2", "raw_text": "Two"},
    ]
    outputs = [
        {"evidence_id": "e-1", "numbers": []},
        {"evidence_id": "e-1", "numbers": []},
    ]

    audit = audit_model_fact_extractions(inputs, outputs)

    assert audit.accepted == {}
    assert audit.errors == ("duplicate_output_id:e-1", "missing_output_id:e-2")


def test_model_fact_audit_rejects_only_item_with_number_absent_from_input() -> None:
    inputs = [
        {"evidence_id": "e-1", "raw_text": "Capacity grew 10.50%."},
        {"evidence_id": "e-2", "raw_text": "No numeric forecast was provided."},
    ]
    outputs = [
        {"evidence_id": "e-1", "numbers": ["10.50%"]},
        {"evidence_id": "e-2", "numbers": ["999%"]},
    ]

    audit = audit_model_fact_extractions(inputs, outputs)

    assert list(audit.accepted) == ["e-1"]
    assert audit.item_audits["e-2"] == {
        "status": "rejected",
        "errors": ["number_not_in_input:999%"],
    }
    assert audit.errors == ("e-2:number_not_in_input:999%",)


def test_ingest_persists_an_audited_fact_row_for_every_event(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "facts.db")

    outcome = ingest(
        FixtureConnector(FIXTURES / "events.json"), store,
        date(2025, 1, 1), date(2025, 1, 31),
    )

    assert outcome["events"] == 3
    facts = [store.extracted_fact(item["event_id"]) for item in store.events()]
    assert all(fact is not None for fact in facts)
    assert all(fact["parser_version"] == "fact-extraction-v1" for fact in facts if fact)
    assert all(fact["content_hash"] for fact in facts if fact)
    store.close()
