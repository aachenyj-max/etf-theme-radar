from __future__ import annotations

import json
from pathlib import Path

from etf_theme_radar.evidence_summary_backfill import backfill_evidence_summaries, _hydrate_historical_cards
from etf_theme_radar.models import RawDocument
from etf_theme_radar.official_connectors import OfficialEtfHoldingsConnector
from etf_theme_radar.store import EvidenceStore
from etf_theme_radar.theme_research import (
    LEGACY_EVIDENCE_SUMMARY,
    _fallback_chinese_evidence,
    _llm_evidence_analysis,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _legacy_card(evidence_id: str = "e-1") -> dict:
    return {
        "evidence_id": evidence_id,
        "publisher": "TD Securities",
        "source_type": "unknown",
        "claim": "AI Infrastructure: Reframing the GPU vs. ASIC Debate",
        "excerpt": (
            "By: Joshua Buchalter, Sean O'Loughlin May 30, 2025 - 5 minutes. "
            "The report reframes GPU vs. ASIC as a build vs. buy decision."
        ),
        "publication_date": None,
        "source_url": "https://example.com/article",
        "zh_fact_summary": (
            "该条记录来自 TD Securities，已按主题相关性和来源质量完成确定性筛选；"
            "具体原文通过来源按钮访问。"
        ),
        "fact_summary": "Original summary",
        "research_implication": "继续核验。",
        "limitation": "需要独立来源复核。",
    }


def test_deterministic_summary_uses_verified_date_and_author() -> None:
    summary = _fallback_chinese_evidence(_legacy_card())["zh_fact_summary"]

    assert summary.startswith("2025年5月30日，Joshua Buchalter, Sean O'Loughlin")
    assert LEGACY_EVIDENCE_SUMMARY not in summary
    assert "地点未知" not in summary

    social = _fallback_chinese_evidence({
        "evidence_id": "social-1", "publisher": "x.com", "source_type": "social",
        "claim": "Depth Anything 3", "excerpt": "Author: Ilir Aliu (@IlirAliu_) [verified] | Posted: Sat Nov 15 09:13:16 +0000 2025",
    })["zh_fact_summary"]
    assert social.startswith("2025年11月15日，Ilir Aliu (@IlirAliu_)")


def test_llm_analysis_deduplicates_ids_and_degrades_only_invalid_item(monkeypatch) -> None:
    captured = {}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self):
            return json.dumps({"choices": [{"message": {"content": json.dumps({"analyses": [
                {"evidence_id": "e-1", "zh_title": "AI 基础设施观点", "zh_fact_summary": "2025年1月1日，机构讨论 GPU 与 ASIC 的部署取舍。", "research_implication": "该观点需要独立证据复核。"},
                {"evidence_id": "e-2", "zh_title": "无效条目", "zh_fact_summary": "机构预计增长 999%。", "research_implication": "包含输入中不存在的数字。"},
            ]}, ensure_ascii=False)}}]}).encode()

    def fake_urlopen(request, **_kwargs):
        captured.update(json.loads(request.data))
        return Response()
    monkeypatch.setattr("etf_theme_radar.theme_research.urlopen", fake_urlopen)
    first = {**_legacy_card("e-1"), "excerpt": "GPU 与 ASIC", "publication_date": "2025-01-01"}
    second = {**_legacy_card("e-2"), "excerpt": "不含数字"}
    result, note = _llm_evidence_analysis([first, first, second], {"api_key": "test", "base_url": "https://example.com", "model": "test"})

    assert list(result) == ["e-1"]
    assert result["e-1"]["summary_schema_version"] == 5
    assert note == "1 条重点证据未通过逐条审计，已使用规则化分析"
    sent_items = json.loads(captured["messages"][1]["content"])
    assert len(sent_items) == 2
    assert "zh_fact_summary" not in sent_items[0]
    assert sent_items[0]["verified_publication_date"] == "2025年1月1日"


def test_historical_hydration_rejects_evidence_observed_after_report() -> None:
    cards = [
        {"evidence_id": "past", "excerpt": "truncated"},
        {"evidence_id": "future", "excerpt": "frozen"},
    ]
    events = {
        "past": {"event_id": "past", "summary": "complete historical text", "observed_at": "2026-08-02T00:00:00+00:00", "publisher": "Past"},
        "future": {"event_id": "future", "summary": "future text", "observed_at": "2026-08-04T00:00:00+00:00", "publisher": "Future"},
    }

    hydrated = _hydrate_historical_cards(cards, events, "2026-08-03T00:00:00+00:00")

    assert hydrated == ["past"]
    assert cards[0]["excerpt"] == "complete historical text"
    assert cards[1]["excerpt"] == "frozen"


def test_backfill_appends_immutable_version_and_is_idempotent(tmp_path) -> None:
    store = EvidenceStore(tmp_path / "reports.db")
    created = "2026-08-03T00:00:00+00:00"
    report_id = "report:test"
    asset = {
        "report_id": report_id, "run_id": "run:test", "title": "AI 基础设施主题研究",
        "kind": "theme_report", "theme_id": "ai", "folder_id": "ai", "status": "watch",
        "tags": ["AI"], "summary": "摘要", "updated_at": created, "created_at": created,
        "version": 1, "source_count": 1, "evidence_count": 1, "audit_passed": True,
    }
    card = _legacy_card()
    result = {
        "brief": {"key_evidence": [card]},
        "detail": {"counter": {"counter_evidence": [{**card, "reason": "风险语境"}]}},
        "audit": {}, "report_markdown": "## 五条重点证据分析\n- 发生了什么：Original summary",
    }
    store.save_report_asset(asset)
    store.save_report_version(report_id, 1, {"asset": asset, "result": result}, result["report_markdown"], created)
    store.save_report_claim(f"{report_id}:v1:c1", report_id, 1, "主题观点", "support", ["e-1"], created)
    original_hash = store.report_versions(report_id)[0]["content_hash"]

    outcome = backfill_evidence_summaries(store, apply=True)
    versions = store.report_versions(report_id)

    assert outcome["updated"] == 1
    assert [item["version"] for item in versions] == [2, 1]
    assert versions[1]["content_hash"] == original_hash
    assert LEGACY_EVIDENCE_SUMMARY not in versions[0]["payload"]["result"]["brief"]["key_evidence"][0]["zh_fact_summary"]
    assert versions[0]["payload"]["result"]["audit"]["evidence_summary_schema_version"] == 5
    assert store.report_claims(report_id, 2)[0]["evidence_ids"] == ["e-1"]
    assert store.report_asset(report_id)["version"] == 2

    again = backfill_evidence_summaries(store, apply=True)
    assert again["updated"] == 0
    assert len(store.report_versions(report_id)) == 2
    store.close()


def test_title_equals_summary_baseline_fixture_is_deidentified() -> None:
    sample = json.loads((FIXTURES / "title_equals_summary.json").read_text(encoding="utf-8"))

    assert sample["title"] == sample["summary"]
    assert sample["expected_issue"] == "title_equals_summary"
    assert sample["source_url"].startswith("https://")
    assert ".invalid/" in sample["source_url"]
    assert not ({"account", "email", "token", "cookie"} & set(sample))


def test_holdings_navigation_noise_baseline_fixture_reproduces_parser_pollution(tmp_path) -> None:
    source_url = "https://issuer.example.invalid/funds/sample/holdings"
    connector = OfficialEtfHoldingsConnector(
        tmp_path / "holdings",
        feeds=[{"ticker": "SAMP", "url": source_url, "format": "html"}],
    )
    connector.records[source_url] = connector.feeds[0]
    document = RawDocument(
        source="official_etf_holdings",
        source_url=source_url,
        title="SAMP official holdings",
        text=(FIXTURES / "holdings_navigation_noise.html").read_text(encoding="utf-8"),
        source_type="etf",
    )

    summary = connector.normalize(document)[0].summary

    assert "Home Products Research Insights" in summary
    assert "Sample Semiconductor" in summary
    assert "10.50%" in summary
