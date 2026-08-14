from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from etf_theme_radar.evidence_summary_backfill import backfill_historical_extractions
from etf_theme_radar.models import NormalizedEvent, RawDocument
from etf_theme_radar.store import EvidenceStore


def _raw(name: str) -> RawDocument:
    return RawDocument(
        source="fixture",
        source_url=f"https://example.com/{name}",
        title=f"{name} capacity update",
        text=f"Sample Semiconductor announced a new {name} production line in Singapore with 10.50% more capacity.",
        source_type="official",
        published_at="2026-07-31T00:00:00+00:00",
        retrieved_at="2026-08-01T00:00:00+00:00",
    )


def _event(event_id: str, raw: RawDocument) -> NormalizedEvent:
    return NormalizedEvent(
        event_id, "fixture", raw.source_url, "official", raw.title,
        f"Sample Semiconductor announced a new {event_id} production line.",
        raw.published_at, "2026-08-01T00:00:00+00:00", ("semiconductors",),
        companies=("Sample Semiconductor",), raw_content_hash=raw.content_hash,
        origin_source_type="official", publisher="Sample Semiconductor",
        publisher_domain="example.com", primary_or_secondary="primary",
        relevance_status="relevant", theme_assignment_status="assigned",
        primary_theme="semiconductors", classification_confidence=.9,
        location="Singapore",
    )


def test_copied_database_backfill_is_resumable_idempotent_and_preserves_raw_text(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    source = EvidenceStore(source_path)
    raw_a, raw_b = _raw("alpha"), _raw("beta")
    for event_id, raw in (("event-a", raw_a), ("event-b", raw_b)):
        source.save_raw(raw)
        source.save_event(_event(event_id, raw))
    source.commit()
    source.close()

    drill_path = tmp_path / "drill.db"
    shutil.copy2(source_path, drill_path)
    drill = EvidenceStore(drill_path)
    original_raw = {
        raw_a.content_hash: drill.raw_text(raw_a.content_hash),
        raw_b.content_hash: drill.raw_text(raw_b.content_hash),
    }

    first = backfill_historical_extractions(drill, apply=True, limit=1)
    second = backfill_historical_extractions(
        drill, apply=True, resume_after=first["recovery_point"], limit=1,
    )
    replay = backfill_historical_extractions(drill, apply=True)

    assert first == {
        "mode": "apply", "scanned": 1, "processed": 1, "effective_increment": 1,
        "skipped_current": 0, "failed": [], "failure_reasons": {},
        "recovery_point": "event-a", "has_more": True,
    }
    assert second["processed"] == 1
    assert second["effective_increment"] == 1
    assert second["recovery_point"] == "event-b"
    assert second["has_more"] is False
    assert replay["processed"] == 0
    assert replay["skipped_current"] == 2
    assert drill.content_quality_result("event-a")["parser_version"] == "content-quality-v1"
    assert drill.extracted_fact("event-b")["parser_version"] == "fact-extraction-v1"
    assert {content_hash: drill.raw_text(content_hash) for content_hash in original_raw} == original_raw
    drill.close()

    untouched = EvidenceStore(source_path)
    assert untouched.content_quality_result("event-a") is None
    assert untouched.extracted_fact("event-b") is None
    untouched.close()


def test_backfill_failure_enters_exception_queue_and_resolves_after_raw_is_restored(tmp_path: Path) -> None:
    database = tmp_path / "recovery.db"
    raw = _raw("recovered")
    store = EvidenceStore(database)
    store.save_event(_event("event-missing", raw))
    store.commit()

    failed = backfill_historical_extractions(store, apply=True)

    assert failed["processed"] == 0
    assert failed["failure_reasons"] == {"missing_raw_document": 1}
    assert failed["failed"] == [{"event_id": "event-missing", "reason": "missing_raw_document"}]
    exception = store.extraction_exceptions("open")[0]
    assert exception["event_id"] == "event-missing"
    assert exception["attempt"] == 1
    assert store.content_quality_result("event-missing") is None

    store.save_raw(raw)
    store.commit()
    recovered = backfill_historical_extractions(store, apply=True)

    assert recovered["processed"] == 1
    assert recovered["effective_increment"] == 1
    assert store.extraction_exceptions("open") == []
    assert store.extraction_exceptions("resolved")[0]["event_id"] == "event-missing"
    assert store.raw_text(raw.content_hash) == raw.text
    store.close()


def test_extraction_backfill_cli_reports_copy_drill_statistics(tmp_path: Path) -> None:
    database = tmp_path / "cli-drill.db"
    raw = _raw("cli")
    store = EvidenceStore(database)
    store.save_raw(raw)
    store.save_event(_event("event-cli", raw))
    store.commit()
    store.close()

    completed = subprocess.run(
        [
            sys.executable, "-m", "etf_theme_radar.cli", "backfill-evidence-extractions",
            "--db", str(database), "--apply", "--limit", "1",
        ],
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    result = json.loads(completed.stdout.decode("utf-8"))
    assert result["processed"] == 1
    assert result["effective_increment"] == 1
    assert result["recovery_point"] == "event-cli"


def test_failed_write_does_not_report_or_persist_effective_increment(tmp_path: Path, monkeypatch) -> None:
    store = EvidenceStore(tmp_path / "write-failure.db")
    raw = _raw("write-failure")
    store.save_raw(raw)
    store.save_event(_event("event-write-failure", raw))
    store.commit()

    def fail_fact_write(_item: dict) -> None:
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(store, "save_extracted_fact", fail_fact_write)
    outcome = backfill_historical_extractions(store, apply=True)

    assert outcome["processed"] == 0
    assert outcome["effective_increment"] == 0
    assert outcome["failure_reasons"] == {"RuntimeError": 1}
    assert store.content_quality_result("event-write-failure") is None
    assert store.extraction_exceptions("open")[0]["error"] == "simulated write failure"
    store.close()
