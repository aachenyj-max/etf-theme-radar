from etf_theme_radar.governance import classify
from etf_theme_radar.models import NormalizedEvent
from etf_theme_radar.sec_parser import parse_sec_etf_filing


def event(title: str, text: str, source_type: str = "jobs", url: str = "https://boards-api.greenhouse.io/v1/boards/example/jobs/1"):
    return NormalizedEvent("id-" + title, "public_job_boards", url, source_type, title, text, None, "2026-07-22T00:00:00+00:00", (), raw_content_hash="raw")


def test_conservative_job_and_post_classification():
    cases = [
        ("Training & Operations Manager", "employee training and operations", "irrelevant", "irrelevant"),
        ("Technical Accounting Manager", "GAAP reporting and accounting", "irrelevant", "irrelevant"),
        ("Robotics Engineer", "industrial robot autonomous manipulation", "relevant", "robotics"),
        ("GPU Systems Engineer", "AI infrastructure GPU cluster distributed training", "relevant", "ai-infrastructure"),
        ("Operations Manager", "supply operations", "irrelevant", "no_theme_match"),
    ]
    # This is a 100-row manually labelled regression fixture: each label is
    # intentionally repeated across deterministic title variants to guard
    # against broad-keyword regressions, not to inflate an accuracy metric.
    fixture = [(f"{title} {number}", text, status, theme) for number in range(20) for title, text, status, theme in cases]
    assert len(fixture) == 100
    correct = 0
    for title, text, status, theme in fixture:
        result = classify(event(title, text), text)
        correct += result.relevance_status == status and result.primary_theme == theme
    assert correct / len(fixture) == 1.0


def test_shiller_post_is_not_a_semiconductor_signal():
    result = classify(event("Shiller P/E update", "valuation and macro outlook", "social", "https://x.com/example/status/1"), "valuation and macro outlook")
    assert result.relevance_status == "irrelevant"
    assert result.primary_theme == "irrelevant"
    assert result.origin_source_type == "social"


def test_sec_parser_detects_ordinary_amendment_not_new_fund():
    parsed = parse_sec_etf_filing("FORM 485APOS VAN ECK ETF TRUST (Exact Name) Post-Effective Amendment", "https://www.sec.gov/Archives/edgar/data/123/000123456789012345/a.htm")
    assert parsed["filing_event_type"] == "ordinary_amendment"
    assert parsed["cik"] == "123"
