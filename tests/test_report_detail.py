from etf_theme_radar.api import _report_detail_payload


def _asset() -> dict:
    return {
        "report_id": "report:test",
        "run_id": "run:test",
        "title": "AI 基础设施主题研究",
        "theme_id": "ai-infrastructure",
        "status": "watch",
        "summary": "治理后研究摘要。",
        "updated_at": "2026-07-24T00:00:00Z",
        "version": 2,
        "source_count": 3,
        "audit_passed": 1,
    }


def test_report_detail_keeps_citations_and_unknown_landscape() -> None:
    run = {
        "result": {
            "status": "WATCH",
            "brief": {
                "source_types": 3,
                "first_party": 2,
                "key_evidence": [{
                    "evidence_id": "e-1",
                    "source_url": "https://www.sec.gov/example",
                    "publisher": "SEC",
                    "source_type": "regulatory",
                    "claim": "监管文件披露基础设施投入。",
                    "fact_summary": "原始事实摘要。",
                    "limitation": "不能据此推导收入。",
                    "classification_confidence": 0.95,
                }],
            },
            "detail": {
                "hypothesis": {"hypothesis": "主题值得持续核验。"},
                "counter": {"missing_evidence": ["ETF 持仓重叠"]},
                "investability": {"identified_public_companies": []},
                "landscape": {"similar_etfs": [], "overlap_status": "unknown", "product_white_space": "unknown"},
            },
            "audit": {"passed": True},
        }
    }

    detail = _report_detail_payload(_asset(), run)

    assert detail["bullCase"][0]["url"] == "https://www.sec.gov/example"
    assert detail["bullCase"][0]["evidenceId"] == "e-1"
    assert detail["etfLandscape"]["dataStatus"] == "unknown"
    assert detail["etfLandscape"]["whiteSpace"] == "unknown"
    assert detail["companyMap"]["purePlays"] == []
    assert detail["decision"]["currentStatus"] == "WATCH"
    assert detail["conclusion"]["verdict"] == "mixed"


def test_report_detail_does_not_invent_company_mapping() -> None:
    detail = _report_detail_payload(_asset(), None)

    assert detail["confidence"] == "medium"
    assert detail["companyMap"]["dataStatus"] == "unknown"
    assert detail["companyMap"]["purePlays"] == []
    assert detail["companyMap"]["enablers"] == []
    assert "不足" in detail["mainRisks"][0]


def test_counter_arguments_are_structured_without_evidence_id() -> None:
    run = {
        "result": {
            "detail": {
                "counter": {
                    "conflicting_evidence": [{
                        "evidence_id": "secret-internal-id",
                        "claim": "商业化可能延迟。",
                        "reason": "成本尚未下降。",
                        "source_url": "https://example.com/counter",
                        "publisher": "Example",
                    }]
                },
                "landscape": {"similar_etfs": []},
            }
        }
    }
    detail = _report_detail_payload(_asset(), run)
    argument = detail["bearCase"]["counterArguments"][0]
    assert argument == {
        "claim": "商业化可能延迟。",
        "reason": "成本尚未下降。",
        "sourceUrl": "https://example.com/counter",
        "publisher": "Example",
    }
    assert "evidence_id" not in argument


def test_legacy_stringified_counter_argument_is_normalized() -> None:
    run = {
        "result": {
            "detail": {
                "counter": {
                    "conflicting_evidence": [
                        "{'evidence_id': 'hidden', 'claim': '成本可能超支。', "
                        "'reason': '历史项目存在延期。', 'source_url': 'https://example.com/risk'}"
                    ]
                },
                "landscape": {"similar_etfs": []},
            }
        }
    }
    argument = _report_detail_payload(_asset(), run)["bearCase"]["counterArguments"][0]
    assert argument["claim"] == "成本可能超支。"
    assert argument["sourceUrl"] == "https://example.com/risk"
    assert "evidence_id" not in argument


def test_legacy_generic_evidence_summary_is_not_exposed() -> None:
    run = {
        "result": {
            "brief": {
                "key_evidence": [{
                    "evidence_id": "e-legacy", "publisher": "TD Securities",
                    "source_type": "unknown", "source_url": "https://example.com/article",
                    "claim": "AI Infrastructure: Reframing the GPU vs. ASIC Debate",
                    "excerpt": "By: Joshua Buchalter May 30, 2025 - 5 minutes",
                    "zh_fact_summary": "该条记录来自 TD Securities，已按主题相关性和来源质量完成确定性筛选；具体原文通过来源按钮访问。",
                    "limitation": "需要复核。", "classification_confidence": 0.9,
                }]
            },
            "detail": {"counter": {}, "landscape": {"similar_etfs": []}},
        }
    }

    evidence = _report_detail_payload(_asset(), run)["bullCase"][0]["evidence"]
    assert evidence.startswith("2025年5月30日，Joshua Buchalter")
    assert "已按主题相关性" not in evidence
